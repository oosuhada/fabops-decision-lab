#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${SCRIPT_DIR}/common.sh"

if [ "$#" -eq 0 ]; then
  set -- api web postgres redpanda neo4j
fi

compose logs --tail=200 "$@"
