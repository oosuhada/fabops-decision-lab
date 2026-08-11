#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for canonical verification" >&2
  exit 1
fi

exec uv run python -m evaluation.canonical_verify --output evidence/m6/canonical-verification.json
