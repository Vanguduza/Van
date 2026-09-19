# VAN Consolidated Deployment-Readiness Closure Blueprint — Rev 1

**Repository:** `Vanguduza/Van`  
**Implementation baseline:** `claude/van-system-audit-ysgtcd`  
**Purpose:** Consolidate the independent ChatGPT audit, the Opus whole-system audit/remediation work, the Independent Audit Brief, and the canonical VAN product architecture into one engineering authority for taking VAN from its current `0.5.0-dev` state to deployment readiness.

**Primary completion doctrine:**  
**Unified at the experience and cognition layer; modular and strictly bounded at the execution layer.**

**Status:** Engineering closure blueprint. This document does not itself certify production readiness. Production readiness exists only when every applicable exit gate below has machine-readable evidence and the owner acceptance journeys pass against the real deployed system.

---

# 0. Executive engineering conclusion

VAN already contains a substantial amount of real engineering: Android surfaces, a deterministic authority gateway, mission and verification structures, VATI risk/execution components, Google capability abstractions, browser/automation contracts, cognition modules, visual-state logic, security controls, and a large test corpus.

The dominant remaining problem is not simply missing source files.

The dominant problem is that several sophisticated components are either:

1. not compiled in the real Android application;
2. not constructed in production;
3. not reachable from an owner action;
4. not connected to a real external runtime;
5. not causally joined to a durable mission;
6. not verified after external side effects;
7. not projected truthfully to the owner;
8. not bounded by one canonical authority model;
9. not exercised under process death, network failure, replay, partial provider success, or dependency degradation;
10. or not evidenced on the target Samsung device and production hosts.

The deployment-readiness programme must therefore close **five distinct classes of incompleteness**:

```text
SOURCE EXISTS
    ↓
BUILDS
    ↓
IS WIRED
    ↓
IS CAUSALLY INTEGRATED
    ↓
IS LIVE-DEPENDENCY VERIFIED
    ↓
IS OWNER-ACCEPTED
```

A capability is shipping only after it reaches the final relevant stage.

---

# 1. Authority and evidence model for this closure programme

## 1.1 Baseline rule

For implementation truth, use:

1. source code on `claude/van-system-audit-ysgtcd`;
2. executable tests;
3. runtime evidence;
4. target-device evidence;
5. live-dependency evidence.

Documents describe intended behaviour, but a document is never proof that code executes.

## 1.2 Locked authorities

The following remain above this blueprint where applicable:

- `docs/SECURITY_POLICY.md`
- `docs/PROJECT_TRUTH_PROTOCOL.md`
- `PROJECT_CANONICAL_STATE.json`
- `hermes/profile/van/SOUL.md`
- `hermes/profile/van/AGENTS.md`
- `visual-authority/rive_contract.json`
- owner-signed decisions and explicit Project Truth records

This blueprint must not silently weaken those authorities.

## 1.3 Corrected voice finding

The previous claim that the current Android recognizer may silently use generic/cloud speech recognition is **not valid for the Claude audit branch**.

Current branch behaviour:

- uses `SpeechRecognizer.createOnDeviceSpeechRecognizer()` only when Android on-device recognition is available;
- has no generic `createSpeechRecognizer()` fallback;
- sets `RecognizerIntent.EXTRA_PREFER_OFFLINE = true`;
- returns `ERROR_SHERPA_PRIMARY_REQUIRED` where policy requires Sherpa.

The real closure defect is:

> **The capability policy declares a Sherpa-primary compatibility path, but the Android application currently has no Sherpa ASR dependency/runtime/model asset.**

This must replace the stale cloud-recognizer defect in the consolidated findings register.

---

# 2. Final product invariants

## 2.1 One VAN

The owner interacts with one intelligence.

The following are surfaces or subordinate runtimes, not independent VANs:

- Android overlay;
- Command Centre;
- voice;
- notifications;
- share-to-VAN;
- trading screens;
- Hermes;
- Google providers;
- Stagehand;
- Browser Harness;
- n8n;
- VATI;
- VEKL / Notebook / knowledge providers.

They may have distinct execution contracts, but the owner must perceive one continuous system identity, one mission history, one attention model, one cognition context, and one truthful status model.

## 2.2 Models never mint authority

Models may interpret, reason, propose, plan, retrieve, summarize, research, generate candidate actions, and select among already permitted bounded tools.

Models may not:

- promote an action class;
- self-approve;
- mint grants;
- widen a standing authority;
- weaken VATI risk controls;
- convert untrusted content into owner intent;
- elevate learned behaviour into greater authority;
- mark an effect verified without a verifier.

## 2.3 Every owner action has one causal identity

