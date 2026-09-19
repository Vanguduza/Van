# VAN Remediation Programme — Rev 1

**Companion to:** `docs/VAN_WHOLE_SYSTEM_IMPLEMENTATION_AUDIT_AND_CERTIFICATION_REV_1.md`
**Machine-readable register:** `evidence/van-system-audit/findings.json`
**Baseline:** branch `claude/van-system-audit-ysgtcd`, HEAD `dff38a0`, version `0.5.0-dev`
**Scope:** close every finding, and give every non-INTEGRATED component an explicit disposition.
**Status:** proposed. No code in this programme has been written.

---

## 1. The one constraint on "everything is equally important"

Treating every gap as equally important is the right *completion* bar, and this programme adopts it:
**nothing is deferred, nothing is written off as acceptable debt, and no finding is closed by lowering
its severity.**

It cannot be the *scheduling* rule, for one reason that is a property of the code rather than a
judgement about value: **roughly a third of the findings are not fixable until another one lands.**

Three worked examples:

- `P1-LEARN-001` (no production event feeds any learning loop) cannot be fixed before `P0-EXEC-001`
  (commands produce no mission). There is no outcome to record until there is a unit of work to
  record it against.
- `P1-AURA-003` (trading state never reaches the aura) cannot be fixed before a semantic state bus
  exists, and that bus is only worth building once there is mission state to publish on it.
- `P1-SYM-001` (episode references are unverified strings) cannot be fixed before missions exist,
  because a mission identifier is what an episode reference is supposed to be.

So the ordering below is **forced by dependency**, not by ranking. Where two items are independent,
they are scheduled in parallel and the document says so. The completion bar is unchanged: all of them.

---

## 2. Register completeness — 55 IDed findings is not the whole set

The audit assigned IDs to 55 findings (15 P0, 26 P1, 14 P2). It also enumerated roughly **25 further
P3 and P4 items in prose** without IDs — no application logging, no retention, no backups, no state
restoration, 18 dead client methods, five hardcoded-healthy subsystems, a blocking sleep in an async
loop, two god files, and so on.

If every gap is equally important, those need identifiers too, or they will be the ones that quietly
survive. **Action W0-1 of this programme extends the register from 55 to approximately 80 IDs** so
that "all closed" is a countable claim rather than a feeling. The waves below carry the P3/P4 work
explicitly; it is not appended as an afterthought.

---

## 3. Disposition rule

Every component the audit classified **ABSENT, STUB, SIMULATED, PARTIAL** or
**IMPLEMENTED_BUT_ISOLATED** receives exactly one verdict. There is no fifth option and no
"leave as is".

| Verdict | Meaning | When it is correct |
|---|---|---|
| **WIRE** | The implementation is sound; connect a producer and a consumer | Real, tested code with no caller |
| **COMPLETE** | Part of the contract is missing; finish it | Genuine partial implementation |
| **REPLACE** | The approach is wrong; build the right thing and remove this | The component cannot meet its contract as designed |
| **DELETE** | Remove the code and withdraw the claim | Redundant, superseded, or not canonically required |

**DELETE is a first-class outcome and is used 14 times below.** An unused module is not free: it
carries a documentation claim, it appears in the matrix as BUILT, it accrues test weight, and it is
indistinguishable from working code to anyone reading the repository. Several of the audit's worst
findings exist precisely because something was built, never wired, and then described as done.

---

## 4. Component disposition inventory

Every non-INTEGRATED component found by the audit, with its verdict and the wave that executes it.

### 4.1 Cognition, context and memory (21 components)

