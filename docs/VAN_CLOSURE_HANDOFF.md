# VAN closure programme — handoff

**Branch:** `claude/van-system-audit-ysgtcd` · **HEAD at writing:** `e64379e` · **Date:** 2026-09-19

This document exists so the next agent can pick the work up cold. It is written to be
argued with. Where it says "do X", X is what the evidence available at the time supported;
if you find better, do better and say why. Where it says "never Y", that is a constraint
the programme has already paid for, and reversing it needs a reason in writing.

---

## 1. Read this first

VAN is a personal intelligence system: a FastAPI gateway (`backend/van_gateway/`, 165
modules), an Android app (`android/app/`, Kotlin/Compose), a trading system (`trading/`,
VATI), and an external agent runtime (Hermes) that **is not in this repository**.

A whole-system audit found one defect shape repeated across the codebase: **a component
built, never wired to a producer or a consumer, and then described in a canonical document
as BUILT.** Twenty classes in the cognition layer had no production caller at all. The
tests passed, the code was real, and nothing could tell the difference from outside.

This programme closes those findings and, more importantly, installs machinery that makes
the shape a CI failure rather than a discovery.

**State:** 113 findings registered, 111 closed, 2 open. 1168 backend tests, 93 contract
tests, 270 Kotlin tests. Schema v24. Every gateway module reachable from an entry point.

### Resume in ten minutes

```bash
cd /path/to/Van
git checkout claude/van-system-audit-ysgtcd && git pull

# The two gates. Both must pass before you commit anything.
python3 tools/ci/maturity_gate.py      # every claim in the ledgers is backed
python3 tools/ci/authority_map.py      # every invariant owned once, implemented, tested

# The suites. Note PYTHONSAFEPATH — see §4.
cd backend && PYTHONSAFEPATH=1 python3 -m pytest -q
cd .. && PYTHONSAFEPATH=1 python3 -m pytest -q tests/contracts
cd android/verification && gradle clean test --console=plain

# What is left
python3 -c "
import json; d=json.load(open('evidence/van-system-audit/findings.json'))
[print(f['id'], f['severity'], f['title']) for f in d['findings'] if f['current_status']!='CLOSED']"

# Then read §7 of this document.
```

**Check CI before anything else.** Run 277 on `e64379e` was in flight when this was
written. `https://github.com/Vanguduza/Van/actions` — if the Android job is green, Gate 1's
build half is complete and you should record it; if not, fix what it says first.

---

## 2. Non-negotiable rules

These come from the original audit brief and from an independent review that found four
real defects in work I had already reported closed. Both are binding.

### From the audit brief

1. **Classify precisely.** `ABSENT` / `STUB` / `SIMULATED` / `PARTIAL` /
   `IMPLEMENTED_BUT_ISOLATED` / `INTEGRATED` / `E2E_VERIFIED` / `PRODUCTION_CERTIFIED`.
   Never collapse into "implemented".
2. **NOT VERIFIED is not NOT IMPLEMENTED.** Never substitute one for the other.
3. Do not rely primarily on documentation. Do not treat compilation as certification.
4. **Do not create fake implementations. Do not create placeholder tests and call them
   coverage.**
5. Do not downgrade owner requirements silently.
6. Do not report external actions complete before verification.
7. Develop, commit and push **only** to `claude/van-system-audit-ysgtcd`. Do not open a
   pull request unless explicitly asked.
8. `docs/SECURITY_POLICY.md` is **locked, pinned by SHA-256. Do not edit it.** It may be
   named as an authority; that is a statement about where authority lives, not a change.

### The closure protocol

> **For every CLOSED finding, construct a counterexample in which the implementation would
> appear green while the user's requested real-world outcome is false. If that
> counterexample still passes, the finding is not closed.**

That sentence is the whole discipline. The rest is how to apply it:

1. **Test the semantic claim, not the plumbing.** "Delete source X" is not verified by "the
   notebook still exists"; it is verified by observing that X is absent.
2. **Bind verification to the exact affected object.** Carry the resource ID, source name,
   message ID, trade ID, repository SHA. Never `exists=true`, counts, HTTP success, or
   executor-reported success.
3. **Support post-execution binding.** A create whose ID the provider assigns must not stay
   permanently unverifiable. See §7.3.
4. **Never collapse UNKNOWN into FAILURE or SUCCESS.** Keep `VERIFIED_SUCCESS`, execution
   failure, `UNVERIFIABLE`, cancellation, policy refusal, unsafe refusal, expiry and
   external unavailability distinct. Learning, scoring and owner modelling must not treat
   all non-success as failure.
5. **Audit downstream consumers of every new state.** Ask: what incorrect conclusion could
   another subsystem draw from this value?
