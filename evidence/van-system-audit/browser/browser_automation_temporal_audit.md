# VAN Browser Fabric + Automation Fabric Audit
Repo: /home/user/Van · branch claude/van-system-audit-ysgtcd · HEAD dff38a0
Read-only evidence-first audit. All citations file:line.

## 0. Scope inventory (LOC)
backend/van_gateway/browser: adapters.py 305, api.py 956, models.py 238, policy.py 188,
service.py 242, subagent.py 388 (__init__.py is EMPTY, 0 bytes).
backend/van_gateway/automation: api.py 611, canonical.py 93, cold.py 356, compiler.py 254,
credentials.py 124, deadletter.py 188, dispatch.py 422, events.py 246, external_runtime.py 182,
grants.py 348, health.py 236, models.py 380, n8n_client.py 186, payments.py 242, policy.py 337,
registry.py 351, repair.py 284, router.py 255, telemetry.py 271, templates.py 481,
validator.py 349, verifier.py 170, workflow_health.py 369 (__init__.py EMPTY).
backend/van_gateway/computer_use/fabric.py 249 (__init__.py EMPTY).

config/automation: credentials.yaml.example, domains.yaml, node_allowlist.json, policy.yaml,
resource_policy.yaml. config/browser: domains.yaml, profiles.yaml.
deploy/van-trading-core/automation: bootstrap-automation-fabric.sh, docker-compose.yml,
postgres/init/01-create-n8n-db.sh, provision-api.py, qualify-automation-runtime.sh,
runtime.env.example.
deploy/van-trading-core/browser: bootstrap-browser-runtime.sh, package.json,
package-lock.json, runtime.env.example.  NOTE: no worker source directory.

---

## 1. BROWSER FABRIC

### 1.1 The two adapters are thin HTTP clients to workers that do not exist in this repo

`backend/van_gateway/browser/adapters.py:55-119` `_PrivateWorkerClient` is a shared
httpx POST-JSON client. Both concrete adapters inherit it.

**Browser Harness adapter** — `adapters.py:122-191`, `CAPABILITY = "browser_harness"`
(`:125`). Endpoints it POSTs to, all relative to `base_url`:
`/navigate` (:158), `/page_info` (:161), `/click` (:164), `/fill` (:170),
`/press` (:173), `/scroll` (:176), `/screenshot` (:179), `/wait` (:182),
`/upload` (:185), `/tabs` (:188). Request envelope `adapters.py:146-155`:
`{task_id, profile_alias, mode:"PRODUCTION_ACTUATOR", allow_helper_authoring:false, ...}`.
Response contract: any JSON object (`dict(response.json())`, :105). No schema check.

**Stagehand adapter** — `adapters.py:194-297`, `CAPABILITY = "stagehand"` (:202).
Endpoints: `/observe` (:247), `/extract` (:257), `/act` (:272), `/agent` (:289).
Envelope `adapters.py:235-244`: `{task_id, profile_alias, model_provider, model_name,
allow_model_self_selection:false, allow_unbounded_agent_loop:false, ...}`.
Only `/observe` and `/extract` parse a typed reply (`controls`, `extraction` keys,
:248-252, :260-262); `/act` and `/agent` return raw dicts.

**No worker source exists in this repo.** Full JS/TS inventory outside node_modules is
13 files, none of them a browser worker (`hermes/mcp/owner_runtime_stdio.mjs`,
`trading/vekl/*`, `trading/commander/*`, supabase edge functions). There is no
directory named harness/stagehand/worker. What exists is only the npm install
surface: `deploy/van-trading-core/browser/package.json:9-13` pins
`@browserbasehq/stagehand 4.1.0`, `@playwright/test 1.63.0`, `zod 4.4.3` — three
libraries, no VAN worker package. `deploy/van-trading-core/browser/bootstrap-browser-runtime.sh`
creates the `van-browser` system user, npm-ci's those libs, installs chromium,
verifies pins (`:49-50`), then writes a manifest whose own field says the truth:
**`"service_state": "ENVIRONMENT_PREPARED_NOT_IMPLEMENTED"` —
`bootstrap-browser-runtime.sh:72`**. Binds are declared at
`bootstrap-browser-runtime.sh:69-70` (stagehand `127.0.0.1:9140`, harness
`127.0.0.1:9141`) and in `deploy/van-trading-core/browser/runtime.env.example:4-7`,
but nothing listens on them because nothing was written to.

**Who imports playwright.** `backend/requirements.txt:11` pins `playwright==1.63.0`.
Python importers: only `tools/google/bootstrap_notebook_consumer.py:32,37`
(a one-shot owner-session bootstrap tool, not the gateway).
`backend/van_gateway/config.py:102` marks the old profile dir "legacy; direct
Playwright is no longer used" and `backend/van_gateway/knowledge/notebook.py:638`
reports `"direct_playwright": False`. So the pinned Python playwright is **unused
by the gateway**; the browser path is Node-side via the (absent) workers.

### 1.2 Fail-closed behaviour when the worker URL is unset — YES, and in three layers

1. `adapters.py:86-90` `_assert_usable`: `not enabled` → `BROWSER_HARNESS_DISABLED` /
   `STAGEHAND_DISABLED`; `not configured` → `..._UNCONFIGURED`. Raised before any socket.
2. `configured` is `bool(base_url)` (`:83-84`); for Stagehand it additionally requires
   both `model_provider` and `model_name` (`adapters.py:229-233`) — §418, the model is
   never chosen at runtime.
