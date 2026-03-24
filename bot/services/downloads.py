from __future__ import annotations

import logging
from typing import Any

from telegram import User as TelegramUser

from bot.database import Download, SessionLocal, User, get_setting
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

    @staticmethod
    def enqueue_download(*, user_id: int, chat_id: int, url: str, platform: str, lang: str, status_message_id: int) -> int:
        payload = {
            "user_id": user_id,
            "chat_id": chat_id,
            "url": url,
            "platform": platform,
            "lang": lang,
            "status_message_id": status_message_id,
        }
        return enqueue_job(DownloadService.job_type, payload, priority=10, max_attempts=3)

    @staticmethod
    def enqueue_broadcast(*, text: str, target: str, broadcast_log_id: int, offset: int = 0) -> int:
        payload = {
            "text": text,
            "target": target,
            "broadcast_log_id": broadcast_log_id,
            "offset": offset,
        }
        return enqueue_job("broadcast_batch", payload, priority=5, max_attempts=3)

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
        fallback_key = "video_caption" if cap_key == "document_caption" else cap_key
        template = get_setting(
            f"{cap_key}_{lang}",
            get_setting(cap_key, get_setting(fallback_key, get_string("success_caption", lang, bot_name=bot_name))),
        )
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
    def record_download_result(*, user_id: int, platform: str, url: str, media_type: str, success: bool) -> None:
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(id=user_id).first()
            if db_user and success:
                db_user.download_count += 1
                counter_field = _PLATFORM_COUNT_FIELDS.get(platform)
                if counter_field and hasattr(db_user, counter_field):
                    setattr(db_user, counter_field, (getattr(db_user, counter_field) or 0) + 1)
            db.add(Download(
                user_id=user_id,
                platform=platform,
                url=url,
                media_type=media_type,
                success=success,
            ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Failed to record download result: %s", exc)
        finally:
            db.close()
