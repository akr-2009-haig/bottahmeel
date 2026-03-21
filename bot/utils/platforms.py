"""
Multi-Platform Download Engine
All supported platforms with their URL patterns and display info
"""
import re
import os
import logging
import asyncio
import tempfile
from typing import Optional, Tuple, List

import yt_dlp

logger = logging.getLogger(__name__)

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
    """
    Detect which platform a URL belongs to.
    Returns: (url, platform_key) or (None, None)
    """
    urls = re.findall(r'https?://\S+', text)
    for url in urls:
        url = url.rstrip('.,;!?)')
        for platform_key, info in PLATFORMS.items():
            for pattern in info["patterns"]:
                if re.match(pattern, url, re.IGNORECASE):
                    return url, platform_key
    return None, None


def is_any_url(text: str) -> bool:
    """Check if text contains any URL."""
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
}


async def download_media(url: str, platform: str = "unknown") -> Tuple[Optional[str], str, str]:
    """
    Universal media downloader using yt-dlp.
    Returns: (file_path, media_type, title)
    media_type: 'video' | 'photo' | 'audio'
    """
    tmp_dir = tempfile.mkdtemp()
    outtmpl = os.path.join(tmp_dir, '%(id)s.%(ext)s')

    opts = {**YDL_BASE_OPTS}
    platform_specific = PLATFORM_OPTS.get(platform, {})
    opts.update(platform_specific)
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

            IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
            AUDIO_EXTS = {"mp3", "m4a", "ogg", "wav", "flac", "opus"}
            ext_lower = ext.lower()
            if ext_lower in IMAGE_EXTS:
                media_type = "photo"
            elif ext_lower in AUDIO_EXTS:
                media_type = "audio"
            else:
                media_type = "video"

            return filepath, media_type, title

    try:
        result = await loop.run_in_executor(None, _download)
        return result
    except Exception as e:
        logger.error(f"[{platform}] Download error: {e}")
        return None, "video", ""


def get_platform_info(platform_key: str) -> dict:
    """Get platform display info."""
    return PLATFORMS.get(platform_key, {
        "name": platform_key.title(),
        "emoji": "📥",
        "db_key": f"{platform_key}_enabled",
        "default_enabled": False,
    })


def all_platforms() -> List[str]:
    """Return list of all platform keys in order."""
    return list(PLATFORMS.keys())
