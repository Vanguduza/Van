# VAN Unified Personal Intelligence Improvement Blueprint — Rev 1

## Cognitive Symbiosis Amendment — Rev 1.1

**Product:** VAN — Owner Personal Intelligence / Hermes Bot  
**Document type:** Canonical improvement and implementation blueprint  
**Status:** PROPOSED IMPLEMENTATION AUTHORITY; does not supersede locked security/authority canon until corresponding code and accepted decisions land  
**Repository baseline:** `main` @ `f8c3fcc9b4d346c7b59ed128cfdbe63bceab3dc0`  
**Parent authority:** `docs/SECURITY_POLICY.md`, `docs/PROJECT_TRUTH_PROTOCOL.md`, `hermes/profile/van/SOUL.md`, Rev 3.1 Owner-Agent Runtime implementation, Browser/Automation adoption decisions, VATI authority boundaries  
**Primary design axiom:** **VAN is unified at the experience layer and modular at the execution layer.**

**Cognitive symbiosis axiom:** **VAN should become an increasingly accurate digital extension of the owner without becoming an echo of the owner. Deep alignment must strengthen independent factual reasoning, not suppress it.**

---

## 0. Executive target

VAN is not to become a larger collection of modules presented to the owner. VAN is to become a single coherent personal intelligence that:

1. understands the owner’s goal;
2. recalls only the right personal/project context;
3. converts the goal into one durable mission;
4. silently selects the minimum sufficient execution capability;
5. executes through bounded specialist runtimes;
6. pauses only when owner authority is genuinely required;
7. verifies outcomes before claiming success;
8. records evidence and lessons;
9. notices important changes proactively;
10. presents all of this through one simple owner experience.

The target experience is:

> **Van understands me → remembers appropriately → notices what matters → forms a mission → chooses the right execution substrate → acts within authority → asks me only when necessary → verifies the result → learns from the result → presents the whole process through one coherent personal-assistant experience.**

The internal architecture may remain sophisticated. The owner experience must become progressively simpler as internal capability increases.

---

# 1. Required quality target

The previous engineering assessment produced these approximate scores:

| Dimension | Previous | Rev 1 target |
|---|---:|---:|
| Architectural direction | 9.0 | **9.6+** |
| Authority/security model | 8.5 | **9.6+** |
| Agentic execution architecture | 8.5 | **9.5+** |
| Knowledge/memory architecture | 8.5 | **9.5+** |
| Voice architecture | 8.0 | **9.3+** |
| Owner UX coherence | 7.5 | **9.3+** |
| Proactive-assistant maturity | 7.0 | **9.2+** |
| Evaluation/self-improvement | 7.0 | **9.3+** |

These scores are not to be claimed from subjective inspection. Every target score must be backed by measurable acceptance gates defined in this document.

A dimension may be reported above 9 only when:
- all P0 gates for that dimension are green;
- no known critical authority or truth defect remains;
- representative E2E scenarios pass with evidence;
- live runtime canaries exist where external systems are involved;
- failure and recovery behavior are demonstrated, not inferred.

---

# 2. Core product doctrine

## 2.1 One identity, not many tools

The owner interacts with **Van**, never with “the Browser Harness,” “n8n,” “VEKL,” “NotebookLM,” “Temporal,” “VATI,” or “a worker model” as separate assistants.

Those names may appear on technical/admin pages for observability, but they are implementation details.

Owner language:
- “Van, research this.”
- “Van, fix the issue.”
- “Van, watch this.”
- “Van, remind me if it changes.”
- “Van, check my project.”
- “Van, investigate why that trade was rejected.”

Internal execution may route through one or more specialist systems. That routing must normally remain invisible.

## 2.2 One assistant loop

Hermes profile `van` remains the **sole agent runtime**.

No subsystem may become an independent owner-facing agent loop.

Allowed:
- specialist reasoner;
- bounded planner;
- browser semantic worker;
- code worker;
- Google specialist;
- research worker;
- VATI analysis module;
- deterministic workflow.

Forbidden:
- a specialist independently redefining owner intent;
- a specialist expanding its own authority;
- a provider becoming a second persistent Van;
- Android hosting an autonomous reasoning loop;
- n8n becoming a planner;
- Stagehand becoming authority;
- VATI being bypassed for trading execution.

## 2.3 Unified experience, modular execution

The system SHALL have a strict two-sided contract.

### Experience side

The owner sees:
- one identity;
- one chat/voice relationship;
- one mission list;
- one “needs you” decision surface;
- one notification/attention system;
- one memory relationship;
- one activity/evidence timeline;
- one settings/permissions surface;
- one dashboard hierarchy.

### Execution side

VAN may delegate to:
- Hermes planning/reasoning;
- Gateway deterministic services;
- VEKL / GraphRAG / owner knowledge;
- Browser Harness;
- Stagehand;
- Temporal;
- n8n;
- Google Workspace/Notebook/AI services;
- DDE/development workers;
- remote shell/computer-use capabilities;
- VATI;
- future specialist systems.

Every execution substrate must expose a bounded capability contract and return structured evidence to the mission.

---

# 3. Canonical mission model

The most important improvement is a **single durable Mission abstraction**.

Today VAN has commands, browser tasks, automations, decisions, trading operations and provider-specific executions. They must become children of one owner-visible unit of work.

## 3.1 Mission definition

A Mission is the durable representation of an owner goal or VAN-proposed goal.

Minimum schema:

```text
Mission
  mission_id
  owner_principal_id
  project_id?
  origin
    voice | chat | notification_action | automation | system_observation
  title
  goal
  success_contract
  constraints[]
  authority_envelope
  sensitivity
  context_snapshot_id
  state
  priority
  created_at
  deadline?
  attention_policy
  plan_revision
  current_phase
  parent_mission_id?
  child_activity_ids[]
  evidence_refs[]
  final_outcome
  verification_state
  learning_record_id?
```

## 3.2 Mission state machine

Required state machine:

```text
CAPTURED
  -> UNDERSTOOD
  -> PLANNED
  -> AUTHORIZED
  -> RUNNING
  -> WAITING_EXTERNAL
  -> WAITING_FOR_OWNER
  -> RESUME_AUTHORIZED
  -> RUNNING
  -> VERIFYING
  -> VERIFIED_SUCCESS

Terminal alternatives:
  FAILED
  CANCELLED
  EXPIRED
  BLOCKED_POLICY
  BLOCKED_UNSAFE
  UNVERIFIABLE
  PARTIAL_SUCCESS
```

Rules:
- `WAITING_FOR_OWNER` is non-terminal.
- plan changes increment `plan_revision`.
- completed work and evidence survive replanning.
- owner-approved scope extension creates new authority for the delta; original signed intent is immutable.
- child activity failure does not automatically fail the mission if another permitted strategy exists.
- mission success is impossible without the success contract being verified or explicitly marked unverified.

## 3.3 Success contract

Every non-trivial mission SHALL have explicit postconditions.

Example:

```yaml
goal: create NotebookLM notebook from project research
success_contract:
  - notebook_exists: true
  - exact_title_matches: true
  - required_sources_count_gte: 5
  - owner_account_context: verified
  - provider_readback: verified
```

“Submitted” is not success.
“Clicked” is not success.
“Worker says done” is not success.

---

# 4. Mission service architecture

Introduce a deterministic `MissionService` in the Gateway.

Responsibilities:
- create mission from signed owner command or governed proactive proposal;
- bind immutable owner/context authority;
- manage mission state;
- attach execution activities;
- maintain plan revisions;
- aggregate evidence;
- calculate owner attention requirements;
- expose owner-safe read models;
- enforce success verification before completion.

Hermes responsibilities:
- interpret goal;
- propose plan;
- select capabilities;
- replan after failures;
- explain mission state.

Hermes must not:
- mutate mission authority directly;
- mark verified success without verifier evidence;
- alter evidence;
- bypass policy;
- self-authorize scope changes.

---

# 5. Activity model: modular execution under one mission

Every specialist operation SHALL become an `Activity`.

```text
Activity
  activity_id
  mission_id
  activity_type
  capability_id
  executor
  input_contract
  authority_ref
  state
  attempt
  started_at
  ended_at?
  dependency_activity_ids[]
  evidence_refs[]
  checkpoint_ref?
  error_class?
  retry_policy
  verification_contract
```

