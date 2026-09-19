# VAN — Independent Implementation Audit Brief

**For:** a second auditor (ChatGPT or any other), working independently of the first.
**Purpose:** find the gap between what VAN's documents say it does and what its code
actually does when run — then let the two audits be compared and consolidated into one
closure plan.
**Repository:** `Vanguduza/Van`, branch `claude/van-system-audit-ysgtcd`.
**Date of brief:** 2026-09-19.

---

## 0. The one rule

**Do not ask for the first audit's results until you have produced your own.**

A first audit of this repository exists. Its findings, its component ledger and its list of
known gaps are deliberately withheld from this document. You will be given them at the
reconciliation step in Part 7, after you have written down what you found.

This is not secrecy for its own sake. If you read the first audit first you will confirm it,
and the entire value of a second audit — catching what the first one missed — is gone. The
first audit is not a baseline to check against. It is a peer whose work you are about to
independently duplicate, so that the two can be compared and the disagreements investigated.

Work Parts 1 through 6. Produce the four artefacts in Part 5. Then ask for the first audit's
results and do Part 7.

**One honest complication.** The first audit's work is *in the repository you are about to
read*. Withholding it from this document does not remove it from the tree. These are the
files that will anchor you if you open them early:

```
docs/VAN_WHOLE_SYSTEM_IMPLEMENTATION_AUDIT_AND_CERTIFICATION_REV_1.md   the first audit's report
evidence/van-system-audit/findings.json                                 its findings register and closures
evidence/van-system-audit/component_ledger.json                         its component ledger
evidence/van-system-audit/INDEPENDENT_AUDIT_BRIEF.md                    this brief, with its results attached
git log                                                                 20 commits of its remediation
```

You are not forbidden from reading them — you are auditing a real repository and its history
is part of it. But read them *after* your own sweep, for the same reason the results are
withheld here. If you read them first, say so in your report, so the consolidation knows how
much independence the second opinion actually has.

## 1. What VAN is

VAN is a personal intelligence system built for a single owner. Its documents describe:

- **An Android app** that is the owner's surface: a floating assistant overlay that lives on
  top of other apps, a Command Centre, a voice interface (wake word, speech in, speech out),
  a trading read-surface, and an animated embodiment ("the aura").
- **A FastAPI gateway** (`backend/van_gateway/`) that is the authority boundary: it
  authenticates the owner's device, classifies every action, gates the dangerous ones behind
  biometric approval, records an audit ledger, and dispatches work.
- **Hermes**, an agent runtime that actually executes work. **It is not in this repository.**
- **VATI**, a trading system (`trading/`) with risk authority, strategy, execution and a
  ledger.
- **A browser and automation fabric** — Stagehand-based browsing and n8n automation, both
  external runtimes.
- **A Google intelligence mesh** — Gmail, Calendar, Drive, Tasks, Contacts, NotebookLM.
- **A cognition layer** — epistemics, owner modelling, symbiotic growth, strategic memory,
  critical reasoning, evolution tracking.

The canonical documents are in `docs/` — 31 markdown files, ~13,700 lines. The most
load-bearing are:

| Document | What it governs |
|---|---|
| `VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md` | The whole product; gate definitions |
| `VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md` | Overlay, presentations, lifecycle, source boundaries |
| `VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md` (and REV3) | Trading contracts, sizing, risk |
| `VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`, `..._DEPLOYMENT_BLUEPRINT_REV5.md` | Trading deployment |
| `VAN_BROWSER_INTELLIGENCE_AUTOMATION_FABRIC_REV_1_2_EXPERT_REVIEW.md` | Browser autonomy tiers, injection containment |
| `VAN_OWNER_AGENT_RUNTIME_REV3_EXPERT_REVIEW.md` | Hermes contract |
| `GOOGLE_INTELLIGENCE_MESH.md` | Google capability set |
| `SECURITY_POLICY.md` | **Locked authority — pinned by SHA-256. Do not edit.** |
| `PROJECT_TRUTH_PROTOCOL.md` | Project context authority |
| `VAN_VISUAL_*` (7 files) | The embodiment, aura and visual acceptance |
| `VAN_REMEDIATION_PROGRAMME_REV_1.md` | The remediation gates |
| `VAN_WHOLE_SYSTEM_IMPLEMENTATION_AUDIT_AND_CERTIFICATION_REV_1.md` | The first audit's report |

### Do not trust the documents as evidence of implementation

This is the single most important instruction in this brief. The project's own
implementation matrix certified **33 of 36 workstreams "BUILT"** against a blueprint that
was not in the repository tree. Documents in this project have repeatedly asserted
completion that the code does not support. Use the documents to learn **what VAN is
supposed to do**. Use only the code to determine **what it does**.

