# PRD → Deterministic Development Pack
## Project Preparation, Research, Architecture, Screen Registry × Feature Graph, Fable Forensics and Anti-Gap Closure Guide — Rev 2

**Standard ID:** PRD-DDP-R2
**Status:** LOCKED / REQUIRED BEFORE DEVELOPMENT
**Supersedes:** Rev 1 for new DIAL-managed project preparation after adoption
**Mandatory forensic method:** DIAL-FFDRM-R1

## 0. Governing rule

A PRD is not a build specification. A plan is not implementation. A repository is not proof that intended capabilities are reachable.

Development may begin only when both are true:

~~~text
FORENSIC_BUILD_READY = true
RUNTIME_DEVELOPMENT_GATE = true
~~~

The first proves the project is prepared. The second proves the DIAL execution fabric is healthy enough to execute work.

## 1. Preparation pipeline

~~~text
PRD / owner intent / existing project
→ source and authority classification
→ exact baseline or greenfield declaration
→ PRD normalization
→ Product Truth
→ Development Units and dependencies
→ Feature Graph × Screen/Surface Registry
→ state/event/workflow/data/authority graphs
→ Fable causal-path model
→ forensic audit or prospective forensic contracts
→ root-cause model
→ research coverage and qualified tools/sources
→ architecture and runtime contracts
→ failure/degraded/recovery design
→ symbiotic-loop model where agentic
→ implementation DAG and atomic packets
→ verification/evidence/independent review
→ counterexamples/mutation/anti-gap plan
→ runtime/external qualification matrix
→ FORENSIC BUILD-READY CERTIFICATE
→ development
~~~

## 2. Independent completeness proofs

Every project independently proves product completeness, causal integration completeness, experience completeness, forensic completeness and qualification completeness. Strength in one dimension cannot hide failure in another.

## 3. Required machine-readable pack

At minimum: PACK_MANIFEST, PRODUCT_TRUTH, AUTHORITY_MAP, DECISION_REGISTER, DEVELOPMENT_UNIT_REGISTRY, DEPENDENCY_GRAPH, FEATURE_REGISTRY, FEATURE_GRAPH, SCREEN_OR_SURFACE_REGISTRY, SCREEN_FEATURE_EDGES, ACTION_REGISTRY, STATE_MACHINES, EVENT_REGISTRY, CAPABILITY_REGISTRY, RESEARCH_COVERAGE, SOURCE_TOOL_REGISTRY, COMPONENT_REGISTRY, IMPLEMENTATION_DAG, TEST_REGISTRY, EVIDENCE_REGISTRY, COMPONENT_LEDGER, COUNTEREXAMPLES, MUTATIONS, ANTI_GAP_REGISTRY, RUNTIME_QUALIFICATION_MATRIX and FORENSIC_BUILD_READY_CERTIFICATE.

Markdown explains; machine artifacts enforce.

## 4. Gate F0 — exact baseline

Existing projects capture repository, branch, SHA, Product Truth revision/hash, schema/runtime/deployment revisions, CI state and external dependencies. Greenfield projects capture authority-input hashes and declare no implementation baseline. Prior closure claims remain hypotheses until corroborated.

## 5. Gate F1 — authority

Define Product Truth ownership, security/approval authority, money/risk authority where relevant, model proposal boundaries, deterministic execution boundaries, scope-change authority, owner proof and external-data trust boundaries.

## 6. Gate F2 — requirements and Product Truth

Every PRD sentence/owner requirement becomes a stable requirement atom mapped to Product Truth, a non-goal or an explicit deferral. Ambiguities are resolved, safely bounded or blocking.

## 7. Gate F3 — Development Units and dependencies

Every unit has stable lineage, revision hash, feature membership, contract fingerprints, dependencies, research dimensions, authority refs, readiness and verification obligations. READY units cannot depend on missing dependencies.

## 8. Gate F4 — Feature Graph × Screen/Surface Registry

Every user-facing feature maps to required surfaces. Every control maps back to feature, action, runtime consumer, authority and verification. Backend/system features use explicit machine-surface exemptions instead of fake UI.

## 9. Gate F5 — Fable causal-path contracts

Every material capability defines requirement, implementation target, construction, registration, production caller, authority, data/control flow, executor, observable result, persistence/audit, failure, degraded behavior, recovery, tests, evidence, independent verifier and anti-gap assertion.

For existing projects these links are audited from actual code. For greenfield they become implementation obligations.

## 10. Gate F6 — research and tooling

Define research denominator, source trust, exact versions/commits/licenses where relevant, contradiction handling, donor role and tool/plugin/MCP supply-chain qualification. Knowledge may challenge but not silently mutate Product Truth.