Every meaningful owner request must be represented by a durable causal chain.

```text
owner_intent_id
  └─ mission_id
      ├─ turn_id
      ├─ command_id
      ├─ command_authority_id
      ├─ context_snapshot_id
      ├─ execution_id(s)
      │   ├─ hermes_run_id
      │   ├─ browser_task_id
      │   ├─ automation_run_id
      │   ├─ google_job_id
      │   └─ trade_decision_id
      ├─ evidence_ref(s)
      ├─ verification_id(s)
      ├─ outcome_id
      └─ learning_episode_id(s)
```

All retries, callbacks, provider receipts, Android status updates, browser checkpoints, n8n runs and VATI effects must preserve this causal lineage.

## 2.4 No false completion

A successful HTTP response, queued job, browser click, n8n execution, Hermes response, Google API acceptance, or broker submission is not automatically task success.

Canonical effect ladder:

```text
UNDERSTOOD
PLANNED
AUTHORIZED
SUBMITTED
OBSERVED
VERIFIED_SUCCESS
VERIFIED_FAILURE
UNVERIFIABLE
TIMED_OUT
CONFLICTED
CANCELLED
```

If a verifier does not exist, the status ceiling is `UNVERIFIABLE` or the last truthful non-terminal state. It must never be promoted to `VERIFIED_SUCCESS`.

## 2.5 Learning cannot increase authority

Learning may change ranking, context retrieval, phrasing, timing, workflow preference, strategy confidence, prediction, and personalization.

Learning may **not** change:

- A1–A5 classification;
- approval requirement;
- payment policy;
- broker sender authority;
- Project Truth authority;
- credential privileges;
- maximum browser action class;
- n8n standing-authority scope;
- destructive-action policy.

The mapping `action/effect → authority class → required gate` is policy/owner data and is never a learned parameter.

## 2.6 Untrusted information never becomes owner authority

Notification content, email, Drive content, web pages, browser DOM, Notebook sources, Google provider output, VEKL research, shared files, messages from external systems, market/news feeds and model-generated summaries begin as untrusted evidence.

They cannot directly become owner instructions, `OWNER_CONFIRMED` facts, authority-expanding preferences, owner-pinned speech corrections, Project Truth, or widened execution policy.

---

# 3. Maturity model

## 3.1 Component maturity classes

Use:

- `ABSENT`
- `STUB`
- `SIMULATED`
- `PARTIAL`
- `IMPLEMENTED_BUT_ISOLATED`
- `NO_CONSTRUCTOR`
- `NO_CALLER`
- `NO_ROUTE`
- `NO_PRODUCER`
- `NO_CONSUMER`
- `TEST_ONLY`
- `REGISTRY_ONLY`
- `READ_ONLY`
- `WRITE_ONLY`
- `INTEGRATED`
- `CAUSALLY_INTEGRATED`
- `E2E_VERIFIED`

## 3.2 New class: CAUSALLY_INTEGRATED

A component is `CAUSALLY_INTEGRATED` only when:

1. its production entry point is real;
2. its inputs preserve authenticated owner/mission provenance;
3. its outputs preserve the same mission identity;
4. authority information is not lost or recomputed incorrectly;
5. retries remain idempotent;
6. externally created IDs/evidence are attached to the mission;
7. the owner-visible result is derived from the same state.

## 3.3 Terminal deployment states

For shipping capabilities, only:

- `E2E_VERIFIED`
- `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` — permitted only before deployment acceptance
- `DELIBERATELY_REMOVED_CANON_CORRECTED`

At final deployment readiness, applicable v1 functionality must be `E2E_VERIFIED`.

---

# 4. Programme structure

The programme is organized into 15 gates.

```text
Gate 0  — Canonical baseline and audit reconciliation
Gate 1  — Real Android buildability
Gate 2  — Component reachability and production wiring
Gate 3  — Universal mission/causality spine
Gate 4  — Authority convergence and security closure
Gate 5  — Verification/outcome truth
Gate 6  — Cognition and owner-understanding activation
Gate 7  — Voice completion and device audio architecture
Gate 8  — Embodiment, aura and semantic-state truth
Gate 9  — Google intelligence mesh production closure
Gate 10 — Browser + automation runtime deployment
Gate 11 — VATI/trading deployment closure
Gate 12 — Resource, recovery and degraded-mode engineering
Gate 13 — Observability, evidence, CI and operations
Gate 14 — Physical-device + live-system E2E certification
```

A later gate may be developed in parallel where dependency-safe, but it cannot be accepted before all prerequisite gates are green.

---

# 5. Gate 0 — Canonical baseline and audit reconciliation

## Objective

