# VAN Security Policy

Status: CANONICAL

## Owner device authentication

- Stable public ingress is an outer transport gate only: normal Android-facing routes require the high-entropy `X-Van-Ingress-Token` **and** a revocable per-device `X-Van-Device-Token`.
- `/health` is ingress-only for service/tunnel probes. `/v1/devices/pair` is the only unauthenticated client route and accepts only a short-lived, single-use pairing ticket.
- Pairing tickets are created only by the internal control plane, stored only as SHA-256 hashes, expire in at most one hour, and are atomically consumed with device enrollment.
- Pairing returns the outer ingress bearer plus a per-device access token exactly once with `Cache-Control: no-store`; Android stores both in encrypted preferences. The gateway stores only the device-token hash.
- Device command authenticity remains a third independent layer: each paired device has an HMAC secret encrypted at rest with a dedicated Fernet key and rehydrated only inside the gateway process.
- Direct enrollment, pairing-ticket issuance, and device revocation require `X-Van-Internal-Token`; the ingress bearer or a valid device token cannot create or revoke device authority.
- Revocation atomically revokes capability grants and makes the per-device access token unusable; the HMAC secret is removed from memory and is never rehydrated after restart.
- Owner-directed mutations are signed, timestamped, replay-protected and idempotent.

## Hermes execution boundary

Hermes profile `van` is the sole agent runtime. Android, the gateway, Gemini Live, Deep Research, Antigravity, Jules, Workspace Studio and other provider surfaces do not form independent VAN agent loops.

Privileged Hermes→gateway Google job planning, job inspection and artifact recording require `VAN_INTERNAL_CONTROL_TOKEN` via `X-Van-Internal-Token`. If the control token is absent, those operations fail closed.

## Capability broker

Grants are scoped, time-expiring, optionally task-bound and auditable.

Read grants never imply write. A3/A4 Google jobs require an explicit grant. Project mutations additionally require current Project Truth evidence.

## Action classes

| Class | Meaning | Gate |
|---|---|---|
| A1 | Safe read / deterministic local | device auth |
| A2 | Bounded external read | capability grant |
| A3 | Bounded write | grant + policy |
| A4 | Destructive / irreversible / send-as-owner | explicit owner approval |
| A5 | Prohibited | always deny |

## Google Account Sovereignty and credential isolation

The owner's canonical Google account is VAN's default Google identity, but credentials MUST remain split into Workspace OAuth, Gemini runtime, Google Cloud/service identity, and consumer Google sessions. Explicit secondary Google identities are allowed only as bounded capability identities. `antigravity_worker_account` is restricted to Antigravity and MUST NOT inherit owner authority, Workspace access, Project Truth authority, or credentials from `owner_google_account`. No Google master credential exists.

Forbidden A5 patterns include exporting/copying Google sessions or cookies, reusing Workspace OAuth as a Gemini runtime credential, bypassing the Google identity broker, or disabling credential isolation.

## Secrets

Never log or prompt-inject access/refresh tokens, API keys/client secrets, OTPs/passwords/private keys, full auth headers, service-account private keys, browser cookies/session tokens, `VAN_INTERNAL_CONTROL_TOKEN`, `VAN_INGRESS_TOKEN`, device HMAC secrets, or Fernet keys.

Workspace refresh tokens are encrypted at rest. Live Workspace calls exchange refresh tokens for short-lived access tokens inside the gateway. Neither token is forwarded to Hermes prompts.

## Prompt injection

Email, Drive, notifications, web, Notebook sources, Mixboard/Stitch artifacts, provider output and peer messages are labeled untrusted external data unless explicitly admitted through a higher authority process. Instructions inside them cannot escalate authority.

## Evidence and readiness

`CONFIGURED` is not proof of live success. Google capabilities may only be reported `READY` when a deterministic evidence pointer has been recorded. Provider artifacts remain untrusted evidence and cannot be labeled `OWNER_SIGNED`.