3. Readiness never reads READY from configuration alone:
   `automation/external_runtime.py:129-157` — POLICY_DISABLED → UNCONFIGURED →
   CONFIGURED_EGRESS_DISABLED → (no canary evidence) CONFIGURED. READY requires a
   persisted `ReadinessEvidence` row (`:149-157`, `:169-174`), and evidence claiming
   `contains_secrets` is refused outright (`:81-84`). Version drift → VERSION_MISMATCH
   (`:158-168`).

### 1.3 End-to-end trace of a browser task

create → `POST /v1/browser/tasks` (`browser/api.py:792-828`), internal-token gated
(`api.py:153-158` via `verify_internal_control`) and feature-flag gated
(`api.py:160-162`, 503 `BROWSER_FABRIC_DISABLED`).
policy → `BrowserTaskService.create_task` (`browser/service.py:125-171`) calls
`BrowserPolicyEngine.check_task` (`browser/policy.py:97-126`) then
`assert_no_secrets(inputs)` (`service.py:147`), then INSERTs into `browser_tasks`.
adapter → **nothing in this path calls an adapter.** `browser/api.py` never imports
`adapters`; `service.py` never imports `adapters`; `subagent.py` never imports
`adapters`. The only gateway code that calls the adapters is the NotebookLM
knowledge provider (`backend/van_gateway/knowledge/notebook.py:749,914` — `stagehand.act`)
and `automation/health.py:94-108` (status probes only).
evidence → `POST /v1/browser/tasks/{id}/evidence` (`api.py:843-859`) →
`seal_evidence` (`service.py:173-223`): secret scan, injection assess, digest-only
row. Evidence is supplied **by the caller** (dom/extraction in the request body),
not captured from a live page.
verification → there is no browser verifier. `complete` (`api.py:861-873`) takes the
status the caller asserts and writes it (`service.py:225-239`).
mission binding → `api.py:814-827`, but only `if body.mission_id and self.binder is not None`.
**`app.py:179` constructs `BrowserApi(store, settings, decisions=decisions)` with no
`binder`**, so in the assembled app `mission_binding` is always `None`. The binder
method exists (`mission/binding.py:87`) and is tested (`test_mission_binding_api.py:143`),
but is not wired into the browser API.
owner → escalations reach the owner through `DecisionService.escalate`
(`api.py:333-347`) and are listed at `GET /v1/browser/escalations` (`api.py:708-746`).

### 1.4 Semantic (Stagehand) vs deterministic (Harness) routing

There is **no router**. `BrowserStrategy` (`browser/models.py:67-70`:
DIRECT_HTTP / HARNESS / STAGEHAND) is a *caller-supplied field* on `CreateTaskBody`
(`api.py:62`) and is only validated, never dispatched on: the one rule is
`policy.py:125-126` — `STAGEHAND` requires `tier.ordinal >= 2`. Nothing reads
`task.strategy` to pick an adapter. Compare `automation/router.py` (a real medium
router) — the browser side has no equivalent.

### 1.5 Domain allowlist / SSRF / profiles / secretref / downloads / injection

ENFORCED in code:
- Mutating task must target an admitted domain — `policy.py:120-124` against
  `config/browser/domains.yaml:18-23` (only `notebooklm.google.com` is admitted).
  **Non-mutating (observe/extract) tasks are NOT domain-checked** — `policy.py:122`
  is `if mutating and ...`. domains.yaml:3-4 says observe/extract are
  `discover_then_admit`, so this matches config, but it means an A1/A2 read task may
  name any domain.
- A4/A5 refused on the browser at task creation — `policy.py:108-111`.
- Profile must exist in `config/browser/profiles.yaml` — `policy.py:113`,
  `automation/policy.py:284-288`; mutation requires exactly
  `mutation: gateway_authorized_only` (`policy.py:114-118`), omission = forbidden.
- secretref: `fill_ref` refuses a value that is not `secretref://` —
  `adapters.py:168-169`; `register_profile` refuses a non-`secretref://` secret —
  `service.py:51-53`.
- Secret containment: six regexes (`policy.py:36-46`) scanned over task inputs
  (`service.py:147`), evidence dom/extraction (`service.py:185-187`) and observation
  controls/extraction (`policy.py:170-171`). Refuse, not redact (`policy.py:144-149`).
- Prompt-injection containment: 12 literal substrings (`policy.py:49-54`),
  `assess_injection` (`policy.py:151-158`) **records only** — it returns an
  assessment, it does not stop anything at this layer. The stop happens in the
  subagent loop: `subagent.py:232-236` ends the run only on
  `CONFIRMED_INJECTION`, which nothing in this repo ever sets (grep: the enum member
  `browser/models.py:173` is set nowhere outside tests). `SUSPECTED_INJECTION` from
  the scanner therefore does **not** stop a run — it is recorded on the observation
  and in evidence.
- Action-class escalation from page content is clamped, not honoured —
  `policy.py:179-181`.
- SSRF: the real SSRF guard lives on the *automation* side
  (`automation/policy.py:34-38` blocked networks, `:154-183` `check_domain`/`check_url`
  https-only + literal-IP rejection). The browser side has no URL check at all; the
  nearest thing is `subagent.py:315-333` `plausible_hostname`, which only decides
  whether a refused domain may be *shown to the owner* (rejects single-label hosts
  and literal IPs).

DOCUMENTED, NOT ENFORCED IN CODE:
- `config/browser/domains.yaml:7-17`: `prohibited` list (raw_cloud_metadata,
  unrestricted_private_network_access) and `rules` (stagehand/harness public
  listener forbidden, arbitrary_javascript_normal_interface forbidden,
  external_content_owner_authority forbidden,
  action_class_a3_a4_discovery_requires_reauthorization). `load_browser_policy`
  (`automation/policy.py:296-317`) reads only `policy_version`, `default_policy`,
  `admitted_domains` and the profiles `runtime` block — **`prohibited:` and `rules:`
  are parsed and discarded**. `GET /v1/browser/policy` re-states the prohibitions as
  a hardcoded Python list (`api.py:676-682`) rather than from config.
