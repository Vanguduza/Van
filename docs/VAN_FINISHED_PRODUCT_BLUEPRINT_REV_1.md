# VAN Finished Product Blueprint — Rev 1

**Document purpose:** Canonical implementation blueprint for taking VAN from the current partially integrated `0.5.0-dev` system to a finished, fully functional, production-certifiable personal intelligence product.

**Repository:** `Vanguduza/Van`  
**Audit evidence baseline:** `dff38a030367e640c6621ea80dab794b2c5c55b7`  
**Remediation starting baseline:** `0b0efad0e63600a2f55597e448cd37b359d475a1`  
**Current version at blueprint creation:** `0.5.0-dev`  
**Source documents consolidated:** Whole-System Audit Rev 1, Remediation Programme Rev 1, Project Truth, Security Policy, Unified Intelligence work, visual authority, trading blueprints, external-gate documentation, current repository state, and the consolidated expert remediation plan.

**Revision note (2026-09-19):** consolidated into the repository with four corrections applied —
gate count reconciled to thirteen (0–12); the §15 parallelism graph rebuilt so it matches its own
prose and no longer serialises gates 6 through 12; §14 re-costed to 165–230 engineer-days to price
the mandatory reasoning kernel, maturity CI, layered CI and expanded operations scope; and §7.1
added to give every shared surface exactly one owning gate. The Gate 0 reasoning decision is now
bounded to four executable checks so it can be finished and tested.

---

## 1. Mission

Finish VAN as one coherent, context-aware, critically reasoning, continuously improving personal intelligence whose user-facing experience, execution, memory, evidence, voice, visual state and delegated tool use behave as one system.

The finished product must not merely contain implemented modules. It must prove that those modules are connected, exercised, observable, fail-closed, evidence-backed and owner-visible where applicable.

This blueprint adopts the owner completion rule:

> **All findings matter. Nothing is deferred. Nothing is written off as acceptable debt. Nothing is closed by lowering its severity or by rewriting documentation to hide an intended capability.**

Dependency order determines **when** work happens. It does not determine **whether** it is completed.

---

## 2. Non-negotiable completion model

### 2.1 Maturity invariant

A shipping capability is not complete unless it has all applicable elements below:

1. **A real producer** of its inputs.
2. **A real consumer** of its outputs.
3. **An invoked production path**, not merely test construction.
4. **Deterministic authority and failure semantics.**
5. **Automated tests** at the correct layer.
6. **Runtime evidence** proving the production path.
7. **An owner-visible projection** where the capability affects owner experience.
8. **Degraded behavior** that tells the truth when dependencies fail.
9. **Observability** sufficient to trace the capability through the system.
10. **Canonical documentation** that matches the implementation.

No capability advertised as shipping may remain classified:

- `ABSENT`
- `STUB`
- `SIMULATED`
- `PARTIAL`
- `IMPLEMENTED_BUT_ISOLATED`

### 2.2 Engineering action vs completion state

Engineering work uses four dispositions:

| Engineering disposition | Meaning |
|---|---|
| **WIRE** | Sound implementation exists but lacks production producer/consumer wiring |
| **COMPLETE** | Genuine partial implementation must be finished |
| **REPLACE** | Current approach cannot satisfy the contract and must be replaced |
| **DELETE** | Redundant, superseded or non-canonical implementation must be removed |

These are **actions**, not terminal states.

Every capability or component must ultimately reach exactly one terminal state:

| Terminal state | Meaning |
|---|---|
| **INTEGRATED + EVIDENCED** | Fully functional, production-path invoked, tested and evidenced |
| **DELIBERATELY REMOVED + CANON CORRECTED** | Feature is not required; code, routing, tests and claims are removed coherently |
| **EXTERNALLY BLOCKED + REPOSITORY COMPLETE** | All repository-side work is finished and the remaining external gate is explicit, evidenced and owner-visible |

No fourth terminal state is allowed.

---

## 3. Current-system truth

VAN already has strong deterministic foundations:

- three-layer device authentication;
- owner approval for destructive actions;
- fail-closed payment prohibition;
- credential-plane separation;
- a deterministic trading order funnel;
- a real degraded-mode contract;
- mission, context, reasoning, owner-model, browser-policy and verification structures;
- a sophisticated visual state model;
- a substantial Android application;
- a large automated test suite.

The central defect is not that VAN is a collection of random features. The defect is that several architecturally sound layers are not load-bearing in the production path.

The current execution shape is approximately:

```text
owner input
  -> authenticated command
  -> authority checks
  -> Hermes dispatch
  -> accepted

then the durable model largely ends.
```

The finished shape must be:

```text
owner intent
  -> provenance classification
  -> durable mission
  -> context retrieval
  -> reasoning / interpretation
  -> plan
  -> deterministic authority
  -> execution
  -> externally observed verification
  -> durable outcome
  -> semantic state publication
  -> Android / voice / aura response
  -> evidence
  -> learning / owner-model update
```

That closed loop is the core of the finished VAN product.

---

## 4. Canonical target architecture

### 4.1 Owner experience layer

The owner interacts with one VAN through:

- floating bot;
- wake voice;
- command centre;
- trading centre;
- notifications;
- share-to-VAN;
- Google surfaces;
- needs-you approvals;
- mission history;
- project / browser / automation / development operations.

These are different **ingress and presentation surfaces**, not different intelligences.

### 4.2 Mission Core as system spine

Every owner-visible unit of work must create or bind to exactly one durable `mission_id`.

That mission becomes the parent identity for:

- `command_id`
- `hermes_run_id`
- `execution_id`
- `automation_run_id`
- `browser_task_id`
- `trade_decision_id`
- verifier receipts
- evidence references
- learning episodes
- semantic-state events
- owner-visible activities

No owner-visible work may exist only as an ephemeral HTTP response.

### 4.3 Deterministic authority layer

The deterministic gateway retains sole authority over:

- action classes;
- capability grants;
- approval requirements;
- project scope;
- execution ceilings;
- owner identity;
- payment refusal;
- trading risk;
- destructive-action approval;
- evidence requirements;
- mission lifecycle transitions.

Models may interpret, propose, reason and plan. They may not mint authority.

### 4.4 Hermes role

Hermes remains the sole agent runtime for model-driven work.

Hermes may:

- reason;
- call bounded tools;
- request approved actions;
- orchestrate research;
- run development tasks;
- use browser workers;
- produce evidence candidates.

Hermes may not:

- enroll owner devices;
- mint owner authority;
- self-approve;
- claim success without verification;
- bypass risk authority;
- turn untrusted content into owner instructions;
- write arbitrary owner-confirmed memories.

