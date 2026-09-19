# VAN closure programme — handoff

**Branch:** `claude/van-system-audit-ysgtcd` · **HEAD at writing:** `85cc5e6` · **Date:** 2026-09-19

This document exists so the next agent can pick the work up cold. It is written to be
argued with. Where it says "do X", X is what the evidence available at the time supported;
if you find better, do better and say why. Where it says "never Y", that is a constraint
the programme has already paid for, and reversing it needs a reason in writing.

---

## 1. Read this first

VAN is a personal intelligence system: a FastAPI gateway (`backend/van_gateway/`, 166
modules), an Android app (`android/app/`, Kotlin/Compose), a trading system (`trading/`,
VATI), and an external agent runtime (Hermes) that **is not in this repository**.

A whole-system audit found one defect shape repeated across the codebase: **a component
built, never wired to a producer or a consumer, and then described in a canonical document
as BUILT.** Twenty classes in the cognition layer had no production caller at all. The
tests passed, the code was real, and nothing could tell the difference from outside.

This programme closes those findings and, more importantly, installs machinery that makes
the shape a CI failure rather than a discovery.

**State:** 121 findings registered, **121 closed**. 142 components inventoried, **142 at a
terminal state**. 1221 backend tests, 153 contract tests, 296 Kotlin tests. Schema v26. CI
green on both jobs; the debug APK publishes on every run.

**Both registers are at zero. That is not the same as VAN being finished, and the difference
is the whole of what is left.** Read this table before quoting either number.

| terminal state | components | what it means |
|---|---|---|
| `INTEGRATED_AND_EVIDENCED` | 111 | wired, tested, and a CI run executed the tests |
| `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` | 24 | the repository side is done; something outside it is absent |
| `DELIBERATELY_REMOVED_CANON_CORRECTED` | 7 | the code is gone and the gate checks it is gone |

The middle row is where VAN actually stands. Each of those entries names the specific thing
that is missing — a keyword-spotting model owner decision 2 declined, an unauthored `.riv`
asset, an n8n harness, a Stagehand runtime, a VEKL endpoint, an Obsidian vault, Exa egress
the owner switched off, a live market feed, a Postgres instance, a device that can play a
sound or speak, and above all **Hermes**, which is what drives a mission to `VERIFYING` and
is not in this repository. Read the `rationale` on each; "externally blocked" without a
named artefact is a way of saying "not done" that sounds finished.

The residual classes are the third axis and the honest measure of what is untrue:
30 `DELIBERATE_SCOPE`, 16 `ENVIRONMENT_UNVERIFIED` waiting on a physical device,
19 `EXTERNAL_RUNTIME` waiting on Hermes, 10 `OWNER_DEPLOYMENT_DECISION`, 3 `EXTERNAL_ARTEFACT`.

Run the census in the resume block rather than trusting these figures.

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

# The mutation harness, when you have changed behaviour rather than only added to it.
# It now has a Kotlin arm that drives Gradle, so it takes longer than it used to.
cd ../../backend && python3 ../tools/audit/mutation_suite.py

# What is left. No finding is OPEN any more, so the first line prints "none" — which is
# the point at which the residuals become the work. They are where the untrue things live.
python3 - <<'EOF'
import collections, json
findings = json.load(open("evidence/van-system-audit/findings.json"))["findings"]
print("OPEN findings:", [f["id"] for f in findings if f["current_status"] != "CLOSED"] or "none")

by_class = collections.defaultdict(list)
for f in findings:
    cls = (f.get("closure") or {}).get("residual_class")
    if cls:
        by_class[cls].append(f["id"])
print("\nresiduals — what is still untrue about closed findings:")
for cls, ids in sorted(by_class.items()):
    print(f"  {cls:26} {len(ids):3}  {', '.join(ids[:4])}")

# The component register. It is also at zero, so the useful reading is no longer "how many
# are left" but "how many are terminal on the strength of something outside this repository".
ledger = json.load(open("evidence/van-system-audit/component_ledger.json"))
comps = ledger["components"] if isinstance(ledger, dict) else ledger
unfinished = [c for c in comps if not c.get("terminal_state")]
print(f"\ncomponents: {len(comps)} inventoried, {len(comps) - len(unfinished)} terminal, "
      f"{len(unfinished)} NOT")
for disp, n in sorted(collections.Counter(c.get("disposition") for c in unfinished).items()):
    print(f"  {str(disp):10} {n:3}")
for state, n in sorted(collections.Counter(c.get("terminal_state") for c in comps).items()):
    print(f"  {str(state):42} {n:3}")