6. **Fail-closed is not capability-complete.** Making unavailable functionality explicitly
   unavailable is valid closure of a false-capability claim. It is not completion of the
   capability.
7. **Distinguish maturity levels.** Registered / wired / configured / health-visible /
   policy-safe / executor-present / runtime-qualified / verified end-to-end / owner-usable
   are different. Do not use `INTEGRATED_AND_EVIDENCED` unless the final claimed level is
   demonstrated.
8. **One source of truth.** A build guard must read the value it guards. Never mirror
   `minSdk`, action-class ceilings, runtime versions or supported API levels into a second
   constant whose drift another test happens to catch.
9. **Check environmental capability, not API level.** Android API support does not prove a
   feature exists on a device. Voice, biometrics, notification access, overlay permission
   and background execution need runtime probes and honest degraded states.
10. **Separate transient commands from durable memory.** Do not convert every mission into
    a standing intent, preference or decision pattern. Promotion needs evidence.
11. **Memory keeps provenance and confidence.** What caused it, whether the owner stated it
    or VAN inferred it, scope, recency, contradiction state, and a reversible path. Never
    let repeated system-generated observations look like repeated owner evidence.
12. **Learning must never mint authority.** Re-check every indirect path by which success,
    inference, promotion or repetition could widen an action class, standing permission,
    data access or weaken a gate.
13. **Verification must be causally attributable.** "Trading is halted" is not enough; the
    relevant *owner* halt must be represented.
14. **Never verify an executor with its own report.** HTTP 2xx, n8n status, Hermes DONE,
    Stagehand success, a model assertion — all execution claims, not verification.
15. **Negative and adversarial tests are mandatory.** Happy path, false positive, false
    negative/degraded, authority boundary, and a mutation proving the invariant is
    load-bearing.
16. **Test the family, not the instance.** If source-delete verification was weak, inspect
    add/create/update/delete. If one outcome was misclassified, inspect every terminal
    state.
17. **Producer and consumer together.** A store with a producer and no consumer is still
    dead architecture. Closure needs producer → durable state → consumer → observable
    behaviour.
18. **No "conceptually active" features.** Either a demonstrated production effect, or
    explicitly classified as observational / not-yet-operative.
19. **Check reachability from real ingress.** Drive commands through the actual
    gateway/orchestrator path, not by instantiating services.
20. **Test the joins.** Android→gateway, command→mission, mission→Hermes, activity→verifier,
    verifier→outcome, outcome→learning, notification→attention, VATI→trading, Google→readback.
21. **Prevent silent partial completion.** Multi-step operations must represent which
    substeps succeeded and whether compensation is possible.
22. **Owner-visible language derives from semantic state.** Never collapse submitted /
    accepted / running / completed / verified / unverifiable / blocked / expired into "done".
23. **Identify residuals honestly.** Do not erase them to improve the closed count.
24. **A closed finding must not create a new hidden finding.** Review your own diff for new
    empty registries, orphaned state, duplicated constants, dormant branches, unbounded
    inference, broadened authority, unprotected routes, weakened verification.
25. **Static source assertions are guardrails, not substitutes** for executing the
    production path.
26. **For build assertions, prove the release task executes them** — not that a
    `dependsOn(...)` string exists.
27. **Run the whole regression suite after each closure group.**
28. **Do not claim independent certification from local output.** Record local verification
    separately from CI. Implementation-complete and CI-uncertified are different states.
29. **Run CI on the exact SHA being certified.**
30. **Counterexample review before every closure commit.** How could this tell the owner
    something happened when it did not? How could it learn the wrong lesson? How could
    authority widen? How could the UI overstate readiness? Add a test for each answer.
31. **Before declaring complete, do a repository-wide sweep independent of
    `findings.json`.** The register is evidence, not the universe of possible defects.

### Required closure record

Every finding must carry: exact semantic requirement; production entry point; production
execution path; authoritative postcondition; independent verifier/evidence source;
failure/degraded behaviour; authority boundary; owner-visible result; learning/memory
consequence; negative and adversarial tests; full-suite evidence; commit SHA; CI status for
that SHA; residual limitations; and **`falsified_by`** — what would show the claim is wrong.

---

## 3. The machinery

Four tools. Learn these before writing code; they are how the programme keeps itself honest.

### `tools/ci/maturity_gate.py`

Enforces that the ledgers do not over-claim. Reads
`evidence/van-system-audit/findings.json` and
`evidence/van-system-audit/component_ledger.json`.