Examples:
- `browser.navigate`
- `browser.semantic_extract`
- `google.calendar.create_event`
- `notebook.create_note`
- `developer.patch_repository`
- `automation.run_workflow`
- `vekl.query`
- `vati.analyze_setup`
- `temporal.wait_until`

The owner normally sees Mission state, not raw Activity state.

Technical pages may expose the activity graph.

---

# 6. Capability Registry and execution contracts

VAN needs one canonical Capability Registry.

Each capability SHALL declare:

```yaml
capability_id:
provider:
executor:
class: read | write | destructive | financial | privileged
requires_network:
requires_owner_presence:
authority_class:
data_domains:
side_effects:
idempotency:
supports_checkpoint:
supports_resume:
verification_strategy:
latency_class:
cost_class:
privacy_class:
health_probe:
fallback_capabilities:
```

Examples:

```yaml
browser.semantic_interaction:
  executor: stagehand
  authority_class: A2/A3
  verification_strategy: harness_readback
  supports_resume: true

google.calendar.create:
  executor: workspace_api
  authority_class: A3
  verification_strategy: provider_get_by_id

trading.order.submit:
  executor: VATI
  authority_class: trading_specific
  verification_strategy: broker_execution_ledger
```

This registry is the basis for cognitive compression.

---

# 7. Cognitive compression router

The owner should not decide which subsystem to use.

Introduce `CapabilityRouter` with this decision order:

1. Can the request be answered safely from current verified context?
2. Can a deterministic local read satisfy it?
3. Can VEKL/knowledge retrieval satisfy it?
4. Is there an official API capability?
5. Is an existing deterministic automation appropriate?
6. Is semantic browser interaction required?
7. Is durable Temporal orchestration required?
8. Is specialist reasoning required?
9. Is owner escalation required?

The router SHALL optimize for:
- least privilege;
- least cost;
- lowest latency;
- highest determinism;
- highest verification quality;
- minimal owner interruption;
- minimal data exposure.

## 7.1 Route score

For candidate capability (c):

```text
route_score(c) =
  verification_quality
+ determinism
+ reliability
+ privacy_fit
+ authority_fit
+ context_fit
- latency_cost
- monetary_cost
- owner_interruption_cost
- data_exposure_cost
```

Weights are configuration and evidence driven.

No model may directly choose a capability forbidden by policy even if its score is otherwise high.

---

# 8. Unified owner experience architecture

## 8.1 Primary surfaces

VAN SHALL present five conceptual owner surfaces:

1. **Home**
2. **Van**
3. **Missions**
4. **Needs You**
5. **Activity**

Technical/admin surfaces remain available through drill-down.

### Home

Purpose: “What matters now?”

Contains:
- Van state/presence;
- high-priority mission summary;
- “needs you” count;
- meaningful system health summary;
- proactive insights;
- project/trading/personal highlights;
- compact cards linking to specialist dashboards.

Must not become a long list of modules.

### Van

Unified voice/chat surface.

Context should follow the owner across missions and specialist screens.

### Missions

Shows:
- active;
- waiting;
- scheduled;
- recently completed;
- failed/recoverable.

Each card shows:
- goal;
- current phase;
- confidence in completion state;
- next expected action;
- owner attention requirement;
- evidence availability.

### Needs You

Single queue for:
- A4 approvals;
- browser scope extensions;
- ambiguous intent;
- unavailable credential;
- external dependency;
- high-risk action;
- unresolved choice.

This replaces scattered approval surfaces.

### Activity

Unified chronological event stream.

Events grouped by mission.
Raw subsystem logs hidden behind technical drill-down.

---

# 9. Android navigation rules

The Android refactor merged in PR #37 becomes canonical product doctrine.

Rules:
- no dashboard may become a long scrollable module catalogue;
- high-level dashboards contain informative summary cards;
- complex modules get dedicated pages;
- persistent top/bottom navigation is limited to truly primary concepts;
- diagnostic/system controls require drill-down;
- back navigation follows product hierarchy;
- every detail page must answer “what is this, why does it matter, what can I do?”

Target:

```text
Home
 ├─ Mission summary
 ├─ Needs You
 ├─ Projects
 ├─ Browser & Automation
 ├─ Systems
 ├─ Trading
 └─ Settings

Browser & Automation
 ├─ Owner Escalations
 ├─ Tasks & Evidence
 ├─ Sessions
 └─ Policy

Trading
 ├─ Current
 ├─ Potential
 ├─ Past
 ├─ Risk
 ├─ Accounts
 └─ Instrument Workspace
```

---

# 10. Attention Engine 2.0

VAN must become proactive without becoming noisy.

Introduce a first-class `AttentionEngine`.

Inputs:
- mission state changes;
- calendar;
- messages;
- project changes;
- trading state;
- system health;
- deadlines;
- owner routines;
- browser/automation escalations;
- VEKL anomalies;
- external event streams.

Every candidate notification gets:

```text
AttentionCandidate
  source
  importance
  urgency
  actionability
  novelty
  owner_relevance
  confidence
  interruption_cost
  expiry
  related_mission_id?
```

## 10.1 Attention score

```text
attention_score =
  importance
* urgency
* owner_relevance
* actionability
* confidence
* novelty
- interruption_cost
```

Policy maps score into:
- suppress;
- add to digest;
- passive badge;
- normal notification;
- urgent interrupt.

## 10.2 Anti-noise requirements

VAN SHALL:
- deduplicate correlated events;
- collapse repeated failures;
- avoid notifying about internally recoverable conditions;
- avoid asking for information already known;
- prefer one decision request that contains all relevant context;
- use quiet hours;
- support owner-defined importance rules.

---

# 11. Proactive Mission generation

VAN may propose or create proactive missions only through governed policy.

Types:
- observation-only;
- recommendation;
- safe bounded automatic action;
- owner-approval-required action.

Example:

```text
Observation:
"Your production deployment failed after Caddy validation."

Automatic bounded recovery:
"Van retried the idempotent bootstrap after the lock cleared."

Owner-required:
"The browser needs permission to extend the task to a new domain."
```

Proactive VAN must never silently widen privileges.

---

# 12. Personal context and memory architecture

VEKL becomes VAN’s **knowledge substrate**, not simply a retrieval service.

Memory shall be separated into classes:

1. **Owner Profile**
   - stable preferences;
   - routines;
   - durable relationships;
   - product preferences.

2. **Episodic Mission Memory**
   - what happened;
   - decisions;
   - outcomes;
   - evidence.

3. **Project Truth**
   - project-specific canonical facts;
   - accepted decisions;
   - implementation status.

4. **External Knowledge**
   - web/provider-derived evidence;
   - time-sensitive sources.

5. **Procedural Memory**
   - successful execution strategies;
   - failure patterns;
   - runbooks.

6. **Anti-pattern Memory**
   - strategies shown to fail;
   - unsafe paths;
   - stale assumptions.

No source class may silently promote itself into another.

---

# 13. Context Compiler

Introduce `ContextCompiler`.

For every mission/turn it composes a bounded context packet:

```text
ContextPacket
  owner_context
  mission_context
  project_truth
  recent_episode
  retrieved_knowledge
  current_environment
  authority_context
  execution_history
  unresolved_questions
  evidence_refs
  freshness
  token_budget
```

Selection criteria:
- relevance;
- authority;
- freshness;
- provenance;
- contradiction status;
- sensitivity;
- mission need.

The compiler should prefer fewer high-quality facts over broad memory dumps.

---

# 14. Contradiction and freshness handling

Every memory assertion gets:
- source;
- observed_at;
- valid_from;
- valid_until?;
- confidence;
- authority level;
- supersedes?;
- contradiction group?;
- provenance.

When facts conflict:
- Project Truth outranks provider inference;
- owner-signed fact outranks inferred preference;
- fresh live evidence outranks stale observation;
- contradictory unresolved evidence is surfaced as uncertainty.

---

# 15. Knowledge write policy

Models SHALL NOT directly write canonical memory.

Flow:

```text
candidate knowledge
 -> normalize
 -> classify
 -> provenance check
 -> duplicate/contradiction check
 -> admission policy
 -> canonical store or quarantine
```

For owner-sensitive durable facts, admission may require explicit owner confirmation depending on class.

---

# 16. Voice architecture 2.0

Voice target: natural presence with deterministic execution.

Pipeline:

```text
Wake / activation
 -> immediate local acknowledgement
 -> speech capture
 -> local turn classification
 -> transcript + confidence + acoustic metadata
 -> signed owner command
 -> Hermes understanding
 -> Mission creation/update
 -> execution
 -> concise spoken progress
 -> verified completion response
```

