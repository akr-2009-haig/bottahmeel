from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import Bot

from bot.config import load_settings
from bot.database import BroadcastLog, SessionLocal, User, UserStatus, get_setting
from bot.locales import get_string
from bot.queue import claim_next_job, complete_job, fail_job, retry_job
from bot.services import DownloadService
from bot.temp import cleanup_path, cleanup_stale_directories
from bot.utils.platforms import download_media

logger = logging.getLogger(__name__)

BASE_RETRY_DELAY_SECONDS = 30
BACKOFF_MULTIPLIER = 2
MAX_RETRY_DELAY_SECONDS = 300


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
    bot = Bot(token=settings.bot_token)
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
                    delay_seconds=min(
                        MAX_RETRY_DELAY_SECONDS,
                        BASE_RETRY_DELAY_SECONDS * (BACKOFF_MULTIPLIER ** (job.attempts - 1)),
                    ),
                )
            await asyncio.sleep(settings.worker_poll_interval)


def run_worker() -> None:
    settings = load_settings()
    settings.validate_for_mode()
    logger.info("Starting worker %s", settings.worker_name)
    asyncio.run(_worker_loop())
