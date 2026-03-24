from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery.exceptions import Retry
from telegram import Bot

from bot.config import load_settings
from bot.database import AntiFloodSettings, BroadcastLog, SessionLocal, User, UserStatus, get_setting, init_db
from bot.locales import get_string
from bot.queue import claim_job_for_processing, claim_next_job, complete_job, fail_job, retry_job
from bot.queue.celery_app import get_celery_app
from bot.services import DownloadService
from bot.temp import cleanup_path, cleanup_stale_directories
from bot.utils.platforms import download_media

logger = logging.getLogger(__name__)

BASE_RETRY_DELAY_SECONDS = 30
BACKOFF_MULTIPLIER = 2
MAX_RETRY_DELAY_SECONDS = 300
celery_app = get_celery_app()
_worker_bot: Bot | None = None


def _get_worker_bot() -> Bot:
    global _worker_bot
    if _worker_bot is None:
        _worker_bot = Bot(token=load_settings().bot_token)
    return _worker_bot


def _retry_delay(attempts: int) -> int:
    return min(
        MAX_RETRY_DELAY_SECONDS,
        BASE_RETRY_DELAY_SECONDS * (BACKOFF_MULTIPLIER ** max(attempts - 1, 0)),
    )


async def _safe_delete_message(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        return


async def _safe_edit_message(bot: Bot, chat_id: int, message_id: int | None, text: str) -> None:
    if not message_id:
        await bot.send_message(chat_id=chat_id, text=text)
        return
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
    except Exception:
        await bot.send_message(chat_id=chat_id, text=text)


async def _process_download(bot: Bot, payload: dict) -> dict:
    user_id = int(payload["user_id"])
    chat_id = int(payload["chat_id"])
    url = payload["url"]
    platform = payload["platform"]
    lang = payload.get("lang") or "ar"
    status_message_id = payload.get("status_message_id")

    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(id=user_id).first()
        if not db_user:
            raise RuntimeError(f"User {user_id} not found")
        await bot.send_chat_action(chat_id=chat_id, action=get_setting("activity_status", "upload_video"))
        filepath, media_type, _title = await download_media(url, platform)
        if not filepath:
            error_text = get_setting(f"error_message_{lang}", get_setting("error_message", get_string("error", lang)))
            await _safe_edit_message(bot, chat_id, status_message_id, error_text)
            DownloadService.record_download_result(user_id=user_id, platform=platform, url=url, media_type="video", success=False)
            return {"status": "failed"}

        caption = DownloadService.build_caption(
            media_type=media_type,
            lang=lang,
            telegram_user=db_user,
            platform=platform,
        )
        main_markup, extra_markup = DownloadService.get_download_reply_markup()
        await _safe_delete_message(bot, chat_id, status_message_id)
        try:
            with open(filepath, "rb") as media_handle:
                if media_type == "photo":
                    await bot.send_photo(chat_id=chat_id, photo=media_handle, caption=caption, reply_markup=main_markup)
                elif media_type == "audio":
                    await bot.send_audio(chat_id=chat_id, audio=media_handle, caption=caption, reply_markup=main_markup)
                elif media_type == "document":
                    await bot.send_document(chat_id=chat_id, document=media_handle, caption=caption, reply_markup=main_markup)
                else:
                    await bot.send_video(chat_id=chat_id, video=media_handle, caption=caption, supports_streaming=True, reply_markup=main_markup)
            if extra_markup:
                await bot.send_message(chat_id=chat_id, text="⌨️", reply_markup=extra_markup)
            DownloadService.record_download_result(user_id=user_id, platform=platform, url=url, media_type=media_type, success=True)
            return {"status": "sent", "media_type": media_type}
        finally:
            cleanup_path(filepath)
    finally:
        db.close()


async def _process_broadcast(bot: Bot, payload: dict) -> dict:
    text = payload["text"]
    target = payload["target"]
    log_id = int(payload["broadcast_log_id"])
    offset = int(payload.get("offset", 0))
    settings = load_settings()
    db = SessionLocal()
    sent = 0
    failed = 0
    try:
        if target != "users":
            raise RuntimeError(f"Unsupported broadcast target: {target}")
        antiflood = db.query(AntiFloodSettings).first()
        delay_between_messages = antiflood.delay_between_messages if antiflood else 1.0
        messages_per_minute = antiflood.messages_per_minute if antiflood else 20
        if messages_per_minute and messages_per_minute > 0:
            delay_between_messages = max(delay_between_messages, 60.0 / messages_per_minute)
        users = (
            db.query(User)
            .filter_by(status=UserStatus.ACTIVE)
            .order_by(User.id)
            .offset(offset)
            .limit(settings.worker_batch_size)
            .all()
        )
        for user in users:
            try:
                await bot.send_message(chat_id=user.telegram_id, text=text)
                sent += 1
            except Exception:
                failed += 1
            if delay_between_messages > 0:
                await asyncio.sleep(delay_between_messages)
        log = db.query(BroadcastLog).filter_by(id=log_id).first()
        if log:
            log.total_sent += sent
            log.total_failed += failed
            if len(users) < settings.worker_batch_size:
                log.finished_at = datetime.now(timezone.utc)
        db.commit()
        if len(users) == settings.worker_batch_size:
            DownloadService.enqueue_broadcast(text=text, target=target, broadcast_log_id=log_id, offset=offset + settings.worker_batch_size)
        return {"status": "processed", "sent": sent, "failed": failed, "offset": offset}
    finally:
        db.close()


async def _process_job(bot: Bot, job) -> dict:
    if job.job_type == DownloadService.job_type:
        return await _process_download(bot, job.payload or {})
    if job.job_type == "broadcast_batch":
        return await _process_broadcast(bot, job.payload or {})
    raise RuntimeError(f"Unsupported job type: {job.job_type}")


async def _worker_loop() -> None:
    settings = load_settings()
    bot = _get_worker_bot()
    cleanup_stale_directories()
    while True:
        job = claim_next_job(settings.worker_name)
        if not job:
            await asyncio.sleep(settings.worker_poll_interval)
            continue
        try:
            result = await _process_job(bot, job)
            complete_job(job.id, result)
        except Exception as exc:
            logger.exception("Job %s failed: %s", job.id, exc)
            if job.attempts >= job.max_attempts:
                fail_job(job.id, str(exc))
            else:
                retry_job(
                    job.id,
                    str(exc),
                    delay_seconds=_retry_delay(job.attempts),
                )
            await asyncio.sleep(settings.worker_poll_interval)


def _run_job_once(job_id: int, *, task_id: str | None, worker_name: str) -> dict:
    claimed_job = claim_job_for_processing(job_id, worker_name, task_id=task_id)
    if claimed_job is None:
        logger.info("Skipping job %s because it is already claimed or completed", job_id)
        return {"status": "skipped", "job_id": job_id}
    result = asyncio.run(_process_job(_get_worker_bot(), claimed_job))
    complete_job(claimed_job.id, result, task_id=task_id)
    logger.info("Completed job %s via worker=%s task_id=%s", claimed_job.id, worker_name, task_id)
    return result


@celery_app.task(bind=True, name="bot.process_background_job", acks_late=True, reject_on_worker_lost=True)
def process_background_job(self, job_id: int) -> dict:
    settings = load_settings()
    worker_name = getattr(self.request, "hostname", None) or settings.worker_name
    cleanup_stale_directories()
    try:
        return _run_job_once(job_id, task_id=self.request.id, worker_name=worker_name)
    except Retry:
        raise
    except Exception as exc:
        logger.exception("Celery job %s failed on worker %s: %s", job_id, worker_name, exc)
        claimed_job = claim_job_for_processing(job_id, worker_name, task_id=self.request.id)
        if claimed_job is None:
            raise
        if claimed_job.attempts >= claimed_job.max_attempts:
            fail_job(claimed_job.id, str(exc), task_id=self.request.id)
            raise
        delay_seconds = _retry_delay(claimed_job.attempts)
        retry_job(claimed_job.id, str(exc), delay_seconds=delay_seconds, task_id=self.request.id)
        raise self.retry(exc=exc, countdown=delay_seconds)


def run_worker() -> None:
    settings = load_settings()
    settings.validate_for_mode()
    init_db()
    cleanup_stale_directories()
    if settings.queue_backend == "redis":
        logger.info(
            "Starting Redis-backed Celery worker name=%s queue=%s concurrency=%s",
            settings.worker_name,
            settings.queue_name,
            settings.worker_concurrency,
        )
        celery_app.worker_main([
            "worker",
            f"--loglevel={settings.log_level.lower()}",
            f"--hostname={settings.worker_name}@%h",
            f"--concurrency={settings.worker_concurrency}",
            f"--queues={settings.queue_name}",
            "--prefetch-multiplier=1",
        ])
        return
    logger.warning("Starting legacy database-backed worker loop because QUEUE_BACKEND=%s", settings.queue_backend)
    asyncio.run(_worker_loop())
