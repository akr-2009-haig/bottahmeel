import unittest
from threading import Event
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from bot.config.settings import AppSettings, RuntimeMode
from bot.webhook.server import _build_webhook_registration_url, create_webhook_app


class WebhookServerTests(unittest.TestCase):
    def _settings(self, **overrides):
        defaults = dict(
            bot_token="token",
            bot_owner_id=1,
            database_url="sqlite:///test.db",
            mode=RuntimeMode.WEBHOOK,
            queue_backend="database",
            redis_url="",
            queue_name="jobs",
            webhook_url="https://example.com",
            webhook_full_url="",
            webhook_path="/telegram/webhook",
            webhook_secret_token="",
            disable_auto_webhook_set=False,
            listen_host="0.0.0.0",
            port=8080,
            temp_base_dir="/tmp",
            temp_retention_hours=1,
            worker_poll_interval=1.0,
            worker_batch_size=1,
            worker_concurrency=1,
            worker_name="worker",
            worker_heartbeat_ttl_seconds=90,
            job_lock_timeout_seconds=90,
            healthcheck_port=8081,
            enable_healthcheck=True,
            log_level="INFO",
            rate_limit_requests_per_window=1,
            rate_limit_window_seconds=1,
            rate_limit_block_seconds=1,
        )
        defaults.update(overrides)
        return AppSettings(**defaults)

    def test_prefers_full_webhook_url_when_present(self):
        settings = self._settings(
            webhook_url="https://example.com",
            webhook_full_url="https://example.com/telegram/webhook",
        )
        self.assertEqual(
            _build_webhook_registration_url(settings),
            "https://example.com/telegram/webhook",
        )

    def test_avoids_duplicate_path_when_base_url_already_contains_path(self):
        settings = self._settings(webhook_url="https://example.com/telegram/webhook")
        self.assertEqual(
            _build_webhook_registration_url(settings),
            "https://example.com/telegram/webhook",
        )

    def test_builds_webhook_url_from_base_and_path(self):
        settings = self._settings(webhook_url="https://example.com/")
        self.assertEqual(
            _build_webhook_registration_url(settings),
            "https://example.com/telegram/webhook",
        )

    def test_returns_503_until_webhook_runtime_finishes_initializing(self):
        settings = self._settings(disable_auto_webhook_set=True, queue_backend="redis", redis_url="redis://localhost:6379/0")
        release_factory = Event()
        initialized = Event()
        fake_application = MagicMock()
        fake_application.initialize = AsyncMock(side_effect=lambda: initialized.set())
        fake_application.start = AsyncMock()
        fake_application.stop = AsyncMock()
        fake_application.shutdown = AsyncMock()
        fake_application.process_update = AsyncMock()
        fake_application.bot = MagicMock()
        fake_application.bot.set_webhook = AsyncMock()
        fake_application.bot.delete_webhook = AsyncMock()

        def application_factory():
            release_factory.wait(timeout=2)
            return fake_application

        app = create_webhook_app(settings=settings, application_factory=application_factory)
        with TestClient(app) as client:
            response = client.post(settings.webhook_path, json={})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.text, "Webhook runtime is starting")

            release_factory.set()
            self.assertTrue(initialized.wait(timeout=2))

        fake_application.initialize.assert_awaited_once()
        fake_application.start.assert_awaited_once()
        fake_application.stop.assert_awaited_once()
        fake_application.shutdown.assert_awaited_once()
