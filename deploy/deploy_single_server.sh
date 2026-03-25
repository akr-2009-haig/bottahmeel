#!/usr/bin/env bash
# deploy/deploy_single_server.sh
#
# نص نشر Karar Bot على خادم Ubuntu 24.04 LTS (Hostinger KVM 8 أو ما يعادله)
# ─────────────────────────────────────────────────────────────────────────────
# الاستخدام:
#   chmod +x deploy/deploy_single_server.sh
#   sudo bash deploy/deploy_single_server.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── الألوان ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── التحقق من صلاحيات الجذر ──────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "شغّل هذا السكريبت بصلاحيات root: sudo bash $0"

# ── متغيرات قابلة للتعديل ─────────────────────────────────────────────────────
PROJECT_DIR="${PROJECT_DIR:-/opt/karar-bot}"
COMPOSE_FILE="docker-compose.single-server.yml"
ENV_FILE=".env.production"
NGINX_SITE="karar-bot"

# ══════════════════════════════════════════════════════════════════════════════
# 1. تحديث النظام
# ══════════════════════════════════════════════════════════════════════════════
info "تحديث قائمة الحزم..."
apt-get update -qq

# ══════════════════════════════════════════════════════════════════════════════
# 2. تثبيت Docker (إذا لم يكن مثبتاً)
# ══════════════════════════════════════════════════════════════════════════════
if ! command -v docker &>/dev/null; then
    info "تثبيت Docker..."
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    success "Docker مُثبَّت بنجاح"
else
    success "Docker موجود: $(docker --version)"
fi

# تحقق من Docker Compose Plugin
if ! docker compose version &>/dev/null; then
    info "تثبيت Docker Compose Plugin..."
    apt-get install -y docker-compose-plugin
fi
success "Docker Compose: $(docker compose version)"

# ══════════════════════════════════════════════════════════════════════════════
# 3. تثبيت Nginx
# ══════════════════════════════════════════════════════════════════════════════
if ! command -v nginx &>/dev/null; then
    info "تثبيت Nginx..."
    apt-get install -y nginx
    systemctl enable nginx
    success "Nginx مُثبَّت"
else
    success "Nginx موجود: $(nginx -v 2>&1)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 4. تثبيت Certbot
# ══════════════════════════════════════════════════════════════════════════════
if ! command -v certbot &>/dev/null; then
    info "تثبيت Certbot..."
    apt-get install -y certbot python3-certbot-nginx
    success "Certbot مُثبَّت"
else
    success "Certbot موجود: $(certbot --version 2>&1)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5. إنشاء مجلد المشروع
# ══════════════════════════════════════════════════════════════════════════════
info "إنشاء مجلد المشروع في $PROJECT_DIR ..."
mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/backups"
mkdir -p /var/www/certbot

# ══════════════════════════════════════════════════════════════════════════════
# 6. نسخ ملفات المشروع (إذا كنت تشغّل من داخل المستودع)
# ══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [[ "$(realpath "$REPO_ROOT")" != "$(realpath "$PROJECT_DIR")" ]]; then
    info "نسخ ملفات المشروع إلى $PROJECT_DIR ..."
    rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
          --exclude='.env*' \
          "$REPO_ROOT/" "$PROJECT_DIR/"
    success "تم نسخ الملفات"
fi

cd "$PROJECT_DIR"

# ══════════════════════════════════════════════════════════════════════════════
# 7. التحقق من ملف البيئة
# ══════════════════════════════════════════════════════════════════════════════
if [[ ! -f "$ENV_FILE" ]]; then
    warn "ملف البيئة $ENV_FILE غير موجود!"
    echo ""
    echo "  ─────────────────────────────────────────────────────────────────"
    echo "  الخطوات المطلوبة منك قبل المتابعة:"
    echo ""
    echo "  1. انسخ نموذج البيئة:"
    echo "     cp deploy/.env.single-server.example $PROJECT_DIR/$ENV_FILE"
    echo ""
    echo "  2. عدّل الملف وأدخل القيم الحقيقية:"
    echo "     nano $PROJECT_DIR/$ENV_FILE"
    echo ""
    echo "  3. شغّل هذا السكريبت مجدداً."
    echo "  ─────────────────────────────────────────────────────────────────"
    exit 1
fi
success "ملف البيئة موجود: $ENV_FILE"

