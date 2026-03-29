import os
import unittest
from unittest.mock import MagicMock, patch

from bot.config.settings import AppSettings, RuntimeMode
from bot.main import main


class MainEntrypointTests(unittest.TestCase):
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

    def test_webhook_uses_runtime_port_from_environment(self):
        settings = self._settings(port=8080)
        with (
            patch.dict(os.environ, {"PORT": "10000"}, clear=False),
            patch("bot.main.configure_logging"),
            patch("bot.main.load_settings", return_value=settings),
            patch("bot.main.bootstrap_application", return_value=MagicMock()),
            patch("bot.main.create_webhook_app", return_value=MagicMock()),
            patch("bot.main.uvicorn.run") as uvicorn_run,
        ):
            main()

        uvicorn_run.assert_called_once()
        self.assertEqual(uvicorn_run.call_args.kwargs["port"], 10000)

    def test_webhook_defers_bootstrap_until_web_server_startup(self):
        settings = self._settings(port=8080)
        with (
            patch("bot.main.configure_logging"),
            patch("bot.main.load_settings", return_value=settings),
            patch("bot.main.bootstrap_application") as bootstrap_application,
            patch("bot.main.create_webhook_app", return_value=MagicMock()) as create_webhook_app,
            patch("bot.main.uvicorn.run"),
        ):
            main()

        bootstrap_application.assert_not_called()
        self.assertIs(
            create_webhook_app.call_args.kwargs["application_factory"],
            bootstrap_application,
        )
