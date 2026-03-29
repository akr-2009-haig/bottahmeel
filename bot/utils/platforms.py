"""
Multi-Platform Download Engine
All supported platforms with their URL patterns and display info
"""
import re
import os
import logging
import asyncio
from typing import Any, Optional, Tuple, List
from urllib.parse import urlparse

import yt_dlp

from bot.temp import create_temp_download_dir

logger = logging.getLogger(__name__)

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
AUDIO_EXTS = {"mp3", "m4a", "ogg", "wav", "flac", "opus"}
VIDEO_EXTS = {"mp4", "m4v", "mov", "mkv", "webm", "avi", "flv", "3gp", "mpeg", "mpg"}

PLATFORMS = {
    "tiktok": {
        "name": "TikTok",
        "emoji": "🎵",
        "patterns": [
            r'https?://(www\.)?tiktok\.com/@[\w.]+/video/\d+',
            r'https?://vm\.tiktok\.com/\S+',
            r'https?://vt\.tiktok\.com/\S+',
            r'https?://m\.tiktok\.com/v/\S+',
            r'https?://(www\.)?tiktok\.com/t/\S+',
        ],
        "db_key": "tiktok_enabled",
        "default_enabled": True,
    },
    "youtube": {
        "name": "YouTube",
        "emoji": "📺",
        "patterns": [
            r'https?://(www\.)?youtube\.com/watch\?v=\S+',
            r'https?://(www\.)?youtube\.com/shorts/\S+',
            r'https?://youtu\.be/\S+',
            r'https?://m\.youtube\.com/\S+',
            r'https?://music\.youtube\.com/\S+',
        ],
        "db_key": "youtube_enabled",
        "default_enabled": True,
    },
    "instagram": {
        "name": "Instagram",
        "emoji": "📷",
        "patterns": [
            r'https?://(www\.)?instagram\.com/p/\S+',
            r'https?://(www\.)?instagram\.com/reel/\S+',
            r'https?://(www\.)?instagram\.com/reels/\S+',
            r'https?://(www\.)?instagram\.com/tv/\S+',
            r'https?://(www\.)?instagram\.com/stories/\S+',
            r'https?://(www\.)?instagram\.com/(?!p/|reel/|reels/|tv/|stories/|explore/)[\w.]+/?(?:\?\S*)?$',
        ],
        "db_key": "instagram_enabled",
        "default_enabled": True,
    },
    "twitter": {
        "name": "Twitter / X",
        "emoji": "🐦",
        "patterns": [
            r'https?://(www\.)?twitter\.com/\S+/status/\d+',
            r'https?://(www\.)?x\.com/\S+/status/\d+',
            r'https?://t\.co/\S+',
        ],
        "db_key": "twitter_enabled",
        "default_enabled": True,
    },
    "facebook": {
        "name": "Facebook",
        "emoji": "📘",
        "patterns": [
            r'https?://(www\.)?facebook\.com/\S+/videos/\S+',
            r'https?://(www\.)?facebook\.com/watch/?\?v=\S+',
            r'https?://(www\.)?fb\.watch/\S+',
            r'https?://fb\.com/\S+',
            r'https?://(www\.)?facebook\.com/reel/\S+',
            r'https?://(www\.)?facebook\.com/share/v/\S+',
            r'https?://(www\.)?facebook\.com/share/r/\S+',
        ],
        "db_key": "facebook_enabled",
        "default_enabled": True,
    },
    "pinterest": {
        "name": "Pinterest",
        "emoji": "📌",
        "patterns": [
            r'https?://(www\.)?pinterest\.\w+/pin/\S+',
            r'https?://pin\.it/\S+',
            r'https?://(www\.)?pinterest\.\w+/\S+',
        ],
        "db_key": "pinterest_enabled",
        "default_enabled": True,
    },
    "likee": {
        "name": "Likee",
        "emoji": "❤️",
        "patterns": [
            r'https?://(www\.)?likee\.video/\S+',
            r'https?://l\.likee\.video/\S+',
        ],
        "db_key": "likee_enabled",
        "default_enabled": True,
    },
    "snapchat": {
        "name": "Snapchat",
        "emoji": "👻",
        "patterns": [
            r'https?://(www\.)?snapchat\.com/\S+',
            r'https?://t\.snapchat\.com/\S+',
        ],
        "db_key": "snapchat_enabled",
        "default_enabled": False,
    },
    "reddit": {
        "name": "Reddit",
        "emoji": "🔴",
        "patterns": [
            r'https?://(www\.)?reddit\.com/r/\S+',
            r'https?://v\.redd\.it/\S+',
            r'https?://redd\.it/\S+',
        ],
        "db_key": "reddit_enabled",
        "default_enabled": False,
    },
    "google_drive": {
        "name": "Google Drive",
        "emoji": "📁",
        "patterns": [
            r'https?://drive\.google\.com/file/d/\S+',
            r'https?://drive\.google\.com/open\?id=\S+',
            r'https?://drive\.google\.com/uc\?id=\S+',
        ],
        "db_key": "google_drive_enabled",
        "default_enabled": False,
    },
    "linkedin": {
        "name": "LinkedIn",
        "emoji": "💼",
        "patterns": [
            r'https?://(www\.)?linkedin\.com/posts/\S+',
            r'https?://(www\.)?linkedin\.com/feed/update/\S+',
            r'https?://(www\.)?linkedin\.com/embed/feed/update/\S+',
            r'https?://lnkd\.in/\S+',
        ],
        "db_key": "linkedin_enabled",
        "default_enabled": False,
    },
    "vimeo": {
        "name": "Vimeo",
        "emoji": "🎬",
        "patterns": [
            r'https?://(www\.)?vimeo\.com/\d+',
            r'https?://player\.vimeo\.com/\S+',
        ],
        "db_key": "vimeo_enabled",
        "default_enabled": False,
    },
    "dailymotion": {
        "name": "Dailymotion",
        "emoji": "▶️",
        "patterns": [
            r'https?://(www\.)?dailymotion\.com/video/\S+',
            r'https?://dai\.ly/\S+',
        ],
        "db_key": "dailymotion_enabled",
        "default_enabled": False,
    },
}


