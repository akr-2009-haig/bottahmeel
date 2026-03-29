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
- `bot/queue/` provides a Redis-backed Celery queue while keeping PostgreSQL job records for tracking and retries.
- `bot/services/` contains download-related business logic and queue orchestration.
- `bot/workers/` runs heavy jobs outside the Telegram update intake path.
- `bot/temp/` provides safer, explicit temp directory handling plus stale cleanup.
- `bot/monitoring/` exposes `/healthz`, `/readyz`, and `/queuez` for operations.
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
3. The bot stores a background job record in PostgreSQL, pushes the job to Redis/Celery, and immediately responds to the user.
4. One Celery worker process claims the job from Redis and atomically marks the job record as processing.
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
# fill TELEGRAM_BOT_TOKEN, BOT_OWNER_ID, DATABASE_URL, and REDIS_URL
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
- `.dockerignore`
- `.env.example`

Typical deployment layout:
- one `bot` instance for Telegram intake
- one or more `worker` instances for heavy media work
- one PostgreSQL instance
- one Redis instance

## Large-launch deployment blueprint (up to ~2 million users)

For a large public launch, keep the intake path light and scale the worker side horizontally. A practical first production shape is:

- **1-2 webhook intake instances**
  - 2 vCPU, 2-4 GB RAM each
  - only accepts Telegram updates, validates requests, and enqueues jobs
- **4-8 worker instances**
  - 4 vCPU, 4-8 GB RAM each
  - sized based on average media size, `yt-dlp` latency, and queue depth
- **1 managed PostgreSQL instance**
  - start around 4 vCPU / 8-16 GB RAM / fast SSD
  - use automated backups and connection pooling if available
- **1 managed Redis instance**
  - start around 2 vCPU / 4-8 GB RAM
  - keep Redis dedicated to queue traffic
- **1 reverse proxy / load balancer**
  - Nginx, Caddy, HAProxy, or a managed ingress
  - terminates TLS and forwards only the webhook path to the intake service

Important note: no single static server size can guarantee support for 2 million users by itself. This codebase is designed for queue-based horizontal scaling, so the real capacity comes from:

- webhook mode instead of polling
- enough worker replicas
- healthy Redis/PostgreSQL infrastructure
- monitoring `/readyz` and `/queuez`
- fast SSD storage and good outbound bandwidth

### Step-by-step Ubuntu server deployment

This is the simplest serious production path if you want to deploy from GitHub onto your own Linux server:

1. Provision an Ubuntu 24.04 or 22.04 server with Docker and Docker Compose plugin support.
2. Point your public DNS record to the server IP.
3. Install Docker:
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl gnupg
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```
4. Clone the repository and prepare env vars:
   ```bash
   git clone https://github.com/<your-user-or-org>/Karar-bots-downloader.git
   cd Karar-bots-downloader
   cp .env.example .env
   ```
5. Edit `.env` and set at minimum:
   - `TELEGRAM_BOT_TOKEN`
   - `BOT_OWNER_ID`
   - `DATABASE_URL`
   - `REDIS_URL`
   - `BOT_MODE=webhook`
   - `WEBHOOK_URL=https://your-domain.example.com`
   - `WEBHOOK_SECRET_TOKEN=<strong-random-secret>`
   - `QUEUE_BACKEND=redis`
6. Start the stack:
   ```bash
   docker compose up -d --build
   ```
7. Scale workers when needed:
   ```bash
   docker compose up -d --scale worker=4
   ```
8. Verify the deployment:
   ```bash
   curl http://127.0.0.1:8081/healthz
   curl http://127.0.0.1:8081/readyz
   curl http://127.0.0.1:8081/queuez
   ```
9. Put Nginx/Caddy or a cloud load balancer in front of the webhook port and enable TLS before switching public traffic.

### GitHub-integrated hosting options

If you want your deployment workflow to start from GitHub pushes, these platforms integrate well with this repository shape:

- **GitHub Actions + Ubuntu VPS** (Hetzner, DigitalOcean, Contabo, Akamai/Linode, OVH)
  - best balance of control, cost, and performance
  - use GitHub Actions for build/deploy and keep PostgreSQL/Redis managed or separate
- **Railway**
  - easy GitHub-connected deploys
  - best for moderate traffic or early production, not the first choice for the largest sustained launch
