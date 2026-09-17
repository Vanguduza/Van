# VAN Profile — Expected MCP / Capability Servers

Hermes profile **`van`** is the sole agent runtime. Credentials are brokered through the VAN gateway or provider runtime; raw secrets never enter prompts. A missing server/capability fails closed.

## Core

| Server | Purpose | Credential model |
|---|---|---|
| `van_owner_runtime` | Deterministic owner-context readiness/graph/snapshot, typed resolution, research routing and action lifecycle verification | Local Hermes internal-control credential; fixed tool allowlist; no generic HTTP; no canonical-memory admission |
| `van-gateway` | Owner auth, grants, Google planner, evidence, attention/reminders, health | Device-signed; no secret passthrough |
| `filesystem` (scoped) | Registered project files | Path allowlist + Project Truth + grants |
| `git` (scoped) | SHA/evidence/diff/write | Read default; writes require grant |

### `van_owner_runtime`

The canonical stdio shim is `hermes/mcp/owner_runtime_stdio.mjs`. Register it into the live Hermes config with:

```bash
./tools/hermes/register_owner_runtime_mcp.sh --dry-run
./tools/hermes/register_owner_runtime_mcp.sh
```

The registration script reads no secret into YAML. The shim obtains `VAN_INTERNAL_CONTROL_TOKEN` from the existing local gateway environment (default `~/.config/van/gateway.env`) or an explicitly configured local token file. The token is used only as `X-Van-Internal-Token` and is never emitted as tool output.

Allowed tools are deliberately narrow:

- `runtime_status`
- `resolve_command`
- `context_graph_query`
- `context_readiness`
- `context_snapshot`
- `research_status`
- `research_search`
- `action_begin`
- `action_submitted`
- `action_verify`
- `action_get`

There is **no** generic HTTP/shell tool and no fact/edge canonical-admission tool. Hermes is not a truth authority. Any Hermes-originated memory candidate reaching the internal runtime API is forced to `MODEL_DERIVED + INFERRED`; owner/canonical promotion requires a separate trusted gateway/owner path.

The context graph is a bounded temporal retrieval primitive, not an autonomous GraphRAG loop. Exact facts remain ahead of graph retrieval in the critical path; external research remains an escalation.

## Trading (van-trading-core)

| Server | Purpose | Credential model |
|---|---|---|
| `van_trading_commander` | Hermes subordinate on the trading VM: status, ledger, services, bounded log tail, bounded backtest, trading-VEKL resolve, owner-signed halt, doctor, accounts | HMAC-signed requests with a 0600 token file; no shell, no file writes, no order path; account-credential commands are hidden from MCP and refused for agent requesters |

The commander reaches the dedicated trading VEKL (`trading/vekl`, loopback :9134 on the VM) and the VATI ledger. It cannot place, size, modify or cancel an order; halting is the only trading effect and it needs an owner signature reference (A4). Registration is spliced into `~/.hermes/config.yaml` by `deploy/van-trading-core/hermes/register-commander-mcp.sh`.

## Google Workspace — gateway mediated

| Capability | Purpose | Gate |
|---|---|---|
| `google-gmail` | Mail read/draft/send | A2 read; A4 send |
| `google-calendar` | Events read/write | A2/A3; irreversible/external effects as A4 |
| `google-drive` | File metadata/content | External content is untrusted |
| `google-contacts` | Contact resolution | A2 |
| `google-tasks` | Task reads/writes | A2/A3 |

Workspace refresh tokens are encrypted in the gateway and exchanged for short-lived access tokens before API calls. Neither token is visible to Hermes prompts.

## Google intelligence mesh

The canonical capability registry is `registries/google_capabilities.json`. Hermes requests deterministic plans through the VAN gateway before invoking Google specialists.

| Capability | Role | Credential plane |
|---|---|---|
| `gemini` | Reasoning/multimodal | Gemini runtime |
| `gemini_live` | Live voice/screen perception | Gemini runtime |
| `deep_research` | Cited autonomous investigation | Gemini runtime |
| `gemini_notebook` | Personal source-grounded research | Consumer session |
| `gemini_notebook_enterprise` | Programmatic notebook/source lifecycle | Google Cloud/service |
| `mixboard` | Divergent visual ideation | Consumer session |
| `stitch` | UI design convergence | Consumer session |
| `antigravity` | Complex development worker | Consumer/developer session |
| `jules` | Bounded GitHub maintenance worker | Consumer/developer session |
| `workspace_api` | Deterministic Workspace actions | Workspace OAuth |
| `workspace_studio` | Multi-step Workspace-native workflows | Consumer session |
| `nano_banana` | Image generation/editing | Gemini runtime |
| `veo` | Video generation | Gemini runtime |
| `flow` | Human-facing video creative surface | Consumer session |
| `ai_studio` | Google model prototyping | Consumer session |
| `a2a_adk` | External Google-agent interoperability | Cloud/service |

A configured consumer session is not automatically `READY`. Recorded certification evidence is required before VAN claims successful live use.

## Provider routing

Gemini is a Hermes provider route, not a second assistant. Antigravity/Jules are workers. Google ADK/A2A peers are external workers. All remain subordinate to the `van` profile, action classes, Project Truth, grants and evidence rules.

## Configuration checklist

1. No committed secrets.
2. Install/refresh the VAN profile, then register `van_owner_runtime` into live Hermes configuration.
3. Verify `runtime_status` before relying on context/action/research tools.
4. Register the canonical owner Google principal with `tools/google/configure_google_identity.py`.
5. Configure each credential plane independently.
6. Use `tools/google/certify_google_mesh.py` to inspect readiness.
7. `CONFIGURED` means wiring exists; `READY` requires certification evidence.
8. Missing capability => `DEGRADED`; never simulate results.
9. Consumer cookies/session tokens may not be exported or injected into prompts.

## References

- `docs/GOOGLE_INTELLIGENCE_MESH.md`
- `hermes/profile/van/AGENTS.md`
- `hermes/profile/van/config.yaml`
- `hermes/providers/gemini.md`