Rules: every finding assigned a remediation gate; every non-integrated component carries
exactly one disposition; `INTEGRATED_AND_EVIDENCED` requires producer, consumer, production
caller, tests and runtime evidence; `DELIBERATELY_REMOVED` proves the file or symbols are
absent; a CLOSED finding names change, tests and evidence with every cited path existing;
bidirectional coverage; forbidden routes stay absent.

**It refused five of my closures during this programme and was right every time.** Four of
those were the same error: claiming `INTEGRATED_AND_EVIDENCED` while naming a residual the
repository cannot finish. If it refuses you, the classification is usually the bug.

`tests/contracts/test_maturity_gate.py` injects each defect shape and asserts rejection — a
gate that only ever passes proves nothing.

### `tools/ci/authority_map.py` + `docs/project-state/AUTHORITY_MAP.yaml`

37 invariants across 12 domains, each bound to exactly one owning document. A machine
cannot detect that two prose documents contradict each other; it *can* detect two claiming
authority over the same subject, which is the condition that lets a contradiction survive.

Enforces: one owner per subject; owners drawn from a declared `owning_documents` list
(otherwise a derived document acquires authority by being cited — that is how
`IMPLEMENTATION_LEDGER.md` came to certify workstreams against a blueprint it does not own);
no duplicate statements; every path exists; every invariant has an implementation and a
test; every cited finding is in the register and **closed** — an invariant resting on an
open finding is describing an intention.

**When you close a finding that establishes an invariant, add it here.**

### `tools/audit/mutation.py` + `mutation_suite.py`

The mutation harness. `mutation_suite.py` holds all ~60 mutations this programme relied on,
so "N caught" can be re-checked rather than believed.

```bash
cd backend && python3 ../tools/audit/mutation_suite.py    # ~6 minutes
```

To mutate your own work:

```python
import sys; sys.path.insert(0, "../tools/audit")
from mutation import run
run([("path/to/file.py", "original text", "mutated text", "what this breaks")],
    ["tests/test_yours.py"], root=".")
```

**A survivor is information, not a nuisance.** Every survivor in this programme named a
real gap. Two examples worth internalising: the notebook source verifier could fall back to
a weaker observation on a path the command layer cannot currently reach; and a no-demotion
invariant was held by coincidence between two mutually-redundant guards, so mutating either
survived an example-shaped test.

**Known harness hazard, already fixed:** the first version restored a mutated file with
`shutil.move`, which preserves the backup's mtime; that mtime was older than the `.pyc`
written while mutated, so Python reused the *mutated* bytecode on the next run. Verdicts
reached that way are worthless in both directions. The restore now rewrites the text and
purges every `__pycache__`. **Do not "optimise" that back.**

### `tools/audit/reachability.py` + `entrypoint_reach.py`

AST scanners. `reachability.py` distinguishes `NO_REFERENCE` from `TEST_ONLY` for
module-level symbols; `entrypoint_reach.py` computes the import closure from `app.py`,
`orchestrator.py`, `runtime_api.py`.

Current: 165/165 modules reachable, zero dead modules, zero `NO_REFERENCE` symbols, 6
`TEST_ONLY` — and each of those six is *correctly* test-only (see §6.6).

**Candidates, not verdicts.** Dynamic dispatch is invisible to static analysis.

---

## 4. Environment facts that will trip you up

**The Android Gradle Plugin cannot be fetched here.** The proxy refuses `dl.google.com`
with 403 on CONNECT. Maven Central and `plugins.gradle.org` return 200. So `:app:*` tasks
cannot run locally at all. `android/verification/` is a standalone Kotlin/JVM Gradle harness
that compiles the *shipping* app's pure decision files on the JVM — it is a convenience, it
is **not** the Android build, and its passing has never been evidence the app compiles.

**`python -m pytest` is not what CI runs.** CI runs the bare `pytest` binary, which does
**not** put the working directory on `sys.path`. `python -m pytest` does. A contract test
importing `backend.van_gateway...` passed locally and failed the first time CI reached it.
Use `PYTHONSAFEPATH=1 python3 -m pytest` to reproduce CI's import shape on the same
interpreter.

**This repository's bare `pytest` is a separate uv-managed install** with different
packages. Running it locally produces unrelated failures (`pydantic_settings` missing,
twelve fewer tests collected). Those are a local artefact, not a defect. Do not chase them.

**Beware `cmd | tail && git commit`.** A pipe's exit status is the last command's, so
`tail` returning 0 lets a failing gate through. I pushed a commit that way. Use
`set -o pipefail` and check `${PIPESTATUS[0]}`.

**Do not run the test suite concurrently with the mutation harness.** The harness mutates
files on disk; a concurrent suite reads the mutated tree and reports contamination as
failure.

