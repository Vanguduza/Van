# Fable Forensic Development & Remediation Method — Rev 1

**Method ID:** DIAL-FFDRM-R1
**Status:** LOCKED_GOVERNING_DEVELOPMENT_METHOD
**Applies to:** every DIAL-managed software, infrastructure, agentic, data, trading, automation, mobile, web, desktop and mixed project.

## 0. Executive contract

The Fable Forensic Development & Remediation Method adds a mandatory forensic layer between project preparation and implementation. It exists to prevent a project from being called complete because a class, schema, route, screen, test or document exists while the real production caller, authority boundary, effect or verification path is absent.

The mandatory causal chain is:

~~~text
requirement
→ canonical Product Truth
→ Development Unit
→ feature/capability
→ implementation
→ instantiation
→ registration
→ production caller
→ authority boundary
→ data/control flow
→ executor
→ observable result
→ persistence/audit
→ failure/degraded path
→ recovery
→ tests/evidence
→ independent verification
→ anti-regression guard
~~~

No project is FORENSIC_BUILD_READY until the preparation pack proves how every required capability will satisfy that chain. Where a repository already exists, an evidence-backed forensic audit must establish what is actually present, reachable, disconnected, contradictory, externally gated or absent.

## 1. Five independent proofs

### Product completeness
Every requirement resolves to Product Truth, a feature/capability, workflow/action, data/state, surface or machine outcome, and acceptance condition. No requirement may live only in prose.

### Causal integration completeness
Every capability proves producer → typed/durable state → consumer → production caller → authority → executor → observable effect → persistence/audit → verification.

A class with tests but no production caller is not integrated. A route with no caller is not a capability. A learning store that is written but never read into a decision is not learning.

### Experience completeness
Every user-facing capability proves feature → surface → interaction → action → runtime → state → owner-visible outcome. Every control traces backward to feature, action, runtime consumer, authority, state, failure behavior and verification.

### Forensic completeness
For an existing repository, prior audits and closure claims are hypotheses until corroborated. For greenfield projects, every planned capability must have a falsifiable causal contract before coding.

### Qualification completeness
Repository proof and live qualification remain separate. SPEC_READY, IMPLEMENTATION_READY, REPOSITORY_PROVEN, RUNTIME_QUALIFIED, DEVICE_QUALIFIED, LIVE_QUALIFIED and OWNER_ACCEPTED are distinct states.

## 2. Baseline doctrine

Before material work capture repository, branch, commit, Product Truth revision, schemas, runtime/deployment revisions, CI state, external dependencies, authoritative documents and previous audits.

For greenfield work, capture the accepted authority inputs and initial empty implementation state.

## 3. Bounded forensic workers

Large audits may use specialist read-only workers. Every worker returns:

~~~yaml
scope:
evidence:
proven:
suspected:
false_positives:
uncertainty:
uninspected:
~~~

Workers propose. The manager decides. Workers cannot change Product Truth or certify closure.

## 4. Mandatory trace

Every material capability is traced through requirement, implementation, instantiation, registration, production caller, authority boundary, input source, control flow, executor, observable result, persistent/audit result, failure, degraded behavior, recovery, tests, runtime evidence and owner-visible evidence.

Any non-applicable link must be explicitly justified.

## 5. Closed forensic taxonomy

Use only these top-level states:

~~~text
INTEGRATED_AND_EVIDENCED
IMPLEMENTED_NOT_REACHABLE
PARTIAL_IMPLEMENTATION
STUB_OR_PLACEHOLDER
TEST_ONLY
UI_ONLY
BACKEND_ONLY
CONTRADICTORY_IMPLEMENTATION
DEAD_OR_ORPHANED
EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
RUNTIME_CERTIFICATION_REQUIRED
DEVICE_CERTIFICATION_REQUIRED
OWNER_ACCEPTANCE_REQUIRED
DELIBERATE_SCOPE
SUPERSEDED_BY_BETTER_IMPLEMENTATION
OPEN_GAP
NOT_APPLICABLE
~~~

## 6. Root-cause clustering

Findings are not a flat to-do list. For every material gap derive symptom → missing causal link → root cause → dependent gaps → smallest structural remediation.

Root-cause families include tool surfaces narrower than authority, missing producers, write-only learning, enum/predicate drift without exhaustiveness tests, declared dependencies without injection points, UI not consuming runtime signals, design artifacts left unwired, verification that checks calls rather than postconditions, and runtime claims derived only from repository presence.

Repair root causes before dependent symptoms.

## 7. Adversarial second pass

A material audit requires an independent challenge pass. The adversary attempts to falsify findings, discover missed callers, identify test-only paths, contradictory docs/code, stale evidence, bypasses and simpler root causes.

Results are recorded as CONFIRMED, REFINED, REJECTED_FALSE_POSITIVE, NEW_FINDING or UNRESOLVED.

Author self-review does not satisfy independence where independence is required.

## 8. Runtime reproduction

When feasible, reproduce important findings through real application wiring, router registration, database semantics, process lifecycle, emulator/device paths, service configuration and host qualification. Static evidence remains valid when live reproduction is impossible, but must be labelled as static.

## 9. Deterministic execution ownership

Typed deterministic operations execute at the subsystem that owns their state and authority. Open-ended reasoning belongs to the reasoning/orchestration plane.

Preferred shape:

~~~text
typed request
→ deterministic resolver
→ authority gate
→ owning service
→ postcondition verification
~~~

Do not route deterministic state mutations through an LLM merely because an LLM exists.

## 10. Models propose; deterministic authority disposes

Models may reason, research, rank, explain, propose and synthesize. They do not gain authority from confidence, history, learning, repetition, fallback order or provider identity.