### 4.5 Semantic state bus

A typed event bus must carry owner-relevant system state from backend domains to Android.

Required event families:

- mission phase;
- listening / thinking / planning / executing / verifying;
- tool use;
- browser use;
- Google operation;
- project development operation;
- trading classification;
- risk rising / halt / degraded;
- needs-owner-attention;
- success / failure / timeout / conflict;
- connectivity degradation;
- verification state.

The aura, body state, voice behavior, command centre and notifications subscribe to this common state vocabulary.

### 4.6 Evidence and learning loop

Only verified outcomes can produce high-confidence learning.

```text
mission
 -> activities
 -> external effect
 -> verifier
 -> verified outcome
 -> episode
 -> owner feedback / correction
 -> model update candidate
 -> evidence threshold
 -> inspectable adaptation
```

---

## 5. Universal ingress invariant

All external content must obey one trust rule:

```text
external content
  -> DATA / CONTEXT ingress
  -> provenance
  -> trust classification
  -> interpretation
  -> optional owner confirmation
  -> separate authority transition
```

External content can never increase authority merely because it arrived on an owner device.

This applies equally to:

- notifications;
- shared text/images/files;
- email;
- web pages;
- browser DOM;
- search results;
- documents;
- Notebook content;
- Google content;
- VEKL knowledge;
- social content;
- broker/news feeds.

A cryptographic device signature proves **which device sent the envelope**. It does not prove the owner authored the embedded external text.

---

## 6. Product-wide finding and component ledgers

The implementation programme must maintain two complementary machine-readable ledgers.

### 6.1 Findings ledger

The audit’s 55 IDed findings must be extended to include the additional P3/P4 prose findings so that the whole register is countable.

Target: approximately 80 individually identified findings.

Each finding record must contain:

- ID;
- title;
- severity;
- canonical requirement;
- exact evidence;
- affected components;
- root cause;
- remediation wave;
- implementation tasks;
- test requirements;
- runtime-evidence requirement;
- terminal state;
- closure commit(s);
- certification artifact.

### 6.2 Component maturity ledger

The 70 known non-integrated components remain individually tracked.

Each component must record:

- current maturity class;
- WIRE / COMPLETE / REPLACE / DELETE disposition;
- canonical requirement;
- producer;
- consumer;
- production caller;
- tests;
- runtime evidence;
- owner-facing projection;
- final terminal state.

### 6.3 Bidirectional coverage

CI must verify both directions:

```text
requirement
 -> finding
 -> component
 -> remediation
 -> test
 -> evidence
 -> terminal state
```

and:

```text
component
 -> canonical requirement
 OR
 -> explicit DELETE justification
```

No orphan finding and no orphan partial implementation may remain.

---

## 7. Dependency-ordered programme

The programme is organized into thirteen gates, numbered 0 through 12. Work may run in parallel inside a
gate when dependency-safe, and several gates run in parallel with each other — see §15.

### 7.1 Single-owner rule for shared surfaces

Four surfaces are touched by more than one gate. Each has exactly one owning gate; every other gate
may only regression-check it. A gate that changes a surface it does not own is a merge blocker.

| Shared surface | Owning gate | Other gates may |
|---|---|---|
| Hermes MCP registration: include list, policy hook, skill counts, dead council bridge | **Gate 0** | Gate 7 regression-checks only |
| Mission-aware MCP tools, correlation propagation, Hermes result binding | **Gate 7** | Gate 3 defines the callback contract it consumes |
| Google capability inventory: which capabilities exist, are implemented, or are removed from routing | **Gate 4** | Gate 7 regression-checks only |
| Google credential planes, mutating-workflow readback contract, verification | **Gate 7** | Gate 4 consumes the contract, does not define it |

---

# GATE 0 — Truth, governance and maturity enforcement

## Objective

Make repository truth match implementation truth before product work continues.

## Required work

- Merge or supersede the relevant Unified Intelligence blueprint so implementation matrices do not point to non-canonical specifications.
- Correct all false `BUILT` / `INTEGRATED` claims.
- Correct Temporal claims.
- Correct voice claims.
- Correct visual-evidence revision claims.
- Correct Android README drift.
- Reconcile skill counts across config, installer, doctor, tests and attestation.
- Register all intended MCP tools **in the installer's include list** (mechanical drift fix only;
  mission-aware tool surfaces and correlation propagation belong to Gate 7 — see §7.1).
- Register and attest the Hermes policy hook.
- Delete redundant gateway council / `message_agent` bridge methods because councils are canonical on the Hermes side.
- Extend the findings register to include all P3/P4 items.
- Add the 70-component disposition ledger.
- Add maturity-gate CI.

## Temporal decision

Temporal is **not adopted by default**.

Canonical Rev 3 decision D9 makes it optional and requires measured need plus an owner-signed adoption decision.

Therefore the current implementation disposition is:

> **DELETE the dead Temporal routing/claims and make durable-routing behavior honest.**

Temporal may be reintroduced later only through the explicit owner-adoption mechanism.

## Reasoning decision

The Critical Reasoning Kernel is **not optional** for the finished VAN product.

It must be completed as a real reasoning pipeline rather than relabeled as a ledger.

**Bounded definition.** "Real reasoning" is otherwise an open-ended research goal and cannot be
finished or tested. For the purposes of closure, the critic pass is defined as these four executed
checks, each producing a finding the caller did not supply:

1. **Source existence** — every fact flagged `factual_authority` resolves to a retrievable evidence
   record. An unresolvable source is a finding, not a warning.
2. **Evidence supports claim** — the cited evidence is checked for relevance to the claim it is
   attached to, not merely for presence.
3. **Contradiction against retrieved context** — the claim set is checked against the facts sealed in
   the mission's context snapshot, and conflicts are surfaced with both sides retained.
4. **Confidence bounded by evidence** — stated confidence may not exceed a ceiling derived from the
   count and authority tier of supporting evidence.

An assessment that fails any check cannot be `is_actionable`. This is the closure bar; anything
beyond it is a later revision, not a blocker for Gate 4.

Cost: approximately 8–12 engineer-days, priced into §14.1.

## CI maturity enforcement

Any capability marked `INTEGRATED` must include machine-readable references to:

- producer;
- consumer;
- production entry point;
- tests;
- evidence;
- owner-facing projection where applicable.

CI fails if those references are missing or stale.

## Exit criterion

No canonical document describes an absent, stub, simulated, partial or isolated implementation as finished.

---

# GATE 1 — Security and authority containment

## Objective