Create one authoritative implementation baseline and eliminate contradictory audit state.

## Required implementation

### 5.1 Freeze the closure baseline

Create `release/van-deployment-readiness` from the approved reconciled branch after owner review of the Claude audit branch.

Record repository, baseline branch, baseline SHA, creation time and owner authority.

No remediation may proceed against `main` while relying on branch-only fixes.

### 5.2 Reconcile audit registers

Generate `evidence/closure/CONSOLIDATED_FINDINGS.json`.

Every finding needs source, source IDs, title, severity, status, paths, disposition, dependencies, acceptance test, runtime-evidence requirement and terminal state.

Explicitly:

- withdraw the stale cloud-ASR finding;
- add the missing Sherpa-primary implementation finding;
- add the universal mission-causality invariant;
- add learning-authority immutability;
- add whole-runtime resource envelope;
- add Owner Context Graph lifecycle;
- add Google credential-plane degradation;
- add recovery matrix;
- add machine-checkable document authority mapping.

### 5.3 Reconcile component ledger

The previous finding count is not a completion metric.

All inventoried components must be terminal.

CI must fail if any component remains WIRE without closure, stale duplicate, non-terminal, or referenced only by a superseded finding.

### 5.4 Machine-checkable authority map

Create `docs/project-state/AUTHORITY_MAP.yaml`.

CI requirements:

- every locked invariant has implementation/test references;
- no two documents claim equal canonical ownership for the same invariant without precedence;
- SHA-pinned documents are checked byte-for-byte.

## Exit gate

- one baseline SHA;
- one reconciled finding ledger;
- one component ledger;
- zero stale duplicate rows;
- authority map passes CI.

---

# 6. Gate 1 — Real Android buildability

## Objective

Stop treating partial JVM compilation as evidence that the Android product builds.

## Required implementation

Run the real app build:

```bash
cd android
./gradlew clean
./gradlew :app:compileDebugKotlin
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug
./gradlew :app:lintDebug
```

Then validate the release variant with a valid test/release signing configuration.

Resolve all failures involving Compose imports, delegated state imports, manifest references, resources, navigation routes, lifecycle APIs, API-level guards, Rive runtime calls, foreground service declarations, serialization contracts, build variants and R8 rules.

Create `android/app/src/androidTest/` with smoke tests for onboarding, Command Centre, overlay permission, overlay service, biometric path, notification-listener settings, trading navigation and state restoration.

The real Android app build must run in CI. The JVM verification harness remains useful but is not a substitute.

## Exit gate

- debug app compiles;
- debug APK installs on emulator;
- release variant builds;
- lint passes;
- Android instrumented smoke suite passes.

---

# 7. Gate 2 — Component reachability and production wiring

## Objective

Eliminate “implemented but never runs.”

Priority components include:

### Cognition / understanding / evolution

`ContextCompiler`, `ContextPacket`, epistemic structures, promotion guard, admission outcome/verdict, shared vocabulary, cognitive complement mapping, `SymbioticGrowthLedger`, `IntentContinuityGraph`, `StrategicMemory`, `DecisionFingerprints`, `ExternalRealityModel`, `BenchmarkHarness`, `StrategyLearning`, `AIEvolutionRadar`, `VanEval`, `ContextRetrievalService`, `CriticalReasoningKernel.assess`, relationship calibration.

### Verification

`PostconditionObserver`, `DocumentUploadObserver`, `NotificationObserver`, `ApiReadbackVerifier`, `CiRunVerifier`, `RepositoryShaVerifier`.

### Automation/computer use

`CredentialResolver`, `RepairService`, `ComputerInteractionFabric`, COLD-tier pattern source, browser/automation policy cache reset path.

### Android

wake runtime/pipeline/coordinator, acknowledgement manager, TTS call path, local second pass, personal speech correction/pinning, `MissionRepository`, notification policy mutations, Compose restoration, Rive embodiment.

### Trading

`key_provider_from_registry`, MT5 pull app creation, Deriv live feed construction, token signing path where canonical.

For each WIRE component:

```text
ENTRY POINT
  → CONSTRUCTOR/DI
  → CALLER
  → DOMAIN OUTPUT
  → CONSUMER
  → OWNER/EXTERNAL EFFECT
```

A unit test directly constructing the class is not a production caller.

If a component is not canonical, delete code, registry entry and preserving tests, then update docs and authority map.

## Exit gate

- zero `NO_CONSTRUCTOR`;
- zero `NO_CALLER`;
- zero `TEST_ONLY` shipping components;
- zero `REGISTRY_ONLY` shipping capabilities;
- all retained components at least `INTEGRATED`.

---

# 8. Gate 3 — Universal mission and causality spine