# The row that matters. Every one of these names an artefact that is not here.
blocked = [c for c in comps
           if c.get("terminal_state") == "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE"]
print(f"\n  {len(blocked)} components are complete in the repository and blocked outside it.")
print("  Read the rationale on each. 'Externally blocked' with no named artefact is a way")
print("  of saying 'not done' that sounds finished.")
EOF
```

**Check CI before anything else.** The last run this document saw finish green was 295 on
`85cc5e6`, both jobs and every step, with `van-debug-apk` uploaded. Do not take that on trust, and do not take it as
covering the commit you are standing on: read the newest run at
`https://github.com/Vanguduza/Van/actions` and fix what it says before anything else.
CI is the only authority for anything Android — the Android Gradle Plugin cannot be fetched
in this container (§4), so a local pass says nothing about the app. Nothing may be recorded
as evidenced while CI is red.

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

Six tools. Learn these before writing code; they are how the programme keeps itself honest.
Four of them run in CI on every push: the maturity gate, the authority map, the ledger
reconciler and the Kotlin reachability scanner.

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

41 invariants across 15 subject areas, each bound to exactly one owning document. A machine
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

Current: 166/166 modules reachable, zero dead modules, zero `NO_REFERENCE` symbols, 6
`TEST_ONLY` — and each of those six is *correctly* test-only (see §6.7).

**Candidates, not verdicts.** Dynamic dispatch is invisible to static analysis.

### `tools/ci/ledger_reconcile.py`

The maturity gate catches over-claiming. This catches the opposite, which is what the
register actually did: twenty-two components recorded as unreached had acquired a producer
in the course of closing some other finding, and nothing made updating the second register
a condition of closing anything in the first.

For every component that claims nothing reaches it and names `reachability_symbols`, it
asks the source whether that is still true. Two limits are inside the tool rather than
around it. A reference from dead code is not integration, so an entry may name
`reachability_excludes`; and an entry with no symbol to search for is reported
`CLAIMS_UNREACHED`-unverifiable rather than assumed correct.

**It must not shell out to anything.** The first version used ripgrep, which this container
has and the GitHub runner does not, so it passed here for four commits and died in CI.
`tests/contracts/` refuses `subprocess` in any `tools/ci` gate for that reason.

### `tools/audit/kotlin_reachability.py`

Protocol rule 31's Android half. Kotlin has no import closure to walk, so this reads the
manifest for declared components — scoped to `<activity|service|receiver|provider|application>`,
because reading every `android:name` picks up permissions — and follows construction from
there. `_strip_noise` removes comments and string literals first: a class name inside a log
message is not a caller.

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

57 commits at `85cc5e6`. Grouped by what changed, not chronologically.

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

### 6.8 The last block — the shapes the machinery could not see

The final thirteen commits are worth reading separately, because each found a defect that
every gate then in place agreed was fine.

- **P2-OPS-013** — CI assembled a debug APK and threw it away at the end of the job. Every
  Android claim in this programme rested on a run whose only durable output was a log line.
  The workflow uploads the APK now, with `if-no-files-found: error`, so a build that quietly
  stops producing one fails rather than publishing nothing.
- **P2-CTX-003** — `FORGETTABLE` decided what could be deleted and the export path walked a
  second list. VAN could therefore forget a category it would never have shown the owner.
  `ContextLifecycle` iterates the one set. The first test I wrote for this derived the
  expected answer from the same constant and compared it back; it is deleted, because a
  tautology in a test file reads exactly like coverage.
- **P1-CTX-004** — an owner preference could be ruled stale by a clock. `CANONICAL_OWNER`
  and `PROJECT_TRUTH` are excluded from `max_age_ms` now: the owner saying a thing once does
  not expire because a timer ran out, and the rule had passed its own tests while enforcing
  nothing.
- **P3-PERF-003** — five subsystems each had a budget and nothing owned the sum.
  `VanResourceEnvelope` takes the max of the five pressure contributions and the weaker of
  ladder and ceiling, and `NEVER_SHED` keeps the wake word, owner commands and degraded
  reporting outside the shedding ladder: a system that sheds its own ability to say it is
  degraded fails silently by construction.
- **P1-REASON-001** — §15's assumption gate had no producer, no consumer and no door. It is
  the clearest instance of the defect shape the whole audit is about: real code, real tests,
  unreachable from outside. It now has ingress routes, and `/actions/begin` refuses
  irreversible work on unsettled assumptions — with `UNDECLARED` treated as gated, because
  "nobody said" is not "nobody minds".