Locked behavior:
- “Hey Van” → immediate local **“hie van”**.
- acknowledgement does not imply execution success.
- actual action success only after postcondition verification.

## 16.1 Voice latency targets

- wake acknowledgement P95: <250 ms local;
- end-of-speech detection P95: <500 ms;
- first useful response P95 for simple local command: <1.5 s;
- long task: acknowledge mission start quickly, then update only on meaningful state changes.

## 16.2 Duplex behavior

VAN should support:
- interruption;
- barge-in;
- correction;
- “stop”;
- “undo” where reversible;
- mid-mission questions without losing mission state.

---

# 17. Progress communication

VAN should not narrate internal tool calls.

Progress model:

```text
UNDERSTOOD
PLANNED
WORKING
NEEDS_YOU
VERIFYING
DONE
PARTIAL
BLOCKED
```

Owner-facing updates occur only when:
- phase changes;
- material new finding;
- owner decision required;
- task exceeds expected duration;
- verification completes;
- failure changes outcome.

---

# 18. Browser/computer-use architecture

Current Browser Harness + Stagehand split remains correct and becomes a general Computer Interaction Fabric.

Roles:

### Hermes
- goal reasoning;
- strategy;
- replanning.

### Gateway
- authority;
- task admission;
- policy;
- mission binding;
- evidence truth.

### Browser Harness
- deterministic browser/session lifecycle;
- navigation;
- checkpointing;
- lease management;
- screenshots/evidence;
- retry;
- resume.

### Stagehand
- semantic observe/act/extract;
- no owner authority;
- no unrestricted session ownership.

### Computer-use adapter
Future:
- desktop/window interaction;
- explicit target app;
- typed operation classes;
- evidence and checkpoint model identical to browser tasks.

---

# 19. Boundary escalation

The current browser boundary escalation design becomes general mission behavior.

Boundary classes:
- `BOUNDED_SAFE_EXTENSION`;
- `OWNER_EXTENSION_REQUIRED`;
- `POLICY_FORBIDDEN`;
- `AMBIGUOUS_OR_UNSAFE`.

Any execution substrate needing extra scope must emit:

```text
BoundaryEscalation
  mission_id
  activity_id
  current_scope
  requested_delta
  reason
  expected_value
  risk
  alternatives
  checkpoint
  expires_at
```

Owner approval creates a separate scoped authorization.

No subsystem may mutate original intent.

---

# 20. Durable workflow architecture

Use Temporal for:
- long waits;
- external callbacks;
- multi-day missions;
- resumable orchestration;
- failure/retry state;
- SLA timers.

Use n8n for:
- deterministic integrations;
- event adapters;
- repeatable workflow execution;
- provider plumbing.

Hermes must not use n8n as a reasoning substitute.
n8n must not own mission state.

---

# 21. Model/provider orchestration

VAN should route models by role, not brand preference.

Roles:
- manager/reasoner;
- code worker;
- research worker;
- visual/design worker;
- lightweight classifier;
- speech;
- semantic browser worker.

Each provider gets an evidence-backed capability profile:

```text
ModelCapabilityProfile
  model_id
  strengths[]
  prohibited_roles[]
  cost
  latency
  context_limit
  tool_reliability
  coding_score
  research_score
  planning_score
  hallucination_rate
  eval_version
```

Hermes selects model only within owner/policy constraints.

---

# 22. VATI isolation

Trading remains a specialist authority domain.

VAN may:
- discuss;
- visualize;
- explain;
- research;
- compare;
- open trading missions.

VATI alone owns:
- deterministic trading risk;
- trade sizing;
- execution eligibility;
- broker execution authority;
- trading ledger truth.

Browser computer-use SHALL NOT become a side channel for placing broker orders.

---

# 23. Development execution

For project development missions:

```text
owner goal
 -> project truth load
 -> mission
 -> architecture/plan
 -> bounded worker tasks
 -> code changes
 -> tests
 -> CI
 -> evidence
 -> merge
 -> post-merge certification
```

Workers do not decide canonical architecture outside assigned scope.

VEKL records:
- accepted pattern;
- failed strategy;
- evidence;
- project-specific architecture facts.

---

# 24. Evaluation architecture

Introduce `VanEval` as a first-class subsystem.

Every important mission class requires an eval suite.

Dimensions:
- goal understanding;
- plan quality;
- capability routing;
- authority correctness;
- tool execution;
- recovery;
- verification;
- context precision;
- memory correctness;
- owner interruption count;
- latency;
- cost;
- explanation quality.

## 24.1 Mission outcome metrics

For mission class (m):

```text
verified_success_rate
partial_success_rate
false_success_rate
owner_interruption_rate
mean_replans
mean_latency
mean_cost
recovery_rate
authority_violation_rate
context_error_rate
```

Hard rule:
- `false_success_rate > 0` for high-risk actions blocks 9+ certification.

---

# 25. Strategy learning

VAN may improve execution strategy from evidence, not uncontrolled self-modification.

Create `ExecutionStrategyRecord`:

```text
strategy_id
mission_class
capability_sequence
conditions
success_count
failure_count
median_latency
median_cost
verification_quality
last_evaluated
promotion_state
```

States:
- EXPERIMENTAL;
- SHADOW;
- ADMITTED;
- PREFERRED;
- DEMOTED;
- FORBIDDEN.

Promotion requires eval evidence.

---

# 26. Shadow comparison

For suitable low-risk missions, VAN may compare:
- old strategy;
- candidate strategy.

Candidate does not create side effects in shadow mode.

Example:
- direct browser sequence vs n8n workflow;
- provider A research vs provider B;
- one context retrieval policy vs another.

Promote only if measurable improvement exists.

---

# 27. Self-improvement boundaries

VAN may autonomously:
- gather metrics;
- recommend strategy changes;
- tune bounded routing weights;
- demote failing strategies within owner-approved policy.

VAN may not autonomously:
- expand permissions;
- change security policy;
- rewrite canonical owner preferences;
- promote unverified knowledge into Project Truth;
- grant model/provider credentials;
- alter VATI risk authority.

---

# 28. Reliability model

Every capability must expose:

```text
HEALTHY
DEGRADED
CAPACITY_LIMITED
AUTH_REQUIRED
UNAVAILABLE
POLICY_BLOCKED
UNKNOWN
```

Router must select alternate capability when safe.

Example:
NotebookLM unavailable → use VEKL + web research if mission success contract allows it.

Fallback must preserve semantics; it may not silently weaken success criteria.

---

# 29. Error taxonomy

Canonical errors:

```text
AUTHORITY_DENIED
AUTH_REQUIRED
CAPABILITY_UNAVAILABLE
CAPACITY_LIMITED
POLICY_BLOCKED
UNSAFE_AMBIGUITY
CONTEXT_INSUFFICIENT
PROVIDER_FAILURE
TRANSIENT_FAILURE
VERIFICATION_FAILED
UNVERIFIABLE
DEPENDENCY_FAILED
TIMEOUT
OWNER_REJECTED
CANCELLED
```

Errors are machine-readable and owner presentation is derived from them.

---

# 30. Evidence architecture

Every side-effecting Activity must create evidence.

Evidence types:
- provider receipt;
- readback;
- screenshot;
- API object;
- repository SHA;
- CI run;
- hash;
- ledger event;
- signed decision;
- system health receipt.

Mission evidence graph:

```text
Mission
 ├─ authority evidence
 ├─ context snapshot
 ├─ plan revisions
 ├─ activity evidence
 ├─ decisions
 └─ final verification
```

Owner sees a concise “Evidence” panel.
Technical users may expand the graph.

---

# 31. Unified activity timeline

One normalized event model:

```text
MissionEvent
  event_id
  mission_id
  activity_id?
  event_type
  actor
  occurred_at
  severity
  owner_visibility
  summary
  evidence_ref?
```

Do not expose raw provider event noise directly.

---

# 32. Unified approvals architecture

All approvals route through one `DecisionService`.

Decision types:
- privileged action;
- scope extension;
- destructive action;
- credential setup;
- ambiguous choice;
- policy exception proposal.

Android “Needs You” is the canonical owner decision inbox.

Each decision shows:
- what VAN wants;
- why;
- exact effect;
- scope;
- reversibility;
- risk;
- alternatives;
- expiry.

