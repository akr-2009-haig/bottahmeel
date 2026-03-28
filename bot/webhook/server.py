from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response
from telegram import Update
from telegram.ext import Application

from bot.config import AppSettings

logger = logging.getLogger(__name__)


def create_webhook_app(*, application: Application, settings: AppSettings) -> FastAPI:
    """Create a FastAPI app that handles Telegram webhook updates explicitly."""

    webhook_url = f"{settings.webhook_url.rstrip('/')}{settings.webhook_path}"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("Initializing Telegram application for webhook mode")
        await application.initialize()
        await application.start()

        logger.info("Registering Telegram webhook url=%s", webhook_url)
        await application.bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook_secret_token or None,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )

        try:
            yield
        finally:
            logger.info("Stopping Telegram webhook runtime")
            await application.bot.delete_webhook(drop_pending_updates=False)
            await application.stop()
            await application.shutdown()

    app = FastAPI(lifespan=lifespan)

    @app.post(settings.webhook_path)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> Response:
        if settings.webhook_secret_token and x_telegram_bot_api_secret_token != settings.webhook_secret_token:
            logger.warning("Rejected webhook request due to invalid secret token")
            raise HTTPException(status_code=403, detail="Invalid webhook secret token")

        payload = await request.json()
        update = Update.de_json(payload, application.bot)
        await application.process_update(update)
        return Response(status_code=200)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