| # | Component | Class today | Verdict | Rationale | Wave |
|---|---|---|---|---|---|
| 1 | `ContextCompiler` / `ContextPacket` | ISOLATED | **DELETE** | Duplicates `ContextRetrievalService`, which is on a real path. Port its three good behaviours first: cross-project isolation, contradiction grouping, deliberate drop order | 5 |
| 2 | `epistemics.SemanticClass` / `Claim` | ISOLATED | **DELETE** | Second, unenforced taxonomy beside `EpistemicState`, which *is* enforced at admission. Two vocabularies for one concept is the drift itself | 5 |
| 3 | `FORBIDDEN_SELF_PROMOTIONS` / `may_promote` | ISOLATED | **REPLACE** | The rule is correct and belongs in `context/service._validate_admission`, expressed in `EpistemicState` terms | 5 |
| 4 | `AdmissionOutcome` / `AdmissionVerdict` | Unused by anything | **DELETE** | Referenced by no code and no test | 5 |
| 5 | `CriticalReasoningKernel.assess` | ABSENT as reasoner | **COMPLETE** | Add a real critic pass over supplied evidence, plus a route and an MCP tool so Hermes can reach it. If the owner declines the scope, the honest alternative is DELETE plus a matrix correction | 5 |
| 6 | `assert_safe_for_irreversible_work` | No caller | **WIRE** | Call it from `ActionRuntime.begin` for A3/A4 | 5 |
| 7 | `assess_premise` + sycophancy metrics | No producer | **WIRE** | Route plus MCP tool; fed by the Hermes post-turn hook | 5 |
| 8 | `RelationshipCalibrationEngine` | No caller | **WIRE** | Consume in the Hermes context packet; fix the "owner-confirmed" wording | 5 |
| 9 | `OwnerCognitiveModel` | No writer | **WIRE** | Feed from owner corrections, accepted and rejected recommendations, and mission outcomes | 5 |
| 10 | `SharedVocabularyRegistry` | Read-only | **WIRE** | Write path from owner corrections | 5 |
| 11 | `CognitiveComplementMap` | Read-only | **WIRE** | Populate from verified mission outcomes | 5 |
| 12 | `SymbioticGrowthLedger` | Read-only | **WIRE** | Record adaptations at the point they are proposed | 5 |
| 13 | `IntentContinuityGraph` | No constructor | **WIRE** | Construct in `app.py`; nodes from missions | 5 |
| 14 | `StrategicMemory` | No constructor | **WIRE** | Construct; write on rejected recommendations | 5 |
| 15 | `DecisionFingerprints` | No constructor | **WIRE** | Construct; record on every decision resolution | 5 |
| 16 | `ExternalRealityModel` | No constructor | **DELETE** | No canonical requirement, no producer, and no consumer. Re-add when a real external-signal source exists | 5 |
| 17 | `BenchmarkHarness` | No constructor | **WIRE** | Drive from the existing CI benchmark job | 5 |
| 18 | `StrategyLearning` | No constructor | **WIRE** | Record outcomes from mission verification | 5 |
| 19 | `AIEvolutionRadar` | Read-only API | **COMPLETE** | Add the discover and transition routes its state machine implies | 5 |
| 20 | `VanEval` | Read-only, self-scoring | **COMPLETE** | Scores must come from measurement; stop writing 11 rows on every GET | 5 |
| 21 | `ContextRetrievalService` | API only | **WIRE** | Put it on the command path via derived requirements | 5 |

### 4.2 Mission, capability and verification (5 components)

| # | Component | Class today | Verdict | Rationale | Wave |
|---|---|---|---|---|---|
| 22 | `MissionService` | One internal caller | **WIRE** | The orchestrator creates a mission per accepted command | 2 |
| 23 | `MissionBinder` | Not wired in `app.py` | **WIRE** | Pass the binder; browser and automation bind automatically | 2 |
| 24 | `CapabilityRouter` | One caller | **WIRE** | Route on mission creation, not only via the internal route | 2 |
| 25 | `VerifierRegistry` + 5 adapters | Test-only | **WIRE** | `MissionService.transition` executes a verifier instead of accepting a record | 3 |
| 26 | `PostconditionObserver` + 2 observers | No caller | **WIRE** | Supply the real observer map to `AutomationDispatcher` | 3 |

### 4.3 Voice (9 components)