**CI is the authority.** `van-ci` triggers on `main` and `claude/**`. Two jobs: `backend`
(maturity gate, authority map, backend tests, contract tests, gate self-tests, Hermes and
trading policy suites, automation fail-closed proofs, context-latency evidence) and
`android-and-visual-evidence` (pure Kotlin harness, `:app:testDebugUnitTest`,
`:app:assembleDebug`, `:app:lintDebug`, visual geometry, preview rendering).

`tools/ci/github-actions-ci.yml` must stay **byte-identical** to
`.github/workflows/van-ci.yml` — `install_github_workflow.py --apply` copies one over the
other, and it had drifted seventy lines behind, so running it would have silently deleted
most of CI. `tests/contracts/test_ci_workflow_is_what_it_claims.py` enforces the equality.

---

## 5. Architecture you need to hold in your head

### The command → verification spine

This is the load-bearing path and most of the programme's value is in it.

```
POST /v1/commands
  → orchestrator.handle()
      · authenticate, check nonce/expiry, refuse A5, require owner approval for A4
      · TypedCommandResolver.resolve(text) → CommandResolution
          mode = EXACT_ACTION | HERMES_INTERPRETATION_REQUIRED
          action_id, parameters, intent_id, verifier_type
      · ingress trust: third-party content is data, never a mutating command
  → CommandMissionLink.open(req, resolution=...)
      · exactly one mission per command (existing_for_command returns the open one)
      · mission_class = resolution.intent_id            (schema v21)
      · success_contract = contract_for(resolution)     ← the joint
      · constraints gain "unverifiable: <reason>" where no contract exists
  → mission states: CAPTURED → UNDERSTOOD → PLANNED → AUTHORIZED → RUNNING
      · deadline set at RUNNING; MissionDeadlineSweeper expires the silent ones
  → (Hermes executes; MissionBinder binds specialist activities)
  → MissionService.transition(target=VERIFIED_SUCCESS)
      · _perform_verification picks the verifier from success_contract.verifier_class
      · VerifierRegistry adapter observes the target system INDEPENDENTLY
      · refuses without a checkable contract, evidence, and zero unmet postconditions
  → terminal → LearningFeed records outcome, strategy outcome, decision outcome
```

**`backend/van_gateway/command/success_contracts.py` is the joint that was missing.**
Before it, `CommandMissionLink.open` created every mission with an empty `SuccessContract()`,
so `CommandResolution.verifier_type` was written by the resolver and read by nothing — **no
owner command could ever reach `VERIFIED_SUCCESS`**, including `halt trading`.

The rule for adding a contract: **a contract may only name a strategy whose observation
reaches a system independent of whoever did the work.**

### Registered verification strategies

In `backend/van_gateway/verification/production.py`:

| Strategy | Independent source | Status |
|---|---|---|
| `ledger-event` | VATI hash-chained ledger — trade readback | wired |
| `trading-halt` | VATI kill-switch ledger; refuses stale or broken chain | wired |
| `browser-evidence` | stored browser artefacts (weakest admissible) | wired |
| `api-readback` | notebook provider — notebook existence | wired |
| `notebook-source-readback` | notebook provider — **per named source** | wired |
| `repository-sha` | none — no git remote configured | `UnobservableStrategyVerifier` |
| `ci-run` | none — no CI API configured | `UnobservableStrategyVerifier` |

`UnobservableStrategyVerifier` returns `UNVERIFIABLE` **carrying the reason**, so "something
was promised and could not be checked" is distinguishable from "nothing was promised". That
distinction matters and both halves are tested.

### Three verification vocabularies, reconciled

`VerifierType` (action registry), `VerificationStrategy` (capability registry) and mission
`verifier_class` strings are the same small set in three spellings.
`backend/van_gateway/authority/descriptor.py::VERIFICATION_ALIASES` translates. Translation
is idempotent; an untranslatable name **raises** rather than passing through, because
forwarding one is how an unverifiable action comes to look verified.

### The canonical action descriptor

`backend/van_gateway/authority/descriptor.py`. Seven vocabularies described an action's
authority; this is a **derivation over them, not an eighth store**. It defines only `Gate`,
`Reversibility` and `EgressClass` — the three things that genuinely had no vocabulary. Two
tests assert it declares no `ActionClass` of its own and holds no table.

The load-bearing tests read the orchestrator's own source (comments stripped) and assert the
descriptor names the gate the orchestrator applies; three more assert the capability router
refuses for owner presence, authority ceiling and external disclosure exactly where the
descriptor says. **The routability gate was deliberately not rewritten to call the
descriptor** — churn with real risk in the one place that decides whether the owner gets
asked. Lockstep is what the finding needed.

Projected at `GET /v1/authority`.

### Learning, and the authority it must never mint

