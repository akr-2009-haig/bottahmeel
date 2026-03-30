from __future__ import annotations

import asyncio
import calendar
import logging
import os
from datetime import datetime, timedelta, timezone

from celery.exceptions import Retry
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import load_settings
from bot.database import (
    AntiFloodSettings,
    BroadcastLog,
    PublishChannel,
    ScheduledPost,
    SessionLocal,
    User,
    UserStatus,
    get_setting,
    init_db,
)
from bot.locales import get_string
from bot.queue import (
    claim_job_for_processing,
    claim_next_job,
    complete_job,
    fail_job,
    recover_stale_processing_jobs,
    retry_job,
)
from bot.queue.celery_app import get_celery_app
from bot.services import DownloadService
from bot.temp import cleanup_path, cleanup_stale_directories
from bot.utils.platforms import download_media

logger = logging.getLogger(__name__)
DEFAULT_STATUS_LANGUAGE = "ar"

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


def _download_status_text(lang: str, *, state: str, delay_seconds: int | None = None) -> str:
    defaults = {
        "processing": {
            "ar": "⚙️ تم بدء معالجة طلبك الآن، وسيتم إرسال النتيجة فور اكتمالها.",
            "en": "⚙️ Your download is now being processed. The result will be sent as soon as it is ready.",
            "ru": "⚙️ Ваш запрос обрабатывается. Результат будет отправлен сразу после завершения.",
        },
        "retry": {
            "ar": "🔁 حدث تأخير مؤقت أثناء المعالجة. سنعيد المحاولة خلال {delay_seconds} ثانية.",
            "en": "🔁 Processing hit a temporary issue. We will retry in about {delay_seconds} seconds.",
            "ru": "🔁 Во время обработки возникла временная проблема. Повторим попытку примерно через {delay_seconds} сек.",
        },
        "failed": {
            "ar": "❌ تعذر إكمال الطلب بعد عدة محاولات. يمكنك إعادة إرسال الرابط للمحاولة مجدداً.",
            "en": "❌ We could not complete this request after several attempts. You can resend the link to try again.",
            "ru": "❌ Не удалось завершить запрос после нескольких попыток. Вы можете отправить ссылку снова.",
        },
    }
    localized_defaults = defaults.get(state, defaults["failed"])
    default_text = localized_defaults.get(lang, localized_defaults[DEFAULT_STATUS_LANGUAGE])
    if state == "retry":
        default_text = default_text.format(delay_seconds=delay_seconds or 30)
    return get_setting(f"download_{state}_message_{lang}", get_setting(f"download_{state}_message", default_text))


async def _notify_download_job_state(bot: Bot, payload: dict, *, state: str, delay_seconds: int | None = None) -> None:
    chat_id = int(payload.get("chat_id") or 0)
    if not chat_id:
        return
    status_message_id = payload.get("status_message_id")
    lang = payload.get("lang") or "ar"
    await _safe_edit_message(
        bot,
        chat_id,
        status_message_id,
        _download_status_text(lang, state=state, delay_seconds=delay_seconds),
    )


def _download_failure_message(lang: str, reason: str) -> str:
    if reason == "private":
        key = "download_private_error"
        defaults = {
            "ar": "❌ هذا المحتوى خاص أو يتطلب تسجيل الدخول.",
            "en": "❌ This content is private or requires login.",
            "ru": "❌ Этот контент приватный или требует входа.",
        }
    elif reason == "expired":
        key = "download_expired_error"
        defaults = {
            "ar": "❌ هذا الرابط لم يعد متاحاً أو انتهت صلاحيته.",
            "en": "❌ This link is no longer available or has expired.",
            "ru": "❌ Эта ссылка больше недоступна или срок действия истёк.",
        }
    elif reason == "timeout":
        key = "download_timeout_error"
        defaults = {
            "ar": "⏱️ انتهت مهلة التحميل. حاول مرة أخرى خلال دقائق.",
            "en": "⏱️ Download timed out. Please try again in a few minutes.",
            "ru": "⏱️ Время ожидания загрузки истекло. Попробуйте снова через несколько минут.",
        }
    elif reason == "file_too_large":
        key = "download_too_large_error"
        defaults = {
            "ar": "📦 الملف كبير جداً للإرسال عبر تيليجرام بهذا الإعداد.",
            "en": "📦 The file is too large to send via Telegram with current settings.",
            "ru": "📦 Файл слишком большой для отправки через Telegram с текущими настройками.",
        }
    else:
        key = "error_message"
        defaults = {"ar": get_string("error", "ar"), "en": get_string("error", "en"), "ru": get_string("error", "ru")}
    default_text = defaults.get(lang, defaults[DEFAULT_STATUS_LANGUAGE])
    return get_setting(f"{key}_{lang}", get_setting(key, default_text))