Make it structurally impossible for untrusted input, weak credentials or replay to become owner authority.

## Notification and share boundary

Replace the current trust-laundering behavior.

Requirements:

- `CONTEXT_INGEST` is never replayed as an owner command.
- `VanGatewayClient` accepts explicit provenance/trust rather than hardcoding `CONVERSATION`.
- UI-origin payloads carrying untrusted markers are rejected server-side if they attempt command authority.
- notification and share payloads are data-only.
- owner action is required to elevate data into a command.
- every trust transition is audited.

## Internal credential split

Replace the static root-like internal token with scoped credentials.

At minimum separate:

- Hermes execution client;
- device-enrollment authority;
- automation worker;
- browser worker;
- trading commander;
- knowledge provider;
- administrative bootstrap.

Requirements:

- purpose bound;
- least privilege;
- short-lived where practical;
- rotation;
- revocation;
- auditable subject identity;
- Hermes cannot access enrollment authority.

## Replay and concurrency protection

- persistent command nonce table;
- nonce uniqueness enforcement;
- atomic idempotency claim;
- SQLite WAL;
- busy timeout;
- `BEGIN IMMEDIATE` or equivalent serialization around the claim;
- concurrency and crash tests.

## Authentication abuse controls

Add rate limiting / lockout for:

- pairing;
- ingress bearer;
- device bearer;
- approval challenge;
- public trading HMAC surfaces.

## Tamper-evident audit

Convert authority audit storage into an append-only verifiable chain:

- monotonic sequence;
- previous hash;
- entry hash;
- optional sealing/signature;
- verification command;
- tamper test.

## Biometric and signature hardening

- CryptoObject-bound biometric for trading credential/account changes;
- real registered-key verification for trading owner signatures;
- bind `requested_by` to authenticated identity;
- client strings never define principal identity.

## Credential lifecycle

Define expiry / renewal / rotation for:

- capability grants;
- ingress credentials;
- device HMAC secrets;
- commander credentials;
- VEKL credentials;
- bridge PKI;
- Google consent states where applicable.

## Production-only routes

Remove fake-transport/test mutation routes from production application assembly.

## Exit criterion

All authority-escalation probes fail closed, replay is refused, concurrent idempotency is safe and audit tampering is detectable.

---

# GATE 2 — Durable mission identity

## Objective

Give every owner-visible unit of work a durable existence.

## Command-to-mission binding

For every accepted owner command:

1. create mission;
2. seal authority envelope;
3. attach context snapshot identity;
4. generate initial activity;
5. route capability;
6. dispatch execution;
7. publish mission event.

## Critical bug fix

`CreateMissionBody` must accept and preserve the real authority envelope.

This closes the current A2-default ceiling problem that prevents legitimate A3 automation binding.

## Mission binder

Construct and inject `MissionBinder` in production `app.py`.

All domains capable of work must receive mission binding:

- automation;
- browser;
- Hermes;
- Google;
- trading;
- development;
- reminders;
- research.

## Owner-facing lifecycle

Collapse the eleven internal work-status vocabularies into one projection such as:

- RECEIVED
- UNDERSTANDING
- WAITING_FOR_OWNER
- QUEUED
- EXECUTING
- VERIFYING
- COMPLETED
- DEGRADED
- FAILED
- TIMED_OUT
- CONFLICTED
- CANCELLED

Domain-specific states remain internal details.

## Required APIs

- `GET /v1/commands/{command_id}`
- mission detail
- mission activities
- mission evidence
- mission verification
- mission events
- needs-you projection

## Android integration

Construct `MissionRepository`.

No unknown gateway state may silently map to `ACCEPTED`.

## Exit criterion

A canonical command produces a mission, activities, execution identity and owner-readable status that survive process restart.

---

# GATE 3 — Executable verification and result return

## Objective

Make “done” mean externally observed effect, never caller assertion.

## Verification authority

`MissionService.transition` must execute a registered verifier.

A client may provide:

- claimed result;
- evidence candidate;
- external identifier.

A client may not provide the final verification truth.

## Verifier Registry

Make `VerifierRegistry` the single canonical verification system.

Retire or fold parallel verification implementations into it.

Verifier types should include:

- Google readback;
- file / repository SHA verification;
- CI/workflow verification;
- browser DOM/external-site effect;
- reminder fire verification;
- Notebook readback;
- trading ledger verification;
- automation postcondition;
- system-state verification.

## Hermes callback binding

Persist:

- `hermes_run_id`;
- command/mission mapping;
- callback sequence;
- deadline;
- last evidence;
- terminal callback state.

Missing callback becomes truthful timeout, not silence.

## Automation observers

Supply real observer map to automation dispatch.

`UNVERIFIABLE` is acceptable when no verifier exists. False success is not.

## Trading signature verification

Replace all “non-empty string” owner-signature checks with cryptographic verification.

Apply across:

- mandate;
- halt;
- halt clear;
- capsule promotion;
- gateway trading mutation;
- all owner-authority trade operations.

## Parameter sealing

For A3/A4 operations, seal the complete action parameter set before approval/execution.

Hermes cannot choose or mutate authority-sensitive fields later, including arbitrary Notebook destination IDs.

## Exit criterion

Self-asserted success is rejected, real verifier evidence is accepted, missing result becomes timeout/degraded state, and Android receives the final outcome.

---

# GATE 4 — Context, memory, cognition and learning

## Objective

Turn the rich cognitive architecture into a real producer-consumer pipeline.

## Context writers

Add authoritative producers for:

- explicit owner facts;
- owner corrections;
- project truth;
- verified external observations;
- verified mission outcomes;
- conversation-derived low-authority context.

## Project Truth importer

Project Truth must populate the authoritative context tier automatically and preserve provenance.

## Command-path retrieval

Every command derives `ContextRequirements` from:

- project;
- intent;
- requested capability;
- entity references;
- continuity;
- safety/authority needs.

The sealed context snapshot records:

- fact IDs;
- evidence IDs;
- authority tier;
- hashes;
- revision;
- conflicts;
- stale markers;
- dropped items and reason.

## Taxonomy reconciliation

Use one canonical epistemic taxonomy.

Port useful behavior from duplicate taxonomies then delete the duplicates.

At minimum preserve:

- fact;
- inference;
- assumption;
- model-derived;
- owner-confirmed;
- evidence-derived;
- contradicted;
- stale.

## Critical Reasoning Kernel

Implement a real bounded reasoning pipeline:

```text
problem framing
 -> evidence retrieval
 -> candidate analysis
 -> critic pass
 -> source/evidence verification
 -> contradiction check
 -> uncertainty classification
 -> assumption ledger
 -> safe-for-action decision
```