`LearningFeed` (`backend/van_gateway/learning/feed.py`) is the producer for every learning
and memory store. On a terminal mission it records: the outcome, the **strategy** outcome,
and the **decision** outcome.

`StrategyOutcome` is `SUCCESS` / `FAILURE` / `INCONCLUSIVE`. Only `VERIFIED_SUCCESS` and
`FAILED` are evidence about an approach; cancellation, policy refusal, unsafe refusal,
expiry, `UNVERIFIABLE` and `PARTIAL_SUCCESS` are `INCONCLUSIVE` and count toward neither
`runs` nor `success_rate`. This was a boolean whose `False` branch incremented
`failure_count`, so three owner cancellations would have demoted a strategy that had never
once failed.

`execution_strategies.max_action_class` records the ceiling a sequence was **exercised
under**; `permitted_for` refuses to offer a strategy to a mission whose envelope does not
reach it. The wider strategy is not hidden — concealing it would make the learning surface
lie — it is simply not an answer to a narrower question.

A structural test asserts no module under `learning/` or `evolution/` writes
`action_definitions`, `permission_grants`, `capability_registry`, `capability_grants`,
`standing_automation_authorities`, `automation_capabilities`, `domain_trust` or
`proactive_policies`, plus a test that every named table still exists.

### Owner memory and the intent horizon

`IntentContinuityGraph` promotes `EPHEMERAL` → `PROJECT` → `STANDING` on evidence: an owner
declaration, or three observations. Every promotion records what caused it, and the two
kinds of evidence stay distinguishable so VAN's own counting cannot read as something the
owner said. `/v1/understanding/intents` separates standing goals from one-off requests.

`DecisionFingerprints` records approvals and their outcomes and **infers no reason**.
`/v1/understanding/decisions` reports that explicitly, because an owner reading "no
falsified patterns" off a silent surface would take it to mean VAN's model of them is
accurate.

### Schema migrations added by this programme

| v | What | Why |
|---|---|---|
| 21 | `missions.mission_class`, `execution_strategies.max_action_class` | strategies keyed on a concept nothing named; authority ceiling |
| 22 | `idempotency.claim_count` | a recovered claim must be visible |
| 23 | `execution_strategies.inconclusive_count` | UNKNOWN recorded, not discarded |
| 24 | `intent_nodes.horizon`, `observation_count`, `promoted_reason`, `promoted_at_ms` | transient commands vs durable goals |

---

## 6. What was done

44 commits. Grouped by what changed, not chronologically.

### 6.1 The verification spine (the most important work)

- **P0-VERIFY-001** — `VerifierRegistry` was constructed only in tests; `create_app` never
  built one. Now built in `create_app`, and there is **no parameter to hand a receipt in**.
- **P1-VERIFY-003** — owner commands get success contracts. This is the one that made
  verification reachable at all.
- **P1-VERIFY-004** — a notebook source mutation was certified by the notebook still
  existing. A delete that silently failed satisfied the contract. Contracts now bind exact
  source names; expected sets stated in full, because a count is satisfied by the right
  number of the wrong sources.
- **P2-VERIFY-002** — unobservable strategies named with reasons.

### 6.2 Execution and causality

**P0-EXEC-001/002/003, P2-COH-001** — one mission per command; deadlines with a sweeper; one
owner-facing work-status projection across eleven executor vocabularies.

### 6.3 Security and trust

**P0-SEC-001/002, P1-SEC-005/006/007, P2-SEC-009, P2-AUTO-002** — control scopes that are
terminal rather than falling through to device auth; external events are data; atomic
idempotency claims; hash-chained audit with prune anchors; rate limiting; the fake-transport
route deleted; payment instruments unreachable.

### 6.4 Wiring the isolated

**P2-DEAD-001, P2-CU-001, P2-MEM-001, P2-EVO-001, P1-LEARN-002/003/004** — 163→165 modules,
all reachable; `ExternalEventIngestor`, `CredentialResolver`, `RepairService`,
`RelationshipCalibrationEngine` given routes; `context_compiler` deleted (duplicated
`ContextRetrievalService`); computer-use fabric kept and its missing executor made a runtime
refusal rather than a claim; owner-memory stores given a producer; external reality fed from
research; benchmark corpus absence reported.

### 6.5 Operations and governance

**P3-OPS-008/009/010/011/012, P0-OPS-011, P3-DOC-005** — recovery matrix (6 cells, 26
tests); backup drill scheduled; the CI installer that would have deleted CI; CI on the
certification branch; the invocation-dependent import; the authority map.

**P0-OPS-011 was found by writing the recovery matrix, not by an incident.** An `IN_FLIGHT`
idempotency claim had no lease, so a gateway that died between claiming a key and completing
it made that command **permanently unrepeatable** — and the key is part of the signed
request, so the owner could not work around it.