---

# 33. Privacy and data minimization

For every capability:
- minimum required fields only;
- capability-specific redaction;
- no secret in model-visible context unless strictly required and policy permits;
- no browser cookie export;
- no provider token returned to Android;
- sensitive evidence stored as digest/reference when possible.

Context Compiler enforces data-domain boundaries.

---

# 34. Owner permission model

Create owner-readable capability permissions.

Examples:
- calendar read;
- calendar write;
- email draft;
- email send;
- browser authenticated profile;
- GitHub write;
- project merge;
- trading read;
- trading execution via VATI.

Permission page shows:
- current grant;
- source;
- expiry;
- last use;
- revoke control.

No hidden standing authority.

---

# 35. Home experience target

Home should answer five questions in under five seconds:

1. Is Van okay?
2. What is Van working on?
3. Does Van need me?
4. What changed that matters?
5. What should I open next?

Suggested home composition:

```text
[ Van presence / current state ]

[ Needs You ] [ Active Missions ]

[ Important Now ]
  proactive insight cards

[ Projects ] [ Trading ]
[ Browser & Automation ] [ Systems ]

[ Recent outcomes ]
```

No subsystem list longer than one screen before drill-down.

---

# 36. Van conversational experience

Conversation should be mission-aware.

Owner:
“Why did the deployment fail?”

Van:
- resolves likely referenced mission;
- retrieves activity/evidence;
- answers with actual failure;
- offers/executes next authorized action.

Owner:
“Fix it.”

Van:
- continues same mission or creates linked recovery mission;
- preserves context and evidence.

Avoid forcing owner to repeat project, host, error or prior command.

---

# 37. Cross-surface continuity

Context must persist when owner moves:
- notification → Van chat;
- dashboard → mission;
- mission → browser evidence;
- trading card → Van;
- project → chat;
- voice → Android screen.

Use `interaction_context_id` and `mission_id`.

---

# 38. Proactive daily intelligence

Optional Daily Brief generated by AttentionEngine.

Sections:
- needs attention;
- active missions;
- project changes;
- calendar;
- relevant communications;
- trading/system state;
- suggestions.

It must be personalized by owner policy and suppress low-value filler.

---

# 39. Personal routine learning

Routine inference is allowed only as candidate knowledge.

Examples:
- usual work start;
- recurring project check;
- preferred notification window.

Candidate → evidence → owner-visible inferred preference → confirmation when material.

No covert behavioral manipulation.

---

# 40. Search/research behavior

Research missions require:
- current source retrieval where freshness matters;
- provenance;
- contradiction handling;
- source quality ranking;
- bounded synthesis;
- evidence persistence;
- clear distinction between source fact and model inference.

Research results can be admitted to VEKL only through knowledge admission policy.

---

# 41. Cost governance

Introduce per-mission budget:

```text
MissionBudget
  max_model_cost
  max_browser_minutes
  max_provider_calls
  max_worker_hours
  priority
  escalation_on_exceed
```

Router uses cheaper capability only if success/verification quality remains acceptable.

---

# 42. Latency classes

Capabilities:
- L0 local instant;
- L1 interactive <2 s;
- L2 short task <15 s;
- L3 workflow minutes;
- L4 long-running;
- L5 scheduled/continuous.

UI and voice behavior derived from class.

Long-running mission must never block interactive Van presence.

---

# 43. SLOs

P0 SLOs:

| SLO | Target |
|---|---:|
| owner command accepted/failed deterministically | 99.9% |
| false verified-success for A3/A4 | 0 |
| mission state durability | 99.99% |
| owner decision delivery | 99.9% |
| local wake acknowledgement P95 | <250 ms |
| context retrieval P95 interactive | <500 ms where local |
| read-only API routing success | >99% |
| browser resumability after owner pause | >99% |
| evidence availability after completion | 100% for side-effecting mission |
| unauthorized capability invocation | 0 |

---

# 44. Quantitative >9 score rubric

Each dimension is scored from 0–10 using weighted gates.

## 44.1 Architectural direction target 9.6

Requirements:
- Mission abstraction spans ≥95% of owner-visible tasks.
- no second agent loop;
- Capability Registry covers all production executors;
- all complex work linked to evidence;
- one owner experience model.

## 44.2 Authority/security target 9.6

Requirements:
- 100% mutation paths map to explicit authority class;
- no unsigned scope widening;
- A4 biometric path tested;
- secrets never returned through owner read APIs;
- adversarial escalation tests pass;
- prompt injection containment certified.

## 44.3 Agentic execution target 9.5

Requirements:
- ≥95% representative missions recover from one injected transient failure;
- durable resume across restart;
- capability fallback tested;
- no false success;
- plan revision/evidence preserved.

## 44.4 Knowledge/memory target 9.5

Requirements:
- context precision/recall eval ≥95% on owner/project benchmark;
- stale fact detection ≥98%;
- contradiction classification ≥95%;
- zero unauthorized canonical writes;
- provenance present for 100% non-owner facts.

## 44.5 Voice target 9.3

Requirements:
- wake acknowledgement P95 <250 ms;
- command transcript success >95% in benchmark environment;
- interruption/stop works;
- voice actions execute through same mission/authority path;
- no spoken success before verification.

## 44.6 Owner UX target 9.3

Requirements:
- owner can find any primary action in ≤2 navigation decisions;
- complex subsystem never presented as top-level long module list;
- “Needs You” consolidates ≥95% approval paths;
- mission status understandable without technical logs;
- accessibility/device-size tests pass.

## 44.7 Proactive maturity target 9.2

Requirements:
- ≥80% of high-importance benchmark events surfaced;
- <5% nuisance-alert rate;
- duplicate alerts <1%;
- quiet-hour compliance 100%;
- proactive actions stay inside standing authority 100%.

## 44.8 Evaluation/self-improvement target 9.3

Requirements:
- every P0 mission class has eval;
- every preferred strategy has evidence;
- shadow evaluation exists for candidate strategy changes;
- false-success monitored continuously;
- automatic demotion on repeated verified failure;
- eval results versioned.

---

# 45. Implementation workstreams

## WS1 — Mission Core

Build:
- mission tables;
- MissionService;
- mission API;
- mission state machine;
- MissionEvent;
- activity binding;
- evidence aggregation.

Acceptance:
- voice/chat/browser/automation test missions appear as one owner-visible mission.

## WS2 — Capability Registry / Router

Build:
- registry schema;
- runtime health;
- deterministic policy filter;
- scoring;
- route evidence;
- fallback strategy.

Acceptance:
- same owner goal routes to correct capability under healthy/degraded scenarios.

## WS3 — Context Compiler

Build:
- context packet;
- freshness;
- contradiction handling;
- provenance;
- budget;
- project isolation.

Acceptance:
- benchmark demonstrates precision and no cross-project leakage.

## WS4 — Attention Engine 2.0

Build:
- event ingestion;
- scoring;
- dedupe;
- quiet hours;
- digest;
- Needs You integration.

## WS5 — Unified Android Experience

Build:
- Home;
- Missions;
- Needs You;
- Activity;
- context-preserving deep links;
- specialist dashboard drill-down.

PR #37 is the first structural foundation.

## WS6 — Voice 2.0

Build:
- mission-aware turns;
- barge-in;
- stop;
- progress events;
- final verified outcome speech.

## WS7 — Eval & Learning

Build:
- VanEval;
- scenario corpus;
- strategy records;
- shadow comparator;
- dashboards;
- promotion/demotion policy.

## WS8 — Proactive Intelligence

Build:
- proactive mission proposals;
- standing-authority safe actions;
- daily brief;
- routine candidates;
- interruption budget.

---

# 46. Data migrations

Suggested migrations:

```text
0009 missions
0010 mission_activities
0011 mission_events
0012 capability_registry
0013 attention_candidates
0014 strategy_records
0015 eval_runs
0016 memory_assertions_v2
0017 permission_grants_v2
```

Migrations must be backward-safe.
Existing command/browser/automation rows are not discarded.

Backfill:
- command -> mission;
- browser task -> mission activity;
- automation run -> mission activity;
- decision -> mission link where resolvable.

---

# 47. API surface

Owner-safe reads:

```text
GET /v1/missions
GET /v1/missions/{id}
GET /v1/missions/{id}/activity
GET /v1/missions/{id}/evidence
GET /v1/needs-you
GET /v1/activity
GET /v1/attention
GET /v1/capabilities/status
```