| # | Component | Class today | Verdict | Rationale | Wave |
|---|---|---|---|---|---|
| 27 | `WakeWordEngine` | Interface only | **COMPLETE** | Integrate a real keyword spotter; ship the model and native libraries | 8 |
| 28 | `WakePhraseVerifier` | Interface only | **COMPLETE** | Second-stage verification of "Hey Van" | 8 |
| 29 | `SpeakerSimilarityScorer` | Interface only | **COMPLETE** | Closes `P2-SEC-010`; without it any voice is the owner's voice | 8 |
| 30 | `WakePipeline` / `WakeRuntimeController` / `WakeCoordinator` | Never constructed | **WIRE** | Construct in `VanApplication`; arm on a microphone-typed foreground service | 8 |
| 31 | `WakeAcknowledgementManager.play` | Never called | **WIRE** | Play before any network call, as designed | 8 |
| 32 | `TtsOutputManager.speak` | Never called | **WIRE** | Speak on verified mission outcomes only | 8 |
| 33 | `LocalSecondPassAsr` | No implementation | **COMPLETE** | Or DELETE the fusion path; a fusion with one input is not a fusion | 8 |
| 34 | `PersonalSpeechModel.recordCorrection` / `pinTerm` | No callers | **WIRE** | Feed from the correction capture UI | 8 |
| 35 | `VoiceTurnAudioCapture` evidence ref | Unresolvable URI | **COMPLETE** | Either serve the reference or stop signing a pointer to nothing | 8 |

### 4.4 Browser, automation and durable execution (7 components)

| # | Component | Class today | Verdict | Rationale | Wave |
|---|---|---|---|---|---|
| 36 | Browser Harness worker | ABSENT | **COMPLETE** | Build or vendor the worker behind the existing HTTP contract | 7 |
| 37 | Stagehand worker | ABSENT | **COMPLETE** | As above; the adapter contract is already correct | 7 |
| 38 | `SubagentWorker` | No implementation | **WIRE** | Bind the subagent state machine to the real worker | 7 |
| 39 | Browser task path → adapters | Never calls an adapter | **WIRE** | The task path must actually actuate | 7 |
| 40 | Injection containment | Records only | **COMPLETE** | Make `CONFIRMED_INJECTION` reachable and stop the task | 7 |
| 41 | `PatternSource` / COLD tier | No implementation | **DELETE** | COLD is identical to WARM in practice. Collapse to one tier until a pattern source exists | 7 |
| 42 | **Temporal** | ABSENT | **DELETE the routing branch** | Blueprint Rev 3 decision D9 makes Temporal *optional*, adopted only on measured need with an owner-signed decision. No such decision exists. Make the router refuse `critical_durable` honestly instead of naming a medium with no executor | 7 |
| 43 | `computer_use/fabric.py` | STUB, claimed BUILT | **DELETE or fold** | Nothing executes its 12 operations. Fold the vocabulary into the browser fabric when workers land, or delete and correct the matrix. Do not keep a claimed-BUILT surface with no executor | 7 |

### 4.5 Android (10 components)

| # | Component | Class today | Verdict | Rationale | Wave |
|---|---|---|---|---|---|
| 44 | `MissionRepository` | Never constructed | **WIRE** | 371 lines of correct owner language already written | 2 |
| 45 | 18 dead `VanGatewayClient` methods | Unused | **WIRE** | They are the mission, understanding and needs-you reads the new screens require | 2 |
| 46 | `ShareIntentReceiver` | Wrong component type | **REPLACE** | A transparent Activity; a receiver can never appear in the share sheet | 8 |
| 47 | 5 hardcoded-healthy subsystems | Fake healthy | **COMPLETE** | Drive overlay, queue, notifications, voice and biometric from real signals | 8 |
| 48 | `RestoreAction` values | Never rendered | **WIRE** | Render the restore action the degraded contract already carries | 8 |
| 49 | `NotificationPolicy.setPolicy` / `setQuietHours` | No call site | **WIRE** | Build the owner control surface | 8 |
| 50 | Rive embodiment | No asset | **COMPLETE** | External gate: author the `.riv`. Until then keep the honest fallback and do not ship the 4-5 MB runtime | 9 |
| 51 | `QueueReplayer` | Called once | **COMPLETE** | Trigger on connectivity and health recovery | 8 |
| 52 | Compose state restoration | ABSENT | **COMPLETE** | ViewModels and `rememberSaveable` throughout | 8 |
| 53 | `CommandCentreActivity` (1238 lines) | God file | **REPLACE** | Rebuild as a `NavHost` over mission read models | 8 |