### 6.6 Android

**P0-AND-012** — **the app did not compile**, and had not for many commits.
`CommandCentreViewModel` was public and exposed the internal `CommandModule`;
`VanGatewayClient` called `toByteArray` on a `JsonObject`. Nothing here could see it: AGP
unreachable, the harness compiles only pure files, CI never ran on the branch. Confirmed
fixed by run `35449312512`.

**P0-AND-013** — two app-module tests asserted behaviour earlier closures had changed.
**P1-AND-014** — `ACCESS_NETWORK_STATE` missing, and the `SecurityException` swallowed by a
bare `runCatching { }`, so the offline queue's replay-on-recovery never fired and nothing
said why.

**P1-VOICE-002/003** — `minSdk` 26→31 with `assertVoiceRuntimeIsShippable` reading
`android.defaultConfig.minSdk` (it originally mirrored the value into a second constant);
and API 31 + no recognizer now reports `UNAVAILABLE` with a reason rather than a Sherpa tier
the app deliberately does not ship.

### 6.7 The six remaining `TEST_ONLY` symbols — all correct

`canonical_verification` (used by tests of the alias table), `reset_policy_cache` (test
helper), `assert_payment_action_is_owner_approved` (owner decision 3 leaves the payment path
deliberately unwired), `CiRunVerifier` and `RepositoryShaVerifier` (complete adapters waiting
on a source that does not exist here), `is_correlation_id` (validator). **Do not "wire" these
to make a number look better.**

---

## 7. What remains

Ordered by what I would do next. Reorder if you have reason.

### 7.0 — Get CI green (blocking)

Run 277 on `e64379e` was in flight at writing. The backend job has been green since
`654d937`. The Android job has progressed: compile ✅ → unit tests ✅ → lint (one error,
fixed in `e64379e`). If lint is now clean the Android job goes green for the first time.

**Do this first.** Nothing else should be recorded as evidenced while CI is red.

### 7.1 — `P2-CTX-003`: Owner Context Graph lifecycle governance

> The graph holds people, devices, accounts, decisions, policies, habits and relationships.
> Retention exists. Export, correction, erasure, revision history and conflict semantics do
> not.

**Where:** `backend/van_gateway/context/`, `backend/van_gateway/understanding/memory.py`,
`backend/van_gateway/ops/retention.py`. Owner surfaces in `understanding/api.py`.

**Prior art to follow:** `P2-MEM-002` closed "no owner-facing forget for the owner model,
evidence or reasoning ledgers" — read its closure record first; this is the same shape one
layer out, and its residual (the audit ledger and missions table are deliberately not
clearable) tells you where the boundary is.

**Execution sketch:**
- Export: `GET /v1/context/export` producing everything VAN holds about the owner, with
  provenance per assertion. Owner route, not internal control.
- Correction: already partly exists via `OwnerCognitiveModel.correct`. Check whether the
  context *graph* (facts, edges) has the same path; the owner model did.
- Erasure: a delete that **records that a deletion happened** without keeping what was
  deleted. The audit chain must stay intact — you cannot erase from a hash chain, so the
  right move is a tombstone plus an anchor, following `P3-OPS-001`'s prune-anchor pattern.
- Revision history: `context_snapshots` exists (schema v5). Check whether it is a producer
  or just a table.
- Conflict semantics: what happens when two facts contradict. §77's intent conflicts are a
  model; do not invent a resolver — surface the conflict.

**Counterexamples to defeat:** an export that omits inferred assertions (the owner would
believe VAN knows less than it does); an erasure that leaves the fact reachable through a
snapshot or an edge; a correction that supersedes without recording what it superseded.

### 7.2 — `P3-PERF-003`: whole-runtime resource envelope

> Always-available voice, the animated embodiment, local indexes, notification processing,
> context compilation, network connections and trading updates all compete on one phone.
> Each has its own budget; nothing owns the sum.

**Where:** `android/app/src/main/java/com/dial/van/visual/VanFrameBudget.kt` is the existing
per-subsystem budget and the finding's cited evidence. `VanEffectBudget.kt` too.

**Execution sketch:** declare one envelope (battery, memory, storage, CPU/GPU, thermal) and
make each subsystem yield against *it* rather than its own budget. `VanFrameBudget` is pure
and already in the verification harness include list, so the arbitration logic can be tested
locally without AGP — **put the decision logic in a pure file and add it to
`android/verification/build.gradle.kts`.**

**Environmental honesty (protocol rule 9):** you cannot measure thermal or battery here.
Declare the envelope and the yielding *policy*, test the policy with injected readings, and
record the measurement itself as `ENVIRONMENT_UNVERIFIED` pending Gate 14.

