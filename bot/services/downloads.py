from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from telegram import User as TelegramUser

from bot.database import Download, PublishChannel, ScheduledPost, SessionLocal, User, get_setting
from bot.locales import get_string
from bot.queue import enqueue_job
from bot.utils.button_engine import build_reply_markup, get_buttons_for_location
from bot.utils.helpers import get_user_name
from bot.utils.platforms import get_platform_info

logger = logging.getLogger(__name__)

_PLATFORM_COUNT_FIELDS = {
    "tiktok": "tiktok_count",
    "youtube": "youtube_count",
    "instagram": "instagram_count",
    "likee": "likee_count",
}


class DownloadService:
    job_type = "download_request"
    broadcast_job_type = "broadcast_batch"
    scheduled_post_job_type = "scheduled_post"

    @staticmethod
    def enqueue_download(
        *,
        user_id: int,
        chat_id: int,
        url: str,
        platform: str,
        lang: str,
        status_message_id: int,
        download_mode: str = "default",
        caption_override: str | None = None,
    ) -> int:
        payload = {
            "user_id": user_id,
            "chat_id": chat_id,
            "url": url,
            "platform": platform,
            "lang": lang,
            "status_message_id": status_message_id,
            "download_mode": download_mode,
            "caption_override": caption_override,
        }
        return enqueue_job(DownloadService.job_type, payload, priority=10, max_attempts=3)

    @staticmethod
    def enqueue_broadcast(
        *,
        text: str,
        target: str,
        broadcast_log_id: int,
        offset: int = 0,
        scope: str = "all",
        media_type: str | None = None,
        media_file_id: str | None = None,
    ) -> int:
        payload = {
            "text": text,
            "target": target,
            "broadcast_log_id": broadcast_log_id,
            "offset": offset,
            "scope": scope,
            "media_type": media_type,
            "media_file_id": media_file_id,
        }
        return enqueue_job(DownloadService.broadcast_job_type, payload, priority=5, max_attempts=3)

    @staticmethod
    def enqueue_scheduled_post(*, scheduled_post_id: int) -> int:
        return enqueue_job(
            DownloadService.scheduled_post_job_type,
            {"scheduled_post_id": scheduled_post_id},
            priority=8,
            max_attempts=3,
        )

    @staticmethod
    def enqueue_due_scheduled_posts(*, limit: int = 20) -> list[int]:
        db = SessionLocal()
        now = datetime.now(timezone.utc)
        enqueued_job_ids: list[int] = []
        try:
            candidate_ids = [
                post_id
                for (post_id,) in (
                    db.query(ScheduledPost.id)
                    .filter(
                        ScheduledPost.is_active.is_(True),
                        ScheduledPost.is_sent.is_(False),
                        ScheduledPost.scheduled_at <= now,
                        # `queued_at < scheduled_at` lets repeating posts become dispatchable again
                        # after the worker advances `scheduled_at` to the next occurrence.
                        (ScheduledPost.queued_at.is_(None) | (ScheduledPost.queued_at < ScheduledPost.scheduled_at)),
                    )
                    .order_by(ScheduledPost.scheduled_at.asc(), ScheduledPost.id.asc())
                    .limit(limit)
                    .all()
                )
            ]
        finally:
            db.close()

        for post_id in candidate_ids:
            claim_db = SessionLocal()
            try:
                claimed = (
                    claim_db.query(ScheduledPost)
                    .filter(
                        ScheduledPost.id == post_id,
                        ScheduledPost.is_active.is_(True),
                        ScheduledPost.is_sent.is_(False),
                        ScheduledPost.scheduled_at <= now,
                        # Same condition as the candidate scan above; this makes the claim idempotent
                        # while still allowing repeated posts to be queued again after rescheduling.
                        (ScheduledPost.queued_at.is_(None) | (ScheduledPost.queued_at < ScheduledPost.scheduled_at)),
                    )
                    .update(
                        {
                            ScheduledPost.queued_at: now,
                            ScheduledPost.last_error: None,
                        },
                        synchronize_session=False,
                    )
                )
                if not claimed:
                    claim_db.rollback()
                    continue
                claim_db.commit()
            finally:
                claim_db.close()

            try:
                job_id = DownloadService.enqueue_scheduled_post(scheduled_post_id=post_id)
            except Exception as exc:
                reset_db = SessionLocal()
                try:
                    post = reset_db.query(ScheduledPost).filter_by(id=post_id).first()
                    if post:
                        post.queued_at = None
                        post.last_error = str(exc)
                        reset_db.commit()
                finally:
                    reset_db.close()
                logger.exception("Failed to enqueue scheduled post %s: %s", post_id, exc)
                continue

            update_db = SessionLocal()
            try:
                post = update_db.query(ScheduledPost).filter_by(id=post_id).first()
                if post:
                    post.last_job_id = job_id
                    update_db.commit()
            finally:
                update_db.close()
            enqueued_job_ids.append(job_id)
        return enqueued_job_ids

    @staticmethod
    def default_scheduled_channel_ids() -> list[int]:
        db = SessionLocal()
        try:
            return [
                channel.id
                for channel in (
                    db.query(PublishChannel)
                    .filter_by(is_active=True)
                    .order_by(PublishChannel.id.asc())
                    .all()
                )
            ]
        finally:
            db.close()

    @staticmethod
    def build_caption(*, media_type: str, lang: str, telegram_user: TelegramUser | None, platform: str) -> str:
        bot_name = get_setting("bot_name", "SaveEliteBot")
        platform_info = get_platform_info(platform)
        if media_type == "photo":
            cap_key = "photo_caption"
        elif media_type == "audio":
            cap_key = "audio_caption"
        elif media_type == "document":
            cap_key = "document_caption"
        else:
            cap_key = "video_caption"
        default_template = get_string("success_caption", lang, bot_name=bot_name)
        if cap_key == "document_caption":
            # Documents reuse the video caption when no document-specific caption has been configured yet.
            base_template = get_setting("document_caption", get_setting("video_caption", default_template))
        else:
            base_template = get_setting(cap_key, default_template)
        template = get_setting(f"{cap_key}_{lang}", base_template)
        if telegram_user is not None:
            user_name = get_user_name(telegram_user)
        else:
            user_name = ""
        return (
            template
            .replace("{bot_name}", bot_name)
            .replace("{name}", user_name)
            .replace("{platform}", platform_info.get("name", platform.title()))
            .replace("{platform_emoji}", platform_info.get("emoji", "📥"))
        )

    @staticmethod
    def get_download_reply_markup() -> tuple[Any, Any]:
        inline_rows, reply_buttons = get_buttons_for_location("download")
        return build_reply_markup(inline_rows, reply_buttons)

    @staticmethod
    def record_download_result(*, user_id: int, platform: str, url: str, media_type: str, success: bool) -> int | None:
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(id=user_id).first()
            if db_user and success:
                db_user.download_count += 1
                counter_field = _PLATFORM_COUNT_FIELDS.get(platform)
                if counter_field and hasattr(db_user, counter_field):
                    setattr(db_user, counter_field, (getattr(db_user, counter_field) or 0) + 1)
            download_record = Download(
                user_id=user_id,
                platform=platform,
                url=url,
                media_type=media_type,
                success=success,
            )
            db.add(download_record)
            db.commit()
            db.refresh(download_record)
            return download_record.id
        except Exception as exc:
            db.rollback()
            logger.error("Failed to record download result: %s", exc)
            return None
        finally:
            db.close()