# تحقق من وجود متغيرات إلزامية
for var in TELEGRAM_BOT_TOKEN BOT_OWNER_ID DATABASE_URL REDIS_URL WEBHOOK_URL \
           WEBHOOK_SECRET_TOKEN POSTGRES_PASSWORD; do
    val="$(grep -E "^${var}=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true)"
    if [[ -z "$val" ]]; then
        error "المتغير $var غير موجود أو فارغ في $ENV_FILE – أضف قيمته أولاً."
    elif [[ "$val" == *CHANGE_ME* ]]; then
        error "المتغير $var لا يزال يحتوي على القيمة الافتراضية 'CHANGE_ME' في $ENV_FILE – استبدلها بقيمة حقيقية."
    elif [[ "$val" == *YOUR_DOMAIN* ]]; then
        error "المتغير $var لا يزال يحتوي على 'YOUR_DOMAIN' في $ENV_FILE – استبدله بنطاقك الفعلي."
    fi
done
success "المتغيرات الإلزامية موجودة"

# ══════════════════════════════════════════════════════════════════════════════
# 8. إعداد Nginx
# ══════════════════════════════════════════════════════════════════════════════
NGINX_AVAILABLE="/etc/nginx/sites-available/$NGINX_SITE"
NGINX_ENABLED="/etc/nginx/sites-enabled/$NGINX_SITE"

if [[ ! -f "$NGINX_AVAILABLE" ]]; then
    info "نسخ إعداد Nginx..."
    cp "$PROJECT_DIR/deploy/nginx.conf" "$NGINX_AVAILABLE"
    warn "يجب عليك تعديل $NGINX_AVAILABLE واستبدال YOUR_DOMAIN بنطاقك الفعلي."
fi

[[ -L "$NGINX_ENABLED" ]] || ln -s "$NGINX_AVAILABLE" "$NGINX_ENABLED"

# إزالة الموقع الافتراضي إن وجد
[[ -L "/etc/nginx/sites-enabled/default" ]] && rm -f "/etc/nginx/sites-enabled/default"

nginx -t || error "إعداد Nginx يحتوي على أخطاء – راجع $NGINX_AVAILABLE"
systemctl reload nginx
success "Nginx جاهز"

# ══════════════════════════════════════════════════════════════════════════════
# 9. بناء صور Docker وتشغيل الخدمات
# ══════════════════════════════════════════════════════════════════════════════
info "بناء صور Docker..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --pull

info "تشغيل الخدمات..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# ══════════════════════════════════════════════════════════════════════════════
# 10. انتظار جاهزية الخدمات
# ══════════════════════════════════════════════════════════════════════════════
info "انتظار جاهزية الخدمات (حتى 60 ثانية)..."
TIMEOUT=60
ELAPSED=0
until curl -sf http://127.0.0.1:8081/readyz >/dev/null 2>&1; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    [[ $ELAPSED -ge $TIMEOUT ]] && {
        warn "انتهت مهلة الانتظار. تحقق من السجلات:"
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=50
        error "البوت لم يصبح جاهزاً خلال $TIMEOUT ثانية"
    }
    echo -n "."
done
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# 11. التحقق من حالة الخدمات
# ══════════════════════════════════════════════════════════════════════════════
info "التحقق من حالة الحاويات..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

info "فحص نقطة الصحة..."
curl -sf http://127.0.0.1:8081/healthz | python3 -m json.tool || true

# ══════════════════════════════════════════════════════════════════════════════
# 12. رسالة الختام
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  تم نشر Karar Bot بنجاح! ✅${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  النطاق    : $(grep -E '^WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2-)"
echo "  الـ Webhook: $(grep -E '^WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2-)$(grep -E '^WEBHOOK_PATH=' "$ENV_FILE" | cut -d= -f2-)"
echo ""
echo "  الأوامر المفيدة:"
echo "    docker compose -f $COMPOSE_FILE --env-file $ENV_FILE logs -f bot"
echo "    docker compose -f $COMPOSE_FILE --env-file $ENV_FILE logs -f worker"
echo "    docker compose -f $COMPOSE_FILE --env-file $ENV_FILE ps"
echo "    curl http://127.0.0.1:8081/readyz"
echo ""
echo "  لتفعيل SSL (مطلوب للـ Webhook):"
echo "    bash $PROJECT_DIR/deploy/init-letsencrypt.sh"
echo ""
