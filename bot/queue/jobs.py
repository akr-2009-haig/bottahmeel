from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import asc, desc

from bot.database import BackgroundJob, JobStatus, SessionLocal

logger = logging.getLogger(__name__)


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
        return job.id
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


def complete_job(job_id: int, result: dict[str, Any] | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
            return
        job.status = JobStatus.COMPLETED
        job.result = result or {}
        job.error_message = None
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def retry_job(job_id: int, error_message: str, *, delay_seconds: int = 30) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
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


def fail_job(job_id: int, error_message: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
            return
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
