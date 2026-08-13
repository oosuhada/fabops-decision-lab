#!/usr/bin/env bash
set -euo pipefail

SSH_HOST="${FABOPS_LOCAL_LLM_SSH_HOST:-macbook-pro}"
LOCAL_PORT="${FABOPS_LOCAL_LLM_TUNNEL_PORT:-12345}"
REMOTE_PORT="${FABOPS_LOCAL_LLM_REMOTE_PORT:-1234}"

if /usr/bin/nc -z 127.0.0.1 "${LOCAL_PORT}" >/dev/null 2>&1; then
  echo "FabOps local LLM tunnel already reachable on 127.0.0.1:${LOCAL_PORT}"
  exit 0
fi

/usr/bin/ssh \
  -f \
  -N \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
  "${SSH_HOST}"

if ! /usr/bin/nc -z 127.0.0.1 "${LOCAL_PORT}" >/dev/null 2>&1; then
  echo "FabOps local LLM tunnel did not become reachable" >&2
  exit 1
fi

echo "FabOps local LLM tunnel ready: 127.0.0.1:${LOCAL_PORT} -> ${SSH_HOST}:127.0.0.1:${REMOTE_PORT}"
