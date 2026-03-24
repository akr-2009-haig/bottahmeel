from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

from aiohttp import web
from sqlalchemy import text

from bot.config import load_settings
from bot.database import SessionLocal, WorkerHeartbeat
from bot.database import db as database_db
from bot.queue import get_queue_stats, ping_broker

logger = logging.getLogger(__name__)
_server_started = False
_lock = threading.Lock()


async def _healthz(_request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "queue_backend": load_settings().queue_backend,
    })


def _worker_snapshot() -> dict:
    settings = load_settings()
    db = SessionLocal()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.worker_heartbeat_ttl_seconds)
    try:
        workers = db.query(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_name).all()
        active_workers = [
            {
                "worker_name": worker.worker_name,
                "status": worker.status,
                "active_task_id": worker.active_task_id,
                "last_seen": worker.last_seen.isoformat() if worker.last_seen else None,
            }
            for worker in workers
            if worker.last_seen and worker.last_seen >= cutoff and worker.status != "stopped"
        ]
        return {
            "active_count": len(active_workers),
            "active": active_workers,
        }
    finally:
        db.close()


def _readiness_payload() -> tuple[dict, int]:
    if database_db.engine is None:
        return {"status": "starting"}, 503
    payload = {
        "status": "ready",
        "components": {
            "database": "ready",
            "broker": "ready" if ping_broker() else "error",
        },
        "queue": get_queue_stats(),
        "workers": _worker_snapshot(),
    }
    if payload["components"]["broker"] != "ready":
        payload["status"] = "error"
        return payload, 503
    return payload, 200


async def _readyz(_request: web.Request) -> web.Response:
    try:
        if database_db.engine is None:
            return web.json_response({"status": "starting"}, status=503)
        with database_db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        payload, status = _readiness_payload()
        return web.json_response(payload, status=status)
    except Exception as exc:
        return web.json_response({"status": "error", "detail": str(exc)}, status=503)


async def _queuez(_request: web.Request) -> web.Response:
    payload, status = _readiness_payload()
    return web.json_response(payload, status=status)


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
        app.router.add_get("/queuez", _queuez)
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
