#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${SCRIPT_DIR}/common.sh"

DATA_ROOT=$(env_value FABOPS_DATA_ROOT)
BACKUP_DIR="${DATA_ROOT}/backups/postgres"
DUMP=${1:-$(ls -1t "${BACKUP_DIR}"/fabops-*.dump 2>/dev/null | head -1)}

if [ -z "${DUMP}" ] || [ ! -f "${DUMP}" ]; then
  echo "no FabOps PostgreSQL dump available" >&2
  exit 2
fi

DB="fabops_restore_test_$(date -u '+%Y%m%d%H%M%S')"
cleanup() {
  compose exec -T postgres dropdb -U fabops --if-exists "${DB}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

compose exec -T postgres createdb -U fabops "${DB}"
cat "${DUMP}" | compose exec -T postgres pg_restore -U fabops -d "${DB}" --no-owner --no-acl

EVENTS=$(compose exec -T postgres psql -U fabops -d "${DB}" -Atc 'SELECT count(*) FROM fabops_event_log')
CASES=$(compose exec -T postgres psql -U fabops -d "${DB}" -Atc 'SELECT count(*) FROM fabops_cases')
MIGRATIONS=$(compose exec -T postgres psql -U fabops -d "${DB}" -Atc 'SELECT count(*) FROM fabops_schema_migrations')

test "${EVENTS}" -gt 0
test "${CASES}" -gt 0
test "${MIGRATIONS}" -gt 0

echo "restore_test_database=${DB} events=${EVENTS} cases=${CASES} migrations=${MIGRATIONS}"
