# VAN Audit — Hermes Integration and Model Orchestration

Repo: /home/user/Van, branch claude/van-system-audit-ysgtcd, HEAD dff38a0. Read-only audit; no repo files modified.
Probes run: pytest (hermes/policy, tests/hermes, tests/contracts, backend/tests/test_hermes_bridge.py) = 70 pass / 1 fail
(the 1 failure is `test_install_profile_preserves_runtime_state_and_secrets`, caused by `rsync` being absent in this sandbox —
tools/hermes/install_van_profile.sh:66 `require_cmd rsync`; not a code defect). `node --test trading/commander/test/mcp_stdio.test.mjs`
= 1/1 pass. Direct stdio probe of hermes/mcp/owner_runtime_stdio.mjs confirmed: unknown tool -> `-32602 tool not allowed`,
missing token -> exit 2, gateway unreachable -> `isError:true "fetch failed"`.

All paths below are absolute under /home/user/Van unless stated.

---------------------------------------------------------------------------------------------------
## 1. Ownership split, location of the agent loop, and what the gateway sends to Hermes

### 1.1 Who owns what (per repo)
- Hermes owns reasoning, tools, skills, MCP, provider routing, project execution: hermes/profile/van/SOUL.md:5, :43;
  hermes/profile/van/AGENTS.md:8 ("sole agent runtime"), :12 ("planner/reasoner, not a truth or authorization authority").
- VAN gateway owns owner authentication, signed-command authority, context sealing, action authorization and verification,
  credential isolation, deterministic engines: AGENTS.md:8,12; backend/van_gateway/runtime_api.py:87-94 (docstring);
  runtime_api.py:133-134 returns `hermes_is_sole_agent_runtime: True, hermes_is_truth_authority: False`.
- Android is explicitly "not a second planner": backend/van_gateway/mission/api.py:10, :303.

### 1.2 Where is the LLM agent loop?
- **Not in this repo.** `git ls-files | grep -i hermes` returns only the bridge client, tests, deploy/registration scripts and two
  PNGs. No Hermes runtime source, no model client. backend/van_gateway contains no anthropic/openai/genai import and no call to
  api.anthropic.com / generativelanguage.googleapis.com (grep over backend/van_gateway: zero hits). The only outbound HTTP clients
  are: Hermes bridge (hermes/bridge.py), Exa research (research/exa.py:89), n8n (automation/n8n_client.py:102), browser workers
  (browser/adapters.py:95), Google Workspace transport (google/transport.py), VEKL projection (knowledge/vekl.py:96), Notebook
  (knowledge/notebook.py), trading commander client (trading/accounts.py:87). None of these is an LLM API.
- The loop lives entirely in the external Hermes deployment on host `dial-hermes-control` (10.0.0.184):
  artifacts/google/hermes_live_attestation.json:3; deploy/van-trading-core/README.md:7; docs/OWNER_SUPPLY_FOR_V1.md:23.
- Android/Kotlin also has no model SDK references (grep over android/**/*.kt for gemini|anthropic|openai|llm: only Compose
  `fillMaxSize` false positives).
- bridge.py:19 docstring: "Talk to Hermes profile `van` only. Never launches models directly."

### 1.3 What the gateway actually sends to Hermes (backend/van_gateway/hermes/bridge.py)
- Construction: app.py:139 `HermesBridge(settings.hermes_base_url, settings.hermes_bearer_token, settings.hermes_profile)`;
  defaults config.py:13-15 = `http://127.0.0.1:8642`, profile `van`, bearer `""` (empty bearer -> no Authorization header, bridge.py:29-30).
- URL scheme: bridge.py:33-39 — non-default profile is routed at `{base}/p/{profile}{path}` (Hermes multi-profile API surface).
  Verified by backend/tests/test_hermes_bridge.py:28-31 (`/p/van/health`, `/p/van/v1/capabilities`).
- Headers: bridge.py:27-31 `X-Hermes-Profile: van` + optional `Authorization: Bearer <token>`.
- Endpoints and timeouts (no retry anywhere in the bridge):
  | method | HTTP | path | timeout | error mapping |
  |---|---|---|---|---|
  | health() | GET | /health | 5s (l.42) | >=400 or HTTPError -> `{ok:False, degraded:HERMES_OFFLINE}` (l.46-53) |
  | create_run() | POST | /v1/runs | 60s (l.59) | >=400 -> HermesBridgeError("hermes_reject") (l.68-69); HTTPError -> "hermes_offline" (l.71-72) |
  | capabilities() | GET | /v1/capabilities | 10s (l.78) | "capabilities_unavailable" / "hermes_offline" |
  | message_agent() | POST | /v1/message_agent | 30s (l.92) | "message_agent_failed" |
  | create_council() | POST | /v1/group_rooms | 60s (l.123) | requires 2-6 members; if caps lack `group_rooms`, falls back to per-member message_agent (l.113-122) |
