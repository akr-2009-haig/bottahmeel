"""
Multi-Platform Download Engine
All supported platforms with their URL patterns and display info
"""
import re
import os
import logging
import asyncio
from typing import Optional, Tuple, List

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
}


async def download_media(url: str, platform: str = "unknown") -> Tuple[Optional[str], str, str]:
    tmp_dir = create_temp_download_dir(platform)
    outtmpl = os.path.join(tmp_dir, '%(id)s.%(ext)s')

    opts = {**YDL_BASE_OPTS}
    opts.update(PLATFORM_OPTS.get(platform, {}))
    opts['outtmpl'] = outtmpl
    if 'format' not in opts:
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
                    filepath = os.path.join(tmp_dir, sorted(files)[0])
                    ext = filepath.rsplit('.', 1)[-1].lower()
                else:
                    return None, "video", title

            ext_lower = ext.lower()
            if ext_lower in IMAGE_EXTS:
                media_type = "photo"
            elif ext_lower in AUDIO_EXTS:
                media_type = "audio"
            elif ext_lower in VIDEO_EXTS:
                media_type = "video"
            else:
                logger.warning("[%s] Treating unknown extension '%s' as document for %s", platform, ext_lower, url)
                media_type = "document"

            return filepath, media_type, title

    try:
        return await loop.run_in_executor(None, _download)
    except Exception as e:
        logger.error(f"[{platform}] Download error: {e}")
        return None, "video", ""


def get_platform_info(platform_key: str) -> dict:
    return PLATFORMS.get(platform_key, {
        "name": platform_key.title(),
        "emoji": "📥",
        "db_key": f"{platform_key}_enabled",
        "default_enabled": False,
    })


def all_platforms() -> List[str]:
    return list(PLATFORMS.keys())