Requirements:

- critic findings are generated, not caller-supplied;
- invented sources are rejected;
- confidence cannot outrun evidence;
- irreversible work invokes `assert_safe_for_irreversible_work`;
- assessment artifacts preserve provenance;
- reasoning remains advisory to deterministic authority.

## Owner model and symbiosis

Feed the owner model from real events:

- explicit corrections;
- accepted recommendations;
- rejected recommendations;
- recurring verified behavior;
- mission outcomes;
- owner overrides.

Distinguish:

- OWNER_CONFIRMED;
- EVIDENCE_DERIVED;
- TENTATIVE;
- REJECTED;
- REVOKED.

No arbitrary free-form episodes may become “owner-confirmed.”

## Learning

Wire verified mission outcomes into:

- strategy learning;
- decision fingerprints;
- cognitive complement map;
- shared vocabulary;
- symbiotic growth ledger;
- eval/benchmark systems.

Every adaptation must be:

- evidence-backed;
- inspectable;
- reversible;
- demotable;
- scoped;
- timestamped.

## Forget and retention

Add owner-facing controls for:

- owner-model entries;
- reasoning artifacts;
- evidence;
- learned preferences;
- strategic memory.

Add retention policies to every unbounded table.

## Google capability completion

**Ownership:** Gate 4 owns the *capability inventory* — which Google capabilities exist, which are
implemented, and which are removed from routing. Gate 7 owns the *credential and verification plane*
for those capabilities. Neither gate may change the other's surface; see §7.1.

Every selectable capability must be real or removed.

Implement or remove routing for registry-only capabilities.

Required useful paths include:

- Gmail draft creation;
- allowed send path;
- calendar read;
- event insert;
- reschedule;
- Drive search;
- contact resolve;
- task list;
- Notebook verified mutation;
- other declared integrations only when concrete.

Remove `workspace_studio` fallback while unimplemented.

## VEKL and knowledge

VEKL must have a real configured endpoint or report unavailable.

Obsidian and Exa should be wired only if their policy and deployment contracts are real.

## Exit criterion

A real owner command seals non-empty authoritative context, reasoning consumes that context, a verified outcome feeds learning, and the owner can inspect/revert the adaptation.

---

# GATE 5 — Trading production correctness

## Objective

Make trading safe, live-state-derived, restart-safe and symbiotically visible to VAN.

## Health authority

Replace hardcoded healthy flags with real state for:

- reconciliation;
- risk store;
- Tier-1 event blackout.

Reconciliation should update at the required live cadence.

## Halt semantics

Owner halt must be:

- synchronous or near-synchronous;
- durable;
- restart-safe;
- independent of session-start filtering;
- externally observable;
- auditable.

## Idempotency

Trade idempotency must survive:

- process restart;
- session restart;
- same-bar duplicate signal;
- network retry.

Use decision content and market/bar identity, not ephemeral session ID.

## Margin model

Add margin state and authority gates:

- free margin;
- used margin;
- margin level;
- projected margin impact;
- venue-specific requirements where needed.

No order proceeds without deterministic margin validation.

## Ledger truth

Gateway and trading runtime must read the same authoritative ledger.

If data is stale:

- reject current-state claims;
- surface staleness;
- never present old data as live.

## Live market feed

Replace file-only live session assumptions with an actual market feed contract.

Keep deterministic recording/replay for tests.

## Strategy targets

Preserve winning strategy targets through the real order path.

Delete dead/discarded target logic.

## Live learning

Learning may consume verified trade outcomes but may not bypass deterministic risk.

## Semantic trade state

Publish classified states such as:

- watching;
- setup forming;
- opportunity;
- risk rising;
- no trade;
- executing;
- protected;
- stop invalidation;
- halted;
- degraded.

These feed the common semantic state bus.

## Exit criterion

Demo/live-safe certification shows real reconciliation refusal, restart-safe halt, margin refusal, duplicate-order refusal, authoritative ledger visibility and semantic-state propagation to VAN.

---

# GATE 6 — Semantic experience and living VAN state

## Objective

Make execution state visible through one coherent VAN presence.

## Semantic event bus

Backend publishes typed events keyed by mission and correlation ID.

Android subscribes through a bounded resilient channel.

## Durable visual semantics

Extend state vocabulary for:

- interpreting;
- planning;
- researching;
- browser use;
- tool use;
- verifying;
- interrupted;
- needs owner;
- trading semantic states;
- degraded modes.

## Monotonic animation clock

Use one monotonic clock for the living visual runtime.

State changes must not restart time or produce snapping artifacts.

## Transition system

Blend aura/body semantic transitions over the canonical 120–420 ms envelope where appropriate.

## Aura geometry

Enforce:

- detached field;
- body-to-field gap ≥10 dp at the canonical floating size;
- non-ring topology;
- continuously moving windy/electrical field;
- semantic color/topology changes;
- body identity stability.

## Performance

- cache stable geometry;
- minimize per-frame allocations;
- add JankStats/Choreographer measurement;
- produce `frameBudgetMissed`;
- suspend animation when screen is off or lifecycle below active threshold;
- reduced-motion mode;
- low-power mode.

## Shared renderer

Preview and shipping rendering must use the same rendering implementation.

No second painter.

## Exit criterion

A real backend mission/trading event visibly changes VAN state on-device within the defined latency and performance envelope.

---

# GATE 7 — Hermes, Google and execution integration

## Objective

Make delegated intelligence and tool use complete, bounded and observable.

## Hermes MCP completeness

**Ownership:** the mechanical registration drift (include list, policy hook, skill counts, dead
council bridge) is closed in Gate 0. Gate 7 owns only what depends on the mission spine existing.

- expose mission-aware tools;
- propagate correlation IDs and mission IDs into every Hermes tool call;
- bind Hermes results back to the originating mission;
- verify at this gate that the Gate 0 registration fixes are still intact (regression check, not
  re-work).

## Snapshot authority

Resolve duplicate snapshot concepts.

Only one sealed authority artifact may authorize action.

## Google sovereignty

**Ownership:** Gate 7 owns credential planes, the mutating-workflow contract and verification.
The capability inventory itself was settled in Gate 4.

Maintain separate credential planes.

No master credential.

Each mutating workflow follows:

```text
resolve
 -> authority
 -> execute
 -> read back
 -> verify
 -> mission outcome
```

## Knowledge providers

Every provider is one of:

- real and configured;
- deliberately removed;
- explicitly unavailable.

No “configured-looking” dead adapter.

## Exit criterion

