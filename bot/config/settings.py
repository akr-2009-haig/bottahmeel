from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache


class RuntimeMode(str, Enum):
    POLLING = "polling"
    WEBHOOK = "webhook"
    WORKER = "worker"


@dataclass(frozen=True)
class AppSettings:
    bot_token: str
    bot_owner_id: int
    database_url: str
    mode: RuntimeMode
    webhook_url: str
    webhook_path: str
    listen_host: str
    port: int
    temp_base_dir: str
    temp_retention_hours: int
    worker_poll_interval: float
    worker_batch_size: int
    worker_name: str
    healthcheck_port: int
    enable_healthcheck: bool
    log_level: str

    def validate_for_mode(self) -> None:
        if not self.bot_token:
            raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")
        if not self.database_url:
            raise EnvironmentError("DATABASE_URL is not set")
        if self.mode is RuntimeMode.WEBHOOK and not self.webhook_url:
            raise EnvironmentError("WEBHOOK_URL must be set when BOT_MODE=webhook")


@lru_cache(maxsize=1)
def load_settings() -> AppSettings:
    mode_raw = os.environ.get("BOT_MODE", RuntimeMode.POLLING.value).strip().lower() or RuntimeMode.POLLING.value
    try:
        mode = RuntimeMode(mode_raw)
    except ValueError as exc:
        raise EnvironmentError(f"Unsupported BOT_MODE: {mode_raw}") from exc

    return AppSettings(
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        bot_owner_id=int(os.environ.get("BOT_OWNER_ID", "0").strip() or "0"),
        database_url=os.environ.get("DATABASE_URL", "").strip(),
        mode=mode,
        webhook_url=os.environ.get("WEBHOOK_URL", "").strip(),
        webhook_path=os.environ.get("WEBHOOK_PATH", "/telegram/webhook").strip() or "/telegram/webhook",
        listen_host=os.environ.get("BOT_LISTEN_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.environ.get("PORT", "8080").strip() or "8080"),
        temp_base_dir=os.environ.get("BOT_TEMP_DIR", "/tmp/karar-bot").strip() or "/tmp/karar-bot",
        temp_retention_hours=int(os.environ.get("TEMP_RETENTION_HOURS", "6").strip() or "6"),
        worker_poll_interval=float(os.environ.get("WORKER_POLL_INTERVAL", "1.0").strip() or "1.0"),
        worker_batch_size=int(os.environ.get("WORKER_BATCH_SIZE", "25").strip() or "25"),
        worker_name=os.environ.get("WORKER_NAME", "download-worker").strip() or "download-worker",
        healthcheck_port=int(os.environ.get("HEALTHCHECK_PORT", "8081").strip() or "8081"),
        enable_healthcheck=os.environ.get("ENABLE_HEALTHCHECK", "true").strip().lower() == "true",
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
    )