def _build_inline_keyboard(buttons_json) -> InlineKeyboardMarkup | None:
    if not buttons_json:
        return None
    rows = []
    for raw_row in buttons_json:
        row_buttons = []
        if not isinstance(raw_row, list):
            continue
        for raw_button in raw_row:
            if not isinstance(raw_button, dict):
                continue
            text = str(raw_button.get("text") or raw_button.get("label") or "").strip()
            if not text:
                continue
            if raw_button.get("url"):
                row_buttons.append(InlineKeyboardButton(text=text, url=str(raw_button["url"])))
            elif raw_button.get("callback_data"):
                row_buttons.append(InlineKeyboardButton(text=text, callback_data=str(raw_button["callback_data"])))
        if row_buttons:
            rows.append(row_buttons)
    return InlineKeyboardMarkup(rows) if rows else None


def _next_month(value: datetime) -> datetime:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _next_scheduled_at(value: datetime, repeat_type: str | None) -> datetime | None:
    repeat = (repeat_type or "once").strip().lower()
    if repeat == "daily":
        return value + timedelta(days=1)
    if repeat == "weekly":
        return value + timedelta(days=7)
    if repeat in {"monthly", "forever"}:
        # The legacy admin UI exposes `forever` without a separate cadence field.
        # Until that is expanded, treat it as an open-ended monthly recurrence.
        return _next_month(value)
    return None