def detect_platform(text: str) -> Tuple[Optional[str], Optional[str]]:
    urls = re.findall(r'https?://\S+', text)
    for url in urls:
        url = url.rstrip('.,;!?)')
        for platform_key, info in PLATFORMS.items():
            for pattern in info["patterns"]:
                if re.match(pattern, url, re.IGNORECASE):
                    return url, platform_key
    return None, None


def is_any_url(text: str) -> bool:
    return bool(re.search(r'https?://\S+', text))


YDL_BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'extract_flat': False,
    'http_headers': {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    },
}

PLATFORM_OPTS: dict = {
    "youtube": {
        'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]/best',
    },
    "twitter": {
        'format': 'best[ext=mp4]/best',
    },
    "instagram": {
        'format': 'best[ext=mp4]/best',
    },
    "tiktok": {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    },
    "facebook": {
        'format': 'best[ext=mp4]/best',
    },
    "pinterest": {
        'format': 'best[ext=mp4]/best[ext=jpg]/best',
    },
    "reddit": {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    },
    "google_drive": {
        'format': 'best/bestvideo+bestaudio',
    },
    "linkedin": {
        'format': 'best[ext=mp4]/best',
    },
    "likee": {
        'format': 'best[ext=mp4]/best',
    },
    "snapchat": {
        'format': 'best[ext=mp4]/best',
    },
    "vimeo": {
        'format': 'best[ext=mp4]/best',
    },
    "dailymotion": {
        'format': 'best[ext=mp4]/best',
    },
}


async def download_media(url: str, platform: str = "unknown", *, download_mode: str = "default") -> Tuple[Optional[str], str, str]:
    tmp_dir = create_temp_download_dir(platform)
    outtmpl = os.path.join(tmp_dir, '%(id)s.%(ext)s')

    opts = {**YDL_BASE_OPTS}
    opts.update(PLATFORM_OPTS.get(platform, {}))
    opts['outtmpl'] = outtmpl
    if download_mode == "audio":
        opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif download_mode.startswith("video_"):
        quality = download_mode.split("_", 1)[1]
        opts['format'] = (
            f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/'
            f'best[height<={quality}][ext=mp4]/best[height<={quality}]/best'
        )
    elif download_mode == "fingerprint":
        opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
    elif 'format' not in opts:
        opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

    loop = asyncio.get_event_loop()

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None, "video", ""

            title = info.get("title", "")
            ext = info.get("ext", "mp4")
            video_id = info.get("id", "unknown")

            filepath = os.path.join(tmp_dir, f"{video_id}.{ext}")
            if not os.path.exists(filepath):
                files = [f for f in os.listdir(tmp_dir) if not f.endswith('.part')]
                if files:
                    if download_mode == "audio":
                        files = sorted(files, key=lambda name: (0 if name.lower().endswith(".mp3") else 1, name))
                    else:
                        files = sorted(files)
                    filepath = os.path.join(tmp_dir, files[0])
                    ext = filepath.rsplit('.', 1)[-1].lower()
                else:
                    return None, "video", title

            ext_lower = ext.lower()
            media_type = _guess_media_type({"ext": ext_lower}, requested_mode=download_mode)
            if media_type == "document":
                logger.warning("[%s] Treating unknown extension '%s' as document for %s", platform, ext_lower, url)

            return filepath, media_type, title

    try:
        return await loop.run_in_executor(None, _download)
    except Exception as e:
        logger.error(f"[{platform}] Download error: {e}")
        return None, "video", ""


