from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery import Celery, signals
from kombu import Queue

from bot.config import load_settings
from bot.database import SessionLocal, WorkerHeartbeat, init_db

logger = logging.getLogger(__name__)

_celery_app: Celery | None = None


def get_celery_app() -> Celery:
    global _celery_app
    if _celery_app is not None:
        return _celery_app

    settings = load_settings()
    broker_url = settings.redis_url or "memory://"
    app = Celery("karar_bot", broker=broker_url, backend=broker_url if settings.redis_url else None)
    app.conf.update(
        task_default_queue=settings.queue_name,
        task_queues=(Queue(settings.queue_name),),
        task_track_started=True,
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"visibility_timeout": settings.job_lock_timeout_seconds},
        result_backend_transport_options={"visibility_timeout": settings.job_lock_timeout_seconds},
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        enable_utc=True,
        timezone="UTC",
    )
    _celery_app = app
    return app


def _update_worker_heartbeat(worker_name: str, *, status: str, active_task_id: str | None = None, completed: bool = False) -> None:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        heartbeat = db.query(WorkerHeartbeat).filter_by(worker_name=worker_name).first()
        if heartbeat is None:
            heartbeat = WorkerHeartbeat(worker_name=worker_name)
            db.add(heartbeat)
        heartbeat.status = status
        heartbeat.active_task_id = active_task_id
        heartbeat.last_seen = now
        if status == "ready" and heartbeat.last_started_at is None:
            heartbeat.last_started_at = now
        if completed:
            heartbeat.last_completed_at = now
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to update worker heartbeat for %s: %s", worker_name, exc)
    finally:
        db.close()


@signals.worker_process_init.connect
def _worker_process_init(**_kwargs) -> None:
    init_db()


@signals.worker_ready.connect
def _worker_ready(sender=None, **_kwargs) -> None:
    worker_name = getattr(sender, "hostname", None) or "celery-worker"
    _update_worker_heartbeat(worker_name, status="ready")


@signals.heartbeat_sent.connect
def _worker_heartbeat_sent(sender=None, **_kwargs) -> None:
    worker_name = getattr(sender, "hostname", None) or "celery-worker"
    _update_worker_heartbeat(worker_name, status="ready")


@signals.worker_shutdown.connect
def _worker_shutdown(sender=None, **_kwargs) -> None:
    worker_name = getattr(sender, "hostname", None) or "celery-worker"
    _update_worker_heartbeat(worker_name, status="stopped")


@signals.task_prerun.connect
def _task_prerun(task_id=None, task=None, **_kwargs) -> None:
    worker_name = getattr(task.request, "hostname", None) or "celery-worker"
    _update_worker_heartbeat(worker_name, status="busy", active_task_id=task_id)


@signals.task_postrun.connect
def _task_postrun(task_id=None, task=None, **_kwargs) -> None:
    worker_name = getattr(task.request, "hostname", None) or "celery-worker"
    _update_worker_heartbeat(worker_name, status="ready", completed=True)


celery_app = get_celery_app()