Hermes work returns evidence into the mission spine and every enabled Google/knowledge capability has a real owner-useful flow.

---

# GATE 8 — Browser, automation and computer-use substrates

## Objective

Turn the existing browser/automation contracts into real execution systems.

## Browser Harness

Deploy/vendor the deterministic browser worker behind the existing contract.

Responsibilities:

- deterministic navigation;
- DOM inspection;
- screenshots/evidence;
- bounded actions;
- replayable task traces.

## Stagehand

Deploy semantic browser worker behind the adapter contract.

Responsibilities:

- semantic interpretation;
- resilient element targeting;
- research/browser reasoning;
- evidence return.

## Task actuation

Browser task path must actually invoke an adapter.

`SubagentWorker` must bind state-machine work to real workers.

## Prompt-injection containment

The containment pipeline must be able to:

- classify suspected injection;
- escalate to confirmed;
- stop/quarantine task;
- preserve evidence;
- request owner intervention.

Recording `SUSPECTED` without enforcement is insufficient.

## External domains

Populate explicit allowed-domain policy.

Default-deny remains.

## Temporal

Remove dead Temporal routing unless owner formally adopts it later.

## Computer Interaction Fabric

Either fold its useful vocabulary into the real browser/computer-use worker or delete it.

Do not retain a BUILT claim around a non-executor.

## Automation/n8n

Use the self-hosted automation architecture already designed, with mission binding, scoped grants and verifier-backed outcomes.

## Exit criterion

A live browser task executes through the real worker, survives bounded failure, stops on confirmed injection and returns verifier-backed mission evidence.

---

# GATE 9 — Voice and owner interaction

## Objective

Make VAN a real always-available personal assistant rather than a tap-to-transcribe interface.

## Wake word

Implement a real local keyword spotter for:

> **Hey Van**

Requirements:

- local;
- low latency;
- measured false positives / negatives;
- background-compatible under Android restrictions.

## Local acknowledgement

Play the local acknowledgement immediately, before network dependence.

Target phrase should follow canonical owner preference.

## Foreground microphone architecture

Use the correct microphone foreground-service type and lifecycle.

## Speaker verification

Implement `SpeakerSimilarityScorer`.

Important:

- speaker verification is an identity/provenance signal;
- it does not replace deterministic authorization;
- destructive actions still use required owner approval/biometric mechanisms.

## ASR

Complete or delete the second-pass fusion path.

If retained, both first and second pass must be real.

## TTS

`TtsOutputManager.speak` must run only on verified/owner-safe outputs.

No success speech before verification.

## Barge-in and interruption

Support:

- user interruption;
- stop speaking;
- correction;
- reissue;
- continuation against same mission.

## Personal speech adaptation

Feed explicit correction capture into the speech model.

## Evidence references

Audio evidence references must resolve to real retrievable evidence or be removed from signed envelopes.

## Exit criterion

Voice journey:

```text
Hey Van
 -> local acknowledgement
 -> owner speech
 -> transcript
 -> mission
 -> execution
 -> verification
 -> spoken verified result
```

works on the owner device with measured latency.

---

# GATE 10 — Android product closure

## Objective

Make the S24 application a polished owner product and complete system projection.

## Share-to-VAN

Replace the unreachable `BroadcastReceiver` share target with an exported transparent `Activity`.

The share activity:

- accepts Android share intents;
- classifies content as untrusted DATA;
- creates context/mission ingress as appropriate;
- never directly mints owner-command authority;
- opens the correct VAN surface.

## Onboarding

First-run flow must complete:

- permissions;
- device enrollment;
- pairing;
- overlay;
- notifications;
- microphone;
- biometric;
- gateway connectivity;
- required Google consent where selected;
- final readiness check.

The owner must never land on a dashboard where everything simply fails because pairing was skipped.

## Command Centre

Replace the monolithic engineering-console activity with structured navigation over read models.

Required surfaces:

- Home / status;
- Missions;
- Needs You;
- Projects;
- Google;
- Trading;
- Automation;
- Browser / research;
- Memory / learning;
- Settings / security;
- diagnostics where owner-appropriate.

Use owner language, not raw internals.

Remove:

- raw enums;
- JSON blobs;
- `A4`;
- `HMAC`;
- truth hashes;
- developer command instructions.

## Accessibility

- semantic labels;
- minimum touch targets;
- scalable typography;
- content descriptions;
- screen-reader order;
- contrast testing;
- reduced motion.

## Responsive UI

Use adaptive layouts / window size.

## State restoration

Use ViewModels / `rememberSaveable` appropriately.

Rotation/background restore must not reset owner state.

## Themes

Support canonical dark experience and coherent light mode unless canon explicitly elects dark-only.

## Real health

Replace hardcoded healthy states with real signals for:

- overlay;
- queue;
- notifications;
- voice;
- biometric;
- gateway;
- trading;
- knowledge;
- Google;
- browser.

## Offline queue

Replay automatically on connectivity/gateway recovery.

No duplicate dispatch.

## Restore actions

Render the degraded contract’s actionable restore instruction.

## APK/device certification

CI must continue to:

- build;
- lint;
- unit test;
- verify signing;
- verify alignment;
- install on clean Android 16 emulator;
- launch package.

Physical Samsung acceptance remains a separate gate and must capture the real Package Manager result if installation fails.

## Exit criterion

First-run to daily-use owner journey works on the physical S24 without developer intervention.

---

# GATE 11 — Observability, reliability, operations and performance

## Objective

Make VAN operable as a production system rather than only testable in code.

## Correlation model

One correlation chain spans:

```text
owner input
 -> command
 -> mission
 -> Hermes run
 -> tool/browser/automation execution
 -> external effect
 -> verification
 -> outcome
 -> semantic event
 -> owner response
 -> learning episode
```

## Structured logging

Every production process emits structured logs with:

- timestamp;
- service;
- mission ID;
- command ID;
- correlation ID;
- action class;
- principal;
- result;
- degraded code;
- error class.

Never log secrets.

## Metrics

Export:

- gateway latency;
- mission duration;
- verifier latency;
- Hermes callback latency;
- queue depth;
- browser task status;
- automation status;
- trade halt latency;
- event-bus lag;
- wake latency;
- ASR latency;
- TTS latency;
- aura frame time;
- battery/memory indicators;
- error/degraded counts.

## Alerts

Add actionable alert thresholds for critical runtime failures.

## Backups and restore

Define:

- databases;
- configuration;
- evidence;
- project state;
- secrets metadata where appropriate.

Run actual restore drills.

## Retention

Every unbounded data store requires retention policy.

