#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT"
echo "http://127.0.0.1:8080"
exec python -m uvicorn webapp.app:app --host 0.0.0.0 --port 8080