- Downloads: `download_policy: evidence_scoped` (`profiles.yaml:7,12`) and
  `download_default_deny` are loaded (`automation/policy.py:313`) and surfaced by the
  policy route (`api.py:667,672`), but **no code path checks them** — there is no
  download operation in the adapter surface at all.
- Uploads: `HttpBrowserHarnessAdapter.upload` (`adapters.py:184-185`) takes a
  `file_ref` and, unlike `fill_ref`, **does not validate its shape** — no
  `secretref://`/path check, no policy call.
- `HarnessMode` / `check_harness_mode` (`policy.py:130-134`): no caller in
  non-test code (the envelope asserts `allow_helper_authoring: False` to a worker
  that does not exist).


## 2. BROWSER SUBAGENT (subagent.py) — real state machine, tested, but no worker

`SubagentAssignment` (`subagent.py:63-87`) is the bound set: `turn_id`, `command_id`,
`task_id`, `goal`, `allowed_domains`, `action_class_ceiling` (default A2),
`autonomy_tier` (default L4), `max_steps` (`Field(default=12, ge=1, le=50)`, :80),
`deadline_ms`, `max_steps_without_progress` (`ge=1, le=10`, :83). `goal_digest`
(:85-87) is what goal-drift is compared against.

`BrowserSubagentRunner.run` (`subagent.py:162-256`) is a real loop with pre-flight and
per-step enforcement:
- pre-flight tier check (`:171-177`) → SCOPE_VIOLATION on refusal;
- pre-flight A4/A5 ceiling refusal (`:178-185`) → ACTION_CLASS_VIOLATION;
- deadline check each iteration (`:194-195`) → DEADLINE_REACHED;
- worker exception → WORKER_ERROR (`:199-203`, `:215-219`);
- `_check` before execution (`:208-211`, body `:258-278`): domain not in
  `allowed_domains` → SCOPE_VIOLATION; class rank above ceiling →
  ACTION_CLASS_VIOLATION; restated goal digest mismatch → GOAL_DRIFT;
  `assert_not_automated_payment` → PAYMENT_REFUSED;
- observation sanitized post-execution (`:223-236`); stagnation counter →
  NO_PROGRESS (`:250-252`); loop exit → BUDGET_EXHAUSTED (`:256`).
All ten stop reasons (`SubagentStop`, `:48-60`) are terminal — the docstring at `:49`
("none escalates") is accurate for the runner; escalation is decided one layer up.

Escalation to WAITING_FOR_OWNER is in `browser/api.py`, not the runner:
`classify_boundary` (`subagent.py:336-375`) is a pure function deciding
POLICY_FORBIDDEN (payment/injection/A4-A5 request) vs AMBIGUOUS_OR_UNSAFE (goal drift,
unparseable delta, implausible hostname) vs OWNER_EXTENSION_REQUIRED. Only the last
becomes an owner question (`api.py:293-296`). Then `api.py:280-389` creates a
`decisions.escalate` record, inserts `browser_escalations` with an idempotency key
that includes the *requested delta digest* (`api.py:311-312` — the comment at :308-310
records a real prior collision bug), releases the profile lease (`api.py:330`,
`:234-251`), and sets the task to WAITING_FOR_OWNER (`api.py:374-378`).
24h TTL at `api.py:191`.

Resume with scoped authorization is real: `_sync_waiting_owner_decision`
(`api.py:472-585`) checks expiry *before* the decision (`api.py:496-516`), rejects an
approved A4/A5 even if a row somehow carries one (`api.py:531-550`), and mints a
`browser_scope_authorizations` row with the approved domains/ceiling
(`api.py:551-565`) then sets RESUME_AUTHORIZED. `_enforce_resume_authorization`
(`api.py:588-617`) requires an ACTIVE authorization, requires the new assignment's
domains to be a subset and its ceiling ≤ approved, and marks the authorization
CONSUMED (single use).

**But the loop cannot run in the assembled app.** `run_assignment`
(`api.py:875-953`) returns 503 `BROWSER_WORKER_UNCONFIGURED` when `self.worker is None`
(`api.py:888-889`), and `app.py:177-179` constructs `BrowserApi` with no worker and
says so in a comment: *"No worker is configured: the semantic worker is a separate
private service and the gateway refuses an assignment rather than pretending to run
one."* No `SubagentWorker` implementation exists outside tests
(`backend/tests/test_browser_subagent.py:54,69`, `test_browser_api.py:56`).
Note also that `StagehandAdapter.agent()` (`adapters.py:274-294`), whose docstring says
"`BrowserSubagentRunner` is the supported caller", is never called by the runner — the
runner talks to an abstract `SubagentWorker` Protocol (`subagent.py:137-148`) and no
adapter implements it.

Tests: `backend/tests/test_browser_subagent.py` (fake workers, all stop reasons),
`backend/tests/test_browser_api.py` (route-level escalation/resume with a fake worker).

## 3. AUTOMATION / n8n

### 3.1 n8n_client.py — a real REST client

