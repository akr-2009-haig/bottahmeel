from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response
from telegram import Update
from telegram.ext import Application

from bot.config import AppSettings

logger = logging.getLogger(__name__)


def _build_webhook_registration_url(settings: AppSettings) -> str:
    if settings.webhook_full_url:
        return settings.webhook_full_url.rstrip("/")

    base_url = settings.webhook_url.rstrip("/")
    webhook_path = settings.webhook_path if settings.webhook_path.startswith("/") else f"/{settings.webhook_path}"
    if base_url.endswith(webhook_path):
        return base_url
    return f"{base_url}{webhook_path}"


def create_webhook_app(*, application: Application, settings: AppSettings) -> FastAPI:
    """Create a FastAPI app that handles Telegram webhook updates explicitly."""

    webhook_url = _build_webhook_registration_url(settings)
    alternate_path = settings.webhook_path[:-1] if settings.webhook_path.endswith("/") else f"{settings.webhook_path}/"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("Initializing Telegram application for webhook mode")
        await application.initialize()
        await application.start()

        embedded_worker_stop_event: asyncio.Event | None = None
        embedded_worker_task: asyncio.Task | None = None
        if settings.queue_backend == "database":
            embedded_worker_stop_event = asyncio.Event()
            from bot.workers.runner import run_database_worker_loop

            embedded_worker_task = asyncio.create_task(
                run_database_worker_loop(
                    stop_event=embedded_worker_stop_event,
                    worker_name=f"{settings.worker_name}-webhook",
                )
            )
            logger.info("Started embedded database worker loop for webhook runtime")

        if settings.disable_auto_webhook_set:
            logger.info("Skipping automatic webhook registration (DISABLE_AUTO_WEBHOOK_SET=true)")
        else:
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
            if embedded_worker_stop_event is not None:
                embedded_worker_stop_event.set()
            if embedded_worker_task is not None:
                try:
                    await asyncio.wait_for(embedded_worker_task, timeout=10)
                except asyncio.TimeoutError:
                    embedded_worker_task.cancel()
            if not settings.disable_auto_webhook_set:
                await application.bot.delete_webhook(drop_pending_updates=False)
            await application.stop()
            await application.shutdown()

    app = FastAPI(lifespan=lifespan)

    @app.post(settings.webhook_path)
    @app.post(alternate_path)
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
