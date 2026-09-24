#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${CHARACTER_FORGE_GPU_ROOT:-/opt/dial-character-forge-gpu}"
SEE_THROUGH_COMMIT="7f139bb25c46a0c8ac720d95ddab185fcda5451c"
WEIGHT_LOCK="${CHARACTER_FORGE_WEIGHT_LOCK:-/etc/van-character-forge/see-through-weights.lock.yaml}"
MODE="${CHARACTER_FORGE_GPU_MODE:-production}"

die(){ echo "[character-forge-gpu] ERROR: $*" >&2; exit 1; }
log(){ echo "[character-forge-gpu] $*"; }

[[ "$(id -u)" -eq 0 ]] || die "run as root"
command -v nvidia-smi >/dev/null || die "NVIDIA runtime missing"
nvidia-smi >/dev/null || die "GPU not usable"
command -v git >/dev/null || die "git missing"
command -v python3.12 >/dev/null || die "python3.12 required"

mkdir -p "$ROOT"
python3.12 -m venv "$ROOT/venv"
"$ROOT/venv/bin/pip" install --disable-pip-version-check --no-input "PyYAML==6.0.2"

if [[ "$MODE" == "production" ]]; then
  [[ -f "$WEIGHT_LOCK" ]] || die "production mode requires $WEIGHT_LOCK"
  "$ROOT/venv/bin/python" - "$WEIGHT_LOCK" <<'PY'
import hashlib, pathlib, re, sys, yaml
data=yaml.safe_load(open(sys.argv[1],encoding="utf-8")) or {}
if data.get("status")!="CLEARED":
    raise SystemExit("weight lock status is not CLEARED")
models=data.get("models") or []
if not models:
    raise SystemExit("weight lock has no models")
for row in models:
    expected=str(row.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}",expected):
        raise SystemExit("weight lock contains non-SHA256 model")
    if not str(row.get("license") or "").strip():
        raise SystemExit("weight lock contains model without licence")
    path=pathlib.Path(str(row.get("path") or ""))
    if not path.is_file():
        raise SystemExit(f"locked model is missing: {path}")
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024),b""):
            digest.update(chunk)
    if digest.hexdigest()!=expected:
        raise SystemExit(f"locked model hash mismatch: {path}")
PY
fi

if [[ ! -d "$ROOT/see-through/.git" ]]; then
  git clone https://github.com/shitagaki-lab/see-through.git "$ROOT/see-through"
fi
git -C "$ROOT/see-through" fetch --depth=1 origin "$SEE_THROUGH_COMMIT"
git -C "$ROOT/see-through" checkout --detach "$SEE_THROUGH_COMMIT"
[[ "$(git -C "$ROOT/see-through" rev-parse HEAD)" == "$SEE_THROUGH_COMMIT" ]] || die "commit pin failed"

"$ROOT/venv/bin/pip" install --disable-pip-version-check --no-input \
  --index-url https://download.pytorch.org/whl/cu128 \
  torch==2.8.0+cu128 torchvision==0.23.0+cu128 torchaudio==2.8.0+cu128
"$ROOT/venv/bin/pip" install --disable-pip-version-check --no-input \
  -r "$ROOT/see-through/requirements.txt"

cat > "$ROOT/worker.lock.json" <<EOF
{"see_through_commit":"$SEE_THROUGH_COMMIT","mode":"$MODE"}
EOF

log "GPU worker bootstrap complete. Model weights are governed by $WEIGHT_LOCK."
