#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${SCRIPT_DIR}/common.sh"

API_PORT=$(env_value FABOPS_API_PORT)
WEB_PORT=$(env_value FABOPS_WEB_PORT)

compose ps
curl -fsS "http://127.0.0.1:${API_PORT}/health/ready"
printf '\n'
curl -fsS "http://127.0.0.1:${WEB_PORT}/health/live"
printf '\n'
