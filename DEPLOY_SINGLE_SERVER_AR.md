# دليل النشر على خادم واحد – Hostinger KVM 8
## Karar Bot – نشر الإنتاج على Ubuntu 24.04 LTS

---

## جدول المحتويات

1. [هل KVM 8 مناسب لهذا المشروع؟](#1-هل-kvm-8-مناسب-لهذا-المشروع)
2. [ما يمكن تحمّله وما لا يمكن على خادم واحد](#2-ما-يمكن-تحمّله-وما-لا-يمكن-على-خادم-واحد)
3. [لماذا KVM 8 وليس خطة أصغر؟](#3-لماذا-kvm-8-وليس-خطة-أصغر)
4. [المتطلبات الأولية](#4-المتطلبات-الأولية)
5. [خطوات النشر على Ubuntu 24.04](#5-خطوات-النشر-على-ubuntu-2404)
6. [إعداد النطاق](#6-إعداد-النطاق)
7. [إعداد SSL](#7-إعداد-ssl)
8. [إعداد الـ Webhook](#8-إعداد-الـ-webhook)
9. [ضبط Workers على خادم واحد](#9-ضبط-workers-على-خادم-واحد)
10. [مراقبة السجلات والصحة](#10-مراقبة-السجلات-والصحة)
11. [التحقق من صحة النشر](#11-التحقق-من-صحة-النشر)
12. [النسخ الاحتياطي والاستعادة](#12-النسخ-الاحتياطي-والاستعادة)
13. [القيود المعمارية لخادم واحد](#13-القيود-المعمارية-لخادم-واحد)
14. [متى تنتقل إلى خوادم متعددة؟](#14-متى-تنتقل-إلى-خوادم-متعددة؟)

---

## 1. هل KVM 8 مناسب لهذا المشروع؟

**نعم – وهو الحد الأدنى الموصى به للإنتاج الحقيقي.**

موارد KVM 8 من Hostinger:
- **8 vCPU** – كافية لتشغيل البوت + 2-4 workers متزامنة مع تحميل yt-dlp
- **32 GB RAM** – تُتيح تشغيل PostgreSQL + Redis + Docker + workers بهامش مريح
- **400 GB NVMe** – يسمح بتخزين الملفات المؤقتة والسجلات والنسخ الاحتياطية لأشهر
- **32 TB نطاق ترددي** – كافٍ جداً لبوت تنزيل وسائط على مستوى آلاف المستخدمين اليوميين

---

## 2. ما يمكن تحمّله وما لا يمكن على خادم واحد

### ✅ ما يمكن تحقيقه بواقعية على KVM 8

| السيناريو | التفاصيل |
|-----------|----------|
| **عدد المستخدمين النشطين** | 5,000 – 20,000 مستخدم نشط يومياً |
| **الطلبات المتزامنة** | 8 تنزيلات متزامنة (worker×2, concurrency×4) |
| **حجم الملفات** | ملفات فيديو تصل إلى 50 MB بأداء جيد |
| **Webhook** | استقبال تحديثات Telegram بسرعة عالية |
| **قاعدة البيانات** | PostgreSQL بآلاف السجلات يومياً بلا إشكال |
| **الجدول الزمني** | المهام المجدولة (scheduled posts) تعمل بثبات |

### ⚠️ القيود الواقعية

| القيد | التفاصيل |
|-------|----------|
| **500,000 مستخدم** | **غير واقعي على خادم واحد** – راجع القسم 13 |
| **تنزيلات متزامنة عالية** | CPU يتشبع بعد ~8-12 تنزيل ffmpeg متزامن |
| **بدون failover** | توقف الخادم = توقف كامل للبوت |
| **PostgreSQL مُحمَّل** | ليس مُعداً لعشرات الآلاف من الاستعلامات في الثانية |
| **ذاكرة Redis** | مضبوطة على 512 MB – اضبطها حسب حجم الطابور |

---

## 3. لماذا KVM 8 وليس خطة أصغر؟

| الخطة | السبب |
|-------|-------|
| **KVM 1 (4GB RAM)** | ❌ غير كافية – ffmpeg وحده يستهلك 200-400 MB لكل تنزيل |
| **KVM 2 (8GB RAM)** | ⚠️ ضيقة – تنزيل عدة مقاطع فيديو يوقفها |
| **KVM 4 (16GB RAM)** | ✅ حد أدنى مقبول للإنتاج الخفيف |
| **KVM 8 (32GB RAM)** | ✅✅ **الاختيار الأمثل** – يعطي هامشاً مريحاً للنمو |

**العوامل الحاسمة للبوت:**
- **ffmpeg** يستهلك CPU وذاكرة بشكل مكثّف عند معالجة الفيديو
- **yt-dlp** يفتح اتصالات شبكة متعددة لكل تنزيل
- **PostgreSQL + Redis** يحتاجان ذاكرة ثابتة
- **Docker** نفسه يحتاج ذاكرة للحاويات

---

## 4. المتطلبات الأولية

قبل البدء، تأكد من:

1. **خادم Hostinger KVM 8** جاهز وتعرف عنوان IP الخاص به
2. **نطاق (Domain)** تملكه وتستطيع إدارة DNS الخاص به
3. **وصول SSH** إلى الخادم كـ root أو بصلاحيات sudo
4. **توكن بوت Telegram** من BotFather
5. **معرّف Telegram الخاص بك** (BOT_OWNER_ID) – ابحث عن @userinfobot لمعرفته

**أدوات مفيدة عند الضرورة (من هاتفك/Termux):**
```bash
# تثبيت Termux على Android ثم:
pkg install openssh
ssh root@YOUR_SERVER_IP
```

---

## 5. خطوات النشر على Ubuntu 24.04

### الخطوة 1: الاتصال بالخادم

```bash
ssh root@YOUR_SERVER_IP
```

### الخطوة 2: تحديث النظام

```bash
apt update && apt upgrade -y
apt install -y git curl
```

### الخطوة 3: استنساخ المستودع

```bash
cd /opt
git clone https://github.com/akr-2009-haig/Karar-bots-downloader.git karar-bot
cd karar-bot
```

### الخطوة 4: إعداد ملف البيئة

```bash
cp deploy/.env.single-server.example .env.production
nano .env.production
```

**القيم الإلزامية التي يجب تغييرها:**

```
TELEGRAM_BOT_TOKEN=123456789:AA...     ← توكن البوت
BOT_OWNER_ID=123456789                 ← معرّف Telegram الخاص بك
WEBHOOK_URL=https://bot.example.com   ← نطاقك مع https
WEBHOOK_SECRET_TOKEN=...               ← رمز عشوائي قوي
DATABASE_URL=postgresql://karar:PASS@db:5432/karar_bot
POSTGRES_PASSWORD=PASS                 ← كلمة مرور قوية
```

> **لتوليد رمز عشوائي:**
> ```bash
> python3 -c "import secrets; print(secrets.token_hex(32))"
> ```

### الخطوة 5: تشغيل السكريبت الآلي

```bash
chmod +x deploy/deploy_single_server.sh
sudo bash deploy/deploy_single_server.sh
```

هذا السكريبت سيقوم تلقائياً بـ:
- تثبيت Docker + Docker Compose Plugin
- تثبيت Nginx + Certbot
- إعداد Nginx
- بناء صور Docker
- تشغيل جميع الخدمات
- التحقق من الصحة

---

## 6. إعداد النطاق

### 6.1 إضافة A Record

اذهب إلى لوحة DNS الخاصة بنطاقك وأضف:

| النوع | الاسم | القيمة |
|-------|-------|--------|
| A | `bot` | `YOUR_SERVER_IP` |

أو إذا أردت النطاق الرئيسي:

| النوع | الاسم | القيمة |
|-------|-------|--------|
| A | `@` | `YOUR_SERVER_IP` |

### 6.2 التحقق من DNS

انتظر 5-30 دقيقة ثم تحقق:
```bash
dig +short bot.example.com A
# يجب أن يظهر IP خادمك
```

---

## 7. إعداد SSL

SSL **إلزامي** للـ Webhook – Telegram يرفض URLs بدون HTTPS.

### الطريقة الآلية (Certbot):

```bash
DOMAIN=bot.example.com \
EMAIL=admin@example.com \
sudo bash deploy/init-letsencrypt.sh
```

السكريبت سيقوم بـ:
1. التحقق من توجيه DNS
2. طلب شهادة مجانية من Let's Encrypt
3. تفعيل SSL في Nginx
4. إعداد التجديد التلقائي

### التحقق من SSL:

```bash
curl -I https://bot.example.com/telegram/webhook
# يجب أن يظهر: HTTP/2 404 (أو 200 عند الإرسال الصحيح)
```

---

## 8. إعداد الـ Webhook

البوت يُسجّل الـ Webhook تلقائياً عند بدء التشغيل في وضع webhook، لكن يمكن التحقق يدوياً:

### التحقق من تسجيل الـ Webhook:

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo" | python3 -m json.tool
```

**النتيجة المتوقعة:**
```json
{
  "ok": true,
  "result": {
    "url": "https://bot.example.com/telegram/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "last_error_message": ""
  }
}
```

### ملاحظة مهمة حول المنافذ:

| المنفذ | الغرض | الوصول |
|--------|--------|--------|
| `8080` | استقبال تحديثات Telegram (Webhook) | عبر Nginx (مخفي) |
| `8081` | نقاط فحص الصحة: `/healthz` `/readyz` `/queuez` | داخلي فقط |

**المنفذ 8081 لا يُكشف للإنترنت.** يمكن الوصول إليه من الخادم نفسه فقط:
```bash
curl http://127.0.0.1:8081/healthz
curl http://127.0.0.1:8081/readyz
curl http://127.0.0.1:8081/queuez
```

---

## 9. ضبط Workers على خادم واحد

### الإعداد الافتراضي

يشغّل docker-compose.single-server.yml بشكل افتراضي:
- **1 حاوية bot** (webhook receiver)
- **2 حاوية worker** (معالجة التنزيلات)
- كل worker بـ `WORKER_CONCURRENCY=4`
- إجمالي: **8 تنزيلات متزامنة**

### رفع عدد الـ Workers

على KVM 8 يمكنك رفع إلى 4 workers:

```bash
docker compose -f docker-compose.single-server.yml \
  --env-file .env.production \
  up -d --scale worker=4
```

> ⚠️ **قاعدة عامة:** لا ترفع WORKER_CONCURRENCY × replicas فوق عدد vCPU الفعلي.
> على KVM 8 (8 vCPU): الحد الأقصى الموصى به = 2 workers × 4 concurrency = 8 تزامن.

### متى ترفع Workers؟

راقب باستخدام:
```bash
# مراقبة CPU
watch -n 2 'docker stats --no-stream'

# قائمة انتظار المهام
curl http://127.0.0.1:8081/queuez
```

إذا رأيت:
- `pending_jobs` > 10 باستمرار → زد عدد الـ workers
- CPU < 50% → يمكن زيادة WORKER_CONCURRENCY

---

## 10. مراقبة السجلات والصحة

### عرض السجلات المباشر

```bash
# سجلات البوت (webhook)
docker compose -f docker-compose.single-server.yml --env-file .env.production \
  logs -f bot

# سجلات الـ workers
docker compose -f docker-compose.single-server.yml --env-file .env.production \
  logs -f worker

# جميع السجلات معاً
docker compose -f docker-compose.single-server.yml --env-file .env.production \
  logs -f
```

### فحص صحة الخدمات

```bash
# فحص سريع
curl http://127.0.0.1:8081/healthz

# فحص الجاهزية الكاملة (database + redis + workers)
curl http://127.0.0.1:8081/readyz

# إحصاءات الطابور ونبضات الـ workers
curl http://127.0.0.1:8081/queuez
```

**نتيجة /readyz عند الجاهزية الكاملة:**
```json
{
  "status": "ready",
  "database": "ok",
  "broker": "ok",
  "workers": "ok"
}
```

### مراقبة موارد الخادم

```bash
# استخدام الموارد لكل حاوية
docker stats

# مساحة القرص
df -h /var/lib/docker
du -sh /opt/karar-bot/backups
```

---

## 11. التحقق من صحة النشر

قائمة تحقق سريعة بعد كل نشر:

```bash
# 1. التحقق من تشغيل الحاويات
docker compose -f docker-compose.single-server.yml --env-file .env.production ps

# 2. فحص الصحة
curl -s http://127.0.0.1:8081/readyz | python3 -m json.tool

# 3. التحقق من تسجيل Webhook
source .env.production
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
  | python3 -m json.tool

# 4. اختبار البوت مباشرة
# أرسل /start للبوت في Telegram وتأكد من الرد

# 5. التحقق من SSL
curl -I https://YOUR_DOMAIN/telegram/webhook
```

---

## 12. النسخ الاحتياطي والاستعادة

### أخذ نسخة احتياطية يدوية

```bash
cd /opt/karar-bot
bash deploy/backup_postgres.sh
```

تُحفظ النسخة في: `./backups/karar_bot_YYYYMMDD_HHMMSS.sql.gz`

### إعداد نسخ احتياطية تلقائية يومية

```bash
# إضافة مهمة cron
crontab -e

# أضف هذا السطر (نسخ احتياطي يومياً في 2:00 صباحاً)
0 2 * * * cd /opt/karar-bot && bash deploy/backup_postgres.sh >> /var/log/karar-bot-backup.log 2>&1
```

### استعادة من نسخة احتياطية

```bash
cd /opt/karar-bot

# عرض النسخ المتاحة
ls -lh backups/

# تنفيذ الاستعادة
bash deploy/restore_postgres.sh backups/karar_bot_20240101_120000.sql.gz
```

> ⚠️ سيطلب السكريبت تأكيدك قبل حذف البيانات الحالية.
> يأخذ نسخة احتياطية تلقائية قبل تنفيذ الاستعادة.

### النسخ الاحتياطية على Hostinger

Hostinger KVM يوفر **نسخاً احتياطية أسبوعية مجانية** على مستوى الخادم (snapshot).
يُنصح باستخدامها كطبقة حماية إضافية بجانب pg_dump اليومي.

---

## 13. القيود المعمارية لخادم واحد

### نقطة الفشل الواحدة (Single Point of Failure)

| المكوّن | التأثير عند التوقف |
|---------|-------------------|
| الخادم الكامل | البوت يتوقف 100% |
| Docker daemon | جميع الخدمات تتوقف |
| PostgreSQL | لا استقبال طلبات |
| Redis | الطابور يُعطَّل |

**الحل:** خطط للصيانة في أوقات قليلة الاستخدام.

### حدود الأداء الواقعية

| المقياس | القيمة على KVM 8 |
|---------|-----------------|
| مستخدمون نشطون يومياً | 5,000 – 15,000 |
| تنزيلات في الساعة | ~300-500 (حسب الحجم) |
| ذروة طلبات Telegram | ~100 تحديث/ثانية |
| مساحة الملفات المؤقتة | ~10-50 GB يومياً (تُحذف بعد 6 ساعات) |

### طموح 500,000 مستخدم – الحقيقة الكاملة

**خادم واحد لا يستطيع تحقيق هذا الهدف بأمان وجودة.** إليك لماذا:

1. **ffmpeg مُكثَّف**: كل تنزيل فيديو يحتاج 0.5-3 ثوانٍ من CPU
2. **الاتصالات بـ Telegram**: حجم الـ webhook يرتفع بشكل غير خطي
3. **قاعدة البيانات**: كتابة/قراءة آلاف السجلات المتزامنة
4. **تخزين الملفات المؤقتة**: تكبر بسرعة مع كثافة الاستخدام

> **التقدير الواقعي:** خادم KVM 8 يُعالج 5,000-20,000 مستخدم نشط يومياً بجودة عالية.
> للوصول إلى 500,000 تحتاج معمارية موزّعة (راجع القسم 14).

---

## 14. متى تنتقل إلى خوادم متعددة؟

### المؤشرات التي تدل على الحاجة للتوسع

```
متوسط CPU > 70%  لأكثر من ساعة في اليوم
RAM متاح < 4 GB
قائمة الانتظار: pending_jobs > 50 باستمرار
زمن استجابة البوت > 3 ثوانٍ
```

### معمارية متعددة الخوادم (المرحلة التالية)

```
[Telegram] → [Load Balancer]
                     ↓
         ┌──────────────────────┐
         │  Bot instances (×3)  │  ← خوادم webhook منفصلة
         └──────────────────────┘
                     ↓
         ┌──────────────────────┐
         │  Redis Cluster       │  ← طابور مهام موزّع
         │  (3 nodes)           │
         └──────────────────────┘
                     ↓
         ┌──────────────────────┐
         │  Worker pool (×N)    │  ← خوادم تنزيل منفصلة
         └──────────────────────┘
                     ↓
         ┌──────────────────────┐
         │  PostgreSQL primary  │  ← قاعدة بيانات مع read replicas
         │  + read replicas     │
         └──────────────────────┘
```

### جدول النمو التقريبي

| المرحلة | المستخدمون اليوميون | البنية التحتية |
|---------|---------------------|----------------|
| المرحلة 1 | 0 – 20,000 | KVM 8 (خادم واحد) |
| المرحلة 2 | 20,000 – 100,000 | 2 بوت + 4 workers + PostgreSQL مُدار |
| المرحلة 3 | 100,000 – 500,000 | Kubernetes / خوادم متخصصة |

---

## ملحق: أوامر مرجعية سريعة

```bash
# تشغيل الخدمات
docker compose -f docker-compose.single-server.yml --env-file .env.production up -d

# إيقاف الخدمات
docker compose -f docker-compose.single-server.yml --env-file .env.production down

# إعادة بناء وتشغيل
docker compose -f docker-compose.single-server.yml --env-file .env.production up -d --build

# عرض الحاويات
docker compose -f docker-compose.single-server.yml --env-file .env.production ps

# سجلات مباشرة
docker compose -f docker-compose.single-server.yml --env-file .env.production logs -f

# نسخة احتياطية
bash deploy/backup_postgres.sh

# استعادة
bash deploy/restore_postgres.sh backups/karar_bot_YYYYMMDD_HHMMSS.sql.gz

# فحص الصحة
curl http://127.0.0.1:8081/readyz

# تجديد SSL يدوياً
certbot renew --post-hook "systemctl reload nginx"
```

---

> **ملاحظة:** هذا الدليل مُعدّ خصيصاً لـ Hostinger KVM 8 بنظام Ubuntu 24.04 LTS.
> لأي تغييرات في البنية التحتية، راجع الوثائق التقنية للمشروع.
