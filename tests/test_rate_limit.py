import os
import unittest
from unittest.mock import patch

from bot.config.settings import load_settings
from bot.security import rate_limit as rate_limit_module


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "token",
            "DATABASE_URL": "sqlite:///test.db",
            "REDIS_URL": "",
            "RATE_LIMIT_REQUESTS_PER_WINDOW": "2",
            "RATE_LIMIT_WINDOW_SECONDS": "60",
            "RATE_LIMIT_BLOCK_SECONDS": "30",
        }, clear=False)
        self.env.start()
        load_settings.cache_clear()
        rate_limit_module._memory_hits.clear()
        rate_limit_module._memory_blocks.clear()
        rate_limit_module._redis_client = None

    def tearDown(self):
        self.env.stop()
        load_settings.cache_clear()
        rate_limit_module._memory_hits.clear()
        rate_limit_module._memory_blocks.clear()
        rate_limit_module._redis_client = None

    def test_rate_limit_blocks_after_threshold(self):
        self.assertEqual(rate_limit_module.check_download_rate_limit(123), (True, 0))
        self.assertEqual(rate_limit_module.check_download_rate_limit(123), (True, 0))
        allowed, retry_after = rate_limit_module.check_download_rate_limit(123)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)

    def test_admins_are_exempt(self):
        for _ in range(5):
            allowed, retry_after = rate_limit_module.check_download_rate_limit(999, is_admin=True)
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0)

    def test_default_settings_match_four_requests_per_half_hour(self):
        with patch.dict(os.environ, {
            "RATE_LIMIT_REQUESTS_PER_WINDOW": "",
            "RATE_LIMIT_WINDOW_SECONDS": "",
            "RATE_LIMIT_BLOCK_SECONDS": "",
        }, clear=False):
            load_settings.cache_clear()
            settings = load_settings()

        self.assertEqual(settings.rate_limit_requests_per_window, 4)
        self.assertEqual(settings.rate_limit_window_seconds, 1800)
        self.assertEqual(settings.rate_limit_block_seconds, 1800)
