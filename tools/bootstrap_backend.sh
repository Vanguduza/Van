#!/usr/bin/env bash
# Bootstrap Van gateway locally. Idempotent, fail-closed, secret-safe.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
echo "VAN gateway bootstrap OK"