Equally: do not trust the first audit's register (`evidence/van-system-audit/findings.json`),
its component ledger, or the git commit messages. They are all the first auditor's claims.
Verify anything you rely on.

---

## 2. Repository map

```
backend/     236 files   54,474 lines   Python — the gateway
trading/     148 files   16,160 lines   Python — VATI
android/     182 files   28,498 lines   Kotlin — the owner's app
tools/        25 files    3,503 lines   CI, ops, evidence tooling
tests/        11 files    1,687 lines   cross-cutting contract tests
hermes/        3 files      419 lines   profile pack for the external runtime
docs/         31 files   13,737 lines   canonical documents
```

### Backend modules (`backend/van_gateway/`)

```
action  approval  attention  audit  auth  automation  briefing  browser
capability  coherence  command  computer_use  context  context_compiler
decisions  degraded  epistemics  events  evolution  google  hermes
idempotency  knowledge  learning  mission  notifications  observability
ops  orchestrator.py  proactive  projects  reasoning  reminders  research
runtime_api.py  storage  trading  understanding  verification
app.py  — 59 HTTP routes
```

### Trading modules (`trading/vati/`)

```
accounts  app  arbiter  authority.py  backtest  contracts  core  execution
intelligence  learning  market_data  observability  risk  strategies  vtil  zse
```

### Android packages (`android/app/src/main/java/com/dial/van/`)

```
command  control  degraded  events  gateway  mission  notification  onboarding
overlay  queue  security  share  status  telemetry  trading  visual  voice
VanApplication.kt
```

Gradle modules: `:app`, `:visual-preview`. There is also a standalone JVM harness at
`android/verification/` (see §3).

---

## 3. What can and cannot be executed

You must know this before you interpret any test result.

### Runnable

```bash
python3 -m pytest backend/tests -q      # ~997 tests, in-process FastAPI
python3 -m pytest trading -q            # ~309 tests
python3 -m pytest tests -q              # 95 tests, cross-cutting contracts
python3 tools/ci/maturity_gate.py       # the register's own consistency gate
cd android/verification && gradle test --offline   # ~259 Kotlin tests, JVM only
```

### NOT runnable — and this is the central constraint

