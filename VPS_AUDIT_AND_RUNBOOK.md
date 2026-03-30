## القسم A — Executive Summary

- الوضع السابق كان يحتوي بقايا إعدادات Render بالإضافة إلى إعدادات تشغيل غير مناسبة لسيرفر صغير.
- المشروع **يمكن** تشغيله على VPS واحد، بشرط الالتزام بفصل `webhook receiver` عن `worker` واستخدام queue.
- بعد التعديلات أصبح المسار التشغيلي موجهاً لـ Ubuntu 24.04 + Docker Compose + Nginx + Redis + Worker منفصل.

## القسم B — Render-to-VPS Audit

المكتشفات:
- `render.yaml`: blueprint خاص Render services/database/redis.
- `Procfile`: process model خاص Heroku/Render.
- `.env.example`: كان يحتوي `example.onrender.com`.
- `bot/config/settings.py`: كان يستنتج mode بناءً على وجود `PORT` (سلوك managed-platform).

الإجراء:
- حذف `render.yaml` و `Procfile`.
- تحديث `.env.example` إلى domain عام VPS.
- إزالة ربط اختيار mode بوجود `PORT` فقط.

## القسم C — Target VPS Architecture

- Nginx على host يستقبل `443` ويعمل proxy إلى `127.0.0.1:8080`.
- حاوية `bot` تستقبل webhook فقط وتدفع jobs إلى Redis.
- حاوية `worker` تنفذ التحميل/التحويل والإرسال إلى Telegram.
- Redis broker + PostgreSQL persistence.
- تنظيف ملفات مؤقتة على startup ودورياً.

سبب الملاءمة لـ 2 vCPU / 8 GB:
- worker واحد + `WORKER_CONCURRENCY=1` لتقليل ضغط CPU/RAM.
- عدم expose لقواعد البيانات على الإنترنت.
- log rotation + memory caps على الخدمات.

## القسم D — File/Folder Refactor Plan

- تعديل: `docker-compose.yml` لضبط production single-VPS conservative.
- تعديل: `.env.example` لقيم VPS حقيقية.
- تعديل: `bot/config/settings.py` لإزالة fallback مرتبط بـ Render PORT.
- تعديل: `README.md` ليوثق التشغيل الحالي فقط.
- حذف: `render.yaml` و `Procfile`.

## القسم E — Download Runtime Audit

المسار الحالي:
1. استقبال URL في handler.
2. enqueue job عبر `DownloadService.enqueue_download`.
3. worker يلتقط job من queue.
4. تنفيذ download (`yt-dlp`) + تحويل (`ffmpeg`) عند الحاجة.
5. إرسال الوسائط إلى Telegram.
6. cleanup فوري للملفات.
7. retry/backoff عند الفشل المؤقت.

نقاط الحماية:
- webhook لا ينفذ التحميل الثقيل مباشرة.
- timeout للتحميل موجود.
- حد حجم الملف قبل الإرسال.
- retry مع backoff ومحاولات قصوى.

## القسم F — Exact Changes Applied

تم تطبيق التعديلات فعلياً على الملفات المذكورة أعلاه، مع حذف الملفات الخاصة بـ Render وتحديث compose/env/runtime defaults.

## القسم G — Deployment Files

الملفات الأساسية النهائية:
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `deploy/nginx.conf`
- `scripts/healthcheck.py`

## القسم H — VPS Runbook

1. تثبيت Docker + Compose + Nginx على Ubuntu 24.04.
2. استنساخ المشروع.
3. `cp .env.example .env` ثم تعبئة المتغيرات الفعلية.
4. تفعيل Nginx config من `deploy/nginx.conf` بعد استبدال `YOUR_DOMAIN`.
5. تشغيل: `docker compose up -d --build`.
6. التحقق: `/healthz` + `/readyz` + `getWebhookInfo` من Telegram.
7. المتابعة: `docker compose logs -f bot worker`.

## القسم I — Resource Fit Assessment

- مناسب لسيرفر 2 vCPU / 8 GB عند workload متوسط.
- الحدود العملية تعتمد على أحجام الفيديو وطول التحويل.
- إذا زاد queue depth باستمرار: خفف التزامن أو زد موارد السيرفر.

## القسم J — Final Verdict

- المشروع الآن جاهز عملياً لنشر self-hosted VPS single-bot webhook.
- المتبقي قبل go-live: تعبئة env الحقيقية + DNS/SSL + اختبار روابط فعلية متعددة.
- الخطر المتبقي: burst كبير من تنزيلات ثقيلة قد يرفع latency؛ المراقبة مطلوبة.
