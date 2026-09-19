# VAN Whole-System Implementation Audit and Certification — Rev 1

**Audit authority:** repository-first, implementation-first, runtime-evidence-first.
**Repository:** `Vanguduza/Van`
**Branch audited:** `claude/van-system-audit-ysgtcd`
**HEAD at audit:** `dff38a030367e640c6621ea80dab794b2c5c55b7` (identical tree to `origin/main`)
**Declared version:** `0.5.0-dev` (`VERSION`)
**Audit date:** 2026-09-18
**Audit method:** repository inspection, in-process runtime probes of the real FastAPI application, full
Python test execution, static call-graph tracing, and inspection of committed visual artefacts.
**Production code changed by this audit:** none. Every artefact written by this audit lives under
`docs/` and `evidence/van-system-audit/`.

---

## 0. How to read this document

Every capability in this report carries exactly one maturity class. The classes are not interchangeable
and are never collapsed into "implemented":

| Class | Meaning in this audit |
|---|---|
| **ABSENT** | No implementation exists. |
| **STUB** | A type, interface or signature exists with no implementation behind it. |
| **SIMULATED** | Code returns a plausible result without performing the real effect. |
| **PARTIAL** | Real implementation covering part of the contract. |
| **IMPLEMENTED_BUT_ISOLATED** | Real, tested implementation that no production code path invokes. |
| **INTEGRATED** | A production path invokes it on a real request. |
| **E2E_VERIFIED** | An automated or recorded test drives the whole owner journey through it. |
| **PRODUCTION_CERTIFIED** | E2E verified against live external systems with recorded token-free evidence. |

Two distinctions are held throughout and never substituted for one another:

- **NOT IMPLEMENTED** — the repository proves the capability does not exist.
- **NOT VERIFIED** — the capability exists in code but this environment could not exercise it.

Where this audit could not reach a live dependency (the Hermes runtime on `dial-hermes-control`, the
Oracle trading VM, a physical Samsung device, Google's live APIs, the Browser Fabric workers, a live n8n
instance), the finding says **NOT VERIFIED** and names the missing dependency precisely.

---

## 1. Executive verdict

**VAN is a rigorously engineered owner-authority and evidence layer wrapped around an intelligence that
lives in another repository, with a presentation layer that cannot currently observe what that
intelligence does.** It is not a collection of disconnected features under one skin — the module
boundaries are principled and the deterministic core is genuinely strong. It is also not yet one
continuous intelligence, because the artefact that would make it continuous does not exist.

**Overall production readiness: 4.2 / 10. NOT PRODUCTION CERTIFIED. NOT v1.0.**
This agrees with the repository's own `PROJECT_CANONICAL_STATE.json`, which already sets
`release_blocked: true` at version `0.5.0-dev`.

**The single most important finding.** A runtime probe submitted the ten canonical owner intents to the
real gateway with a real paired device and real signatures. All ten authenticated, authorised and
dispatched correctly. Afterwards `GET /v1/missions` returned `[]`, `GET /v1/activity` returned no
missions, and `GET /v1/commands/{id}` does not exist. **The owner's intent enters the system, is
verified and forwarded, and then leaves VAN's model of the world entirely.** Nothing records that work
is in flight, nothing returns a result, and nothing can tell the difference between a command that
succeeded and one that was silently never executed.

**Five statements that summarise the system's truth:**

1. **The authority layer is production-grade.** Three-layer device authentication, an A4 path that
   refuses to let free text become an approvable destructive action, payment refusal at six independent
   layers, four non-collapsible Google credential planes, and a trading order path with exactly one
   funnel and no model anywhere near it. These were verified by probe, not by reading.
2. **The cognition layer is real code with no callers.** Twenty classes across context, epistemics,
   reasoning, understanding, evolution and autonomy are implemented and tested, and nothing in
   production invokes them. The Critical Reasoning Kernel does not reason: a probe stored a fabricated
   fact with an invented source, zero critic findings and 0.99 confidence as an actionable assessment.
3. **Verification is asserted, not performed.** A probe drove a mission to `VERIFIED_SUCCESS` on a
   receipt reading `verifier_version: "i-say-so/1.0"` with the single evidence reference
   `evidence://trust-me`. No server-side verifier executes.
4. **Two security boundaries are crossed today.** One static internal token mints owner-device
   credentials and is deliberately provisioned to a model-driven Hermes. Separately, any application's
   notification becomes a device-signed owner command labelled `CONVERSATION`, so the prompt-injection
   screen never fires.
5. **The visual system is better than its evidence.** The aura is a genuine detached field with a
   tested non-ring invariant and correct priority arbitration — but every committed image was rendered
   by a painter that diverges from the shipping one, omits the electrical layer entirely, and is two
   authority revisions stale.

**Fifteen P0 findings, and every one of them is repository-side** — none needs an external dependency to fix. The open
external gates — a physical device, a named tunnel, live Google credentials, browser workers, a broker
account, a `.riv` asset — are real, but they are not what stands between VAN and coherence.

**Six root causes explain the register's 55 findings** (§32), and the remediation programme in §35 orders them
by dependency: correct the documentation, contain the two security paths, give work a durable identity,
make verification execute, wire cognition to a producer and consumer, then publish a semantic state bus.
No new framework and no rewrite is required. The architecture is largely right; what is missing is the
wiring between the layers it correctly separated — and the discipline of not describing that wiring as
finished before it exists.

**The most encouraging finding:** the project's own governance documents already forbid every mistake
this report identifies. The gap is not one of judgement. It is one of enforcement.

---

## 2. Repository state inspected

### 2.1 Lineage

```
dff38a0  Unified Personal Intelligence: Mission Core, capability registry, cognition layer (#39)
5ec35e9  Android unit tests get a real org.json, not the stub that throws
0249ef0  Execution binds itself to Missions, and an honest integration ledger
04e24db  Relationship calibration: style adapts, truth standards do not
2b876b5  Android data layer for the six owner surfaces (UNVERIFIED IN CONTAINER)
9a03a44  Permissions, computer use, verifiers: backend complete at 32/36
10fcc9c  Cognition, autonomy and evolution: 23 workstreams
f8c3fcc  Refactor Android dashboards to summary-first drill-down navigation (#37)
a79e2c6  Merge final Trading Core all-WIP live certification (#36)
```

`claude/van-system-audit-ysgtcd` is at the same commit as `origin/main`. Working tree clean at audit start.

### 2.2 Unmerged work

