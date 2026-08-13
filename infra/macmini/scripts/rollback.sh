#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${SCRIPT_DIR}/common.sh"

MODE=${1:-stop}
DATA_ROOT=$(env_value FABOPS_DATA_ROOT)

case "${MODE}" in
  stop)
    compose down --remove-orphans
    ;;
  first-deploy)
    STAMP=$(date -u '+%Y%m%dT%H%M%SZ')
    QUARANTINE="${DATA_ROOT}/rollback-quarantine/${STAMP}"
    compose down --remove-orphans
    mkdir -p "${QUARANTINE}"
    for name in postgres redpanda neo4j; do
      if [ -e "${DATA_ROOT}/${name}" ]; then
        mv "${DATA_ROOT}/${name}" "${QUARANTINE}/${name}"
      fi
      mkdir -p "${DATA_ROOT}/${name}"
    done
    echo "first_deploy_active_state_reset=true quarantine=${QUARANTINE}"
    ;;
  *)
    echo "usage: $0 [stop|first-deploy]" >&2
    exit 2
    ;;
esac