### 4.6 Google, knowledge and Hermes (12 components)

| # | Component | Class today | Verdict | Rationale | Wave |
|---|---|---|---|---|---|
| 54 | `gmail_draft` | No route | **WIRE** | Without it `gmail_send` is unusable — VAN cannot create the draft it is allowed to send | 5 |
| 55 | `calendar_reschedule` | No route | **WIRE** | Plus add `events.insert`, absent entirely | 5 |
| 56 | `drive_search`, `contacts_resolve`, `tasks_list` | No routes | **WIRE** | Each needs a route and a resolver intent | 5 |
| 57 | 13 registry-only Google capabilities | Registry entries | **COMPLETE or DELETE** | Per capability. A registry row with no code that is selectable as a routing fallback is worse than an absent row | 5 |
| 58 | `workspace_studio` as fallback | Selectable, unimplemented | **DELETE** | Remove from the fallback chain until implemented | 5 |
| 59 | VEKL adapter | No endpoint | **COMPLETE** | Configure the DDE endpoint, or mark the capability unavailable rather than DISABLED | 5 |
| 60 | Obsidian provider | Unconfigured | **WIRE** | Self-contained; needs only a vault path and a flag | 5 |
| 61 | `NotebookConsumerProvider` | Transport absent | **WIRE** | Unblocked by wave 7 workers | 7 |
| 62 | Exa research | Disabled | **WIRE** | Enable with the egress policy already written | 5 |
| 63 | `bridge.message_agent` / `create_council` | Dead code | **DELETE** | Hermes owns councils natively; the gateway bridge duplicates it and has no caller | 0 |
| 64 | 9 unregistered MCP tools | Registration drift | **COMPLETE** | Align the include list; assert it in the contract test | 0 |
| 65 | Policy hook registration | Never registered | **COMPLETE** | Register at install; assert in the doctor and attestation | 0 |

### 4.7 Trading (5 components)

| # | Component | Class today | Verdict | Rationale | Wave |
|---|---|---|---|---|---|
| 66 | Owner signature verification | STUB (non-empty string) | **REPLACE** | Real signature against a registered key, at all six sites | 3 |
| 67 | Live market feed → session | ABSENT | **COMPLETE** | Sessions currently read bars from a file on disk | 4 |
| 68 | Learning in the live session | Backtest only | **WIRE** | Pass `learning=` in `SessionService.build` | 4 |
| 69 | Postgres ledger | Test skipped | **COMPLETE** | Un-skip and run it in CI | 4 |
| 70 | Margin model | ABSENT | **COMPLETE** | Add margin fields and a Risk Authority gate | 4 |

**Totals: 70 components — 35 WIRE, 22 COMPLETE, 4 REPLACE, 9 DELETE.**

These counts are derived from `evidence/van-system-audit/component_ledger.json`, which is the
machine-readable authority. An earlier draft of this section stated 14 DELETE; that over-counted by
treating four conditional dispositions ("complete or delete") as deletions. The ledger and the
maturity CI are authoritative over this prose.

---

## 5. Wave plan

Each wave states what it closes, what it disposes, how it is proven, and what must be true to exit.
Effort is a range in engineer-days for one competent engineer with this codebase loaded, estimated by
an auditor who has read the code but not written it. Treat the ranges as planning input, not a bid.

### Wave 0 — Truth correction · 3–5 days · no dependencies · **start immediately**

**Why first:** every other wave is planned against the documentation. While the matrix claims 33 of 36
workstreams BUILT, nobody can tell a wired component from an isolated one, and the programme cannot be
tracked.

