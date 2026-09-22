# VAN Profile — Expected MCP / Capability Servers

Hermes profile **`van`** is the sole agent runtime. Credentials are brokered through the VAN gateway or provider runtime; raw secrets never enter prompts. A missing server/capability fails closed.

## Core

| Server | Purpose | Credential model |
|---|---|---|
| `van_owner_runtime` | Deterministic owner-context readiness/graph/lexical/hot-capsule/snapshot, typed resolution, research routing, action lifecycle verification, read-only trading/attention/briefing state, owner-behalf reminders, INFERRED/MODEL_DERIVED memory candidates, and the already-governed browser-assignment/automation-execute routes | Local Hermes internal-control credential; fixed tool allowlist; no generic HTTP; no canonical-memory admission |
| `filesystem` (scoped) | Registered project files | Path allowlist + Project Truth + grants |
| `git` (scoped) | SHA/evidence/diff/write | Read default; writes require grant |

There is no separate `van-gateway` MCP server: an earlier revision of this document
described one (grants, evidence, health) that was never built. Every gateway surface
Hermes reaches goes through the single `van_owner_runtime` shim above, or through the
`van_trading_commander`/`van_trading_local_commander` servers documented below for
Trading Core.

### `van_owner_runtime`

The canonical stdio shim is `hermes/mcp/owner_runtime_stdio.mjs`. Register it into the live Hermes config with:

```bash
./tools/hermes/register_owner_runtime_mcp.sh --dry-run
./tools/hermes/register_owner_runtime_mcp.sh
```

The registration script reads no secret into YAML. The shim obtains `VAN_INTERNAL_CONTROL_TOKEN` from the existing local gateway environment (default `~/.config/van/gateway.env`) or an explicitly configured local token file. The token is used only as `X-Van-Internal-Token` and is never emitted as tool output.

The credential this shim reads must be scoped for `runtime`, `browser` and `automation`
(`ControlScope` in `backend/van_gateway/auth/control_scopes.py`) — for example, in
`internal_control_scoped_tokens`: `runtime,browser,automation:<32+ char token>`. A token
scoped for `runtime` alone still answers `runtime_status`, the context/knowledge/research/
action/trading/reminder/attention/briefing tools, but the `browser_*` and `automation_*`
tools answer 403 until `browser`/`automation` are granted too. Device enrolment and
observability are deliberately never granted to this credential.

Allowed tools are deliberately narrow:

- `runtime_status`
- `mission_result`
- `resolve_command`
- `context_graph_query`
- `context_lexical_query`
- `context_hot_capsule`
- `context_readiness`
- `context_snapshot`
- `context_fact_candidate` / `context_edge_candidate` — INFERRED/MODEL_DERIVED only
- `knowledge_status`, `vekl_query`, `obsidian_query`, `notebook_enterprise_recent`,
  `notebook_enterprise_get`, `notebook_consumer_ask`, `knowledge_action_execute`
- `google_status`, `google_capabilities`, `google_gmail_search`, `google_calendar_agenda`,
  `google_drive_search`, `google_contacts_resolve`, `google_tasks_list`, `google_job_plan`,
  `google_action_execute`
- `trading_portfolio`, `trading_positions`, `trading_risk`, `trading_market_state`,
  `trading_trade_detail`, `trading_status` — read-only; no halt, ticket or account tool
- `reminder_create` — on the owner's behalf; `text` must be the owner's own words
- `attention_list`, `briefing_read` — read-only
- `browser_task_create`, `browser_assignment_run`, `browser_task_status`,
  `browser_task_evidence` — creation carries `command_id`/`mission_id` (that route has no
  `turn_id` field); the run itself is bounded and enforced by `browser/api.py`'s
  `run_assignment`, not by this shim
- `automation_route`, `automation_execute`, `automation_run_status` — execution runs only
  under an existing signed command authority; this tool cannot mint or approve one
- `research_status`
- `research_search`
- `action_begin`
- `action_submitted`
- `action_verify`
- `action_get`

There is **no** generic HTTP/shell tool and no CANONICAL_OWNER-tier fact/edge admission
tool. Hermes is not a truth authority. Any Hermes-originated memory candidate reaching the
internal runtime API is forced to `MODEL_DERIVED + INFERRED`; owner/canonical promotion
requires a separate trusted gateway/owner path (GAP-F-015: this shim's memory-candidate
tools and AGENTS.md's "may submit inferred/model-derived memory candidates" now agree).

The context graph is a bounded temporal retrieval primitive, not an autonomous GraphRAG loop. Deterministic lexical retrieval runs locally over current owner facts and graph edges without embeddings, model inference or a remote call. Hot-context capsules are revision-sealed, bounded caches of evidence references used to reduce repeated lookup latency; they are invalidated by context revision/expiry and are never a new truth store. Exact facts remain ahead of graph/lexical retrieval in the critical path; external research remains an escalation.

## Trading (van-trading-core)

| Server | Purpose | Credential model |
|---|---|---|
| `van_trading_commander` | Hermes subordinate on the trading VM: status, ledger, services, bounded log tail, bounded backtest, trading-VEKL resolve, owner-signed halt, doctor, accounts | HMAC-signed requests with a 0600 token file; no shell, no file writes, no order path; account-credential commands are hidden from MCP and refused for agent requesters |
| `van_trading_local_commander` | Full Desktop Commander machine/session actuator on Trading Core, owned by Hermes; process/session/file/config tools and local ChatGPT/Codex session control | Private forced-command SSH stdio from `dial-hermes-control`; complete pinned Commander surface; calls pass through DIAL's Hermes Commander authority gateway |

The commander reaches the dedicated trading VEKL (`trading/vekl`, loopback :9134 on the VM) and the VATI ledger. It cannot place, size, modify or cancel an order; halting is the only trading effect and it needs an owner signature reference (A4). Registration is spliced into `~/.hermes/config.yaml` by `deploy/van-trading-core/hermes/register-commander-mcp.sh`.

The independent Trading Core review worker is also isolated from the VM administrator. It runs as `vanreviewer`, with no `vati`, `sudo`, or `docker` membership, and uses a separately authenticated ChatGPT/Codex session plus forced-SSH shared-memory clients. Its model session is read-only and cannot inherit broker/VATI secret access from the `ubuntu` administrator.

The two commander surfaces are intentionally different. `van_trading_commander` remains the bounded **trading-domain** API and preserves VATI as the sole trading execution/risk authority. `van_trading_local_commander` is the **machine/session** actuator: Hermes receives the complete pinned Desktop Commander capability surface so it can operate processes, files, terminals and persistent ChatGPT/Codex work sessions. It is not an order-routing API and must not be used to bypass VATI.

Hermes reaches the full Commander over a purpose-specific SSH key enrolled only into the dedicated `vancommander` OS account. Its `authorized_keys` entry is `restrict,command="/var/lib/van-commander/.local/bin/van-local-commander-mcp"`. The account is excluded from `vati`, `sudo`, and `docker`, cannot read `/opt/van-trading/secrets`, and works from its own isolated Git checkout. The key therefore opens the Commander stdio process and cannot open a general shell or inherit VATI secret authority. DIAL's authority gateway sits above that full capability: authenticated owner turns may use the complete surface; unattended calls require a named designed automation.

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