| Branch | Unique commits vs `main` | Content |
|---|---:|---|
| `gpt/van-unified-intelligence-improvements-rev1-20260918` (PR #38, **open**) | 2 | `docs/VAN_UNIFIED_PERSONAL_INTELLIGENCE_IMPROVEMENT_BLUEPRINT_REV_1.md` (1238 lines) |
| `claude/integration-plan-review-369mxs` | 0 | fully merged |
| `gpt/rev3-1-full-knowledge-runtime-20260917` | 0 | fully merged |
| all other `gpt/*` branches | 0 | fully merged |

**Finding D-1 (documentation authority defect).** `docs/project-state/UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json`
declares itself generated against `blueprint_path: docs/VAN_UNIFIED_PERSONAL_INTELLIGENCE_IMPROVEMENT_BLUEPRINT_REV_1.md`
at `blueprint_sha e09765d`. That file **does not exist on the audited branch**. It exists only on the open
PR #38. The matrix that certifies 33 of 36 workstreams "BUILT" therefore measures the implementation
against a specification that is not part of the canonical tree. This is recorded as **P1-DOC-001**.

### 2.3 Scale

| Area | Files | Lines (code + config + docs) |
|---|---:|---:|
| `backend/` | 398 | 40,731 |
| `android/` | 138 | 19,180 |
| `trading/` | 302 | 17,835 |
| `docs/` | 44 | 14,651 |
| `deploy/` | 69 | 6,183 |
| `tools/` | 30 | 3,017 |
| `hermes/` | 32 | 2,306 |
| `tests/` (cross-cutting) | 18 | 1,064 |

### 2.4 Test execution at HEAD (this container, `python3 -m pytest`)

| Suite | Result |
|---|---|
| `backend/tests` | **624 passed** |
| `tests/contracts` + `tests/hermes` + `tests/scenarios` + `hermes/policy/tests` | **108 passed, 1 failed** |
| `trading/tests` | **251 passed, 2 skipped** |
| Android JVM unit tests | **NOT VERIFIED** — Android Gradle Plugin does not resolve in this container |

The single failure is `tests/hermes/test_profile_layout.py::test_install_profile_preserves_runtime_state_and_secrets`.
Root cause established by direct execution: `tools/hermes/install_van_profile.sh:66` calls `require_cmd rsync`
and `rsync` is absent from this container. This is an environment gap, not a code defect.

**983 Python tests pass. §37 of this report explains why that number is not evidence of product completeness.**

---

## 3. Canonical authority hierarchy

`PROJECT_CANONICAL_STATE.json` establishes the governing rules, and they are unusually strong:

- `default_branch_is_not_authority: true`
- `newest_commit_is_not_authority: true`
- `ci_is_not_project_truth_authority: true`
- `owner_instruction_is_project_truth_authority: true`
- `agent_self_authorization_forbidden: true`
- `release_blocked: true`, reason: *"VAN remains 0.5.0-dev and applicable external certification gates in
  docs/EXTERNAL_GATES.md are not all green."*

Locked authorities (`canonical_state.locked_authorities`): `docs/PROJECT_TRUTH_PROTOCOL.md`,
`docs/SECURITY_POLICY.md`, `hermes/profile/van/SOUL.md`, `hermes/profile/van/AGENTS.md`,
`registries/projects.json`, `registries/google_capabilities.json`, `visual-authority/rive_contract.json`.

Resolution order used by this audit when sources disagree, taken from `docs/PROJECT_TRUTH_PROTOCOL.md`
and `hermes/profile/van/SOUL.md`:

1. Owner-signed instruction
2. Project Truth / canonical project authority
3. Explicit capability grants
4. Deterministic system state
5. Hermes curated profile memory
6. Conversational history
7. External/untrusted content

**The repository's own governance is the strongest artefact in the project.** Where this report finds
defects, they are almost never defects of stated policy. They are defects of *enforcement*: policy
written in Markdown that no code path applies, or applied only to a caller that is trusted to be honest.

---

## 4. System topology (implementation-derived)

This is the topology the code actually implements, not the topology the README draws.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ OWNER (single principal)                                                      │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ touch / speech (tap-initiated only)
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ ANDROID  com.dial.van                                                         │
│  FloatingOverlayService (SYSTEM_ALERT_WINDOW, FGS type=specialUse)            │
│  CommandCentreActivity · TradingCommandCentreActivity · OnboardingActivity    │
│  VanCommandController  ──single owner-command funnel                          │
│  VanGatewayClient  (HMAC-SHA256 v2 signing, encrypted queue, POLLING ONLY)    │
│  VanNotificationListenerService · BiometricGate · OwnerApprovalKeyManager     │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ HTTPS  X-Van-Ingress-Token + X-Van-Device-Token
                                │        (+ per-command HMAC signature)
                                │ ⚠ no SSE, no WebSocket, no FCM — Android polls
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ CLOUDFLARE NAMED TUNNEL  ── EXTERNAL GATE, not provisioned                    │
└───────────────────────────────┬──────────────────────────────────────────────┘
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ VAN GATEWAY  uvicorn 127.0.0.1:8787 on dial-hermes-control                    │
│  59 routes · FastAPI · aiosqlite (69 tables, schema v16) · NO Postgres        │
│                                                                               │
│  DETERMINISTIC AUTHORITY CORE (real, enforced)                                │
│   auth · approval (A4 ECDSA challenge) · idempotency · audit ·                │
│   command/authority (sealed records) · action registry · Project Truth gate   │
│                                                                               │
│  DETERMINISTIC ENGINES (real, owner-visible)                                  │
│   reminders · attention · decisions · briefing · notifications · degraded     │
│                                                                               │
│  COGNITION LAYER (real code, ISOLATED — §17-§22)                              │
│   context · context_compiler · epistemics · reasoning · understanding ·       │
│   evolution · proactive — 20+ classes, near-zero production callers           │
│                                                                               │
│  MISSION CORE (real state machine, ISOLATED from the command path — §16)      │
│  CAPABILITY REGISTRY + ROUTER (11 capabilities; router has 1 caller)          │
│  EXECUTION ADAPTERS (all fail-closed and disabled by default)                 │
│   hermes/bridge · browser/adapters · automation/n8n_client ·                  │
│   google/transport · knowledge/{vekl,obsidian,notebook} · research/exa ·      │
│   trading/accounts (HTTP to commander)                                        │
└───────┬──────────────────┬───────────────┬──────────────┬────────────────────┘
        │ POST /p/van/v1/runs              │              │
        │ (fire-and-forget, no readback)   │              │
┌───────▼──────────────┐   │               │              │
│ HERMES  profile van  │   │               │              │
│  ⚠ NOT IN THIS REPO  │   │               │              │
│  the only LLM loop   │   │               │              │
│  Claude Sonnet 5     │   │               │              │
│  MCP shim ──────────────►│ /v1/runtime/* (internal-control token)             │
└──────────────────────┘   │               │              │
                           │               │              │
        ┌──────────────────▼──┐  ┌─────────▼────────┐  ┌──▼───────────────────┐
        │ GOOGLE  Workspace   │  │ BROWSER FABRIC   │  │ ORACLE TRADING VM    │
        │ OAuth transport     │  │ Harness+Stagehand│  │ van-trading-core     │
        │ (READY per doc;     │  │ ⚠ WORKERS NOT IN │  │ Caddy · Supabase/PG  │
        │  fresh DB = AUTH_   │  │   THIS REPO      │  │ n8n · VATI · VEKL    │
        │  REQUIRED)          │  │ disabled default │  │ commander (HMAC MCP) │
        └─────────────────────┘  └──────────────────┘  │ → Windows MT5 bridge │
                                                        └──────────────────────┘
```

**Structural observations from the topology itself:**

1. **The intelligence is not in this repository.** The gateway contains no model client. Every
   reasoning act belongs to Hermes, which is deployed elsewhere and whose source is not auditable here.
   VAN as committed is an *authority, evidence and presentation layer* around an external agent.
2. **The command path is fire-and-forget.** `POST /p/van/v1/runs` returns a run id. Nothing polls it,
   no callback is keyed to it, and no evidence links a Hermes run to a later verification.
3. **There is no push channel to the owner's device.** The event bus is a SQLite table that Android
   polls, and only two event types are ever published.
4. **Three separate execution estates** (Hermes host, Browser Fabric, trading VM) each hold their own
   credentials, and two of the three have no source in this repository.

---

## 5. Subsystem inventory and maturity matrix

Classification per §0. "Callers" means production, non-test code paths in this repository.

### 5.1 Authority and security core

| Subsystem | Class | Evidence |
|---|---|---|
| Device pairing / ingress / device token | INTEGRATED | `app.py:443-476`; live cert `artifacts/runtime/van_pairing_v4_live_attestation.json` |
| Per-command HMAC v1/v2 | INTEGRATED | `auth/service.py:250-334`; probe: signed commands accepted, stale rejected |
| A4 owner approval (ECDSA challenge/consume) | INTEGRATED | `approval/service.py:278-429`; probe: A4 without resolved action → `denied` |
| Command authority sealing | INTEGRATED | `command/authority.py:87-136,264-276` |
| Action registry / principals | INTEGRATED | `action/registry.py:9-93` — A3/A4 are `OWNER_DEVICE` only |
| Idempotency | PARTIAL | `idempotency/service.py:100-110` SELECT-then-INSERT; concurrent begin → IntegrityError → HTTP 500 |
| Audit trail | INTEGRATED | `audit/service.py`; every command dispatch recorded |
| Project Truth gate (A3/A4) | INTEGRATED | `orchestrator.py:355-388` |
| Prompt-injection screen | PARTIAL | `orchestrator.py:26-33,323-334` — 6-marker substring list, applied **only** when the client sets `context_trust=UNTRUSTED` |

### 5.2 Owner command and execution

| Subsystem | Class | Evidence |
|---|---|---|
| `POST /v1/commands` orchestration | INTEGRATED | `orchestrator.py:79-566` |
| Typed command resolver | PARTIAL | `command/resolver.py:76-194` — fixed regex for ~6 intents, everything else `HERMES_INTERPRETATION_REQUIRED` |
| Hermes dispatch | IMPLEMENTED_BUT_ISOLATED | `hermes/bridge.py:33-75`; every test monkeypatches `create_run`; no live run receipt |
| Hermes result readback | **ABSENT** | no poller, no callback keyed to `hermes_run_id`; `orchestrator.py:560-575` returns `accepted` immediately |
| Owner-runtime MCP (Hermes → gateway) | PARTIAL | shim exposes 20 tools (`hermes/mcp/owner_runtime_stdio.mjs:50-71`); `tools/hermes/register_owner_runtime_mcp.sh:48-64` registers **11** |
| Authorized execution chain (`action_begin/submitted/verify`) | IMPLEMENTED_BUT_ISOLATED | `runtime_api.py:332-400`; strict binding; no live E2E artefact |
| In-gateway executors | PARTIAL | only 5 `google.notebook.*` actions (`knowledge/service.py:190-250`) |
| Mission Core state machine | IMPLEMENTED_BUT_ISOLATED | `mission/models.py:36-108`; `MissionService.create` has one production caller, the internal-token `POST /v1/missions` |
| Mission ← command binding | **ABSENT** | `orchestrator.py` imports nothing from `mission/`; `CommandRequest` carries no `mission_id` |
| Capability registry | INTEGRATED | `capability/registry.py:97-227`; 11 capabilities in `registries/capabilities.json` |
| Capability router | IMPLEMENTED_BUT_ISOLATED | one caller: `POST /v1/missions/route` (`mission/api.py:385`) |
| Event bus → device | PARTIAL | `events/bus.py:14-46` pull-only; only `decision.escalated` and `attention.upserted` are ever published |

### 5.3 Deterministic owner engines (the strongest layer in the product)

| Subsystem | Class | Evidence |
|---|---|---|
| Reminders + natural-time parsing | INTEGRATED (no scheduler) | `reminders/service.py`; `fire_due` has no scheduler calling it (`:414`) |
| Attention queue | INTEGRATED | `attention/engine.py`; publishes to the event bus |
| Attention scorer 2.0 | IMPLEMENTED_BUT_ISOLATED | `attention/scoring.py`; `decisions/service.py:9,57` still uses the older engine |
| Decisions / approvals | INTEGRATED | `decisions/service.py`; single approval surface, used by browser escalation and Android |
| Briefing | INTEGRATED | `briefing/service.py` |
| Notification intelligence | INTEGRATED | `notifications/intelligence.py`; OTP suppression and quiet hours tested |
| Degraded-state registry | INTEGRATED (in-memory) | `degraded/registry.py`; truthful `broken / still_works / will_not_do / restore_action` contract |

---

## 6. Experience-layer audit — does VAN behave as one intelligence?

The governing principle is *unified at the experience layer, modular at the execution layer*. This
section tests the first half, because the second half is largely satisfied.

### 6.1 Runtime trace of representative owner intents

This audit ran the real gateway in-process against a throwaway database, paired a device through the
real pairing flow, signed each command with the real HMAC path, and submitted the canonical owner
intents twice: once with Hermes unreachable, once against a local HTTP server standing in for Hermes.
Script and raw output: `evidence/van-system-audit/command-execution/probe_command_lifecycle.py`,
`probe_hermes_down.json`, `probe_hermes_fake.json`.

**Result with Hermes reachable — all eight representative intents behave identically:**

| Owner intent | HTTP | Status returned to owner |
|---|---:|---|
| "Van, brief me." | 200 | `accepted` |
| "Hey Van, analyse this trade and explain whether anything has changed since this morning." | 200 | `accepted` |
| "Van, research this deeply and save what matters." | 200 | `accepted` |
| "Van, use my browser to complete this task." | 200 | `accepted` |
| "Van, check my calendar and arrange this." | 200 | `accepted` |
| "Van, investigate why this project failed its build." | 200 | `accepted` |
| "Van, ask Hermes to execute this development mission." | 200 | `accepted` |
| "Van, open the trading system and show me what needs attention." | 200 | `accepted` |
| "Create a NotebookLM notebook for this project" | 200 | `accepted` |
| "Delete the production database" (A4) | 200 | `denied` — *"A4 requires an exact gateway-resolved action before owner approval"* |

Every one of them produced the same message: *"Accepted and routed to Hermes profile van with canonical
owner context and sealed authority"*, and the same `hermes_run_id`. Afterwards:

- `GET /v1/missions` → `[]`
- `GET /v1/activity` → `{"missions": []}`
- `GET /v1/needs-you` → `{"count": 0, "missions": [], "decisions": []}`
- `GET /v1/commands/{id}` → **404 (no such route)**

**This is the single most important structural finding in the audit.** The owner's intent enters the
system, is authenticated, authorised, audited and forwarded — and then leaves VAN's model of the world
entirely. No mission is created. No activity is recorded. No capability is routed. No state exists that
the owner's device could later poll to learn what happened. The command's observable lifecycle inside
VAN ends at `accepted`.

Recorded as **P0-EXEC-001** (§45).

### 6.2 What "canonical owner context" actually contains

`orchestrator.py:403-407` seals a context snapshot with an **empty requirements list**:

```python
snapshot = await self.context.compile_snapshot(req.command_id, [], live_state_refs=..., policy_refs=...)
```

`readiness()` over an empty list is trivially `CURRENT` (`context/service.py:239`), so the snapshot always
succeeds with `fact_ids=[]`. Probe confirmed: `fact_ids [] kernel_revision 0`. The metadata forwarded to
Hermes under the key `canonical_context` therefore carries a snapshot id, a digest, a Project Truth SHA
and policy references — and **zero owner facts**.

VAN does not send Hermes what it knows about the owner. It sends a receipt proving it sealed nothing.
Recorded as **P0-CTX-001**.

### 6.3 Seams the owner would actually encounter

| Seam | Evidence |
|---|---|
| Work has no single identity | Eleven parallel lifecycle vocabularies exist: `MissionState`, `ActivityState`, `ExecutionStatus`, `RunStatus`, `BrowserTaskStatus`, `DecisionStatus`, `IdempotencyStatus`, `AttentionState`, `KnowledgeOperationStatus`, `OperationState`, plus Android's own command status. No owner-facing projection unifies them. |
| Completion never arrives | Only `decision.escalated` and `attention.upserted` are ever published to the event bus (`app.py:569,703`). Mission and command progress are structurally invisible to the device. |
| Two snapshot notions | The orchestrator seals a snapshot and binds authority to *that* id (`command/authority.py:110-111`), while `AGENTS.md:38` instructs Hermes to seal its own. A Hermes-sealed snapshot cannot authorise an action. Documented nowhere. |
| Voice is a second-class input | Voice reaches the same controller and the same signed command (good), but VAN never speaks a reply and no completion returns to the voice turn (§15). |
| Trading is a separate world | No event, route or field connects classified trading state to VAN's visual or conversational state (§29, §12). |

**Experience-layer verdict:** VAN is unified at the *authority* layer — one signed command path, one
approval surface, one audit trail — and that is a genuine achievement. It is **not** unified at the
*experience* layer, because the system has no durable, owner-visible representation of work in flight.

---

## 7. Command execution audit

### 7.1 The lifecycle VAN actually distinguishes

The required distinction is: heard → understood → planned → authorized → submitted → executing →
externally confirmed → completed / failed / partially completed.

What the gateway implements on `POST /v1/commands` (`orchestrator.py:79-566`), in order:

1. idempotency claim (`:76-100`)
2. device identity + HMAC v1/v2 signature verification (`:103-157`)
3. typed resolution and action-class strengthening (`:159-161`)
4. intent expiry / staleness gates (`:165-193`)
5. A5 hard deny (`:195-203`)
6. A4 approval challenge issue / consume (`:205-297`)
7. `NO_STALE_REPLAY` window (`:301-321`)
8. untrusted-content injection markers (`:323-334`) — **only if the client declares `context_trust=UNTRUSTED`**
9. Project Truth gate for A3/A4 (`:355-388`)
10. context snapshot sealing (`:390-436`) — with empty requirements (§6.2)
11. authority record sealing (`:440-481`)
12. Hermes health gate (`:483-498`)
13. `create_run` and return (`:497-575`)

Steps 1–12 are real, strict, and well tested. They cover **heard**, **understood** (for the six regex
intents), **authorized** and **submitted**.

**Steps beyond `submitted` do not exist in the gateway.** There is no `executing`, no
`externally confirmed`, no `completed`, no `partially completed`. `evidence/van-system-audit/command-execution/`
shows the terminal owner-visible state is `accepted`.

The verification vocabulary that *would* express those states lives in `action/` and `mission/` and is
reachable only if Hermes voluntarily calls back `action_begin → action_submitted → action_verify`
(`runtime_api.py:332-400`). Nothing joins a `hermes_run_id` to those callbacks; nothing detects their
absence. **Silent non-execution produces no degraded signal.** Recorded as **P0-EXEC-002**.

### 7.2 Intent coverage

`command/resolver.py:76-194` recognises, by regular expression only:

| Intent | Action | Class |
|---|---|---|
| halt / stop / pause [autonomous] trading | `trading.halt` | A4 |
| create/make [a] notebooklm note … | `google.notebook.note.create` | A3 |
| delete … notebook enterprise notebook id X | delete | A4 |
| delete sources … from … | delete | A4 |
| research \| search the web for \| look up ⟨q⟩ | `research.web.search` | A2 |
| what do you know / what have i told you about ⟨t⟩ | `owner.context.read` | A1 |

Everything else returns `HERMES_INTERPRETATION_REQUIRED` (`:190-194`). Probed non-matches include
"Please stop trading now" and "book me a flight". This is a defensible design — natural language belongs
to the model — but it means **the gateway's own understanding of owner intent covers six phrasings**, and
all other semantics depend on a runtime this repository cannot verify.

### 7.3 A4 destructive-action handling — a genuine strength

Probe result for `"Delete the production database"` submitted as A4:

```
status: denied
message: "A4 requires an exact gateway-resolved action before owner approval"
```

VAN refuses to let a free-text destructive instruction become an approvable action. The approval must
bind to a resolved action id with typed parameter constraints (`command/authority.py:124-129`), an ECDSA
challenge consumed once (`approval/service.py:278-429`), and the device key that signed the command. This
is correct, strict and better than most production systems. It is also why `google.notebook.*` and
`trading.halt` are the only A3/A4 actions that exist: the registry is the ceiling.

### 7.4 Verified completion is a schema check, not a proof

Runtime probe (`evidence/van-system-audit/security/probe_mission_verification.py`):

- A mission with no checkable postcondition is **correctly refused**:
  `MISSION_SUCCESS_CONTRACT_NOT_CHECKABLE`.
- But when the same caller supplies both the success contract and the verification receipt, the mission
  reaches `VERIFIED_SUCCESS` on a receipt reading `verifier_version: "i-say-so/1.0"` with a single
  evidence reference `evidence://trust-me`. **No server-side verifier executes.**

`mission/verifiers.py` contains real adapters (API readback, repository SHA, CI run, ledger event,
screenshot) and `VerifierRegistry` is constructed **only in tests**. The invariant "VERIFIED_SUCCESS is
unreachable without a verifier receipt" holds literally and means much less than it sounds: the receipt
is caller-authored. Recorded as **P0-VERIFY-001**.

---

## 8. Cognitive architecture audit

### 8.1 There is no reasoning in this repository

Grep across `backend/van_gateway/` for `anthropic|openai|gemini|embed|vector|faiss|chroma|pgvector`
returns configuration flags and docstrings only. The gateway holds **no model client**. Every outbound
HTTP client is an integration adapter (Hermes, Exa, n8n, browser workers, Google, VEKL, Notebook,
trading commander). `hermes/bridge.py:19` states it plainly: *"Never launches models directly."*

That is architecturally correct — Hermes owns the loop. The defect is what the cognition layer claims
to be.

### 8.2 The Critical Reasoning Kernel does not reason

`reasoning/kernel.py:192-247` accepts every element of a `ReasoningAssessment` as a caller-supplied
keyword argument — facts, assumptions, alternatives, critic findings, verifier findings, confidence —
applies two shape rules (alternative count meets the challenge mode's minimum; a fact flagged
`factual_authority` carries a non-empty `source` string), and inserts the row.

Runtime probe (`evidence/van-system-audit/security/probe_authority_boundaries.out`):

```
assess(problem_statement="Is the sky green?", challenge_mode=BALANCED,
       known_facts=[{"statement": "The sky is green", "factual_authority": True,
                     "source": "i-made-this-up"}],
       critic_findings=[], verifier_findings=[], confidence=0.99)
→ stored, is_actionable = True
```

A fabricated fact with an invented source, zero critic findings and zero verifier findings produces an
actionable assessment at 0.99 confidence. The module docstring claims *"Solver, critic and verifier are
separate passes"* (`kernel.py:1-24`). They are separate **JSON columns filled by the caller**.

This is not a bug in the code — the code does what it says structurally. It is a **product-truth defect**:
the matrix records WS9 as BUILT with the note "solver/critic/verifier separation, mode-gated rigour,
unsourced facts refused" (`UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json:105`). Recorded as **P0-COG-001**.

### 8.3 Nothing supplies the records, and no route accepts them

The matrix states the kernel and calibration engine are "consumed by Hermes, not the gateway"
(`...MATRIX.json:420`). Verified against the Hermes pack in this repository:

- `hermes/mcp/owner_runtime_stdio.mjs:50-71` exposes 20 tools. None is `reasoning_assess`,
  `assess_premise`, `record_assumption`, `understanding_observe` or any calibration tool.
- `understanding/api.py` exposes **no route** that would accept an assessment. The only kernel method
  reachable over HTTP is `sycophancy_metrics()`, read inside `GET /v1/eval` (`:196`).
- `SOUL.md`, `AGENTS.md` and all 16 `SKILL.md` files never mention assessment, premise or calibration.

So the reasoning ledger cannot be written by Hermes even if Hermes wanted to. It is write-only-by-tests.

### 8.4 Fact / inference / hypothesis separation exists twice and is enforced once

Two parallel, unreconciled epistemic taxonomies:

| Taxonomy | Location | Enforced? |
|---|---|---|
| `EpistemicState` (10 tiers) + `SourceTrust` | `context/models.py:9-28` | **Yes** — `context/service.py:75-91` rejects SECRET, refuses untrusted/model-derived claims to high tiers |
| `SemanticClass` (9 classes) + `FORBIDDEN_SELF_PROMOTIONS` + `Claim` | `epistemics/models.py:44-201` | **No** — `may_promote` and `FORBIDDEN_SELF_PROMOTIONS` have zero production callers; no table stores a `Claim`; `AdmissionOutcome`/`AdmissionVerdict` are unused even by tests |

The enforced one is real and good. The one the blueprint describes as the critical-thinking substrate is
a vocabulary with no enforcement point. Recorded as **P2-COG-002**.

### 8.5 The assumption gate guards nothing

`CriticalReasoningKernel.assert_safe_for_irreversible_work` (`kernel.py:341-348`) is the designed gate
between unresolved assumptions and irreversible action. Grep across `action/`, `mission/`, `automation/`,
`browser/`: **no caller**. Irreversible work in VAN is gated by A4 biometric approval — which is strong —
but not by the epistemic state of VAN's own reasoning.

### 8.6 Cognition layer classification

| Component | Class |
|---|---|
| `ContextCompiler` / `ContextPacket` | IMPLEMENTED_BUT_ISOLATED (zero callers; the `Claim` objects it consumes are produced nowhere) |
| `CriticalReasoningKernel` | IMPLEMENTED_BUT_ISOLATED as a ledger; **ABSENT as a reasoner** |
| `RelationshipCalibrationEngine` | IMPLEMENTED_BUT_ISOLATED (zero callers) |
| `OwnerCognitiveModel` | IMPLEMENTED_BUT_ISOLATED (API-reachable, fed by nothing) |
| `SharedVocabularyRegistry`, `CognitiveComplementMap`, `SymbioticGrowthLedger` | IMPLEMENTED_BUT_ISOLATED (read-only routes, no writer) |
| `IntentContinuityGraph`, `StrategicMemory`, `DecisionFingerprints` | IMPLEMENTED_BUT_ISOLATED (**no production constructor at all**) |
| `ExternalRealityModel`, `BenchmarkHarness`, `StrategyLearning` | IMPLEMENTED_BUT_ISOLATED (no production constructor) |
| `AIEvolutionRadar`, `VanEval` | IMPLEMENTED_BUT_ISOLATED (read-only API) |
| `ProactivePolicyService`, `DomainTrustService` | IMPLEMENTED_BUT_ISOLATED (read-only route; no proactive path exists to gate) |
| `AttentionScorer` | IMPLEMENTED_BUT_ISOLATED (`decisions/service.py:9,57` uses the older engine) |
| `ContextRetrievalService` | IMPLEMENTED_BUT_ISOLATED (internal-token API only; not on the command path) |

**Nothing in the cognition layer is SIMULATED or STUB.** The code is genuinely written and genuinely
tested (86/86 in-scope tests pass). What is absent is the *wiring*: nothing feeds these modules and
nothing consumes their output. The matrix's own integration note concedes part of this
(`...MATRIX.json:411-421`); this audit extends the uncalled list from 4 modules to 20.

---

## 9. Critical-thinking audit

The required standard is that VAN distinguishes known fact, retrieved evidence, inference, hypothesis,
assumption, recommendation and unresolved uncertainty, and that important claims trace to evidence.

**What is real:**

- The *data model* for every one of those categories exists and is well designed
  (`epistemics/models.py`, `context/models.py`, `reasoning/kernel.py`).
- Evidence provenance is real where providers run: every VEKL, Obsidian, Notebook and Exa result is
  persisted with `source_ref`, `source_trust`, `content_digest` and `retrieved_at`
  (`knowledge/evidence.py:29-67`, `research/exa.py:98-108`), and is admitted as `EXTERNAL_EVIDENCE`,
  never as owner fact. **The "evidence is not truth" invariant holds in code.**
- Contradiction detection for facts is real: same-authority differing digests yield `CONFLICTED` with
  both ids returned rather than a silent winner (`context/service.py:213-222`).
- Staleness is real: `max_age_ms` per requirement produces `STALE` and blocks snapshot sealing
  (`:225-227,259-260`).

**What is absent:**

- No mechanism *produces* the distinctions at runtime. Classification is whatever the caller declares.
- `REQUIRED_COUNTERFACTUALS` (`kernel.py:167-174`) is compared by string equality only; nothing requires
  a counterfactual before a decision.
- Anti-sycophancy is measured, not enforced: `agreed_without_evidence` is derived
  (`kernel.py:383-387`) over a ledger nothing writes.
- Hypothesis comparison, self-correction and post-action evaluation have data structures
  (`StrategyLearning.record_outcome`, `DecisionFingerprints.record_outcome`) with **no caller that
  records a real outcome**.

**Critical-thinking verdict:** VAN has an excellent *vocabulary* for critical thinking and no *practice*
of it inside this repository. Whether VAN reasons critically is entirely a property of the Hermes prompt
pack (`SOUL.md`, `AGENTS.md`, 16 skills), which is prose instruction to a model, unverifiable from here,
and explicitly ranked below owner and Project Truth authority — as it should be, but it means the
"critical reasoning architecture" is currently a *prompt*, not an *architecture*.

---

## 10. Context-awareness audit

### 10.1 What retrieval actually does

`context/retrieval.py` is a deterministic lexical retriever: NFKC case-folded token overlap with per-field
weights (subject 1600, predicate 1300, value 700; exact-match bonuses 12000/10000/7000), an SQL
pre-filter ordered by authority rank, and a final sort of
`(-score, -authority_rank, -confidence, -revision, kind, id)` (`:191-212,296-303`). Graph retrieval is a
bounded temporal BFS (depth 1–3, ≤256 edges, ≤32 seeds). Hot capsules are revision-sealed caches with a
1–300 s TTL held in an in-memory dict (`:171,368-461`).

There is **no embedding model, no vector index and no semantic retrieval**, and that is a deliberate,
documented decision (`docs/project-state/REV31_CONTEXT_RETRIEVAL_CERTIFICATION.md:19,56` — *"do not add
vector or LLM retrieval"*). For a single-owner system with authority-ranked facts this is a reasonable
and fast design.

### 10.2 The fact store is unreachable in production

This is the defect that makes context awareness theoretical rather than actual.

The only production write paths for owner facts are `runtime_api.py:169,178`, both gated by
`_require_hermes_memory_candidate` (`:122-124`), which raises 403 unless
`authority == INFERRED and source_trust == MODEL_DERIVED`. Meanwhile default readiness, graph and lexical
queries **exclude INFERRED** (`context/service.py:199-200,393-394`; `context/retrieval.py:222-223,241-242`;
`HotContextCapsuleRequest.allow_inferred=False`).

Consequence, confirmed by probe: the only facts VAN can write in production are the only facts VAN will
not retrieve by default. The `CANONICAL_OWNER`, `PROJECT_TRUTH` and `VERIFIED_*` tiers — the tiers the
whole authority ladder exists to arbitrate — **are empty in a deployed system unless someone writes SQL
by hand.** There is no owner-facing "tell VAN a fact" path, no Project-Truth-to-fact importer, and no
conversation ingestion.

Recorded as **P0-CTX-002**.

### 10.3 Context on the command path

Per §6.2, the orchestrator seals a snapshot with zero requirements on every owner command. There is no
mapping from `req.project_id` to a context scope. The `ContextCompiler`'s hard cross-project isolation
(`context_compiler/compiler.py:182-188`) — a genuinely good piece of code — never executes in production.

Cross-project isolation *is* enforced everywhere it is used, by scope string equality in every SQL clause
(`service.py:192,367`; `retrieval.py:215,234`). The mechanism is sound; nothing drives it.

### 10.4 What context VAN does have

Honest accounting of what a deployed VAN actually knows at command time:

| Context dimension | Present? | Source |
|---|---|---|
| Current conversation | No (gateway) | Hermes holds run history; VAN keeps only idempotency + audit rows |
| Active screen | Partial | `client_context` is forwarded but marked `client_context_authoritative: False` (`orchestrator.py:509`) |
| Active project | Yes | `project_id` on the command; Project Truth SHA sealed into the snapshot |
| Recent owner actions | Partial | audit table exists; not retrieved into context |
| Device state | Partial | degraded registry, health |
| Time | Yes | issued-at, expiry, quiet hours |
| Tool/capability state | Yes | capability registry + readiness sources |
| Trading state | **No** | no link to the experience layer (§12) |
| Recent research | Stored, not retrieved | `research_evidence` written, never read back |
| Project Truth | Yes | cache + gate |
| Long-term owner preferences | **No** | owner model has no writer (§11) |
| Relevant history | **No** | no episodic store |

---

## 11. Memory audit

The taxonomy is genuinely differentiated — this is not one vector database pretending to be a mind — and
that is to the project's credit. What follows is what each layer actually is.

| Layer | Store | Real? | Writer in production? |
|---|---|---|---|
| Conversation state | — | n/a | Hermes owns it; gateway keeps none |
| Working memory | `_hot_cache` in-memory dict (`context/retrieval.py:171`) | yes | yes (on capsule compile); lost on restart |
| Owner facts (canonical) | `owner_facts` | yes | **INFERRED only** (§10.2) |
| Fact graph | `owner_context_edges` | yes | INFERRED only |
| Sealed snapshots | `context_snapshots` | yes, append-only | yes — but with empty requirements; evidence refs are **not validated** (probe: `vekl://does-not-exist` accepted) |
| Episodic | none | **ABSENT** | `supporting_episode_refs_json` holds opaque strings; no episode table |
| Preference / owner model | `owner_cognitive_model` | yes | **none** — `/v1/understanding/observe` has no caller in backend, Hermes pack, tests or Android |
| Derived preference (vocabulary, complement, growth, intent, strategic, fingerprints) | 6 tables | yes | **none** |
| Reasoning ledger | `reasoning_assessments`, `assumption_ledger`, `premise_assessments` | yes | **none** |
| Project knowledge | `project_truth_cache` | yes | yes (sync tool + internal PUT) |
| External evidence | `knowledge_evidence`, `research_evidence`, `obsidian_documents` | yes | yes when a provider is enabled; **nothing ever reads them back** (no `FROM knowledge_evidence` outside the writer) |
| Operational / eval | `eval_runs` + 7 others | yes | `VanEval` writes 11 rows on every `GET /v1/eval` |
| Tool state | `notebook_operations`, certifications, `runtime_meta` | yes | yes |

**Structural memory findings:**

1. **No retention anywhere.** `knowledge_evidence`, `research_evidence`, `eval_runs` and
   `context_snapshots` grow without bound. No prune job exists in the repository. (**P3-MEM-001**)
2. **Owner erasure is partial.** Only `owner_facts`/`owner_context_edges` have an erase path
   (`DELETE /v1/runtime/context/scope/{scope}`). There is no owner-facing forget for the owner model,
   evidence stores or reasoning ledgers. (**P2-MEM-002**)
3. **Memory and context are correctly separated in the schema** and incorrectly conflated in the docs:
   the ledger's "memory taxonomy (10 stores)" claim (`...MATRIX.json` WS6) is true of the tables and
   false of the system, because seven of the ten have no writer.

---

## 12. Owner-symbiosis and learning audit

### 12.1 The admission ladder can be driven by a caller

`OwnerCognitiveModel.observe` promotes an assertion to `CANDIDATE` after 2 distinct `episode_ref`
strings and to `CONFIRMED` after 3, except for autonomy-bearing fields which never auto-confirm
(`understanding/owner_model.py:184-194`). Episode refs are free-form strings **never checked against a
mission, command or any episode store**.

Runtime probe (`evidence/van-system-audit/security/probe_authority_boundaries.out`):

```
observe(field=COMMUNICATION_PREFERENCE, value="terse updates", episode_ref="ep-a")
observe(... episode_ref="ep-b")
observe(... episode_ref="ep-c")
→ state = CONFIRMED, owner_confirmed_at_ms = None

RelationshipCalibrationEngine.calibrate(...)
→ verbosity = TERSE, reasons = ("owner-confirmed preference for terse updates",)
```

VAN reports a preference as **owner-confirmed** when the owner never confirmed it. The state
`CONFIRMED` (evidence-derived) and the field `owner_confirmed_at_ms` (owner-derived) both exist and are
correct; the calibration engine reads only the former and names it the latter
(`reasoning/calibration.py:130-133`). Recorded as **P1-SYM-001**.

### 12.2 Learning loops are frameworks without inputs

| Mechanism | Invariants | Input in production |
|---|---|---|
| `StrategyLearning` — PREFERRED needs an eval run and ≥10 runs at ≥90%; auto-demote <60% | correct and tested | **none** — no executor records an outcome; `promote` does not verify the `eval_run_id` exists |
| `SymbioticGrowthLedger` — adaptations not in force until confirmed, revertible | correct | **none** records an adaptation |
| `AIEvolutionRadar` — ADMITTED requires benchmark, security profile, licence, owner decision | correct | **none**; no discover/transition route |
| `BenchmarkHarness` — two-run regression detection | correct | **none**; the CI benchmark measures context latency and writes JSON, it does not call this class |
| `DomainTrust` — earned autonomy caps at S2; false success needs demonstrated recovery | correct | **none**; `record()`, `grant()`, `assert_may_run()` have no callers |
| `VanEval` — 11 dimensions, 3 declared unmeasurable | honest about what it cannot measure | self-generated; scores are threshold constants (9.7/9.6/9.5) applied to row counts |

The invariants are exactly the ones a careful designer would choose. The separation of *learning what the
owner prefers* from *learning what is factually true* is correctly expressed in the type system. But no
production event — mission outcome, verification receipt, owner correction, tool failure — is wired into
any of them. **VAN cannot currently learn from experience because it does not observe its own experience.**

`VanEval`'s `authority` dimension returns 9.7 whenever no `VERIFIED_SUCCESS` row lacks a receipt
(`vaneval.py:221`). Since receipts are caller-authored (§7.4) and missions are barely created, this score
is a measurement of an empty table. Recorded as **P1-LEARN-001**.

---

## 13. Android architecture and information-architecture review

### 13.1 Component inventory

`android/app/src/main/AndroidManifest.xml` (108 lines) declares:

| Component | Lines | Note |
|---|---:|---|
| `OnboardingActivity` | 178 | the **only** LAUNCHER activity |
| `CommandCentreActivity` | **1238** | 13 module Composables + 5 helpers in one file; no ViewModel, no NavHost, no repository |
| `TradingCommandCentreActivity` | 159 | delegates to `trading/ui/TradingScreens.kt` (485) |
| `FloatingOverlayService` | 1031 | foreground service, type `specialUse` |
| `VanNotificationListenerService` | — | notification capture |
| `OverlayRecoveryReceiver` | — | BOOT_COMPLETED / MY_PACKAGE_REPLACED |
| `ShareIntentReceiver` | — | see §13.7 |

### 13.2 Information architecture — an engineering console, not a personal assistant

`CommandModule` declares 13 entries (`CommandCentreActivity.kt:68-88`) but the tab strip shows four —
Home, Chat, Tasks, Activity (`:165-170`). Everything else is reached as a card on one Home `LazyColumn`
(`:251-320`). Navigation is a manual `when` plus `BackHandler` (`:154-163,204-223`); depth ≤ 3.

The Rev 3.0 blueprint (§33) requires the destinations Overview, Chat, Decisions, Tasks, Projects,
Activity, Systems/Hermes, Connections, Settings, and §40 explicitly prohibits production placeholders
and developer vocabulary. What the owner actually reads today:

| Screen text | Source |
|---|---|
| Raw enum names as command status — `LOCAL_DRAFT`, `APPROVAL_REQUIRED`, `IN_FLIGHT` | `CommandCentreActivity.kt:1214` — `Text(it.name…)` |
| "This action is **A4** … **BIOMETRIC_STRONG**" | `:295` |
| "command **HMAC** credential" | `:1081` |
| `reason_code`, `current_scope_json`, `requested_scope_delta_json` as raw JSON | `:749-752` |
| `autonomy_tier`, `injection_assessment` | `:831,853` |
| `truth_sha`, `repo_sha` | `:555` |
| Raw `payload.toString()` as the entire Activity feed | `:600` |
| `Degraded: <raw JSON array>` | `:1005` |
| Trading empty state instructing the owner to run `python -m vati lake …` | `TradingScreens.kt:283` |
| Unformatted float — "cap 2.0000000000000004%" | `TradingScreens.kt:412,413,424` |

There is no greeting, no agenda, no plain-English summary anywhere in the Command Centre. A capable
engineer would find this usable. The owner of a personal intelligence would not recognise it as one.
Recorded as **P2-UX-001**.

Note the genuine irony: `android/.../mission/MissionRepository.kt` contains exactly the owner language
the product needs — `ownerReadableStatus` renders "Waiting for you" and "Finished, but Van could not
confirm it worked" (371 lines of it) — and `grep -rn "MissionRepository("` returns **one hit: its own
declaration**. The good vocabulary is written and unused. **IMPLEMENTED_BUT_ISOLATED.**

### 13.3 Networking

`VanGatewayClient.kt` (535 lines) uses raw `HttpURLConnection` — no OkHttp, no Retrofit. Two auth
headers (`:497-502`), plus a real HMAC-SHA256 signature over a 19-field canonical string on
`POST /v1/commands` (`:365-386,463-468`). HTTPS is enforced in code (`:65-75`) and at release assembly
(`build.gradle.kts:71-93`).

Defects:

- **No retry, no backoff, no circuit breaker anywhere.**
- 40 endpoint methods are declared; **only 14 are ever called.** All four mission methods, `needsYou`,
  `activityFeed`, the six understanding methods, permissions, autonomy, technology radar, eval report,
  briefing and attention are dead code (`:139,200,231-329`).
- `/health` is polled every 60 s (`VanApplication.kt:199`). `/v1/events` is **not polled** — there is a
  single call, `events(0)`, in `ActivityModule`'s `LaunchedEffect(Unit)` (`CommandCentreActivity.kt:580`),
  with the cursor hardcoded to 0 and never persisted.
- Zero hits for SSE, WebSocket, FCM, `ConnectivityManager` or `WorkManager`.

### 13.4 The command path is honest and then permanently frozen

The honesty is real and deserves credit. The default response text is
*"Hermes accepted the command. Completion has not been confirmed yet."* (`VanCommandController.kt:284`),
and `publishCommandVisualStatus` carries the comment "without inventing task completion"
(`VanGatewayClient.kt:431`). VAN does not lie about success.

But **a completion can never arrive.** `recordResponse` is the only status writer and is called only
from the single synchronous HTTP response (`:162,221`). No `/v1/commands/{id}` method exists (and no
such route exists server-side — §6.1). The one `events(0)` result is never joined to a message. Every
long-running command therefore displays `ACCEPTED` forever.

Further: `understood` and `planned` states do not exist at all; `executing`, `verifying` and `submitted`
all collapse to `ACCEPTED` (`:248`); and an unknown gateway status falls through to
`else -> ACCEPTED` (`:255`) — a failure mode that silently reads as progress. Command history is an
in-memory `MutableStateFlow`, never persisted.

Recorded as **P0-EXEC-003** (device side of P0-EXEC-001).

### 13.5 Trading UI — the one genuinely integrated owner surface

This is the best screen in the application, and it is the only part of the Android app that looks like a
product. Real `NavHost`, 7 routes, Material3 navigation bar
(`TradingCommandCentreActivity.kt:96-144`). Multi-account, positions, history, potential trades and risk
(heat, drawdown, concentration, mandate limits — `TradingScreens.kt:400-453`) are all present, with real
candlestick rendering from pure geometry (`TradeChartCanvas.kt`). **Data is live gateway, with zero
fixtures** — verified by grep for TODO/fixture/sample/mock across the whole main source set. On failure
`TradingRepository` returns `Loaded.Unavailable("Gateway unreachable…")` with no fabricated fallback.

Gaps: alerts are **ABSENT** (grep "alert" in `trading/` → zero); account-scope chips exist only on
Overview (`:75,91-94`) so Trades/Risk/Instrument ignore the selected account; and "Ask Van about $symbol"
(`:392`) calls `startActivity(CommandCentreActivity)` with **no extras** (`:88,133`), dropping all
context — a visible seam in the unified-experience principle.

### 13.6 Offline, degraded and state handling

`DegradedMode.kt:48-63` declares 8 subsystems. Only gateway, hermes and google are driven by real
`/health` data (`VanApplication.kt:109-134`); **overlay, queue, notifications, voice and biometric are
hardcoded `WORKING` and never written** (`:51-55`). All seven `RestoreAction` values are defined and
never rendered.

The offline queue is effectively inert for owner commands: `replayAsync()` is called exactly once, at
`VanApplication.kt:78`, with no connectivity or health trigger, and **owner commands never enter the
queue** — `submit` dispatches directly and, on failure, writes a "Command dispatch failed" bubble
(`:310-324`). Offline behaviour classification: **STUB**.

`grep rememberSaveable|onSaveInstanceState|ViewModel|configChanges` across the whole main source set and
manifest returns **zero hits**. Rotation destroys the selected module, the chat draft, every module's
fetched data, and the onboarding position (`OnboardingActivity.kt:80` returns to step 0). There is no
`androidx.window`/WindowSizeClass, and `res/` has no `-night`, `-sw600dp` or other qualifier directories.
Four `contentDescription`s exist in the entire application; `CommandCentreActivity` has none, and
`TradeChartCanvas` is a silent Canvas. Touch targets include an 18 dp clickable icon
(`TradingScreens.kt:66`) and ~29 dp chips. Type runs 8–12 sp with `maxLines=1`. Dark mode is hardcoded
(`darkColorScheme` in all three activities, no `isSystemInDarkTheme`).

Accessibility and adaptive layout classification: **ABSENT.**

### 13.7 Two structural Android defects

**Share-to-VAN is non-functional.** `ShareIntentReceiver` is declared as a `<receiver>` with
`ACTION_SEND`/`ACTION_SEND_MULTIPLE` intent filters (`AndroidManifest.xml:77-105`) and implemented as a
`BroadcastReceiver` (`share/ShareIntentReceiver.kt:21`). Android's share sheet resolves against
*activities*; a broadcast receiver never appears in it and is never invoked. The capability is listed in
the device acceptance checklist (`docs/EXTERNAL_GATES.md` physical device checklist: "share-to-VAN
routing"). Recorded as **P1-AND-001**.

**Onboarding never pairs the device.** `OnboardingActivity.kt:101-153` covers overlay, notifications,
listener, microphone and biometric permissions. It contains **no gateway pairing step**; pairing lives
buried at Home → Connections (`CommandCentreActivity.kt:1026-1093`). A first-run owner therefore lands on
a dashboard where every card fails with `ingress_token_unconfigured` and no explanation. Additionally the
steps advance on `startActivity(settings)` rather than on an actual grant (`:106-114,130-133`), and
nothing re-checks `canDrawOverlays` or the enabled-listener set. Recorded as **P1-AND-002**.

### 13.8 Android security — genuinely strong

`OwnerApprovalKeyManager` generates an EC secp256r1 key **inside** the Android Keystore with
`setUserAuthenticationRequired(true)`, `AUTH_BIOMETRIC_STRONG` and
`setInvalidatedByBiometricEnrollment(true)` (`:28-49,78`). `BiometricGate.requestA4CommandApproval` signs
the challenge inside `onAuthenticationSucceeded` via `result.cryptoObject.signature` (`:84-88,104-107`).
`EncryptedCommandQueue` uses Keystore AES-256-GCM with a randomised IV and 128-bit tag over
EncryptedSharedPreferences (`:156-193`). This is correct, real cryptography.

One defect: the **weak** `requestA4Approval` overload (`BiometricGate.kt:22-53`, no `CryptoObject`) is
what guards trading account and credential changes (`AccountOnboardingScreen.kt:26`). Recorded as
**P1-SEC-004**. There is no certificate pinning and no `res/xml` network security config.

### 13.9 Android test reality

24 unit test files, 2,073 lines, **129 `@Test` methods** — 68 visual, 18 voice, 16 trading, 11 mission,
9 overlay, 5 queue, 2 degraded. There are **zero tests** for `CommandCentreActivity`,
`VanCommandController`, `VanGatewayClient`, `QueueReplayer`, notifications, share, `BiometricGate`,
`OwnerApprovalKeyManager`, onboarding, or any Composable.

**No instrumentation tests exist at all**: `android/app/src/` contains only `main/` and `test/`; there is
no `androidTest/` source set, despite `testInstrumentationRunner` being configured
(`build.gradle.kts:30`). `tests/contracts/test_android_dashboard_navigation.py` is 57 lines of
`read_text()` plus substring assertions on Kotlin source (`assert "horizontalScroll" not in text`) — a
lint rule that would pass on code that does not compile.

---

## 14. Voice audit

### 14.1 What is actually wired

Exactly one voice path works end to end:

```
owner taps "Voice"  →  Android on-device SpeechRecognizer  →  final transcript
   →  VanCommandController.submitText(source = VOICE)
   →  HMAC-v2 signed POST /v1/commands (origin_channel=VOICE, speech_evidence_ref)
   →  gateway authority pipeline  →  Hermes
```

The signing is real: `speech_evidence_ref` is inside the canonical string the device HMAC covers
(`auth/service.py:302,329`), so transcript provenance is cryptographically bound to the command.
ASR is on-device only — `createOnDeviceSpeechRecognizer` with `EXTRA_PREFER_OFFLINE`
(`VoiceInterfaces.kt:73-88,268-302`) — which honours the stated core rule that the recogniser must not be
cloud-backed. The audio arbiter is real work: a single `AudioRecord` at 16 kHz with AEC/NS, a 750 ms
pre-roll ring buffer and a bounded pipe (`VoiceAudioArbiter.kt:51-119,172-223`).

### 14.2 What is not wired

| Requirement | Status | Evidence |
|---|---|---|
| "Hey Van" wake word | **ABSENT** | `WakeWordEngine`, `WakePhraseVerifier`, `SpeakerSimilarityScorer` are `fun interface`s (`WakeRuntime.kt:31-44`) whose only implementations are constant lambdas in tests. `build.gradle.kts:128-161` contains no Porcupine/Vosk/Whisper/sherpa/ONNX/TFLite/ML Kit; no `jniLibs`, `.so` or `.ppn` anywhere. |
| Wake phrase configured | **ABSENT** | The only literal is the acknowledgement text `"hie van"` (`WakeAcknowledgement.kt:15`). The string "Hey Van" appears nowhere in the repository. |
| Wake pipeline armed | **ABSENT** | `WakePipeline`, `WakeRuntimeController`, `WakeCoordinator` are never constructed in production; `VanApplication.kt:59-80` builds no wake pipeline; `WakeCoordinator.arm()` has no caller. |
| Local wake acknowledgement | IMPLEMENTED_BUT_ISOLATED | Real pre-render via `TextToSpeech.synthesizeToFile` → SoundPool `USAGE_ASSISTANT` (`WakeAcknowledgement.kt:33-115`), instantiated at `VanApplication.kt:66`, designed to play before recognition — **`play()` has zero call sites**. |
| **VAN speaks at all** | **ABSENT in practice** | `TtsOutputManager.speak()` (`VoiceInterfaces.kt:414`) has zero call sites app-wide. Verified independently by the lead: the only `.speak(` in the whole app is the internal `tts?.speak` on line 416. |
| Second-pass ASR fusion | IMPLEMENTED_BUT_ISOLATED | Policy and fusion are real and tested (`VoiceSecondPass.kt:28-102`), but `LocalSecondPassAsr` has no implementation and `VoiceInputManager` is constructed with `secondPassCoordinator = null` (`VanApplication.kt:70-74`). |
| PersonalSpeechModel adaptation | PARTIAL | A real encrypted confusion-edge graph exporting bias strings to `EXTRA_BIASING_STRINGS` (`PersonalSpeechModel.kt:32-56,125-160`) — but `recordCorrection()` and `pinTerm()` have no callers, so the model is always empty. It is vocabulary biasing, not acoustic adaptation. |
| Barge-in | STUB | Manual only via `beginOwnerTurn` (`VoiceInterfaces.kt:445-448`), unreachable because TTS never speaks. |
| Hands-free / continuous conversation | **ABSENT** | `commandTurnFinished` rearm hook (`WakeCoordinator.kt:111`) never called; no conversation id anywhere. |
| Background operation | **ABSENT** | FGS type is `specialUse`, not `microphone` (`AndroidManifest.xml:50-57`); voice starts only from taps. |
| Latency measurement (P95 targets) | **ABSENT** | `startedAtMs`/`finalizedAtMs` are never read; `vaneval.py:78-81` declares the VOICE dimension unmeasurable. |
| Mission binding | **ABSENT** | `orchestrator.py` imports nothing from `mission/`; `CommandRequest` and `VanOwnerCommand` carry no `mission_id`. |
| Audio focus | **ABSENT** | no Android `AudioFocus` request exists. |

Devices without Google on-device ASR, or on API ≤ 30, get `SHERPA_PRIMARY_REQUIRED` → recogniser `null` →
`ERROR_SHERPA_PRIMARY_REQUIRED` (`VoiceRecognitionModels.kt:45-59`): **voice input simply fails**, and no
fallback engine is bundled.

### 14.3 The canonical voice test case

The blueprint's own example — *"Create a NotebookLM notebook for this project"* — traced through the
committed code:

1. No wake word exists, so the owner must tap Voice.
2. On-device ASR yields the transcript. No second pass, no correction capture.
3. A signed A1 VOICE command is sent.
4. `command/resolver.py:86-89` note patterns do not match this phrasing → `HERMES_INTERPRETATION_REQUIRED`.
5. The gateway returns `accepted` with *"Accepted and routed to Hermes profile van…"* (`orchestrator.py:566-576`).
6. Android renders that sentence as a chat bubble (`VanCommandController.kt:280-282`).
7. **VAN says nothing aloud.** No completion, no verification, ever returns to that voice turn.

The good news: VAN does **not** claim success before verification. The bad news: it gives no spoken
feedback at all, and the interaction ends at "accepted" forever.

**Voice verdict:** the gateway-side contract for voice (signed transcript provenance, origin channel,
same authority path as typed input) is correctly built. The Android voice *experience* — wake, speak,
interrupt, converse — is a set of well-designed interfaces with no implementations behind them. The
matrix's WS28 note, *"Wake pipeline, 'hie van' pre-rendered ack, PersonalSpeechModel, second-pass ASR
fusion and signed transcript provenance all exist. Mission binding is the delta"*
(`...MATRIX.json` WS28), materially overstates the state. The real deltas are: a keyword-spotting engine,
a phrase verifier, a local ASR fallback, a microphone-typed foreground service and arming, acknowledgement
playback, any TTS invocation, correction capture, and mission binding. Recorded as **P1-VOICE-001**.

---

## 15. Floating VAN bot — embodiment, aura and semantic state

This is a major product surface and received the deepest single inspection in this audit.
Scope: 5,944 lines across `visual/` (22 files) and `overlay/` (7 files), 12 visual unit test files,
the `visual-preview` JVM renderer, and every committed PNG.

### 15.1 Aura rendering — a real detached field, drawn with vector primitives

`VanAura.kt:26-43` is a plain Compose `Canvas`. The entire field is composed from three primitive
families only: stroked paths for filaments (`:79-96`), circles for ion dots (`:116-125`), and
`Brush.radialGradient` circles for the Zone A haze (`:208-225`).

Verified absent across the whole visual package: `RuntimeShader`, AGSL, `RenderEffect`,
`Modifier.blur`, `MaskFilter`, and any procedural noise (Perlin/simplex/hash-lattice). "Glow" is a
second, wider, lower-alpha stroke of the same path; "bloom" is a 2.8× radius circle at alpha × 0.16.
Pseudo-randomness is the classic GLSL sine-hash used per element, not as a spatial noise field
(`VanFieldGeometry.kt:504-507`).

**The structural requirement is met: this is not a border, not a ring, and not a body-hugging glow.**

| Required quality | Present | Evidence |
|---|---|---|
| Wave motion | YES — 3 summed harmonics | `VanFieldGeometry.kt:467-471` |
| Phase evolution / advection | YES | `:467-469,475-479` |
| Turbulence / curl | PARTIAL — one extra sinusoid | `:472-473` |
| Field displacement | YES | `VanWindFieldMotion.kt:57,66-69` |
| Irregular perimeter | YES — open ribbons in a wind basis | `VanFieldGeometry.kt:400-445` |
| Layered glow | PARTIAL — faked by 2-pass stroking | `VanAura.kt:79-96` |
| Depth | WEAK — alpha/width tiering only | `VanFieldGeometry.kt:85` |
| Translucency | YES | `VanAura.kt:81,178` |
| Breathing | YES — ±1.8–5.3% radial | `VanWindFieldMotion.kt:52-55` |
| Electrical activity | YES — forked branches with birth/death | `VanFieldGeometry.kt:320-398` |
| Constrained randomness | YES — deterministic seeds | `VanFieldGeometry.kt:504-507` |
| **Volumetric / noise turbulence** | **NO** — sums of sines only | §15.1 |
| **Real blur / bloom** | **NO** — wide low-alpha strokes | §15.1 |

The non-ring invariant is not merely claimed, it is **tested**: `VanFieldRev3Test.kt:58`
`frozenFrameDoesNotCollapseToCommonRadiusHalo` checks radius variance, and
`VanEffectPolicyTest.kt:28` asserts no full ring. Body detachment is tested at
`VanFieldGeometryTest.kt:78` and `VanFieldRev3Test.kt:21`. These are genuinely good tests.

### 15.2 Three defects that undermine the aura on the real device

**(a) The body gap is scale-relative and too small at the shipping size.** The exclusion profile
expresses everything as a fraction of `bodyEdge`: `gap = bodyEdge * 0.055`
(`VanBodyExclusionProfile.kt:162`). There is **no dp anywhere** in the exclusion maths. The floating
character is 96 dp (`OverlayTheme.kt:14`), giving a gap of **5.3 dp** against the Rev 3.0 §15
requirement of a 10–14 dp minimum. No test asserts any dp gap. **P2-AURA-001.**

**(b) There is no monotonic animation clock, and every state change is a hard cut.** Rev 3.0 §22
requires "one monotonic visual clock, never restarted on recomposition or transition".
`grep withFrameNanos` returns zero hits app-wide. The only driver is
`rememberInfiniteTransition` whose tween **duration changes per state**
(`VanCanvasFallback.kt:250-279`: 2000 ms for LISTENING/WORKING, 2800 ms for URGENT/WARNING,
6000 ms for SLEEPING/OFFLINE, 4200 ms otherwise). Changing state replaces the transition object and
restarts the ramp. Worse, Rev 3.0 §25 requires 120–420 ms blended pose transitions, and:

```
grep "animateColorAsState|animateFloatAsState|Crossfade|animateDpAsState|lerp\(" visual/ overlay/
  -> NO MATCHES
```

**Every aura state change and every pose change is a one-frame snap.** Intensity, filament count,
envelope segments, envelope radius and semantic colour all change on the next composed frame.
**P1-AURA-002.**

**(c) The geometry is rebuilt every frame.** `VanFieldGeometryEngine.build()` allocates fresh lists
and rebuilds all 35-point polylines per frame (`VanFieldGeometry.kt:74-76,415-444`) — several hundred
point allocations per frame per VAN instance, which is precisely what Rev 3.0 §19/§42 says to avoid.
There is no frame-time measurement anywhere: `VanEffectConditions.frameBudgetMissed`
(`VanEffectBudget.kt:247`) has **no producer**, and no `Choreographer`/`JankStats` exists.
Thermal and power-save state are sampled **once per composition** (`VanCanvasFallback.kt:159`) and
never re-polled. **P2-PERF-001.**

### 15.3 The semantic state machine — the strongest design in the visual stack

`RiveContract.kt:7-31` declares 18 durable states, and `VanPresenceFrame.kt:10-16` adds four
**orthogonal** channels: health, authority, speech and turn phase. This orthogonality means
"listening while the Google mesh is unverified" correctly renders a LISTENING body with a DEGRADED
Zone C rather than one state clobbering the other. It is tested (`VanFieldGeometryTest.kt:38`,
plus 19 tests across `VanPresenceFrameTest` and `VanPresenceTest`).

Arbitration is real: an integer priority ladder (`VanLiveVisualState.kt:177-188`), a 320 ms
anti-thrash hold (`:84-87`), and a generation token so a stale delayed idle cannot clobber a newer
state (`:118-135`). This is correct, careful engineering.

**But 10 of the 22 required semantics are absent or preview-only:**

| Required state | Status |
|---|---|
| hearing (distinct from listening), interpreting, planning, tool use, browser use, interrupted | **ABSENT** |
| researching, executing, waiting-external, reconnecting | PARTIAL — `SEARCHING`/`WORKING`/`WAITING`/`CONNECTING` exist; `WAITING` and `CONNECTING` are never set by any production caller |
| trade opportunity, trade management, restrained/high-risk | **ABSENT from the state machine** — preview-only specs |

And the production surface that writes visual state is very narrow. `grep -rn "VanLiveVisualState\."`
gives **every** mutation site: voice recognition in `VanApplication.kt:151-195`, and the gateway
command envelope in `VanGatewayClient.kt:419-459`. That is all. No mission, no tool, no browser, no
trading subsystem ever writes VAN's visual state.

### 15.4 Trading → aura: ABSENT

This was a headline requirement of the audit and the answer is unambiguous.

```
grep -rniE "aura|van_state|visual_state|durable_state|semantic_state"  backend/ trading/ hermes/
  -> ONE hit, an unrelated persistence test (test_automation_compiler.py:421)
grep -rn "VanLiveVisualState|VanAura|VanDurableState" android/.../trading/
  -> five hits, ALL read-only
```

`TradingCommandCentreActivity.kt:78` computes `VanPresence.cue(degraded)` — VAN's presence on the
trading screen derives **only from the gateway's degraded-code set**, not from any trade. Worse,
`:81` caches it with `remember(cue.durableState)`, so it cannot even change as the screen polls
market data.

The nearest thing to a binding is `VanAuraSpecs.tradePreview(kind)` (`VanAuraSpec.kt:238-299`), which
defines eight trade semantic families (watching teal, setup violet, entry gold, in-trade cyan, profit
green, risk amber, stop red, urgent vivid red) with distinct Zone C topologies. Its own KDoc says
*"architecture capacity, not a live trading product"* (`:237`), and its **only caller in the entire
repository** is the PNG evidence-board renderer (`VanPreviewSheets.kt:750`). It is not referenced from
`android/app` at all, the families are not members of `VanDurableState`, and so no arbitration, no
priority ladder and no Rive input can carry them.

**Classification: the trade aura families are a rendered mock-up, not a binding.** A kill switch
tripping, a position going three multiples of risk against the owner, or a
`REJECTED:MAX_DAILY_LOSS` produces no change whatsoever in VAN's presence. **P1-AURA-003.**

### 15.5 Body animation — bitmap swaps, not articulation

The renderer ladder is RIVE → OWNER_ART → CANVAS (`VanVisualRuntime.kt:243-258`). Hard facts:

```
find android/app/src/main -type d -name assets -o -type d -name raw   -> NOTHING
find . -name "*.riv"                                                   -> NOTHING
grep rive android/app/build.gradle.kts -> implementation("app.rive:rive-android:9.6.5")
```

**There is no `.riv` asset anywhere, while the multi-megabyte Rive runtime with native libraries ships
in the APK.** `context.assets.open(...)` throws, and `decide()` returns `ASSET_MISSING`. The Rive path
is dead code on every build. To the project's credit this is surfaced honestly in the UI and in the
evidence boards, and it is listed as an external gate.

The shipping rung is OWNER_ART: a single `Image(painterResource(...))` (`VanCanvasFallback.kt:103-116`)
selecting one of **eight bitmaps for eighteen states** (`VanArtPose.kt:85-116`). IDLE, CONNECTING,
SPEAKING, SLEEPING and OFFLINE all render the *same* image, so transitions between them are
invisible in the body. There is no `Crossfade` and no `AnimatedContent` — pose changes are hard cuts.

Continuous life does exist and is nicely bounded: `VanCharacterMotion.sample()` applies four
desynchronised harmonics to offset, rotation and scale, with tested envelopes of ≤1.65 dp bob,
≤0.82° sway and ≤0.7% scale (`VanCharacterMotion.kt:129-211`, `VanCharacterMotionTest.kt:61-85`
exhaustive over 18 states × 201 phases). It is a very subtle float, not articulation — and because
the harmonics are at 1.31/0.57/2.17× they are not period-1, so the character motion **does** jump at
each phase wrap every 2–6 seconds.

### 15.6 Overlay lifecycle

Genuinely good: gestures are attached **only to the VAN embodiment, not the workboard**
(`FloatingOverlayService.kt:243-260,276-279`), so board scrolling never drags the overlay — one of the
Rev 3.0 hard prohibitions, correctly honoured. Drag clamps to screen bounds, snaps to an edge within
48 px, persists position/dock, and offers a bottom-centre dismiss target with haptic arming.
`START_STICKY` plus `OverlayRecoveryReceiver` on `BOOT_COMPLETED`/`MY_PACKAGE_REPLACED` covers restart.

Defects:

- **No `Settings.canDrawOverlays` check inside the service.** `onCreate` calls `addView` unguarded
  (`:155`); if the permission was revoked the service crashes.
- `startForeground` (`:157`) and `startForegroundService` (`:1024`) are **not wrapped in try/catch**;
  on API 31+/34 a `specialUse` FGS restarted from the background can throw.
- **The animation never stops.** The custom lifecycle is driven to `STARTED` and never below while the
  service lives (`:156,174`). There is no `ACTION_SCREEN_OFF` receiver and no visibility check, so
  `rememberInfiniteTransition` keeps animating the aura at 2–6 s per cycle **with the screen off**.
  **P1-PERF-002.**
- MINIMIZED renders `VanMinimizedAvatar` only, which draws **no aura at all** — minimized VAN has no
  living field.

### 15.7 Visual evidence — the largest evidence finding in the audit

**(a) Evidence could not be regenerated here.** Both attempted builds of `:visual-preview` failed
because the root `android/build.gradle.kts:1` declares the Android Gradle Plugin for the whole build,
so even the pure-JVM preview module cannot configure without resolving AGP, which this environment
cannot reach. Recorded as NOT VERIFIED, not as a defect.

**(b) The evidence pipeline is only partly shared.** `visual-preview/build.gradle.kts:14-38` compiles
the *same source files* for `VanFieldGeometry`, `VanWindFieldMotion`, `VanBodyExclusionProfile` and
`VanAuraSpec` — so the point positions in the PNGs really are the numbers the device computes. That is
an unusually good property. **But `VanAura.kt` is not in that list**: the painter is re-implemented in
AWT (`GlassPainter.kt:215-314`), and the two diverge materially:

| Aspect | Compose (ships) | AWT (evidence) |
|---|---|---|
| Electrical branches | drawn, 3-pass | **not drawn at all** — zero references |
| Zone A alpha | clamp 0.035–0.085 | clamp 0.08–0.18 (≈2× brighter) |
| Zone A radius | `bodyEdge × 0.13` | `bodyEdge × 0.20 × scale` (≈1.5× larger) |
| Zone A blob placement | `± bodyEdge × 0.31/0.34` (off the body) | `± bodyEdge × 0.05/0.07` (on the body) |
| Dot bloom | 2.8× bloom circle | none |

So the boards show **less** than the device in one respect (no electrical life) and **more** in
another (a brighter, larger, closer haze). The build file's claim that drift "shows up in previews" is
true for geometry and false for the painted result. **P1-VIS-001.**

**(c) The committed evidence is two authority revisions stale.** `VanEvidenceMatrix.kt:36` sets
`EVIDENCE_DIR = "rev23"`, and `VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md §13` states that the Rev 2.3
generator writes `artifacts/release/preview/rev23/` and no longer writes `rev21/`. The repository
contains **only `rev21/`**, whose manifest declares `authority_revision: "2.1"`, while
`visual-authority/van-visual-authority-v2.yaml` is at revision 2.3. The doc's central certification
board, `van_orthogonal_presence.png`, does not exist (`find artifacts -name "*orthogonal*"` → nothing).
**Every committed PNG was produced by an older generator against an older authority revision.**
**P1-VIS-002.**

**(d) A manifest integrity defect.** In `artifacts/release/preview/rev21/manifest.json`, the entries
`command-centre-idle` and `command-centre-degraded` carry the **identical** SHA-256 and identical byte
count. Visual inspection confirms it: the file named `-idle` renders a page headed "Van / **Degraded** /
Some subsystems are down." The IDLE evidence shot is a DEGRADED render. **P2-VIS-003.**

**(e) What the images honestly show.** Read directly: the aura in every board is **a handful of thin,
hairline, unconnected teal arcs** at roughly one to one-and-a-half body widths out, plus two or three
dots. There is no visible haze, no volume, no gradient field. In the five-rung effect-budget ladder all
five cells look essentially identical. Across the 18-state matrix, roughly seven distinct bodies and
four distinct arc colours are discernible; most per-state differentiation comes from the **baked-in
bitmap prop** (warning triangle, tick, envelope) and the text label, not from the aura — which is
precisely what the Rev 2.2 anti-patterns warn against. All eight trade-state cells use the identical
character bitmap. Every artefact is a **single frame at one hardcoded phase** (`GlassPainter.kt:222`,
`phase = 0.18f`); motion is literally not depicted anywhere, and there are no device screenshots, no
animation frames and no video.

### 15.8 What the visual tests cannot prove

The tests are good at what they cover (non-ring invariant, body detachment, grayscale distinctness,
orthogonality, motion envelopes, Zone C coverage and uniqueness). They structurally cannot prove:

1. **Motion quality** — every test samples the pure geometry function at chosen phases. The one
   catchable defect, the phase restart at state change, is invisible because `vanIdlePhase` is a
   `@Composable` never exercised.
2. **The Compose painter** — zero tests touch `VanAura.kt`. Alphas, glow widths and the electrical
   draw calls are entirely unverified, which is exactly where the device/evidence divergence lives.
3. **GPU and frame cost** — no benchmark, no macrobenchmark module, no jank sampling.
4. **Perceived aura** — `VanAcceptanceGateTest` compares two freshly-rendered images **to each other**,
   never to a committed baseline. A regression that dimmed or deleted the whole field would keep every
   test green.
5. **Anything on a device** — there is no `androidTest` source set at all.

### 15.9 Floating bot classification

| Aspect | Class |
|---|---|
| Floating overlay lifecycle | INTEGRATED (with three unguarded-exception defects) |
| Aura rendering | INTEGRATED — a real vector field, not a ring; no shader/noise/blur |
| Aura semantic state machine | PARTIAL — excellent arbitration, 10 of 22 semantics missing, no transitions |
| Trading-state binding | **ABSENT** |
| Body animation | PARTIAL — 8 bitmaps for 18 states, hard cuts, subtle micro-motion |
| Rive embodiment | **ABSENT** (honestly declared; runtime shipped without an asset) |
| Visual evidence | PARTIAL and **STALE** — divergent painter, two revisions old, one mislabelled frame |

---

## 16. Trading system audit

Trading received strict treatment because it is the only high-consequence domain in the product.

### 16.1 The order path is a single, correct funnel

`python -m vati serve` → `SessionService.build()` → `SessionRunner` → `DecisionCycle.step()`.
Every link is real code:

```
bars (BarLake, on disk)
  → build_market_state()            cycle.py:131          REAL
  → OpportunityEngine.assess()      cycle.py:137          REAL
  → TradeIntent                     cycle.py:141-143      REAL
  → RiskAuthority.evaluate_safe()   cycle.py:145          REAL   ← the only gate
  → ExecutionRouter.execute()       cycle.py:158-160      REAL
  → adapter.submit()                router.py:81          REAL   ← venue boundary
  → hash-chained ledger             core/ledger.py        REAL
```

**No model, UI, commander or gateway path can send a broker order without the Risk Authority.**
Enumeration confirms a single funnel at `cycle.py:145 → :159 → router.py:81`. The commander has no
order command at all; its only write to the trading plane is a `KILL_SWITCH` ledger append. The
capability registry declares `trading.vati.submit_order` as A4 with
`readiness_source: NEVER_ROUTABLE` and an explicit `never_routable_reason` so the generic fabric
cannot reach it as a side channel. `NO_TRADE` is a genuine first-class outcome
(`arbiter/opportunity.py:72-77`). Sealed, hash-recomputable risk decisions with router refusal on
hash mismatch (`router.py:56`) and ledger append-only enforced **at the database grant level** are
genuinely strong engineering.

### 16.2 Eight safety findings

**P0-TRADE-001 — "Owner-signed" is a non-empty string, everywhere.**
`trading/vati/risk/mandate.py:156-157` is the *entire* mandate verification:

```python
if not str(data["owner_signature_ref"]).strip():
    raise MandateError("mandate is unsigned (owner_signature_ref empty)")
```

No signature algorithm, no public key, no authority-record lookup, no revocation check. The identical
pattern repeats in `risk/governor.py:51-53` (kill-switch clear), `app/runner.py:55-57` (owner halt),
`strategies/capsule.py:101-102` (capsule promotion), `commander/app.py:226-228` and
`backend/van_gateway/trading/service.py:208-212`. Anyone who can write a session config, or reach the
gateway's internal-token endpoint, can mint a mandate that the Risk Authority honours as owner
authority, bounded only by `PlatformCeilings` (2% per trade, 6% heat, 5% daily, 10% weekly). The
ceilings, not the signature, are the real last line of defence. The only mandate shipped in the
repository is `trading/examples/mandate.fx_primary.example.json:46`:
`"sig:owner-device:REPLACE_WITH_DEVICE_SIGNATURE_REF"`.

**P0-TRADE-002 — The live risk snapshot hardcodes three safety flags to healthy.**
`cycle.py:118-119` sets `reconciliation_ok=True`, `risk_store_ok=True`,
`tier1_event_blackout_active=False`. The authority's `RECONCILIATION_FAILED` (`authority.py:173`),
`RISK_STORE_UNAVAILABLE` (`:177`) and `EVENT_BLACKOUT` (`:197`) gates are therefore **unreachable in
the live path** and only fire in tests that hand-build a snapshot. Reconciliation is checked once at
startup and never again, so a broker position appearing mid-session is not detected. `self.integrity`
(`cycle.py:88`) is never written, so `MARKET_INTEGRITY` and the elevated half-size reduction are dead
too.

**P0-TRADE-003 — Owner halt is asynchronous, polled, and lost on restart.**
The gateway and commander only append a `KILL_SWITCH` event; the running session notices on its next
loop, up to `poll_seconds` (default 5.0) later. Worse, `_observe_owner_halt` filters
`ev.event_time_ms >= self._started_ms` (`service.py:181`), so **restarting the session discards an
active owner halt** — and `restart_service` is an exposed commander command (`commander/app.py:97`).

**P0-TRADE-004 — The gateway reads the wrong ledger by default.**
`config.py:21` sets `vati_ledger_path = "data/vati_ledger.sqlite3"` while the trading VM writes to
Supabase Postgres. No code path makes the gateway talk to the commander for ledger reads, and nothing
in `deploy/` reconciles the two. Out of the box the owner's app shows an empty, permanently degraded
trading surface; with a stale local file it would show **old data presented as current**, because
`last_event_ms` is not thresholded server-side.

**P0-TRADE-005 — The idempotency key is session-scoped.** The key derives from
`session_id = f"{alias}:{symbol}:{clock()}"`, so a crash-and-restart on the same bar yields a
*different* key and neither the in-process set nor the ledger-seeded router set blocks a duplicate
order. Nothing prevents two `serve` processes for one alias.

**P0-TRADE-006 — No margin model.** `AccountState` carries equity and balance only; there is no
margin, free-margin or margin-level field anywhere in `trading/`. The Risk Authority sizes by stop
distance with no visibility of broker margin.

**P1-TRADE-007 — Strategy targets are discarded.** `cycle.py:150-157` throws away the winning
signal's target and re-derives one from `expected_gross_move_pct`, alongside dead code
(`sig_targets = ()`, `for c in oa.candidates: pass`) sitting in the live order path.

**P1-TRADE-008 — Learning is silently inert in production.** `SessionService.build()` does not pass
`learning=` (`service.py:143`), so capsule-health demotion, broker-liquidity learning and experience
artefacts exist only in backtests. The learning boundary itself is well designed (reduce-only,
demote-only, evidence-required, 30-sample minimum) and simply never runs live.

### 16.3 What the live attestation actually certifies

`artifacts/runtime/van_trading_core_reconciliation_live_attestation.json` (2026-09-18, certified
commit `54ee68fe`) certifies **infrastructure only**: qualification GREEN, automation fabric green,
Supabase green, firewall green, Caddy active, public TLS green, ledger backend PostgresLedger, chain
valid, six services active, and component versions.

Its own `non_required_amber` rows are decisive, verbatim:

1. *"no session heartbeats yet because no trading account is enabled"*
2. *"MT5 is external to the ARM64 Trading Core and runs on the Windows bridge worker"*

Row 1 means **no `vati serve` session has ever run on that host**: no decision cycle has stepped, no
risk authority has evaluated a live intent, no adapter has connected to a broker. `ledger_chain_ok:
true` is the integrity of an effectively empty chain. **Nothing in this repository attests a single
live broker order on any venue.**

### 16.4 Trade state → VAN experience: where the chain breaks

Inside `trading/` the classification is rich and well-formed: `MARKET_STATE` with regime and
integrity, `OPPORTUNITY_ASSESSMENT` (TRADE/REDUCE_SIZE/WAIT/SKIP/NO_TRADE), `RISK_DECISION`
(APPROVED/REDUCED/REJECTED + reason code), `MARKET_DATA_HEALTH` (LIVE/DELAYED/STALE/NO_DATA), across
23 ledger event kinds. The required propagation is
`market state → analysis → classification → risk authority → VAN semantic state → aura → owner`.

```
cycle.py:134/139/146   MARKET_STATE / OPPORTUNITY_ASSESSMENT / RISK_DECISION      ✅
        ↓ ledger append                                                            ✅
service.py:93-130      TradingService read models                                  ✅
app.py:770-878         GET /v1/trading/*                                           ✅
        ↓  ❌ BREAK 1 — no event, no push. Nothing writes to /v1/events; Android polls.
        ↓  ❌ BREAK 2 — no classification for the experience layer. The payload is
        ↓               numbers plus one English prose sentence (`van_summary`);
        ↓               no semantic_state token, no severity, is ever computed.
TradingRepository.kt   7 polling calls                                             ✅
        ↓  ❌ BREAK 3 — no mapping. Nothing feeds VanLiveVisualState.
VanLiveVisualState     driven ONLY by dispatch/approval outcomes                   ✅ (wrong source)
```

The required flow is broken at three independent points. **ABSENT**, recorded jointly with
P1-AURA-003.

### 16.5 Execution transports and trading classification

| Component | Class | Note |
|---|---|---|
| Risk Authority | IMPLEMENTED_BUT_ISOLATED | logic integrated into the cycle; never exercised against a real venue; 3 health gates dead in the live path |
| Decision cycle | **SIMULATED** | proven end-to-end only over `PaperAdapter` and synthetic bars |
| MT5 push bridge (Windows worker) | IMPLEMENTED_BUT_ISOLATED | full mTLS round-trip tested; attestation says MT5 is external and unexercised |
| MT5 pull bridge (MQL5 EA) | IMPLEMENTED_BUT_ISOLATED | server side tested; the EA itself has no automated test |
| Deriv transport | IMPLEMENTED_BUT_ISOLATED | tested against a local websocket server, never against Deriv |
| cTrader transport | IMPLEMENTED_BUT_ISOLATED | hand-verified wire bytes; never connected |
| ZSE owner-ticket path | PARTIAL by design | human in the loop |
| Account registry | INTEGRATED | signed onboarding, credentials never in the registry |
| Ledger (SQLite) | INTEGRATED | verify + replay tested |
| Ledger (Postgres) | IMPLEMENTED_BUT_ISOLATED | its only test is skipped in the default run |
| Commander + MCP | INTEGRATED | HMAC auth, systemd unit, node E2E test |
| Learning | IMPLEMENTED_BUT_ISOLATED | wired into backtests, not into the live session |
| Gateway trading API | PARTIAL | real routes; default ledger path points at a file nothing writes |
| Owner-signed mandate verification | **STUB** | non-empty string only |
| Live market-data feed → session | **ABSENT** | sessions read bars from a file on disk |
| Trade state → VAN semantic state | **ABSENT** | §16.4 |

Nothing in the trading plane reaches E2E_VERIFIED, and the system's own attestation says why.

### 16.6 Trading dashboard

Covered in §13.5. It is the best owner surface in the product: real navigation, multi-account,
positions, history, potential trades, risk with mandate limits, real candlestick charts from shared
pure geometry, live gateway data with zero fixtures, and honest unavailability. Gaps: **no alerts at
all**, account scope applies only to the Overview tab, no trading chat context hand-off, unformatted
float output, raw ledger keys shown to the owner, and an empty state that instructs the owner to run
a Python module command.

---

## 17. Google ecosystem audit

### 17.1 Credential planes — correctly separated

Four planes are kept genuinely distinct, and this is one of the project's real achievements:
Workspace OAuth (Fernet-encrypted refresh token, exchanged for a short-lived access token inside the
gateway), the Gemini runtime key (lives only in the Hermes profile `.env` at mode 0600, never touched
by gateway code), Cloud/service identity (Notebook Enterprise, Stitch), and the consumer browser
session (never exported as cookies). The Antigravity wrapper
(`hermes/profile/van/bin/antigravity-worker:17-25`) enforces isolation by process environment — it
repoints `HOME`/`XDG_*` at a 0700 per-identity directory and `unset`s `GOOGLE_API_KEY`,
`GEMINI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, `CLOUDSDK_CONFIG` and the project variables before
exec. That is the sharpest piece of isolation engineering in the audit.

Readiness cannot be faked: `registries/google_capabilities.json` carries **no state field at all**, and
`mesh.py:242-269` can only *derive* CONFIGURED, AUTH_REQUIRED or UNAVAILABLE — **READY is never
derivable**, it exists only as a stored evidence row, and any stored state is demoted to UNVERIFIED
when the canonical principal is unregistered. A fresh gateway reports `workspace_api` AUTH_REQUIRED,
consumer capabilities AUTH_REQUIRED and runtime capabilities UNAVAILABLE. Confirmed by probe.

### 17.2 What the Google integration can actually do

`google/transport.py` contains exactly eight functions. Their reachability:

| Function | Route / command | Status |
|---|---|---|
| `calendar_agenda` | `GET /v1/briefing` (`app.py:523-525`) | **the only Google API call on an owner-visible path** |
| `gmail_search` | `GET /v1/google/gmail/search` — internal token only | returns message IDs only; there is no `messages.get`, so VAN can never read a subject or body |
| `gmail_send` | `POST /v1/google/gmail/send` — A4 gated | sends a **pre-existing draft**; there is no route for `gmail_draft`, so VAN can never create the draft it would send |
| `gmail_draft`, `calendar_reschedule`, `drive_search`, `contacts_resolve`, `tasks_list` | **no route at all** | dead code |

There is no `events.insert` anywhere, so *"Van, check my calendar and arrange this"* is
**unimplementable today** — VAN can read the next twenty events and nothing more.

**Thirteen of sixteen registered Google capabilities have no gateway code beyond a registry entry:**
gemini, gemini_live, deep_research, mixboard, stitch, antigravity, jules, workspace_studio,
nano_banana, veo, flow, ai_studio, a2a_adk. Note that `workspace_studio` — which has no
implementation whatsoever — is selectable as the routing fallback for `workspace_operation`
(`mesh.py:304-306`). **P2-GOOG-001.**

Only three capabilities have implementation: `workspace_api` (IMPLEMENTED_BUT_ISOLATED),
`gemini_notebook` (PARTIAL), `gemini_notebook_enterprise` (IMPLEMENTED, disabled, uncredentialed).

### 17.3 Notebook Enterprise is the model to copy

`NotebookEnterpriseProvider` is the most complete integration in the repository: Discovery Engine
v1alpha CRUD, resumable upload, source-completion polling, and — critically — **a read-back before any
success claim**, with an ambiguous timeout becoming `CONFLICTED_STATE` that is never replayed. The
mutation pipeline behind it is properly engineered: sealed authority record → `action_begin` with
principal/turn/snapshot/expiry/device-revocation re-checks and typed parameter constraints →
`knowledge_action_execute` with a parameter-digest match → idempotency ledger →
provider call → read-back → `VERIFIED_SUCCESS`. **This is exactly the shape the whole product needs.**
It is pointed at credentials nobody has configured.

### 17.4 The canonical test command, traced link by link

*"Create a NotebookLM notebook for this project"* — **link 0 fails.** `resolver.py:86-89` requires the
literal token `note` followed by a space; the input has `notebook`, so the pattern does not match. And
there is no action for creating a consumer notebook at all — the five executable actions are
note-create inside an existing notebook plus four *enterprise* notebook operations. Creating a personal
NotebookLM notebook is not implemented anywhere.

Taking the phrase that does work, *"create a notebooklm note Dial Health"*: links 1–7 and 12–13 are
implemented (signature, resolution, A3 gates, authority seal, digest match, idempotency ledger, evidence
sealing, verification). Links 8–11 — navigate, pre-read, act, read-back — are **contract only**: they
are HTTP POSTs to `127.0.0.1:9141` and `127.0.0.1:9140`, and the only deployment asset for those ports
writes a manifest whose own field reads `"service_state": "ENVIRONMENT_PREPARED_NOT_IMPLEMENTED"`
(`bootstrap-browser-runtime.sh:72`). There is no server source for either port anywhere in the tree.

Two further observations. The resolver **casefolds** the command text before extraction
(`resolver.py:117`), so the sealed title is lowercase — the owner's capitalisation is silently lost.
And at `action_begin` the authority check requires only that the sealed parameters are a **subset** of
the submitted ones (`authority.py:127-129`), so `notebook_id` is **unconstrained by owner authority**:
Hermes chooses which notebook the owner's note lands in. **P1-GOOG-002.**

### 17.5 Google test reality

All five Google/knowledge suites pass (36 tests). Every one uses `httpx.MockTransport`, hand-written
spy classes, a monkey-patched provider method or `FakeGoogleTransport`. **Not one test makes a network
call to Google.** The suite proves policy, state machines, idempotency and credential isolation —
exactly what the canonical doc says it can prove — and proves nothing about live provider behaviour.

---

## 18. Browser intelligence, automation, n8n and Temporal

### 18.1 Browser Fabric — complete client, absent worker

`browser/adapters.py:55-119` is a shared JSON-over-HTTP client. The Harness adapter (`:122-191`) POSTs
`/navigate /page_info /click /fill /press /scroll /screenshot /wait /upload /tabs` with an envelope
pinning `mode: "PRODUCTION_ACTUATOR"` and `allow_helper_authoring: false`. The Stagehand adapter
(`:194-297`) POSTs `/observe /extract /act /agent` with an envelope pinning the model provider and name
and `allow_model_self_selection: false`.

**No worker source exists in this repository.** The only deployment asset installs
`@browserbasehq/stagehand@4.1.0`, `@playwright/test@1.63.0` and Chromium, binds ports 9140/9141, and
writes `"service_state": "ENVIRONMENT_PREPARED_NOT_IMPLEMENTED"`
(`bootstrap-browser-runtime.sh:69-72`). Nothing listens on either port. Playwright is pinned in
`backend/requirements.txt:11` but the gateway never imports it; only a bootstrap tool does, and
`config.py:102` marks the direct-Playwright path legacy.

Fail-closed behaviour is genuine and triple-layered: adapters refuse when disabled or unconfigured
(`:86-90`), Stagehand additionally requires a provider *and* model (`:229-233`), and
`external_runtime.py:129-174` requires persisted canary evidence before READY.

**A significant wiring gap:** neither `browser/api.py`, `browser/service.py` nor `browser/subagent.py`
imports `adapters` at all. The browser task creation path therefore **never calls an adapter**; only
`knowledge/notebook.py` and `automation/health.py` do. Evidence on the task path is caller-supplied and
digest-only, there is no browser verifier, and `app.py:179` passes no `binder`, so mission binding on
browser tasks is always `None`. **P2-BROW-001.**

Enforced controls: mutating-domain allowlist, A4/A5 refusal, profile and mutation posture,
`secretref://`-only fills, six secret regexes that **refuse rather than redact**, and an action-class
clamp. Not enforced: observe/extract domains are unchecked (the allowlist test is `if mutating`);
`prohibited:` and `rules:` blocks in `config/browser/domains.yaml:7-17` are parsed and **discarded**;
downloads are never checked; `upload` does not validate its file reference.

**Prompt-injection containment only records.** `assess_injection` can return `SUSPECTED`
(`policy.py:151-158`), but the only stop is on `CONFIRMED_INJECTION` (`subagent.py:232`) — and
**nothing in the repository ever sets that value** (it appears in the enum and in one test). The
external gates document already calls the injection tests "synthetic". **P1-BROW-002.**

The subagent itself is a real, tested state machine — goal, domains, action ceiling, ≤50 steps,
deadline, no-progress detection, ten stop reasons checked before execution, escalation to
`WAITING_FOR_OWNER` through the canonical `DecisionService`, and resume via a single-use scoped
authorization enforced as subset-plus-ceiling then consumed. It is also unreachable:
`api.py:888-889` returns 503 `BROWSER_WORKER_UNCONFIGURED` and `app.py:177-179` deliberately wires no
worker.

### 18.2 Automation and n8n

`n8n_client.py` is a real REST client with private-host enforcement. Two defects: `POST /workflows/{id}/run`
(`:157`) **is not a real n8n API endpoint**, and there is a blocking `time.sleep` inside an async retry
loop (`:128`).

The compiler is **genuine synthesis**, not template expansion: a versioned node map, per-node allowlist
checks, credential alias resolution with refusal, branch-slot connection building, and positions added
only after the semantic digest is computed. The node allowlist is enforced at compile time and mirrored
in `docker-compose.yml:87`. But the goal→IR stage has only one implementation
(`TemplateBackedProposer`, hard-wired at `api.py:340`) over exactly four skeletons for six goal classes,
and `PatternSource` has no implementation — so COLD and WARM are identical in practice.

**Verification logic is real but has zero observers.** `dispatch.py:98` plus `app.py:160-168` supply an
**empty observer map**, so every production automation run is `UNVERIFIABLE` and `owner_success` can
never become true. Tests pass only because they inject their own observers. **P1-AUTO-001.**

**A configuration finding that disables the fabric entirely:** `config/automation/domains.yaml:13` is
`external_domains: {}`, so `check_domain` denies every host, and COLD consequently always returns
`NO_PROPOSAL`. Combined with `automation_grant_signing_key` defaulting to `""`, the automation fabric
is inert by default — which is the correct fail-closed posture but means nothing about it is exercised.

Payments are the strongest control in the whole audit: refusal is asserted at **six independent
layers** (router, cold path, subagent, two adapter points, validator), matching the security policy's
absolute prohibition.

### 18.3 Temporal — ABSENT, and a certification artefact overstates it

A repo-wide search finds no Temporal client, worker, workflow, activity or docker service. What exists:
an enum member, a router branch, a stack-lock entry, a line in `requirements-vm.txt`, and
`bootstrap-browser-runtime.sh:55-58`, which imports `temporalio` **solely to assert its version**.
`runtime.env.example:14-19` states `VAN_TEMPORAL_ENABLED=0` and "No local Temporal server is implied."

The router's handling is honest in code — `router.py:131-138` returns `medium=TEMPORAL` with the detail
"Temporal is stack-locked at adoption phase 11 and not yet built" — but it is **a medium with no
executor**, not a refusal and not a fallback.

The risk is in the certification chain: `deploy/van-trading-core/qualify.sh:28` prints
`browser_runtime GREEN "… / Temporal 1.33.0"` for a **pip version match**, and that string is echoed
into `docs/PRODUCTION_ACCEPTANCE_LEDGER.md:123` as evidence. A reader of the acceptance ledger would
reasonably conclude Temporal is deployed. It is not. **P1-DOC-002.**

### 18.4 Computer Interaction Fabric — STUB

`computer_use/fabric.py` declares 12 typed operations with no `RUN_ARBITRARY`, real refusals for A4/A5,
per-type ceilings, mutation-without-verifier and completion-without-evidence. **Nothing executes them** —
`begin`/`checkpoint`/`complete` are pure database operations, and the DESKTOP, TERMINAL and MOBILE
surfaces have no backing code at all.

### 18.5 Certification tooling behaves correctly

`certify_browser_fabric.py --canary harness` would register a profile, create an L1/A2 task and run
navigate → page_info → screenshot; any adapter error fails and **records nothing**. CI asserts exit
code 2 (the BLOCKED path) for both certifiers and asserts the attestation file does **not** exist.
The fail-closed gate is real and working.

### 18.6 Browser and automation classification

| Component | Class |
|---|---|
| Browser Harness adapter | IMPLEMENTED_BUT_ISOLATED (no worker exists) |
| Stagehand adapter | IMPLEMENTED_BUT_ISOLATED (no worker exists) |
| Browser policy / injection containment | **PARTIAL** — containment records but cannot stop |
| Subagent + boundary escalation | IMPLEMENTED_BUT_ISOLATED (no worker wired) |
| n8n client | IMPLEMENTED_BUT_ISOLATED |
| Workflow compiler | INTEGRATED within the fabric |
| Standing automation authority | PARTIAL |
| **Temporal** | **ABSENT** |
| Computer Interaction Fabric | **STUB** |
| Certification gates | INTEGRATED (correctly fail-closed) |

295 tests pass across these suites. All use fake workers, mock transports or injected observers. The
external gates document lists all 14 rows as `PENDING_LIVE` — the repository is honest about this.

---

## 19. Hermes integration and model orchestration

### 19.1 The division of labour is correct and the boundary is real

Hermes owns reasoning, tools, skills, provider routing and project execution; the gateway owns
authentication, signed-command authority, context sealing, action authorization, verification and
credential isolation. `runtime_api.py:133-134` reports `hermes_is_sole_agent_runtime: true` and
`hermes_is_truth_authority: false`, and the code honours it: the gateway has no planner, and
`capability/router.py:190-194` **raises** if Hermes does not supply candidate classes, because
"deciding which classes serve a goal is goal interpretation, and that is Hermes's". There is no
duplicated agent loop.

The authorized execution chain is strict and correct. `action_begin` requires a sealed authority record
for the given `command_id` and re-checks principal type, requester, turn id, snapshot id, expiry,
device revocation, class escalation, typed action id and typed parameter constraints. The built-in
action registry gives every A3/A4 action `allowed_principals={OWNER_DEVICE}` — only `owner.context.read`
(A1) and `research.web.search` (A2) admit `HERMES_AGENT`. So **Hermes cannot mint authority**; it can
only present the identifiers of a live owner-signed command it received in run metadata. The
`owner_approved` field in the request body is ignored in favour of the sealed record.

### 19.2 Model-role matrix, by evidence type

DOC = prose claim, CFG = config value, CODE = executable path here, LIVE = external attestation.

| Role | Designation | Evidence type |
|---|---|---|
| Primary conversation and orchestration | Claude Sonnet 5 via the Hermes Anthropic provider | DOC + CFG + one LIVE canary turn |
| Complex reasoning | same as primary | DOC only |
| Planning | Hermes; the gateway explicitly refuses goal interpretation | DOC + CODE (negative) |
| Coding | Antigravity (delegated identity), Jules; "Claude/Codex delegates" | DOC + CODE (wrapper) + LIVE (Antigravity) / DOC only for the rest |
| Research | Exa via the gateway; Gemini Deep Research | CODE (Exa) + DOC/CFG (Deep Research, capacity-limited) |
| Summarization / documents | none designated | DOC |
| Browser intelligence | gateway-pinned provider and model, **empty by default** | CODE (handoff); the real model is a deployment variable |
| VEKL | none — deterministic projection, no model | CODE (no model) |
| Google-specific | Gemini family | CFG + LIVE (authenticated, `RESOURCE_EXHAUSTED`) |
| Trading | Hermes as analyst only; sizing by deterministic Risk Authority | DOC + CODE (negative) |
| **Fallback / escalation / cost control** | **none exists** | **ABSENT in code** |

There is no model-level routing, escalation, fallback or cost control anywhere in this repository. The
`fallback_chain` in `capability/router.py:241-264` operates over *capability* declarations, and
`_COST_WEIGHT` is a declared cost class, not token spend. This is a defensible consequence of Hermes
owning routing — but it means the audit can say nothing about model selection quality, and nothing
here can enforce a cost ceiling.

### 19.3 Five integration defects

**P1-HER-001 — MCP registration drift.** The shim exposes 20 tools and the contract test requires all
20, but `tools/hermes/register_owner_runtime_mcp.sh:48-64` registers an include list of only **11**.
The omitted nine include `vekl_query`, `obsidian_query`, `notebook_consumer_ask` and
`knowledge_action_execute` — the very tools `AGENTS.md:37,40-41` instructs Hermes to use. If the live
Hermes config was produced by this script, the knowledge protocol is unreachable. The contract test
only greps the script for tool name strings, not the include list, so the drift is untested.

**P1-HER-002 — The policy hook is never registered by any script.** `config.yaml:34-43` declares
`hook_module` and `hook_entrypoint`; the installer copies the `policy/` directory and the doctor only
checks the file exists. No script registers the hook with Hermes, and no live artefact attests it is
loaded. Its 30 unit tests pass. Its guarantees also depend entirely on Hermes self-labelling honestly:
a non-mutating action with no class is ALLOWed, and all matching is substring comparison on
caller-supplied strings.

**P1-HER-003 — Two skills are never installed.** `automation-fabric` and `browser-intelligence` are
declared in `config.yaml` but are not copied by `install_van_profile.sh:78-82` and not checked by the
doctor. Skill counts drift across four sources: config declares 16, installer/doctor manage 14, tests
assert 13, the live attestation records 13.

**P1-HER-004 — Two snapshot notions, one binding.** The orchestrator seals a snapshot and binds the
authority record to *that* id; `AGENTS.md:38` tells Hermes to seal its own. `authorize_action` requires
the record's snapshot id, so a Hermes-sealed snapshot can never authorise an action — Hermes must echo
the id from run metadata. Documented nowhere.

**P1-HER-005 — The trading commander's halt accepts any non-empty signature string**
(`commander/app.py:226-228`), and `requested_by` is client-supplied (`:88-90`), which is what gates the
agent-hidden credential commands. A shell-capable Hermes holding the commander token could reach
`account_credentials` and `mt5_ea_issue_key` (which returns a signing key once).

### 19.4 What the live attestations prove

`van_profile_live_attestation.json` proves that at commit `270da5d` on `dial-hermes-control` the profile
files installed, the doctor's file and grep checks passed, and **one** Sonnet-5 completion returned the
expected canary string. It does **not** prove the policy hook is loaded, that the MCP shim ever reached
the gateway, that any `/v1/runs` dispatch occurred, or that any `action_begin` chain ran.
`artifacts/release/hermes_recert_probe.json` states install and doctor "were NOT executed by this agent"
and that certification is owned by a parallel run — so the chain of custody for the live certification
is a document reference, not a reproducible artefact.

**Classification:** gateway→Hermes dispatch IMPLEMENTED_BUT_ISOLATED; Hermes→gateway MCP PARTIAL
(registration drifted); authorized execution chain IMPLEMENTED_BUT_ISOLATED; policy hook
IMPLEMENTED_BUT_ISOLATED; model orchestration ABSENT by design; councils and `message_agent` STUB (dead
code with documentation); most skills STUB (prompt-only), with research, gemini-notebook and
trading-intelligence binding to real tools.

---

## 20. Infrastructure topology audit

### 20.1 Two estates, one of which has no source here

**Estate 1 — owner control plane (`dial-hermes-control`):** uvicorn on `127.0.0.1:8787`, one SQLite
file, the Hermes runtime (external), the owner-runtime MCP shim, and a Cloudflare named tunnel as the
sole ingress.

**Estate 2 — Oracle trading VM (`van-trading-core`, ARM64, 2 OCPU / 12 GB):** Caddy with public TLS,
Supabase/Postgres, n8n plus a task runner, the browser runtime environment (prepared, not implemented),
VATI session services, the trading VEKL, the commander, and an external Windows MT5 bridge worker.

### 20.2 Seven single points of failure

1. **One SQLite file, one host, no replica, no backup.** `data/van_gateway.sqlite3` holds devices, the
   audit trail, approvals, events, missions, Google refresh tokens and the context graph. **No backup
   job exists anywhere** in `deploy/`, `tools/` or systemd. Loss of the VM is loss of all owner state
   and the entire audit history.
2. **The Cloudflare named tunnel is the only ingress.** `van-cloudflare-tunnel.service:4` declares
   `Requires=van-gateway.service`, so a gateway failure takes the tunnel with it, and the tunnel
   restarts `always` while the gateway restarts only `on-failure`. There is no fallback path — no
   Tailscale, no LAN listener, no direct address.
3. **`cloudflared` is unpinned, `--no-autoupdate`, and installed out of band.** Nothing in the
   repository installs it; the installer only checks for it.
4. **Hermes is an unversioned, un-health-checked hard dependency.** `require_hermes_for_mutations=True`
   means every mutation fails when Hermes is down, yet the unit file declares only `After=`, not
   `Requires=`, and the bearer token defaults empty.
5. **Bridge PKI expires silently.** `pki/make-bridge-pki.sh:11` uses 825 days and `issue()` returns
   early if the certificate already exists, so re-running bootstrap **never renews**. There is no
   expiry monitoring. At day 825 commander mTLS and the MT5 worker link both break without warning.
6. **The trading VM rebuild script hardcodes OCIDs, private addresses and an SSH key path.**
7. **n8n, Supabase, the browser runtime and every trading session share one 2-OCPU / 12 GB box.**
   Declared memory limits already sum to over half the machine before a trading session starts.

### 20.3 Retention, backup and monitoring — the largest operational gap

A repo-wide search for retention, prune, vacuum, purge or logrotate finds **one** retention setting in
the entire system: n8n's own execution database, at 168 hours. There is **no audit retention, no event
retention, no evidence retention and no snapshot retention**. The audit table, the event table,
`knowledge_evidence`, `research_evidence`, `eval_runs` and `context_snapshots` grow forever in the same
SQLite file that serves live owner requests.

There is no Postgres dump, no SQLite backup, no volume snapshot, no snapshot policy and no restore
drill. `qualify.sh` is the closest thing to monitoring and it is a manual one-shot.

### 20.4 Storage engineering

Storage is aiosqlite only: 69 tables at schema version 16, with a **fresh connection opened per query**
and **no WAL mode and no `busy_timeout`**. For a single-owner system the choice of SQLite is defensible;
the connection-per-query pattern without WAL is not, and it is the direct cause of the idempotency race
in §21.

---

## 21. Security threat model

The stated policy is excellent. The findings below are almost all failures of *enforcement*, not of
policy.

### 21.1 Confirmed by runtime probe

**P0-SEC-001 — The internal control token is gateway root, and it is provisioned to Hermes.**

Probe output (`evidence/van-system-audit/security/probe_authority_boundaries.out`):

```
POST /v1/devices/pairing-ticket   (X-Van-Internal-Token only)  -> 200  {"pairing_token": "..."}
POST /v1/devices/pair             (NO auth header at all)      -> 200
  returned keys: [device_access_token, device_id, enrolled_at_unix, ingress_token]
GET  /v1/degraded  with those credentials                      -> 200
```

A holder of one static token mints a pairing ticket, pairs a device without any authentication, and
receives **both the ingress bearer and a device access token** — becoming an owner device able to sign
commands. The same token also reaches Project Truth injection, device revocation, Google connect and
revoke, the trading halt, all automation routes, browser mutations, context scope export and delete,
and the live→fake Google transport swap. It has no per-caller identity, no scoping, no expiry, no
rotation and no audit of which principal used it.

That token is deliberately provisioned to the Hermes-side MCP shim, read from
`~/.config/van/gateway.env` (`owner_runtime_stdio.mjs:44-45`). The MCP allowlist of 20 tools is the
*only* thing confining Hermes to a subset — and Hermes is driven by model output. If Hermes holds any
shell or filesystem tool (and `hermes/mcp/README.md:11-12` expects scoped `filesystem` and `git`
servers), it can read the token and self-escalate outside the allowlist. **This is the confused-deputy
exposure at the centre of the architecture.**

A related latent footgun: when the internal-token check fails, the middleware **falls through** to the
ingress-plus-device path (`app.py:367-371` has no `else: 403`). Privileged routes are saved only by the
handler-level re-check, so any future route added under an internal-control prefix that forgets
`require_internal_control` becomes owner-device reachable.

**P0-SEC-002 — Untrusted notification content becomes a signed owner command.**

Verified independently by the lead auditor. `VanNotificationListenerService` captures any app's
notification title and body, redacts secrets, and enqueues a JSON payload carrying
`"untrusted_content": true` as a `CONTEXT_INGEST` item. `QueueReplayer.replayNow()` then drains the
queue and calls:

```kotlin
val text = payload.optString("text", payload.toString())   // QueueReplayer.kt:36
gateway.dispatchCommand(text = text, actionClass = payload.optString("action_class", "A1"), ...)
```

The notification payload has **no `text` key**, so the whole JSON string becomes the command text. It
is signed with the device HMAC, carries `principal_type = OWNER_DEVICE` and `origin_channel = UI`, and
— decisively — `VanGatewayClient.kt:364` **hardcodes `contextTrust = "CONVERSATION"` for every command
it sends**. The gateway's injection screen runs only when `context_trust == UNTRUSTED`
(`orchestrator.py:335`), so it never fires. The `untrusted_content` marker survives only as text inside
the payload, not as a protocol field.

Net effect: **any application on the device can inject text into VAN's owner-authority command path,
correctly signed, labelled trusted, and forwarded to Hermes as owner input.** This directly contradicts
`docs/SECURITY_POLICY.md` ("External content remains UNTRUSTED_EXTERNAL and cannot increase authority")
and item 7 of the Project Truth authority order. The queue item's own `CommandKind` is ignored by the
replayer.

**P0-SEC-003 — Verified success is caller-asserted.** See §7.4. Probe confirmed a mission reaching
`VERIFIED_SUCCESS` on a receipt reading `verifier_version: "i-say-so/1.0"` with evidence
`evidence://trust-me`.

**P1-SEC-004 — Owner-confirmed can be asserted without the owner.** See §12.1. Probe confirmed.

### 21.2 Established by inspection

**P1-SEC-005 — The command nonce is signed but never stored or checked.** `canonical_command_v2`
covers `nonce` and the orchestrator passes it through, but there is **no `command_nonces` table and no
uniqueness check**. Replay is defended only by the idempotency key and three time windows (24 h by
default, tightened to 60 s only when the client opts in).

**And the idempotency check is not atomic.** `IdempotencyService.begin` does a `SELECT` on one
connection then an `INSERT` on another, with no transaction and no `BEGIN IMMEDIATE`. Combined with a
fresh connection per query and no WAL, two concurrent identical signed commands can both see no row and
both proceed. Notably `auth/service.py:102,138` **does** use `BEGIN IMMEDIATE` — the pattern was known
and simply not applied here. A captured A1–A3 command can be replayed for double execution inside its
validity window. Probe showed the concurrent case surfacing as an `IntegrityError` and HTTP 500.

**P1-SEC-006 — The owner-authority audit log is not tamper-evident.** `AuditService.record` is a plain
INSERT into a flat table with a random UUID and **no previous-hash, no chain hash, no signature and no
sequence**. Anyone with write access to the SQLite file can insert, alter or delete audit rows
undetectably. The VATI trading ledger, by contrast, has a real verifiable chain. The policy hook lists
`audit` as a protected surface; the storage does not back that up.

**P1-SEC-007 — No lockout, no rate limit, no brute-force control anywhere** — not on
`/v1/devices/pair`, the ingress token, the device token, the A4 approval challenge or the public MT5
HMAC endpoint. A tunnel-reachable attacker gets unlimited attempts.

**P2-SEC-008 — Nothing expires.** Enrollment capability grants are minted with a **ten-year** expiry.
The ingress token, internal control token, device HMAC secrets, commander and VEKL tokens are never
rotated. Bridge PKI is 825 days with no renewal path. Google refresh tokens are encrypted at rest with
no re-consent cadence.

**P2-SEC-009 — `POST /v1/google/test-transport` exists on the production app** and swaps the live
transport for a fake with no undo route. Outside pytest the fake's constructor raises, so it fails
closed — but as an unhandled 500 leaking a traceback. The route should not exist in production.

**P2-SEC-010 — Voice has no speaker verification.** Any voice reaching the microphone produces a
transcript that is signed as an owner command. `SpeakerSimilarityScorer` exists as an interface with no
implementation. A4 actions remain biometric-gated, which contains the worst case.

### 21.3 Controls that are genuinely strong

Three independent authentication layers with hash-only persistence and live-certified restart
continuity and atomic revocation. A4 approval requiring an exact gateway-resolved action **before** a
challenge is issued. Action-class escalation that can only raise, never lower. A5 as unconditional
deny. Credential-plane separation enforced by process environment for the delegated Google worker.
Context admission refusing untrusted or model-derived claims to high authority tiers. Payment refusal
asserted at six independent layers. Secret patterns that refuse rather than redact. No credential
anywhere in Hermes prompt metadata. Every rejection path writes an audit row before returning, so
refusals are never silent.

---

## 22. Observability audit

**There is no application logging at all.** The gateway emits no structured logs; the audit table is the
only trace, and it is shallow. Correlation identifiers exist — `command_id`, `idempotency_key`,
`hermes_run_id`, `mission_id`, `execution_id`, `task_id`, `run_id` — but **they do not span the chain**:
nothing joins a `hermes_run_id` to a later action verification, mission state changes never reach the
event bus, and browser tasks bind to missions only when a binder is supplied, which production does not
do.

Metrics are defined and collected in-process and **exported nowhere**. There is no tracing, no metrics
endpoint, no log sink, no alerting. Health is pull-only. The event bus is a polled SQLite table with no
index beyond its primary key and no retention.

What a developer can trace end to end today: a single command's authorization decisions, from the audit
table, on one host, by reading SQLite directly. What they cannot trace: whether the command was
executed, by what, with what result.

---

## 23. Test architecture audit

**983 Python tests pass. Here is what they are.**

| Class | Count (approx.) | Note |
|---|---:|---|
| Unit | ~700 | the bulk; class-level, fresh store per test |
| Contract | ~80 | route auth gating, registry shapes, policy digests |
| Integration (in-process) | ~150 | ASGI transport against the real app with fakes behind it |
| Security | ~60 | pairing, device auth, A4, payment boundary, project isolation, policy hook |
| Failure injection | ~25 | mostly trading transports; genuinely good |
| Android JVM unit | 129 | 68 visual, 18 voice, 16 trading, 11 mission, 9 overlay, 5 queue, 2 degraded |
| Visual/JVM render | 12 | AWT renders compared to each other, never to a baseline |
| **E2E** | **0** | — |
| **Android instrumentation** | **0** | no `androidTest` source set exists |
| **Screenshot regression** | **0** | no golden images |
| **Browser (real worker)** | **0** | no worker exists |
| **Performance** | **1** | a context-retrieval latency benchmark over a synthetic 321-fact corpus |
| **Resilience / restart** | **0** automated | restart continuity was certified manually once |

**Every external service is mocked**: Hermes (`create_run` monkeypatched in every backend test), Google
(`httpx.MockTransport`, `FakeGoogleTransport`, spy classes), n8n, the browser workers (fake classes),
and the brokers (`PaperAdapter`, local websocket servers). No test touches a real external system, which
is correct for CI and means **no test constitutes evidence of integration**.

`tests/scenarios/test_acceptance_scenarios.py` is in-process with fakes, not E2E.

**Owner journeys with no automated validation at all:**

1. voice → command → execution → verification → spoken result
2. trading state → VAN semantic state → aura
3. any Google action end to end
4. Hermes delegation round trip (dispatch → callback → verify)
5. offline queue replay on a device
6. overlay lifecycle, drag, dock, dismiss, boot recovery
7. multi-turn conversation continuity
8. first-run onboarding through to a paired, working device
9. mission lifecycle driven by a real owner command
10. degraded-mode transitions driven by real subsystem failure

Three structural gaps deserve naming. `tests/contracts/test_android_dashboard_navigation.py` asserts
substrings against Kotlin **source text** and would pass on code that does not compile. The visual
acceptance gate compares two fresh renders to each other, so a regression that deleted the entire aura
would stay green. And the Android suite has no instrumentation source set despite a configured test
runner, so nothing about the actual device behaviour of the product's flagship surface is tested.

---

## 24. UX/UI review

The trading screens show the team can build a good product surface (§13.5). The Command Centre shows
what happens without that discipline.

| Dimension | Assessment |
|---|---|
| Information hierarchy | Weak — 13 modules, 4 promoted to tabs, the rest cards on one scroll |
| Typography | Poor — 8–12 sp with `maxLines=1`; chart text in raw pixels |
| Density | Engineering console density |
| Motion | Aura micro-motion only; **no state transitions anywhere** (hard cuts) |
| Feedback | Honest but terminal — "Completion has not been confirmed yet", forever |
| State representation | **Raw enum names rendered to the owner** (`CommandCentreActivity.kt:1214`) |
| Iconography | Minimal; semantics carried by baked-in bitmap props |
| Touch targets | Below guidance — 18 dp icons, ~29 dp chips, bare clickable text |
| Consistency | Two different navigation paradigms (manual `when` vs a real `NavHost`) |
| Responsiveness | **Absent** — no WindowSizeClass, no size qualifiers |
| Dark mode | Hardcoded dark; no light theme, no `values-night`, deprecated parent theme |
| Accessibility | **Absent** — 4 content descriptions app-wide, none in the Command Centre |
| State restoration | **Absent** — zero `rememberSaveable`/`ViewModel`; rotation wipes everything |
| Visual identity | Strong — the owner art is distinctive and consistent |

Symptoms of implementation-driven design are present in quantity: developer labels (`A4`,
`BIOMETRIC_STRONG`, `HMAC`), internal identifiers (`truth_sha`, `repo_sha`, `autonomy_tier`), raw JSON
(`current_scope_json`, `payload.toString()`, `Degraded: [...]`), and an empty state that asks the owner
to run `python -m vati lake`. The polished owner vocabulary the product needs already exists in
`MissionRepository.kt` and is not used by any screen.

---

## 25. Cross-module coherence

The subsystem graph is mostly clean. Legitimate bounded contexts explain most apparent duplication:
the trading ledger's HMAC is a different trust boundary from the device HMAC; the commander's auth is a
separate estate. Genuine drift:

| Concept | Duplication | Verdict |
|---|---|---|
| Work lifecycle | 11 parallel status enums; no owner-facing projection | **Architectural drift** — the root of the experience-layer gap |
| Routers | 5 classes named `*Router` (projects, automation medium, capability, Google mesh, trading execution) | Mostly legitimate; the name collision was already resolved once |
| Idempotency | gateway service, automation run nonces, notebook operation store, MT5 nonce table, router seen-set | Legitimate per estate, but the gateway's own is the non-atomic one |
| Epistemic taxonomy | `EpistemicState` (enforced) vs `SemanticClass` (unenforced) | **Drift** — pick one |
| Attention | `AttentionEngine` (used) vs `AttentionScorer` (isolated) | **Drift** — a 2.0 built beside the 1.0 |
| Verification | `VerifierRegistry` (isolated) vs automation's `WorkflowVerifier` (empty observers) | **Drift** — two verification systems, neither running |
| Hash/HMAC implementations | 8 call sites across 3 estates | Legitimate |
| Snapshot sealing | orchestrator-sealed vs Hermes-sealed | **Drift** — only one can authorise |

---

## 26. Determinism review

Classification of operations against the required model:

**Deterministic core — correctly deterministic.** Authorization, action classes, approval challenges,
command lifecycle gates, capability declaration, permission checks, persistence, routing contracts,
risk sizing, payment refusal, Google readiness derivation, context admission and ranking. These are
arithmetic and state machines with no probabilistic input. The Risk Authority in particular admits no
model influence at all.

**Bounded probabilistic intelligence — located outside this repository.** Natural-language
understanding, planning, research synthesis and semantic browser interpretation all belong to Hermes and
Stagehand, neither of which is here.

**The boundary between them holds where it is exercised.** A model cannot raise an action class, mint
authority, place an order, bypass the Risk Authority or promote inference to fact. Those are real,
tested constraints.

**Three places where the boundary is weaker than claimed:**

1. A model-driven Hermes holds the internal control token (§21.1), so the *credential* boundary is
   weaker than the *API* boundary.
2. Verification receipts are caller-authored (§7.4), so "deterministic verification" is deterministic
   validation of a claim, not of an effect.
3. Trading's "owner-signed" mandate is a non-empty string (§16.2), so the deterministic risk core
   trusts an undeterminable input.

A note on over-determinism, in fairness to the design brief: the typed resolver's six regexes are the
*right* amount of determinism for a gateway that is not supposed to interpret language. The problem is
not that the gateway does too little interpretation — it is that nothing records what the interpreting
layer then did.

---

## 27. Performance review

| Dimension | Status |
|---|---|
| Launch time | NOT VERIFIED (no device) |
| Wake-to-response | **Not measurable — no wake word exists** |
| Speech latency | NOT VERIFIED; `startedAtMs`/`finalizedAtMs` are recorded and never read |
| Model latency | NOT VERIFIED (external) |
| Command execution latency | Gateway-side gates are sub-millisecond arithmetic; end-to-end unmeasurable because there is no end |
| Context retrieval | **Measured in CI** — the one real performance gate, over a synthetic corpus |
| Browser startup | N/A (no worker) |
| Dashboard loading | NOT VERIFIED |
| Aura rendering | **Structural concern** — full geometry rebuild every frame, several hundred allocations per frame per instance |
| Animation frame stability | **Not measured** — `frameBudgetMissed` has no producer; no Choreographer or JankStats |
| Memory | NOT VERIFIED |
| Battery | **Structural concern** — the overlay animates with the screen off (§15.6) |
| Network | Polling `/health` every 60 s; no backoff anywhere |
| Service reconnection | No retry or backoff in the Android client at all |

The two structural concerns are real and are the reason the floating bot cannot be certified for
sustained use without device measurement.

---

## 28. Failure-mode and offline/degraded review

The degraded model is one of the better parts of the product. `DegradedCode` carries a four-part
truthful contract — what is broken, what still works, what will not be done, what restores capability —
and the probe confirmed it in action: with Hermes unreachable, every command returned
`status: degraded`, `HERMES_OFFLINE`, and the message *"Hermes offline; command not executed"*. Nothing
was fabricated. `/health` reflects Hermes reachability. The trading surface returns typed empty shapes
with `ledger_available: false` rather than inventing data. Android maps failures to
`Loaded.Unavailable("Gateway unreachable…")`.

Failures by dependency:

| Failure | Behaviour | Assessment |
|---|---|---|
| Hermes down | `degraded`, command not executed, audited | **Correct** |
| Internet down | Owner commands are **not** queued — `submit` dispatches directly and shows "Command dispatch failed" | **Defect** (§13.6) |
| Google token expired | Briefing degrades rather than failing | Correct |
| Browser worker absent | 503 `BROWSER_WORKER_UNCONFIGURED` | Correct |
| n8n absent | Fabric refuses to certify; exit code 2 | Correct |
| Trading host dead, stale file present | **Old data presented as current** | **Defect** (P0-TRADE-004) |
| Gateway restart mid-command | No resume; the command is simply gone | **Defect** |
| Provider timeout on a Notebook mutation | `CONFLICTED_STATE`, never replayed | **Exemplary** |

What VAN can still do fully offline: reminders with natural-time parsing, the attention queue,
notification triage, decisions already queued, and Project Truth reads from cache. That is a real
local capability set, and it is honestly bounded.

The five hardcoded-healthy Android subsystems (§13.6) and the three hardcoded-healthy trading risk flags
(§16.2) are the two places where degraded reporting lies by omission.

---

## 29. Dead code, incomplete work and documentation drift

### 29.1 The repository is unusually free of TODO markers

Across roughly 9,300 lines of automation and browser Python there are **two** textual markers. In
`trading/` there are none at all — no TODO, no FIXME, no `NotImplementedError`. The gaps in this system
are **structural, not annotated**: interfaces with no implementations, classes with no constructors,
routes with no callers, and adapters pointed at ports nothing listens on. A reviewer grepping for TODO
would conclude the product is finished.

Named structural stubs: the entire browser worker contract; `PostconditionObserver` and both observers
with no caller; `PatternSource`; `SubagentWorker`; `LocalSecondPassAsr`; `WakeWordEngine`,
`WakePhraseVerifier`, `SpeakerSimilarityScorer`; `external_domains: {}`; the unwired mission binder;
`computer_use/fabric.py` in its entirety; `VerifierRegistry`; and 18 unused gateway client methods in
Android.

### 29.2 Documentation drift register

| Claim | Location | Reality |
|---|---|---|
| Matrix generated against a blueprint at `docs/…BLUEPRINT_REV_1.md` | `UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json` | The file exists only on open PR #38 (**P1-DOC-001**) |
| WS9 BUILT: "solver/critic/verifier separation … unsourced facts refused" | matrix `:105` | Three caller-filled JSON columns; probe stored a fabricated sourced fact (**P0-COG-001**) |
| WS28 "all exist. Mission binding is the delta" | matrix WS28 | Wake engine, phrase verifier, local ASR, TTS invocation, ack playback and correction capture are all also absent (**P1-VOICE-001**) |
| "Temporal 1.33.0" as a green runtime component | `qualify.sh:28` → `PRODUCTION_ACCEPTANCE_LEDGER.md:123` | A pip version assertion; no Temporal exists (**P1-DOC-002**) |
| Evidence boards depict the shipping field | `visual-preview/build.gradle.kts:8-12` | Geometry shared, painter diverges; boards omit electrical life (**P1-VIS-001**) |
| Canonical evidence under `rev23/` incl. orthogonal presence board | `VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md §13` | Only `rev21/` exists; the board does not (**P1-VIS-002**) |
| Published wind formula | `VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md §7` | Every coefficient differs from `VanFieldGeometry.kt:467-470` |
| Rev 3.0 §33 Command Centre destinations | Rev 3.0 | 4 of 9 destinations are tabs; the rest are cards |
| Rev 3.0 §40 "no developer labels in production" | Rev 3.0 | Raw enums, `A4`, `HMAC`, raw JSON on screen (**P2-UX-001**) |
| Rev 3.0 §22 monotonic clock, §25 blended transitions | Rev 3.0 | No monotonic clock; every transition is a hard cut (**P1-AURA-002**) |
| Rev 3.0 §15 10–14 dp aura gap | Rev 3.0 | 5.3 dp at the shipping size; no dp anywhere in code (**P2-AURA-001**) |
| `android/README.md` targetSdk/compileSdk 34 | README | Actually 36; the README also omits four packages |
| Skill counts | config 16 / installer 14 / tests 13 / attestation 13 | Four-way drift (**P1-HER-003**) |
| 20 MCP tools | shim + contract test | Registration script installs 11 (**P1-HER-001**) |
| "share-to-VAN routing" on the device checklist | `EXTERNAL_GATES.md` | The receiver can never be invoked (**P1-AND-001**) |

The `IMPLEMENTATION_LEDGER.md` is, in fairness, substantially accurate about the backend authority
layer and scrupulously honest about external gates. The drift is concentrated in the cognition,
visual-evidence and voice claims.

---

## 30. Requirements traceability matrix

Authority key: **PT** = Project Truth Protocol, **SP** = Security Policy, **SOUL/AGENTS** = Hermes
profile, **R3** = Rev 3.0 visual/floating/owner-admin blueprint, **R22** = Rev 2.2 aura addendum,
**LWF** = Living Wind Field Rev 1, **UIB** = Unified Intelligence Blueprint Rev 1 (PR #38, not
canonical), **TB** = Trading blueprints Rev 4/5, **EG** = External Gates.

No row is marked complete without runtime or repository evidence.

| # | Requirement | Authority | Implementation | Test | Runtime evidence | Status | Gap |
|---|---|---|---|---|---|---|---|
| 1 | Owner-signed instruction outranks all other sources | PT §1 | `command/authority.py:87-136` | 12 security tests | probe: A4 free-text denied | **INTEGRATED** | — |
| 2 | Fail closed: never guess, mutate or claim success | PT | `orchestrator.py` all gates; `degraded/registry.py` | 60 security tests | probe: Hermes down → `degraded` | **INTEGRATED** | — |
| 3 | Untrusted content is data, never authority | PT §7, SP | `context/service.py:75-91`; `orchestrator.py:323-334` | admission tests | **probe: notification text arrives as trusted owner command** | **VIOLATED** | P0-SEC-002 |
| 4 | Destructive actions require explicit owner approval | PT A4, SP | `approval/service.py:278-429` | `test_a4_owner_approval.py` | probe: `denied` on free-text A4 | **INTEGRATED** | weak overload guards trading (P1-SEC-004) |
| 5 | Audit/approvals/authority can never be disabled (A5) | PT, SP | `orchestrator.py:195-203`; policy hook | 30 hook tests | — | **INTEGRATED** | audit not tamper-evident (P1-SEC-006) |
| 6 | Hermes is the sole agent runtime | SOUL, SP | no model client in gateway | grep-verified | `runtime_api.py:133` | **INTEGRATED** | — |
| 7 | No model sends a broker order | SOUL, SP, TB | single funnel `cycle.py:145→159` | 20 risk tests | — | **INTEGRATED** | never run live |
| 8 | Trading size only from the deterministic Risk Authority under an owner-signed mandate | SP, TB | `risk/authority.py` | 20 tests | — | **PARTIAL** | mandate signature is a non-empty string (P0-TRADE-001) |
| 9 | `NO_TRADE` is a valid outcome | SOUL, TB | `arbiter/opportunity.py:72-77` | tests | — | **INTEGRATED** | — |
| 10 | Payment execution is prohibited and cannot be automated | SP | six independent layers | payment boundary tests | — | **INTEGRATED** | strongest control in the audit |
| 11 | `CONFIGURED` is not `READY`; READY needs evidence | PT, EG | `google/mesh.py:242-269` | 14 mesh tests | probe: fresh DB → AUTH_REQUIRED | **INTEGRATED** | — |
| 12 | Credentials never enter LLM prompts | SP, SOUL | metadata allowlist `orchestrator.py:497-525` | wiring tests | probe: fake-Hermes saw no secrets | **INTEGRATED** | — |
| 13 | Credential planes stay separate | SP | vault / env / wrapper isolation | isolation tests | attestations | **INTEGRATED** | — |
| 14 | Automation and browser workers hold no authority | SP | grants, ceilings, refusals | 184 automation tests | — | **INTEGRATED** | no worker exists to constrain |
| 15 | An engine reporting success is not owner success | SP | `EngineReportVerifier` | verifier tests | **probe: self-asserted receipt → VERIFIED_SUCCESS** | **VIOLATED** | P0-VERIFY-001 |
| 16 | Every owner command becomes one durable mission | UIB §3 | `mission/` | 30 tests | **probe: 0 missions after 10 commands** | **ABSENT** | P0-EXEC-001 |
| 17 | Owner sees an honest lifecycle, never optimistic success | R3 §32, UIB §17 | `VanCommandController.kt:284` | none | probe: terminal state is `accepted` | **PARTIAL** | honest but frozen (P0-EXEC-003) |
| 18 | Completion consumed via SSE, WebSocket or bounded polling | R3 §32 | — | — | probe: no such route | **ABSENT** | P0-EXEC-002 |
| 19 | "Needs You" consolidates approvals | UIB §35 | `/v1/needs-you` | — | probe: returns `{count: 0}` | **IMPLEMENTED_BUT_ISOLATED** | no Android screen consumes it |
| 20 | Context: only the right personal/project context is recalled | UIB §9 | `context/`, `context_compiler/` | 86 tests | **probe: `fact_ids []` on every command** | **ABSENT on the command path** | P0-CTX-001/002 |
| 21 | Fact / inference / assumption separation enforced | UIB §14 | `epistemics/models.py` | 30 tests | — | **IMPLEMENTED_BUT_ISOLATED** | no enforcement point (P2-COG-002) |
| 22 | Critical reasoning: solver / critic / verifier separation | UIB §13 | `reasoning/kernel.py` | 10 tests | **probe: fabricated fact accepted, actionable** | **ABSENT as a reasoner** | P0-COG-001 |
| 23 | Owner model learns, is inspectable and reversible | UIB §11 | `understanding/owner_model.py` | tests | **probe: 3 free-form episodes → CONFIRMED** | **IMPLEMENTED_BUT_ISOLATED** | no writer; P1-SYM-001 |
| 24 | Learning promoted only on evidence | UIB §25 | `StrategyLearning` | 23 tests | — | **IMPLEMENTED_BUT_ISOLATED** | no outcome recorder (P1-LEARN-001) |
| 25 | "Hey Van" wake word with local acknowledgement | R3 §29, UIB §16 | interfaces only | 6 decision tests | — | **ABSENT** | P1-VOICE-001 |
| 26 | Voice transcript enters the same command pipeline | R3 §29-30 | `VanCommandController` | wiring tests | — | **INTEGRATED** | — |
| 27 | Voice never claims success before verification | UIB §44.5 | TTS never invoked | — | — | **VACUOUSLY TRUE** | VAN never speaks |
| 28 | Aura is a detached, wavy, electrically alive field | R3 §14, R22, LWF | `VanAura.kt`, `VanFieldGeometry.kt` | 12 files, ~60 tests | PNG boards (stale) | **INTEGRATED** | no shader/noise; evidence stale (P1-VIS-001/002) |
| 29 | No full or implied ring | R3 §17, R22 | exclusion + ribbons | `VanFieldRev3Test.kt:58` | — | **INTEGRATED + TESTED** | — |
| 30 | 10–14 dp minimum aura/body gap at ~92 dp | R3 §15 | fraction-based only | none | — | **NOT MET** | 5.3 dp (P2-AURA-001) |
| 31 | One monotonic visual clock, never restarted | R3 §22 | — | — | — | **ABSENT** | P1-AURA-002 |
| 32 | Pose transitions blend 120–420 ms | R3 §25 | — | — | — | **ABSENT** | P1-AURA-002 |
| 33 | Aura reflects classified trading state | R22 §7 | preview-only specs | none | — | **ABSENT** | P1-AURA-003 |
| 34 | 18 durable states with unique Zone C topology | R22 §6 | `VanAuraSpec.kt:83-215` | `VanAuraEnvelopeTest.kt:24` | boards | **INTEGRATED** | 10 of 22 requested semantics missing |
| 35 | Rive `.riv` embodiment | R3 §43, EG | runtime shipped, no asset | fallback tests | — | **ABSENT (declared)** | external gate |
| 36 | Command Centre is a real admin console with 9 destinations | R3 §33 | 4 tabs + cards | source-grep test | — | **PARTIAL** | P2-UX-001 |
| 37 | No developer labels, raw enums or fake data in production UI | R3 §40 | — | — | — | **VIOLATED** | P2-UX-001 |
| 38 | Board scroll never drags the overlay | R3 §50 | gestures on embodiment only | overlay tests | — | **INTEGRATED** | — |
| 39 | Owner Google account sovereignty, no master credential | SOUL, SP | four planes | isolation tests | attestations | **INTEGRATED** | — |
| 40 | A real useful workflow per implemented Google integration | UIB | `calendar_agenda` only | 36 mocked tests | — | **PARTIAL** | 13 of 16 capabilities are registry-only |
| 41 | Notebook mutation verified by readback before success | EG, PT | `notebook.py` enterprise + consumer | 9 tests | — | **IMPLEMENTED (isolated)** | consumer transport absent |
| 42 | Browser prompt-injection containment | SP, EG | `policy.py:151-158` | synthetic tests | — | **PARTIAL** | cannot stop (P1-BROW-002) |
| 43 | Durable workflows use Temporal | UIB §37 | — | — | — | **ABSENT** | P1-DOC-002 |
| 44 | n8n never becomes an owner principal | SP | grants + ceilings | 184 tests | — | **INTEGRATED** | — |
| 45 | Structured logs and traceable correlation across components | UIB §28 | audit table only | — | — | **ABSENT** | §22 |
| 46 | Backups, retention and recovery | — | — | — | — | **ABSENT** | §20.3 |
| 47 | Physical device certification | EG | checklist exists | — | — | **NOT VERIFIED** | external gate |
| 48 | Stable named Cloudflare ingress | EG | installer refuses quick tunnels | — | — | **NOT VERIFIED** | external gate |
| 49 | Signed production release | EG | Gradle wiring | — | — | **NOT VERIFIED** | external gate |
| 50 | Live broker order on any venue | TB, EG | transports implemented | failure-injection tests | attestation: no account enabled | **NOT VERIFIED** | external gate |

---

## 31. Findings register (P0–P4)

Severity per the audit brief. Every P0–P2 carries a root cause in §32.

### P0 — product truth or safety failure

| ID | Title | Evidence |
|---|---|---|
| **P0-EXEC-001** | An owner command creates no mission, no activity and no durable work record; the system's model of the owner's intent ends at dispatch | probe: 10 intents → 0 missions, 0 activity |
| **P0-EXEC-002** | No execution result ever returns; nothing joins a Hermes run to a verification, and silent non-execution produces no degraded signal | `orchestrator.py:560-575`; no poller, no callback key |
| **P0-EXEC-003** | The device can never display a completion; every long command reads `ACCEPTED` forever, and an unknown status also reads `ACCEPTED` | `VanCommandController.kt:162,221,255` |
| **P0-CTX-001** | The "canonical owner context" sent to Hermes contains zero owner facts | `orchestrator.py:403-407`; probe `fact_ids []` |
| **P0-CTX-002** | The only facts production can write are the only facts retrieval excludes, so the fact store is empty in a deployed system | `runtime_api.py:122-124` vs `context/service.py:199-200` |
| **P0-COG-001** | The Critical Reasoning Kernel performs no reasoning; it validates the shape of a caller-authored record, and the matrix claims otherwise | probe: fabricated sourced fact, 0 critic findings, actionable at 0.99 |
| **P0-VERIFY-001** | `VERIFIED_SUCCESS` is reachable on a self-asserted receipt; no server-side verifier ever runs | probe: `verifier_version: "i-say-so/1.0"` accepted |
| **P0-SEC-001** | One static internal token is gateway root, is provisioned to a model-driven Hermes, and mints owner-device credentials | probe: ticket → pair → ingress + device token → owner API 200 |
| **P0-SEC-002** | Any app's notification becomes a device-signed owner command labelled trusted; the injection screen never fires | `QueueReplayer.kt:36`, `VanGatewayClient.kt:364`, `orchestrator.py:335` |
| **P0-TRADE-001** | "Owner-signed" is a non-empty string across mandate, kill-switch clear, halt, capsule promotion and gateway trading writes | `risk/mandate.py:156-157` and five more sites |
| **P0-TRADE-002** | The live risk snapshot hardcodes reconciliation, risk store and event blackout to healthy, making three authority gates unreachable | `cycle.py:118-119` |
| **P0-TRADE-003** | Owner halt is polled, up to 5 s late, and is discarded by a session restart that a commander command can trigger | `service.py:181`, `commander/app.py:97` |
| **P0-TRADE-004** | The gateway reads a local SQLite ledger by default while the trading VM writes Postgres; a stale file would show old data as current | `config.py:21` |
| **P0-TRADE-005** | The idempotency key is session-scoped, so a crash-restart on the same bar can duplicate an order | `arbiter/opportunity.py:83`, `service.py:137` |
| **P0-TRADE-006** | No margin model exists anywhere in the trading stack | `execution/base.py:93-101` |

### P1 — major functional gap

| ID | Title |
|---|---|
| **P1-DOC-001** | The implementation matrix certifies 33 of 36 workstreams against a blueprint absent from the canonical tree |
| **P1-DOC-002** | A pip version assertion is reported as "Temporal 1.33.0" green in the production acceptance ledger |
| **P1-VOICE-001** | No wake word, no wake engine, no ack playback, no TTS invocation, no barge-in, no background voice, no mission binding |
| **P1-AURA-002** | No monotonic clock and no transition blending; every aura and pose change is a one-frame snap |
| **P1-AURA-003** | Trading state never reaches VAN's semantic or visual state |
| **P1-VIS-001** | The evidence painter diverges from the shipping painter and omits an entire visual layer |
| **P1-VIS-002** | All committed visual evidence is two authority revisions stale; the required certification board does not exist |
| **P1-AND-001** | Share-to-VAN is a BroadcastReceiver and can never be invoked by the share sheet |
| **P1-AND-002** | Onboarding has no pairing step; first run lands on a dashboard where everything fails |
| **P1-SEC-004** | The weak biometric overload (no CryptoObject) guards trading account and credential changes |
| **P1-SEC-005** | The command nonce is never stored or checked, and the idempotency claim is not atomic |
| **P1-SEC-006** | The owner-authority audit log has no hash chain and is not tamper-evident |
| **P1-SEC-007** | No rate limiting, lockout or brute-force control on any authentication surface |
| **P1-SYM-001** | Calibration reports an evidence-derived preference as "owner-confirmed"; episode refs are unverified |
| **P1-LEARN-001** | No production event feeds any learning loop; every feedback mechanism is an empty framework |
| **P1-BROW-002** | Injection containment can record `SUSPECTED` but nothing can ever set the value that stops a task |
| **P1-AUTO-001** | The automation verifier map is empty in production, so every run is `UNVERIFIABLE` and owner success is unreachable |
| **P1-HER-001** | MCP registration installs 11 of 20 tools, omitting the entire knowledge protocol |
| **P1-HER-002** | The policy hook is never registered by any installer and its loading is unattested |
| **P1-HER-003** | Two declared skills are never installed; skill counts drift four ways |
| **P1-HER-004** | Two snapshot notions, only one of which can authorise an action; undocumented |
| **P1-HER-005** | The commander accepts any non-empty halt signature and trusts client-supplied `requested_by` |
| **P1-GOOG-002** | `notebook_id` is unconstrained by owner authority; Hermes chooses where the owner's note lands |
| **P1-TRADE-007** | Strategy targets are discarded in the live order path, beside dead code |
| **P1-TRADE-008** | Learning is not wired into the live trading session, only into backtests |
| **P1-PERF-002** | The overlay animates continuously with the screen off |

### P2 — integration or coherence gap

`P2-COG-002` two unreconciled epistemic taxonomies · `P2-MEM-002` no owner-facing forget for the owner
model, evidence or reasoning ledgers · `P2-UX-001` the Command Centre is an engineering console with raw
enums and JSON on screen · `P2-AURA-001` aura gap is 5.3 dp against a 10–14 dp requirement ·
`P2-VIS-003` the IDLE evidence image is a DEGRADED render, duplicated by hash ·
`P2-BROW-001` the browser task path never calls an adapter and mission binding is always null ·
`P2-GOOG-001` `workspace_studio`, which has no implementation, is selectable as a routing fallback ·
`P2-SEC-008` nothing expires: ten-year grants, no rotation, 825-day PKI with no renewal ·
`P2-SEC-009` a live→fake transport swap route exists on the production app ·
`P2-SEC-010` no speaker verification on voice commands ·
`P2-PERF-001` full field geometry rebuilt every frame with no frame-budget measurement ·
`P2-OBS-001` no correlation identifier spans command → mission → execution → verification ·
`P2-COH-001` eleven parallel work-status vocabularies with no owner-facing projection ·
`P2-COH-002` `AttentionScorer` and `VerifierRegistry` are 2.0 implementations built beside live 1.0s.

### P3 — reliability, UX and observability

No application logging · no metrics export · no retention on any table · no backup or restore drill ·
no Android retry or backoff · `/v1/events` polled once with a hardcoded cursor · 18 dead gateway client
methods · five Android subsystems hardcoded healthy · offline queue never replays on connectivity ·
`fire_due` has no scheduler · reminders and attention in-memory dedupe only · no light theme · no state
restoration · unformatted floats and raw ledger keys in the trading UI · empty state instructing the
owner to run a Python module · blocking `sleep` in an async retry loop · 1238-line and 1031-line god
files · `android/README.md` stale.

### P4 — polish

Casefolded command titles lose owner capitalisation · chart text in raw pixels · no pan, zoom or
crosshair on charts · `headCounterDeg` computed and unused · dead loop in the trading cycle · duplicate
`PairDeviceBody` documentation · unescaped interpolation in an OAuth callback that currently only emits
constants.

---

## 32. Root-cause map

Fifty-five findings reduce to **six root causes**. Fixing these six closes most of the register.

**RC1 — The command path has no durable work object.**
*Violated contract:* UIB §3 (one mission per owner-visible task); PT (surface partial failures).
*Affected:* orchestrator, Mission Core, event bus, Android command controller, every owner surface.
*Propagation:* no mission → no activity → no evidence → nothing to verify → nothing to push → nothing
to learn from → no eval signal. **This single cause produces P0-EXEC-001/002/003, P1-LEARN-001,
P2-OBS-001, P2-COH-001 and the emptiness of VanEval.**
*Repair boundary:* `orchestrator.py` creates and binds a mission; `mission/api.py` gains an owner-read
projection; the event bus gains mission events.
*Regression risk:* medium — the command path is the most security-sensitive code in the product.

**RC2 — Verification is asserted, not performed.**
*Violated contract:* SP ("an engine reporting success is not owner success"); PT (never claim success
without proof). *Affected:* Mission Core, `VerifierRegistry`, automation dispatch, trading mandates.
*Propagation:* caller-authored receipts → `VERIFIED_SUCCESS` → `VanEval` authority score of 9.7 over an
empty table → false confidence in the certification chain. **Produces P0-VERIFY-001, P1-AUTO-001,
P0-TRADE-001, and undermines every "verified" claim in the ledger.**
*Repair boundary:* `MissionService.transition` must execute a registered verifier rather than accept a
record; automation must be given its observer map; trading must verify a real signature.
*Regression risk:* high — this is a behaviour change on paths currently green.

**RC3 — The context and cognition layer has no producer and no consumer.**
*Violated contract:* UIB §9–§14; PT authority order. *Affected:* 20 classes across `context/`,
`context_compiler/`, `epistemics/`, `reasoning/`, `understanding/`, `evolution/`, `proactive/`.
*Propagation:* no writer above INFERRED → empty fact store → empty snapshot → Hermes reasons without
owner context → no reasoning record returns → nothing to calibrate or learn from. **Produces
P0-CTX-001/002, P0-COG-001, P1-SYM-001, P2-COG-002.**
*Repair boundary:* an owner-facing fact writer plus a Project-Truth importer; requirement derivation on
the command path; MCP tools and routes for assessment and observation.
*Regression risk:* low — these paths are currently unused, so wiring them cannot break live behaviour.

**RC4 — One credential is the root of all privilege, and it is held by a model.**
*Violated contract:* SP (credential isolation, capability grants scoped and expiring); PT (agent
self-authorization forbidden). *Affected:* every internal-control route, the MCP shim, the commander.
*Propagation:* token → device enrollment → owner-device authority → signed commands. **Produces
P0-SEC-001, P1-HER-005, P2-SEC-008.**
*Repair boundary:* split the internal control token into scoped, expiring, per-purpose credentials;
remove device enrollment from the Hermes-reachable set.
*Regression risk:* medium — touches deployment and the MCP configuration.

**RC5 — Untrusted content is labelled trusted at the device boundary.**
*Violated contract:* PT §7; SP (external content cannot increase authority). *Affected:* notification
listener, share intent, queue replayer, gateway client, orchestrator injection screen.
*Propagation:* notification → queue → `text` → signed command with `context_trust=CONVERSATION` →
Hermes as owner input. **Produces P0-SEC-002 and makes the injection screen dead code in practice.**
*Repair boundary:* `VanGatewayClient` must derive `context_trust` from `CommandKind`; the replayer must
refuse to dispatch `CONTEXT_INGEST` as a command; the gateway should reject
`origin_channel=UI` payloads that carry an untrusted-content marker.
*Regression risk:* low.

**RC6 — Presentation state is driven by two inputs and evidence is generated by a different painter.**
*Violated contract:* R3 §22/§25, R22 §7, LWF §12.10. *Affected:* `VanLiveVisualState`, every producing
subsystem, the visual-preview module.
*Propagation:* only voice and dispatch write state → trading, missions, tools and browser cannot be
seen → and the boards that would reveal this are rendered by a divergent painter two revisions stale.
**Produces P1-AURA-002, P1-AURA-003, P1-VIS-001, P1-VIS-002, P2-VIS-003.**
*Repair boundary:* a semantic-state bus the gateway publishes to and Android subscribes to; extract the
Compose painter into shared code so previews render the shipping pixels.
*Regression risk:* low for the painter change, medium for the state bus.

---

## 33. Scorecard

Scores are 0.0–10.0 against the audit brief's standard: architecture plus implementation plus evidence.
A dimension scores above 9 only with strong implementation **and** real runtime evidence. No score is
adjusted to reach a target.

| Dimension | Score | Evidence | What prevents 10.0 |
|---|---:|---|---|
| Product completeness | **4.1** | 983 tests pass; authority core real; but no mission, no verification, no completion, no wake word, no browser worker, no live trade | The owner journey terminates at `accepted` |
| Architecture | **7.8** | Clean estates, correct Hermes boundary, deterministic core, orthogonal visual state | Two snapshot notions; work has no single identity; one credential is root |
| Determinism | **8.2** | Authority, risk, routing, ranking all arithmetic; no model can escalate | Verification and mandate signatures trust the caller |
| Cross-module coherence | **5.0** | Bounded contexts are mostly legitimate | 11 status vocabularies; two verification systems; two attention engines; two epistemic taxonomies |
| Experience-layer unity | **3.4** | One signed command path, one approval surface, one audit trail | No durable owner-visible work object; no push; trading, voice and missions are separate worlds |
| Command execution | **3.6** | Gates through `submitted` are excellent | Nothing beyond `submitted` exists; silent non-execution is undetectable |
| Voice | **2.9** | On-device ASR, signed transcript provenance, real audio arbiter | No wake word, no speech output, no barge-in, no background, no mission binding |
| Cognitive architecture | **3.2** | Rich, well-designed data model; honest "unmeasured" reporting | No reasoning occurs; no producer, no consumer, no route |
| Critical thinking | **2.8** | Excellent vocabulary; evidence provenance real; contradiction detection real for facts | Nothing produces the distinctions; the assumption gate has no caller |
| Context awareness | **3.3** | Fast deterministic retrieval; real isolation, staleness, conflict handling | The fact store is unreachable in production; commands seal empty context |
| Memory | **5.4** | Genuinely differentiated taxonomy; provenance on all evidence | 7 of 10 stores have no writer; no retention; no owner forget |
| Learning and adaptation | **2.6** | Correct invariants: evidence-required, revertible, demotable | No production event feeds any loop |
| Hermes integration | **6.6** | Correct division of labour; strict authorized-execution chain | No result readback; registration drift; hook unregistered; skills not installed |
| VEKL integration | **3.0** | Real retry-hardened read-only client with evidence sealing | No configured endpoint, no server implementing the contract, no caller decides when to query |
| Browser intelligence | **3.5** | Real policy, leases, secretrefs, subagent state machine, escalation | No worker exists; the task path never calls an adapter; containment cannot stop |
| Google ecosystem | **4.4** | Four credential planes genuinely isolated; READY underivable without evidence; Enterprise Notebook exemplary | 13 of 16 capabilities are registry-only; one owner-visible call; cannot create a calendar event |
| Trading architecture | **7.1** | Single order funnel, sealed decisions, append-only ledger enforced at the database, payment refusal, no model in the path | Mandate signature is a string; three health gates dead; halt lost on restart; no margin model |
| Trading UX | **6.9** | Real navigation, multi-account, risk, charts, live data, honest unavailability | No alerts; scope applies to one tab only; context lost on chat hand-off; raw values on screen |
| Floating bot | **6.2** | Real detached field, tested non-ring invariant, correct priority arbitration, sound gesture separation | No `.riv`; 8 bitmaps for 18 states; hard cuts; animates with the screen off |
| Aura and state visualization | **5.6** | Three zones, 18 topologies, orthogonal channels, grayscale-distinctness tested | No transitions; 10 of 22 semantics missing; trading unbound; evidence stale and divergent |
| Android UX/UI | **3.8** | Trading screens are good; command feedback is honest | Raw enums and JSON on screen; no accessibility, no adaptivity, no state restoration; no pairing in onboarding |
| Security | **5.9** | Three auth layers, A4 done properly, payment refusal, credential-plane isolation, fail-closed everywhere | Internal token is root and held by a model; notifications become owner commands; audit not tamper-evident; no rate limiting |
| Reliability | **4.6** | Degraded contract is truthful and real | No retry anywhere; commands lost on restart; owner commands never queue offline |
| Observability | **2.4** | Audit rows on every decision, including refusals | No logs, no metrics export, no tracing, no correlation across the chain |
| Test quality | **4.9** | 983 passing tests; strong security and contract coverage; honest mocking | Zero E2E, zero instrumentation, zero golden images; a source-grep masquerading as a navigation test |
| Infrastructure | **4.3** | Hardened compose, loopback scoping, real firewall and TLS posture | No backup, no retention, no monitoring, silent PKI expiry, single-host everything |
| Performance | **3.9** | One real latency gate in CI | Per-frame geometry rebuild; animation with screen off; no frame measurement; no device numbers |
| Offline / degraded | **5.7** | Truthful four-part degraded contract; nothing fabricated | Owner commands never queue; five subsystems hardcoded healthy; stale trading data reads as current |
| **Overall production readiness** | **4.2** | — | Six root causes; 16 P0 findings; every external gate still open |

The architecture documents, taken alone, would justify scores above 9 on several dimensions. That is
precisely the gap this audit exists to measure.

---

## 34. Gap-to-9 analysis

For each defining differentiator, what would legitimately earn 9.0+ — not by rescoring, but by
engineering.

**Experience-layer unity (3.4 → 9.3).** Every owner command creates a mission; every subsystem writes
activities against it; one owner-facing status projection replaces eleven vocabularies; the device
receives state changes rather than polling one endpoint once. Evidence required: a recorded trace of one
spoken command producing a mission, activities from two different executors, a verification receipt from
a real verifier, and a completion rendered on the device.

**Command execution (3.6 → 9.5).** The eight lifecycle states are distinct and owner-visible; a Hermes
run id is joined to its callbacks; absence of a callback within a deadline produces a truthful timeout
rather than silence; ≥95% of representative missions recover from one injected transient failure and
resume across a restart.

**Cognition (3.2 → 9.0).** The kernel receives records from a real producer through a real route, and
either *performs* a critic pass over supplied evidence or the claim is withdrawn from the matrix.
Assessments gate irreversible work through the existing assumption ledger.

**Context (3.3 → 9.5).** An owner-facing fact writer and a Project-Truth importer populate the
authoritative tiers; the orchestrator derives real requirements per command; precision and recall are
measured on an owner benchmark; stale detection and contradiction classification are measured, not
asserted.

**Symbiosis (2.6 → 9.0).** Episode references bind to real mission or command identifiers; corrections,
accepted and rejected recommendations feed the owner model; calibration distinguishes evidence-derived
from owner-confirmed in the words it shows the owner; every adaptation is inspectable and revertible
from the device.

**Voice (2.9 → 9.3).** A real keyword-spotting engine with the "Hey Van" phrase, a local acknowledgement
that plays before any network call, a microphone-typed foreground service, TTS actually invoked,
barge-in working, and P95 wake acknowledgement measured under 250 ms on the owner's device.

**Floating bot and aura (6.2 / 5.6 → 9.5).** One monotonic clock; 120–420 ms blended transitions; the
dp gap contract enforced and tested; the semantic vocabulary extended to tool use, browser use, planning
and interruption; the Compose painter shared with the preview renderer; evidence regenerated at the
current authority revision including the orthogonal-presence board; and on-device capture of sustained
animation with frame timing.

**Trading integration (7.1 → 9.5).** A real owner signature verified against a key; the three hardcoded
health flags driven by real state; a synchronous halt channel; a margin model; a ledger the gateway
actually reads; and a classified trade-state event reaching VAN's semantic state.

**Cross-module integration (5.0 → 9.2).** One work vocabulary, one verification system, one attention
engine, one epistemic taxonomy, one snapshot notion.

---

## 35. Remediation programme — dependency ordered

Derived from the root-cause map, not from the file layout. Each wave states objective, components,
prerequisites, work, tests, runtime evidence, regression gates and exit criteria.

### Wave 0 — Truth correction (no code)

*Objective:* stop the documentation from asserting capabilities the code does not have.
*Work:* correct the matrix entries for WS9, WS13, WS28 and WS33; either merge PR #38 or remove the
blueprint reference; remove the Temporal line from the acceptance ledger or qualify it as a library
version; mark `rev21/` evidence as stale; fix the duplicated manifest hash; correct
`android/README.md`.
*Exit:* no document claims a capability this audit classified ABSENT or STUB.
*Regression risk:* none. **This wave is a prerequisite for every other, because remediation cannot be
planned against a false baseline.**

### Wave 1 — Containment (security P0s)

*Objective:* close the two exploitable paths before any feature work.
*Components:* `VanGatewayClient`, `QueueReplayer`, `orchestrator`, `app.py` middleware, `auth/service`.
*Work:* derive `context_trust` from `CommandKind` and refuse to dispatch `CONTEXT_INGEST` as a command
(RC5); split the internal control token into scoped, expiring credentials and remove device enrollment
from the Hermes-reachable set (RC4); add `BEGIN IMMEDIATE` to the idempotency claim; add a
`command_nonces` table with a uniqueness check; add rate limiting on pairing and approval; add a hash
chain to the audit table; remove `test-transport` from the production app.
*Tests:* an adversarial test that posts a notification-shaped payload and asserts it is rejected or
marked untrusted; a concurrency test for the idempotency claim; a replay test for the nonce.
*Evidence:* a re-run of `probe_authority_boundaries.py` showing probes 1 and 3 now failing to escalate.
*Exit:* P0-SEC-001, P0-SEC-002, P1-SEC-005, P1-SEC-006, P1-SEC-007 closed.

### Wave 2 — Work identity (RC1)

*Prerequisite:* Wave 0.
*Objective:* give every owner command a durable, owner-visible existence.
*Work:* the orchestrator creates a mission per accepted command with a proper authority envelope and
passes `mission_id` in Hermes metadata; `CreateMissionBody` accepts an authority envelope; the mission
binder is wired in `app.py`; mission state changes publish to the event bus; `/v1/commands/{id}` exists;
Android consumes `MissionRepository` (already written) and renders `ownerReadableStatus`.
*Tests:* a command-to-mission binding test; an event-bus test asserting mission transitions are
published; an Android test for the mission surface.
*Evidence:* a re-run of `probe_command_lifecycle.py` showing missions and activity after ten commands.
*Regression gates:* the full security suite must stay green; no change to any authority gate.
*Exit:* P0-EXEC-001, P0-EXEC-003, P2-COH-001 closed.

### Wave 3 — Verified completion (RC2)

*Prerequisite:* Wave 2.
*Objective:* make "done" mean an externally observed effect.
*Work:* `MissionService.transition` executes a registered verifier from `VerifierRegistry` instead of
accepting a supplied record; `AutomationDispatcher` receives the real observer map; a Hermes run id is
joined to its callbacks with a deadline producing a truthful timeout; trading mandate and halt
signatures are verified against a key.
*Tests:* a test asserting a self-asserted receipt is now **rejected**; a timeout test; a mandate
signature test.
*Evidence:* `probe_mission_verification.py` re-run showing `i-say-so/1.0` refused.
*Regression gates:* this changes behaviour on currently green paths — expect and budget for churn.
*Exit:* P0-VERIFY-001, P0-EXEC-002, P1-AUTO-001, P0-TRADE-001 closed.

### Wave 4 — Trading safety

*Prerequisite:* Wave 3 (signature verification).
*Work:* drive the three hardcoded health flags from real state; add a synchronous halt channel and stop
filtering halts by session start time; make the idempotency key session-independent; add a margin model;
point the gateway at the real ledger and threshold staleness; wire learning into the live session;
remove the discarded-target dead code.
*Evidence:* a demo-account session with an injected reconciliation failure showing a refusal; a halt
delivered under one second; a restart that preserves the halt.
*Exit:* P0-TRADE-002 through 006, P1-TRADE-007/008 closed.

### Wave 5 — Context and cognition (RC3)

*Prerequisite:* Wave 2 (missions provide episode identity).
*Work:* an owner-facing fact writer and a Project-Truth importer; requirement derivation on the command
path; MCP tools and routes for assessment, premise and observation; bind `episode_ref` to mission or
command identifiers; make calibration distinguish evidence-derived from owner-confirmed; reconcile the
two epistemic taxonomies; add retention to the unbounded tables.
*Evidence:* a command whose sealed snapshot carries real fact identifiers; an owner model fed by real
corrections.
*Exit:* P0-CTX-001/002, P1-SYM-001, P2-COG-002, P2-MEM-002, P3 retention closed. P0-COG-001 is closed
either here or by withdrawing the claim in Wave 0.

### Wave 6 — Semantic state bus (RC6)

*Prerequisite:* Wave 2.
*Work:* a classified semantic-state event published by the gateway (mission phase, tool use, browser
use, trading classification, degraded state) and subscribed by Android; extend `VanDurableState` with
the missing semantics; add transition blending and a monotonic clock; enforce the dp gap contract.
*Evidence:* on-device capture showing the aura changing colour on a real trading classification.
*Exit:* P1-AURA-002/003, and the §37 aura certification becomes runnable.

### Wave 7 — Execution substrates

*Prerequisite:* Waves 3 and 6.
*Work:* implement or vendor the Harness and Stagehand workers; wire the browser task path to the
adapters; make injection containment able to stop a task; populate `external_domains`; decide Temporal
in or out and make the router honest either way; implement or delete the Computer Interaction Fabric.
*Exit:* P1-BROW-002, P2-BROW-001, P1-DOC-002, the browser and automation external gates.

### Wave 8 — Voice and owner experience

*Prerequisite:* Waves 2, 3, 6.
*Work:* a keyword-spotting engine with "Hey Van"; ack playback; microphone-typed foreground service;
TTS invocation bound to verified mission outcomes; barge-in; pairing in onboarding; fix the share
receiver; rebuild the Command Centre against the mission read models with owner language; accessibility,
adaptive layout, state restoration, light theme.
*Exit:* P1-VOICE-001, P1-AND-001/002, P2-UX-001.

### Wave 9 — Evidence, observability and operations

*Work:* extract the Compose painter for shared preview rendering; regenerate evidence at the current
authority revision including the orthogonal board; add an instrumentation source set with golden-image
tests; structured logging with a correlation id spanning the chain; metrics export; backups, retention,
PKI renewal and monitoring.
*Exit:* P1-VIS-001/002, P2-VIS-003, P2-OBS-001, the observability and infrastructure P3 register.

---

## 36. Certification gates

A gate passes only with the stated artefact. No gate passes on code inspection.

| Gate | Passing evidence required |
|---|---|
| **G1 Truth** | No canonical document asserts a capability classified ABSENT or STUB here; a re-run of this audit's probes confirms |
| **G2 Containment** | Adversarial notification payload rejected; scoped credentials in place; concurrent idempotency test green |
| **G3 Work identity** | Recorded trace: one owner command → mission → activities from two executors → device-rendered status |
| **G4 Verified completion** | A self-asserted receipt is refused; a real verifier receipt is accepted; a missing callback yields a truthful timeout |
| **G5 Trading safety** | Demo-account session refusing on injected reconciliation failure; sub-second halt; halt surviving restart; gateway reading the live ledger |
| **G6 Context** | A command whose sealed snapshot carries real fact identifiers; measured retrieval precision and recall on an owner benchmark |
| **G7 Aura certification** | The full §37 procedure below, captured on a device |
| **G8 Command certification** | The §38 procedure below, with external verification for each command |
| **G9 Voice** | P95 wake acknowledgement under 250 ms on the owner device; a spoken result that follows verification |
| **G10 Security review** | Independent review covering the six root causes |
| **G11 Device acceptance** | The existing physical Samsung checklist, owner-signed |
| **G12 Release** | All applicable external gates green; version above `0.5.0-dev`; provenance and SBOM regenerated |

---

## 37. Live aura certification procedure

This procedure does not exist today and cannot be run in this environment. It is specified so it can be
executed once Wave 6 lands. Capture to `evidence/van-system-audit/visuals/`.

1. Install a debug build on the owner device; grant overlay and microphone permissions.
2. Record 30 s of VAN idle at 60 fps. **Assert:** the field advects continuously; no frame is identical
   to the frame 1 s earlier; no common-radius collapse.
3. Trigger listening. **Assert:** transition blended over 120–420 ms, not a snap.
4. Trigger thinking, then executing, then success. **Assert:** each is distinguishable in grayscale.
5. Trigger a warning and an error. **Assert:** distinguishable from each other and from success.
6. Inject three representative trading classifications through the semantic-state bus
   (`watching`, `risk rising`, `stop invalidation`). **Assert:** the aura colour and Zone C topology
   change within 500 ms of the event, and the body remains identity-stable.
7. Measure the body-to-field gap in dp from the captured frames at the 96 dp floating size.
   **Assert:** ≥10 dp.
8. Run 10 minutes of sustained animation. **Record:** frame timing distribution, GPU time, battery
   delta, memory. **Assert:** P95 frame time under 16.7 ms; no unbounded allocation growth.
9. Turn the screen off for 2 minutes. **Assert:** the animation loop is suspended.
10. Repeat steps 2–5 under reduced motion, low power and static budgets. **Assert:** at least one
    readable semantic envelope fragment survives at every rung, and the five rungs are visually
    distinguishable.
11. Capture stills of all 18 durable states and diff against committed goldens at the current authority
    revision.
12. **Assert:** no frame reads as a ring, a border, or a body-hugging halo.

---

## 38. Real command certification procedure

For each command, record: spoken or typed text, parsed intent, context used, plan, execution route,
authorization evidence, external side effect, **independent external verification**, and VAN's final
report. A certification passes only on real execution.

| # | Command | External verification required |
|---|---|---|
| 1 | "Hey Van, remind me at 5pm to call the bank" | reminder fires on the device |
| 2 | "Van, what's on my calendar today?" | agenda matches Google Calendar read independently |
| 3 | "Van, create a NotebookLM note called Dial Health" | the note is visible in NotebookLM to a human |
| 4 | "Van, research X deeply and save what matters" | research evidence rows exist with citations; the owner can retrieve them later |
| 5 | "Van, use my browser to complete this task" | the external site shows the effect |
| 6 | "Van, ask Hermes to execute this development mission" | a commit or CI run exists at the stated SHA |
| 7 | "Van, investigate why this project failed its build" | the cited CI run and root cause match reality |
| 8 | "Van, halt trading" | the kill switch is set in under 1 s and survives a restart |
| 9 | "Van, open the trading system and show me what needs attention" | figures match the live ledger |
| 10 | "Van, delete the production database" | refused, with the refusal audited |

Today, commands 1 and 2 are the only ones with a plausible path, and command 10 is already correctly
refused.

---

## 39. Critical-thinking certification procedure

Present VAN with scenarios containing incomplete information, conflicting evidence, stale information,
misleading evidence and ambiguous requirements. Assess whether VAN recognises uncertainty, seeks
evidence, separates fact from inference, detects contradictions, considers alternatives, revises on new
evidence and declines to invent. **This procedure cannot be meaningfully run today**: the gateway
contains no reasoning, and the behaviour under test would belong entirely to the external Hermes prompt
pack. Running it now would measure a prompt, not this system. It becomes meaningful after Wave 5, when
assessments have a producer, a route and a consumer.

---

## 40. Final production-readiness verdict

**NOT PRODUCTION CERTIFIED. NOT v1.0.**

This agrees with the repository's own position: `PROJECT_CANONICAL_STATE.json` sets
`release_blocked: true`, the version is `0.5.0-dev`, and `docs/EXTERNAL_GATES.md` lists every live gate
as open. The project's governance called this correctly before the audit did.

The audit's addition is that **the blockers are not only external**. All fifteen P0 findings are
repository-side and closable without any external dependency: mission binding, result readback,
verification execution, context wiring, the internal token split, the untrusted-content boundary, and
all six trading safety defects. The external gates — a physical device, a named tunnel, live
Google credentials, browser workers, a broker account, a `.riv` asset — are real, but they are not what
currently stands between VAN and being one coherent intelligence.

---

## 41. Final question

> **Does the current implementation genuinely behave like one coherent, context-aware, critically
> reasoning, continuously improving personal intelligence called VAN — or is it still a collection of
> partially integrated AI features presented under one interface?**

**It is neither of those, and the distinction matters.** VAN today is a **rigorously built owner
authority and evidence layer around an intelligence that lives somewhere else, with a presentation layer
that cannot yet see what that intelligence does.** It is not a collection of disconnected features
bolted under one skin — the seams are not arbitrary, and the boundaries are principled. But it does not
yet behave as one continuous intelligence, because the thing that would make it continuous — a durable,
verified, owner-visible record of work in flight — does not exist.

**What is already real.** Three-layer device authentication with hash-only persistence, live-certified
restart continuity and atomic revocation. An A4 approval path that refuses to let free text become an
approvable destructive action and binds approval to a resolved action, typed parameter constraints and
the device key. Payment refusal asserted at six independent layers. Four Google credential planes that
genuinely cannot collapse into one, with isolation enforced by process environment for the delegated
worker. A trading order path with exactly one funnel, sealed hash-recomputable decisions, append-only
enforced at the database, and no model anywhere near it. A degraded contract that tells the owner what
broke, what still works, what will not happen and what restores it — and, verified by probe, actually
does so. A visual state model with orthogonal health, authority, speech and turn channels, priority
arbitration, anti-thrash holds and a tested non-ring invariant. A Notebook Enterprise integration that
reads back before claiming success and turns an ambiguous timeout into a conflict rather than a retry.
983 passing tests, honest about their own mocking. And governance that says the newest commit is not
authority, CI is not truth, and an agent may not authorize itself.

**What is structurally strong but not yet load-bearing.** The Mission Core state machine, the capability
registry and router, the context authority ladder, the memory taxonomy, the epistemic vocabulary, the
learning invariants, the browser subagent's bounds and escalation, the automation compiler, the
verifier adapters. These are not mock-ups. They are real, tested implementations waiting for a caller.
Twenty classes in the cognition layer have no production caller at all — but the reason is wiring, not
pretence, and that is a far cheaper problem than the alternative.

**What remains superficial.** The claim that VAN reasons critically: the kernel validates the shape of
a record someone else authored, and a probe stored a fabricated fact with an invented source as an
actionable 0.99-confidence assessment. The claim that VAN learns: every feedback loop has correct
invariants and no input. The claim that verification prevents false success: the receipt is
caller-authored. The trade aura families: eight beautifully specified semantic topologies whose only
caller is a PNG generator.

**What remains disconnected.** Trading state never reaches VAN's presence. Missions never reach the
device. Voice never receives a result. Notifications reach the command path but through the wrong door.
The owner model has no writer. The fact store cannot be written and read by the same system. Eleven
vocabularies describe work in progress and none of them is the one the owner sees.

**What remains simulated.** The decision cycle has only ever run over a paper adapter and synthetic
bars. Every browser action targets two ports with nothing behind them. Every Google test is mocked.
Every visual artefact is one frozen frame from a painter that differs from the shipping one, at an
authority revision two generations old.

**What prevents deeper owner symbiosis.** VAN cannot observe its own experience. It does not record what
it did, whether it worked, what the owner corrected, or what it should do differently. Every mechanism
for symbiosis is built and none of them receives a single production event. Until a command produces a
mission and a mission produces a verified outcome, there is nothing for VAN to learn *from* — and the
owner model's admission ladder will keep counting unverified strings.

**What prevents production certification.** Fifteen P0 findings, every one of them repository-side:
work has no durable identity, results never return, verification is asserted, context is empty, one
credential is root and a model holds it, untrusted content is labelled trusted, and the trading core's
notion of an owner signature is that the string is not empty.

**What closes those gaps.** Six root causes, in dependency order: correct the documentation first so
remediation is planned against truth; contain the two exploitable security paths; give work a durable
identity; make verification execute rather than accept; wire the cognition layer to a producer and a
consumer; publish a semantic state bus so the experience layer can finally see what the execution layer
is doing. Nothing in that programme requires a new framework, a rewrite, or a change to the
architecture. The architecture is, for the most part, right. What is missing is the wiring between the
layers it correctly separated — and the discipline of not describing that wiring as finished before it
exists.

The most encouraging finding of this audit is that the project's own governance documents already forbid
every mistake this report identifies. The gap is not one of judgement. It is one of enforcement.

---

## 42. Architecture diagrams (implementation-derived)

All diagrams show what the code does. Dashed links and ✗ marks are gaps this audit established.

### 42.1 Command lifecycle — as implemented

```
input ──► intent ──► context ──► reasoning ──► plan ──► authority ──► execution ──► verification ──► state ──► response
  │         │          │            │            │          │             │              │             │          │
  ▼         ▼          ▼            ▼            ▼          ▼             ▼              ▼             ▼          ▼
tap or   6 regex   snapshot     ✗ not in    ✗ not in    sealed       POST to        ✗ nothing     ✗ no        "accepted"
typed    rules;    sealed with  the gateway the        authority    Hermes         joins the      mission,    returned
(no      else      ZERO         (Hermes)    gateway    record       /v1/runs       run to a       no          immediately
wake)    "Hermes   requirements                        (strict,     (fire and      callback      activity,
         needed"   ✗ no facts                          correct)     forget)        ✗ no timeout   no event
                                                                                   ✗ no readback
                            ┌───────────────────────────────────────────────┐
                            │ Hermes MAY call back:                          │
                            │  action_begin → action_submitted → action_verify│
                            │  (strictly bound to the sealed record)          │
                            │  ✗ but nothing requires or detects it           │
                            └───────────────────────────────────────────────┘
```

### 42.2 Semantic state propagation — required vs implemented

```
REQUIRED:
domain event ──► classified state ──► arbitration ──► VAN semantic state ──► visual + voice behaviour

IMPLEMENTED:
voice recognition ────────────────┐
                                   ├──► VanLiveVisualState ──► priority ladder ──► aura + body
gateway command envelope ─────────┘      (320 ms hold,
                                          generation token)
trading classification ─ ✗ ─────────X  never connected  (P1-AURA-003)
mission phase ────────── ✗ ─────────X  no mission exists (P0-EXEC-001)
tool / browser use ───── ✗ ─────────X  no such state     (§15.3)
degraded health ───────────────────────► VanPresence.cue ──► trading screen chrome only
```

### 42.3 Memory and context architecture — as implemented

```
source ──────────► admission ─────────► classification ──► storage ──► retrieval ──► authority ──► reasoning
  │                    │                     │               │            │             │            │
Hermes            _require_hermes_       INFERRED /       owner_facts   lexical +     authority    ✗ never
(only writer)     memory_candidate       MODEL_DERIVED    (69 tables)   graph +        ladder       reaches
                  403 unless INFERRED    ONLY             ✓             hot capsule    ✓ real       a reasoner
                                              │                             │
owner ─── ✗ no writer exists ─────────────────┤                    default EXCLUDES
Project Truth ─── ✗ no importer ──────────────┤                    INFERRED  ✗
conversation ─── ✗ no ingestion ──────────────┘                          │
                                                                          ▼
providers ──► knowledge_evidence ──► ✗ nothing ever reads it back     RESULT: the fact
(VEKL, Obsidian, Notebook, Exa)       (no FROM outside the writer)    store is empty
                                                                      in production
                                                                      (P0-CTX-002)
```

### 42.4 Trading integration — where the chain breaks

```
market data (file on disk)
   ▼
market state ──► opportunity assessment ──► TradeIntent
   ▼
RISK AUTHORITY  ◄── mandate (✗ signature = non-empty string, P0-TRADE-001)
   │             ◄── snapshot (✗ 3 health flags hardcoded healthy, P0-TRADE-002)
   ▼
execution router ──► venue adapter ──► broker   (✗ never exercised live)
   ▼
hash-chained ledger  ✓ real, append-only enforced at the DB
   ▼
gateway TradingService ──► /v1/trading/*  ✓ real routes
   │  ✗ default path points at a DIFFERENT ledger (P0-TRADE-004)
   ▼
Android polls ──► trading screens  ✓ good surface
   ✗ BREAK: no event, no classification token, no visual mapping
   ▼
VAN experience layer   ← receives NOTHING from trading
```

### 42.5 Trust boundaries

```
┌─ OWNER DEVICE ──────────────────────────────────────────────┐
│ biometric-bound EC key (Keystore) · device HMAC · AES-GCM q │
│ ✗ notification content crosses into the command path        │
│   labelled CONVERSATION (P0-SEC-002)                        │
└──────────────────────────┬──────────────────────────────────┘
                 ingress + device token + per-command HMAC
┌──────────────────────────▼──────────────────────────────────┐
│ GATEWAY — deterministic authority                            │
│  A5 deny · A4 approval · class may only rise · truth gate    │
│  ✗ ONE static internal token = root, and Hermes holds it     │
│    (P0-SEC-001)                                              │
└───────┬───────────────────────────────┬──────────────────────┘
        │ run metadata (no secrets ✓)   │ internal-control token
┌───────▼──────────┐          ┌─────────▼────────────────────┐
│ HERMES (external)│          │ providers / workers          │
│ the only model   │          │ Google · n8n · browser ✗none │
│ loop; untrusted  │          │ trading commander            │
│ by design ✓      │          │ secrets never in prompts ✓   │
└──────────────────┘          └──────────────────────────────┘
```