def is_instagram_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return False
    parts = path.split("/")
    if len(parts) != 1:
        return False
    if parts[0].lower() in {"p", "reel", "reels", "tv", "stories", "explore"}:
        return False
    return bool(re.fullmatch(r"[\w.]+", parts[0]))


def classify_extraction_error(exc: Exception) -> str:
    message = str(exc).lower()
    if any(marker in message for marker in ("private", "login required", "sign in", "not authorized", "forbidden")):
        return "private"
    if any(marker in message for marker in ("story unavailable", "story has expired", "expired", "no longer available")):
        return "expired"
    return "generic"


def _guess_media_type(info: dict[str, Any], *, requested_mode: str = "default") -> str:
    ext = str(info.get("ext") or "").lower()
    if requested_mode == "fingerprint" and ext in AUDIO_EXTS:
        return "voice"
    if ext in IMAGE_EXTS:
        return "photo"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "document"


def _normalize_entries(entries: Any, *, requested_mode: str = "default") -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not entries:
        return normalized
    for entry in list(entries):
        if not isinstance(entry, dict):
            continue
        normalized.append({
            "url": entry.get("webpage_url") or entry.get("original_url") or entry.get("url"),
            "title": entry.get("title") or "",
            "thumbnail": entry.get("thumbnail") or "",
            "media_type": _guess_media_type(entry, requested_mode=requested_mode),
        })
    return normalized


async def extract_media_info(url: str, platform: str = "unknown", *, requested_mode: str = "default") -> dict[str, Any]:
    opts = {**YDL_BASE_OPTS}
    opts.update(PLATFORM_OPTS.get(platform, {}))
    opts.update({
        "skip_download": True,
        "quiet": True,
        "noplaylist": False,
    })
    if requested_mode == "audio":
        opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    elif requested_mode == "fingerprint":
        opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"

    loop = asyncio.get_event_loop()

    def _extract() -> dict[str, Any]:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info or {}

    try:
        info = await loop.run_in_executor(None, _extract)
    except Exception as exc:
        logger.warning("[%s] Metadata extraction failed for %s: %s", platform, url, exc)
        return {
            "ok": False,
            "error": classify_extraction_error(exc),
            "url": url,
            "platform": platform,
        }

    uploader = info.get("channel") or info.get("uploader") or info.get("creator") or ""
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    username_hint = path_parts[0] if path_parts else ""
    display_name = info.get("uploader") or info.get("channel") or info.get("fulltitle") or ""
    view_count = info.get("view_count") or info.get("channel_follower_count") or 0
    entries = _normalize_entries(info.get("entries"), requested_mode=requested_mode)
    post_count = info.get("playlist_count") or info.get("media_count") or len(entries)

    return {
        "ok": True,
        "url": url,
        "platform": platform,
        "title": info.get("title") or info.get("playlist_title") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": info.get("duration") or 0,
        "view_count": view_count,
        "filesize": info.get("filesize") or info.get("filesize_approx") or 0,
        "channel": uploader,
        "username": info.get("uploader_id") or username_hint,
        "display_name": display_name,
        "bio": info.get("description") or "",
        "post_count": post_count or 0,
        "followers": info.get("channel_follower_count") or info.get("follower_count") or 0,
        "following": info.get("following_count") or 0,
        "entries": entries,
        "media_type": _guess_media_type(info, requested_mode=requested_mode),
        "raw_id": info.get("id") or "",
        "is_instagram_profile": platform == "instagram" and is_instagram_profile_url(url),
    }


def get_platform_info(platform_key: str) -> dict:
    return PLATFORMS.get(platform_key, {
        "name": platform_key.title(),
        "emoji": "📥",
        "db_key": f"{platform_key}_enabled",
        "default_enabled": False,
    })


def all_platforms() -> List[str]:
    return list(PLATFORMS.keys())
