from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable

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


def create_webhook_app(
    *,
    settings: AppSettings,
    application: Application | None = None,
    application_factory: Callable[[], Application] | None = None,
) -> FastAPI:
    """Create a FastAPI app that handles Telegram webhook updates explicitly."""

    if application is None and application_factory is None:
        raise ValueError("application or application_factory must be provided")

    webhook_url = _build_webhook_registration_url(settings)
    alternate_path = settings.webhook_path[:-1] if settings.webhook_path.endswith("/") else f"{settings.webhook_path}/"
    telegram_application = application
    initialization_error: Exception | None = None
    initialization_complete = asyncio.Event()
    application_initialized = False
    application_started = False

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal telegram_application, initialization_error, application_initialized, application_started
        embedded_worker_stop_event: asyncio.Event | None = None
        embedded_worker_task: asyncio.Task | None = None

        async def _initialize_runtime() -> None:
            nonlocal telegram_application, embedded_worker_stop_event, embedded_worker_task
            nonlocal initialization_error, application_initialized, application_started
            try:
                if telegram_application is None:
                    logger.info("Bootstrapping Telegram application for webhook mode")
                    telegram_application = await asyncio.to_thread(application_factory)

                logger.info("Initializing Telegram application for webhook mode")
                await telegram_application.initialize()
                application_initialized = True
                await telegram_application.start()
                application_started = True

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
                    await telegram_application.bot.set_webhook(
                        url=webhook_url,
                        secret_token=settings.webhook_secret_token or None,
                        drop_pending_updates=True,
                        allowed_updates=Update.ALL_TYPES,
                    )
            except Exception as exc:
                initialization_error = exc
                logger.exception("Failed to initialize Telegram webhook runtime")
            finally:
                initialization_complete.set()

        runtime_task = asyncio.create_task(_initialize_runtime())

        try:
            yield
        finally:
            if not initialization_complete.is_set():
                runtime_task.cancel()
                try:
                    await runtime_task
                except asyncio.CancelledError:
                    pass
            else:
                await runtime_task

            if embedded_worker_stop_event is not None:
                embedded_worker_stop_event.set()
            if embedded_worker_task is not None:
                try:
                    await asyncio.wait_for(embedded_worker_task, timeout=10)
                except asyncio.TimeoutError:
                    embedded_worker_task.cancel()

            if telegram_application is not None:
                logger.info("Stopping Telegram webhook runtime")
                if application_started and not settings.disable_auto_webhook_set:
                    await telegram_application.bot.delete_webhook(drop_pending_updates=False)
                if application_started:
                    await telegram_application.stop()
                if application_initialized:
                    await telegram_application.shutdown()

    app = FastAPI(lifespan=lifespan)

    @app.post(settings.webhook_path)
    @app.post(alternate_path)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> Response:
        if not initialization_complete.is_set() or telegram_application is None:
            return Response(status_code=503, content="Webhook runtime is starting")

        if initialization_error is not None:
            raise HTTPException(status_code=503, detail="Webhook runtime failed to initialize")

        if settings.webhook_secret_token and x_telegram_bot_api_secret_token != settings.webhook_secret_token:
            logger.warning("Rejected webhook request due to invalid secret token")
            raise HTTPException(status_code=403, detail="Invalid webhook secret token")

        payload = await request.json()
        update = Update.de_json(payload, telegram_application.bot)
        await telegram_application.process_update(update)
        return Response(status_code=200)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        if initialization_error is not None:
            return {"status": "error"}
        if not initialization_complete.is_set():
            return {"status": "starting"}
        return {"status": "ok"}

    return app