**Closes:** `P1-DOC-001`, `P1-DOC-002`, `P1-HER-001`, `P1-HER-002`, `P1-HER-003`, `P1-HER-004`, plus
register extension W0-1.
**Disposes:** #63 DELETE, #64 COMPLETE, #65 COMPLETE.

**Work:** extend the findings register from 55 to ~80 IDs. Correct the matrix for WS9, WS13, WS28,
WS33, WS34 — replacing BUILT with the audit's classification. Merge PR #38 or remove the blueprint
reference. Remove the Temporal line from the acceptance ledger. Mark `rev21/` evidence stale. Fix the
duplicated manifest hash. Align the MCP include list with the shim and assert it. Register the policy
hook at install and assert it in the doctor. Install the two missing skills; reconcile the skill count
across config, installer, doctor, tests and attestation. Delete the dead bridge methods. Correct
`android/README.md`.

**Tests:** a contract test asserting the MCP include list matches the shim's tool list; a doctor
assertion that the hook is loaded; a test asserting the skill count is identical in all five sources.
**Evidence:** a matrix where every `status` matches this audit's classification for that component.
**Exit:** no canonical document asserts a capability classified ABSENT or STUB.

### Wave 1 — Containment · 8–12 days · depends on 0 · **runs parallel to 2**

**Why early:** two paths are exploitable today and neither depends on any feature work.

**Closes:** `P0-SEC-001`, `P0-SEC-002`, `P1-SEC-005`, `P1-SEC-006`, `P1-SEC-007`, `P1-SEC-004`,
`P2-SEC-008`, `P2-SEC-009`, `P1-HER-005`.

**Work:** split the internal control token into scoped, expiring, per-purpose credentials, and remove
device enrollment from the Hermes-reachable set (RC4). Add an explicit 403 when the internal check
fails instead of falling through to the device path. Derive `context_trust` from `CommandKind` in
`VanGatewayClient`; refuse to dispatch `CONTEXT_INGEST` as a command; reject UI-channel payloads
carrying an untrusted-content marker server-side (RC5). Add a `command_nonces` table with a uniqueness
check. Make the idempotency claim atomic with `BEGIN IMMEDIATE`, and enable WAL with a busy timeout.
Add a hash chain to the audit table. Add rate limiting and lockout on pairing, the ingress token, the
device token and the approval challenge. Route trading credential changes through the
`CryptoObject`-bound biometric path. Add expiry and rotation for every long-lived credential; add a
PKI renewal path. Remove `test-transport` from the production app. Verify commander halt signatures and
bind `requested_by` to the authenticated principal.

**Tests:** an adversarial test posting a notification-shaped payload and asserting refusal; a
concurrency test for the idempotency claim; a nonce replay test; an audit-chain tamper test; a rate
limit test.
**Evidence:** a re-run of `probe_authority_boundaries.py` in which probes 1 and 3 no longer escalate.
**Exit:** **G2**. Neither probe reproduces.

### Wave 2 — Work identity · 12–18 days · depends on 0 · **runs parallel to 1**

**Why here:** this is root cause RC1 and the largest single unlock in the programme. Six other findings
become fixable only after it.

**Closes:** `P0-EXEC-001`, `P0-EXEC-003`, `P2-COH-001`.
**Disposes:** #22, #23, #24, #44, #45 WIRE.

**Work:** the orchestrator creates a mission per accepted command with a real authority envelope, and
passes `mission_id` in Hermes run metadata. `CreateMissionBody` accepts an authority envelope, fixing
the A3-above-A2 ceiling bug that prevents automation from ever binding. Wire `MissionBinder` in
`app.py`. Publish mission transitions onto the event bus. Add `GET /v1/commands/{id}`. Define **one**
owner-facing work status projection and map all eleven internal vocabularies onto it. On Android,
construct `MissionRepository` and render `ownerReadableStatus`; make an unknown gateway status an
explicit UNKNOWN rather than `ACCEPTED`.

