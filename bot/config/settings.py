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
    queue_backend: str
    redis_url: str
    queue_name: str
    webhook_url: str
    webhook_full_url: str
    webhook_path: str
    webhook_secret_token: str
    disable_auto_webhook_set: bool
    listen_host: str
    port: int
    temp_base_dir: str
    temp_retention_hours: int
    worker_poll_interval: float
    worker_batch_size: int
    worker_concurrency: int
    worker_name: str
    worker_heartbeat_ttl_seconds: int
    job_lock_timeout_seconds: int
    healthcheck_port: int
    enable_healthcheck: bool
    log_level: str
    rate_limit_requests_per_window: int
    rate_limit_window_seconds: int
    rate_limit_block_seconds: int

    def validate_for_mode(self) -> None:
        if not self.bot_token:
            raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")
        if not self.database_url:
            raise EnvironmentError("DATABASE_URL is not set")
        if self.queue_backend == "redis" and not self.redis_url:
            raise EnvironmentError("REDIS_URL must be set when QUEUE_BACKEND=redis")
        if self.mode is RuntimeMode.WEBHOOK and not (self.webhook_full_url or self.webhook_url):
            raise EnvironmentError("WEBHOOK_FULL_URL or WEBHOOK_URL must be set when BOT_MODE=webhook")


@lru_cache(maxsize=1)
def load_settings() -> AppSettings:
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    webhook_full_url = os.environ.get("WEBHOOK_FULL_URL", "").strip()
    mode_raw = os.environ.get("BOT_MODE", "").strip().lower()
    if not mode_raw:
        mode_raw = (
            RuntimeMode.WEBHOOK.value
            if os.environ.get("PORT", "").strip() and (webhook_full_url or webhook_url)
            else RuntimeMode.POLLING.value
        )
    try:
        mode = RuntimeMode(mode_raw)
    except ValueError as exc:
        raise EnvironmentError(f"Unsupported BOT_MODE: {mode_raw}") from exc

    redis_url = os.environ.get("REDIS_URL", "").strip()
    queue_backend_raw = os.environ.get("QUEUE_BACKEND", "").strip().lower()
    if queue_backend_raw:
        if queue_backend_raw not in {"database", "redis"}:
            raise EnvironmentError(f"Unsupported QUEUE_BACKEND: {queue_backend_raw}")
        queue_backend = queue_backend_raw
    else:
        queue_backend = "redis" if redis_url else "database"

    webhook_path = os.environ.get("WEBHOOK_PATH", "/telegram/webhook").strip() or "/telegram/webhook"
    if not webhook_path.startswith("/"):
        webhook_path = f"/{webhook_path}"

    return AppSettings(
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        bot_owner_id=int(os.environ.get("BOT_OWNER_ID", "0").strip() or "0"),
        database_url=os.environ.get("DATABASE_URL", "").strip(),
        mode=mode,
        queue_backend=queue_backend,
        redis_url=redis_url,
        queue_name=os.environ.get("QUEUE_NAME", "karar-bot-jobs").strip() or "karar-bot-jobs",
        webhook_url=webhook_url,
        webhook_full_url=webhook_full_url,
        webhook_path=webhook_path,
        webhook_secret_token=os.environ.get("WEBHOOK_SECRET_TOKEN", "").strip(),
        disable_auto_webhook_set=os.environ.get("DISABLE_AUTO_WEBHOOK_SET", "false").strip().lower() == "true",
        listen_host=os.environ.get("BOT_LISTEN_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.environ.get("PORT", "8080").strip() or "8080"),
        temp_base_dir=os.environ.get("BOT_TEMP_DIR", "/tmp/karar-bot").strip() or "/tmp/karar-bot",
        temp_retention_hours=int(os.environ.get("TEMP_RETENTION_HOURS", "6").strip() or "6"),
        worker_poll_interval=float(os.environ.get("WORKER_POLL_INTERVAL", "1.0").strip() or "1.0"),
        worker_batch_size=int(os.environ.get("WORKER_BATCH_SIZE", "25").strip() or "25"),
        worker_concurrency=int(os.environ.get("WORKER_CONCURRENCY", "1").strip() or "1"),
        worker_name=os.environ.get("WORKER_NAME", "download-worker").strip() or "download-worker",
        worker_heartbeat_ttl_seconds=int(os.environ.get("WORKER_HEARTBEAT_TTL_SECONDS", "90").strip() or "90"),
        job_lock_timeout_seconds=int(os.environ.get("JOB_LOCK_TIMEOUT_SECONDS", "3600").strip() or "3600"),
        healthcheck_port=int(os.environ.get("HEALTHCHECK_PORT", "8081").strip() or "8081"),
        enable_healthcheck=os.environ.get("ENABLE_HEALTHCHECK", "true").strip().lower() == "true",
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        rate_limit_requests_per_window=int(os.environ.get("RATE_LIMIT_REQUESTS_PER_WINDOW", "4").strip() or "4"),
        rate_limit_window_seconds=int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "1800").strip() or "1800"),
        rate_limit_block_seconds=int(os.environ.get("RATE_LIMIT_BLOCK_SECONDS", "1800").strip() or "1800"),
    )
