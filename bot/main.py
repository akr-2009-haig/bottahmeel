import logging
import os

from bot.app.bootstrap import bootstrap_application
from bot.app.logging import configure_logging
from bot.config import RuntimeMode, load_settings
from bot.workers import run_worker

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
        # 🔥 أهم تعديل (Render PORT)
        port = int(os.getenv("PORT", settings.port))

        webhook_url = f"{settings.webhook_url.rstrip('/')}{settings.webhook_path}"

        logger.info(
            "Starting webhook server on %s:%s path=%s",
            settings.listen_host,
            port,
            settings.webhook_path,
        )

        app.run_webhook(
            listen=settings.listen_host,
            port=port,  # ✅ تم إصلاح المشكلة هنا
            url_path=settings.webhook_path.lstrip('/'),
            webhook_url=webhook_url,
            secret_token=settings.webhook_secret_token or None,
            drop_pending_updates=True,
            allowed_updates=None,
        )
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