**Tests:** command-to-mission binding; event-bus publication on transition; automation binding to an
API-created mission; an Android mission-surface test.
**Evidence:** a re-run of `probe_command_lifecycle.py` showing missions and activities after the ten
canonical intents.
**Regression gates:** the full security suite stays green; no authority gate changes.
**Exit:** **G3**.

### Wave 3 — Verified completion · 10–15 days · depends on 2

**Why here:** this is RC2. It is the wave most likely to turn currently-green paths red, which is the
point — those paths are green because nothing verifies them.

**Closes:** `P0-VERIFY-001`, `P0-EXEC-002`, `P1-AUTO-001`, `P0-TRADE-001`, `P1-GOOG-002`, and the
verification half of `P2-COH-002` — `VerifierRegistry` becomes the single verification system and
automation's `WorkflowVerifier` is retired into it.
**Disposes:** #25, #26 WIRE; #66 REPLACE.

**Work:** `MissionService.transition` executes a registered verifier from `VerifierRegistry` rather
than accepting a supplied record. Supply the real observer map to `AutomationDispatcher`. Join
`hermes_run_id` to its action callbacks and add a deadline producing a truthful timeout state. Verify
trading owner signatures against a registered key at all six sites. Seal the full parameter set for A3
actions so `notebook_id` cannot be chosen by Hermes.

**Tests:** a self-asserted receipt is now **rejected**; a real verifier receipt is accepted; a missing
callback produces a timeout, not silence; an unsigned mandate is refused.
**Evidence:** `probe_mission_verification.py` showing `i-say-so/1.0` refused.
**Budget warning:** expect churn in tests that currently assert success on unverified paths. That churn
is the finding surfacing, not a regression.
**Exit:** **G4**.

### Wave 4 — Trading safety · 10–14 days · depends on 3

**Closes:** `P0-TRADE-002`, `P0-TRADE-003`, `P0-TRADE-004`, `P0-TRADE-005`, `P0-TRADE-006`,
`P1-TRADE-007`, `P1-TRADE-008`.
**Disposes:** #67, #68, #69, #70.

**Work:** drive `reconciliation_ok`, `risk_store_ok` and `tier1_event_blackout_active` from real state,
and re-run reconciliation per bar rather than once at startup. Add a synchronous halt channel and stop
filtering halts by session start time, so a restart cannot discard an owner halt. Derive the
idempotency key from decision content and bar identity rather than the session id; add a per-alias
process lock. Add margin fields to `AccountState` and a margin gate to the Risk Authority. Point the
gateway at the live ledger and threshold staleness server-side. Wire learning into the live session
behind the existing reduce-only boundary. Use the winning signal's target and delete the dead loop.
Connect a live market feed to the session.

**Tests:** injected reconciliation failure produces a refusal; a halt is observed in under one second;
a halt survives a restart; a duplicate signal after a crash is refused; a margin-constrained order is
rejected.
**Evidence:** a demo-account session exercising each of the five.
**Exit:** **G5**.

### Wave 5 — Context and cognition · 18–25 days · depends on 2

**Why after 2:** episode references are supposed to be mission identifiers. Wiring the owner model
before missions exist would rebuild the same unverifiable-string defect.

**Closes:** `P0-CTX-001`, `P0-CTX-002`, `P0-COG-001`, `P1-SYM-001`, `P1-LEARN-001`, `P2-COG-002`,
`P2-MEM-002`, `P2-GOOG-001`, and the attention half of `P2-COH-002` — `decisions/service` migrates to
`AttentionScorer` and the older `AttentionEngine` is deleted. Plus the retention items from P3.
**Disposes:** #1–#21 (the entire cognition inventory), #54–#60, #62.