- **Render**
  - simple GitHub integration and managed TLS
  - easier than a VPS, but less control for very large scale
- **Fly.io**
  - GitHub-friendly and good for globally distributed webhook intake
  - works best when you are comfortable with Docker-based deploys
- **Google Cloud Run / AWS App Runner**
  - strong GitHub automation paths and elastic scaling
  - pair with managed PostgreSQL/Redis equivalents for serious production

For the biggest launch, the safest default is usually **GitHub + VPS/cloud VM + managed PostgreSQL + managed Redis + webhook mode + multiple workers**.

## Migration checklist from the old architecture

Use this checklist when moving from the old inline-processing architecture to the queued worker architecture:

- [ ] Back up the PostgreSQL database before deployment.
- [ ] Pull the new code and reinstall dependencies from `requirements.txt`.
- [ ] Ensure the runtime user can create/alter tables and indexes on first startup.
- [ ] Provision Redis and set `REDIS_URL` before switching the queue backend to production traffic.
- [ ] Start one intake instance so `init_db()` can create the `background_jobs` table and indexes.
- [ ] Start at least one separate worker process using the same environment and database.
- [ ] Prefer `BOT_MODE=webhook` and set `WEBHOOK_SECRET_TOKEN` before public cutover.
- [ ] Verify `BOT_TEMP_DIR` is writable on every intake/worker host.
- [ ] If switching to webhook mode, prepare the reverse proxy and public `WEBHOOK_URL` before changing `BOT_MODE`.
- [ ] Review admin platform settings after rollout; Reddit, Google Drive, and LinkedIn are available in the platform list and can be enabled or disabled per platform.
- [ ] Review built-in start/help/platform-disabled messages if you rely on default copy.
- [ ] Send one real download and one small admin broadcast to confirm queue processing before full traffic cutover.

## Production runbook

### Shared preparation

1. Provision PostgreSQL and Redis.
2. Copy `.env.example` to `.env`.
3. Set at minimum:
   - `TELEGRAM_BOT_TOKEN`
   - `BOT_OWNER_ID`
   - `DATABASE_URL`
   - `REDIS_URL`
   - `BOT_TEMP_DIR`
4. Optionally tune:
   - `BOT_MODE`
   - `QUEUE_BACKEND`
   - `QUEUE_NAME`
   - `WEBHOOK_URL`
   - `WEBHOOK_PATH`
   - `WEBHOOK_SECRET_TOKEN`
   - `WORKER_BATCH_SIZE`
   - `WORKER_CONCURRENCY`
   - `WORKER_NAME`
   - `WORKER_HEARTBEAT_TTL_SECONDS`
   - `JOB_LOCK_TIMEOUT_SECONDS`
   - `HEALTHCHECK_PORT`
   - `RATE_LIMIT_REQUESTS_PER_WINDOW`
   - `RATE_LIMIT_WINDOW_SECONDS`
   - `RATE_LIMIT_BLOCK_SECONDS`
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
- Redis
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
QUEUE_BACKEND=redis \
REDIS_URL=redis://redis:6379/0 \
WEBHOOK_URL=https://your-bot.example.com \
WEBHOOK_PATH=/telegram/webhook \
WEBHOOK_SECRET_TOKEN=replace-me \
PORT=8080 \
python run_bot.py
```

If `BOT_MODE` is left unset on Render, the app now auto-detects webhook mode when Render injects `PORT` and you already configured `WEBHOOK_URL` or `WEBHOOK_FULL_URL`.

Required companion services/processes:
- PostgreSQL
- Redis
- at least one worker process: `python run_bot.py worker`
- reverse proxy / load balancer terminating TLS and forwarding `WEBHOOK_PATH`

Verification:
- `curl http://127.0.0.1:${HEALTHCHECK_PORT:-8081}/readyz`
- `curl http://127.0.0.1:${HEALTHCHECK_PORT:-8081}/queuez`
- verify the reverse proxy forwards the webhook path to the intake process
- send a real Telegram update and confirm it becomes a queued background job

### Run worker mode