- **The Android app has never been compiled.** The Android Gradle Plugin cannot be fetched
  (`dl.google.com` is blocked by the environment's proxy). `:app` has never been through a
  Kotlin compiler.
  - `android/verification/` is a **JVM-only Gradle harness** that compiles a *subset* of the
    app's real source files — the ones with no Android or Compose imports. It points at
    `../app/src/main/java`, not at copies.
  - **Coverage: 43 of 113 Kotlin files, 6,232 of 19,185 lines (32%).** The other **68% has
    never been compiled by anything.**
  - There are **zero instrumented Android tests** (`androidTest`).
- **No live Hermes.** The agent runtime that executes work is not in this repo and is not
  deployed here.
- **No live n8n, no browser worker, no Stagehand.**
- **No trading venue, no broker, no market data feed.**
- **No deployed gateway.** All backend tests are in-process.
- **No end-to-end path has ever run.** Not once, in any environment reachable from here.

If you have an environment where you *can* build `:app`, **do that first**. It is the single
highest-value action available to this project, and it is not available to the first auditor.

---

## 4. The audit method

### 4.1 The disease to look for

The characteristic failure in this codebase is **not** missing code. It is code that exists,
is well written, is sometimes even tested — and is never reached at runtime. Examples of the
shape (these are the *pattern*, drawn from the general class, not a list of answers):

- a class with no constructor call anywhere in production
- a method with zero call sites
- a capability in a registry with no executor behind it
- an enum whose values no screen ever renders
- a service instantiated only by its own tests
- a route declared and never registered, or a transport method with no route
- a value computed every frame and consumed by nothing
- a "policy" object that is read but never written, or written but never read

A document says the feature exists. A grep says the code exists. Neither tells you it runs.
**The only question that matters: is there a path from an owner action to this code?**

### 4.2 The maturity vocabulary

Classify every component you assess into exactly one of these. Do **not** collapse anything
into a generic "implemented".

| Class | Meaning |
|---|---|
| `ABSENT` | Documented; no code |
| `STUB` | Code exists; returns a fixed or fabricated answer |
| `SIMULATED` | Reports a state it does not measure |
| `PARTIAL` | Some declared behaviour present, some missing |
| `IMPLEMENTED_BUT_ISOLATED` | Complete and correct; nothing in production calls it |
| `NO_CONSTRUCTOR` | Class exists; never instantiated in production |
| `NO_CALLER` | Function exists; zero production call sites |
| `NO_ROUTE` | Handler/transport exists; no HTTP route reaches it |
| `NO_PRODUCER` / `NO_CONSUMER` | One side of a data flow is missing |
| `TEST_ONLY` | Only its own tests construct or call it |
| `REGISTRY_ONLY` | Declared in a registry with nothing behind it |
| `READ_ONLY` / `WRITE_ONLY` | Data structure only ever read, or only ever written |
| `INTEGRATED` | Real producer, real consumer, invoked production path |
| `E2E_VERIFIED` | Integrated **and** exercised end to end against real dependencies |

### 4.3 The invariant a component must satisfy to count as done

For each component, answer all seven. A "no" anywhere means it is not done.

1. **Real producer** — something writes/creates this, in production code.
2. **Real consumer** — something reads/uses the result, in production code.
3. **Invoked production path** — trace it from an owner-reachable entry point (an HTTP route,
   an Android Activity/Service/gesture, a scheduled job). Name the entry point.
4. **Failure semantics** — what happens when it fails? Is failure distinguishable from
   success and from "not attempted"?
5. **Tests that would fail if it broke** — not tests that merely execute it. Break it
   mentally: does a test go red?
6. **Runtime evidence** — has it ever actually run? Where is the artefact?
7. **Owner-visible projection** — can the owner tell, from the app, whether this is working?

### 4.4 Distinctions to hold precisely

- **NOT IMPLEMENTED vs NOT VERIFIED.** Code that cannot be run here is not thereby absent.
  Say which one you mean, always.
- **Absent vs unreachable.** "There is no margin model" and "there is a margin model nothing
  calls" are different findings with different fixes.
- **Blocked vs unfinished.** A feature waiting on an owner-supplied ML model is not the same
  as a feature nobody wired.
- **Compiled vs correct.** Compilation certifies nothing. Neither does a passing test that
  asserts only that a function returns.

---

## 5. Required output

Produce **four** artefacts.

### 5.1 Component gap ledger

JSON, so the two audits can be diffed mechanically. One object per component you assessed:

```json
{
  "component": "MissionBinder",
  "path": "backend/van_gateway/mission/binding.py",
  "documented_in": "docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md §N",
  "maturity_class": "NO_CONSTRUCTOR",
  "producer": null,
  "consumer": null,
  "production_caller": null,
  "entry_point_trace": "none found; searched app.py, orchestrator.py, runtime_api.py",
  "failure_semantics": "n/a — never runs",
  "tests": "backend/tests/test_mission_binding.py (constructs it directly)",
  "runtime_evidence": null,
  "owner_facing_projection": null,
  "disposition": "WIRE",
  "evidence": ["backend/van_gateway/mission/binding.py:12", "backend/van_gateway/app.py (no match)"],
  "confidence": "high",
  "effort": "M"
}
```

`disposition` ∈ `WIRE` | `COMPLETE` | `REPLACE` | `DELETE`.
`effort` ∈ `S` (<1 day) | `M` (1–3 days) | `L` (>3 days).
`confidence` ∈ `high` | `medium` | `low` — say low when you could not execute the check.

**Every claim must cite `path:line` or an explicit "no match" search you ran.**

### 5.2 Defect findings

Anything that is wrong rather than merely unwired — a security hole, a wrong calculation, a
state machine that can't reach a state, a contract two sides disagree about:

```json
{
  "id": "X-SEC-001",
  "severity": "P0",
  "title": "one line",
  "description": "what is wrong",
  "evidence": ["file:line", "file:line"],
  "impact": "what the owner experiences",
  "remediation": "what to do",
  "confidence": "high"
}
```

Severity: `P0` unsafe/data-loss/authority bypass · `P1` core feature does not work ·
`P2` degraded · `P3` quality · `P4` cosmetic.

### 5.3 Documentation-to-code traceability

For each major documented capability: is it `ABSENT` / `PARTIAL` / `PRESENT_UNWIRED` /
`WIRED` / `VERIFIED`? Name the document section and the code. Flag every place a document
asserts something the code contradicts.

### 5.4 Narrative

800–1,500 words: what is actually built, what is theatre, what would break first for a real
owner, and what you could not determine and why.

---

## 6. Where to push hardest

These are the first audit's known weak spots. They are the likeliest places for it to have
missed something.

1. **Android, everything except pure logic.** 68% has never been compiled. Compose wiring,
   resources, manifest, `R` references, the Rive path, Activity and Service lifecycles. The
   first audit could only check these by reading and by static analysis. Expect real compile
   errors: one was already found that way — a class carrying two `companion object`
   declarations, which Kotlin forbids, meaning it could never have compiled. Assume more.
2. **The cognition / understanding / evolution layer.** `backend/van_gateway/epistemics/`,
   `understanding/`, `evolution/`, `reasoning/`, `learning/`. Thousands of lines of
   well-written, well-tested code implementing the most abstract parts of the documents.
   Abstraction plus good tests is the combination that most reliably hides unreachability,
   because everything looks healthy from the inside. Trace each entry point yourself.
3. **The Google mesh.** `backend/van_gateway/google/`. Registry declarations vs actual
   executors vs actual routes. Count all three and compare.
4. **The trading stack end-to-end.** `trading/` is 16k lines with its own tests. Whether the
   risk authority genuinely gates the execution path, or is merely consulted, deserves an
   independent read.
5. **Cross-language contracts.** The Android client and the gateway must agree on route
   paths, payload shapes, header names, status codes, enum values, idempotency keys. The
   first audit checked a handful. There are 59 routes.
6. **Database schema vs models.** `backend/van_gateway/storage/` — schema v20. Look for
   columns written and never read, models with fields the schema lacks, migrations that
   don't round-trip.
7. **Error and failure paths.** Almost all tests are happy-path. What happens on a
   half-written row, a revoked device mid-command, a clock skew, a duplicate delivery?
8. **The recent commits themselves.** The last 20 commits on this branch are remediation
   work. Review them as you would any pull request. Two scripted errors are known to have
   occurred during it: nine files were corrupted by a bad string operation, and
   `getValue`/`setValue` imports were deleted from nine files by an "unused import" sweep
   that could not see property delegates. Both were caught and fixed. Assume others were
   not.
9. **Whatever a finding-driven audit would skip.** The first audit worked a fixed list of
   defects. A list is a filter: anything not on it was never examined. Sweep structurally
   rather than by list — every module, every route, every exported symbol — and you will
   cover ground it did not.

---

## 7. Reconciliation

Once your own output is written down and submitted, ask for the first audit's findings
register and component ledger. Then produce:

1. **Agreed** — both audits found it. Highest confidence; schedule first.
2. **Only the first audit found it** — do you concur? If not, say why; a false finding
   matters as much as a missed one.
3. **Only you found it** — the payload of this exercise. Rank by severity.
4. **Contradictions** — where the two disagree on the facts. These need a third check, and
   the resolution should be an executable test, not an argument.
5. **Consolidated closure plan**, ordered by *what unblocks the most*:
   - **Tier 0 — Make it buildable.** Nothing else can be trusted until `:app` compiles.
   - **Tier 1 — Wire what exists.** The `WIRE` dispositions. Cheapest real capability gain.
   - **Tier 2 — Fix what is wrong.** P0/P1 defects.
   - **Tier 3 — Build what is absent.**
   - **Tier 4 — Owner supply and deployment.** Models, keys, hosts, decisions.
   - **Tier 5 — Prove it.** End-to-end journeys, on a device, against a real Hermes.
   Each item: owner, effort, dependency, and **the test that will prove it done**.

---

## Appendix A — Commands

```bash
# Test suites
python3 -m pytest backend/tests -q
python3 -m pytest trading -q
python3 -m pytest tests -q
python3 tools/ci/maturity_gate.py
cd android/verification && gradle test --offline

# Find the disease: Python symbols with no production reference.
# An AST scanner, not a grep — it separates "referenced nowhere" from "referenced only by
# its own tests", which is the distinction that matters and the one grep cannot make.
python3 tools/audit/reachability.py                    # backend/van_gateway
python3 tools/audit/reachability.py trading/vati
python3 tools/audit/reachability.py --json             # to diff against your own pass
python3 tools/audit/reachability.py --include-models   # keep pydantic/enum subclasses

# Read its caveats. It excludes pydantic models and enums by default because FastAPI
# constructs them from the wire, and it cannot see dynamic dispatch — a registry keyed by
# string, a getattr, an entry point. Its output is a worklist, not a verdict.
# There is no equivalent for Kotlin. Writing one is a worthwhile contribution.

# Android: what is never compiled anywhere
#   compare `find android/app/src/main/java -name '*.kt'`
#   against the kotlin.include(...) list in android/verification/build.gradle.kts

# Routes declared vs handlers present
grep -oE '@app\.(get|post|put|patch|delete)\("([^"]+)"' backend/van_gateway/app.py

# The first audit's own artefacts (treat as claims, not evidence)
evidence/van-system-audit/findings.json
evidence/van-system-audit/component_ledger.json
tools/ci/maturity_gate.py
```

Environment note: `dl.google.com` is blocked here; Maven Central and plugins.gradle.org are
reachable. If your environment differs, say so in your report — it changes what your results
mean.

---

---

*A first audit of this repository exists. Its results are withheld until Part 7 by design.
Ask for them once your own findings are written down.*
