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
        ├── Google Intelligence Mesh
        │     ├── Gemini Live / Deep Research
        │     ├── Gemini Notebook
        │     ├── Mixboard / Stitch
        │     ├── Antigravity / Jules
        │     ├── Workspace APIs / Studio
        │     └── Nano Banana / Veo / Flow / ADK-A2A
        ├── skills / MCP / Bot Chat / message_agent
        ├── group rooms / councils
        └── registered projects (dial, dde, gtr, goat, aeci, van)
```

## Google Account Sovereignty

All Google capabilities used by VAN trace ownership, entitlement, delegated access, or Cloud administration to the owner's canonical Google account.

Credentials remain compartmentalized into Workspace OAuth, Gemini runtime, Google Cloud/service identity, and consumer-session planes. There is no Google master credential. Hermes remains the sole agent runtime.

Canonical specification: `docs/GOOGLE_INTELLIGENCE_MESH.md`.

## Repository layout

| Path | Role |
|---|---|
| `android/` | Owner Android application |
| `backend/` | Secure gateway, authority, deterministic engines and Google broker |
| `hermes/` | Profile `van` install pack (SOUL, skills, policy, MCP/providers) |
| `visual-authority/` | Locked character identity and Rive contract |
| `docs/` | Canonical product authority |
| `registries/` | Projects and Google capability catalogs |
| `tests/` | Cross-cutting contract and acceptance tests |
| `tools/` | Bootstrap, Google setup/certification, release and certification scripts |
| `trading/` | VAN Adaptive Trading Intelligence (VATI): deterministic Risk Authority, contracts and tests — see `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md` and `..._REV3.md` (incl. Zimbabwe Stock Exchange module) |

## Quick start

```bash
# Backend
cd backend && python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
uvicorn van_gateway.app:app --reload --port 8787

# Register owner Google principal (raw subject is hashed before persistence)
python ../tools/google/configure_google_identity.py --subject "<google-subject>"

# Inspect Google mesh readiness
python ../tools/google/certify_google_mesh.py

# Android (JDK 17 + Android SDK required)
cd ../android
./gradlew :app:assembleDebug :app:lintDebug

# Hermes profile install (on Hermes host)
./tools/hermes/install_van_profile.sh
```

## Non-negotiables

1. Hermes owns reasoning/tool/project execution.
2. Project Truth outranks chat memory and Google-generated output.
3. Fail closed — never guess, mutate, or claim success without proof.
4. Visual identity is locked under `visual-authority/`.
5. OAuth/API/service/session credentials never enter LLM prompts.
6. `CONFIGURED` is not `READY`; live Google claims require evidence.
7. No model sends a broker order. Trading size comes only from the deterministic Risk Authority under an owner-signed mandate; `NO_TRADE` is a valid outcome.

## Version

See `VERSION` and release/acceptance documentation.
