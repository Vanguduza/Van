# Production Acceptance Ledger

**Version under test:** 0.5.0-dev  
**Date:** 2026-09-14  
**Verdict:** NOT v1.0 PRODUCTION ACCEPTED — external gates remain

## Repository gates

| Gate | Status |
|---|---|
| No fake success paths for Hermes/Google offline | PASS (fail closed) |
| Backend suite | PASS (14 backend tests incl. speech) |
| Cross-cutting contracts/scenarios/hermes | PASS (39 total python tests in aggregate run) |
| Android assembleDebug | PASS |
| Android lintDebug | PASS |
| Android unit tests | PASS |
| Visual authority contract tests | PASS |
| SBOM / provenance / checksums | PASS (artifacts/release) |
| Clean tree after commit | pending commit |

## External gates (blocking v1.0)

| Gate | Status |
|---|---|
| Prior history recovery (v0.4.0-local / VA commits) | UNAVAILABLE |
| Live Hermes profile install + Bot Mode cert | BLOCKED (SSH timeout) |
| Google OAuth live cert | BLOCKED (no credentials) |
| Gemini separate credential cert | BLOCKED |
| Physical Samsung certification + soak | BLOCKED (no device run this session) |
| Artist `.riv` + owner visual acceptance | BLOCKED |
| Live Project Truth mounts for dial/dde/gtr/goat/aeci | BLOCKED |
| Signed production release keystore | BLOCKED |

## Tag policy

Do **not** tag `v1.0` until every applicable gate above is green. Current development tag candidate after push: `v0.5.0-dev`.
