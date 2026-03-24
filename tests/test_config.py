import os
import unittest
from unittest.mock import patch

from bot.config.settings import RuntimeMode, load_settings


class SettingsTests(unittest.TestCase):
    def tearDown(self):
        load_settings.cache_clear()

    def test_webhook_requires_webhook_url(self):
        with patch.dict(os.environ, {
            "BOT_MODE": RuntimeMode.WEBHOOK.value,
            "TELEGRAM_BOT_TOKEN": "token",
            "DATABASE_URL": "sqlite:///test.db",
            "WEBHOOK_URL": "",
        }, clear=False):
            settings = load_settings()
            with self.assertRaises(EnvironmentError):
                settings.validate_for_mode()

    def test_polling_accepts_minimal_configuration(self):
        with patch.dict(os.environ, {
            "BOT_MODE": RuntimeMode.POLLING.value,
            "TELEGRAM_BOT_TOKEN": "token",
            "DATABASE_URL": "sqlite:///test.db",
        }, clear=False):
            settings = load_settings()
            settings.validate_for_mode()
            self.assertEqual(settings.mode, RuntimeMode.POLLING)

    def test_queue_backend_defaults_to_database_without_redis_url(self):
        with patch.dict(os.environ, {
            "BOT_MODE": RuntimeMode.POLLING.value,
            "TELEGRAM_BOT_TOKEN": "token",
            "DATABASE_URL": "sqlite:///test.db",
            "REDIS_URL": "",
            "QUEUE_BACKEND": "",
        }, clear=False):
            settings = load_settings()
            self.assertEqual(settings.queue_backend, "database")

    def test_queue_backend_defaults_to_redis_when_redis_url_exists(self):
        with patch.dict(os.environ, {
            "BOT_MODE": RuntimeMode.POLLING.value,
            "TELEGRAM_BOT_TOKEN": "token",
            "DATABASE_URL": "sqlite:///test.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "QUEUE_BACKEND": "",
        }, clear=False):
            settings = load_settings()
            self.assertEqual(settings.queue_backend, "redis")
            settings.validate_for_mode()
