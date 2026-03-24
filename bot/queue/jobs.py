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
_MAX_ERROR_MESSAGE_LENGTH = 2048


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


def _format_job_error(previous_error: str | None, message: str) -> str:
    latest_error = message.strip()
    if len(latest_error) >= _MAX_ERROR_MESSAGE_LENGTH:
        return latest_error[:_MAX_ERROR_MESSAGE_LENGTH]
    if not previous_error or not previous_error.strip() or previous_error.strip() == latest_error:
        return latest_error
    separator = " | "
    available_for_previous = _MAX_ERROR_MESSAGE_LENGTH - len(separator) - len(latest_error)
    if available_for_previous <= 0:
        return latest_error
    previous_prefix = previous_error.strip()
    if len(previous_prefix) > available_for_previous:
        trim_length = max(available_for_previous - 1, 0)
        previous_prefix = f"{previous_prefix[:trim_length]}…" if trim_length else ""
    return f"{previous_prefix}{separator}{latest_error}".strip()


def _age_seconds(now: datetime, value: datetime | None) -> int:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int((now - value).total_seconds())


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
        logger.info(
            "Enqueued background job id=%s type=%s priority=%s backend=%s",
            job.id,
            job_type,
            priority,
            _queue_backend(),
        )
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
            return None
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
        job.locked_at = None
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
            job.error_message = _format_job_error(job.error_message, error_message)
            job.completed_at = datetime.now(timezone.utc)
            logger.error(
                "Background job id=%s exhausted retries attempts=%s max_attempts=%s task_id=%s error=%s",
                job.id,
                job.attempts,
                job.max_attempts,
                task_id,
                error_message,
            )
        else:
            job.status = JobStatus.RETRY
            job.error_message = _format_job_error(job.error_message, error_message)
            job.available_at = datetime.now(timezone.utc) + timedelta(seconds=max(delay_seconds, 1))
            logger.warning(
                "Retrying background job id=%s attempt=%s/%s delay_seconds=%s task_id=%s error=%s",
                job.id,
                job.attempts,
                job.max_attempts,
                delay_seconds,
                task_id,
                error_message,
            )
        job.locked_at = None
        if job.status == JobStatus.FAILED and task_id:
            job.celery_task_id = task_id
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
        job.error_message = _format_job_error(job.error_message, error_message)
        job.completed_at = datetime.now(timezone.utc)
        job.locked_at = None
        if task_id:
            job.celery_task_id = task_id
        logger.error(
            "Background job id=%s failed permanently attempts=%s max_attempts=%s task_id=%s error=%s",
            job.id,
            job.attempts,
            job.max_attempts,
            task_id,
            error_message,
        )
        db.commit()
    finally:
        db.close()


def recover_stale_processing_jobs(*, lock_timeout_seconds: int | None = None) -> dict[str, int]:
    settings = load_settings()
    timeout_seconds = max(lock_timeout_seconds or settings.job_lock_timeout_seconds, 1)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    db = SessionLocal()
    try:
        stale_jobs = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.status == JobStatus.PROCESSING,
                BackgroundJob.locked_at.is_not(None),
                BackgroundJob.locked_at <= cutoff,
            )
            .order_by(asc(BackgroundJob.locked_at), asc(BackgroundJob.id))
            .all()
        )
        retried = 0
        failed = 0
        for job in stale_jobs:
            recovery_message = (
                f"Processing lock expired after {timeout_seconds}s; previous worker={job.worker_name or 'unknown'}"
            )
            if job.attempts >= job.max_attempts:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                failed += 1
            else:
                job.status = JobStatus.RETRY
                job.available_at = datetime.now(timezone.utc)
                job.completed_at = None
                retried += 1
            job.error_message = _format_job_error(job.error_message, recovery_message)
            job.locked_at = None
            job.worker_name = None
            job.celery_task_id = None
        if stale_jobs:
            db.commit()
            logger.warning(
                "Recovered stale processing jobs total=%s retried=%s failed=%s timeout_seconds=%s",
                len(stale_jobs),
                retried,
                failed,
                timeout_seconds,
            )
        return {
            "total": len(stale_jobs),
            "retried": retried,
            "failed": failed,
        }
    finally:
        db.close()


def get_queue_stats() -> dict[str, Any]:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(seconds=max(load_settings().job_lock_timeout_seconds, 1))
    try:
        counts = {status.value: 0 for status in JobStatus}
        for status, total in db.query(BackgroundJob.status, func.count(BackgroundJob.id)).group_by(BackgroundJob.status).all():
            status_key = status.value if hasattr(status, "value") else str(status)
            counts[status_key] = total
        job_types: dict[str, dict[str, int]] = {}
        for job_type, status, total in (
            db.query(BackgroundJob.job_type, BackgroundJob.status, func.count(BackgroundJob.id))
            .group_by(BackgroundJob.job_type, BackgroundJob.status)
            .all()
        ):
            status_key = status.value if hasattr(status, "value") else str(status)
            job_counts = job_types.setdefault(job_type, {job_status.value: 0 for job_status in JobStatus})
            job_counts[status_key] = total
        ready_filter = and_(
            BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.RETRY]),
            BackgroundJob.available_at <= now,
        )
        oldest_pending = (
            db.query(BackgroundJob.created_at)
            .filter(BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.RETRY]))
            .order_by(asc(BackgroundJob.created_at))
            .first()
        )
        oldest_ready = (
            db.query(BackgroundJob.created_at)
            .filter(ready_filter)
            .order_by(asc(BackgroundJob.created_at))
            .first()
        )
        oldest_processing = (
            db.query(BackgroundJob.locked_at)
            .filter(
                BackgroundJob.status == JobStatus.PROCESSING,
                BackgroundJob.locked_at.is_not(None),
            )
            .order_by(asc(BackgroundJob.locked_at))
            .first()
        )
        ready_count = db.query(func.count(BackgroundJob.id)).filter(ready_filter).scalar() or 0
        delayed_retry_count = (
            db.query(func.count(BackgroundJob.id))
            .filter(
                BackgroundJob.status == JobStatus.RETRY,
                BackgroundJob.available_at > now,
            )
            .scalar()
            or 0
        )
        stale_processing_count = (
            db.query(func.count(BackgroundJob.id))
            .filter(
                BackgroundJob.status == JobStatus.PROCESSING,
                BackgroundJob.locked_at.is_not(None),
                BackgroundJob.locked_at <= stale_cutoff,
            )
            .scalar()
            or 0
        )
        return {
            "backend": _queue_backend(),
            "counts": counts,
            "job_types": job_types,
            "oldest_pending_age_seconds": _age_seconds(now, oldest_pending[0] if oldest_pending else None),
            "ready_count": int(ready_count),
            "delayed_retry_count": int(delayed_retry_count),
            "stale_processing_count": int(stale_processing_count),
            "oldest_ready_age_seconds": _age_seconds(now, oldest_ready[0] if oldest_ready else None),
            "oldest_processing_lock_age_seconds": _age_seconds(now, oldest_processing[0] if oldest_processing else None),
            "lock_timeout_seconds": max(load_settings().job_lock_timeout_seconds, 1),
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
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        result = process_background_job.apply_async(
            args=[job_id],
            queue=load_settings().queue_name,
            priority=max(0, min(priority, 9)),
        )
        if job:
            job.celery_task_id = result.id
            db.commit()
            logger.info("Queued Redis job %s as Celery task %s", job_id, result.id)
    except Exception:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.error_message = "Failed to dispatch job to Redis queue"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        else:
            db.rollback()
        logger.exception("Failed to dispatch job %s to Redis queue", job_id)
        raise
    finally:
        db.close()