**Work:** add an owner-facing fact writer and a Project Truth importer so the authoritative tiers can
be populated. Derive real `ContextRequirements` on the command path from `project_id` and resolver
output. Port `ContextCompiler`'s three good behaviours into `ContextRetrievalService` and delete the
module along with the `SemanticClass` taxonomy; move `FORBIDDEN_SELF_PROMOTIONS` into
`_validate_admission` in `EpistemicState` terms. Bind `episode_ref` to mission or command identifiers.
Make calibration distinguish evidence-derived from owner-confirmed in the words it shows the owner.
Add routes and MCP tools for assessment, premise and observation, plus a Hermes post-turn hook that
emits them. Call `assert_safe_for_irreversible_work` from `ActionRuntime.begin`. Record mission
outcomes into `StrategyLearning`, `DecisionFingerprints` and `SymbioticGrowthLedger`. Add retention to
every unbounded table. Add the missing Google routes including `events.insert`, and remove
`workspace_studio` from the fallback chain.

**Tests:** a command whose sealed snapshot carries real fact identifiers; measured retrieval precision
and recall on an owner benchmark; an owner correction that changes the model and is revertible; a
retention job test.
**Exit:** **G6**.

### Wave 6 — Semantic state bus · 8–12 days · depends on 2

**Closes:** `P1-AURA-002`, `P1-AURA-003`, `P1-PERF-002`, `P2-AURA-001`, `P2-PERF-001`.

**Work:** publish a classified semantic-state event from the gateway covering mission phase, tool use,
browser use, trading classification and degraded state; subscribe the Android visual runtime to it.
Extend `VanDurableState` with the missing semantics — tool use, browser use, planning, interpreting,
interrupted. Introduce a monotonic animation clock and blend aura and pose changes over 120–420 ms.
Express the body gap contract in dp and assert it. Cache stable field topology and update only dynamic
coordinates. Add frame-time sampling so `frameBudgetMissed` has a producer. Drive the overlay lifecycle
below STARTED on screen off.

**Tests:** a state-bus contract test; a dp gap assertion; a transition-duration assertion.
**Evidence:** on-device capture of the aura changing on a real trading classification.
**Exit:** the §37 aura certification becomes runnable.

### Wave 7 — Execution substrates · 20–30 days · depends on 3 and 6

**Closes:** `P1-BROW-002`, `P2-BROW-001`, and the browser and automation external gates.
**Disposes:** #36, #37, #38, #39, #40 COMPLETE/WIRE; #41, #42, #43 DELETE; #61 WIRE.

**Work:** build or vendor the Harness and Stagehand workers behind the existing HTTP contract — the
contract is already correct, which makes this bounded. Wire the browser task path to the adapters and
the mission binder. Make `CONFIRMED_INJECTION` reachable and stop the task on it. Populate
`external_domains`, which is currently `{}` and denies every host. Collapse COLD into WARM until a
pattern source exists. Make the automation router refuse `critical_durable` honestly rather than naming
Temporal as a medium with no executor. Fold or delete the Computer Interaction Fabric. Fix the blocking
sleep in the async retry loop and the non-existent n8n run endpoint.

**Tests:** a live adversarial injection canary; a browser task producing verifier-backed evidence.
**Exit:** the Browser Fabric external gates.

### Wave 8 — Voice and owner experience · 25–35 days · depends on 2, 3 and 6

**Closes:** `P1-VOICE-001`, `P1-AND-001`, `P1-AND-002`, `P2-UX-001`, `P2-SEC-010`, plus the Android
P3/P4 items.
**Disposes:** #27–#35, #46–#49, #51–#53.

**Work:** integrate a real keyword spotter with the "Hey Van" phrase and ship its model; add a
microphone-typed foreground service and arm the wake pipeline; play the acknowledgement before any
network call; invoke TTS on verified mission outcomes; implement speaker verification and gate dispatch
on it; add correction capture feeding `PersonalSpeechModel`. Convert `ShareIntentReceiver` to a
transparent Activity. Add pairing to onboarding and gate step advancement on real grant checks. Rebuild
the Command Centre as a `NavHost` over the mission read models, in owner language, with accessibility,
adaptive layout, state restoration and a light theme. Drive the five hardcoded-healthy subsystems from
real signals. Trigger queue replay on connectivity recovery.

**Tests:** the first Android instrumentation suite; wake-word false-positive and latency tests;
accessibility assertions.
**Evidence:** P95 wake acknowledgement under 250 ms on the owner device.
**Exit:** **G9** and the §38 command certification.