## Objective

Make every owner-visible action part of one durable trace.

Standardize:

```text
OwnerIntentId
MissionId
TurnId
CommandId
AuthorityId
ContextSnapshotId
ExecutionId
EvidenceId
VerificationId
OutcomeId
LearningEpisodeId
```

Persist mission, execution, evidence and verification relations with indexed durable storage.

Before model reasoning/execution, seal Project Truth revision, owner-context revision, relevant knowledge evidence, capability readiness, authority envelope, temporal context and trading/account freshness where applicable.

No callback may silently execute under a changed authority/context snapshot without creating a new execution attempt.

Propagate mission/execution/authority/idempotency/context IDs across HTTP, MCP and jobs.

`MissionRepository` must render canonical mission state. Unknown backend states must fail visible as `UNKNOWN_REMOTE_STATE`, never silently map to success/accepted.

## Exit gate

A single voice command can be traced end-to-end using one mission ID across Android, gateway, Hermes and one real external executor.

---

# 9. Gate 4 — Authority convergence and security closure

## Objective

Make all execution surfaces obey one action authority model.

Create one gateway-owned immutable `ActionDescriptor` carrying action type, A1–A5 class, principal, mission, requested effect, scope, credential plane, verifier, biometric requirement, standing-authority allowance and expiry.

All subsystems consume this descriptor or a cryptographically bound derivative. They do not independently reclassify the action.

### Payment exception

Verify the production path around `assert_payment_action_is_owner_approved`.

Requirements:

- no autonomous payment;
- no standing-authority payment;
- exact payee/amount/currency/reference binding;
- fresh biometric;
- A4 preserved;
- no durable payment instrument storage;
- production caller exists if owner-approved payment is canonical.

If not canonical for v1, delete the exception and correct docs.

### Trading authority

Enforce:

```text
VAN/Hermes
  → trade proposal/request
  → VATI mandate/risk authority
  → execution router
  → single sender
  → broker
```

Prove by induced-failure tests that Hermes, Stagehand, n8n and Android cannot bypass VATI or broker credential boundaries.

### Principal binding

Never trust caller-supplied principal strings. Derive identity from authentication.

### Revocation

Device revocation propagates to grants, queued commands, approvals, standing automations, browser continuation and voice execution. Add `AUTHORITY_REVOKED`.

## Exit gate

Cross-surface induced attacks cannot bypass A1–A5, payment rules, VATI or principal identity.

---

# 10. Gate 5 — Verification and outcome truth

## Objective

Make real-world postconditions the source of completion truth.

Implement one canonical verifier registry. Every mutating capability registers timeout, observation strategy, correlation fields, success and failure predicates.

Never verify by bare existence alone. Correlate using provider operation ID, idempotency key, resource ID, timestamps, creator metadata, revision/etag, repository SHA, broker order ID or workflow execution ID.

Actions with no verifier enter `UNVERIFIABLE`, not `VERIFIED_SUCCESS`.

If a provider times out after possible mutation:

1. do not blindly retry;
2. read back;
3. correlate;
4. verify existing effect if found;
5. retry only when safe/idempotent;
6. otherwise enter `CONFLICTED` or `WAITING_FOR_OWNER`.

## Exit gate

Every canonical mutating action has a verifier or an explicit owner-visible `UNVERIFIABLE` contract.

---

# 11. Gate 6 — Cognition and owner-understanding activation

## Objective

Turn cognition from architectural inventory into the production reasoning path.

Canonical path:

```text
Owner Input
   ↓
Ingress Provenance
   ↓
Mission
   ↓
Context Retrieval
   ↓
Context Compiler
   ↓
Epistemic Classification
   ↓
Critical Reasoning
   ↓
Intent / Decision Model
   ↓
Action Planning
   ↓
Authority Gate
   ↓
Execution
   ↓
Verification
   ↓
Outcome Learning
```

Construct `ContextCompiler` under gateway dependency injection.

Its immutable `ContextPacket` carries provenance references rather than untraceable flattened prose.

`CriticalReasoningKernel` must execute evidence existence, relevance/support, contradiction and confidence-bounding checks from the real planning path.

`StrategicMemory`, `IntentContinuityGraph` and `DecisionFingerprints` must answer continuity questions and write memory only from verified events or explicit owner input.

### Owner Context Graph lifecycle

Require encryption, provenance, revision history, conflict representation, confidence bounds, retention, size limits, export, correction, selective erase, reset and deletion receipts.

Sensitive/secret data must never enter general semantic indexes.

### Symbiotic growth

Use promotion states:

```text
OBSERVED
INFERRED
CONFIRMED_LEARNED
OWNER_PINNED
```

