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

# أنشئ ملف كوكيز قبل تشغيل الحاوية (مطلوب)
cp cookies.txt.example cookies.txt
# الصق كوكيزات متصفحك الحقيقية داخل cookies.txt ثم احفظ الملف

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

## إعداد ملف الكوكيز (مطلوب لتحميل يوتيوب)

عند ظهور خطأ `Sign in to confirm you're not a bot` يجب توفير كوكيز حقيقية:

```bash
# 1. انسخ القالب
cp cookies.txt.example cookies.txt

# 2. احصل على كوكيزاتك من المتصفح
#    استخدم إضافة "Get cookies.txt LOCALLY" من متصفح Chrome/Firefox
#    بعد تسجيل الدخول إلى يوتيوب، ثم صدّر الملف بصيغة Netscape

# 3. ضع محتوى الملف المُصدَّر داخل cookies.txt
#    (استبدل محتوى الملف بالكامل بما أنتجه المتصفح)

# 4. تأكد أن COOKIES_FILE=./cookies.txt موجود في .env
grep COOKIES_FILE .env

# 5. أعد تشغيل الحاوية
docker compose restart bot worker
```

> **ملاحظة:** ملف `cookies.txt` مُدرج في `.gitignore` لحمايتك من نشر بيانات الجلسة عن طريق الخطأ.
> لا تشاركه مع أحد ولا ترفعه إلى أي مستودع عام.

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