## PKI and credentials

Monitor expiry and renewal.

## Retry/backoff

No busy-loop or fixed aggressive retry.

Use bounded exponential backoff with jitter where appropriate.

Fix blocking sleeps in async paths.

## Scheduler ownership

`fire_due` and reminder/attention dispatch need a real scheduler.

## Code quality cleanup

Resolve god files and dead code where identified by the register.

Delete unused gateway methods if their intended consumer was removed; otherwise wire them.

## Exit criterion

A production operator can determine what VAN is doing, why it failed, recover it, restore its data and verify service health without reading SQLite manually.

---

# GATE 12 — Whole-system certification and release

## Objective

Prove the finished system rather than inferring completeness from code.

## 12.1 Required test architecture

Retain strong unit and contract tests, then add:

- Android instrumentation;
- screenshot/golden regression;
- share-sheet invocation test;
- onboarding E2E;
- mission lifecycle E2E;
- offline queue replay;
- restart recovery;
- voice E2E;
- Google live/sandbox tests;
- browser worker E2E;
- automation verifier E2E;
- trading demo-account fault injection;
- semantic-state/aura integration;
- device performance tests;
- backup/restore drill;
- security adversarial probes.

Source-text grep tests cannot count as runtime certification.

## 12.2 Canonical command certification

Each canonical command records:

- owner input;
- parsed intent;
- context used;
- reasoning artifact;
- plan;
- authority;
- execution route;
- external side effect;
- independent verification;
- mission outcome;
- owner-visible response;
- learning effect where applicable.

Representative commands include:

1. reminder creation and actual firing;
2. calendar query verified against Google;
3. Notebook mutation verified by readback;
4. deep research stored with evidence;
5. browser task with external-site confirmation;
6. Hermes development mission producing commit/CI evidence;
7. build investigation tied to real CI evidence;
8. trading halt surviving restart;
9. trading dashboard matching live authoritative ledger;
10. destructive production-database request refused and audited.

## 12.3 Critical reasoning certification

Test VAN against:

- incomplete evidence;
- conflicting evidence;
- stale evidence;
- misleading evidence;
- unsupported owner premise;
- ambiguity;
- uncertainty;
- contradictory sources.

Pass criteria:

- distinguishes fact/inference/assumption;
- cites evidence;
- identifies uncertainty;
- detects conflict;
- asks for evidence when needed;
- revises on new evidence;
- refuses unsupported irreversible conclusions.

## 12.4 Aura / living-presence certification

On physical device:

- 30-second idle recording;
- continuous field motion;
- no ring collapse;
- state transition timing;
- grayscale distinguishability;
- warning/error distinction;
- trading semantic-state reaction;
- ≥10 dp gap;
- 10-minute frame-time run;
- memory/battery capture;
- screen-off suspension;
- reduced-motion/low-power behavior;
- all durable-state golden captures.

## 12.5 Security re-audit

Repeat all authority-boundary probes.

Run an independent security review over:

- credential split;
- ingress trust;
- mission authority;
- verification;
- trading signatures;
- nonce/idempotency;
- audit chain;
- browser injection.

## 12.6 Device acceptance

Owner-device acceptance must include:

- install;
- onboarding;
- permissions;
- overlay;
- wake voice;
- mission execution;
- degraded behavior;
- Google;
- trading;
- browser;
- notifications;
- share;
- restart;
- battery/performance.

## 12.7 Release conditions

Release may proceed only when:

- all register findings are CLOSED;
- all 70 component dispositions are executed;
- maturity CI passes;
- no shipping capability remains partial/stub/simulated/isolated;
- applicable external gates have evidence;
- whole-system audit is rerun from scratch;
- Project Truth, implementation matrix and evidence agree;
- SBOM/provenance are regenerated;
- production signing is valid;
- version advances beyond `0.5.0-dev`;
- release block is deliberately re-evaluated rather than silently removed.

---

## 8. Component-disposition rules

The detailed 70-component inventory from the remediation programme remains authoritative input to execution.

The most important locked dispositions are:

### DELETE

- dead gateway `message_agent` / council bridge;
- duplicate epistemic taxonomy after useful behavior is ported;
- redundant context compiler after useful behavior is ported;
- Temporal routing without owner adoption;
- cold-tier pattern source until a real source exists;
- unexecuted computer-use facade if its vocabulary is folded into real browser workers;
- unimplemented Google fallback entries;
- any stale/dead client method whose intended capability has been removed.

### REPLACE

- non-empty-string owner signatures;
- unreachable share receiver;
- trust-laundering context dispatch;
- monolithic engineering-console Command Centre where necessary.

### WIRE

- MissionService;
- MissionBinder;
- MissionRepository;
- VerifierRegistry;
- automation observers;
- ContextRetrievalService;
- owner-model/learning stores;
- wake runtime;
- TTS;
- notification policy controls;
- live learning;
- real knowledge providers.

### COMPLETE

- Critical Reasoning Kernel;
- wake word;
- speaker scoring;
- browser workers;
- injection containment;
- trading margin;
- live market feed;
- visual transitions;
- state bus;
- observability;
- Android onboarding;
- physical/device certification.

---

## 9. Branching and implementation strategy

### 9.1 Repository-first execution

Every wave begins by checking current `main`, Project Truth and the closure ledger.

Do not implement from conversation memory when repository state differs.

### 9.2 Branch model

Use one bounded branch per closure package.

Examples:

- `closure/g0-truth-maturity`
- `closure/g1-authority-containment`
- `closure/g2-mission-spine`
- `closure/g3-verification`
- `closure/g4-context-cognition`
- `closure/g5-trading`
- `closure/g6-semantic-state`
- `closure/g8-browser`
- `closure/g9-voice`
- `closure/g10-android-product`

Parallel branches may exist only where the dependency DAG allows.

### 9.3 Lead-agent responsibility

The strongest available orchestration model owns:

- canonical architecture;
- reconciliation;
- security policy;
- Project Truth;
- final testing;
- merge acceptance.

Subagents may execute bounded worktrees but may not independently redefine canonical architecture or truth.

### 9.4 Merge rule

A wave package merges only when:

- implementation complete;
- targeted tests green;
- full relevant regression suites green;
- maturity metadata updated;
- closure ledger updated;
- runtime evidence attached where possible;
- no new partial surface introduced.

---

## 10. CI architecture for finished VAN

CI should become layered.

### Layer A — Static truth and policy

- canonical document references valid;
- capability ledger schema valid;
- every INTEGRATED capability has producer/consumer/caller/test/evidence refs;
- no unassigned finding;
- no undisposed non-integrated component;
- MCP/skill registries consistent;
- forbidden security routes absent.