async def _process_download(bot: Bot, payload: dict) -> dict:
    user_id = int(payload["user_id"])
    chat_id = int(payload["chat_id"])
    url = payload["url"]
    platform = payload["platform"]
    lang = payload.get("lang") or "ar"
    status_message_id = payload.get("status_message_id")
    download_mode = payload.get("download_mode") or "default"
    caption_override = payload.get("caption_override")

    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(id=user_id).first()
        if not db_user:
            raise RuntimeError(f"User {user_id} not found")
        await _notify_download_job_state(bot, payload, state="processing")
        await bot.send_chat_action(chat_id=chat_id, action=get_setting("activity_status", "upload_video"))
        filepath, media_type, error_kind = await download_media(url, platform, download_mode=download_mode)
        if not filepath:
            error_text = _download_failure_message(lang, error_kind or "generic")
            await _safe_edit_message(bot, chat_id, status_message_id, error_text)
            DownloadService.record_download_result(
                user_id=user_id,
                platform=platform,
                url=url,
                media_type=media_type or "video",
                success=False,
            )
            return {"status": "failed"}

        max_size_bytes = max(load_settings().max_upload_file_size_mb, 1) * 1024 * 1024
        file_size = os.path.getsize(filepath)
        if file_size > max_size_bytes:
            logger.warning(
                "Skipping send: file too large user_id=%s platform=%s size=%s max=%s",
                user_id,
                platform,
                file_size,
                max_size_bytes,
            )
            await _safe_edit_message(bot, chat_id, status_message_id, _download_failure_message(lang, "file_too_large"))
            DownloadService.record_download_result(
                user_id=user_id,
                platform=platform,
                url=url,
                media_type=media_type,
                success=False,
            )
            cleanup_path(filepath)
            return {"status": "failed", "reason": "file_too_large"}

        caption = caption_override or DownloadService.build_caption(
            media_type=media_type,
            lang=lang,
            telegram_user=db_user,
            platform=platform,
        )
        if platform == "tiktok" and media_type in {"photo", "video"}:
            bot_name = get_setting("bot_name", "SaveEliteBot")
            mention = bot_name if str(bot_name).startswith("@") else f"@{bot_name}"
            if media_type == "photo":
                caption = f"🤖 {mention}"
            else:
                caption = f"📥 تم التحميل بنجاح\n🤖 {mention}"
        main_markup, extra_markup = DownloadService.get_download_reply_markup()
        await _safe_delete_message(bot, chat_id, status_message_id)
        tiktok_audio_markup = None
        if platform == "tiktok" and media_type == "video" and download_mode == "default":
            saved_download_id = DownloadService.record_download_result(
                user_id=user_id,
                platform=platform,
                url=url,
                media_type=media_type,
                success=True,
            )
            if saved_download_id:
                tiktok_audio_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎵 تحميل الصوت", callback_data=f"ttaudio:{saved_download_id}")
                ]])
        try:
            with open(filepath, "rb") as media_handle:
                action_for_media = {
                    "photo": "upload_photo",
                    "audio": "upload_voice",
                    "voice": "upload_voice",
                    "document": "upload_document",
                    "video": "upload_video",
                }.get(media_type, "upload_video")
                await bot.send_chat_action(chat_id=chat_id, action=action_for_media)
                if media_type == "photo":
                    await bot.send_photo(chat_id=chat_id, photo=media_handle, caption=caption, reply_markup=main_markup)
                elif media_type == "audio":
                    await bot.send_audio(chat_id=chat_id, audio=media_handle, caption=caption, reply_markup=main_markup)
                elif media_type == "voice":
                    await bot.send_voice(chat_id=chat_id, voice=media_handle, caption=caption, reply_markup=main_markup)
                elif media_type == "document":
                    await bot.send_document(chat_id=chat_id, document=media_handle, caption=caption, reply_markup=main_markup)
                else:
                    final_markup = tiktok_audio_markup or main_markup
                    await bot.send_video(chat_id=chat_id, video=media_handle, caption=caption, supports_streaming=True, reply_markup=final_markup)
            if extra_markup:
                await bot.send_message(chat_id=chat_id, text="⌨️", reply_markup=extra_markup)
            if not (platform == "tiktok" and media_type == "video" and download_mode == "default"):
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
    scope = (payload.get("scope") or "all").strip().lower()
    if scope not in {"all", "active"}:
        raise RuntimeError(f"Unsupported broadcast scope: {scope}")
    media_type = payload.get("media_type")
    media_file_id = payload.get("media_file_id")
    settings = load_settings()
    db = SessionLocal()
    sent = 0
    failed = 0
    log = None
    try:
        log = db.query(BroadcastLog).filter_by(id=log_id).first()
        if log:
            log.status = "processing"
            log.error_message = None
            db.commit()
        antiflood = db.query(AntiFloodSettings).first()
        delay_between_messages = antiflood.delay_between_messages if antiflood else 1.0
        messages_per_minute = antiflood.messages_per_minute if antiflood else 20
        if messages_per_minute and messages_per_minute > 0:
            delay_between_messages = max(delay_between_messages, 60.0 / messages_per_minute)
        if target == "users":
            recipients = db.query(User)
            if scope == "active":
                recipients = recipients.filter_by(status=UserStatus.ACTIVE)
            else:
                recipients = recipients.filter(User.status != UserStatus.BANNED)
            recipients = (
                recipients
                .order_by(User.id)
                .offset(offset)
                .limit(settings.worker_batch_size)
                .all()
            )
        elif target == "channels":
            recipients = db.query(PublishChannel)
            if scope == "active":
                recipients = recipients.filter_by(is_active=True)
            recipients = (
                recipients
                .order_by(PublishChannel.id)
                .offset(offset)
                .limit(settings.worker_batch_size)
                .all()
            )
        else:
            raise RuntimeError(f"Unsupported broadcast target: {target}")
        for recipient in recipients:
            try:
                chat_id = recipient.telegram_id if target == "users" else recipient.chat_id
                if media_type == "photo" and media_file_id:
                    await bot.send_photo(chat_id=chat_id, photo=media_file_id, caption=text or None)
                elif media_type == "video" and media_file_id:
                    await bot.send_video(chat_id=chat_id, video=media_file_id, caption=text or None, supports_streaming=True)
                elif media_type == "document" and media_file_id:
                    await bot.send_document(chat_id=chat_id, document=media_file_id, caption=text or None)
                else:
                    await bot.send_message(chat_id=chat_id, text=text)
                sent += 1
            except Exception:
                failed += 1
            if delay_between_messages > 0:
                await asyncio.sleep(delay_between_messages)
        if log:
            log.total_sent += sent
            log.total_failed += failed
            if len(recipients) < settings.worker_batch_size:
                log.finished_at = datetime.now(timezone.utc)
                log.status = "completed"
                log.last_job_id = None
        db.commit()
        if len(recipients) == settings.worker_batch_size:
            next_job_id = DownloadService.enqueue_broadcast(
                text=text,
                target=target,
                broadcast_log_id=log_id,
                offset=offset + settings.worker_batch_size,
                scope=scope,
                media_type=media_type,
                media_file_id=media_file_id,
            )
            if log:
                log.last_job_id = next_job_id
                log.status = "processing"
                db.commit()
        return {"status": "processed", "sent": sent, "failed": failed, "offset": offset}
    except Exception as exc:
        if log:
            log.status = "failed"
            log.error_message = str(exc)
            log.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()