### Wave 9 — Evidence, observability and operations · 15–20 days · depends on 6

**Closes:** `P1-VIS-001`, `P1-VIS-002`, `P2-VIS-003`, `P2-OBS-001`, and the infrastructure P3 items.
**Disposes:** #50.

**Work:** extract the Compose painter into the shared source set so previews render the shipping
pixels. Regenerate evidence at the current authority revision including the orthogonal-presence board.
Add an instrumentation source set with golden-image regression tests, so a regression that deleted the
aura would fail rather than pass. Add structured logging with a correlation id spanning command →
mission → execution → verification. Export metrics. Add backups with a restore drill, log rotation, PKI
renewal monitoring and alerting.

**Exit:** **G7**, and the observability and infrastructure register.

---

## 5.1 Coverage check

Every one of the 55 registered findings is assigned to exactly one wave, and every one of the 70
inventory components carries a disposition executed in a named wave. Verified mechanically:

```bash
python3 - <<'EOF'
import json
reg = json.load(open("evidence/van-system-audit/findings.json"))
prog = open("docs/VAN_REMEDIATION_PROGRAMME_REV_1.md").read()
missing = [f["id"] for f in reg["findings"] if f["id"] not in prog]
print("unassigned findings:", missing or "none")
EOF
```

Re-run this after the W0-1 register extension to confirm the additional P3/P4 identifiers are assigned
too. A finding that is in the register and not in this document is a planning defect, not a backlog
item.

---

## 6. Critical path and parallelism

```
W0 Truth ─┬─► W1 Containment ──────────────────────────────────────────────┐
          │                                                                 │
          └─► W2 Work identity ─┬─► W3 Verified completion ─┬─► W4 Trading ─┤
                                │                            │              │
                                │                            └─► W7 Substrates
                                ├─► W5 Context & cognition ─────────────────┤
                                │                                           │
                                └─► W6 Semantic state bus ─┬─► W8 Voice & UX┤
                                                            │               │
                                                            └─► W9 Evidence ┘
```

**Critical path:** W0 → W2 → W3 → W7 (or W8), roughly **68–100 engineer-days**.
**Total programme:** approximately **129–186 engineer-days** of work.

With three engineers split as backend, Android and trading, the wall-clock is roughly **10–14 weeks**.
With one engineer it is **six to nine months**, and the sequencing above matters far more.

Genuinely parallel once W0 lands: W1 with W2; W5 with W6; W7 with W8 once both their prerequisites are
met.

---

## 7. Two decisions the owner must make

These are not engineering calls and the programme cannot make them:

1. **Is the Critical Reasoning Kernel a real reasoner or a ledger?** Component #5. Building a genuine
   critic pass is roughly 8–12 days on top of wave 5. Declaring it a ledger and correcting the matrix
   is under a day. Both are defensible; only silence is not.
2. **Is Temporal adopted?** Component #42. Blueprint Rev 3 decision D9 makes it optional pending an
   owner-signed decision that does not exist. This programme assumes **not adopted** and deletes the
   routing branch. Adopting it instead adds roughly 15–20 days.

---

## 8. Definition of done

The programme is complete when all of the following hold:

- All ~80 register findings are CLOSED, each with a test and, where applicable, runtime evidence.
- All 70 inventory components carry an executed disposition. **Zero components remain
  IMPLEMENTED_BUT_ISOLATED, STUB or SIMULATED.** A component is either INTEGRATED or gone.
- Every certification gate G1–G12 passes with its stated artefact.
- The §37 aura certification, §38 command certification and §39 critical-thinking certification have
  all been executed with captured evidence.
- A re-run of this audit's four probes reproduces none of the four defects.
- No canonical document asserts a capability that the then-current classification does not support.

At that point the scorecard should be re-derived from evidence rather than adjusted, and the release
block in `PROJECT_CANONICAL_STATE.json` re-evaluated against `docs/EXTERNAL_GATES.md`.