Untrusted evidence may support an observation but cannot alone promote to confirmed/pinned owner truth.

## Exit gate

A real owner command demonstrably uses cognition and produces inspectable reasoning/context evidence without authority leakage.

---

# 12. Gate 7 — Voice completion and device audio architecture

## Objective

Make voice a complete local-first command channel.

Owner journey:

```text
"Hey Van"
  → local wake detection
  → immediate acknowledgement
  → local capture
  → ASR
  → owner intent
  → mission
  → execution
  → verification
  → spoken truthful result
```

### Implement missing Sherpa tier

Current policy can select `SHERPA_PRIMARY_REQUIRED` but no Sherpa runtime/model is present.

Preferred: integrate pinned `sherpa-onnx` Android runtime with model acquisition/package strategy, checksums, version manifest, storage quota, warm-up, lifecycle manager and offline tests.

Do not add cloud fallback.

Capability matrix:

```text
API 26–30
  → Sherpa primary

API 31–32
  → Android on-device direct mic if available
  → otherwise Sherpa primary

API 33
  → Android on-device caller audio if available
  → otherwise Sherpa primary

API 34–36
  → Android on-device caller audio + word evidence
  → otherwise Sherpa primary
```

If Sherpa is not implemented, raise `minSdk` and/or explicitly remove unsupported voice tiers.

Wire wake engine, phrase verifier, speaker scorer, coordinator, acknowledgement, audio arbiter, recognition, evidence and command dispatch.

Speaker similarity never authenticates or locks the owner out.

Use one microphone arbiter, bounded audio pipe/backpressure, watchdogs, broken-pipe handling, deterministic recovery and explicit microphone-loss state `WAKE_SUSPENDED_MIC_UNAVAILABLE`.

Voice idempotency derives from device + turn + attempt, never transcript.

Do not queue delayed safety-critical commands such as trading halt for silent replay.

## Exit gate

On target Samsung hardware, wake-to-command works offline for ASR and dispatches/returns a real mission result.

---

# 13. Gate 8 — Embodiment, aura and semantic-state truth

## Objective

Make Van's body and aura a trustworthy projection of canonical state.

Create `SemanticStateAggregator` consuming mission, voice, authority, degraded capability, attention, VATI trading, provider execution and verification state.

Use priority ordering so urgent safety/error/waiting/degraded states dominate transient execution/animation states.

The aura is an information channel. It communicates durable operational/trade/risk state, urgency, degradation and success only after verified success.

No animation callback may set success.

Require real `.riv` asset, contract validation, Canvas fallback, parity tests, owner visual acceptance and performance profiling.

Separate semantic state from procedural animation phase so continuous motion does not fabricate state changes.

## Exit gate

Visual state always agrees with mission/authority/trading truth during induced failures and retries.

---

# 14. Gate 9 — Google intelligence mesh production closure

## Objective

Make Google a set of independently resilient credential/capability planes presented coherently.

Track separately:

```text
WORKSPACE_OAUTH
GEMINI_RUNTIME
GOOGLE_CLOUD_SERVICE
CONSUMER_BROWSER_SESSION
DELEGATED_WORKER_IDENTITY
```

Each has independent auth status, expiry, readiness, scopes, refresh, degradation and reauthentication action.

Do not expose a single `google = offline` state.

For each capability assert:

```text
registry declaration
+ executor implementation
+ owner/Hermes reachable route/tool
```

Reconcile Gmail draft, Calendar reschedule/insert, Drive search, Contacts resolution and Tasks listing.

NotebookLM mutations require target object ID and readback before VAN reports creation success.

When one credential plane expires, only that plane degrades.

## Exit gate

At least one real read and one real write/readback journey pass for each shipping Google capability family.

---

# 15. Gate 10 — Browser and automation runtime deployment

## Objective

Deploy external execution dependencies and prove bounded autonomy.

Browser architecture:

```text
Hermes
  → Browser Task Request
  → Gateway authority
  → Browser Session Broker
  → Browser Harness
  → Stagehand semantic layer
  → target site
  → external observation
  → verifier
```

Stagehand is not authority. Browser Harness is the deterministic actuator.

Deploy browser worker with version pinning, health, bounded queue, session lease, profile isolation, task deadline, domain allowlist, action ceiling, step budget, screenshot/DOM evidence, injection containment and structured callbacks.

Deploy hardened n8n with PostgreSQL, external runner, bounded concurrency, no Docker socket, restricted filesystem, loopback management API, SSRF protection, disabled unapproved community packages, separate networks and execution pruning.

Scheduled/event automations derive from owner-approved standing authority containing trigger, ceiling, constraints, domains/resources, expiry and revocation root. It may never include A4 payment authority.