- **P2-GOOG-004** — six Google capabilities implemented end to end and reachable from no
  route, while the mesh advertised them. The route list was also held twice, and an unscoped
  route falls through to device authentication: adding six paths to one copy and not the
  other would have been a hole rather than an inconsistency. One `frozenset`, two readers.
- **P2-AND-015** — three owner surfaces existed as data layers with no screen. The
  notification one mattered most: the listener service read a policy on every arriving
  notification while nothing could ever write one, so VAN held one of Android's most
  invasive grants with its controls present only as functions.
- **P2-LEDGER-001/002** — I told the owner 65 of 142 components were unfinished without
  checking, and twenty-two were done. The maturity gate could not have caught it and is not
  at fault: it checks that claims are *backed*, and a component claiming to be unreached
  asserts nothing. `tools/ci/ledger_reconcile.py` covers the other direction, and its own
  first version shelled out to ripgrep, which the runner does not have.

**What these have in common is worth more than any of them individually:** every one was a
claim that was true of the code and false of the system. That is the only defect class this
programme has found, in every layer it has looked at.

---

## 7. What remains

Both registers are at zero, so what follows is not a list of open findings. It is what would
make VAN work, in the order I would do it.

### 7.1 — Hermes (the one that matters)

**No owner command can complete in this repository.** `MissionState.VERIFYING` has exactly
one caller and it is a test. In production there are four transition sites: owner
`CANCELLED`, the deadline sweeper's `EXPIRED`, the command ladder up to `RUNNING`, and an
internal-control route that accepts any target — which is the Hermes callback. So a command
goes `RUNNING` → nothing → `EXPIRED`.

The design is right: the gateway must not verify its own execution, which is what
`P0-VERIFY-001` closed. But the verification spine, the success contracts, the independent
readbacks and the assumption gate all sit behind a state nothing enters.

**Everything Hermes needs is now routed.** `/v1/runtime/actions/begin`,
`/v1/runtime/reasoning/assumptions`, `/v1/runtime/reasoning/premises`, the mission transition
route, the context admission routes. `P1-REASON-001` added the last of them. A Hermes that
calls these gets a working system; nothing else in this repository is between here and that.

### 7.2 — Gate 14, on the owner's device

16 `ENVIRONMENT_UNVERIFIED` residuals wait on it. The APK publishes on every CI run as
`van-debug-apk`, now with the certificate that signed it. The first install has been
attempted once and failed — see §7.3.

What it settles, in order of value: that the app installs and runs at all; that the three new
owner surfaces render; that the offline queue replays when connectivity returns
(`P1-AND-014`); that the runtime envelope's thresholds are right rather than reasoned
(`P3-PERF-003`).

### 7.3 — The install failure, still undiagnosed, but now diagnosable

A sideload attempt returned a bare "App not installed". Android parsed the manifest — the
dialog showed VAN's label and icon — so the package is well-formed and installation was
refused after parsing. The manifest has no `sharedUserId`, no custom permissions and no
`uses-feature`, so it is not a parse-level conflict.

**The leading hypothesis:** the debug keystore is generated per machine, a runner is a fresh
machine, so every run's APK carried a different key. An APK cannot then upgrade one from a
previous run, and any prior VAN install refuses this one on a signature mismatch — which
Android reports with exactly that dialog and no code.

`P2-AND-016` closed the half of this the repository owns. Every run now writes the APK's
certificate into `signing-identity.txt` inside `van-debug-apk`, so two runs can be compared
without the phone, and the owner can tell whether the build they are about to install can
replace the one already on it. `tools/ci/restore_debug_keystore.sh` will install an
owner-supplied `VAN_DEBUG_KEYSTORE_BASE64` before the build and validates it against the
credentials Android's debug config is hardcoded to use.

Run 297 on `23e74ce` is the first to record one: `CN=Android Debug`, SHA-256
`57200ab86b098d1f60fb2fac381bf6d14acb9116943d13a99017978de04f7c30`. **That is the baseline.**
The next run printing a different digest demonstrates the per-runner key rather than arguing
it; the same digest would mean the hypothesis is wrong and the install failure is something
else. Compare before you theorise.

**Two things are still open, and they are different in kind.** No such secret exists yet, so
runs still sign per-runner — that is the owner's to supply, because a signing key committed
here would let anyone with the repository install an upgrade over the owner's VAN and
inherit its data directory. And nobody has read the `INSTALL_FAILED_*` code from `adb
install`, so the hypothesis remains a hypothesis. **Do not record the install as fixed on
the strength of the signing work; it explains the symptom and has not been shown to cause
it.**