async def _process_scheduled_post(bot: Bot, payload: dict) -> dict:
    post_id = int(payload["scheduled_post_id"])
    db = SessionLocal()
    post = None
    try:
        post = db.query(ScheduledPost).filter_by(id=post_id).first()
        if not post:
            raise RuntimeError(f"Scheduled post {post_id} not found")
        if not post.is_active:
            return {"status": "skipped", "reason": "inactive"}
        if post.is_sent and (post.repeat_type or "once") == "once":
            return {"status": "skipped", "reason": "already_sent"}

        channels_query = db.query(PublishChannel).filter_by(is_active=True)
        if post.group_id:
            channels_query = channels_query.filter_by(group_id=post.group_id)
        elif post.channel_ids:
            channels_query = channels_query.filter(PublishChannel.id.in_(post.channel_ids))
        channels = channels_query.order_by(PublishChannel.id.asc()).all()
        if not channels:
            raise RuntimeError("No active publish channels available for this scheduled post")

        markup = _build_inline_keyboard(post.buttons_json)
        sent = 0
        failed = 0
        last_error = None
        for channel in channels:
            try:
                if post.media_type == "photo" and post.media_file_id:
                    await bot.send_photo(
                        chat_id=channel.chat_id,
                        photo=post.media_file_id,
                        caption=post.text or None,
                        reply_markup=markup,
                    )
                elif post.media_type == "video" and post.media_file_id:
                    await bot.send_video(
                        chat_id=channel.chat_id,
                        video=post.media_file_id,
                        caption=post.text or None,
                        reply_markup=markup,
                        supports_streaming=True,
                    )
                elif post.media_type == "document" and post.media_file_id:
                    await bot.send_document(
                        chat_id=channel.chat_id,
                        document=post.media_file_id,
                        caption=post.text or None,
                        reply_markup=markup,
                    )
                else:
                    await bot.send_message(chat_id=channel.chat_id, text=post.text or "…", reply_markup=markup)
                channel.post_count = (channel.post_count or 0) + 1
                sent += 1
            except Exception as exc:
                failed += 1
                last_error = str(exc)

        if sent == 0 and failed > 0:
            raise RuntimeError(last_error or "Failed to publish scheduled post")

        next_run = _next_scheduled_at(post.scheduled_at, post.repeat_type)
        post.sent_at = datetime.now(timezone.utc)
        post.last_error = last_error
        post.fail_count = (post.fail_count or 0) + failed
        if next_run is None:
            post.is_sent = True
            post.is_active = False
        else:
            post.is_sent = False
            post.scheduled_at = next_run
            post.queued_at = None
        db.commit()
        return {
            "status": "sent" if failed == 0 else "partial",
            "sent": sent,
            "failed": failed,
            "next_scheduled_at": next_run.isoformat() if next_run else None,
        }
    except Exception as exc:
        if post:
            post.fail_count = (post.fail_count or 0) + 1
            post.last_error = str(exc)
            db.commit()
        raise
    finally:
        db.close()