`N8nManagementClient` (`n8n_client.py:39-183`) is genuine httpx against the n8n public
API with `X-N8N-API-KEY` (`:107`). Calls: `POST /workflows` (`:134`),
`PUT /workflows/{id}` (`:141`), `POST /workflows/{id}/activate` (`:144`),
`/deactivate` (`:147`), `GET /workflows/{id}` (`:150`), `GET /executions/{id}` (`:153`),
`POST /workflows/{id}/run` (`:157`), `GET /settings` for version (`:162`).
**`POST /workflows/{id}/run` is not a real n8n public-API endpoint** (n8n exposes
`/workflows/{id}/activate`, executions, etc.; there is no documented synchronous run
route) — this is the "gateway-adapter invocation" of §159 and would need a custom
n8n-side receiver, which does not exist in the repo.
Fail-closed: disabled → `AUTOMATION_FABRIC_DISABLED` (`:76`); unconfigured →
`AUTOMATION_FABRIC_UNCONFIGURED` (`:78`); a globally-routable management host →
`AUTOMATION_MANAGEMENT_HOST_NOT_PRIVATE` (`:81-100`, using `is_global` rather than
`not is_private`, correctly). Bounded retry, 3 attempts (`:43-45`, `:110-129`) — note
`time.sleep` (`:128`) inside an async method, a blocking-loop bug.

### 3.2 Compiler — genuine deterministic synthesis, not template expansion

`AutomationCompiler.compile` (`compiler.py:83-153`) walks an IR: resolves each
primitive through a versioned `NODE_MAP` (`compiler.py:29-50`), enforces the node
allowlist per node (`compiler.py:96` → `policy.NodeAllowlist.check`,
`automation/policy.py:138-142`), resolves credential *aliases to n8n credential ids*
and refuses an unresolved alias (`compiler.py:103-107`), builds parameters per
primitive (`compiler.py:177-212`, including an HTTP method allowlist at `:183-184` and
forced `authentication: headerAuth` on webhooks at `:193`), compiles connections with
branch slots (`compiler.py:214-236`), computes the semantic digest, and only then adds
canvas positions so layout cannot change the digest (`compiler.py:133-136`,
`:244-251`). That is real compilation. Templates are a *separate*, optional input path.

**Node allowlist is enforced in two places**: at compile (`compiler.py:96`) and in the
validator. `config/automation/node_allowlist.json` is the source
(`automation/policy.py:209-220`); deny-by-default (`policy.py:138-142`).

### 3.3 templates.py — four skeletons, deterministic specialisation

`WorkflowTemplate.specialise` (`templates.py:67-132`) binds `{{hole}}` placeholders
(`_substitute`, `:159-176`), refuses a missing required hole
(`templates.py:142`), an out-of-enum value (`:145-148`) and an unknown binding
(`:151-155`), and derives the action class from the steps rather than trusting the
template's claim (`templates.py:127`). The library is exactly four templates
(`templates.py:424-432`): `collect_normalise_ingest.v1`, `monitor_diff_notify.v1`,
`event_filter_emit.v1`, `fetch_map_verify.v1`, mapped from six goal classes
(`templates.py:435-442`). So the WARM path can compile exactly those shapes.

### 3.4 COLD — real plan/validate pipeline, but the only shipped proposer is the template one

`ColdGenerationPlanner.generate` (`cold.py:198-276`): payment refusal before any
proposal (`:209-216`), parallel retrieval of primitives/nodes/domains/patterns
(`cold.py:156-194`), proposer call, recomputation of the action class from steps
(`:237-247`), full validation (`:249`), then auto-admit only for A1/A2 when policy
allows (`:264-272`). Honest. But `IRProposer` (`cold.py:120-126`) is a Protocol and
the only implementation is `TemplateBackedProposer` (`cold.py:285-345`), which just
specialises the same four templates and gives up (`return None`) on any hole it
cannot infer (`cold.py:337-344`). `POST /v1/automation/generate` hard-wires it:
`api.py:340` `proposer=TemplateBackedProposer(self.templates)`, and the body docstring
says so (`api.py:84` "the gateway ships only the deterministic proposer").
`PatternSource` (`cold.py:129-133`, VEKL/corpus) has **no implementation** —
`planner.patterns` is never set in `api.py:165-...`. So COLD ≡ WARM in practice:
a novel goal outside the six goal classes yields `NO_PROPOSAL`.

### 3.5 Verification — logic is real, but no observer is ever registered

`WorkflowVerifier.verify` (`verifier.py:65-139`) implements VERIFIED / FAILED /
PARTIAL / UNVERIFIABLE honestly: no postcondition → UNVERIFIABLE (`:75-82`), no
observer for the spec kind → UNVERIFIABLE (`:84-90`), observer exception →
UNVERIFIABLE (`:92-99`), postcondition absent → FAILED even when the engine said
success (`:101-109`), incomplete correlation → PARTIAL (`:121-131`).
`DocumentUploadObserver` (`:142-149`) and `NotificationObserver` (`:152-159`) are
constructor wrappers around a caller-supplied `lookup` callable — **neither has a
caller anywhere in the repo**. `AutomationDispatcher` defaults to
`WorkflowVerifier()` with an empty observer map (`dispatch.py:98`) and `app.py:160-168`
passes no `verifier`, so in the assembled app **every dispatch verification returns
UNVERIFIABLE** and no run can ever reach `owner_success == True`
(`dispatch.py:70-73`, `:222-227`). That is fail-closed and honest, but it means the
verification layer is unexercised end to end.

### 3.6 Dispatch — real orchestration

`AutomationDispatcher.dispatch` (`dispatch.py:104-263`): feature flag (`:121-122`),
admitted-artifact gate (`:127-130`), run row, Action-Runtime authority
(`:144-162`) with the dispatcher deliberately holding no judgement, run-scoped grant
mint (`:173-177`, `_mint_grant` `:267-284`), invoke (`:182`), engine result →
verification (`:203-211`) → receipt (`:212-221`) → health (`:237-249`) → telemetry
(`:250-257`). `_invoke` (`dispatch.py:286-...`) refuses an undeployed artifact
(`:294-295`) and refuses unless the n8n runtime status is READY (`:296-299`), i.e.
unless a live canary has recorded evidence.