- create_run payload (bridge.py:61-65): `{"profile": "van", "input": <owner text>, "metadata": {...}}`.
  Metadata composed at orchestrator.py:497-525: command_id, idempotency_key, device_id, project_id, action_class (effective),
  signed_action_class, context_trust, signature_version, turn_id, origin_channel, principal_type, requested_by, expires_at_unix,
  nonce, context_capsule_revision/hash, speech_evidence_ref, no_stale_replay, client_context (+ `client_context_authoritative: False`),
  `canonical_context` {snapshot_id, digest, kernel_revision, fact_ids, live_state_refs, policy_refs} (orchestrator.py:429-436),
  `typed_resolution` (regex resolver output), `gateway_action_authority_required: True`, `owner_approved`.
  No secrets are included (device_id is an identifier; the device HMAC secret and tokens are never in the payload).
- Pre-dispatch gates in orchestrator.py (all before Hermes is contacted): idempotency (76-100), device + signature v1/v2
  (103-157), typed resolution + class strengthening (159-161), expiry/staleness (165-193), A5 deny (195-203), A4 biometric
  approval challenge/verify (205-297), NO_STALE_REPLAY window (301-321), untrusted-content injection markers (323-334),
  Project Truth gate for A3/A4 (355-388), context snapshot sealing (390-436), authority record sealing (440-481),
  Hermes health gate (483-498).
- What comes back: `resp.json()` returned verbatim (bridge.py:70); the orchestrator uses only `run.get("id")`
  (orchestrator.py:560, :567) as `evidence_pointer` and `hermes_run_id`. Status returned to the owner is `"accepted"` immediately
  (orchestrator.py:562-575). **There is no polling of the run, no callback endpoint keyed by hermes_run_id, and no readback**
  (grep for `hermes_run_id|/v1/runs/` in non-test code: only orchestrator.py:567). Completion is expected to be proven later by
  Hermes itself calling `action_begin -> action_submitted -> action_verify` (runtime_api.py:332-400), but nothing joins a
  hermes_run_id to those executions.
- Audit record on dispatch: orchestrator.py:540-560 `model_delegate="hermes:van"`, `after={"hermes_run": run, ...}`.
- Gateway `/health` is defined by Hermes reachability: app.py:400-401, :421 `"ok": hermes_ok`.
- Dead code: `message_agent()` and `create_council()` have no callers outside bridge.py (grep). Council/degraded semantics
  exist only as bot docs (hermes/bot/councils.md) and DegradedCode.GROUP_ROOM_UNSUPPORTED (degraded/registry.py:63-69).

---------------------------------------------------------------------------------------------------
## 2. The owner-runtime MCP server (hermes/mcp/owner_runtime_stdio.mjs)