async def _process_job(bot: Bot, job) -> dict:
    if job.job_type == DownloadService.job_type:
        return await _process_download(bot, job.payload or {})
    if job.job_type == DownloadService.broadcast_job_type:
        return await _process_broadcast(bot, job.payload or {})
    if job.job_type == DownloadService.scheduled_post_job_type:
        return await _process_scheduled_post(bot, job.payload or {})
    raise RuntimeError(f"Unsupported job type: {job.job_type}")


async def run_database_worker_loop(
    *,
    stop_event: asyncio.Event | None = None,
    worker_name: str | None = None,
) -> None:
    settings = load_settings()
    bot = _get_worker_bot()
    cleanup_stale_directories()
    recovery_check_interval = min(max(settings.worker_poll_interval, 5.0), 30.0)
    next_recovery_check = 0.0
    effective_worker_name = worker_name or settings.worker_name
    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("Stopping embedded database worker loop worker=%s", effective_worker_name)
            return
        loop_time = asyncio.get_running_loop().time()
        if loop_time >= next_recovery_check:
            recovered = recover_stale_processing_jobs(lock_timeout_seconds=settings.job_lock_timeout_seconds)
            if recovered["total"]:
                logger.warning(
                    "Recovered stale database-queue jobs before polling total=%s retried=%s failed=%s",
                    recovered["total"],
                    recovered["retried"],
                    recovered["failed"],
                )
            next_recovery_check = loop_time + recovery_check_interval
        job = claim_next_job(effective_worker_name)
        if not job:
            await asyncio.sleep(settings.worker_poll_interval)
            continue
        try:
            result = await _process_job(bot, job)
            complete_job(job.id, result)
            logger.info("Completed database-backed job %s via worker=%s", job.id, effective_worker_name)
        except Exception as exc:
            logger.exception(
                "Database-backed job id=%s worker=%s attempt=%s/%s failed: %s",
                job.id,
                effective_worker_name,
                job.attempts,
                job.max_attempts,
                exc,
            )
            if job.attempts >= job.max_attempts:
                if job.job_type == DownloadService.job_type:
                    await _notify_download_job_state(bot, job.payload or {}, state="failed")
                fail_job(job.id, str(exc))
            else:
                if job.job_type == DownloadService.job_type:
                    await _notify_download_job_state(
                        bot,
                        job.payload or {},
                        state="retry",
                        delay_seconds=_retry_delay(job.attempts),
                    )
                retry_job(
                    job.id,
                    str(exc),
                    delay_seconds=_retry_delay(job.attempts),
                )
            await asyncio.sleep(settings.worker_poll_interval)


async def _worker_loop() -> None:
    await run_database_worker_loop()


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
            if claimed_job.job_type == DownloadService.job_type:
                asyncio.run(_notify_download_job_state(_get_worker_bot(), claimed_job.payload or {}, state="failed"))
            fail_job(claimed_job.id, str(exc), task_id=self.request.id)
            raise
        delay_seconds = _retry_delay(claimed_job.attempts)
        if claimed_job.job_type == DownloadService.job_type:
            asyncio.run(
                _notify_download_job_state(
                    _get_worker_bot(),
                    claimed_job.payload or {},
                    state="retry",
                    delay_seconds=delay_seconds,
                )
            )
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
