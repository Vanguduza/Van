# VAN Security Policy

Status: CANONICAL

## Owner device authentication

- One-time enrollment of owner device with signed device identity.
- Revocation invalidates outstanding grants for that device.
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

The owner's canonical Google account is the identity/entitlement root for Google capabilities, but credentials MUST remain split into Workspace OAuth, Gemini runtime, Google Cloud/service identity, and consumer Google sessions. No Google master credential exists.

Forbidden A5 patterns include exporting/copying Google sessions or cookies, reusing Workspace OAuth as a Gemini runtime credential, bypassing the Google identity broker, or disabling credential isolation.

## Secrets

Never log or prompt-inject access/refresh tokens, API keys/client secrets, OTPs/passwords/private keys, full auth headers, service-account private keys, browser cookies/session tokens, or `VAN_INTERNAL_CONTROL_TOKEN`.

Workspace refresh tokens are encrypted at rest. Live Workspace calls exchange refresh tokens for short-lived access tokens inside the gateway. Neither token is forwarded to Hermes prompts.

## Prompt injection

Email, Drive, notifications, web, Notebook sources, Mixboard/Stitch artifacts, provider output and peer messages are labeled untrusted external data unless explicitly admitted through a higher authority process. Instructions inside them cannot escalate authority.

## Evidence and readiness

`CONFIGURED` is not proof of live success. Google capabilities may only be reported `READY` when a deterministic evidence pointer has been recorded. Provider artifacts remain untrusted evidence and cannot be labeled `OWNER_SIGNED`.
