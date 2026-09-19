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
| `VAN_INTERNAL_CONTROL_TOKEN` | Privileged Hermes→gateway control credential. Since P0-SEC-001 it carries every control scope **except** `device_enrolment`, so it can no longer mint a pairing ticket. Never prompt-visible |
| `VAN_INTERNAL_CONTROL_SCOPED_TOKENS` | Optional per-purpose credentials as `scope,scope:token; scope:token`. Scopes: `runtime`, `automation`, `browser`, `google`, `trading`, `projects`, `missions`, `understanding`, `device_enrolment`, `observability`. Prefer these over one shared token |
| `VAN_DEVICE_ENROLMENT_TOKEN` | The only credential that can mint a pairing ticket, enrol or revoke a device — that is, the only one that can produce owner-device authority. Deliberately **not** read by the Hermes MCP shim. Empty means device enrolment is unreachable, which is the correct state until an operator sets it |
| `VAN_INGRESS_TOKEN` | Outer high-entropy ingress bearer. Paired Android stores it encrypted; normal client APIs also require the separately revocable per-device token |
| `VAN_DEVICE_SECRET_FERNET_KEY` | Dedicated Fernet key for restart-durable encrypted device HMAC secrets |
| `VAN_GOOGLE_TOKEN_FERNET_KEY` | Fernet key for encrypted Workspace OAuth refresh tokens |
| `VAN_GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID used to exchange refresh tokens for access tokens |
| `VAN_GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret; never enters prompts |
| `VAN_GOOGLE_AI_PLAN` | Declared owner plan metadata; not proof of entitlement |
| `VAN_GOOGLE_CLOUD_PROJECT_ID` | Owner-administered Google Cloud project |
| `VAN_GOOGLE_GEMINI_RUNTIME_CONFIGURED` | `true` only when Hermes runtime credential is configured |
| `VAN_GOOGLE_CLOUD_RUNTIME_CONFIGURED` | `true` only when Cloud/service identity is configured |
| `VAN_GOOGLE_CONSUMER_CONNECTED_CAPABILITIES` | Comma-separated account surfaces configured on an authorised browser/device; still unverified until certified |
| `VAN_OBSERVABILITY_TOKEN` | The operator surface below. Its own credential, and **not** carried by `VAN_INTERNAL_CONTROL_TOKEN`: a command trace names device ids, command ids and failure reasons across the whole system, which is not something a model-driven runtime should read because it happens to be able to drive automation. Empty means the operator surface is unreachable |
| `VAN_LOG_LEVEL` | Level for the structured JSON logger. Default `INFO` |
| `VAN_SCHEDULER_ENABLED` | Whether due work actually runs. Default `true`; a reminder the owner set is not optional |
| `VAN_REMINDER_SWEEP_SECONDS` | How often due reminders are swept. Default `60` |
| `VAN_RETENTION_INTERVAL_SECONDS` | How often retention runs. Default `86400`; the horizons are in days |
| `VAN_PKI_DIR` | Bridge PKI directory to monitor for expiry. Empty means this deployment has no trading PKI, which is reported as absent rather than as expired |
| `VAN_PKI_SCAN_INTERVAL_SECONDS` | How often PKI expiry is re-read. Default `3600` |
| `VAN_BACKUP_DIR` | Where timestamped backups are written and read from. Empty means backups are not configured here, which the health surface distinguishes from stale |
| `VAN_BACKUP_ENABLED` | Whether the scheduler takes backups itself. Default `false`: on most hosts the backup belongs to a system job with an offsite target, and a backup on the same disk as the database is not a backup |

Google OAuth tokens, API keys, service credentials, browser cookies and session tokens never enter LLM prompts. Gemini uses a separate Hermes runtime credential.

## Android owner pairing

`POST /v1/devices/pairing-ticket` is internal-control-only and creates a short-lived single-use ticket. `POST /v1/devices/pair` consumes that ticket atomically with encrypted HMAC enrollment, owner-grant creation, and issuance of a per-device access token. The gateway persists only hashes of pairing/device-access tokens. Direct enroll/revoke routes remain internal-control-only.

Normal Android calls carry both `X-Van-Ingress-Token` and `X-Van-Device-Token`; command requests additionally carry the existing signed HMAC payload. `/health` intentionally requires only the ingress bearer so service/tunnel probes do not need a device identity.

## Observability and operations (Gate 11)

Five routes, four of them behind `VAN_OBSERVABILITY_TOKEN`:

| Route | Purpose |
|---|---|
| `GET /v1/observability/metrics` | Prometheus text format. Every metric Gate 11 names appears with its `HELP`/`TYPE` even before anything has observed it — a scrape that omits a metric means a broken exporter, not an idle subsystem. `van_metric_unobserved` names the declared metrics that have never received a sample, which is the difference between a metric at zero and a metric nobody writes |
| `GET /v1/observability/alerts` | The alert rules that are firing now, criticals first, each with the action an operator should take |
| `GET /v1/observability/health` | Scheduler state and last runs, PKI expiry, backup freshness, the audit chain's verification, and the list of silent instruments |
| `GET /v1/observability/trace/{command_id}` | The whole chain for one command — authority decisions, the mission and its timeline, activities, executions, receipts and the context snapshot — in one call. This is the join that previously meant opening SQLite and writing six of them by hand |
| `POST /v1/observability/device-telemetry` | Device-authenticated, not operator-authenticated. Aura frame time, wake/ASR/TTS latency and the battery and memory indicators are measured on the phone; the gateway cannot produce them and must not invent them. A metric name the catalogue does not declare is refused rather than registered |

Every command result carries a `correlation_id`, derived from the command id rather than
minted, so it is present on refusals too and can be quoted by an owner reporting a problem
before anything downstream has run.

### Backups

```
tools/ops/backup.py create  --database data/van_gateway.sqlite3 --into /backups
tools/ops/backup.py verify  /backups/<stamp>
tools/ops/backup.py restore /backups/<stamp> --database /tmp/restored.sqlite3
tools/ops/backup.py drill   --database data/van_gateway.sqlite3
```

Put `drill` in a cron. It takes a backup, restores it to a scratch location and compares
schema version, every table's row count and the audit chain tip, exiting non-zero on any
difference. That is how you find out backups have been writing an empty file for a month
*before* the day you need one.

The database backup uses SQLite's own backup API, not `cp`: the gateway runs in WAL mode
while serving requests, and copying the `.sqlite3` file without its `-wal` sidecar yields a
file that opens cleanly and is missing the most recent committed transactions.

### Retention

Every table carries a retention class, and `backend/tests/test_ops_retention.py` reads the
live schema and fails if a table has none — so the policy cannot fall behind the schema.
`OWNER_STATE` never prunes: the owner's record of their own life is not the system's to
expire, and deletion there goes through `/v1/context/memory`. The audit log is pruned only
as an anchored prefix, so `verify_chain` still reconciles over what remains and the anchor
records how much was removed.
