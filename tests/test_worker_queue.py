import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import bot.database.db as db_module
from bot.config.settings import load_settings
from bot.database import BackgroundJob, BroadcastLog, Download, User, UserStatus, init_db
from bot.queue import claim_next_job, complete_job
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
        finally:
            db.close()

        self.assertEqual(bot.send_message.await_count, 3)
