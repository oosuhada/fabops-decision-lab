#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${SCRIPT_DIR}/common.sh"

DATA_ROOT=$(env_value FABOPS_DATA_ROOT)
API_PORT=$(env_value FABOPS_API_PORT)
WEB_PORT=$(env_value FABOPS_WEB_PORT)

mkdir -p \
  "${DATA_ROOT}/postgres" \
  "${DATA_ROOT}/redpanda" \
  "${DATA_ROOT}/neo4j" \
  "${DATA_ROOT}/backups/postgres" \
  "${DATA_ROOT}/restore-test" \
  "${DATA_ROOT}/rollback-quarantine" \
  "${DATA_ROOT}/burnin"
chmod 700 "${DATA_ROOT}" "${DATA_ROOT}/backups" "${DATA_ROOT}/backups/postgres" "${DATA_ROOT}/restore-test" "${DATA_ROOT}/rollback-quarantine" "${DATA_ROOT}/burnin"

compose config --quiet
compose up -d --build postgres redpanda neo4j
compose up --build redpanda-init
compose up --build init
compose up -d --build api web

attempt=0
until curl -fsS "http://127.0.0.1:${API_PORT}/health/ready" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 30 ]; then
    echo "API readiness did not become healthy" >&2
    compose ps
    exit 1
  fi
  sleep 2
done

attempt=0
until curl -fsS "http://127.0.0.1:${WEB_PORT}/health/live" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 30 ]; then
    echo "Web liveness did not become healthy" >&2
    compose ps
    exit 1
  fi
  sleep 2
done

EXPECTED_VERSION=$(python3 -c 'import json; print(json.load(open("evidence/release/release-manifest.json"))["release_version"])' < /dev/null)
EXPECTED_HASH=$(python3 -c 'import json; print(json.load(open("evidence/release/release-manifest.json"))["release_hash"])' < /dev/null)
curl -fsS "http://127.0.0.1:${API_PORT}/api/release" | python3 -c 'import json,sys; d=json.load(sys.stdin); v=sys.argv[1]; h=sys.argv[2]; assert d["release_version"] == v; assert d["release_hash"] == h' "${EXPECTED_VERSION}" "${EXPECTED_HASH}"

echo "FabOps deployment healthy on localhost ports ${API_PORT}/${WEB_PORT}."
