from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import redis
from sqlalchemy import and_, asc, case, desc, func, or_

from bot.config import load_settings
from bot.database import BackgroundJob, JobStatus, SessionLocal

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis | None:
    global _redis_client
    settings = load_settings()
    if not settings.redis_url:
        return None
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _queue_backend() -> str:
    return load_settings().queue_backend


def enqueue_job(job_type: str, payload: dict[str, Any], *, priority: int = 0, max_attempts: int = 3) -> int:
    db = SessionLocal()
    try:
        job = BackgroundJob(
            job_type=job_type,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
            status=JobStatus.PENDING,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        if _queue_backend() == "redis":
            _dispatch_job(job.id, priority=priority)
        return job.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def claim_next_job(worker_name: str, *, allowed_job_types: list[str] | None = None) -> BackgroundJob | None:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        query = db.query(BackgroundJob).filter(
            BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.RETRY]),
            BackgroundJob.available_at <= now,
        )
        if allowed_job_types:
            query = query.filter(BackgroundJob.job_type.in_(allowed_job_types))
        query = query.order_by(desc(BackgroundJob.priority), asc(BackgroundJob.created_at))
        try:
            job = query.with_for_update(skip_locked=True).first()
        except Exception:
            job = query.first()
        if not job:
            return None
        job.status = JobStatus.PROCESSING
        job.locked_at = now
        job.worker_name = worker_name
        job.attempts += 1
        db.commit()
        db.refresh(job)
        db.expunge(job)
        return job
    finally:
        db.close()


def claim_job_for_processing(job_id: int, worker_name: str, *, task_id: str | None = None) -> BackgroundJob | None:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        claimed = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.id == job_id,
                BackgroundJob.available_at <= now,
                or_(
                    BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.RETRY]),
                    and_(BackgroundJob.status == JobStatus.PROCESSING, BackgroundJob.celery_task_id == task_id),
                ),
            )
            .update(
                {
                    BackgroundJob.status: JobStatus.PROCESSING,
                    BackgroundJob.locked_at: now,
                    BackgroundJob.worker_name: worker_name,
                    BackgroundJob.celery_task_id: task_id,
                    BackgroundJob.attempts: case(
                        (BackgroundJob.status == JobStatus.PROCESSING, BackgroundJob.attempts),
                        else_=BackgroundJob.attempts + 1,
                    ),
                },
                synchronize_session=False,
            )
        )
        if not claimed:
            db.rollback()
            return None
        db.commit()
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
            return
        db.expunge(job)
        return job
    finally:
        db.close()


def complete_job(job_id: int, result: dict[str, Any] | None = None, *, task_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
            return
        if task_id and job.celery_task_id and job.celery_task_id != task_id:
            return
        job.status = JobStatus.COMPLETED
        job.result = result or {}
        job.error_message = None
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def retry_job(job_id: int, error_message: str, *, delay_seconds: int = 30, task_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
            return
        if task_id and job.celery_task_id and job.celery_task_id != task_id:
            return
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED
            job.error_message = error_message
            job.completed_at = datetime.now(timezone.utc)
        else:
            job.status = JobStatus.RETRY
            job.error_message = error_message
            job.available_at = datetime.now(timezone.utc) + timedelta(seconds=max(delay_seconds, 1))
        db.commit()
    finally:
        db.close()


def fail_job(job_id: int, error_message: str, *, task_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
            return
        if task_id and job.celery_task_id and job.celery_task_id != task_id:
            return
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def get_queue_stats() -> dict[str, Any]:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        counts = {status.value: 0 for status in JobStatus}
        for status, total in db.query(BackgroundJob.status, func.count(BackgroundJob.id)).group_by(BackgroundJob.status).all():
            counts[status.value] = total
        oldest_pending = (
            db.query(BackgroundJob.created_at)
            .filter(BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.RETRY]))
            .order_by(asc(BackgroundJob.created_at))
            .first()
        )
        return {
            "backend": _queue_backend(),
            "counts": counts,
            "oldest_pending_age_seconds": int((now - oldest_pending[0]).total_seconds()) if oldest_pending and oldest_pending[0] else 0,
            "broker_depth": get_broker_queue_depth(),
        }
    finally:
        db.close()


def get_broker_queue_depth() -> int | None:
    settings = load_settings()
    if settings.queue_backend != "redis":
        return None
    client = _get_redis_client()
    if client is None:
        return None
    try:
        return int(client.llen(settings.queue_name))
    except Exception:
        logger.exception("Failed to read Redis queue depth")
        return None


def ping_broker() -> bool:
    settings = load_settings()
    if settings.queue_backend != "redis":
        return True
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        logger.exception("Redis broker ping failed")
        return False


def _dispatch_job(job_id: int, *, priority: int) -> None:
    from bot.workers.runner import process_background_job

    db = SessionLocal()
    try:
        result = process_background_job.apply_async(
            args=[job_id],
            queue=load_settings().queue_name,
            priority=max(0, min(priority, 9)),
        )
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if job:
            job.celery_task_id = result.id
            db.commit()
            logger.info("Queued Redis job %s as Celery task %s", job_id, result.id)
    except Exception:
        db.rollback()
        logger.exception("Failed to dispatch job %s to Redis queue", job_id)
        raise
    finally:
        db.close()
