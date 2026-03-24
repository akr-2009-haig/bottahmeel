#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "Usage: $0 /path/to/backup.dump [target_database_url]" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DATABASE_URL="${2:-${DATABASE_URL:-}}"

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

if [ -z "${TARGET_DATABASE_URL}" ]; then
  echo "Set DATABASE_URL or pass a target_database_url argument." >&2
  exit 1
fi

pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --dbname="${TARGET_DATABASE_URL}" \
  "${BACKUP_FILE}"

echo "Restore completed from ${BACKUP_FILE}"
