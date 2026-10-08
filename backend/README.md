# VAN Gateway

Secure owner-authority layer in front of Hermes profile `van`.

Selected estate placement: this backend runs on private `van-trading-core`; Hermes profile
`van` and ARTEMIS run on `dial-control`. The phone uses a separately admitted VAN-only
end-to-end TLS passthrough on `oracle-admin`. The exact public URI and CA are deployment
inputs. See [the owner-core recipe](../deploy/van-owner-core/README.md); the historical
Netcup APK address and the limited DDS development proxy do not qualify this connection.

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

The authorized installer supplies a short-lived signed connection envelope; the app enters
no connection settings. Bootstrap challenge/attestation validates a pinned Google Android
attestation chain, release signer, package and fresh hardware-key proof. Pairing consumes
the exact operator-issued ticket and binding atomically, with encrypted HMAC enrollment,
owner grant and revocable per-device token. Only hashes of bootstrap/pairing/access tokens
persist. Lost bootstrap/pairing replies recover the same attempt through exact token hashes
and fresh proofs; they do not mint replacement authority. Direct enrollment/revocation and
provisioning-status observation remain under the separate operator enrollment scope.

Normal Android calls carry both `X-Van-Ingress-Token` and `X-Van-Device-Token`. Every owner
POST/PUT/PATCH/DELETE requires fresh hardware-key proof over method, exact path/query, time
and serialized body; nonces are durable. Command requests additionally carry their sealed
command authority. `/health` requires the ingress bearer and only establishes process
readiness; Hermes execution and a phone connection require their own evidence.

## Direct phone link (mutual TLS)

The phone's TLS terminates at this gateway on private `van-trading-core`. A dedicated,
governed VAN-only oracle-admin TCP passthrough preserves the original TLS connection and
client certificate; it cannot use a TLS-terminating HTTP proxy or forwarded certificate
headers. TLS 1.3 carries the app's HTTPS calls and its two-way session WebSocket
(`/v1/session/ws`, 20 s keepalive, resume by sequence number).

- **Both ends authenticate.** The server certificate and every phone's client certificate come
  from a private VAN device CA. The app pins that CA (`VAN_GATEWAY_CA_PEM_B64` at build time)
  and trusts no public CA on this link. The phone's key is generated in the Android Keystore
  and never leaves it; the phone sends a CSR to `POST /v1/devices/tls-certificate` after its
  device proof, and the gateway signs it for that device only.
- **The certificate is bound to the device token.** A certificate for one device cannot carry
  another device's token (403 `client_certificate_device_mismatch`; WebSocket close 4403).
- **Revocation is immediate.** `POST /v1/devices/{id}/revoke` also revokes the device's
  certificates. `issued.json` is the authority, checked on every request, and fails closed.
- **Without a certificate**, only pairing, bootstrap, certificate enrolment and the two
  browser surfaces that carry their own credential answer. The WebSocket always needs one.
- **The loopback listener** (`127.0.0.1:8787`) remains local. A source-restricted WireGuard
  relay admits `dial-control` only on core `10.77.0.4:8787`, while per-purpose control tokens
  authenticate Hermes callbacks/MCP. Gateway-to-Hermes uses the separately measured profile
  API on the private control peer. The DDS typed development proxy is a different lane.

Enable it on the host (idempotent; it keeps an existing CA):

```bash
tools/runtime/install_van_gateway_service.sh   # production needs exact clean source SHA
tools/runtime/enable_van_mtls.sh --bind 10.77.0.4 --san DNS:<approved-phone-ingress-name>
```

The last line it prints is the CA certificate, base64-encoded. It is public. The app pins
it together with the exact approved HTTPS ingress URL through the generated external
Android deployment profile. Release builds reject the historical committed fallback; no
credentials enter the APK. The helper changes no firewall rules: the governed deployment
recipe supplies exact private source/port rules and the separately admitted ingress.
An upgrade preserves device identity and encrypted state. The CA key stays
in `~/.local/share/van/mtls` (mode 0700) and is never printed. Revoke by device with
`python -m van_gateway.mtls.pki revoke --dir ~/.local/share/van/mtls --device-id <id>`.

Browser/account surfaces need their own qualified browser trust route. The phone's private
CA does not establish a publicly trusted browser session or authorize moving those routes.

## DIAL development projection

`VAN_DIAL_DEV_ENABLED=false` is the owner-core default. Enabling the independently qualified
DEC-056 limited product proxy requires `VAN_DIAL_DEV_BASE_URL=https://10.77.0.2:8443`,
`VAN_DIAL_DEV_TOKEN_FILE`, `VAN_DIAL_DEV_TLS_CA_FILE`, `VAN_DIAL_DEV_TLS_CLIENT_CERT_FILE`
and `VAN_DIAL_DEV_TLS_CLIENT_KEY_FILE` (private key mode 0600). Production requires TLS 1.3,
hostname verification and client identity for GET and SSE, refuses direct control HTTP or
incomplete TLS, and has no fallback. This does not provide the phone/Hermes WebSocket lane.

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
expire. Owner-memory erasure goes through the signed A4 command pipeline with explicit
scope and fresh biometric approval; direct `DELETE /v1/context/memory` refuses it. The audit log is pruned only
as an anchored prefix, so `verify_chain` still reconciles over what remains and the anchor
records how much was removed.