### Layer B — Unit / contract

- backend;
- trading;
- Android JVM;
- authority;
- context;
- reasoning;
- mission;
- verification;
- browser policy;
- Google.

### Layer C — Integration

- real in-process gateway;
- mission lifecycle;
- verification execution;
- event bus;
- semantic-state mapping;
- PostgreSQL trading ledger;
- n8n integration;
- local browser-worker integration.

### Layer D — Android

- assemble;
- lint;
- signing;
- zip alignment;
- emulator install;
- launch;
- instrumentation;
- screenshots;
- accessibility.

### Layer E — Security probes

- untrusted notification attack;
- nonce replay;
- concurrent idempotency;
- token scope;
- owner signature invalidation;
- audit-chain tamper;
- injection containment.

### Layer F — Certification jobs

Run where credentials/environments are available:

- Google;
- Browser Harness;
- Stagehand;
- trading demo account;
- physical-device capture;
- backup restore.

---

## 11. Evidence layout

Use a stable evidence tree:

```text
evidence/
  closure/
    register/
    g0-truth/
    g1-security/
    g2-missions/
    g3-verification/
    g4-context-cognition/
    g5-trading/
    g6-semantic-state/
    g7-hermes-google/
    g8-browser-automation/
    g9-voice/
    g10-android/
    g11-operations/
    g12-certification/
```

Every closure item should point to an immutable evidence artifact.

Evidence may include:

- JSON probe output;
- signed/hash-chained records;
- screenshots;
- screen recordings;
- test reports;
- benchmark output;
- APK hashes;
- CI run IDs;
- external object IDs;
- ledger hashes;
- restore drill reports.

---

## 12. Runtime invariants of finished VAN

The product is not finished unless all of these statements are true.

### Authority

- Untrusted content never becomes owner authority by transport accident.
- Models cannot mint, extend or lower authority.
- A4 actions require the correct owner approval.
- Owner signatures are cryptographically verified.
- Replay is rejected.

### Work identity

- Every owner-visible task has one durable mission.
- Every execution belongs to a mission.
- Every result returns to the mission.
- Every mission is owner-visible.

### Verification

- No engine can self-certify success.
- Missing verification is visible as missing.
- Timeout is truthful.
- External effects are independently verified where possible.

### Context

- Commands receive real context.
- Context provenance is inspectable.
- Stale/conflicting context is distinguished.
- Project isolation holds.

### Reasoning

- Critic/verifier work is actually executed.
- Confidence is evidence-bounded.
- Assumptions cannot silently authorize irreversible work.

### Learning

- Learning consumes verified outcomes.
- Owner-confirmed and inferred preferences are distinct.
- Adaptations are reversible.

### Trading

- Risk remains deterministic.
- Owner authority is real.
- Halt survives restart.
- stale data is never shown as live.
- margin is enforced.
- trading state reaches VAN presence.

### Experience

- backend state, Android UI, voice and aura tell the same story.
- no surface claims completion before verification.
- degraded state is explicit.

### Reliability

- work survives restart where required.
- retries are bounded.
- backups restore.
- credentials rotate.
- system health is observable.

---

## 13. Performance targets

Targets should be validated and refined with device evidence.

Initial acceptance targets:

- wake acknowledgement P95: <250 ms on owner device;
- semantic-state visual reaction: <500 ms after event receipt;
- floating animation P95 frame time: <16.7 ms at 60 Hz target;
- no unbounded per-frame allocation growth;
- owner halt: <1 second end-to-end under normal healthy network;
- command lifecycle state update: near-real-time bounded event delivery;
- no uncontrolled polling loops;
- screen-off animation suspended;
- no battery behavior materially worse than the defined product budget.

---

## 14. Estimated implementation scale

### 14.1 Revised estimate

The Remediation Programme Rev 1 estimate of **129–186 engineer-days** predates this blueprint and is
now low. It did not price four things this document adds:

| Added scope | Delta (engineer-days) |
|---|---:|
| Critical Reasoning Kernel as a real pipeline rather than a ledger (§7 Gate 0 decision) | +8 to +12 |
| Maturity-gate CI, two machine-readable ledgers, bidirectional coverage (§6) | +5 to +8 |
| Layered CI architecture, Layers A–F (§10) | +8 to +14 |
| Expanded Gate 11 scope: metrics export, alerting, restore drills, credential lifecycle | +10 to +15 |
| Deleted from scope: Temporal implementation (D9, not adopted) | −15 to −20 |

**Revised planning figures:**

- total programme: approximately **165–230 engineer-days**;
- critical path: approximately **85–120 engineer-days**.

### 14.2 Wall-clock expectation

- **3 strong engineers** split backend / Android / trading: approximately **12–18 weeks**, assuming
  environments and credentials are available when their gate needs them.
- **1 engineer:** approximately **8–11 months**, and the dependency order matters far more.

Credential and environment availability is the most common source of slip: Gate 5 needs a demo
trading account, Gate 7 needs live Google consent, Gate 8 needs the browser host, Gate 10 and Gate 12
need the physical S24. Those should be requested at Gate 0, not at the gate that consumes them.

### 14.3 Estimate discipline

These are planning ranges produced by an auditor who has read the code but not written it. They are
not a bid. Two rules apply:

1. No schedule may be used to justify leaving a finding open.
2. If a gate overruns its range by more than 50%, the overrun is itself reported at the gate review
   (Appendix B question 15) rather than absorbed silently into the next gate.

---

## 15. Recommended execution parallelism

The dependency graph, not the gate numbering, determines what may run when. Gate numbers are labels.
Several gates run concurrently, and the diagram below is authoritative over any reading of the
numbering as a sequence.

```text
GATE 0  Truth, governance, maturity enforcement
   │      (blocks everything — nothing else may start)
   ├──────────────────────────────┐
   ▼                              ▼
GATE 1  Security containment   GATE 2  Mission identity
   │   (independent of 2)         │
   │                              ▼
   │                        GATE 3  Verification
   │                              │
   │        ┌─────────────────────┼─────────────────────┐
   │        ▼                     ▼                     ▼
   │   GATE 4  Context      GATE 5  Trading       GATE 6  Semantic state
   │   & cognition          correctness           (needs only Gate 2)
   │        │                     │                     │
   │        │                     │          ┌──────────┴──────────┐
   │        ▼                     │          ▼                     ▼
   │   GATE 7  Hermes,            │    GATE 9  Voice        GATE 10  Android
   │   Google, execution          │          │              product closure
   │        │                     │          │                     │
   │        ▼                     │          │                     │
   │   GATE 8  Browser,           │          │                     │
   │   automation substrates      │          │                     │
   │        │                     │          │                     │
   └────────┴─────────────────────┴──────────┴─────────────────────┤
                                                                    ▼
                                              GATE 11  Observability, operations
                                                                    │
                                                                    ▼
                                              GATE 12  Whole-system certification
```