Workers process queued downloads, admin broadcasts, and due scheduled posts after the bot intake process dispatches them:

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
- enqueue a download request and confirm a worker claims it from Redis/Celery
- queue an admin broadcast and confirm `broadcast_batch` jobs are processed in batches
- keep at least one polling/webhook app process running so it can scan for due `ScheduledPost` rows and enqueue `scheduled_post` jobs every 30 seconds
- create a scheduled post from the admin panel and confirm a `scheduled_post` background job appears when its due time arrives
- watch worker logs for retry/failure events
- confirm `/queuez` exposes `ready_count`, `delayed_retry_count`, `stale_processing_count`, and per-job-type counts

### PostgreSQL production hardening

For one high-traffic bot, treat PostgreSQL as the system of record for users, downloads, settings, broadcast logs, and background job state:

- Keep PostgreSQL on SSD-backed storage and enable regular backups before every deployment.
- Use `QUEUE_BACKEND=redis` in production so PostgreSQL stores job metadata while Redis/Celery handles the hot queue traffic.
- Keep the legacy database-backed queue only as a fallback path; it now automatically reclaims stale `PROCESSING` rows after `JOB_LOCK_TIMEOUT_SECONDS`.
- The app verifies and creates queue-related indexes at startup, including:
  - job claim path: `status + available_at + priority + created_at`
  - backlog/age path: `status + created_at`
  - stuck processing path: `status + locked_at`
  - broadcast user scan path: `users(status, id)`
- Tune `JOB_LOCK_TIMEOUT_SECONDS` to be longer than your slowest expected download job. A low value can cause duplicate recovery of long-running jobs in the legacy DB queue path.
- Watch for growing `stale_processing_count`, `oldest_pending_age_seconds`, or `oldest_processing_lock_age_seconds` in `/queuez`; these are early signs of worker crashes or a queue bottleneck.

### Backup and restore

Use PostgreSQL custom-format dumps for practical operational recovery:

```bash
cd /path/to/Karar-bots-downloader
DATABASE_URL=postgresql://user:password@host:5432/dbname \
BACKUP_DIR=./backups/postgres \
RETENTION_DAYS=7 \
./scripts/postgres_backup.sh
```

Recommended production approach:

- Run the backup script at least daily; for a busy bot, every 6-12 hours is safer.
- Keep at least 7 daily backups locally and copy them to separate durable storage managed by your hosting environment.
- Take an extra manual backup before schema-affecting deployments or major admin changes.
- Verify that `pg_dump` and `pg_restore` are installed on the operator host.
- Periodically test a restore into a separate PostgreSQL database; an untested backup is not a recovery plan.

Restore example:

```bash
cd /path/to/Karar-bots-downloader
./scripts/postgres_restore.sh ./backups/postgres/karar_bot_20260324T120000Z.dump \
  postgresql://user:password@host:5432/karar_bot_restore
```

Practical restore guidance:

1. Stop intake and worker processes before restoring over a live production database.
2. Prefer restoring into a fresh database first, then point the bot to the restored database after verification.
3. Run `python run_bot.py worker` only after the restored database passes a quick smoke test (`/readyz`, a real download, and a queue check).
4. Keep the pre-restore database snapshot until the bot is fully stable again.

### Incident and recovery runbook

#### Intake service restart flow

1. Check `/healthz` for process liveness and `/readyz` for database/broker readiness.
2. If only the intake service is down, restart the intake process first; workers can continue draining queued work.
3. In webhook mode, confirm the reverse proxy still forwards `WEBHOOK_PATH` and that `WEBHOOK_SECRET_TOKEN` matches the running config.
4. After restart, send one real Telegram update and confirm a new background job is created.

#### Worker failure or retry spike

1. Check `/queuez` and worker logs for `stale_processing_count`, `delayed_retry_count`, and retry/failure log lines.
2. If Redis/Celery workers are failing, inspect the error message on the affected `background_jobs` rows and restart or replace the failing worker instance.
3. If using the legacy database-backed worker, confirm `JOB_LOCK_TIMEOUT_SECONDS` is sane and allow the automatic stale-job recovery loop to requeue expired `PROCESSING` rows.
4. If failures are permanent, leave the jobs in `FAILED` until the underlying cause is fixed; avoid blind manual retries during an active outage.

#### Queue backlog handling