### 7.4 — What the absent artefacts would unlock

The 24 `EXTERNALLY_BLOCKED` components are not evenly weighted:

- **An on-device keyword-spotting model** turns the wake word on. Four components. Owner
  decision 2 declined Sherpa, so this is a decision to revisit, not a task to schedule.
- **A `.riv` asset** switches the embodiment from the native renderer to Rive.
- **An n8n harness and a Stagehand runtime** give the browser fabric something to actuate.
- **A live market feed and a margin model** are what VATI needs before it trades anything.

### 7.5 — Ingress-driven tests (protocol rule 19)

`P1-REASON-001` added the first: `/v1/runtime/actions/begin` had no test at all before it.
That is the execution ingress Hermes uses. The same is true of most runtime routes — they are
tested by calling their services, not by driving the route.

### 7.6 — Keep the machinery honest

Four gates now run in CI: the maturity gate, the authority map, the ledger reconciler and the
Kotlin reachability scanner. **Three of them were wrong while in use and each was caught by
mutating it, not by review.** The gate's `symbols_absent` matched `def` and `fun` only, so a
deleted class assertion passed by never matching. The reconciler shelled out to ripgrep,
which the runner does not have. The Kotlin scanner read every `android:name` in the manifest,
including permissions.

**The recurring lesson, four times in one pass:** overlapping guards hide which half is
load-bearing. A mutation that removes one and changes nothing is not reassurance — it means
neither guard is falsifiable, and neither is tested. When that happens, mutate both together
or split the predicate so they can be told apart.

### 7.7 — Deferred product work recorded as residuals

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
9. **I quoted a number to the owner that I had not checked.** "65 of 142 components
   unfinished" was a count of a register nobody had reconciled; twenty-two of those were
   done. Reading a register is not the same as verifying it, and the difference showed up
   as a false statement to the person who asked.
10. **I wrote a test that derived its expectation from the thing it was testing.** The
    export assertion built the expected set out of `FORGETTABLE` and compared it back. It
    passed unconditionally and looked exactly like coverage. Both the constant and the test
    are gone.
11. **A fixture made two orderings coincide.** The supersession-history test admitted facts
    newest-first, so `ORDER BY rowid` produced the right answer for the wrong reason. Any
    test of an ordering needs input whose order matches neither the storage order nor the
    expected one.
12. **A gate assumed its own environment.** `ledger_reconcile.py` shelled out to ripgrep and
    passed here, every time, for four commits. Only CI knew. The second time this programme
    was caught assuming the container it runs in is the machine that matters.

---

## 9. Where things live

```
backend/van_gateway/
  app.py                        create_app; routes; middleware; scheduler jobs
  orchestrator.py               the command path — gates, resolution, dispatch
  runtime_api.py                OwnerRuntimeApi — the runtime's ingress, incl. §15
  reasoning/kernel.py           assumptions, premises; only VERIFIED/FALSIFIED/SUPERSEDED
                                are caller-resolvable
  context/
    service.py                  facts, edges, supersession; resolve_requirement
    lifecycle.py                export / history / conflicts — one FORGETTABLE set
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
  storage/db.py                 SCHEMA_VERSION = 26; MIGRATIONS

tools/ci/maturity_gate.py       the truth gate
tools/ci/authority_map.py       invariant ownership
tools/audit/mutation.py         the mutation harness
tools/audit/mutation_suite.py   every mutation this programme relied on
tools/audit/reachability.py     TEST_ONLY vs NO_REFERENCE
tools/ci/ledger_reconcile.py    the other direction: components claiming to be unreached
tools/audit/kotlin_reachability.py  the same question for Kotlin, from the manifest
tools/ci/restore_debug_keystore.sh  an owner-supplied debug key, or a log line saying there
                                is none and what that costs
tools/ci/record_apk_signing_identity.sh  what actually signed the published APK

android/app/src/main/java/com/dial/van/
  runtime/VanResourceEnvelope.kt  one owner for the resource sum; NEVER_SHED
  command/modules/                MissionsModule, NotificationPolicyModule, SpeechModule
android/verification/             the pure-Kotlin harness (AGP is unreachable here — §4)

docs/project-state/AUTHORITY_MAP.yaml
docs/VAN_CONSOLIDATED_DEPLOYMENT_READINESS_CLOSURE_BLUEPRINT_REV_1.md   (Rev 2 content)
evidence/van-system-audit/findings.json        121 findings, closure records
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