When scope is exceeded:

```text
RUNNING
→ WAITING_FOR_OWNER
→ durable decision
→ new bounded authorization
→ RESUMED
```

Hard policy prohibitions enter `BLOCKED_POLICY`.

## Exit gate

A real Stagehand task and real n8n workflow execute through mission authority, pause correctly and return verifier-backed evidence.

---

# 16. Gate 11 — VATI/trading deployment closure

## Objective

Make trading screens reflect real, fresh VATI truth and prove risk authority dominates execution.

Deploy Trading Core, broker adapter, market data, account credential references, VATI risk authority, execution router, ledger and commander interface.

Every trading read model includes source, account, observation time, data age, broker-state age and readiness.

UI distinguishes LIVE, DELAYED, STALE, DISCONNECTED and SIMULATED.

Keep the primary trading dashboard concise. Use independent pages for accounts, open positions, potential trades, recent outcomes, risk and market state rather than one long scrolling module wall.

Potential trades are proposals, not orders, and show thesis, evidence, timeframe, invalidation, risk, freshness, strategy, confidence and VATI eligibility.

Promotion sequence:

```text
UNIT
→ BACKTEST
→ PAPER/DEMO
→ SHADOW
→ LIMITED_LIVE
→ broader live only by owner decision
```

## Exit gate

Qualified path proves:

```text
analysis → VATI risk → order → broker receipt → ledger → readback → Android
```

with induced risk-denial tests.

---

# 17. Gate 12 — Resource, recovery and degraded-mode engineering

## Objective

Prove Van remains stable as one resident system on the owner's phone and across distributed runtimes.

Create `DeviceRuntimeBudget` and measure RSS/PSS, heap, native memory, renderer/GPU cost, CPU, wake-lock duration, battery per hour, thermal status, network bytes, storage, wake false-positive cost, local ASR cost and aura frame cost.

Set ceilings only after baseline measurement on target hardware.

Set explicit quotas for voice models, speech samples, owner-context graph, evidence cache, mission history, browser evidence, Google temporary artifacts and trading cache.

Use per-capability readiness:

```text
READY
DEGRADED
AUTH_REQUIRED
RATE_LIMITED
CAPACITY_LIMITED
OFFLINE
POLICY_BLOCKED
UNAVAILABLE
STALE
```

Mandatory recovery scenarios:

- Android process death;
- gateway restart mid-command;
- Hermes disappearance;
- network loss after provider mutation;
- duplicate provider callback;
- n8n restart;
- browser worker death;
- device revocation mid-run;
- expired biometric approval;
- market change while approval waits;
- notification permission revocation;
- microphone unavailable;
- Google plane expiry;
- low storage.

Run real backup/restore drills.

## Exit gate

Fault-injection recovery suite passes without duplicate consequential effects or false success.

---

# 18. Gate 13 — Observability, evidence, CI and operations

## Objective

Make one owner command reconstructable across the distributed system.

Every log/event carries mission ID, execution ID, authority ID, device hash, executor, capability, action class, external operation ID and verification state where applicable.

Provide:

```bash
van trace mission <mission_id>
```

showing received → authenticated → context sealed → reasoned → authorized → dispatched → external acknowledgement → effect → verified → owner notified → learning episode.

Certification artifacts live under:

`artifacts/certification/<gate>/<timestamp>-<sha>.json`

CI layers:

- static/governance;
- backend/trading units;
- reachability;
- full Android;
- integration/restart/replay;
- controlled live certification.

A release SHA cannot be promoted unless mandatory layers are green and evidence is attached.

## Exit gate

Release evidence is complete, reproducible, secret-free and SHA-bound.

---

# 19. Gate 14 — Physical-device and live-system E2E certification

## Objective

Prove the actual product, not the repository.

Primary target: Samsung Galaxy S24 Ultra on owner firmware/Android 16 where applicable.

Record build fingerprint, app SHA/version, permission state, battery optimization, assistant role and notification-listener state.

Mandatory journeys:

1. wake + simple command;
2. Google write + readback;
3. browser task + escalation;
4. n8n automation + postcondition;
5. cognition continuity;
6. untrusted notification handling;
7. trading read;
8. trading execution via VATI;
9. device revocation;
10. network failure after write;
11. overnight residency/reboot/Doze.

## Exit gate

All mandatory journeys pass on the release-candidate SHA.

---

# 20. Deployment topology

## Android

Owner interaction, local wake/ASR, overlay, TTS, biometric ceremony, secure device credentials, local queue, attention presentation and read surfaces. Android does not host a second autonomous agent loop.