1. A rising `ready_count` with healthy broker/database usually means more workers are needed or downloads are slowing down.
2. Scale worker replicas before restarting the intake service; the intake process should stay lightweight.
3. A rising `delayed_retry_count` usually points to downstream failures (Telegram send errors, platform download errors, or network issues), not raw queue capacity.
4. If backlog grows rapidly, temporarily reduce admin broadcast activity until normal download latency returns.

#### Database recovery scenario

1. Freeze writes by stopping the intake and worker processes.
2. Take a final snapshot/backup of the damaged database state if possible.
3. Restore the latest healthy dump into a new database using `./scripts/postgres_restore.sh`.
4. Update `DATABASE_URL`, start one intake instance, and verify `init_db()` completes cleanly.
5. Start one worker, run one real download end-to-end, then scale workers back out.
6. Review `background_jobs` for unexpected `FAILED` or stale recovered jobs before declaring the incident closed.

## Required production services for one high-traffic bot

For one high-traffic bot, the minimum practical production setup is:

1. **One intake service**
   - polling for local/dev, webhook for scalable production
   - should stay lightweight and only validate/enqueue work
2. **Multiple worker services**
    - at least **2 workers** for resilience during restarts and traffic spikes
    - scale worker count based on queue depth and average download latency
3. **One PostgreSQL service**
   - stores users, settings, downloads, broadcasts, and job tracking metadata
 4. **One Redis service**
   - stores the production queue used by Celery workers
 5. **One reverse proxy / ingress** for webhook deployments
   - terminates TLS and forwards webhook traffic to the intake service
 6. **Monitoring/log collection**
    - probes `/healthz`, `/readyz`, and `/queuez`
    - collects intake and worker logs

A practical starting topology for one high-traffic bot is:
- **1 webhook intake instance**
- **2-4 worker instances**
- **1 PostgreSQL instance**
- **1 Redis instance**
- **1 reverse proxy / ingress**

## Health endpoints
- `GET /healthz` → process liveness plus configured queue backend
- `GET /readyz` → database + broker readiness plus queue and worker summary
- `GET /queuez` → queue depth, broker state, and worker heartbeat snapshot

The health server listens on `HEALTHCHECK_PORT`.

## Scaling guidance
- Increase Celery worker replicas to process more download jobs.
- Keep bot intake instances lightweight; the heavy work now lives in workers.
- Use webhook mode behind a reverse proxy/load balancer for production.
- Redis-backed queueing is the recommended production path; keep database queueing only as a local/dev fallback if Redis is unavailable.
- Watch `/queuez`, worker heartbeats, and failed job counts when deciding whether to add more worker replicas.

## Migration notes
- Existing database tables are preserved.
- A new `background_jobs` table is added for queue processing.
- Existing `downloads` metadata stays in PostgreSQL; media blobs remain temporary on disk only.
- Local development can continue with polling mode.

## Recommended next steps
- Add integration tests around worker job processing with a disposable PostgreSQL instance.
- Add a small Prometheus/OpenTelemetry exporter for queue depth, worker heartbeats, and retry/failure counts.
- Add a scheduled backup runner (cron/systemd/Kubernetes CronJob) that wraps `scripts/postgres_backup.sh` and ships dumps off-host.
- Add worker autoscaling and deployment automation around Redis/Celery queue depth.

## Render one-click blueprint (webhook + worker)

This repository now includes a ready `render.yaml` blueprint with:
- `karar-bot-webhook` web service (`python run_bot.py`)
- `karar-bot-worker` background worker (`python run_bot.py worker`)
- managed Redis (`karar-bot-redis`)
- managed PostgreSQL (`karar-bot-db`)

### Deploy on Render
1. Push this repository to GitHub.
2. In Render, choose **New +** → **Blueprint** and select the repo.
3. Render will create all services from `render.yaml`.
4. Set only these required secrets on **both** services where prompted:
   - `TELEGRAM_BOT_TOKEN`
   - `BOT_OWNER_ID`
   - `WEBHOOK_SECRET_TOKEN`
5. Set `WEBHOOK_URL` on the web service to your Render HTTPS URL (for example `https://karar-bot-webhook.onrender.com`).
6. Deploy.

Webhook endpoint used by Telegram will be:
- `https://<your-render-domain>/telegram/webhook`

The app is already configured to bind to `0.0.0.0` and use the `PORT` environment variable in webhook mode.
