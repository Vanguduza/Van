#!/usr/bin/env bash
# doctor_van_profile.sh — read-only verification of installed van profile (no mutations)
set -euo pipefail

PROFILE_NAME="van"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_ROOT="${REPO_ROOT}/hermes"

HERMES_BASE="${HERMES_HOME:-${HOME}/.hermes}"
TARGET_ROOT="${HERMES_BASE}/profiles/${PROFILE_NAME}"

log() { printf '[doctor_van_profile] %s\n' "$*"; }
warn() { printf '[doctor_van_profile] WARN: %s\n' "$*" >&2; }
err() { printf '[doctor_van_profile] ERROR: %s\n' "$*" >&2; }

FAIL=0

check_file() {
  local path="$1"
  local label="${2:-$path}"
  if [[ -f "$path" ]]; then
    log "OK  $label"
  else
    err "MISSING  $label ($path)"
    FAIL=1
  fi
}

check_grep() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if [[ -f "$file" ]] && grep -qE "$pattern" "$file"; then
    log "OK  $label"
  else
    err "FAIL  $label ($file)"
    FAIL=1
  fi
}

main() {
  log "VAN Hermes profile doctor (read-only)"
  log "HERMES_HOME base: ${HERMES_BASE}"
  log "Installed profile path: ${TARGET_ROOT}"
  log "Repo pack (reference): ${SOURCE_ROOT}"

  if [[ ! -d "${TARGET_ROOT}" ]]; then
    err "Profile directory not found — run install_van_profile.sh first"
    exit 1
  fi

  # Core profile files
  check_file "${TARGET_ROOT}/SOUL.md" "SOUL.md"
  check_file "${TARGET_ROOT}/AGENTS.md" "AGENTS.md"
  check_file "${TARGET_ROOT}/config.yaml" "config.yaml"
  check_file "${TARGET_ROOT}/VERSION" "VERSION"

  check_grep "${TARGET_ROOT}/config.yaml" '^profile: van' "config profile name is van"
  check_grep "${TARGET_ROOT}/SOUL.md" 'Project Truth' "SOUL mentions Project Truth"
  check_grep "${TARGET_ROOT}/SOUL.md" 'Owner-signed instruction' "SOUL authority order present"

  # Policy
  check_file "${TARGET_ROOT}/policy/van_policy_hook.py" "policy hook"
  check_file "${TARGET_ROOT}/policy/tests/test_van_policy_hook.py" "policy tests"

  # Bot
  check_file "${TARGET_ROOT}/bot/BOT_CHAT.md" "BOT_CHAT.md"
  check_file "${TARGET_ROOT}/bot/message_agent.md" "message_agent.md"
  check_file "${TARGET_ROOT}/bot/councils.md" "councils.md"
  check_grep "${TARGET_ROOT}/bot/councils.md" 'fail closed' "councils fail-closed documented"

  # MCP / providers
  check_file "${TARGET_ROOT}/mcp/README.md" "mcp README"
  check_file "${TARGET_ROOT}/providers/gemini.md" "gemini provider doc"

  # Skills
  local skills=(
    owner-briefing google-workspace google-intelligence gemini-notebook google-design google-development
    project-steering research decision-support document-work notification-triage
    infrastructure-diagnostics hermes-administration
  )
  for s in "${skills[@]}"; do
    check_file "${TARGET_ROOT}/skills/${s}/SKILL.md" "skill ${s}"
  done

  # The live profile intentionally owns a root .env credential file. It must
  # remain private; managed static subtrees must never contain credential files.
  if [[ -f "${TARGET_ROOT}/.env" ]]; then
    local env_mode
    env_mode="$(stat -c '%a' "${TARGET_ROOT}/.env" 2>/dev/null || printf 'unknown')"
    if [[ "${env_mode}" == "600" ]]; then
      log "OK  root .env present with mode 600"
    else
      err "FAIL  root .env permissions must be 600 (got ${env_mode})"
      FAIL=1
    fi
  else
    warn "root .env not present; provider credentials may be supplied by another approved secret source"
  fi
  if find "${TARGET_ROOT}/bin" "${TARGET_ROOT}/skills" "${TARGET_ROOT}/policy" "${TARGET_ROOT}/bot" "${TARGET_ROOT}/mcp" "${TARGET_ROOT}/providers" -type f \( -name '.env' -o -name 'gemini.env' -o -name 'google-oauth-client.json' \) 2>/dev/null | grep -q .; then
    err "Secret-like files found inside managed profile content"
    FAIL=1
  else
    log "OK  no credential filenames in managed profile content"
  fi

  # Optional: repo layout test hint
  if [[ -f "${REPO_ROOT}/tests/hermes/test_profile_layout.py" ]]; then
    log "Hint: pytest ${REPO_ROOT}/tests/hermes/test_profile_layout.py"
  fi

  if [[ "$FAIL" -ne 0 ]]; then
    err "Doctor found problems — profile is not healthy"
    exit 1
  fi

  log "All checks passed"
}

main "$@"
