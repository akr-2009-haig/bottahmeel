#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/karar_bot_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

if [ -n "${DATABASE_URL:-}" ]; then
  pg_dump \
    --format=custom \
    --no-owner \
    --no-privileges \
    --dbname="${DATABASE_URL}" \
    --file="${BACKUP_FILE}"
else
  pg_dump \
    --format=custom \
    --no-owner \
    --no-privileges \
    --file="${BACKUP_FILE}"
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"
fi

find "${BACKUP_DIR}" -type f -name '*.dump' -mtime +"${RETENTION_DAYS}" -delete
find "${BACKUP_DIR}" -type f -name '*.dump.sha256' -mtime +"${RETENTION_DAYS}" -delete

echo "Backup created: ${BACKUP_FILE}"
