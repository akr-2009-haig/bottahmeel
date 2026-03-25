#!/usr/bin/env bash
# deploy/init-letsencrypt.sh
#
# إعداد شهادة SSL من Let's Encrypt باستخدام Certbot + Nginx
# ─────────────────────────────────────────────────────────────
# المتطلبات:
#   - Nginx مثبت ويعمل
#   - النطاق يشير إلى هذا الخادم (A record → IP الخادم)
#   - deploy/nginx.conf مُطبَّق (يحتوي على إعداد HTTP لـ ACME challenge)
#
# الاستخدام:
#   DOMAIN=bot.example.com EMAIL=admin@example.com \
#   sudo bash deploy/init-letsencrypt.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "شغّل هذا السكريبت بصلاحيات root: sudo bash $0"

# ── المتغيرات ─────────────────────────────────────────────────────────────────
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/sites-available/karar-bot}"
STAGING="${STAGING:-0}"      # اضبط STAGING=1 للاختبار دون استهلاك حد الطلبات

# ── التحقق من المدخلات ────────────────────────────────────────────────────────
if [[ -z "$DOMAIN" ]]; then
    read -rp "أدخل اسم النطاق (مثال: bot.example.com): " DOMAIN
fi
[[ -z "$DOMAIN" ]] && error "لم يتم تحديد النطاق"

if [[ -z "$EMAIL" ]]; then
    read -rp "أدخل بريدك الإلكتروني لتنبيهات Let's Encrypt: " EMAIL
fi
[[ -z "$EMAIL" ]] && error "لم يتم تحديد البريد الإلكتروني"

info "النطاق : $DOMAIN"
info "البريد : $EMAIL"

# ── التحقق من توجيه DNS ──────────────────────────────────────────────────────
SERVER_IP="$(curl -4 -sf https://ifconfig.me || curl -4 -sf https://api.ipify.org || true)"
if [[ -z "$SERVER_IP" ]]; then
    warn "تعذّر تحديد IP الخادم تلقائياً."
    read -rp "أدخل IP الخادم يدوياً (أو اضغط Enter للتخطي): " SERVER_IP
fi
DOMAIN_IP="$(dig +short "$DOMAIN" A | tail -1 || true)"

if [[ "$DOMAIN_IP" != "$SERVER_IP" ]]; then
    warn "IP الخادم: $SERVER_IP"
    warn "IP النطاق: $DOMAIN_IP"
    warn "قد لا يشير النطاق إلى هذا الخادم بعد. تأكد من ضبط A record قبل المتابعة."
    read -rp "هل تريد المتابعة رغم ذلك؟ (yes/no): " CONFIRM
    [[ "$CONFIRM" == "yes" ]] || exit 0
fi

# ── التحقق من تثبيت Certbot ──────────────────────────────────────────────────
command -v certbot &>/dev/null || {
    info "تثبيت Certbot..."
    apt-get update -qq
    apt-get install -y certbot python3-certbot-nginx
}
success "Certbot: $(certbot --version 2>&1)"

# ── إنشاء مجلد ACME ──────────────────────────────────────────────────────────
mkdir -p /var/www/certbot

# ── تحديث Nginx ليحتوي على النطاق الصحيح ────────────────────────────────────
if [[ -f "$NGINX_CONF" ]]; then
    if grep -q "YOUR_DOMAIN" "$NGINX_CONF"; then
        info "استبدال YOUR_DOMAIN بـ $DOMAIN في $NGINX_CONF ..."
        sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$NGINX_CONF"
        nginx -t && systemctl reload nginx
        success "Nginx جاهز بالنطاق الصحيح"
    fi
else
    warn "ملف إعداد Nginx غير موجود في $NGINX_CONF"
fi

# ── طلب الشهادة ───────────────────────────────────────────────────────────────
STAGING_FLAG=""
[[ "$STAGING" == "1" ]] && {
    warn "وضع الاختبار مفعّل (--staging) – الشهادة لن تكون موثوقة"
    STAGING_FLAG="--staging"
}

info "طلب شهادة Let's Encrypt لـ $DOMAIN ..."
certbot --nginx \
    $STAGING_FLAG \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --domains "$DOMAIN" \
    --redirect

# ── التحقق من الشهادة ─────────────────────────────────────────────────────────
certbot certificates --domain "$DOMAIN"

# ── إعداد التجديد التلقائي ───────────────────────────────────────────────────
if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
    info "إضافة مهمة cron لتجديد الشهادة تلقائياً..."
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
    success "تم إضافة مهمة cron للتجديد التلقائي"
else
    success "مهمة cron للتجديد موجودة مسبقاً"
fi

# ── التحقق من إعادة تحميل Nginx ──────────────────────────────────────────────
nginx -t && systemctl reload nginx

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  تم إعداد SSL بنجاح! ✅${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  النطاق المحمي: https://$DOMAIN"
echo "  الشهادة       : /etc/letsencrypt/live/$DOMAIN/"
echo "  التجديد       : تلقائي عبر cron (كل يوم 3:00 صباحاً)"
echo ""
echo "  اختبر الـ Webhook:"
echo "    curl -I https://$DOMAIN/telegram/webhook"
echo ""
