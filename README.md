# Karar-bots-downloader

## Current problems found in the original codebase

Before this refactor, the bot had a few production bottlenecks:
- Telegram intake was polling-only, so deployment was not optimized for horizontally scaled production traffic.
- Heavy `yt-dlp` work happened directly inside `bot/handlers/user_handler.py`, which blocked the update path.
- Broadcasts were executed inline from the admin handler, which could freeze the bot during large sends.
- Database sessions were opened ad hoc in handlers and admin routing.
- Temporary files were only deleted on the happy path, with no stale-file sweep after crashes.
- There were no health/readiness endpoints for orchestration platforms.

## Refactor summary

This refactor keeps the current bot features, but introduces a production-oriented architecture:
- `bot/app/` now owns application bootstrap and handler wiring.
- `bot/config/` centralizes runtime configuration and startup validation.
- `bot/queue/` provides a DB-backed background job queue.
- `bot/services/` contains download-related business logic and queue orchestration.
- `bot/workers/` runs heavy jobs outside the Telegram update intake path.
- `bot/temp/` provides safer, explicit temp directory handling plus stale cleanup.
- `bot/monitoring/` exposes `/healthz` and `/readyz` for operations.
- `bot/main.py` now supports polling, webhook-ready deployment, and dedicated worker mode.

## Update flow

### User download flow
1. Telegram update reaches the bot through polling or webhook mode.
2. The handler performs only lightweight validation (subscription check, URL detection, platform enablement).
3. The bot stores a background job in the database and immediately responds to the user.
4. A separate worker process claims the job.
5. The worker downloads media, sends it back to Telegram, records metadata, and cleans up temp files.

### Admin broadcast flow
1. Admin prepares the broadcast in the existing admin UI.
2. The admin callback stores a broadcast job instead of sending inline.
3. The worker processes the broadcast in batches to avoid blocking intake.

## Temp file lifecycle
- Downloads are created under a dedicated base directory (`BOT_TEMP_DIR`).
- Cleanup only happens inside that base directory, preventing accidental deletion elsewhere.
- Files are removed immediately after successful/failed handling.
- A startup sweep and periodic cleanup job remove stale temp directories left behind by crashes.

## Running locally

### Polling mode
```bash
cp .env.example .env
# fill TELEGRAM_BOT_TOKEN and DATABASE_URL
python run_bot.py
```

### Worker mode
```bash
python run_bot.py worker
```

### Webhook mode
```bash
BOT_MODE=webhook WEBHOOK_URL=https://example.com python run_bot.py
```

## Deployment

A basic production-like stack is included:
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

Typical deployment layout:
- one `bot` instance for Telegram intake
- one or more `worker` instances for heavy media work
- one PostgreSQL instance

## Health endpoints
- `GET /healthz` → process health
- `GET /readyz` → database readiness

The health server listens on `HEALTHCHECK_PORT`.

## Scaling guidance
- Increase worker replicas to process more download jobs.
- Keep bot intake instances lightweight; the heavy work now lives in workers.
- Move from polling to webhook mode behind a reverse proxy/load balancer for production.
- If job volume grows beyond what PostgreSQL queue polling should handle, the service boundaries introduced here make it straightforward to replace the queue layer with Redis/Celery later.

## Migration notes
- Existing database tables are preserved.
- A new `background_jobs` table is added for queue processing.
- Existing `downloads` metadata stays in PostgreSQL; media blobs remain temporary on disk only.
- Local development can continue with polling mode.

## Recommended next steps
- Add integration tests around worker job processing with a disposable PostgreSQL instance.
- Move broadcast progress reporting into the admin UI.
- Consider Redis/Celery once queue throughput materially outgrows DB-backed polling.
- Add Prometheus-compatible metrics and centralized logging.
