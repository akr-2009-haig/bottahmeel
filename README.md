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

## Supported platforms

The platform system is centralized in `bot/utils/platforms.py`, and each platform entry automatically participates in:
- user URL detection
- admin enable/disable controls
- per-platform disabled messages
- worker download processing
- admin platform statistics

Current platform entries:
- TikTok
- YouTube
- Instagram
- Twitter / X
- Facebook
- Pinterest
- Likee
- Snapchat
- Reddit
- Google Drive
- LinkedIn
- Vimeo
- Dailymotion

### Platform limitations

- **Reddit**: public Reddit posts and direct `v.redd.it` media are the primary supported cases. Private, quarantined, deleted, or age-restricted posts can fail.
- **Google Drive**: safest support is limited to **publicly shared files** such as `drive.google.com/file/d/...`, `open?id=...`, or `uc?id=...`. Google Docs/Sheets/Slides pages, login-protected files, and non-public shares are not supported.
- **LinkedIn**: support is limited to public LinkedIn post/feed URLs that `yt-dlp` can access anonymously. Login-gated, private, or region-restricted media can fail, so this platform should remain admin-controlled in production.

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
# fill TELEGRAM_BOT_TOKEN, BOT_OWNER_ID, and DATABASE_URL
python run_bot.py
```

### Worker mode
```bash
# use the same .env as the intake process
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

## Migration checklist from the old architecture

Use this checklist when moving from the old inline-processing architecture to the queued worker architecture:

- [ ] Back up the PostgreSQL database before deployment.
- [ ] Pull the new code and reinstall dependencies from `requirements.txt`.
- [ ] Ensure the runtime user can create/alter tables and indexes on first startup.
- [ ] Start one intake instance so `init_db()` can create the `background_jobs` table and indexes.
- [ ] Start at least one separate worker process using the same environment and database.
- [ ] Verify `BOT_TEMP_DIR` is writable on every intake/worker host.
- [ ] If switching to webhook mode, prepare the reverse proxy and public `WEBHOOK_URL` before changing `BOT_MODE`.
- [ ] Review admin platform settings after rollout; Reddit, Google Drive, and LinkedIn are available in the platform list and can be enabled or disabled per platform.
- [ ] Review built-in start/help/platform-disabled messages if you rely on default copy.
- [ ] Send one real download and one small admin broadcast to confirm queue processing before full traffic cutover.

## Production runbook

### Shared preparation

1. Provision PostgreSQL and create the application database.
2. Copy `.env.example` to `.env`.
3. Set at minimum:
   - `TELEGRAM_BOT_TOKEN`
   - `BOT_OWNER_ID`
   - `DATABASE_URL`
   - `BOT_TEMP_DIR`
4. Optionally tune:
   - `BOT_MODE`
   - `WEBHOOK_URL`
   - `WEBHOOK_PATH`
   - `WORKER_POLL_INTERVAL`
   - `WORKER_BATCH_SIZE`
   - `WORKER_NAME`
   - `HEALTHCHECK_PORT`
   - `LOG_LEVEL`
5. Install required system packages and Python dependencies:
   ```bash
   apt-get update
   apt-get install -y ffmpeg gcc libpq-dev
   pip install -r requirements.txt
   ```

### Run polling mode

Best for local development or simple single-instance deployments:

```bash
cd /path/to/Karar-bots-downloader
cp .env.example .env
$EDITOR .env
BOT_MODE=polling python run_bot.py
```

Required companion services/processes:
- PostgreSQL
- at least one worker process: `python run_bot.py worker`

Verification:
- `curl http://127.0.0.1:${HEALTHCHECK_PORT:-8081}/healthz`
- send a supported platform URL to the bot
- confirm the worker completes the queued job

### Run webhook mode

Best for production behind a reverse proxy or ingress:

```bash
cd /path/to/Karar-bots-downloader
cp .env.example .env
$EDITOR .env
BOT_MODE=webhook \
WEBHOOK_URL=https://your-bot.example.com \
WEBHOOK_PATH=/telegram/webhook \
PORT=8080 \
python run_bot.py
```

Required companion services/processes:
- PostgreSQL
- at least one worker process: `python run_bot.py worker`
- reverse proxy / load balancer terminating TLS and forwarding `WEBHOOK_PATH`

Verification:
- `curl http://127.0.0.1:${HEALTHCHECK_PORT:-8081}/readyz`
- verify the reverse proxy forwards the webhook path to the intake process
- send a real Telegram update and confirm it becomes a queued background job

### Run worker mode

Workers process queued downloads and admin broadcasts:

```bash
cd /path/to/Karar-bots-downloader
cp .env.example .env
$EDITOR .env
BOT_MODE=worker \
WORKER_NAME=download-worker-1 \
python run_bot.py
```

Scale-out example:

```bash
BOT_MODE=worker WORKER_NAME=download-worker-1 python run_bot.py
BOT_MODE=worker WORKER_NAME=download-worker-2 python run_bot.py
BOT_MODE=worker WORKER_NAME=download-worker-3 python run_bot.py
```

Verification:
- enqueue a download request and confirm a worker claims it
- queue an admin broadcast and confirm `broadcast_batch` jobs are processed in batches
- watch worker logs for retry/failure events

## Required production services for one high-traffic bot

For one high-traffic bot, the minimum practical production setup is:

1. **One intake service**
   - polling for simple environments, webhook for scalable production
   - should stay lightweight and only validate/enqueue work
2. **Multiple worker services**
   - at least **2 workers** for resilience during restarts and traffic spikes
   - scale worker count based on queue depth and average download latency
3. **One PostgreSQL service**
   - stores users, settings, downloads, broadcasts, and queued jobs
4. **One reverse proxy / ingress** for webhook deployments
   - terminates TLS and forwards webhook traffic to the intake service
5. **Monitoring/log collection**
   - probes `/healthz` and `/readyz`
   - collects intake and worker logs

A practical starting topology for one high-traffic bot is:
- **1 webhook intake instance**
- **2-4 worker instances**
- **1 PostgreSQL instance**
- **1 reverse proxy / ingress**

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