### 3.7 Reachability from an owner command path

`/v1/automation/*` and `/v1/browser/*` are both `x-van-internal-token` gated
(`automation/api.py:222` etc., `browser/api.py:153-158`). `app.py:299-300` mounts both.
Nothing in the Hermes/owner-command path calls them: the dispatcher requires a sealed
`command_id` + `action_id` that the Action Runtime authorizes (`dispatch.py:144-162`),
so an owner command *could* flow through, but no caller in this repo issues
`POST /v1/automation/execute`. The browser fabric has no owner path at all beyond the
internal API.

## 4. AutomationMediumRouter (router.py)

Media: `ExecutionMedium` (`router.py:34-42`) = NATIVE, N8N_HOT, N8N_WARM,
WORKFLOW_COMPILER, BROWSER_HARNESS, BROWSER_SEMANTIC, TEMPORAL, REFUSED.
Decision order in `route` (`router.py:115-210`): payment refusal (`:117-123`) → A5
refusal (`:124-128`) → critical_durable ⇒ TEMPORAL (`:131-138`) → web_only ⇒
BROWSER_HARNESS if a known capsule id else BROWSER_SEMANTIC (`:141-151`) → HOT index
lookup with a health check that *withdraws* a degraded capability rather than only
refusing (`:154-179`) → NATIVE, optionally compiling in the background (`:183-197`) →
WARM template (`:200-205`) → COLD (`:208-210`). `_fallback` (`:221-246`) degrades
HOT → NATIVE → WARM → COLD.

**The TEMPORAL detail** — `router.py:131-138` returns
`medium=TEMPORAL, reason=CRITICAL_DURABLE_PROCESS` with
`detail="Temporal is stack-locked at adoption phase 11 and not yet built; use a
native VAN state machine until it is (§6 fallback)"`. It is *not* a refusal and not a
fallback: the router hands back a medium that has no executor, and the caller
(`automation/api.py:190-...` `/route`) simply returns it. Note also that browser
routing at `:141-151` returns a medium for which, as §1 shows, no worker exists.

## 5. TEMPORAL — classify: ABSENT (stack-lock entry + a version assertion only)

Whole-repo grep for temporal/temporalio finds **no client, no worker, no workflow
definition, no activity, no docker service**:
- `backend/van_gateway/automation/router.py:41,133-138` — enum member + the
  "not yet built" detail above;
- `backend/van_gateway/automation/models.py:23` — `WorkflowEngine.TEMPORAL` enum member;
- `backend/van_gateway/mission/service.py:3` — a docstring mention;
- `deploy/van-trading-core/requirements-vm.txt:13` — `temporalio==1.33.0` pinned;
- `deploy/van-trading-core/browser/bootstrap-browser-runtime.sh:55-58` — imports
  `temporalio` solely to `assert temporalio.__version__ == '1.33.0'`, then writes
  `"temporalio": "1.33.0"` into the manifest (`:68`);
- `deploy/van-trading-core/browser/runtime.env.example:14-19` —
  `VAN_TEMPORAL_ENABLED=0`, empty address, and the comment *"No local Temporal server
  is implied."*;
- `deploy/van-trading-core/qualify.sh:28` — the qualify gate greps the manifest for
  `.temporalio=="1.33.0"` and prints "Temporal 1.33.0" GREEN. **This is the one place
  the absence could read as presence**: a GREEN `browser_runtime` line meaning
  "the pinned library version is installed", displayed as a runtime capability.
  `docs/PRODUCTION_ACCEPTANCE_LEDGER.md:123` and
  `artifacts/runtime/van_trading_core_reconciliation_live_attestation.json:20`
  carry the same string.
- `trading/architecture/stack_lock.json` — the adoption-phase-11 lock entry.

## 6. Computer Interaction Fabric (computer_use/fabric.py) — vocabulary + ledger, no executor

Typed operation set (`fabric.py:46-83`): NAVIGATE, READ, EXTRACT, CLICK, TYPE_TEXT,
FILL_FROM_REFERENCE, SELECT, SCROLL, SCREENSHOT, UPLOAD_FROM_REFERENCE,
DOWNLOAD_TO_EVIDENCE, WAIT_FOR_CONDITION — with no RUN_ARBITRARY/EXECUTE/EVAL, which
is the stated point (`:47-52`). Surfaces: BROWSER/DESKTOP/TERMINAL/MOBILE (`:37-43`).
Real refusals in `begin` (`:122-170`): A4/A5 never on this fabric (`:130-135`);
class above the per-type ceiling (`:136-144`); a mutating op with
`verifier_type == "NONE"` (`:145-149`); empty target (`:150-151`).
`complete` refuses to mark a mutation COMPLETED without an evidence ref (`:199-200`).
**Nothing executes an operation.** `begin` inserts a `computer_operations` row and
returns an id; `checkpoint`/`complete`/`for_mission` are pure DB. There is no
dispatch to any surface worker, and the desktop/terminal/mobile surfaces have no
backing code anywhere in the repo. It is an admission ledger plus a vocabulary.

## 3.8 Standing authority, grants, HOT/WARM/COLD, dead letters, repair, telemetry, health

REAL (cryptographic / stateful), not bookkeeping:
- **Run grants** `grants.py`: HMAC-SHA256 over a canonical grant string with a nonce
  (`grants.py:23,111-130`), single-use or bounded-use nonce rows in
  `automation_run_nonces` (`:183-192`), `hmac.compare_digest` on redeem (`:225`), and
  a liveness re-check of the *source* authority — a revoked or expired standing
  authority invalidates an already-minted grant at redeem time
  (`grants.py:307-334`). **Fails closed only if the key is set**:
  `configured` is `bool(self._signing_key)` (`:118-119`) and
  `Settings.automation_grant_signing_key` defaults to `""` (`config.py:64`), so
  as shipped grants are unconfigured and dispatch raises
  `AUTOMATION_GRANTS_UNCONFIGURED` (mapped to 503 at `automation/api.py:402`).
