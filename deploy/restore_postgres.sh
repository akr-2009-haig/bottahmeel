#!/usr/bin/env bash
# deploy/restore_postgres.sh
#
# استعادة قاعدة بيانات PostgreSQL من نسخة احتياطية
# ─────────────────────────────────────────────────────────────
# ⚠️  تحذير: سيتم حذف البيانات الحالية في قاعدة البيانات واستبدالها
#            بالبيانات الموجودة في ملف النسخة الاحتياطية.
#            تأكد من أخذ نسخة احتياطية حديثة قبل المتابعة.
# ─────────────────────────────────────────────────────────────
# الاستخدام:
#   bash deploy/restore_postgres.sh backups/karar_bot_20240101_120000.sql.gz
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── الألوان ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── الإعدادات ─────────────────────────────────────────────────────────────────
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.single-server.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_FILE="${1:-}"

# ── التحقق من المدخلات ────────────────────────────────────────────────────────
if [[ -z "$BACKUP_FILE" ]]; then
    echo "الاستخدام: bash $0 <ملف_النسخة_الاحتياطية>"
    echo ""
    echo "مثال:"
    echo "  bash $0 backups/karar_bot_20240101_120000.sql.gz"
    echo ""
    echo "النسخ المتاحة في ./backups:"
    ls -lh ./backups/*.sql.gz 2>/dev/null || echo "  (لا يوجد)"
    exit 1
fi

[[ -f "$BACKUP_FILE" ]] || error "ملف النسخة الاحتياطية غير موجود: $BACKUP_FILE"

# ── قراءة متغيرات البيئة ─────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    set -a; source "$ENV_FILE"; set +a
else
    warn "ملف البيئة $ENV_FILE غير موجود – سيتم استخدام القيم الافتراضية"
fi

DB_NAME="${POSTGRES_DB:-karar_bot}"
DB_USER="${POSTGRES_USER:-karar}"
DB_CONTAINER="${DB_CONTAINER:-$(docker compose -f "$COMPOSE_FILE" ps -q db 2>/dev/null || true)}"

if [[ -z "$DB_CONTAINER" ]]; then
    DB_CONTAINER="$(docker ps --filter "name=db" --filter "status=running" -q | head -1 || true)"
fi
[[ -n "$DB_CONTAINER" ]] || error "لم يتم العثور على حاوية قاعدة البيانات. تأكد من تشغيل الخدمات."

# ── تحذير المستخدم ────────────────────────────────────────────────────────────
echo ""
echo -e "${RED}══════════════════════════════════════════════════════════${NC}"
echo -e "${RED}  ⚠️  تحذير: عملية الاستعادة ستحذف البيانات الحالية!${NC}"
echo -e "${RED}══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  الحاوية     : $DB_CONTAINER"
echo "  قاعدة البيانات: $DB_NAME"
echo "  ملف الاستعادة: $BACKUP_FILE"
echo "  الحجم        : $(du -sh "$BACKUP_FILE" | cut -f1)"
echo ""

# أخذ نسخة احتياطية تلقائية قبل الاستعادة
BACKUP_DIR="${BACKUP_DIR:-./backups}"
AUTO_BACKUP="$BACKUP_DIR/${DB_NAME}_before_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
info "أخذ نسخة احتياطية تلقائية قبل الاستعادة..."
mkdir -p "$BACKUP_DIR"
docker exec "$DB_CONTAINER" \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --no-password \
    | gzip > "$AUTO_BACKUP" 2>/dev/null || warn "لم يتمكن من أخذ النسخة الاحتياطية التلقائية (قد تكون القاعدة فارغة)"
[[ -f "$AUTO_BACKUP" ]] && ok "نسخة احتياطية تلقائية: $AUTO_BACKUP"

read -rp "هل أنت متأكد من المتابعة؟ اكتب 'yes' للتأكيد: " CONFIRM
[[ "$CONFIRM" == "yes" ]] || { echo "تم الإلغاء."; exit 0; }

# ── إيقاف البوت والـ workers مؤقتاً ─────────────────────────────────────────
info "إيقاف البوت والـ workers مؤقتاً..."
docker compose -f "$COMPOSE_FILE" stop bot worker 2>/dev/null || true

# ── تنفيذ الاستعادة ──────────────────────────────────────────────────────────
info "بدء الاستعادة من $BACKUP_FILE ..."

# حذف الاتصالات النشطة وإسقاط القاعدة وإعادة إنشاؤها
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres --no-password -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=\$q\$$DB_NAME\$q\$ AND pid <> pg_backend_pid();" \
    2>/dev/null || true

docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres --no-password -c \
    "DROP DATABASE IF EXISTS \"$DB_NAME\";" 2>/dev/null || true

docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres --no-password -c \
    "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" 2>/dev/null

# استيراد النسخة الاحتياطية
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" --no-password -q
else
    docker exec -i "$DB_CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" --no-password -q < "$BACKUP_FILE"
fi

ok "تمت الاستعادة بنجاح"

# ── إعادة تشغيل الخدمات ──────────────────────────────────────────────────────
info "إعادة تشغيل الخدمات..."
docker compose -f "$COMPOSE_FILE" start bot worker 2>/dev/null || \
    docker compose -f "$COMPOSE_FILE" up -d bot worker

echo ""
ok "اكتملت عملية الاستعادة ✅"
echo ""