### 2.1 Surface
- Not an agent; fixed allowlist; no shell/HTTP tool (header comment l.3-8). JSON-RPC 2.0 over stdio, protocol 2024-11-05 (l.15).
- 20 tools declared (l.50-71) mapped 1:1 to gateway routes (l.73-94), all under `/v1/runtime/*` on `VAN_OWNER_RUNTIME_URL`
  (default http://127.0.0.1:8787, l.16):

  | tool | route | authority carried |
  |---|---|---|
  | runtime_status | GET /v1/runtime/status | read |
  | resolve_command | POST /v1/runtime/resolve | deterministic regex resolution, "without granting execution authority" |
  | context_graph_query / context_lexical_query / context_hot_capsule / context_readiness | POST context/* | read/evidence only |
  | context_snapshot | POST /v1/runtime/context/snapshots | seals a snapshot (write to runtime_meta, not owner truth) |
  | knowledge_status / vekl_query / obsidian_query / notebook_enterprise_recent / notebook_enterprise_get / notebook_consumer_ask | knowledge/* | read (consumer_ask drives a NotebookLM UI session, still read/evidence) |
  | knowledge_action_execute | POST knowledge/actions/execute | **executes a Notebook mutation** for an already-AUTHORIZED execution_id with digest-matched params |
  | research_status / research_search | research/* | gateway-mediated Exa egress |
  | action_begin / action_submitted / action_verify / action_get | actions/* | request authorization / record lifecycle |

- Deliberately NOT exposed (contract test tests/contracts/test_owner_runtime_mcp_contract.py:42-53): `/context/facts`,
  `/context/edges` (canonical memory admission), obsidian index/certify, vekl certify, notebook certify. Also absent from the
  shim: `/v1/runtime/context/export/{scope}` and `DELETE /v1/runtime/context/scope/{scope}` (runtime_api.py:225-233) even
  though those routes exist and accept the same internal token.
- Credential: l.40-46 reads `VAN_INTERNAL_CONTROL_TOKEN` from env, an explicit token file, or `~/.config/van/gateway.env`; sent
  as `x-van-internal-token` (l.103); never echoed (only `data.detail` of error bodies returns, l.108). Exits 2 without a token (l.135-137).

### 2.2 Can Hermes execute owner commands through it, or only read?
- It can *execute* only inside the gateway's authorization envelope. `action_begin` (runtime_api.py:332-365) calls
  `CommandAuthorityService.authorize_action` (command/authority.py:87-136) which requires a **sealed authority record for the
  given command_id** (l.99-101) and enforces: principal_type match (l.104), requested_by match (l.106), turn_id match (l.108),
  snapshot_id match (l.110-111), expiry (l.112-113), device not revoked (l.115-120), no class escalation (l.122-123), typed
  action id match (l.124-125), typed parameter constraints (l.126-129). The record is only ever sealed by the orchestrator after
  device signature verification (orchestrator.py:440-461).
- Built-in action registry (backend/van_gateway/action/registry.py:9-93): every A3/A4 action (`google.notebook.*`,
  `trading.halt`) has `allowed_principals={OWNER_DEVICE}`; only `owner.context.read` (A1) and `research.web.search` (A2) admit
  `HERMES_AGENT`. `ActionRuntime.begin` rejects disallowed principals (action/service.py:118-119). So Hermes executes A3/A4
  **only by presenting the exact identifiers of a live owner-signed command** (it receives them in the run metadata,
  orchestrator.py:500-525); it cannot mint authority with the HERMES_AGENT principal.
- `owner_approved` in the request body (runtime_api.py:73) is ignored; the value from the sealed record is used (l.358).
- `knowledge_action_execute` (knowledge/service.py:190-213): requires status AUTHORIZED/RETRYABLE_FAILURE and
  `digest_parameters(parameters) == execution.parameters_digest` (l.212-213). Real; digest-bound.

### 2.3 Is the "authorized execution bridge" real?
- Yes in code and unit/contract tests. Not proven live: the only live receipts are an inference canary and an install doctor
  (see §8). No artifact shows an `action_begin` round trip on the live host.
- **Registration drift**: tools/hermes/register_owner_runtime_mcp.sh:48-64 registers an `include` list of only **11** tools
  (runtime_status, resolve_command, context_graph_query, context_readiness, context_snapshot, research_status,
  research_search, action_begin, action_submitted, action_verify, action_get). It omits context_lexical_query,
  context_hot_capsule, knowledge_status, vekl_query, obsidian_query, notebook_enterprise_recent/get, notebook_consumer_ask,
  knowledge_action_execute. hermes/mcp/README.md:27-39 lists 13; the shim/contract test require 20. If the live Hermes config
  was produced by this script, AGENTS.md:37,40-41 (vekl_query, obsidian_query, notebook_consumer_ask, knowledge_action_execute)
  is unreachable from Hermes. The contract test (test_owner_runtime_mcp_contract.py:58-65) checks only strings in the script,
  not the include list, so this drift is untested.

---------------------------------------------------------------------------------------------------
## 3. Hermes policy hook (hermes/policy/van_policy_hook.py)

- Pure function `evaluate(action: Mapping) -> dict` (l.117-138) and `register_hook(registry)` (l.141-142, sets `registry["van"]`).
- Blocks: invalid/non-mapping action (l.118-121); mutating action with no `action_class` (l.123-124, fail-closed); invalid class
  (l.125-126); A5 substring patterns in name/tool/flags/options/intent (l.27-38, l.97-114) including audit/approval bypass,
  Google session export, OAuth reuse, and the VATI trading prohibitions (bypass_risk_authority, direct_broker_order,
  remove_stop_loss, martingale, learning_* etc.); explicit A5 (l.130-131); protected surfaces (l.23-25) by substring on
  target/resource, or path markers with write/delete/modify/patch ops absent `owner_signed`/`truth_authority_verified`
  (l.79-94, l.132-133); A4 without `owner_approval`/`approval_granted` -> approval_required (l.134-137).
- Fail-closed assessment: partially. A **non-mutating** action with no class is ALLOWed (l.138) — the hook trusts the caller's
  `mutating`/`writes` flags and `action_class`; it cannot derive class from tool semantics. All matching is substring/lowercase
  on caller-supplied strings, so a mutating tool invoked with `action_class: "A1"` and a benign name passes. Its effectiveness
  depends entirely on Hermes populating the envelope honestly (hermes/bot/message_agent.md:27 "Run van_policy_hook.evaluate
  before mutating tools" is a doc instruction).
- Tests: hermes/policy/tests/test_van_policy_hook.py — 30 cases including A5-even-with-owner-approval (l.93-95), pass.
- Wiring: config.yaml:34-43 declares `hook_module: policy/van_policy_hook.py`, `hook_entrypoint: evaluate`. The installer only
  copies the `policy/` directory (install_van_profile.sh:87-90); the doctor only checks the file exists (doctor_van_profile.sh:50-51);
  the MCP registration script touches only `mcp_servers`. **No script registers the hook with Hermes**, and no live artifact
  attests the hook is loaded (van_profile_live_attestation.json has no hook field). AGENTS.md:20 asks Hermes to "confirm
  `van_policy_hook.py` is registered" — an instruction to the model, not evidence. Whether Hermes honours `policy.hook_module`
  in a profile config.yaml is a property of the external Hermes runtime not visible here.

---------------------------------------------------------------------------------------------------
## 4. MODEL-ROLE MATRIX (evidence type per cell)

Legend: DOC = prose claim; CFG = config value; CODE = executable path in this repo; LIVE = external attestation artifact.

| Role | Designated model / provider | Evidence | Type |
|---|---|---|---|
| Primary conversation & orchestration | Claude Sonnet 5 via Hermes Anthropic provider | SOUL.md:13-18; config.yaml:13-15 (`provider: anthropic`, `default: claude-sonnet-5`); gemini.md:7-8, :73; tests/hermes/test_profile_layout.py:65-69 asserts the strings | DOC + CFG (profile metadata; the live `~/.hermes/config.yaml` is never written with a model by any repo script) + LIVE canary (artifacts/runtime/van_profile_live_attestation.json:17-18, 1 API call) |
| Complex reasoning | same as primary | SOUL.md:15 "primary reasoning and orchestration model" | DOC |
| Planning | Hermes (Sonnet 5); gateway explicitly refuses goal interpretation | capability/router.py:174-186 (`candidate_classes` required, "Hermes narrows"); mission/api.py:89 | DOC + CODE (negative: gateway has no planner) |
| Coding | Antigravity (delegated Google identity; canary model `gemini-3.8-flash-low`), Jules; fallback "Hermes Claude/Codex delegates" | hermes/skills/google-development/SKILL.md:15-33; degraded/registry.py:36-40; artifacts/google/antigravity_worker_live_attestation.json:37-42 | DOC + CODE(wrapper bin/antigravity-worker isolates HOME/creds l.17-24) + LIVE(Antigravity READY 2026-09-15). "Claude/Codex delegates" = DOC only, no code |
| Research | Exa via gateway (`research_search`), Gemini Deep Research (`deep-research-preview-04-2026`) | research/exa.py; runtime_api.py:407-414; gemini.md:63; gemini_runtime_auth_attestation.json:28 | CODE (Exa) + DOC/CFG (Deep Research, CAPACITY_LIMITED live) |
| Summarization / documents | none designated (falls to primary) | hermes/skills/document-work/SKILL.md (prompt only) | DOC |
| Browser intelligence (Stagehand) | gateway-pinned provider/model; **empty by default** | config.py:74-75 `browser_stagehand_model_provider=""`, `model_name=""`; adapters.py:231-241 envelope carries provider/name with `allow_model_self_selection: False`; tests use `anthropic/claude-sonnet-5` (backend/tests/test_browser_fabric.py:281) | CODE (handoff to worker) — actual model = deployment env, not in repo; adapter reports unconfigured when empty (adapters.py:233) |
| VEKL | none — deterministic projection, no model | knowledge/vekl.py:70-73 `read_only: True`; trading/vekl/vendor/dial/engineering-resource-resolver.mjs regex | CODE (no model) |
| Google-specific | Gemini family (`gemini-3.6-flash`, live `gemini-3.5-transcribe-live`, Nano Banana `gemini-3.1-flash-image`, Veo `veo-3.1-generate-preview`) | config.yaml:75-102; gemini.md; registries/google_capabilities.json; gemini_runtime_auth_attestation.json:24-30 | CFG + LIVE (AUTHENTICATED but `RESOURCE_EXHAUSTED`, family_states all CAPACITY_LIMITED, 2026-09-17) |
| Trading | Hermes (Sonnet 5) as Tier-2 analyst only; sizing = deterministic Risk Authority; no model in trading/ | SOUL.md:45-53; trading-intelligence/SKILL.md:17-35; grep trading/ for model names = only `AGENT_REQUESTERS` list (trading/commander/app.py:33) | DOC + CODE(negative) |
| Fallback / escalation / cost control | **No model-level routing, fallback, escalation or cost code exists.** | bridge.py:19; router.py fallback_chain (l.241-264) is over *capability* declarations; `_COST_WEIGHT` (l.84-86) is a declared cost class, not token spend; google_capabilities.json `fallback` is capability-to-capability | ABSENT in code; capability-level only |

Other model mentions: README.md:20 ("Claude / Codex / GPT-SOL / Gemini / Antigravity"), docs/GOOGLE_INTELLIGENCE_MESH.md:497-498
(provider tree) — DOC only. deploy/van-trading-core/supabase/docker-compose.yml:49 passes `OPENAI_API_KEY` into the Supabase
stack (vendor image env; no VAN code consumes it).

---------------------------------------------------------------------------------------------------
## 5. Skills: prompt-only vs tool-bound; SOUL/AGENTS guidance on cognition endpoints

All 16 `hermes/skills/*/SKILL.md` are Markdown instruction files with YAML front-matter (name/description). None contains
code, tool schemas, or executable bindings. "Binding" below means the skill names a tool/route that actually exists.

| Skill | Names real tools/routes? | Assessment |
|---|---|---|
| owner-briefing | "gateway attestation or deterministic read APIs"; no Hermes-reachable tool for attention/reminders | STUB (prompt) |
| google-workspace | expects `google-gmail/-calendar/-drive` MCP servers (hermes/mcp/README.md:57-61) — no such server in repo; gateway Google routes are device-auth | PARTIAL (doc contract, no Hermes tool) |
| google-intelligence | `/v1/google/jobs/plan` exists (app.py:657, internal-control) but no MCP tool exposes it; l.24 says the "Hermes tool runtime injects X-Van-Internal-Token" — nothing in repo does that | PARTIAL |
| gemini-notebook | maps to real notebook_* MCP tools + knowledge_action_execute (shim l.61-64) | IMPLEMENTED_BUT_ISOLATED (tools exist; omitted from register include list §2.3) |
| google-design | Mixboard/Stitch/Nano Banana — no tools in repo | STUB |
| google-development | `bin/antigravity-worker` wrapper is real and tested (tests/hermes/test_profile_layout.py:126-157); Jules = doc | PARTIAL |
| project-steering | needs scoped filesystem/git MCP (README expects; none provided) and Project Truth loading | STUB/DOC |
| research | `research_search` MCP tool -> runtime_api.py:407-414 -> research/exa.py; registered in include list | INTEGRATED (gateway side); E2E unverified |
| decision-support | "log to decisions engine via gateway when available" — no Hermes tool | STUB |
| document-work | prompt only | STUB |
| notification-triage | "gateway attention API" — device-auth only, no Hermes tool | STUB |
| infrastructure-diagnostics | references doctor script; Hermes needs shell to run it | PARTIAL |
| hermes-administration | install/doctor/pytest commands are real | IMPLEMENTED_BUT_ISOLATED |
| trading-intelligence | binds to `van_trading_commander` MCP (real, node-tested) and gateway `/v1/trading/*` (device-auth) | INTEGRATED (commander) / PARTIAL (gateway routes not Hermes-reachable) |
| automation-fabric | `/v1/automation/*` is Hermes-only internal-control (app.py:312-313) but no MCP tool; **not copied by installer** (install_van_profile.sh:78-82) nor checked by doctor (l.77-82) | IMPLEMENTED_BUT_ISOLATED / not installed |
| browser-intelligence | `/v1/browser/*` mutations internal-control (app.py:333-334); no MCP tool; **not installed by installer** | IMPLEMENTED_BUT_ISOLATED / not installed |

Skill-count drift: config.yaml:45-63 lists 16; installer/doctor manage 14; tests/hermes SKILL_NAMES = 13 (no trading-intelligence);
live attestation `managed_skills_verified: 13` (van_profile_live_attestation.json:10).

SOUL/AGENTS and the cognition endpoints:
- AGENTS.md:28-43 defines an "Owner-context protocol" ordering the owner-runtime MCP tools (resolve_command -> context_readiness ->
  graph -> lexical -> hot capsule -> knowledge -> context_snapshot -> research -> action_begin -> verify). This is the only
  place Hermes is told how to use VAN cognition, and it targets `/v1/runtime/*` only.
- `ContextPacket` (backend/van_gateway/context_compiler/compiler.py:108), the reasoning kernel (reasoning/kernel.py), the mission
  API (`/v1/missions*`, mission/api.py:163-408) and `/v1/understanding/observe` (understanding/api.py:140) are **never mentioned**
  in hermes/, tools/hermes/, deploy/ or trading/ (grep for `v1/context|v1/understanding|v1/missions|ContextPacket|reasoning kernel`
  across those trees: zero hits). The mission POST routes and `/understanding/observe` are internal-control (app.py:318-330), i.e.
  intended for Hermes, but no MCP tool reaches them. The reasoning kernel stores structured solver/critic/verifier records with
  "no hidden chain-of-thought" (kernel.py:20-24) and makes no model call.
- Net: Hermes-side reaches `/v1/runtime/*` (via shim) only; Mission Core, Understanding, ContextPacket and `/v1/google/jobs/plan`
  are gateway-internal surfaces with no Hermes client in the repo.

---------------------------------------------------------------------------------------------------
## 6. Duplicate orchestration?

- orchestrator.py is an authorization/dispatch pipeline (see §1.3): signature, idempotency, class gating, approval, injection
  markers (l.26-33, a 6-string denylist), Project Truth gate, snapshot + authority sealing, then a single `create_run`. It does
  not plan, select tools, or reason. The `TypedCommandResolver` (command/resolver.py) is regex-based (`rule_id`s at l.125-187)
  and maps a handful of exact phrasings to built-in action ids; `resolve_command` is also exposed to Hermes as a tool.
- capability/router.py: scoring is pure arithmetic over manifest facts (l.129-150) after policy filtering (l.203-212), and it
  **raises if Hermes does not supply `candidate_classes`** (l.190-194, "the router does not interpret goals"). This is a
  deterministic ranker beneath Hermes, not a competing planner. It is exposed at `POST /v1/missions/route` (mission/api.py:370,
  internal-control) — again with no Hermes-side client.
- automation/compiler.py:9 "No model participates. Hermes may help produce the IR; compilation is a pure ..." — consistent.
- One tension: the orchestrator seals a context snapshot with `requirements=[]` before dispatch (orchestrator.py:414-420) and
  binds the authority record to that `snapshot_id` (l.451); AGENTS.md:38 then tells Hermes to seal its own `context_snapshot`.
  `authorize_action` requires the *record's* snapshot_id (authority.py:110-111), so a Hermes-sealed snapshot cannot be used
  for `action_begin`; Hermes must echo `canonical_context.snapshot_id` from run metadata. Two snapshot notions, one binding —
  documented nowhere.
- Verdict: no duplicated LLM loop; the gateway is deterministic gating + evidence. Hermes retains planning and tool choice.

---------------------------------------------------------------------------------------------------
## 7. Trading commander (trading/commander/)

- What it is: FastAPI "typed command surface, deliberately not a shell" on van-trading-core (trading/commander/__init__.py:1-6;
  app.py:108-110). Commands (app.py:28): status, ledger_status, services, restart_service, tail_log, run_backtest, vekl_resolve,
  halt, doctor, accounts + 11 account-onboarding commands from accounts.py:32.
- Auth: HMAC-SHA256 over `ts\nnonce\nMETHOD\npath\nsha256(body)`, ±60 s skew, single-use nonce (auth.py:3-4, :46-58); token file
  must be 0600 and ≥32 chars (app.py:67-78).
- MCP: trading/commander/mcp_stdio.mjs — stdio JSON-RPC; `tools/list` proxies `GET /v1/tools` (l.48) which hides
  `AGENT_HIDDEN_COMMANDS` (app.py:280-281); `tools/call` posts `/v1/cmd/{name}` with `requested_by: 'hermes'` hardcoded (l.53);
  server refuses agent requesters on credential commands (app.py:295-297). Node test verifies the exact 10-tool list, 403 on a
  non-allowlisted unit, 403 on `account_credentials`, error on halt without signature ref (test/mcp_stdio.test.mjs:43-59). Passes.
- Registration into Hermes: deploy/van-trading-core/hermes/register-commander-mcp.sh splices `mcp_servers.van_trading_commander`
  into `~/.hermes/config.yaml` with `authority`-less spec (l.25-30; config.yaml:110-126 mirrors it with
  `authority: SUBORDINATE_CAPABILITY_NOT_AUTHORITY`). Idempotent, verified splice, 0600 backup.
- Relation to Risk Authority: commander has **no order path** (mcp/README.md:49-51; skill l.74). `halt` appends a
  `KILL_SWITCH OWNER_HALT` ledger event (app.py:229-237) — the only trading effect; direction is fail-safe. Guarded surfaces
  (risk_authority, kill_switch, mandate...) are protected in the policy hook (van_policy_hook.py:23-25); the commander's
  `restart_service` is allowlisted to `vati-*`/caddy units (app.py:27, :80-81).
- Weakness: `halt` requires only a **non-empty** `owner_signature_ref` string (app.py:226-228); nothing verifies it against a
  gateway authority record or signature. The gateway's `trading.halt` action (action/registry.py:80-87) is OWNER_DEVICE/A4 and
  is the proper path, but the commander does not check that an execution exists. "Owner-signed halt" is therefore a label.
- `requested_by` is client-supplied (app.py:88-90): anyone holding the commander HMAC token (stored on the Hermes host at
  `~/.van/commander.token`, config.yaml:117) can set `requested_by: "app"` and reach `account_credentials` / `mt5_ea_issue_key`
  (which returns a signing key once, accounts.py:275). The MCP shim cannot do this, but a Hermes with a shell tool could.

---------------------------------------------------------------------------------------------------
## 8. Live attestations — what they prove

### artifacts/google/hermes_live_attestation.json (attested_at 2026-09-15; workspace recheck 2026-09-16)
- Host `dial-hermes-control`; principal subject is a *label* `hermes:dial-hermes-control:owner-google` (l.11) — despite `notes`
  claiming "hashed principal", no hash is present. `ai_plan: PRO`.
- Capability states: 12 × `CONFIGURED`, only `workspace_api` = `READY` (l.56-59) with evidence `live://…/workspace-oauth/canary`;
  all other evidence pointers are opaque `hermes://…` URIs (not hashes, not verifiable from the repo). `gemini_runtime_configured:
  true`, `cloud_runtime_configured: false`. Excludes Notebook Enterprise and A2A/ADK (l.96-99). Antigravity delegated separately.
- Authority (l.5-8): "owner_confirmed_hermes_authentication" + ledger anchor. Proves: someone recorded that Google planes were
  logged in on the Hermes host. Does not prove any Hermes->gateway call, any owner command, or any inference.
- Omitted: raw tokens, account identifiers, any content hashes. Later artifacts contradict "configured = usable":
  gemini_runtime_live_canary.json (2026-09-17T04:06) `AUTH_REQUIRED` (no credential), then gemini_runtime_auth_attestation.json
  (2026-09-17T06:04) `AUTHENTICATED` but inference `RESOURCE_EXHAUSTED` / `PREPAID_CREDITS_DEPLETED`, all families CAPACITY_LIMITED.

### artifacts/runtime/van_profile_live_attestation.json (observed 2026-09-17T05:38:50Z)
- `source_commit 270da5d` (older than HEAD dff38a0); installer preservation + doctor passed; `managed_skills_verified: 13`;
  `.env` mode 0600; inference canary `VAN_PROFILE_CANARY_OK` via `anthropic / claude-sonnet-5`, `api_calls: 1`; `contains_secrets:
  false`. Proves: at that commit on that host, the profile files were installed, the doctor's file/grep checks passed (which
  includes `van_owner_runtime` present in `~/.hermes/config.yaml` and the env file containing the token, doctor l.64-75), and one
  Sonnet-5 completion returned the expected string under the `van` profile.
- Does not prove: policy hook loaded; MCP shim successfully called the gateway; any `/v1/runs` dispatch; any `action_begin` chain;
  the 20-tool surface (registered list is 11, §2.3); the two fabric skills (not installed).
- docs/PRODUCTION_ACCEPTANCE_LEDGER.md:86-109 ("Live Hermes certification — 2026-09-15") reports a different canary string
  (`VAN_SONNET5_OK`, l.94) and "live Hermes-source tests" for message_agent/rooms/delegation (l.96-101) — those are tests of the
  external Hermes codebase, not of VAN. l.61 states restart-durability was proven "without executing Hermes".
  artifacts/release/hermes_recert_probe.json notes install/doctor "were NOT executed by this agent" and certification is "owned
  by the parallel ChatGPT run" — the chain of custody for the live cert is a doc reference, not a reproducible artifact.

---------------------------------------------------------------------------------------------------
## 9. Classification

| Component | Class | Basis |
|---|---|---|
| Gateway -> Hermes dispatch (bridge.py + orchestrator dispatch) | IMPLEMENTED_BUT_ISOLATED | Real client, mock-tested only (all backend tests monkeypatch `create_run`); no live run receipt; no result readback |
| Hermes -> gateway owner-runtime MCP (shim + /v1/runtime) | PARTIAL (code INTEGRATED; registration drifted) | 20 tools + routes + contract tests; register script exposes 11; live doctor only checks presence |
| Authorized execution chain (action_begin/verify, knowledge_action_execute) | IMPLEMENTED_BUT_ISOLATED | Authority binding is real and strict; no live E2E artifact |
| Policy hook | IMPLEMENTED_BUT_ISOLATED | 30 unit tests pass; not wired by any script; loading unverified; trusts caller-supplied class |
| Model orchestration / routing / fallback / cost control | ABSENT (by design) | No model client, router, or fallback code; designations are DOC/CFG; one live Sonnet-5 canary |
| Model designation (Sonnet 5 primary) | E2E_VERIFIED for a single canary turn only; otherwise DOC+CFG | van_profile_live_attestation.json |
| Gemini specialist runtime | PARTIAL / LIVE-DEGRADED | Authenticated, quota exhausted |
| Stagehand model handoff | IMPLEMENTED_BUT_ISOLATED | Envelope code real; provider/model empty by default; worker external |
| Trading commander + MCP | IMPLEMENTED_BUT_ISOLATED | Node E2E test against a local commander passes; live registration unverified; halt signature not verified |
| Skills | see §5 table — mostly STUB (prompt-only); research/gemini-notebook/trading-intelligence bind to real tools |
| Councils / message_agent | STUB (dead code + docs) | No callers |

---------------------------------------------------------------------------------------------------
## 10. Security: escalation, credential exposure, confused deputy

Positive controls (verified in code/tests):
- Internal token is a separate credential from ingress/device tokens and is not accepted on owner routes (app.py:366-389;
  docs/EXTERNAL_GATES.md:83). HMAC compare_digest everywhere (app.py:370, google/control.py:20, commander auth.py:54).
- Hermes memory writes are forced to INFERRED + MODEL_DERIVED (runtime_api.py:122-125, :164-181); canonical admission is not
  in the shim (contract test l.42-43).
- A3/A4 typed actions are OWNER_DEVICE-only and bound to command/turn/snapshot/device/class/params (§2.2). Class escalation is
  rejected (authority.py:122-123). Revoking a device revokes its privileged executions (app.py:499-505).
- No credentials in Hermes payloads: run metadata (orchestrator.py:500-525) carries identifiers only; the bearer is header-only;
  shim never returns the token; commander redacts logs (app.py:25, :84-85) and hides credential commands from agents.
- SOUL.md:113-124 and gemini.md:35-44 forbid secrets in prompts; installer excludes secret-like files (install_van_profile.sh:13-24);
  doctor flags secret filenames (l.91-96).

Risks / confused-deputy findings:
1. **Internal-control token ⇒ owner-device authority.** `POST /v1/devices/pairing-ticket` and `/v1/devices/enroll` require only
   `X-Van-Internal-Token` (app.py:443, :479-483); `/v1/devices/pair` is unauthenticated except for the ticket (middleware skip
   app.py:361; handler l.453-476 returns the ingress token and a device access token). A holder of the internal token can therefore
   enrol a new device, obtain ingress + device tokens, and sign owner commands (A1–A3; A4 still needs a biometric proof bound to
   the *same* device key, approval/service.py — but that key is the attacker's). The shim process reads this token from
   `~/.config/van/gateway.env` in the Hermes user's home (owner_runtime_stdio.mjs:44-45). If the Hermes agent has any shell or
   file tool (hermes/mcp/README.md:11-12 expects scoped `filesystem`/`git` servers; SOUL/AGENTS do not forbid a terminal),
   Hermes can read the token and self-escalate outside the MCP allowlist. docs/SECURITY_POLICY.md:9,12 documents ticket issuance
   as "internal control plane only" without noting that the same credential is provisioned to the Hermes-side MCP shim.
2. Same token reaches `DELETE /v1/runtime/context/scope/{scope}` and `GET …/context/export/{scope}` (runtime_api.py:225-233),
   `/v1/devices/{id}/revoke` (app.py:490), `/v1/google/jobs/plan` (app.py:657), all `/v1/automation/*` and browser mutations
   (app.py:312-313, :333-334). The MCP allowlist is the only thing keeping Hermes to the 20 tools; the credential is not scoped.
3. **Commander token on the Hermes host** (`~/.van/commander.token`, config.yaml:117; register-commander-mcp.sh:11) plus client-
   supplied `requested_by` (app.py:88-90) lets a shell-capable Hermes reach credential-bearing account commands and receive
   broker tokens/keys (accounts.py:275 returns `signing_key`). The agent filter is a string check, not a principal binding.
4. `halt` accepts any non-empty `owner_signature_ref` (app.py:226-228) — a model can halt trading without owner authority
   (fail-safe direction, but contradicts the "A4 owner-signed" label in the skill l.74 and README l.51).
5. Policy hook trusts caller-declared `action_class`/`mutating` (van_policy_hook.py:69-76, :123, :138): unclassified non-mutating
   calls are allowed; its guarantees are only as good as Hermes' self-labelling.
6. Registration drift (§2.3) means the live Hermes may lack `knowledge_action_execute`; the only mutation tool the docs rely on is
   then absent — fail-closed in effect, but the docs claim otherwise.
7. Run outcome is never verified by the gateway (§1.3): `status: accepted` is returned to the owner immediately and no evidence
   links a hermes_run_id to a later `action_verify`. Silent non-execution is possible without any degraded signal.
8. Injection filtering on owner ingress is a 6-marker substring list (orchestrator.py:26-33) applied only when
   `context_trust == UNTRUSTED`; all real prompt-injection defence is delegated to Hermes prose (SOUL.md:39, skills).

Credentials-to-prompt check: none found in repo code paths. Gemini key lives in `~/.hermes/profiles/van/.env` (gemini_runtime_auth_
attestation.json:10-11), loaded by Hermes, never by VAN code. Antigravity wrapper unsets Google credential env vars (bin/antigravity-worker:24).

---------------------------------------------------------------------------------------------------
## Appendix — test/probe log
- `python -m pytest hermes/policy/tests/test_van_policy_hook.py tests/hermes/test_profile_layout.py tests/contracts/test_owner_runtime_mcp_contract.py backend/tests/test_hermes_bridge.py -q` -> 70 passed, 1 failed (rsync missing).
- `node --test trading/commander/test/mcp_stdio.test.mjs` (cwd trading/) -> 1 pass (spawns real commander on a free port, signed calls through the shim).
- stdio probe of owner_runtime_stdio.mjs with `VAN_OWNER_RUNTIME_URL=http://127.0.0.1:1`: initialize OK; `tools/call shell` -> -32602; `runtime_status` -> isError "fetch failed"; no token -> stderr message, exit 2.
