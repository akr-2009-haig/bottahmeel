# Karar Telegram Downloader Bot (VPS Edition)

هذا المستودع مهيأ الآن لتشغيل **بوت واحد** على **VPS واحد** عبر:
- Docker Compose
- Nginx reverse proxy (على نفس السيرفر)
- Redis queue
- Worker منفصل للتحميل الثقيل
- Webhook mode (بدون polling)

## Architecture

- `bot`:
  يستقبل Telegram webhook فقط ويضع jobs في queue.
- `worker`:
  ينفذ عمليات `yt-dlp/ffmpeg` خارج مسار webhook.
- `redis`:
  broker للطابور.
- `db`:
  PostgreSQL لحفظ المستخدمين/jobs/الإعدادات.
- `nginx` (Host service):
  TLS termination + reverse proxy إلى `127.0.0.1:8080`.

## Quick start (Ubuntu 24.04)

```bash
git clone <repo-url>
cd Karar-bots-downloader
cp .env.example .env
# عدّل .env

docker compose up -d --build
```

تحقق:

```bash
curl http://127.0.0.1:8081/healthz
curl http://127.0.0.1:8081/readyz
curl http://127.0.0.1:8081/queuez
```

## Required env vars

- `TELEGRAM_BOT_TOKEN`
- `BOT_OWNER_ID`
- `WEBHOOK_URL` (https)
- `WEBHOOK_SECRET_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`
- `BOT_MODE=webhook`
- `QUEUE_BACKEND=redis`

## Optional: authenticated downloads via cookies (YouTube/TikTok/Instagram)

عند ظهور أخطاء `private/login required` يمكن تمرير كوكيز للـ `yt-dlp`:

- `YTDLP_COOKIES_FILE=/path/to/cookies.txt` (صيغة Netscape)
- أو `YTDLP_COOKIES_FROM_BROWSER=firefox:default-release` (أو `chrome`, `edge`, ... حسب البيئة)

> يفضّل استخدام متغير واحد فقط. إذا لم يكن ملف الكوكيز موجوداً سيستمر البوت بالعمل مع تحذير في السجلات.

## Webhook

- المسار الافتراضي: `/telegram/webhook`
- يجب أن يمر عبر HTTPS domain صالح.
- التطبيق يسجل webhook تلقائياً عند الإقلاع ما لم يكن `DISABLE_AUTO_WEBHOOK_SET=true`.

## Conservative defaults for 2 vCPU / 8 GB

- `WORKER_CONCURRENCY=1`
- `WORKER_BATCH_SIZE=8`
- worker واحد فقط
- cleanup دوري للملفات المؤقتة عبر job + startup sweep

## Useful commands

```bash
docker compose ps
docker compose logs -f bot
docker compose logs -f worker
docker compose restart bot worker
```

## Legacy notes

- تم إيقاف إعدادات Render (`render.yaml`) و `Procfile` لأن النشر المستهدف أصبح VPS self-hosted فقط.
