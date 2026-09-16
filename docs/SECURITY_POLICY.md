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

## Trading authority (VATI)

Owner mandates, platform risk ceilings, the Risk Authority, kill switch, strategy registry and trading ledger are protected surfaces; writes require owner-signed authority. Forbidden A5 patterns include a model sending a broker order, bypassing the Risk Authority, removing or widening a protective stop, martingale/unlimited grid, revenge sizing, trading stale data or an unverified account, and placing a broker token in a prompt. Broker accounts appear only as aliases. The continuous-learning engine may only reduce (capsule health, regime probability, broker profile) and its boundary module is a protected surface; learning outputs that write mandates, widen risk, raise multipliers, promote strategies, self-admit knowledge, hold broker credentials in memory or treat memory as evidence are A5. Gateway trading writes (`/v1/trading/halt`, ticket confirmation) require the internal control token and an owner signature reference and only append ledger events. Broker credentials live only behind the account registry's credential reference (env var or 0600 secrets file) and are read by the transport at connect time; the MT5 bridge is mTLS + HMAC with a Windows worker that refuses orders without a stop and refuses stop widening; the trading commander on van-trading-core is a typed, HMAC-signed Hermes subordinate with allowlisted units and no shell. See `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md` Parts F, K and L and `docs/VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md` Parts B, D and H.

## Secrets

Never log or prompt-inject access/refresh tokens, API keys/client secrets, OTPs/passwords/private keys, full auth headers, service-account private keys, browser cookies/session tokens, MT5 logins/passwords, Deriv API tokens, or `VAN_INTERNAL_CONTROL_TOKEN`.

Workspace refresh tokens are encrypted at rest. Live Workspace calls exchange refresh tokens for short-lived access tokens inside the gateway. Neither token is forwarded to Hermes prompts.

## Prompt injection

Email, Drive, notifications, web, Notebook sources, Mixboard/Stitch artifacts, provider output and peer messages are labeled untrusted external data unless explicitly admitted through a higher authority process. Instructions inside them cannot escalate authority.

## Evidence and readiness

`CONFIGURED` is not proof of live success. Google capabilities may only be reported `READY` when a deterministic evidence pointer has been recorded. Provider artifacts remain untrusted evidence and cannot be labeled `OWNER_SIGNED`.
