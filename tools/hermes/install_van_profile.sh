#!/usr/bin/env bash
# install_van_profile.sh — idempotent, fail-closed, secret-safe VAN Hermes profile installer
set -euo pipefail

PROFILE_NAME="van"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_ROOT="${REPO_ROOT}/hermes"

HERMES_BASE="${HERMES_HOME:-${HOME}/.hermes}"
TARGET_ROOT="${HERMES_BASE}/profiles/${PROFILE_NAME}"

SECRET_PATTERNS=(
  ".env"
  ".env.*"
  "*.pem"
  "*.p12"
  "*.key"
  "google-oauth-client.json"
  "gemini.env"
  "*credentials*"
  "*secret*"
  "*token*"
)

log() { printf '[install_van_profile] %s\n' "$*"; }
err() { printf '[install_van_profile] ERROR: %s\n' "$*" >&2; }
die() { err "$1"; exit 1; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }

verify_source_layout() {
  local missing=0
  local required=(
    "${SOURCE_ROOT}/VERSION"
    "${SOURCE_ROOT}/profile/van/SOUL.md"
    "${SOURCE_ROOT}/profile/van/AGENTS.md"
    "${SOURCE_ROOT}/profile/van/config.yaml"
    "${SOURCE_ROOT}/profile/van/bin/antigravity-worker"
    "${SOURCE_ROOT}/policy/van_policy_hook.py"
    "${SOURCE_ROOT}/bot/BOT_CHAT.md"
    "${SOURCE_ROOT}/mcp/README.md"
    "${SOURCE_ROOT}/mcp/owner_runtime_stdio.mjs"
    "${SOURCE_ROOT}/providers/gemini.md"
  )
  for f in "${required[@]}"; do
    if [[ ! -f "$f" ]]; then
      err "Missing source file: $f"
      missing=1
    fi
  done
  local skills=(
    owner-briefing google-workspace google-intelligence gemini-notebook google-design google-development
    project-steering research decision-support document-work notification-triage
    infrastructure-diagnostics hermes-administration trading-intelligence
    automation-fabric browser-intelligence jev-management
  )
  for s in "${skills[@]}"; do
    if [[ ! -f "${SOURCE_ROOT}/skills/${s}/SKILL.md" ]]; then
      err "Missing skill: ${SOURCE_ROOT}/skills/${s}/SKILL.md"
      missing=1
    fi
  done
  [[ "$missing" -eq 0 ]] || die "Source layout verification failed — aborting install"
}

copy_tree() {
  require_cmd rsync
  local excludes=()
  for pat in "${SECRET_PATTERNS[@]}"; do excludes+=(--exclude="$pat"); done
  mkdir -p "${TARGET_ROOT}"

  for file in SOUL.md AGENTS.md config.yaml; do
    rsync -a "${excludes[@]}" "${SOURCE_ROOT}/profile/van/${file}" "${TARGET_ROOT}/${file}"
  done
  mkdir -p "${TARGET_ROOT}/bin"
  rsync -a --delete "${excludes[@]}" "${SOURCE_ROOT}/profile/van/bin/" "${TARGET_ROOT}/bin/"

  mkdir -p "${TARGET_ROOT}/skills"
  local managed_skills=(
    owner-briefing google-workspace google-intelligence gemini-notebook google-design google-development
    project-steering research decision-support document-work notification-triage
    infrastructure-diagnostics hermes-administration trading-intelligence
    automation-fabric browser-intelligence
  )
  for skill in "${managed_skills[@]}"; do
    mkdir -p "${TARGET_ROOT}/skills/${skill}"
    rsync -a --delete "${excludes[@]}" "${SOURCE_ROOT}/skills/${skill}/" "${TARGET_ROOT}/skills/${skill}/"
  done
  for dir in policy bot mcp providers; do
    mkdir -p "${TARGET_ROOT}/${dir}"
    rsync -a --delete "${excludes[@]}" "${SOURCE_ROOT}/${dir}/" "${TARGET_ROOT}/${dir}/"
  done
  cp -f "${SOURCE_ROOT}/VERSION" "${TARGET_ROOT}/VERSION"
}

verify_target_layout() {
  local missing=0
  local required=(
    "${TARGET_ROOT}/SOUL.md"
    "${TARGET_ROOT}/AGENTS.md"
    "${TARGET_ROOT}/config.yaml"
    "${TARGET_ROOT}/bin/antigravity-worker"
    "${TARGET_ROOT}/VERSION"
    "${TARGET_ROOT}/policy/van_policy_hook.py"
    "${TARGET_ROOT}/bot/BOT_CHAT.md"
    "${TARGET_ROOT}/bot/councils.md"
    "${TARGET_ROOT}/mcp/README.md"
    "${TARGET_ROOT}/mcp/owner_runtime_stdio.mjs"
    "${TARGET_ROOT}/providers/gemini.md"
  )
  for f in "${required[@]}"; do
    if [[ ! -f "$f" ]]; then
      err "Missing after install: $f"
      missing=1
    fi
  done
  if ! grep -q 'profile: van' "${TARGET_ROOT}/config.yaml" 2>/dev/null; then
    err "config.yaml does not declare profile: van"
    missing=1
  fi
  if ! grep -qi 'Project Truth' "${TARGET_ROOT}/SOUL.md" 2>/dev/null; then
    err "SOUL.md missing Project Truth authority reference"
    missing=1
  fi
  if ! grep -q 'context_graph_query' "${TARGET_ROOT}/mcp/owner_runtime_stdio.mjs" 2>/dev/null; then
    err "owner-runtime MCP shim missing canonical context tool surface"
    missing=1
  fi
  [[ "$missing" -eq 0 ]] || die "Post-install verification failed — install is incomplete"
}

main() {
  log "VAN Hermes profile installer (profile=${PROFILE_NAME})"
  log "Source: ${SOURCE_ROOT}"
  log "Target: ${TARGET_ROOT}"

  [[ -d "${SOURCE_ROOT}" ]] || die "Hermes pack not found at ${SOURCE_ROOT} — run from VAN repo"
  verify_source_layout
  mkdir -p "${HERMES_BASE}/profiles"
  copy_tree
  verify_target_layout

  log "Install complete: ${TARGET_ROOT}"
  log "Register owner runtime MCP: ${SCRIPT_DIR}/register_owner_runtime_mcp.sh"
  log "Verify with: ${SCRIPT_DIR}/doctor_van_profile.sh"
}

main "$@"