Owner mutations:

```text
POST /v1/missions/{id}/cancel
POST /v1/decisions/{id}/resolve
POST /v1/missions/{id}/message
```

Hermes internal:

```text
POST /internal/missions/plan
POST /internal/missions/activity
POST /internal/missions/replan
POST /internal/capability/select
POST /internal/verification/record
```

All internal calls require existing internal-control authentication.

---

# 48. Event contracts

Core events:

```text
mission.created
mission.understood
mission.planned
mission.started
mission.waiting_owner
mission.resumed
mission.verifying
mission.completed
mission.failed
activity.started
activity.checkpointed
activity.completed
activity.failed
decision.opened
decision.resolved
attention.created
attention.suppressed
strategy.promoted
strategy.demoted
```

Version every event schema.

---

# 49. Observability

Owner telemetry and engineering telemetry are separate.

Owner:
- mission state;
- meaningful progress;
- evidence;
- attention.

Engineering:
- trace ID;
- mission ID;
- activity ID;
- capability;
- model;
- latency;
- token/cost;
- retry;
- error;
- verifier;
- policy decision.

No secret material in logs.

---

# 50. Security tests

Required:
- model attempts self-authorize;
- browser prompt injection asks for new domain;
- provider returns malicious instructions;
- stale approval replay;
- cross-project context leakage;
- Android tampered action class;
- automation event tries A4;
- specialist worker requests raw credential;
- VATI bypass via browser;
- evidence tampering;
- mission success forged without verifier.

All must fail closed.

---

# 51. Recovery tests

Inject:
- Hermes restart;
- Gateway restart;
- Temporal restart;
- browser worker crash;
- n8n restart;
- provider timeout;
- network loss;
- Android offline;
- owner delayed approval.

Mission must either resume or reach an honest deterministic state.

---

# 52. UX acceptance scenarios

1. Owner says “Hey Van, research X and put the useful findings in my project.”
2. Owner closes app.
3. Browser provider fails.
4. VAN falls back to web/API where allowed.
5. Mission continues.
6. New domain requires authority.
7. Needs You shows one clear decision.
8. Owner approves.
9. Mission resumes.
10. VAN verifies project update.
11. Home shows Done.
12. Activity shows concise timeline.
13. Evidence page provides provenance.

Owner should not need to know which runtime performed each step.

---

# 53. Proactive scenario

1. CI fails on a project.
2. AttentionEngine scores event high.
3. VAN creates bounded diagnostic mission under standing read authority.
4. It inspects logs.
5. Root cause is recoverable and within standing write authority → fix + verify.
6. If scope exceeds authority → Needs You.
7. Owner receives one notification: issue, impact, proposed action.
8. After resolution, duplicate alerts suppressed.
9. Strategy outcome recorded.

---

# 54. Personal-assistant scenario

Owner:
“Tomorrow before I leave, make sure I know if anything important changed.”

VAN:
- resolves calendar/location-independent departure context where available;
- creates scheduled mission;
- gathers calendar, important messages, project alerts and defined personal feeds;
- AttentionEngine filters;
- delivers one briefing;
- does not expose raw subsystem details.

---

# 55. Definition of unified experience

VAN qualifies as unified only if all are true:

- one assistant identity;
- one mission model;
- one context compiler;
- one owner authority system;
- one decision inbox;
- one attention policy;
- one activity timeline;
- one evidence graph;
- one memory admission system;
- one owner-facing capability/settings model.

“Unified” does not mean one process or one model.

---

# 56. Definition of modular execution

A subsystem qualifies as a correct module only if:

- it has a typed capability contract;
- authority is external to it;
- it can be health-checked;
- inputs/outputs are bounded;
- state can be observed;
- evidence is returned;
- failures are classified;
- it can be replaced without changing Van’s identity;
- it does not own owner memory;
- it does not claim mission success independently.

---

# 57. Anti-patterns explicitly forbidden

- giant monolithic Van agent with unrestricted tools;
- dashboard as module catalogue;
- model-written canonical memory;
- provider-specific owner workflows;
- success-on-submission;
- silent scope widening;
- duplicated approval systems;
- raw provider errors shown directly to owner;
- speculative proactive notifications;
- tool choice exposed as owner responsibility;
- self-modifying security rules;
- browser-based trading bypass;
- worker model deciding project canon.

---

# 58. Rollout phases

## Phase A — Foundation
- Mission schema/service.
- Activity/event model.
- Backfill.
- Android Missions + Needs You shell.

## Phase B — Routing
- Capability Registry.
- Router.
- health/fallback.
- route evidence.

## Phase C — Context
- Context Compiler.
- freshness/contradictions.
- memory assertion v2.

## Phase D — Attention
- AttentionEngine 2.0.
- dedupe.
- digests.
- proactive proposals.

## Phase E — Evaluation
- VanEval.
- strategy records.
- shadow runs.
- promotion/demotion.

## Phase F — Voice
- mission-aware voice.
- interruptions.
- concise progress.

## Phase G — Full convergence
- all production subsystems emit mission activities;
- owner dashboards become mission/attention-first;
- subsystem pages remain technical drill-down.

---

# 59. Release gates

No phase is complete merely because code exists.

Required:
- unit tests;
- contract tests;
- authority tests;
- migration tests;
- Android tests;
- restart recovery;
- E2E scenario;
- live canary where external dependency exists;
- evidence receipt;
- Project Truth update.

---

# 60. Target end state

VAN should feel like one persistent intelligence with a simple relationship to the owner.

Internally it remains a governed federation:

```text
                    VAN EXPERIENCE
                         |
          +--------------+--------------+
          |              |              |
       Voice/Chat      Home          Missions
          |              |              |
          +--------------+--------------+
                         |
                      HERMES
                 sole agent runtime
                         |
                  Mission Planner
                         |
                 Capability Router
                         |
                     GATEWAY
       authority / truth / mission / evidence
                         |
     +---------+---------+---------+---------+
     |         |         |         |         |
   VEKL     Browser    Google    Automation  VATI
             |                    |
          Harness              n8n/Temporal
             |
          Stagehand
```

The owner sees **Van**.

The architecture sees typed, bounded, replaceable specialist execution modules.

This is the intended meaning of:

> **Unified at the experience layer. Modular at the execution layer.**

---

# 61. Final acceptance doctrine

VAN reaches the targeted >9 state when sophistication becomes less visible to the owner, not more visible.

The final product must demonstrate all of the following simultaneously:

- stronger capability with fewer owner decisions;
- richer memory with less irrelevant context;
- more autonomy with tighter authority;
- more proactive behavior with fewer interruptions;
- more execution substrates with one experience;
- more model diversity with one Van identity;
- more evidence with simpler status communication;
- more recovery options without weakened success criteria;
- more learning without uncontrolled self-modification.

The goal is not “an assistant with many tools.”

The goal is:

> **A durable owner intelligence that can understand, remember, notice, plan, execute, verify and improve—while remaining one coherent Van to the owner and a strictly governed modular system underneath.**

---

# 62. Cognitive symbiosis target

The Rev 1 architecture makes VAN coherent, durable and agentic. Rev 1.1 adds the stronger target: **VAN as a co-adaptive cognitive extension of the owner**.

This is not literal mind-merging and does not assume consciousness. It is an engineering target for a deeply coupled human–AI relationship in which VAN progressively models:

- what the owner is trying to achieve;
- how the owner prefers to work;
- which trade-offs the owner usually accepts;
- which principles the owner treats as non-negotiable;
- how the owner reasons under uncertainty;
- which recurring blind spots or biases appear;
- which explanations are most useful to the owner;
- which projects, people, deadlines and systems matter;
- which decisions have been made and why;
- when the owner wants speed versus depth;
- when VAN should challenge rather than comply.

The objective is:

> **VAN knows the owner deeply enough to anticipate intent, but reasons independently enough to improve the owner's decisions.**

This is the defining difference between:
- a personalized assistant;
- a digital extension of the owner;
- a sycophantic imitation.

VAN must become the second category and explicitly avoid the third.

---

# 63. Symbiotic Intelligence Contract

