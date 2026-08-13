#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${SCRIPT_DIR}/common.sh"

DATA_ROOT=$(env_value FABOPS_DATA_ROOT)
BACKUP_DIR="${DATA_ROOT}/backups/postgres"
STAMP=$(date -u '+%Y%m%dT%H%M%SZ')
DUMP="${BACKUP_DIR}/fabops-${STAMP}.dump"
TMP="${DUMP}.tmp"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
umask 077

compose exec -T postgres pg_dump -U fabops -d fabops -Fc > "${TMP}"
mv "${TMP}" "${DUMP}"
chmod 600 "${DUMP}"

echo "backup=${DUMP}"
