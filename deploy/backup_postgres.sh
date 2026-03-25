#!/usr/bin/env bash
# deploy/backup_postgres.sh
#
# نسخ احتياطي لقاعدة بيانات PostgreSQL من حاوية Docker
# ─────────────────────────────────────────────────────────────
# الاستخدام:
#   bash deploy/backup_postgres.sh
#
# المتغيرات الاختيارية (يمكن تجاوزها):
#   COMPOSE_FILE  – ملف Docker Compose (افتراضي: docker-compose.single-server.yml)
#   ENV_FILE      – ملف البيئة (افتراضي: .env.production)
#   BACKUP_DIR    – مجلد حفظ النسخ الاحتياطية (افتراضي: ./backups)
#   KEEP_DAYS     – عدد أيام الاحتفاظ بالنسخ (افتراضي: 7)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── الإعدادات ─────────────────────────────────────────────────────────────────
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.single-server.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ── الألوان ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "\033[0;36m[INFO]\033[0m  $*"; }
ok()    { echo -e "${GREEN}[OK]\033[0m    $*"; }
warn()  { echo -e "${YELLOW}[WARN]\033[0m  $*"; }
error() { echo -e "${RED}[ERROR]\033[0m $*" >&2; exit 1; }

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

# ── التحقق من تشغيل حاوية قاعدة البيانات ────────────────────────────────────
if [[ -z "$DB_CONTAINER" ]]; then
    # محاولة الحصول على اسم الحاوية بطريقة أخرى
    DB_CONTAINER="$(docker ps --filter "name=db" --filter "status=running" -q | head -1 || true)"
fi
[[ -n "$DB_CONTAINER" ]] || error "لم يتم العثور على حاوية قاعدة البيانات. تأكد من تشغيل الخدمات."

info "الحاوية: $DB_CONTAINER"
info "قاعدة البيانات: $DB_NAME"

# ── إنشاء مجلد النسخ الاحتياطية ─────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

# ── تنفيذ النسخة الاحتياطية ──────────────────────────────────────────────────
info "بدء النسخ الاحتياطي..."
docker exec "$DB_CONTAINER" \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --no-password \
    | gzip > "$BACKUP_FILE"

# ── التحقق من صحة الملف ──────────────────────────────────────────────────────
FILE_SIZE="$(du -sh "$BACKUP_FILE" | cut -f1)"
ok "تم حفظ النسخة الاحتياطية: $BACKUP_FILE ($FILE_SIZE)"

# ── حذف النسخ القديمة ────────────────────────────────────────────────────────
info "حذف النسخ الأقدم من $KEEP_DAYS أيام..."
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime "+$KEEP_DAYS" -delete
ok "تم تنظيف النسخ القديمة"

# ── ملخص النسخ المتاحة ───────────────────────────────────────────────────────
echo ""
echo "النسخ الاحتياطية المتاحة في $BACKUP_DIR:"
ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null || echo "  (لا يوجد)"
echo ""