## 11. Gate F7 — architecture and authority

Show components, topology, authority/data/execution/security boundaries, persistence, events and ownership. Every external dependency has a real injection/configuration point or is explicitly external/unimplemented.

## 12. Gate F8 — failure, degraded and recovery

Critical capabilities define failure mode, detection, owner-visible state, degraded capability, retry/backoff, idempotency, reconciliation, recovery and data-integrity behavior. Fail-closed proves safety, not feature completeness.

## 13. Gate F9 — implementation DAG

Each atomic packet names inputs, authority, allowed paths, dependencies, output, tests, evidence, counterexamples, mutation obligations and completion gate. No packet may depend on future work to make a current completion claim true.

## 14. Gate F10 — verification and evidence

Before implementation define unit, contract, integration, E2E, runtime, visual/device, performance, security and independent-review evidence. Completion claims require fresh evidence bound to exact objects and revisions.

## 15. Gate F11 — adversarial forensics

Existing projects receive a read-only forensic audit before the next material development wave. Greenfield projects receive adversarial review of the pack. Review hunts orphaned capabilities, missing callers, test-only reachability, circular authority, hidden dependencies, fake success, untestable requirements, unsupported controls, impossible recovery and stale evidence.

## 16. Gate F12 — symbiotic-loop model

Mandatory for agentic/adaptive/intelligence systems:

~~~text
observe
→ contextualize
→ reason
→ decide attention/action
→ seek approval
→ act/delegate
→ observe outcome
→ reconcile
→ learn
→ improve
~~~

Each edge names producer and consumer. Non-agentic systems mark NOT_APPLICABLE with rationale.

## 17. Gate F13 — runtime/external qualification matrix

Every capability not provable in-repo names repository state, live environment, required evidence, responsible authority/owner action, staleness and promotion condition. External gates cannot hide repository gaps and vice versa.

## 18. Gate F14 — counterexamples, mutation and anti-gap closure

Before implementation define how important claims will be falsified. Deleting callers, renaming contracts, removing authority checks, replacing pins, deleting verifiers, substituting fixtures or removing realization edges must make a named test/gate fail. Future closure claims must become executable anti-gap checks.

## 19. Gate F15 — Forensic Build-Ready Certificate

Normal implementation may start only with status FORENSIC_BUILD_READY and a passing deterministic predevelopment gate. The certificate binds standard ID/version, project identity, required gates, evidence paths, Product Truth, DU registry, feature graph, screen/feature graph where applicable, no preparation blockers and a runtime qualification matrix.

The certificate does not claim live production readiness.

## 20. Fable taxonomy and root causes

All findings use the closed DIAL-FFDRM-R1 vocabulary. Every material finding maps to a root cause. Root-cause remediation precedes independent symptom patches.

## 21. Component ledger seed

Create the component ledger before coding. Each component names requirements, producer, state, consumer, caller, authority, executor, effect, persistence, failure/degraded/recovery, tests, runtime evidence, independent verifier, counterexample, mutation, anti-gap guard and falsified_by.

## 22. Existing-project forensic rebase

Before new material work: capture baseline, reconcile Product Truth, inventory subsystems, run bounded audits, trace capabilities, challenge findings, classify gaps, cluster root causes, build remediation packets, separate external qualification, define anti-gap/mutation and issue FORENSIC_BUILD_READY.

## 23. Greenfield prospective forensics

Before first code: capability causal paths, authority, failure/recovery, independent verification, test/evidence obligations, mutation/counterexample obligations and runtime qualification are defined. Implementation may be NOT_STARTED; implementation obligations may not be undefined.

## 24. Emergency recovery exception

Explicit owner-authorized restoration/containment may bypass ordinary preparation. It cannot add features, expand Product Truth or widen authority. Evidence and immediate post-stabilization forensic reconciliation are mandatory.

## 25. Task-envelope binding

Every DIAL task envelope carries predevelopment standard ID/version, certificate hash and preparation fingerprint. If current preparation fingerprint differs, the task envelope is stale and execution is refused. This is independent of VEKL knowledge staleness.

## 26. Development-start rule

Normal development requires all four:

~~~text
PREDEVELOPMENT_FORENSIC_GATE = GREEN
DIAL_EXECUTION_FABRIC_GATE = GREEN or approved fallback
TASK_VEKL_BINDING = CURRENT
TASK_EXECUTION_ENVELOPE = CURRENT
~~~

The first answers whether the project should be developed yet. The second answers whether DIAL can safely execute now. The third proves packet knowledge. The fourth binds the exact task to current truth and structure.
