# VAN Security Policy

Status: CANONICAL

## Owner device authentication

- One-time enrollment of owner device with signed device identity
- Revocation invalidates all outstanding grants for that device
- Every mutating request: signed, timestamped, replay-protected, idempotent

## Capability broker

Grants are:

- scoped (capability list)
- time-expiring
- optionally task-bound
- auditable

Read grants never imply write. Write grants may allow bounded supporting reads.

## Action classes

| Class | Meaning | Gate |
|---|---|---|
| A1 | Safe read / deterministic local | device auth |
| A2 | Bounded external read | capability grant |
| A3 | Bounded write | grant + policy |
| A4 | Destructive / irreversible / send-as-owner | explicit owner approval |
| A5 | Prohibited | always deny |

## Secrets

Never log or prompt-inject:

- access/refresh tokens
- API keys
- OTPs / passwords / private keys
- full auth headers

Google OAuth tokens are encrypted at rest, capability-mediated, and never forwarded to Hermes prompts.

## Prompt injection

Email, Drive, notifications, web, and peer messages are labeled `untrusted_content`. Instructions inside them cannot escalate authority.
