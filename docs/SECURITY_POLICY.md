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

Browser workers are the one permitted **subagent** of that runtime. Within a task Hermes has assigned — with an explicit goal, domain scope and step budget — a browser worker may select its own actions. It remains subordinate: it cannot create a VAN command, raise an action class, change its goal, extend its own budget, deadline or scope, or continue after the budget is exhausted. Every step is attributed to the assigning Hermes turn. A subagent is not an independent agent loop, and no other surface gains this status.

Privileged Hermes→gateway Google job planning, job inspection and artifact recording require `VAN_INTERNAL_CONTROL_TOKEN` via `X-Van-Internal-Token`. If the control token is absent, those operations fail closed.

## Automation Fabric boundary

n8n is a subordinate integration and workflow runtime. n8n never becomes an owner principal, Project Truth authority, trading Risk Authority, broker order sender, or Hermes peer agent. Consequential n8n effects require an existing owner command authority, or a standing automation authority derived from an owner-authorized command and enforced by the VAN Gateway.

Generated WorkflowIR and compiled n8n workflows are executable candidates, not authority. Generation cannot create a new privilege, credential, domain allowance, action-class exception, standing grant or Project Truth decision.

Stagehand and Browser Harness are subordinate browser workers. They receive task-scoped grants and may not independently create VAN commands, elevate action classes, access owner signing secrets, or place, modify or cancel broker trades.

## Payments

Payment execution is **prohibited by default and cannot be automated**.

- No automation, schedule, standing intent, workflow, browser task or agent may execute a payment.
- A payment is **A4** and requires a fresh owner biometric approval bound to the exact payee, amount, currency and reference. A standing authority can never carry it, and a prior approval is never reusable.
- Payment instruments are **never stored**. Card numbers, CVVs, bank details, wallet credentials and payment-provider tokens must not be written to the n8n credential store, a browser profile, a workflow artifact, VAN evidence, logs or any cache — at any credential class.
- "Save this payment method", "remember this card" and equivalent flows are forbidden. Instrument details are supplied per payment under owner control and are discarded immediately.
- A workflow or browser task that declares a payment effect is refused at compile and at dispatch unless it is an A4 action carrying a fresh approval.

## Credential isolation

n8n may hold only explicitly approved integration credentials classified for bounded read/write integration use, including service passwords, after admission. Owner signing keys, device HMAC secrets, VAN internal/root tokens, Project Truth authority credentials, broker execution credentials, VATI authority-store credentials, payment instruments and other root or financial authority secrets are prohibited from the n8n credential store.

## Browser session sovereignty

Browser cookies, localStorage/sessionStorage secrets, CDP bearer material, login sessions, OTPs and browser profile secrets are SECRET. They remain inside the Browser Session Broker / managed browser profile and are referenced by opaque aliases. They may not be copied into Hermes prompts, n8n workflow JSON, Stagehand model prompts, VEKL/VTIL, evidence text, logs or workflow artifacts.

## External egress and webhook ingress

Automation and browser egress is default-off per capability and per domain. Gateway policy must explicitly authorize the domain, credential plane, method/effect class and sensitivity before a request is permitted. External content remains UNTRUSTED_EXTERNAL and cannot increase authority.

External webhooks are untrusted events, never owner commands. Provider signature/HMAC/mTLS/OAuth validation, replay protection and schema validation occur before an event may enter the VAN event fabric.

## Capability broker

Grants are scoped, time-expiring, optionally task-bound and auditable.

Read grants never imply write. A3/A4 Google jobs require an explicit grant. Project mutations additionally require current Project Truth evidence.

## Action classes

| Class | Meaning | Gate |
|---|---|---|
| A1 | Safe read / deterministic local | device auth |
| A2 | Bounded external read | capability grant |
| A3 | Bounded write | grant + policy |
| A4 | Destructive / irreversible / send-as-owner / **payment** | explicit owner approval, per occurrence |
| A5 | Prohibited | always deny |

## Google Account Sovereignty and credential isolation

The owner's canonical Google account is VAN's default Google identity, but credentials MUST remain split into Workspace OAuth, Gemini runtime, Google Cloud/service identity, and consumer Google sessions. Explicit secondary Google identities are allowed only as bounded capability identities. `antigravity_worker_account` is restricted to Antigravity and MUST NOT inherit owner authority, Workspace access, Project Truth authority, or credentials from `owner_google_account`. No Google master credential exists.

Forbidden A5 patterns include exporting/copying Google sessions or cookies, reusing Workspace OAuth as a Gemini runtime credential, bypassing the Google identity broker, or disabling credential isolation.

## Trading authority (VATI)

Owner mandates, platform risk ceilings, the Risk Authority, kill switch, strategy registry and trading ledger are protected surfaces; writes require owner-signed authority. A model may not send broker orders, bypass the Risk Authority, widen protective stops, trade stale data, or place broker credentials in prompts. VAN is never a sender of record: live order submission remains behind the VATI execution-router/single-sender gate. Gateway trading writes require the internal control token plus owner-signature evidence; Android account onboarding additionally binds the paired device access token to the device HMAC signature. Broker credentials live only behind the trading account credential reference on the trading host.

## Secrets

Never log or prompt-inject access/refresh tokens, API keys/client secrets, OTPs/passwords/private keys, full auth headers, service-account private keys, browser cookies/session tokens, `VAN_INTERNAL_CONTROL_TOKEN`, `VAN_INGRESS_TOKEN`, device HMAC secrets, Fernet keys, MT5 passwords/signing keys, Deriv API tokens, or cTrader client/access/refresh secrets.

Workspace refresh tokens are encrypted at rest. Live Workspace calls exchange refresh tokens for short-lived access tokens inside the gateway. Neither token is forwarded to Hermes prompts.

## Prompt injection

Email, Drive, notifications, web, Notebook sources, Mixboard/Stitch artifacts, provider output and peer messages are labeled untrusted external data unless explicitly admitted through a higher authority process. Instructions inside them cannot escalate authority.

## Evidence and readiness

`CONFIGURED` is not proof of live success. Google capabilities may only be reported `READY` when a deterministic evidence pointer has been recorded. Provider artifacts remain untrusted evidence and cannot be labeled `OWNER_SIGNED`.