- **Standing authority** lives outside this package —
  `backend/van_gateway/command/standing.py:111` `StandingAutomationAuthorityService`,
  wired at `app.py:174` and exposed via `POST /v1/automation/standing-intents`
  (`automation/api.py:475`) and `.../disable` (`:541`). Payments can never carry one
  (payment boundary + `docs/decisions/VAN-ADOPT-N8N-001.yaml` `standing_authority:
  PROHIBITED`, asserted by `tests/contracts/test_automation_browser_governance.py:67`).
- **HOT/WARM/COLD**: HOT is an in-process dict index (`registry.py:261` `HotWorkflowIndex`,
  published only from an admitted artifact, `automation/api.py:452-458`); WARM is the
  four templates; COLD is §3.4 above. The ladder is real as a routing mechanism.
- **Dead letters** `deadletter.py:68-164`: `automation_dead_letter` rows with a
  `NextAction` classification and an unresolved-count query. Real persistence,
  no automatic drain loop.
- **Repair lineage** `repair.py`: `decide()` (`:98-129`) is a pure classifier,
  `RepairService.open/promote` (`:189`, `:216`) persist repair records tied to a
  capability version. Bookkeeping plus a decision function; no automatic re-compile
  is triggered anywhere.
- **Telemetry** `telemetry.py:120-231`: real rows in `automation_run_telemetry` and
  `automation_generation_telemetry`, plus a `LadderMetrics` aggregation and a
  percentile helper (`workflow_health.py:352`). Written from `dispatch.py:250-257`.
- **Workflow health** `workflow_health.py:101-350`: GREEN/…/status per capability
  version, consumed by the router to withdraw a degraded capability
  (`router.py:165-177`, `:212-219`). Genuinely closes the loop.
- **External events** `events.py:83-216`: HMAC-verified signed ingress
  (`:123-126`) with dedupe keys. Real.

## 3.9 As-shipped configuration makes most of this inert

- `config/automation/domains.yaml:13` — **`external_domains: {}`**. `DomainPolicy.admitted`
  is therefore empty (`automation/policy.py:228-233`), so `check_domain` denies
  **every** domain (`policy.py:162-163`). No compiled workflow can legally target any
  external host as shipped.
- That in turn makes COLD unreachable: `TemplateBackedProposer._infer_bindings`
  returns `None` when `not context.admitted_domains` (`cold.py:321-322`).
- `config/browser/domains.yaml:18-23` admits exactly one domain
  (`notebooklm.google.com`), and only for mutation checks.
- `Settings.automation_enabled = False` (`config.py:58`) and
  `browser_enabled = False` (`config.py:69`) — both fabrics ship off.
- `automation_n8n_api_key = ""` (`config.py:62`), `automation_grant_signing_key = ""`
  (`config.py:64`), `browser_stagehand_model_provider/name = ""` (`config.py:74-75`).
  Note `browser_harness_base_url`/`browser_stagehand_base_url` default to non-empty
  loopback URLs (`config.py:70,72`), so `configured` is True by default for the
  harness — only `enabled=False` holds it shut.

## 3.10 Payments boundary (payments.py) — the strictest layer in scope

`payments.py` enforces two separable rules (`:10-19`). Detectors: 10 instrument
patterns (PAN, CVV, expiry, IBAN, sort code, account/routing number, Stripe/PayPal
secrets, payment tokens — `:42-55`), a carefully-scoped payment-intent regex that
deliberately does *not* fire on a bare "pay" (`:57-80`, with the reasoning at
`:59-63`), an instrument-persistence regex (`:82-97`), a payment-provider host list
(`:99-108`) and provider path fragments (`:110-114`).
`assert_not_automated_payment` is called from six independent places, which is why
this reads as a boundary rather than a check: `router.py:118` (routing),
`cold.py:210` (before any generation), `subagent.py:272` (per proposed action),
`adapters.py:268` (`stagehand.act`), `adapters.py:287` (`stagehand.agent`), and the
validator. This is the one control in scope that is enforced at every layer.

---

## 7. Certification tools

### `tools/certification/certify_browser_fabric.py`
Four canaries (`:272-277`): harness, profile, stagehand, injection.
`--canary harness` (`:90-130`) would, against a live worker: register the
`public_research` profile (`:93`), create an L1/A2 HARNESS task (`:94-98`), then
`adapter.navigate` → `page_info` → `screenshot` (`:101-103`) against
`https://<target>/`; on any `BrowserAdapterError`/`BrowserPolicyError` print FAIL and
**return 1 without recording anything** (`:104-106`); on success seal digest-only
evidence (`:108-111`), record a `ReadinessEvidence` row for capability
`browser_harness` (`:113-118`) — which is what lets `/v1/browser/health` report READY
— and write the receipt.
**Evidence file:** `artifacts/runtime/van_browser_harness_attestation.json`
(`:119-127`, dir `:50`). The other canaries write
`van_browser_profile_attestation.json` (`:169`), `van_browser_stagehand_attestation.json`
(`:219`), `van_browser_injection_attestation.json` (`:259`).
The profile canary is notably honest: a restored session with no observable
non-secret `account_identity` is a FAIL (`:152-156`), and a secret-shaped observation
is a FAIL (`:159-162`). The stagehand canary fails if zero controls come back —
"generation did not occur" (`:201-203`).

