import logging

from bot.app.bootstrap import bootstrap_application
from bot.app.logging import configure_logging
from bot.config import RuntimeMode, load_settings
from bot.workers import run_worker

logger = logging.getLogger(__name__)


def main():
    configure_logging()
    settings = load_settings()
    settings.validate_for_mode()

    if settings.mode is RuntimeMode.WORKER:
        run_worker()
        return

    logger.info("Bootstrapping bot in %s mode", settings.mode.value)
    app = bootstrap_application()

    if settings.mode is RuntimeMode.WEBHOOK:
        webhook_url = f"{settings.webhook_url.rstrip('/')}{settings.webhook_path}"
        logger.info("Starting webhook server on %s:%s path=%s", settings.listen_host, settings.port, settings.webhook_path)
        app.run_webhook(
            listen=settings.listen_host,
            port=settings.port,
            url_path=settings.webhook_path.lstrip('/'),
            webhook_url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=None,
        )
        return

    logger.info("Starting polling bot")
    from telegram import Update
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
