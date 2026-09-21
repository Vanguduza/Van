#!/usr/bin/env bash
# Bootstrap Van gateway locally. Idempotent, fail-closed, secret-safe.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
# GAP-F-017 — install from the exact-pinned lock so a local bootstrap resolves the same
# dependency set CI and the release host do.
pip install -r requirements.lock
pytest -q
echo "VAN gateway bootstrap OK"
