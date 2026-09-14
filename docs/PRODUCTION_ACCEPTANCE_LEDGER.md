# Production Acceptance Ledger

**Version under test:** 0.5.0-dev  
**Date:** 2026-09-14  
**Verdict:** NOT v1.0 PRODUCTION ACCEPTED — external gates remain

## Repository gates

| Gate | Status |
|---|---|
| No fake success paths for Hermes/Google offline | PASS (fail closed) |
| Backend suite | PASS |
| Cross-cutting contracts/scenarios/hermes | PASS |
| Android assembleDebug | PASS |
| Android lintDebug | PASS |
| Android unit tests | PASS |
| Visual authority contract tests | PASS |
| Owner escalation / decisions API | PASS |
| Reminder time-expression parse | PASS |
| Project Truth put/sync tooling | PASS (van local dry-run OK; other projects fail closed without truth files) |
| Google fake-transport + A4 send gate | PASS |
| Migration idempotent | PASS |
| SBOM / provenance / checksums | PASS (artifacts/release) |
| Clean tree on main | PASS after push |

## External gates (blocking v1.0)

| Gate | Status |
|---|---|
| Prior history recovery (v0.4.0-local / VA commits) | UNAVAILABLE |
| Live Hermes profile install + Bot Mode cert | BLOCKED (SSH timeout) |
| Google OAuth live cert | BLOCKED (no credentials) |
| Gemini separate credential cert | BLOCKED |
| Physical Samsung certification + soak | BLOCKED (adb: no device) |
| Artist `.riv` + owner visual acceptance | BLOCKED |
| Live Project Truth for dial/dde/gtr/goat/aeci | BLOCKED (no truth files in those trees) |
| Signed production release keystore | BLOCKED (docs + gradle wiring ready; keystore not present) |
| GitHub Actions workflow path | BLOCKED (OAuth lacks `workflow` scope; canonical YAML in `tools/ci/`) |

## Tag policy

Do **not** tag `v1.0` until every applicable gate above is green. Current tag: `v0.5.0-dev`.
