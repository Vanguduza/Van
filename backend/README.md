# VAN Gateway

Secure owner-authority layer in front of Hermes profile `van`.

Hermes remains the sole agent runtime. The gateway authenticates owner intent, brokers capability grants, isolates credentials, records evidence, and exposes deterministic Google capability planning.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
pytest
uvicorn van_gateway.app:app --port 8787
```

## Google Account Sovereignty

VAN uses `owner_google_account` as its canonical/default Google identity. Explicit delegated identities may be bound to individual capabilities without inheriting owner authority or credentials. Antigravity is bound to `antigravity_worker_account`; every other Google capability defaults to `owner_google_account`.

Do not create or configure a single Google "master credential". The supported credential planes are:

1. Workspace OAuth — Gmail, Calendar, Drive, Contacts and Tasks.
2. Gemini runtime — Gemini, Gemini Live, Deep Research, Nano Banana and Veo.
3. Google Cloud/service identity — Cloud APIs and Gemini Notebook Enterprise.
4. Consumer session — account-native surfaces such as Gemini Notebook, Mixboard, Stitch, Antigravity, Jules, Flow and AI Studio.

Consumer-session configuration is never equivalent to live certification. A capability is `READY` only after deterministic evidence is recorded.

See `../docs/GOOGLE_INTELLIGENCE_MESH.md`.

## Environment

| Variable | Purpose |
|---|---|
| `VAN_DATABASE_PATH` | SQLite path |
| `VAN_HERMES_BASE_URL` | Hermes gateway |
| `VAN_HERMES_BEARER_TOKEN` | Hermes API token |
| `VAN_INTERNAL_CONTROL_TOKEN` | Shared secret for privileged Hermes→gateway Google job/evidence APIs; never prompt-visible |
| `VAN_INGRESS_TOKEN` | Owner-device bearer required on externally reachable gateway routes; stored encrypted on Android |
| `VAN_DEVICE_SECRET_FERNET_KEY` | Dedicated Fernet key for restart-durable encrypted device HMAC secrets |
| `VAN_GOOGLE_TOKEN_FERNET_KEY` | Fernet key for encrypted Workspace OAuth refresh tokens |
| `VAN_GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID used to exchange refresh tokens for access tokens |
| `VAN_GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret; never enters prompts |
| `VAN_GOOGLE_AI_PLAN` | Declared owner plan metadata; not proof of entitlement |
| `VAN_GOOGLE_CLOUD_PROJECT_ID` | Owner-administered Google Cloud project |
| `VAN_GOOGLE_GEMINI_RUNTIME_CONFIGURED` | `true` only when Hermes runtime credential is configured |
| `VAN_GOOGLE_CLOUD_RUNTIME_CONFIGURED` | `true` only when Cloud/service identity is configured |
| `VAN_GOOGLE_CONSUMER_CONNECTED_CAPABILITIES` | Comma-separated account surfaces configured on an authorised browser/device; still unverified until certified |

Google OAuth tokens, API keys, service credentials, browser cookies and session tokens never enter LLM prompts. Gemini uses a separate Hermes runtime credential.
