from __future__ import annotations

import asyncio
import logging
import threading
from aiohttp import web
from sqlalchemy import text

from bot.config import load_settings
from bot.database import db as database_db

logger = logging.getLogger(__name__)
_server_started = False
_lock = threading.Lock()


async def _healthz(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _readyz(_request: web.Request) -> web.Response:
    if database_db.engine is None:
        return web.json_response({"status": "starting"}, status=503)
    try:
        with database_db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return web.json_response({"status": "ready"})
    except Exception as exc:
        return web.json_response({"status": "error", "detail": str(exc)}, status=503)


def start_health_server() -> None:
    global _server_started
    settings = load_settings()
    if not settings.enable_healthcheck:
        return
    with _lock:
        if _server_started:
            return
        thread = threading.Thread(target=_run_server, name="health-server", daemon=True)
        thread.start()
        _server_started = True


def _run_server() -> None:
    settings = load_settings()

    async def _runner() -> None:
        app = web.Application()
        app.router.add_get("/healthz", _healthz)
        app.router.add_get("/readyz", _readyz)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, settings.listen_host, settings.healthcheck_port)
        await site.start()
        logger.info("Health server listening on %s:%s", settings.listen_host, settings.healthcheck_port)
        while True:
            await asyncio.sleep(3600)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_runner())
