"""
Backward-compatible helpers – imports from platforms module
"""
from .platforms import (
    detect_platform,
    download_media,
    is_any_url,
    PLATFORMS,
)
import os
import logging

logger = logging.getLogger(__name__)


def is_tiktok_url(text: str):
    url, platform = detect_platform(text)
    if platform == "tiktok":
        return url
    return None


async def download_tiktok(url: str):
    return await download_media(url, "tiktok")


def cleanup_file(filepath: str):
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            tmp_dir = os.path.dirname(filepath)
            if os.path.exists(tmp_dir) and not os.listdir(tmp_dir):
                os.rmdir(tmp_dir)
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


def get_user_name(user) -> str:
    if user.first_name:
        name = user.first_name
        if user.last_name:
            name += f" {user.last_name}"
        return name
    elif user.username:
        return f"@{user.username}"
    return str(user.id)
