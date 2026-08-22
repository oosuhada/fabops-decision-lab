#!/bin/sh
set -eu

PATH="/usr/local/bin:/opt/homebrew/bin:${HOME}/.orbstack/bin:${PATH}"
export PATH

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/../../.." && pwd)
DEPLOY_DIR="${REPO_ROOT}/infra/macmini"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.yml"
ENV_FILE="${DEPLOY_DIR}/.env"
PROJECT_NAME="fabops-decision-lab-macmini"

cd "${REPO_ROOT}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "missing server-only ${ENV_FILE}" >&2
  exit 2
fi

mode=$(stat -Lf '%Lp' "${ENV_FILE}")
if [ "${mode}" != "600" ]; then
  echo "server-only .env must have mode 0600" >&2
  exit 2
fi

env_value() {
  awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "${ENV_FILE}"
}

compose() {
  docker compose --project-name "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}