### 15.1 What actually runs in parallel

| Concurrent set | Precondition | Why they do not block each other |
|---|---|---|
| Gate 1 ‖ Gate 2 | Gate 0 | Security containment touches auth, ingress and storage; mission identity touches the orchestrator and mission core. Disjoint surfaces |
| Gate 4 ‖ Gate 5 ‖ Gate 6 | Gate 3 for 4 and 5; **Gate 2 only** for 6 | Cognition, trading and the semantic bus share no files. Gate 6 needs mission state to publish, nothing more |
| Gate 9 ‖ Gate 10 | Gate 6 | Voice and Android UX both consume the semantic bus and the mission read models, in different modules |
| Gate 7 → Gate 8 | Gate 4 | Hermes/Google integration precedes browser substrates because the knowledge providers are the substrates' first consumer |

### 15.2 Corrections to a naive reading of the numbering

Three sequencing errors are easy to introduce and are explicitly rejected here:

1. **Gate 6 does not wait for Gate 8.** The semantic state bus depends only on mission identity.
   Trading classification already exists inside `trading/`; it simply never propagates. Parking the
   aura and trading-state work behind browser-worker construction — the longest single item in the
   programme — would extend the critical path for no dependency reason.
2. **Speaker verification is Gate 9, not Gate 1.** It is an identity and provenance signal that
   requires the completed voice stack. It cannot be delivered with the authority containment work,
   and it never substitutes for deterministic authorization.
3. **Android product closure starts progressively but lands after Gate 6.** Screens may be built
   against the mission read-model contracts as soon as Gate 2 defines them; the final owner surfaces
   must consume the stable semantic-state contract from Gate 6.

### 15.3 Critical path

```text
GATE 0 → GATE 2 → GATE 3 → GATE 4 → GATE 7 → GATE 8 → GATE 11 → GATE 12
```

Everything else has slack against this path. Gate 8 (browser and automation substrates) is the
longest single gate and sits on the critical path; if delivery date is the binding constraint, that
is the gate to staff first and the one whose vendor-versus-build decision matters most.

---

## 16. Anti-regression rules

These rules are permanent.

1. **No fake implementation on a production path.**
2. **No registry entry without a real capability or explicit unavailable state.**
3. **No BUILT claim without maturity metadata.**
4. **No self-asserted verification.**
5. **No external content authority promotion.**
6. **No duplicate canonical taxonomy.**
7. **No duplicate verification system.**
8. **No duplicate owner work-status vocabulary.**
9. **No dead routing branch pretending an executor exists.**
10. **No owner-visible optimistic success.**
11. **No unbounded credential.**
12. **No production feature without failure semantics.**
13. **No external dependency represented as healthy without evidence.**
14. **No evidence renderer that differs from shipping code.**
15. **No release based only on test counts.**

---

## 17. Finished-product acceptance statement

VAN may be called a **finished fully functional product** only when all of the following are simultaneously true:

- every expanded audit finding is closed;
- every non-integrated component has reached a terminal state;
- every intended capability passes the maturity invariant;
- notification/share/browser/external data can never become owner authority implicitly;
- every owner request has durable mission identity;
- results return and are independently verified;
- context contains real owner/project knowledge;
- the reasoning kernel executes real critic/evidence/uncertainty logic;
- owner learning is evidence-backed and reversible;
- trading safety is cryptographic, live-state-driven and restart-safe;
- trading and mission semantics reach VAN’s living visual state;
- Browser Harness and Stagehand execute real tasks;
- enabled Google/knowledge integrations perform real useful workflows;
- wake voice, acknowledgement, ASR, TTS and barge-in work on-device;
- Android onboarding, share, mission, needs-you, trading and degraded flows are functional;
- observability, backup, retention, credential lifecycle and recovery are operational;
- emulator and physical-device acceptance pass;
- live certification gates pass;
- the whole-system audit is rerun from scratch;
- Project Truth, implementation ledger and runtime evidence agree;
- production release signing/provenance/SBOM are valid;
- the explicit release block can be removed based on evidence rather than assertion.

At that point VAN is not merely a secure command gateway with advanced modules around it.

It is one coherent personal intelligence:

```text
one owner
one authority model
one mission spine
one context system
one verification truth
one semantic state
one owner-facing lifecycle
many bounded execution estates
```

That is the production architecture this blueprint is designed to deliver.

---

# Appendix A — Required closure artifacts per gate

| Gate | Minimum closure artifact |
|---|---|
| 0 | Truth/maturity CI report + complete ledgers |
| 1 | Authority-boundary adversarial probe report |
| 2 | Command→mission→activity trace |
| 3 | Self-asserted verification rejection + real verifier acceptance |
| 4 | Context-bearing command + real reasoning + reversible learning evidence |
| 5 | Demo-account trading safety certification |
| 6 | Physical-device semantic/aura capture |
| 7 | Hermes/Google mission-return trace |
| 8 | Browser/Stagehand real execution with injection canary |
| 9 | Wake→verified spoken-result device recording |
| 10 | Full Android owner-journey instrumentation/device report |
| 11 | Observability dashboard + restore drill + credential renewal evidence |
| 12 | Whole-system audit rerun + signed production acceptance ledger |

---

# Appendix B — Gate closure review template

Every gate review must answer:

1. What canonical requirements were addressed?
2. Which findings were closed?
3. Which components changed maturity?
4. Which code was deleted?
5. Which production paths now invoke the capability?
6. What tests prove it?
7. What runtime evidence proves it?
8. What failure/degraded behavior was exercised?
9. What owner-visible behavior changed?
10. What security boundaries were rechecked?
11. What new partial/stub surfaces were introduced?
12. Is Project Truth updated?
13. Is the maturity ledger updated?
14. Is every terminal-state claim justified?
15. Can the next dependent gate safely begin?

A gate may not close when question 11 reveals a new undocumented partial implementation.

---

# Appendix C — Release-block rule

`PROJECT_CANONICAL_STATE.json` release blocking must remain in force until Gate 12 passes.

Neither a green CI run, a large passing-test count, a successful APK build, nor a successful single external integration is sufficient to remove the block.

The release decision is an evidence aggregation decision over the whole system.