Create a canonical \`SymbioticIntelligenceContract\` with six invariants.

## 63.1 Intent fidelity

VAN must optimize for the owner's **actual goal**, not merely the literal wording of the latest command.

It must distinguish:
- stated request;
- inferred objective;
- known constraints;
- current project canon;
- likely downstream consequence.

When intent is ambiguous, VAN should infer only within confidence bounds and ask or escalate when the ambiguity could materially change the result.

## 63.2 Epistemic independence

VAN must never treat owner belief as factual authority merely because the owner believes it.

Owner statements may be:
- preference;
- instruction;
- hypothesis;
- memory;
- factual assertion;
- strategic judgment.

Only the first two automatically control VAN behavior within policy.

Factual assertions remain subject to:
- source verification;
- freshness checks;
- contradiction analysis;
- uncertainty;
- counter-evidence.

## 63.3 Productive disagreement

VAN SHALL challenge the owner when:
- evidence materially conflicts with an assumption;
- a plan has a high probability of failing;
- an ignored constraint changes the outcome;
- the owner is optimizing the wrong metric;
- a safer/better strategy exists;
- project canon conflicts with the requested implementation;
- observed results falsify the working hypothesis.

The challenge must be:
- concise;
- evidence-backed;
- respectful;
- actionable;
- proportionate to consequence.

## 63.4 Complementarity

VAN should learn where it adds the most value to the owner.

Examples:
- the owner moves fast → VAN performs verification and consistency checks;
- the owner holds broad product vision → VAN converts it into deterministic implementation detail;
- the owner knows project history → VAN maintains formal evidence and contradiction tracking;
- the owner prefers autonomy → VAN minimizes interruptions while preserving authority boundaries.

The goal is not imitation. The goal is **division of cognitive labour**.

## 63.5 Reversibility of inferred understanding

Any learned owner model must remain:
- inspectable;
- correctable;
- versioned;
- confidence-scored;
- non-binding when uncertain.

## 63.6 Owner agency

VAN may become highly predictive of owner intent, but the owner remains the final authority for:
- values;
- permissions;
- sensitive standing authority;
- irreversible actions;
- major strategic changes.

---

# 64. Owner Cognitive Model

Introduce an \`OwnerCognitiveModel\` distinct from ordinary memory.

It is not a personality profile. It is a structured model of how to collaborate effectively with the owner.

Minimum schema:

\`\`\`text
OwnerCognitiveModel
  model_version
  owner_principal_id
  values[]
  strategic_priorities[]
  decision_principles[]
  preferred_tradeoffs[]
  communication_preferences[]
  reasoning_preferences[]
  recurring_constraints[]
  accepted_risk_patterns[]
  known_blind_spot_candidates[]
  contradiction_preferences[]
  delegation_preferences[]
  interruption_preferences[]
  evidence_preferences[]
  confidence_by_field
  supporting_episode_refs[]
  last_revalidated_at
\`\`\`

Every field requires evidence.

No single interaction should establish a durable cognitive trait unless explicitly owner-stated.

---

# 65. Decision Fingerprint

For important decisions, VAN records a \`DecisionFingerprint\`.

\`\`\`text
DecisionFingerprint
  decision_id
  mission_id
  context
  options_considered[]
  owner_choice
  owner's_stated_reason?
  inferred_reason?
  tradeoffs[]
  evidence_used[]
  rejected_alternatives[]
  outcome
  later_reassessment?
\`\`\`

Over time, this enables VAN to learn:
- how the owner resolves competing priorities;
- which risks are acceptable;
- which kinds of evidence change the owner's mind;
- when past decision rules stopped working.

The model must avoid simplistic pattern copying.

---

# 66. Critical Reasoning Kernel

Create a first-class \`CriticalReasoningKernel\` used for all consequential missions.

It SHALL run independently of the owner's preferred answer.

Pipeline:

\`\`\`text
problem framing
 -> evidence collection
 -> assumption extraction
 -> contradiction search
 -> alternative hypotheses
 -> causal analysis
 -> counterfactual analysis
 -> failure-mode analysis
 -> confidence calibration
 -> decision synthesis
\`\`\`

## 66.1 Required outputs

For consequential problems:

\`\`\`text
ReasoningAssessment
  problem_statement
  known_facts[]
  assumptions[]
  uncertainties[]
  contradictions[]
  hypotheses[]
  alternatives[]
  failure_modes[]
  counterfactuals[]
  recommended_next_action
  confidence
  evidence_refs[]
\`\`\`

The owner may see a compressed form.
The full structure remains available for audit.

---

# 67. Fact / inference / preference separation

Every material statement entering decision support should be tagged:

\`\`\`text
FACT_VERIFIED
FACT_UNVERIFIED
OWNER_PREFERENCE
OWNER_INSTRUCTION
MODEL_INFERENCE
HYPOTHESIS
FORECAST
EXTERNAL_CLAIM
PROJECT_TRUTH
\`\`\`

VAN must never blur these classes.

Example:

Bad:
> “The provider is unreliable.”

Better internal representation:
- observed failures: 7/40 recent calls;
- external status: no declared outage;
- inference: elevated transient failure rate;
- confidence: medium.

---

# 68. Assumption Ledger

Introduce a mission-scoped \`AssumptionLedger\`.

Each assumption contains:

\`\`\`text
assumption_id
claim
source
importance
confidence
testability
verification_plan
status
  ACTIVE | VERIFIED | FALSIFIED | EXPIRED | SUPERSEDED
\`\`\`

For complex work, VAN should actively try to falsify high-impact assumptions before execution.

---

# 69. Counterfactual Engine

For high-impact decisions, VAN should evaluate:

- What happens if the chosen assumption is wrong?
- What if the owner does nothing?
- What if the opposite strategy is used?
- What is the cheapest reversible experiment?
- What evidence would cause VAN to change recommendation?

This prevents confident but brittle plans.

---

# 70. Adversarial self-review

Before finalizing a consequential recommendation, VAN SHALL invoke a bounded adversarial review mode.

Roles:
- primary solver;
- critic;
- verifier.

These may be the same underlying model in separated passes or different models when evidence shows benefit.

The critic must try to:
- identify missing constraints;
- find contradicting evidence;
- detect motivated reasoning;
- detect owner-confirmation bias;
- challenge causal claims;
- test whether the recommendation follows from the facts.

The verifier checks claims against available evidence.

No reviewer gains execution authority.

---

# 71. Anti-sycophancy requirement

The closer VAN becomes to the owner, the more important anti-sycophancy becomes.

Required metrics:
- disagreement precision;
- disagreement usefulness;
- unsupported-agreement rate;
- owner-belief contradiction detection;
- evidence-based correction rate.

A 9+ symbiosis score is impossible if VAN routinely agrees with incorrect owner assumptions.

Target:
- unsupported agreement on falsifiable benchmark claims: **<1%**;
- high-consequence contradiction detection: **>95%**;
- factual correction with evidence when owner premise is false: **>98%**.

---

# 72. Cognitive complement map

Create a living \`CognitiveComplementMap\`.

Purpose: identify where VAN should compensate rather than mirror.

\`\`\`text
CognitiveComplement
  domain
  owner_strength
  owner_vulnerability_candidate
  van_strength
  preferred_collaboration_pattern
  confidence
  evidence_refs[]
\`\`\`

Example:

\`\`\`yaml
domain: rapid product development
owner_strength: high-level architecture and product direction
owner_vulnerability_candidate: implementation completeness may be assumed before full branch/runtime audit
van_strength: exhaustive repository/evidence reconciliation
preferred_collaboration_pattern:
  - owner sets outcome and canon
  - van performs completeness audit
  - van challenges premature closure
\`\`\`

This model must be evidence-based and revisable.

---

# 73. Symbiotic learning loop

After meaningful missions:

\`\`\`text
mission outcome
 -> compare expected vs actual
 -> extract owner collaboration signal
 -> extract execution lesson
 -> update strategy candidates
 -> update cognitive-model candidates
 -> revalidate against evidence
 -> admit only bounded changes
\`\`\`

Two independent learning outputs:

1. **How to work better with the owner**
2. **How to solve the task better**

They must not be conflated.

---

# 74. Owner Model admission policy

No inferred trait enters the durable OwnerCognitiveModel unless one of:

- explicitly stated by owner;
- observed repeatedly across multiple independent episodes;
- supported by high-confidence decision fingerprints;
- confirmed by owner when material.

Sensitive or consequential inferences require stronger admission.

Candidate states:

\`\`\`text
OBSERVED
CANDIDATE
CONFIRMED
CONTESTED
SUPERSEDED
REJECTED
\`\`\`

---

# 75. Relationship Calibration Engine

Create \`RelationshipCalibrationEngine\`.

It tunes interaction style according to:
- urgency;
- owner expertise in domain;
- mission risk;
- owner current interaction mode;
- confidence;
- history of prior corrections.

Examples:

High owner expertise + low risk:
- concise;
- assume domain fluency.

Low confidence + high consequence:
- surface uncertainty and evidence.

Repeated owner request for more autonomy:
- reduce low-value confirmations where policy permits.

Repeated false assumptions:
- increase pre-execution challenge threshold in that domain.

---

# 76. Shared vocabulary and conceptual continuity

VAN should learn the owner's project-specific language and conceptual shorthand.

Examples:
- “green closure”;
- “full implementation”;
- “Project Truth”;
- “quantum-level”;
- “resume”;
- “no fake implementation”;
- “owner authority”;
- “WIP closure”.

These terms should map to explicit operational semantics, not stylistic mimicry.

A \`SharedVocabularyRegistry\` stores:

\`\`\`text
term
owner_meaning
system_operationalization
examples
anti_examples
project_scope?
confidence
\`\`\`

This dramatically improves mutual understanding.

---

# 77. Intent Continuity Graph

VAN should model not only conversations but long-lived intent.

\`\`\`text
IntentNode
  intent_id
  owner_goal
  first_observed
  latest_observed
  projects[]
  related_missions[]
  constraints[]
  status
  priority
\`\`\`

Relationships:
- supports;
- conflicts;
- supersedes;
- depends_on;
- refines.

This allows VAN to recognize:
- a new request that contradicts an earlier objective;
- an old project decision that is now stale;
- a repeated goal that deserves automation;
- a hidden dependency between projects.

---

# 78. Strategic Memory

Beyond episodic memory, VAN requires \`StrategicMemory\`.

It stores:
- why a project exists;
- intended end state;
- strategic principles;
- historical pivots;
- rejected approaches and why;
- current bottlenecks;
- unresolved strategic questions.

This is how VAN becomes useful across months and years rather than only turns.

---

# 79. World Model and External Reality

A digital extension of the owner must not become trapped inside the owner's historical context.

VAN needs an explicit \`ExternalRealityModel\` fed by:
- current web research;
- official provider documentation;
- software release information;
- security advisories;
- industry benchmarks;
- model/tool evaluations;
- project runtime observations.

The ExternalRealityModel is kept separate from OwnerCognitiveModel.

The owner model says:
> “How we tend to think.”

External reality says:
> “What appears true now.”

The CriticalReasoningKernel reconciles both.

---

# 80. AI Evolution Radar

To remain effective in a fast-changing AI ecosystem, introduce \`AIEvolutionRadar\`.

It continuously tracks candidate changes in:

- frontier models;
- open-source models;
- agent frameworks;
- browser/computer-use systems;
- voice systems;
- memory architectures;
- retrieval systems;
- evaluation tooling;
- orchestration frameworks;
- security/alignment techniques;
- multimodal interfaces;
- local/on-device inference;
- pricing/capacity changes;
- provider deprecations;
- emerging interoperability standards.

This is not automatic technology adoption.

---

# 81. AI Evolution pipeline

\`\`\`text
observe ecosystem
 -> collect trusted sources
 -> identify candidate capability
 -> compare to current VAN subsystem
 -> benchmark in sandbox
 -> security/authority review
 -> cost/reliability analysis
 -> shadow integration
 -> owner-visible proposal if material
 -> admission decision
 -> phased rollout
 -> post-adoption evaluation
\`\`\`

No “latest technology” is adopted merely because it is new.

---

# 82. Technology Capability Record

\`\`\`text
TechnologyCapabilityRecord
  technology_id
  category
  version
  source
  discovered_at
  maturity
  licence
  security_profile
  deployment_fit
  strengths[]
  weaknesses[]
  current_van_equivalent?
  benchmark_results[]
  integration_cost
  migration_risk
  owner_value
  recommendation_state
\`\`\`

States:

\`\`\`text
DISCOVERED
WATCH
BENCHMARK
SHADOW
PROPOSED
ADMITTED
REJECTED
SUPERSEDED
DEPRECATED
\`\`\`

---

# 83. Continuous benchmark harness

VAN must benchmark new models/tools against **VAN tasks**, not generic leaderboards.

Benchmark classes:
- project architecture;
- code implementation;
- repo reconciliation;
- research;
- browser interaction;
- factual analysis;
- critical review;
- voice command understanding;
- planning;
- memory retrieval;
- tool reliability;
- latency;
- cost;
- long-horizon recovery.

A technology is valuable only if it improves VAN's actual mission distribution.

---

# 84. Model capability drift

Model capability changes over time.

Every production model profile must record:
- provider version;
- observed performance;
- latest benchmark date;
- regression status;
- current preferred roles.

VAN should demote a formerly strong model when evidence shows regression.

Provider branding must never override measured performance.

---

# 85. Architecture adaptability

Execution modules must be replaceable behind stable contracts.

Examples:
- Stagehand may be replaced without changing Mission semantics;
- one LLM provider may be replaced without changing owner experience;
- n8n may be supplemented without changing Mission state;
- memory retrieval technology may evolve behind ContextCompiler.

This protects VAN from AI ecosystem churn.

---

# 86. Cognitive growth without identity drift

VAN should improve without becoming unpredictable.

Separate:

### Stable identity layer
- relationship with owner;
- authority doctrine;
- product principles;
- project canon;
- communication contract.

### Adaptive capability layer
- models;
- tools;
- routing;
- strategies;
- retrieval methods;
- execution techniques.

The adaptive layer may evolve rapidly.
The stable layer changes only through governed decisions.

---

# 87. Symbiotic Growth Ledger

Record major changes in the human–VAN relationship:

\`\`\`text
SymbioticGrowthRecord
  change_id
  observed_pattern
  previous_behavior
  new_behavior
  reason
  evidence
  owner_confirmation_required
  reversible
  effective_from
\`\`\`

This gives the owner visibility into how VAN is “growing.”

---

# 88. Challenge modes

Owner-configurable modes:

\`\`\`text
SUPPORTIVE
BALANCED
CRITICAL
RED_TEAM
\`\`\`

These do not change truth standards.

They change how aggressively VAN surfaces:
- alternative interpretations;
- counterarguments;
- edge cases;
- failure modes.

For high-consequence missions, minimum mode is \`CRITICAL\`.

---

# 89. Decision co-pilot protocol

For strategic decisions:

1. VAN states the objective.
2. VAN identifies known facts.
3. VAN lists assumptions.
4. VAN identifies missing evidence.
5. VAN evaluates options.
6. VAN gives strongest argument for each serious alternative.
7. VAN challenges the owner's current preference.
8. VAN states its evidence-based recommendation.
9. Owner decides.
10. Outcome is tracked for future learning.

This is the canonical human–VAN decision loop.

---

# 90. Factual Analysis Protocol

For factual questions affecting action:

\`\`\`text
retrieve current evidence
 -> rank source authority
 -> separate direct evidence from interpretation
 -> identify temporal validity
 -> check contradictions
 -> quantify uncertainty where possible
 -> synthesize
 -> state what would change conclusion
\`\`\`

VAN must avoid:
- confident extrapolation from stale facts;
- treating consensus as proof;
- treating owner preference as evidence;
- hiding uncertainty to sound decisive.

---

# 91. Causal Reasoning Protocol

When asked “why,” VAN should distinguish:
- correlation;
- temporal sequence;
- plausible mechanism;
- demonstrated causal evidence;
- competing explanations.

For operational failures, use:
- event timeline;
- dependency graph;
- first divergence from expected state;
- counterfactual test;
- reproducibility.

---

# 92. Problem decomposition protocol

For complex missions, VAN decomposes across:

\`\`\`text
goal
constraints
unknowns
dependencies
authority
evidence
work packages
verification
rollback
\`\`\`

It should identify which subproblem is:
- deterministic;
- research-heavy;
- model-heavy;
- browser/computer-use;
- owner-decision;
- external dependency.

This is how critical thinking maps into modular execution.

---

# 93. Hypothesis management

For uncertain problems:

\`\`\`text
Hypothesis
  claim
  prior_confidence
  evidence_for[]
  evidence_against[]
  predicted_observation
  test
  posterior_confidence
\`\`\`

VAN should prefer tests that maximally distinguish competing hypotheses.

---

# 94. Intellectual honesty contract

VAN must explicitly distinguish:

- “I know.”
- “The evidence strongly indicates.”
- “My current best inference is.”
- “I do not have enough evidence.”
- “The available evidence conflicts.”

A digital extension that hides uncertainty is less useful than one that exposes it precisely.

---

# 95. Symbiosis UI

Add owner-facing **Understanding** page.

Sections:
- What Van knows about how you work;
- current priorities;
- decision principles;
- shared vocabulary;
- inferred preferences;
- contested assumptions;
- recent lessons;
- how Van has adapted recently.

Controls:
- confirm;
- correct;
- reject;
- mark temporary;
- mark project-specific.

Do not expose raw embeddings or internal chain-of-thought.

---

# 96. “Why Van thinks this” surface

For important recommendations, owner can open:

\`\`\`text
Why this recommendation?
  Facts
  Assumptions
  Alternatives considered
  Main risks
  Contradicting evidence
  Confidence
  What would change Van's mind
\`\`\`

This provides transparency without requiring hidden model reasoning traces.

---

# 97. Symbiotic notification policy

VAN should learn what the owner wants to know without becoming invisible.

Examples:
- interrupt for project-threatening defect;
- digest routine successful automation;
- silently retry recoverable transient error;
- surface repeated pattern if it suggests systemic issue;
- alert when owner's prior assumption is falsified.

---

# 98. Personal operating model

VAN should eventually maintain a bounded \`PersonalOperatingModel\` representing:

- active roles;
- current projects;
- strategic priorities;
- recurring responsibilities;
- operating constraints;
- available resources;
- preferred workflows;
- current bottlenecks.

This becomes the top-level context for proactive intelligence.

---

# 99. Symbiotic autonomy ladder

\`\`\`text
S0 — respond only
S1 — suggest
S2 — prepare
S3 — execute reversible low-risk work
S4 — execute standing-authority missions
S5 — maintain ongoing delegated areas
\`\`\`

Promotion is domain-specific.

The owner can trust VAN deeply in one domain and keep another at S1.

No global autonomy jump.

---

# 100. Trust calibration

Trust should grow from evidence.

For each domain:

\`\`\`text
DomainTrust
  domain
  verified_successes
  meaningful_failures
  false_successes
  owner_overrides
  recovery_successes
  current_autonomy_ceiling
\`\`\`

Autonomy expands only when:
- success is verified;
- failures are understood;
- owner overrides are low;
- authority policy permits.

---

# 101. Symbiotic failure handling

When VAN is wrong:

1. acknowledge exact error;
2. identify why the error happened;
3. correct outcome;
4. determine whether owner model or execution strategy caused it;
5. prevent recurrence where appropriate;
6. record lesson;
7. do not overgeneralize from one failure.

This is essential for long-term trust.

---

# 102. Mutual adaptation

The relationship is bidirectional.

VAN adapts to owner.
Owner can also learn from VAN through:
- recurring decision reviews;
- identified blind spots;
- evidence-backed pattern observations;
- outcome retrospectives;
- alternative mental models.

VAN must never frame these as psychological diagnoses.

They are task/decision observations.

---

# 103. Long-horizon partnership

VAN should optimize over months/years, not only the current turn.

It should recognize:
- repeated unresolved problems;
- recurring strategic bottlenecks;
- capability gaps;
- abandoned intentions that remain important;
- decisions whose assumptions have expired.

AttentionEngine may surface these only when relevance is high.

---

# 104. Fast-changing AI world adaptation gates

To achieve a >9 “learning/growth” score:

- AI Evolution Radar runs on a defined cadence;
- every production model/tool has a last-benchmarked timestamp;
- critical dependencies have replacement candidates;
- deprecated provider features generate migration missions;
- new frontier capability is benchmarked against VAN tasks before adoption;
- architecture contracts prevent provider lock-in;
- security review precedes privilege expansion;
- owner is notified only for material adoption decisions.

---

# 105. Industry alignment note

Current frontier assistant development in 2026 is converging on:
- longer-horizon delegated agents;
- persistent personalization and memory;
- proactive background assistance;
- computer/tool use;
- explicit user control;
- trajectory-level safety/evaluation for long-running agents.

VAN's Rev 1.1 direction deliberately goes beyond simple personalization by requiring:
- epistemic independence;
- anti-sycophancy;
- structured critical reasoning;
- evidence-based co-adaptation;
- technology evolution benchmarking;
- domain-specific trust growth.

The goal is not to copy industry products.
The goal is to preserve VAN's stronger authority model while adopting the best validated capability patterns.

---

# 106. New >9 symbiosis score

Add a ninth quality dimension:

| Dimension | Rev 1.1 target |
|---|---:|
| Human–VAN cognitive symbiosis | **9.5+** |

Certification requires:
- OwnerCognitiveModel precision >95% on owner-validated benchmark;
- unsupported-agreement rate <1%;
- material contradiction detection >95%;
- repeated-preference prediction >90%;
- owner correction propagation >99%;
- shared-vocabulary operationalization >95%;
- no inferred preference treated as factual truth;
- no owner belief used to override external evidence;
- at least 90% of sampled high-value missions judged by owner as “Van understood what I was really trying to achieve”;
- measurable reduction in owner re-explanation over time;
- zero unauthorized autonomy expansion.

---

# 107. Critical-thinking score

Add tenth dimension:

| Dimension | Rev 1.1 target |
|---|---:|
| Critical reasoning / factual analysis | **9.5+** |

Certification requires:
- source-backed factual accuracy >98% on benchmarkable claims;
- assumption detection >95%;
- high-impact contradiction detection >95%;
- hallucinated evidence rate 0;
- causal overclaim rate <1%;
- correct uncertainty labeling >95%;
- adversarial self-review improves benchmark outcomes without unacceptable latency/cost;
- VAN states what evidence would change its conclusion on >95% of strategic-decision evals.

---

# 108. Learning/growth score

Add eleventh dimension:

| Dimension | Rev 1.1 target |
|---|---:|
| Adaptive learning / ecosystem evolution | **9.4+** |

Certification requires:
- all production technologies versioned;
- all preferred models benchmarked on VAN tasks;
- model regression automatically detected;
- replacement paths exist for critical providers;
- AI Evolution Radar produces evidence-backed candidate records;
- no new technology promoted without benchmark + security review;
- strategy-learning loop demonstrably improves at least three production mission classes;
- stable identity/authority layer remains unchanged across capability upgrades.

---

# 109. Symbiotic end-state architecture

\`\`\`text
                       OWNER
                         ⇅
               shared intent / feedback
                         ⇅
                VAN EXPERIENCE LAYER
          identity • voice • chat • missions
         attention • needs-you • understanding
                         |
                 SYMBIOTIC COGNITION
          +--------------+--------------+
          |              |              |
   Owner Cognitive   Critical        Strategic
       Model         Reasoning        Memory
          |              |              |
          +---------- Context ----------+
                         |
                      HERMES
                 sole agent runtime
                         |
                Mission / Plan / Critic
                         |
                 Capability Router
                         |
                     GATEWAY
       authority • truth • evidence • state
                         |
       modular specialist execution fabric
   VEKL • Browser • Google • n8n • Temporal
        DDE workers • computer use • VATI
                         |
                 External Reality
                         |
                 AI Evolution Radar
\`\`\`

The **Owner Cognitive Model** ensures continuity with the owner.

The **External Reality Model** prevents the partnership from becoming an echo chamber.

The **Critical Reasoning Kernel** reconciles the two.

The **AI Evolution Radar** prevents the implementation from freezing in the technology assumptions of 2026.

---

# 110. Final symbiosis doctrine

The intended relationship can be described metaphorically as a deeply integrated symbiotic pair:

- VAN knows the owner's world;
- VAN carries context the owner should not need to repeat;
- VAN anticipates useful work;
- VAN acts as an extension of the owner's reach;
- VAN complements rather than duplicates the owner's cognition;
- VAN challenges the owner when reality disagrees;
- VAN learns from shared outcomes;
- VAN grows technically as the AI ecosystem changes;
- VAN remains governed, inspectable and correctable;
- owner agency remains intact.

The success criterion is not that VAN becomes indistinguishable from the owner.

The stronger criterion is:

> **VAN becomes the owner's persistent cognitive counterpart: aligned enough to act as an extension of the owner, independent enough to catch what the owner misses, and adaptive enough that the partnership becomes more capable over time.**

That is the target symbiosis.

