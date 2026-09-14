# VAN Profile — Expected MCP Servers

Hermes profile **`van`** expects MCP tooling to be brokered through the Van secure gateway where credentials are involved. MCP servers listed here are **required for full capability**; if a server is unreachable, fail closed for operations that depend on it — do not simulate results.

## Core (Hermes host / gateway)

| Server | Purpose | Credential model |
|---|---|---|
| `van-gateway` | Owner auth envelope, capability grants, attention/reminders, health | Device-signed requests; no token passthrough to prompts |
| `filesystem` (scoped) | Repo reads/writes within registered project roots | Path allowlist from Project Truth + grants |
| `git` (scoped) | SHA/evidence capture, status, bounded diff | Read default; write requires grant |

## Google (gateway-mediated only)

| Server | Purpose | Notes |
|---|---|---|
| `google-gmail` | Bounded mail read/send | OAuth stays in gateway; A2 read / A4 send |
| `google-calendar` | Events read/write | Timezone from owner device |
| `google-drive` | File list/read/write | Content labeled untrusted_content |

**Never** configure raw Google OAuth tokens on Hermes MCP env for prompt access. See `docs/SECURITY_POLICY.md`.

## Communication

| Server | Purpose | Notes |
|---|---|---|
| `hermes-bot` | Bot Chat surfaces per `bot/BOT_CHAT.md` | Direct messaging always available fallback |
| `hermes-rooms` | Native group rooms for councils | Required for council mode; else fail closed |

## Diagnostics

| Server | Purpose |
|---|---|
| `hermes-admin` | Profile doctor signals, policy hook status |
| `process` / `shell` (restricted) | Infrastructure diagnostics only with explicit grant; no secret env dumps |

## Provider routing

| Server | Purpose |
|---|---|
| `gemini` | Google-centric research/generation via separate API credential — see `providers/gemini.md` |

Claude/Codex/GPT-SOL/Antigravity routes are Hermes-native model providers, not duplicated as MCP unless your Hermes deployment wraps them.

## Configuration checklist

1. MCP config lives on Hermes host — not committed with secrets
2. Each server has health probe used by `infrastructure-diagnostics` skill
3. Missing server → operations that need it return `DEGRADED` with explicit missing dependency
4. Councils: if `hermes-rooms` unavailable, use direct bot messaging only (`bot/councils.md`)

## References

- `hermes/profile/van/config.yaml`
- `hermes/skills/infrastructure-diagnostics/SKILL.md`
