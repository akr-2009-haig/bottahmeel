import os
import tempfile
import time
import unittest
from unittest.mock import patch

from bot.config.settings import load_settings
from bot.temp.manager import cleanup_path, cleanup_stale_directories, create_temp_download_dir


class TempManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="karar-tests-")
        load_settings.cache_clear()
        self.env = patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "token",
            "DATABASE_URL": "sqlite:///test.db",
            "BOT_TEMP_DIR": self.temp_root,
        }, clear=False)
        self.env.start()
        load_settings.cache_clear()

    def tearDown(self):
        self.env.stop()
        load_settings.cache_clear()

    def test_create_temp_download_dir_uses_configured_base_dir(self):
        download_dir = create_temp_download_dir("job/unsafe")
        self.assertTrue(download_dir.startswith(self.temp_root))
        self.assertIn("job-unsafe", download_dir)

    def test_cleanup_path_removes_job_directory(self):
        download_dir = create_temp_download_dir("cleanup")
        file_path = os.path.join(download_dir, "video.mp4")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("data")
        cleanup_path(file_path)
        self.assertFalse(os.path.exists(download_dir))

    def test_cleanup_stale_directories_only_removes_old_directories(self):
        old_dir = create_temp_download_dir("old")
        new_dir = create_temp_download_dir("new")
        old_time = time.time() - 7200
        os.utime(old_dir, (old_time, old_time))
        removed = cleanup_stale_directories(retention_seconds=3600)
        self.assertEqual(removed, 1)
        self.assertFalse(os.path.exists(old_dir))
        self.assertTrue(os.path.exists(new_dir))
