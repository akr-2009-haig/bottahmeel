from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from bot.config import load_settings

logger = logging.getLogger(__name__)


def _base_dir() -> Path:
    base_dir = Path(load_settings().temp_base_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def create_temp_download_dir(job_prefix: str = "download") -> str:
    safe_prefix = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in job_prefix)[:48] or "download"
    return tempfile.mkdtemp(prefix=f"{safe_prefix}-", dir=str(_base_dir()))


def cleanup_path(filepath: str | None) -> None:
    if not filepath:
        return

    try:
        path = Path(filepath).resolve()
        base_dir = _base_dir()
        if base_dir not in path.parents:
            logger.warning("Refusing to cleanup path outside temp base dir: %s", path)
            return

        if path.is_file():
            path.unlink(missing_ok=True)
            parent = path.parent
        else:
            parent = path

        if parent.exists() and parent.is_dir():
            shutil.rmtree(parent, ignore_errors=True)
    except Exception as exc:
        logger.error("Cleanup error for %s: %s", filepath, exc)


def cleanup_stale_directories(retention_seconds: int | None = None) -> int:
    settings = load_settings()
    cutoff_seconds = retention_seconds or settings.temp_retention_hours * 3600
    cutoff = time.time() - max(cutoff_seconds, 0)
    removed = 0
    base_dir = _base_dir()

    for entry in base_dir.iterdir():
        try:
            if not entry.is_dir():
                continue
            if entry.stat().st_mtime > cutoff:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.warning("Failed to cleanup stale temp directory %s: %s", entry, exc)
    return removed