### 7.3 — Post-execution verification binding (the biggest architectural item)

Currently every verifier target is decided at command ingress. A create whose ID the
provider assigns is therefore **permanently unverifiable** — recorded as a `DELIBERATE_SCOPE`
residual on `P1-VERIFY-004`, and it should not stay one.

**The shape:**
1. Execution returns the created identity into the mission/activity record. The knowledge
   runtime already does this internally — `NotebookEnterpriseProvider.create_notebook`
   returns a `NotebookOperationResult` with `resource_id` and `correlation`. The identity
   exists; nothing carries it back to the mission.
2. `MissionService` gains a way to **enrich** a success contract after execution — not
   replace it. Enrichment must be append-only and must not be able to weaken an existing
   postcondition, or you have built a way for the executor to choose its own test.
3. The verifier then reads that exact object back.

**Where:** `backend/van_gateway/command/success_contracts.py`,
`backend/van_gateway/mission/service.py`, `backend/van_gateway/mission/models.py` (the
contract is a pydantic model on the mission row — enrichment needs a migration or a
structured update), `backend/van_gateway/knowledge/service.py::execute_authorized_action`.

**The counterexample that must fail:** an executor that reports a created ID which does not
exist, and a contract enriched from it that then "verifies" against the executor's own
claim. The enrichment must bind an identity the executor *asserts*, and the verification
must still be an independent readback of that identity. If the readback can be satisfied by
anything the executor controls, you have re-created the defect `P0-VERIFY-001` closed.

**Also in scope:** `research.web.search` and `owner.context.read` currently get no contract
with recorded reasons. Post-execution binding does not help them (a search leaves nothing
independently readable). Leave them, and leave the reasons.

### 7.4 — Ingress-driven reachability tests (protocol rule 19)

Almost every test in this programme instantiates services directly. That is exactly the
blind spot that let `P0-AND-012` live.

**Build:** a test module that drives representative owner commands through `POST /v1/commands`
on the real app — signed, enrolled device, real orchestrator — and asserts the whole chain:
mission created with the right class and contract, activities bound, verification performed,
attention raised where expected, learning recorded, owner projection correct.

**Candidate commands:** `halt trading` (A4, verifiable), `delete the sources X from the
notebook enterprise notebook id N` (A4, source-exact), `research X` (A2, deliberately
unverifiable — assert the reason reaches the mission), a free-form instruction (Hermes path).

**Prior art:** `backend/tests/test_command_creates_mission.py` and
`test_command_execution_result.py` do some of this. Read them; extend rather than duplicate.

**Expect to find defects here.** This is the least-tested surface in the system.

### 7.5 — Subsystem join tests (protocol rule 20)

The joins, in rough order of risk:

| Join | Why it is risky |
|---|---|
| mission → Hermes → activity | Hermes is not in the repo; `MissionBinder` binds what it creates, and most missions produce no activities at all (`P1-LEARN-003` residual) |
| activity → verifier → mission outcome | the chain works; whether it is *driven* end to end is untested |
| outcome → learning → future routing | nothing consumes `permitted_for` yet (`P1-LEARN-002` residual) |
| notification → attention | `P0-SEC-002` closed the laundering; the positive path is thinner |
| Android → gateway | `VanGatewayClient` is not in the verification harness (needs `android.content.Context`); CI compiles it but nothing exercises it against a real gateway |
| Google → readback | `READ_BACK` covers Gmail and Drive only (`P1-AUTO-001` residual) |

### 7.6 — Repository-wide reconciliation (protocol rule 31)

**Do this earlier than last.** The two most serious defects found on the final day
(`P0-AND-012`, `P3-OPS-012`) were in neither the register nor the plan. They came from
turning on a gate.

Sweep for: dead modules, unused production symbols, empty adapters, unconsumed fields,
capabilities with no executor, verifier types with no independent observer, owner-facing
screens without live producers, stores without producers or consumers, scheduler jobs with
no effect, runtime declarations without live qualification, and documents claiming maturity
beyond runtime evidence.

`tools/audit/reachability.py` and `entrypoint_reach.py` cover the Python side. **The Kotlin
side has no equivalent** — an Android reachability scanner would be genuinely valuable and
does not exist. Consider writing one.

### 7.7 — Gate 1 completion and Gate 14

Gate 1 (Android build) was blocked when this programme started and **is no longer** — CI can
reach `dl.google.com`. Once the Android job is green, `:app:assembleDebug` has produced an
APK on a runner. Consider uploading it as a workflow artifact so there is a downloadable
build.