### Exit code 2 = fail-closed, and CI asserts it
`certify_browser_fabric.py:288-292`: `VAN_BROWSER_ENABLED` false → print BLOCKED,
`return 2`, nothing recorded. Same shape at
`certify_automation_runtime.py:203-207` for `VAN_AUTOMATION_ENABLED`.
`.github/workflows/van-ci.yml:48-64` runs both and asserts:
`test "$automation_status" -eq 2` (`:61`), `test "$browser_status" -eq 2` (`:62`),
plus `test ! -f artifacts/runtime/van_automation_n8n_readiness_attestation.json`
(`:63`). The comment at `:52-54` states the intent: "anything else means a default
flipped on." **Confirmed.** CI also runs a named subset of the fabric tests at
`van-ci.yml:40-47`.
`certify_automation_runtime.py --check readiness` (`:69-104`) does a real
`GET /settings` version comparison against the manifest and refuses on drift
(`:80-83`) before recording evidence.

## 8. Deployment

`deploy/van-trading-core/automation/docker-compose.yml` — three services:
`postgres:${POSTGRES_VERSION}` (`:4-29`), `n8n:${N8N_VERSION}` (`:31-110`),
`n8n-runner` (`:112-143`). Hardening that is real and worth naming:
- n8n published only on loopback: `ports: "127.0.0.1:5678:5678"` (`:96`);
- two networks, the inner one `internal: true` (`:145-150`), so only n8n gets egress;
- `no-new-privileges:true` on all three (`:25-26`, `:106-107`, `:139-140`);
- `mem_limit`/`cpus`/`pids_limit` on all three (`:27-29`, `:108-110`, `:141-143`),
  driven by `runtime.env.example:9-16`;
- community/unverified packages off (`:77-78`), env access blocked in nodes (`:79`),
  file access restricted to `/files` (`:81`), n8n's own SSRF protection on with the
  same `default,100.64.0.0/10` list the gateway uses (`:85-86`), and
  `NODES_EXCLUDE: ["n8n-nodes-base.executeCommand","n8n-nodes-base.readWriteFile"]`
  (`:87`) — which mirrors `config/automation/node_allowlist.json:15-19` (that file
  additionally denies `.ssh`, which NODES_EXCLUDE does not).
- Telemetry/diagnostics off (`:73-76`), execution data pruned (`:64-66`).
**No browser service exists in any compose file** — the browser runtime is a host
bootstrap script only, and it stops at "environment prepared".
Resource policy `config/automation/resource_policy.yaml` states
`canonical_numbers_in_repository: false` and `deployment_evidence_required: true`
(`:14-17`) with `degrade_before_vati: true` (`:19`) — i.e. the numbers in
`runtime.env.example` are explicitly marked `PROVISIONAL` (`:17`).

**Secrets: none in the repository.** All four n8n secrets are docker `secrets:`
entries backed by files under a required env var
(`docker-compose.yml:159-167`, `${VAN_AUTOMATION_SECRETS_DIR:?...}/{postgres_admin_password,
n8n_db_password, n8n_encryption_key, n8n_runner_auth_token}`), read at runtime via
`*_FILE` env vars (`:9`, `:48`, `:49`) or `cat /run/secrets/...` in the entrypoint
(`:40`, `:121`). `config/automation/credentials.yaml.example` contains
`credential_aliases: {}` and class rules only — no values. The only tracked files
matching secret-ish names are `.example` files and Kotlin key-manager source. Shape
only; no values observed or reproduced.

## 9. Test results (`python3 -m pytest -q -p no:cacheprovider`)

| Suite | Result |
|---|---|
| `backend/tests/test_browser_api.py`, `test_browser_escalation_boundary.py`, `test_browser_fabric.py`, `test_browser_subagent.py` | **86 passed** (12.8s) |
| `backend/tests/test_automation_{api,compiler,dispatch,health_api,hot_warm_cold,operations,run_grants,security_contracts}.py` | **184 passed** (23.5s) |
| `tests/contracts/test_automation_browser_governance.py` (repo root, NOT backend/) | **18 passed** (0.10s) |
| `trading/tests/test_stack_lock.py` | **7 passed** (0.01s) |
| **Total in scope** | **295 passed, 0 failed, 0 skipped** |

Caveat on what the green means: every browser test drives a **fake** worker
(`test_browser_subagent.py:54,69`, `test_browser_api.py:56`) or a mocked
`httpx.MockTransport`; every automation dispatch test supplies its own
`WorkflowVerifier({...})` observer (`test_automation_dispatch.py:108`,
`test_automation_api.py:664`) that the production wiring does not. And
`tests/contracts/test_automation_browser_governance.py` is a **documentation
assertion suite** — it greps `docs/decisions/*.yaml` and `docs/SECURITY_POLICY.md`
for strings (`:54-59`, `:65-67`, `:73-75`, `:105-107`) and sha256-pins the security
policy (`:110-118`). It proves the governance text says the right things; it exercises
no fabric code.

## 10. Classification