## VAN Gateway

Authentication, mission creation, classification, authority, approvals, context orchestration, verification, audit, readiness/degradation, dispatch and event aggregation.

## Hermes

Model-driven reasoning, planning, bounded tool use, councils/subagents where canonical, research and development execution.

## Trading Core

VATI, market data, accounts, broker execution, risk and trading ledger.

## Automation/Browser runtime

n8n, Browser Harness, Stagehand and managed browser profiles. No authority ownership.

---

# 21. Security-specific closure tests

The release pipeline must include induced-failure tests for:

- prompt injection in email/web/notification;
- external content attempting A4/A5 escalation;
- forged principal;
- replayed signed command;
- duplicate idempotency key;
- concurrent idempotency race;
- stale approval;
- reused biometric approval;
- payment standing-authority attempt;
- browser domain/action-class escape;
- n8n broker credential access;
- Hermes device-enrollment attempt;
- direct broker bypass of VATI;
- stale market data execution;
- device revocation;
- tampered audit row;
- provider callback with wrong mission/execution identity.

---

# 22. Owner Context and privacy closure

The final product must let the owner:

- inspect learned facts;
- inspect why a fact is believed;
- correct;
- pin/unpin;
- delete selected facts/history;
- export context;
- clear personalization;
- clear retained speech samples;
- display provenance;
- show conflicts rather than silently overwrite.

Deletion produces receipts where applicable. Secret-class data remains outside semantic learning.

---

# 23. Product UI closure requirements

## Command Centre

Avoid a monolithic vertical module list.

Use a concise owner dashboard with navigable surfaces:

- Attention / Needs You
- Missions
- Projects
- Browser & Automation
- Google
- Trading
- Knowledge
- System Health
- Settings / Accounts / Devices

Cards summarize; detailed models live on independent pages.

## Needs You

One owner approval surface for biometric-required actions, browser escalation, conflict resolution, reauthentication, Project Truth decisions and trading decisions where applicable.

## Truthful labels

Distinguish working, waiting, submitted, verifying, verified, unverified, failed, stale, degraded, needs login and needs owner decision.

---

# 24. Release engineering

Suggested progression:

```text
0.5.x-dev       closure development
0.8.0-alpha     all repository gates integrated
0.9.0-beta      live runtimes deployed + device certification
0.9.5-rc        all owner journeys pass
1.0.0           owner-approved production release
```

Release candidate includes signed APK/AAB, SBOM, commit SHA, dependency lock evidence, deployment manifests, DB migration version, authority-map hash, policy hash, certification manifest, rollback procedure and backup/restore evidence.

Rollback must preserve database compatibility, audit chain, mission history, revocations, trading ledger and device enrollment integrity.

---

# 25. Closure ordering by unblock value

## Tier 0 — Establish truth

1. freeze correct branch/SHA;
2. reconcile findings;
3. correct voice finding;
4. add Sherpa finding;
5. close stale component ledger;
6. authority map.

## Tier 1 — Make the product build

1. full Android compile;
2. manifest/resources/Compose fixes;
3. APK install;
4. instrumentation foundation.

## Tier 2 — Wire existing capability

1. cognition;
2. mission repository;
3. verification observers;
4. voice runtime;
5. Google routes;
6. computer-use fabric;
7. trading constructors.

## Tier 3 — Add cross-system invariants

1. causal mission lineage;
2. canonical action descriptor;
3. verifier contract;
4. capability-granular degradation;
5. learning-authority immutability;
6. cognition provenance;
7. semantic-state aggregator.

## Tier 4 — Build truly absent pieces

1. Sherpa ASR;
2. real Rive asset/runtime completion;
3. Browser Harness worker;
4. Stagehand worker deployment;
5. live market feed;
6. any remaining canonical margin/risk model;
7. external provider pieces not present.

## Tier 5 — Deploy

1. gateway;
2. Hermes integration;
3. browser;
4. n8n;
5. Google planes;
6. Trading Core.

## Tier 6 — Prove

1. live canaries;
2. Samsung certification;
3. recovery/fault injection;
4. owner journeys;
5. final release evidence.

---

# 26. Definition of Done for every capability

A capability is complete only when all applicable answers are YES:

1. Does the code exist?
2. Does it compile?
3. Is there a real producer?
4. Is there a real consumer?
5. Is there a production constructor?
6. Is there an owner-reachable entry point?
7. Does it preserve mission identity?
8. Does it preserve authority identity?
9. Are retries idempotent?
10. Does it have failure semantics?
11. Does it have degraded semantics?
12. Do tests fail when the feature is broken?
13. Has it run against the real dependency?
14. Is runtime evidence recorded?
15. Does the owner see truthful state?
16. If it mutates external state, is the postcondition verified?
17. Does it survive restart/recovery where required?
18. Does documentation match?
19. Does CI enforce continued correctness?
20. Has the target release SHA passed the test?