Gate 14 (physical S24) stays deferred per the owner's standing instruction: *leave physical
verification for last*. The 14 `ENVIRONMENT_UNVERIFIED` residuals are mostly waiting on it.

### 7.8 — Deferred product work recorded as residuals

Not defects; deliberate scope. Read `falsified_by` on each before touching it.

- **`P0-EXEC-001`** — missions stop at RUNNING; nothing drives them to VERIFYING because
  Hermes reports completion and Hermes is not here. **This is the single biggest gap between
  the architecture and a working product.**
- **`P1-LEARN-002`** — nothing consumes `permitted_for`. Learning records and reports; it
  does not steer. The guard is deliberately in place *before* anything can act on it.
- **`P2-MEM-003`** — nothing sets `owner_declared_standing`; there is no owner surface for
  "this is a standing goal". The parameter exists and is tested.
- **`P2-EVO-001`** — no benchmark suite has a task corpus, so no technology can be ADMITTED.
  That is §23's intended fail-closed state, reported on `/v1/eval`.
- **`P2-CU-001`** — no computer-use worker for any surface. `SURFACE_WORKERS` is empty and
  `begin()` refuses before writing. **Do not read this as computer use being complete.**

---

## 8. Mistakes I made, so you do not repeat them

Recorded because each cost real time and each is easy to repeat.

1. **I encoded a defect in a test.** `test_a_mission_that_was_never_verified_is_not_a_success`
   asserted `failure_count == 1` for an `UNVERIFIABLE` mission — pinning the collapse rather
   than catching it. When you write a test, ask whether it asserts what *should* be true or
   what merely *is* true.
2. **I reproduced the audit's own defect while closing it.** `unavailableReason` was, for
   twenty minutes, read only by tests. Run `reachability.py` on your own new symbols.
3. **A static checker took three attempts.** Column-zero-only missed the case entirely
   (exposure is in indented members); tracking enclosing visibility produced false positives
   on locals in a composable; brace-depth tracking settled it. **A checker written to catch
   one known error is worth only as much as its handling of everything it must not flag.**
4. **A static check that leans on the compiler to be honest is measuring the wrong thing.**
   My permission guard asserted `registered.isFailure` appeared but not that the binding
   existed, so a mutation leaving an undefined reference passed.
5. **I pushed with the gate failing** because of `cmd | tail && git commit`.
6. **I claimed `INTEGRATED_AND_EVIDENCED` four times while naming a residual the repository
   cannot finish.** The gate caught all four.
7. **I ran the suite concurrently with the mutation harness** and spent time on a
   contamination failure.
8. **I reported local test counts as though they were certification** for a configuration CI
   does not run.

---

## 9. Where things live

```
backend/van_gateway/
  app.py                        create_app; routes; middleware; scheduler jobs
  orchestrator.py               the command path — gates, resolution, dispatch
  command/
    resolver.py                 TypedCommandResolver → CommandResolution
    success_contracts.py        ← contract_for(): the verification joint
    mission_link.py             one mission per command
  mission/
    models.py service.py        state ladder; transition; _perform_verification
    verifiers.py                adapters; UnobservableStrategyVerifier
  verification/
    observations.py             ← the ONLY place independent observations live
    production.py               what create_app actually registers
  authority/descriptor.py       canonical ActionDescriptor (a derivation)
  learning/feed.py              the producer for every learning/memory store
  evolution/radar.py            StrategyLearning, radar, benchmarks, external reality
  understanding/                owner model, memory, api
  google/planes.py              credential planes
  computer_use/fabric.py        typed operations; SURFACE_WORKERS is empty
  storage/db.py                 SCHEMA_VERSION = 24; MIGRATIONS

tools/ci/maturity_gate.py       the truth gate
tools/ci/authority_map.py       invariant ownership
tools/audit/mutation.py         the mutation harness
tools/audit/mutation_suite.py   every mutation this programme relied on
tools/audit/reachability.py     TEST_ONLY vs NO_REFERENCE

docs/project-state/AUTHORITY_MAP.yaml
docs/VAN_CONSOLIDATED_DEPLOYMENT_READINESS_CLOSURE_BLUEPRINT_REV_1.md   (Rev 2 content)
evidence/van-system-audit/findings.json        113 findings, closure records
evidence/van-system-audit/component_ledger.json
```

---

## 10. How to know you are done

Not "all findings closed" — that number is a measure of the register, not the system.

**Done means:** CI green on the exact SHA; every closure record complete including
`falsified_by`; every residual honestly classified; the repository-wide sweep of §7.6
finding nothing new; and for each closed finding, a counterexample constructed in which the
implementation appears green while the owner's requested real-world outcome is false — that
still fails.

The last one is the only one that matters. The rest are how you get there.
