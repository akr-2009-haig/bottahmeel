import logging
from bot.app.bootstrap import bootstrap_application
from bot.app.logging import configure_logging
from bot.config import RuntimeMode, load_settings
from bot.webhook import create_webhook_app
from bot.workers import run_worker

import uvicorn

logger = logging.getLogger(__name__)


def main():
    configure_logging()
    settings = load_settings()
    settings.validate_for_mode()

    # 🔧 Worker mode
    if settings.mode is RuntimeMode.WORKER:
        run_worker()
        return

    logger.info("Bootstrapping bot in %s mode", settings.mode.value)

    if settings.mode is RuntimeMode.POLLING:
        logger.warning(
            "Polling mode is intended for local/dev usage. "
            "Use webhook mode with Redis-backed workers for production."
        )

    if settings.mode is RuntimeMode.WEBHOOK and not settings.webhook_secret_token:
        logger.warning(
            "WEBHOOK_SECRET_TOKEN is not set. Configure it in production "
            "to harden Telegram webhook intake."
        )

    app = bootstrap_application()

    # 🔥 Webhook mode
    if settings.mode is RuntimeMode.WEBHOOK:
        logger.info(
            "Starting FastAPI webhook server on %s:%s path=%s",
            settings.listen_host,
            settings.port,
            settings.webhook_path,
        )
        webhook_app = create_webhook_app(application=app, settings=settings)
        uvicorn.run(webhook_app, host=settings.listen_host, port=settings.port)
        return

    # 🔧 Polling fallback
    logger.info("Starting polling bot")
    from telegram import Update

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
