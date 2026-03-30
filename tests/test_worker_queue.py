import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import bot.database.db as db_module
from bot.config.settings import load_settings
from bot.database import (
    BackgroundJob,
    BroadcastLog,
    Download,
    JobStatus,
    PublishChannel,
    ScheduledPost,
    User,
    UserStatus,
    init_db,
)
from bot.queue import claim_job_for_processing, claim_next_job, complete_job, get_queue_stats, recover_stale_processing_jobs
from bot.queue.jobs import _format_job_error
from bot.services import DownloadService
from bot.workers.runner import _process_broadcast, _process_job


class WorkerQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="karar-worker-tests-")
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.env = patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "token",
            "DATABASE_URL": f"sqlite:///{self.db_path}",
            "BOT_TEMP_DIR": os.path.join(self.temp_dir.name, "downloads"),
            "WORKER_BATCH_SIZE": "2",
        }, clear=False)
        self.env.start()
        self._reset_db_state()
        init_db()

    def tearDown(self):
        self.env.stop()
        self._reset_db_state(dispose=True)
        self.temp_dir.cleanup()

    def _reset_db_state(self, *, dispose: bool = False):
        load_settings.cache_clear()
        db_module._settings_cache.clear()
        if dispose and db_module.engine is not None:
            db_module.engine.dispose()
        db_module.engine = None
        db_module.SessionLocal._factory = None

    def _session(self):
        return db_module.SessionLocal()

    async def test_queued_download_job_runs_through_worker_and_sends_document(self):
        db = self._session()
        try:
            user = User(
                telegram_id=12345,
                first_name="Queue",
                last_name="Tester",
                language_code="en",
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = user.id
        finally:
            db.close()

        download_dir = os.path.join(self.temp_dir.name, "downloads", "worker-download")
        os.makedirs(download_dir, exist_ok=True)
        file_path = os.path.join(download_dir, "file.pdf")
        with open(file_path, "wb") as handle:
            handle.write(b"pdf-data")

        job_id = DownloadService.enqueue_download(
            user_id=user_id,
            chat_id=777,
            url="https://drive.google.com/file/d/abc123/view",
            platform="google_drive",
            lang="en",
            status_message_id=55,
        )
        job = claim_next_job("test-worker")
        self.assertIsNotNone(job)
        self.assertEqual(job.id, job_id)

        bot = AsyncMock()
        with patch("bot.workers.runner.download_media", new=AsyncMock(return_value=(file_path, "document", "Shared file"))):
            result = await _process_job(bot, job)

        complete_job(job.id, result)

        self.assertEqual(result["status"], "sent")
        bot.send_document.assert_awaited_once()
        bot.delete_message.assert_awaited_once_with(chat_id=777, message_id=55)
        bot.send_chat_action.assert_awaited()

        db = self._session()
        try:
            persisted_job = db.query(BackgroundJob).filter_by(id=job.id).first()
            self.assertEqual(persisted_job.status.value, "completed")
            download = db.query(Download).filter_by(user_id=user_id, platform="google_drive", success=True).first()
            self.assertIsNotNone(download)
            self.assertEqual(download.media_type, "document")
        finally:
            db.close()

    async def test_broadcast_queue_batches_users_and_finishes_last_batch(self):
        db = self._session()
        try:
            users = [
                User(telegram_id=1001, first_name="U1", status=UserStatus.ACTIVE),
                User(telegram_id=1002, first_name="U2", status=UserStatus.ACTIVE),
                User(telegram_id=1003, first_name="U3", status=UserStatus.ACTIVE),
            ]
            db.add_all(users)
            log = BroadcastLog(text="hello", target_type="users", total_sent=0, total_failed=0, sent_by=999)
            db.add(log)
            db.commit()
            db.refresh(log)
            log_id = log.id
        finally:
            db.close()

        bot = AsyncMock()
        first_result = await _process_broadcast(bot, {
            "text": "hello",
            "target": "users",
            "broadcast_log_id": log_id,
            "offset": 0,
        })
        self.assertEqual(first_result["sent"], 2)
        self.assertEqual(first_result["failed"], 0)

        first_job = claim_next_job("broadcast-worker", allowed_job_types=["broadcast_batch"])
        self.assertIsNotNone(first_job)
        self.assertEqual(first_job.payload["offset"], 2)

        second_result = await _process_job(bot, first_job)
        complete_job(first_job.id, second_result)
        self.assertEqual(second_result["sent"], 1)

        db = self._session()
        try:
            log = db.query(BroadcastLog).filter_by(id=log_id).first()
            self.assertEqual(log.total_sent, 3)
            self.assertEqual(log.total_failed, 0)
            self.assertIsNotNone(log.finished_at)
            self.assertEqual(log.status, "completed")
            self.assertIsNone(log.last_job_id)
        finally:
            db.close()

        self.assertEqual(bot.send_message.await_count, 3)

    async def test_broadcast_queue_supports_publish_channels(self):
        db = self._session()
        try:
            channels = [
                PublishChannel(chat_id=-1001, title="C1", is_active=True),
                PublishChannel(chat_id=-1002, title="C2", is_active=True),
            ]
            db.add_all(channels)
            log = BroadcastLog(text="hello channels", target_type="channels", total_sent=0, total_failed=0, sent_by=999)
            db.add(log)
            db.commit()
            db.refresh(log)
            log_id = log.id
        finally:
            db.close()

        bot = AsyncMock()
        result = await _process_broadcast(bot, {
            "text": "hello channels",
            "target": "channels",
            "broadcast_log_id": log_id,
            "offset": 0,
            "scope": "active",
        })

        self.assertEqual(result["sent"], 2)
        self.assertEqual(bot.send_message.await_count, 2)

        follow_up_job = claim_next_job("broadcast-channel-worker", allowed_job_types=["broadcast_batch"])
        self.assertIsNotNone(follow_up_job)
        follow_up_result = await _process_job(bot, follow_up_job)
        complete_job(follow_up_job.id, follow_up_result)

        db = self._session()
        try:
            log = db.query(BroadcastLog).filter_by(id=log_id).first()
            self.assertEqual(log.total_sent, 2)
            self.assertEqual(log.status, "completed")
        finally:
            db.close()

    async def test_broadcast_queue_supports_media_payloads(self):
        db = self._session()
        try:
            user = User(telegram_id=2001, first_name="Media", status=UserStatus.ACTIVE)
            db.add(user)
            log = BroadcastLog(text="caption", target_type="users", total_sent=0, total_failed=0, sent_by=999)
            db.add(log)
            db.commit()
            db.refresh(log)
            log_id = log.id
        finally:
            db.close()

        bot = AsyncMock()
        result = await _process_broadcast(bot, {
            "text": "caption",
            "target": "users",
            "broadcast_log_id": log_id,
            "offset": 0,
            "scope": "active",
            "media_type": "photo",
            "media_file_id": "photo-file-id",
        })

        self.assertEqual(result["sent"], 1)
        bot.send_photo.assert_awaited_once_with(chat_id=2001, photo="photo-file-id", caption="caption")

    async def test_enqueue_due_scheduled_posts_dispatches_once_and_worker_completes_post(self):
        now = datetime.now(timezone.utc)
        db = self._session()
        try:
            channel = PublishChannel(chat_id=-100123456, username="pub1", title="Pub 1", is_active=True)
            db.add(channel)
            db.commit()
            db.refresh(channel)
            channel_id = channel.id
            post = ScheduledPost(
                text="Scheduled hello",
                channel_ids=[channel_id],
                scheduled_at=now - timedelta(minutes=1),
                repeat_type="once",
                created_by=999,
                is_active=True,
                is_sent=False,
            )
            db.add(post)
            db.commit()
            db.refresh(post)
            post_id = post.id
        finally:
            db.close()

        first_jobs = DownloadService.enqueue_due_scheduled_posts()
        second_jobs = DownloadService.enqueue_due_scheduled_posts()
        self.assertEqual(len(first_jobs), 1)
        self.assertEqual(second_jobs, [])

        job = claim_next_job("scheduled-worker", allowed_job_types=[DownloadService.scheduled_post_job_type])
        self.assertIsNotNone(job)

        bot = AsyncMock()
        result = await _process_job(bot, job)
        complete_job(job.id, result)

        self.assertEqual(result["status"], "sent")
        bot.send_message.assert_awaited_once_with(chat_id=-100123456, text="Scheduled hello", reply_markup=None)

        db = self._session()
        try:
            post = db.query(ScheduledPost).filter_by(id=post_id).first()
            channel = db.query(PublishChannel).filter_by(id=channel_id).first()
            persisted_job = db.query(BackgroundJob).filter_by(id=job.id).first()
            self.assertTrue(post.is_sent)
            self.assertFalse(post.is_active)
            self.assertIsNotNone(post.sent_at)
            self.assertEqual(post.last_job_id, job.id)
            self.assertEqual(channel.post_count, 1)
            self.assertEqual(persisted_job.status, JobStatus.COMPLETED)
        finally:
            db.close()

    async def test_download_retry_and_failure_update_status_message_in_place(self):
        db = self._session()
        try:
            user = User(
                telegram_id=777001,
                first_name="Retry",
                language_code="en",
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = user.id
        finally:
            db.close()

        job_id = DownloadService.enqueue_download(
            user_id=user_id,
            chat_id=555,
            url="https://drive.google.com/file/d/abc123/view",
            platform="google_drive",
            lang="en",
            status_message_id=44,
        )
        job = claim_next_job("retry-worker")
        self.assertEqual(job.id, job_id)

        bot = AsyncMock()
        with patch("bot.workers.runner.download_media", new=AsyncMock(side_effect=RuntimeError("temporary failure"))):
            with self.assertRaises(RuntimeError):
                await _process_job(bot, job)

        from bot.workers.runner import _notify_download_job_state
        await _notify_download_job_state(bot, job.payload or {}, state="retry", delay_seconds=30)
        await _notify_download_job_state(bot, job.payload or {}, state="failed")

        bot.edit_message_text.assert_any_await(
            chat_id=555,
            message_id=44,
            text="🔁 Processing hit a temporary issue. We will retry in about 30 seconds.",
        )
        bot.edit_message_text.assert_any_await(
            chat_id=555,
            message_id=44,
            text="❌ We could not complete this request after several attempts. You can resend the link to try again.",
        )

    async def test_failed_download_records_requested_media_type(self):
        db = self._session()
        try:
            user = User(telegram_id=333001, first_name="Audio", language_code="en", status=UserStatus.ACTIVE)
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = user.id
        finally:
            db.close()

        job_id = DownloadService.enqueue_download(
            user_id=user_id,
            chat_id=404,
            url="https://youtube.com/watch?v=abc123",
            platform="youtube",
            lang="en",
            status_message_id=12,
            download_mode="audio",
        )
        job = claim_next_job("failed-media-type-worker")
        self.assertEqual(job.id, job_id)

        bot = AsyncMock()
        with patch("bot.workers.runner.download_media", new=AsyncMock(return_value=(None, "audio", "generic"))):
            result = await _process_job(bot, job)

        self.assertEqual(result["status"], "failed")
        db = self._session()
        try:
            download = db.query(Download).filter_by(user_id=user_id, success=False).order_by(Download.id.desc()).first()
            self.assertIsNotNone(download)
            self.assertEqual(download.media_type, "audio")
        finally:
            db.close()

    async def test_large_download_is_rejected_before_upload(self):
        db = self._session()
        try:
            user = User(telegram_id=333002, first_name="Large", language_code="en", status=UserStatus.ACTIVE)
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = user.id
        finally:
            db.close()

        oversized_dir = os.path.join(self.temp_dir.name, "downloads", "oversized")
        os.makedirs(oversized_dir, exist_ok=True)
        oversized_path = os.path.join(oversized_dir, "video.mp4")
        with open(oversized_path, "wb") as handle:
            handle.write(b"0" * (2 * 1024 * 1024))

        with patch.dict(os.environ, {"MAX_UPLOAD_FILE_SIZE_MB": "0"}, clear=False):
            load_settings.cache_clear()
            job_id = DownloadService.enqueue_download(
                user_id=user_id,
                chat_id=405,
                url="https://youtube.com/watch?v=abc123",
                platform="youtube",
                lang="en",
                status_message_id=13,
            )
            job = claim_next_job("large-file-worker")
            self.assertEqual(job.id, job_id)

            bot = AsyncMock()
            with patch("bot.workers.runner.download_media", new=AsyncMock(return_value=(oversized_path, "video", ""))):
                result = await _process_job(bot, job)

        self.assertEqual(result["reason"], "file_too_large")
        bot.send_video.assert_not_awaited()
        bot.edit_message_text.assert_awaited()

    def test_claim_job_for_processing_is_idempotent_for_same_task_id(self):
        db = self._session()
        try:
            user = User(
                telegram_id=54321,
                first_name="Queue",
                last_name="Tester",
                language_code="en",
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = user.id
        finally:
            db.close()

        job_id = DownloadService.enqueue_download(
            user_id=user_id,
            chat_id=888,
            url="https://drive.google.com/file/d/abc123/view",
            platform="google_drive",
            lang="en",
            status_message_id=66,
        )

        job = claim_job_for_processing(job_id, "celery@test", task_id="task-1")
        self.assertIsNotNone(job)
        self.assertEqual(job.attempts, 1)

        same_job = claim_job_for_processing(job_id, "celery@test", task_id="task-1")
        self.assertIsNotNone(same_job)
        self.assertEqual(same_job.attempts, 1)

        other_job = claim_job_for_processing(job_id, "celery@test", task_id="task-2")
        self.assertIsNone(other_job)

    def test_queue_stats_reports_ready_retry_and_stale_processing_counts(self):
        now = datetime.now(timezone.utc)
        db = self._session()
        try:
            db.add_all([
                BackgroundJob(
                    job_type="download",
                    status=JobStatus.PENDING,
                    payload={"url": "https://example.com/1"},
                    available_at=now - timedelta(minutes=5),
                    created_at=now - timedelta(minutes=5),
                ),
                BackgroundJob(
                    job_type="download",
                    status=JobStatus.RETRY,
                    payload={"url": "https://example.com/2"},
                    available_at=now + timedelta(minutes=2),
                    created_at=now - timedelta(minutes=3),
                    attempts=1,
                    max_attempts=3,
                ),
                BackgroundJob(
                    job_type="download",
                    status=JobStatus.PROCESSING,
                    payload={"url": "https://example.com/3"},
                    locked_at=now - timedelta(hours=2),
                    created_at=now - timedelta(hours=2),
                    available_at=now - timedelta(hours=2),
                    attempts=1,
                    max_attempts=3,
                    worker_name="stalled-worker",
                ),
            ])
            db.commit()
        finally:
            db.close()

        stats = get_queue_stats()

        self.assertEqual(stats["counts"]["pending"], 1)
        self.assertEqual(stats["counts"]["retry"], 1)
        self.assertEqual(stats["counts"]["processing"], 1)
        self.assertIn("download", stats["job_types"])
        self.assertEqual(stats["job_types"]["download"]["pending"], 1)
        self.assertEqual(stats["job_types"]["download"]["retry"], 1)
        self.assertEqual(stats["job_types"]["download"]["processing"], 1)
        self.assertEqual(stats["ready_count"], 1)
        self.assertEqual(stats["delayed_retry_count"], 1)
        self.assertEqual(stats["stale_processing_count"], 1)
        self.assertGreaterEqual(stats["oldest_pending_age_seconds"], 180)
        self.assertGreaterEqual(stats["oldest_processing_lock_age_seconds"], 3600)

    def test_recover_stale_processing_jobs_retries_or_fails_expired_jobs(self):
        now = datetime.now(timezone.utc)
        db = self._session()
        try:
            retry_job_row = BackgroundJob(
                job_type="download",
                status=JobStatus.PROCESSING,
                payload={"url": "https://example.com/retry"},
                available_at=now - timedelta(minutes=10),
                created_at=now - timedelta(minutes=10),
                locked_at=now - timedelta(hours=2),
                attempts=1,
                max_attempts=3,
                worker_name="retry-worker",
                celery_task_id="task-retry",
            )
            failed_job_row = BackgroundJob(
                job_type="download",
                status=JobStatus.PROCESSING,
                payload={"url": "https://example.com/fail"},
                available_at=now - timedelta(minutes=20),
                created_at=now - timedelta(minutes=20),
                locked_at=now - timedelta(hours=2),
                attempts=3,
                max_attempts=3,
                worker_name="failed-worker",
                celery_task_id="task-fail",
            )
            db.add_all([retry_job_row, failed_job_row])
            db.commit()
            retry_job_id = retry_job_row.id
            failed_job_id = failed_job_row.id
        finally:
            db.close()

        recovered = recover_stale_processing_jobs(lock_timeout_seconds=60)
        self.assertEqual(recovered, {"total": 2, "retried": 1, "failed": 1})

        db = self._session()
        try:
            retried_job = db.query(BackgroundJob).filter_by(id=retry_job_id).first()
            failed_job = db.query(BackgroundJob).filter_by(id=failed_job_id).first()
            self.assertEqual(retried_job.status, JobStatus.RETRY)
            self.assertIsNone(retried_job.locked_at)
            self.assertIsNone(retried_job.worker_name)
            self.assertIsNone(retried_job.celery_task_id)
            self.assertIn("Processing lock expired", retried_job.error_message)
            self.assertEqual(failed_job.status, JobStatus.FAILED)
            self.assertIsNone(failed_job.locked_at)
            self.assertIsNotNone(failed_job.completed_at)
            self.assertIn("Processing lock expired", failed_job.error_message)
        finally:
            db.close()

    def test_format_job_error_preserves_latest_message_when_truncating(self):
        previous_error = "old-" * 600
        latest_error = "latest failure details"

        formatted = _format_job_error(previous_error, latest_error)

        self.assertIn(latest_error, formatted)
        self.assertLessEqual(len(formatted), 2048)