| Component | Class | Basis |
|---|---|---|
| Browser Harness adapter | **IMPLEMENTED_BUT_ISOLATED** | Real httpx client, 10 typed endpoints, fail-closed (`adapters.py:122-191`), but the worker it targets does not exist in this repo and no gateway task path calls it (only `knowledge/notebook.py` and `health.py`). |
| Stagehand adapter | **IMPLEMENTED_BUT_ISOLATED** | Same (`adapters.py:194-297`); `act`/`agent` reachable only from `knowledge/notebook.py:749,914` and tests. |
| Browser policy / injection containment | **PARTIAL** | Secret scan, action-class clamp, profile/mutation/domain checks and A4 refusal are enforced (`policy.py:97-185`). Injection detection only *records* (`policy.py:151-158`); the stop condition is `CONFIRMED_INJECTION` (`subagent.py:232`), which nothing sets. `prohibited:`/`rules:` in `config/browser/domains.yaml:7-17` are parsed and discarded. Downloads and `check_harness_mode` have no enforcement caller. `upload` does not validate its `file_ref`. |
| Browser subagent / escalation | **IMPLEMENTED_BUT_ISOLATED** | Full bounded state machine + durable escalation + scoped single-use resume + 86 passing tests, but `app.py:177-179` wires no worker and `api.py:888-889` returns 503; `binder` is also not wired, so mission binding is dead in the assembled app. |
| n8n client | **IMPLEMENTED_BUT_ISOLATED** | Real REST + private-host + version-drift enforcement (`n8n_client.py`), never exercised live (CI proves it refuses). `POST /workflows/{id}/run` has no upstream counterpart. |
| Workflow compiler | **INTEGRATED** (within the fabric) | Genuine deterministic IR→n8n synthesis with allowlist and digest stability (`compiler.py`), reachable via `POST /v1/automation/compile`, 184 passing tests. Not E2E: nothing has been deployed to a live n8n. |
| Standing automation | **PARTIAL** | Authority service, signed grants and revocation-at-redeem are real (`grants.py:307-334`), but `automation_grant_signing_key` is empty by default (`config.py:64`) and no scheduler/event loop in this repo fires a standing run. |
| Temporal | **ABSENT** | No client/worker/workflow/service anywhere. Two enum members, one "not yet built" string (`router.py:135`), a pinned library and a version assertion in a bootstrap script. `qualify.sh:28` reports it GREEN. |
| Computer-use fabric | **STUB** (typed vocabulary + ledger) | Real refusals and a DB table, zero execution (`computer_use/fabric.py:122-239`). No surface worker for BROWSER/DESKTOP/TERMINAL/MOBILE. |
| Certification | **INTEGRATED** (as a fail-closed gate) | Both tools run in CI and their exit-2 refusal is asserted (`van-ci.yml:61-62`). The live canary paths themselves are unexecuted — every external gate row reads PENDING_LIVE (`docs/EXTERNAL_GATES.md:48-61`). |

Nothing in scope is **E2E_VERIFIED**, and the repository says so itself:
`docs/EXTERNAL_GATES.md:44` — "Approval authorizes the architecture; it does **not**
certify a live runtime."

## 11. Stubs / TODO / "not yet" / synthetic markers in scope

Explicit textual markers are remarkably few — only two in 9,301 lines of in-scope
Python:
1. `backend/van_gateway/automation/router.py:135` — "Temporal is stack-locked at
   adoption phase 11 and **not yet built**".
2. `backend/van_gateway/automation/n8n_client.py:9` — "nothing silently **no-ops**"
   (a docstring describing correct behaviour, not a marker).

Outside Python:
3. `deploy/van-trading-core/browser/bootstrap-browser-runtime.sh:72` —
   `"service_state": "ENVIRONMENT_PREPARED_NOT_IMPLEMENTED"` — the single most
   load-bearing admission in scope.
4. `deploy/van-trading-core/automation/runtime.env.example:8,17` — `PROVISIONAL`
   resource envelope; echoed at `qualify-automation-runtime.sh:55`.
5. `registries/automation_browser_dependencies.json:11,19,29,37` — four
   `"pin_status": "UNPINNED_VERIFY_AT_ADOPTION"` entries (n8n, stagehand,
   browser_harness, postgres) with `image_digest: null` (`:7`) and `commit: null`
   (`:24`). Only playwright and node are `PINNED` (`:44,51`).
6. `docs/decisions/VAN-ADOPT-{BROWSER-HARNESS-001:42, N8N-001:52, STAGEHAND-001:60}.yaml`
   — same `UNPINNED_VERIFY_AT_ADOPTION`.
7. `docs/EXTERNAL_GATES.md:48-61` — 14 gate rows, every one PENDING_LIVE or
   REPO_COMPLETE/PENDING_LIVE. `:59` explicitly calls the injection tests
   "**synthetic** policy tests".

Unmarked structural stubs (no comment says so — these are the ones to watch):
8. `backend/van_gateway/browser/adapters.py` — the entire worker contract; no
   implementation, no OpenAPI/schema file, no fixture describing the reply shape.
9. `backend/van_gateway/automation/verifier.py:52-56,142-159` — `PostconditionObserver`
   Protocol and both concrete observers have **no caller**; `dispatch.py:98` +
   `app.py:160-168` give the dispatcher an empty observer map, so every production
   verification is UNVERIFIABLE.
10. `backend/van_gateway/automation/cold.py:129-133` — `PatternSource` (VEKL/corpus
    retrieval) has no implementation and is never passed to the planner.
11. `backend/van_gateway/automation/cold.py:120-126` — `IRProposer`; the only
    implementation is the four-template one (`api.py:340`).
12. `backend/van_gateway/browser/subagent.py:137-148` — `SubagentWorker` Protocol,
    implemented only in tests.
13. `config/automation/domains.yaml:13` — `external_domains: {}`; an empty allowlist
    that silently makes every compiled workflow undeployable against any host.
14. `backend/van_gateway/browser/api.py:814-827` vs `app.py:179` — mission binding
    code with no binder wired.
15. `backend/van_gateway/computer_use/fabric.py` — whole module: typed vocabulary and
    a `computer_operations` ledger with no executor.
16. `backend/van_gateway/automation/n8n_client.py:128` — blocking `time.sleep` inside
    an `async def` retry loop (bug, not a stub, but it stalls the event loop).
