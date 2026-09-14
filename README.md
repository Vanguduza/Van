# VAN

DIAL's owner-facing AI personal assistant and operator.

Hermes profile `van` owns agent execution. VAN provides Android embodiment, owner authority, deterministic attention/reminders, Google capability mediation, and a fail-closed secure gateway.

## Architecture

```text
Android owner device
        │
        ▼
Van floating assistant / Command Centre
        │
        ▼
Van secure gateway / owner-authority layer
        │
        ▼
DIAL Hermes profile: van
        ├── Claude / Codex / GPT-SOL / Gemini / Antigravity
        ├── skills / MCP / Bot Chat / message_agent
        ├── group rooms / councils
        └── registered projects (dial, dde, gtr, goat, aeci, van)
```

## Repository layout

| Path | Role |
|---|---|
| `android/` | Owner Android application |
| `backend/` | Secure gateway, authority, deterministic engines |
| `hermes/` | Profile `van` install pack (SOUL, skills, policy, MCP) |
| `visual-authority/` | Locked character identity and Rive contract |
| `docs/` | Canonical product authority |
| `registries/` | Project registrations and capability catalogs |
| `tests/` | Cross-cutting contract and acceptance tests |
| `tools/` | Bootstrap, release, certification scripts |

## Quick start

```bash
# Backend
cd backend && python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
uvicorn van_gateway.app:app --reload --port 8787

# Android (JDK 17 + Android SDK required)
cd android
./gradlew :app:assembleDebug :app:lintDebug

# Hermes profile install (on Hermes host)
./tools/hermes/install_van_profile.sh
```

## Non-negotiables

1. Hermes owns reasoning/tool/project execution.
2. Project Truth outranks chat memory.
3. Fail closed — never guess, mutate, or claim success without proof.
4. Visual identity is locked under `visual-authority/`.
5. OAuth tokens never enter LLM prompts.

## Version

See `VERSION` and `docs/RELEASE.md`.