Consequential actions follow model proposal → typed contract → deterministic authority → execution boundary → independent verification.

Learning improves competence; learning never mints authority.

## 11. Independent postcondition verification

A successful call is not necessarily a successful outcome.

Where the effect is independently observable:

~~~text
execute
→ observe/read back
→ compare expected postcondition
→ VERIFIED_SUCCESS
~~~

If no reliable postcondition exists, UNVERIFIABLE remains a valid terminal state.

## 12. Symbiotic-loop audit

Agentic, adaptive and owner-assistant systems must model:

~~~text
OBSERVE
→ CONTEXTUALIZE
→ REASON
→ DECIDE ATTENTION/ACTION
→ SEEK APPROVAL
→ ACT/DELEGATE
→ OBSERVE OUTCOME
→ RECONCILE
→ LEARN
→ IMPROVE FUTURE BEHAVIOUR
~~~

Each link names producer, state/data, consumer, authority, production caller, evidence and failure behavior. A collection of individually correct subsystems is not coherent if the loop cannot close.

Non-agentic systems mark this gate NOT_APPLICABLE with rationale.

## 13. Learning-quality doctrine

Where outcomes are stochastic, decision quality and outcome quality are separate. A profitable mistake must not be reinforced as good reasoning, and a sound decision with a bad stochastic outcome must not automatically be rejected.

## 14. Proactivity boundary

Introduce proactivity in layers: proactive observation → proactive attention/follow-up → proactive proposal → explicitly authorized proactive execution. Never jump from detection to action authority.

## 15. Honest degraded states

Missing subsystems are represented explicitly as DEGRADED, BLOCKED, UNAVAILABLE, UNCONFIGURED, EXTERNAL, CAPACITY_LIMITED, UNVERIFIABLE or STALE. Fake capability is worse than explicit absence.

## 16. UI/runtime truth binding

Every live panel names its data source. Production does not use fixture/sample data. Every displayed runtime state has a producer. Every control has a registered action, authority and consumer. Loading, empty, error, degraded, offline and stale behavior are designed where applicable.

Visual/embodiment states without real producers are decorative, not integrated.

## 17. Legacy ratchet

Large existing projects do not disable a valid rule because legacy code violates it. Measure debt, forbid new debt, and require the measured baseline to fall. The baseline itself is machine-generated and reviewed.

## 18. Delete superseded paths

When a new architecture replaces an old one, preserve compatibility only where a real contract requires it. Permanent parallel old/new architectures require an explicit migration reason and removal condition.

## 19. Executable anti-gap closure

Every material closure becomes executable. A closed gap records gap ID, root cause, status, implementation references, production caller, tests, runtime evidence, independent verification, falsified_by and anti-gap check.

Deleting a closure artifact later must reopen the gate visibly.

## 20. Mutation testing

Critical guards require proof that they fail when the invariant is broken. Mutations may remove callers, rename fields, bypass authority, change accepted hashes, delete verifiers, replace exact pins or substitute fixtures. The expected result is a named test or gate failure.

## 21. Repository vs live qualification

Every project maintains a runtime qualification matrix separate from repository closure. IMPLEMENTATION_CLOSED=true, RUNTIME_QUALIFIED=false and LIVE_ELIGIBLE=false is a valid state.

## 22. Greenfield application

Before first code: normalize requirements; define Product Truth; define DUs/dependencies; define features/screens/actions/states/data/authority; define causal traces; identify root-cause risks; define failure/recovery; define independent verification; define anti-gap assertions; define runtime qualification; define mutations/counterexamples; emit the forensic predevelopment certificate.

## 23. Existing-project application

Before the next material development wave: capture baseline; treat old closure claims as hypotheses; inventory runtime surfaces; run bounded audits; trace capabilities; classify gaps; group root causes; reconcile Product Truth; create remediation packets; separate external qualification; create anti-gap/mutation plans; issue a forensic predevelopment certificate.

## 24. Emergency recovery exception

Emergency restoration/containment may bypass normal feature preparation only under explicit owner recovery authority. It may not add features, expand Product Truth or widen authority. Evidence is mandatory and forensic reconciliation follows stabilization.

## 25. Mandatory Development Pack outputs

The pack contains or machine-equivalently represents: baseline manifest, PRD normalization, Product Truth, scope/non-goals, authority map, decision register, DU registry, dependency graph, feature registry/graph, screen/surface registry and realization edges, states, workflows/actions, events, data, APIs/contracts, capabilities/authority, research coverage, source/tool qualification, architecture/topology, component registry, failure/degraded/recovery, security, performance, observability, deployment/release, implementation DAG, workstreams/atomic packets, tests, evidence, component ledger seed, counterexamples, mutations, anti-gap plan, runtime qualification matrix, symbiotic-loop model when applicable, existing-repo forensic reconciliation, and the Build-Ready certificate.

## 26. Component closure formula

A component cannot be CLOSED unless its applicable producer, state, consumer, production caller, authority, executor, effect, persistence/audit, failure, degraded, recovery, tests, runtime evidence, independent verification, counterexample, mutation, anti-gap check, falsified_by and qualification state are present.

## 27. Build-ready freshness

The predevelopment certificate is bound to current Product Truth, DU registry, feature registry, screen/feature graph, governing contracts and this standard. Material changes make the certificate stale. No task envelope may be created from a stale certificate.

## 28. Final principle

The governing question is not “does code exist?” It is:

**Is the intended outcome causally reachable, correctly authorized, observable, independently verifiable, recoverable and protected against regression?**

That question is mandatory before development begins and at every closure boundary.