---

# 27. Final deployment-readiness decision

VAN is deployment-ready only when:

```text
Android full compile                          PASS
Android physical-device acceptance           PASS
Component terminal-state gate                PASS
Mission causal-integrity gate                PASS
Authority/security induced-failure gate      PASS
Verification truth gate                      PASS
Cognition production-path gate               PASS
Voice local-first gate                       PASS
Aura semantic-truth gate                     PASS
Google live capability gate                  PASS
Browser live gate                            PASS
n8n live gate                                PASS
Trading demo/LIMITED_LIVE gate               PASS
Recovery/fault-injection gate                PASS
Observability/evidence gate                  PASS
Owner end-to-end journey suite               PASS
Owner release approval                       SIGNED
```

No count such as “84 findings closed” can substitute for these gates.

---

# 28. Final engineering principle

The target is not a collection of green modules.

The target is:

> **One Van who understands the owner, preserves continuity across time, reasons critically from evidence, delegates through bounded specialist runtimes, never silently acquires authority, never confuses submission with success, survives failure without duplicating consequential effects, and presents one truthful living state to the owner across voice, aura, Command Centre, trading, Google, browser and automation.**

Every implementation decision in the closure programme should be tested against that sentence.

If a change makes a subsystem individually more capable but makes the whole VAN experience less causally coherent, less truthful or less authority-safe, it is not a valid closure change.

---

# Appendix A — Immediate first execution packet

Before broad feature work resumes, produce:

```text
1. evidence/closure/CONSOLIDATED_FINDINGS.json
2. evidence/closure/COMPONENT_MATURITY.json
3. docs/project-state/AUTHORITY_MAP.yaml
4. docs/project-state/RELEASE_BASELINE.json
5. CI terminal-state check
6. full Android compile evidence
7. updated voice finding: remove stale cloud-ASR defect; add Sherpa absence
8. mission causal-ID migration proposal
9. canonical ActionDescriptor implementation proposal
10. target-device certification harness skeleton
```

---

# Appendix B — Minimum evidence bundle per gate

Each gate produces:

```text
gate.json
tests.txt
runtime-attestation.json
dependency-versions.json
source-sha.txt
secret-scan.txt
known-limitations.json
```

Runtime attestations contain no secrets.

---

# Appendix C — High-value branch-specific checks

Before declaring the Claude audit branch canonical, explicitly verify:

- all remediation commits are present and ordered correctly;
- scripted corruption was fully reverted;
- no residual missing delegated-property imports remain;
- no contract test passes merely because a token appears in comments/raw source;
- `MissionBinder` and `CapabilityRouter` are genuinely invoked;
- restored UI actions render through real Compose navigation;
- payment exception is wired or deliberately removed;
- flagged verifier/observer classes are wired or deleted;
- Android voice remains local-only;
- no generic `SpeechRecognizer.createSpeechRecognizer()` is introduced;
- `SHERPA_PRIMARY_REQUIRED` cannot ship without Sherpa or an explicit supported-API policy change.

---

# Appendix D — Recommended certification artifact names

```text
artifacts/certification/gate-00-baseline/
artifacts/certification/gate-01-android-build/
artifacts/certification/gate-02-reachability/
artifacts/certification/gate-03-causality/
artifacts/certification/gate-04-authority/
artifacts/certification/gate-05-verification/
artifacts/certification/gate-06-cognition/
artifacts/certification/gate-07-voice/
artifacts/certification/gate-08-embodiment/
artifacts/certification/gate-09-google/
artifacts/certification/gate-10-browser-automation/
artifacts/certification/gate-11-trading/
artifacts/certification/gate-12-recovery-resource/
artifacts/certification/gate-13-observability-ci/
artifacts/certification/gate-14-e2e/
```

The release manifest hashes every accepted artifact.

---

# Appendix E — Stop conditions

Development must stop and return to the relevant authority gate if any of these occur:

- a model is found to mint/widen authority;
- payment can execute without fresh exact-bound owner approval;
- browser/n8n can reach broker execution;
- a provider mutation can be called successful without verification;
- untrusted external content can become owner instruction without a new authority transition;
- device revocation does not stop consequential continuation;
- mission identity is lost across an executor boundary;
- trading can execute on stale data;
- Android silently switches to cloud ASR;
- aura/UI reports success while mission status is not verified;
- test/build evidence comes from a different SHA than the release candidate.

These are release-blocking defects, not backlog items.
