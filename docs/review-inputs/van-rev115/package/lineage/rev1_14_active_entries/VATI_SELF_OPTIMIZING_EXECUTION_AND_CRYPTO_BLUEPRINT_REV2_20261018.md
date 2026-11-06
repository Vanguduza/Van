# VATI — Deterministic Self-Optimizing Execution and Crypto Trading
## Revised architecture and complete lifecycle acceptance blueprint · Rev 2 / Unified Rev 1.14

**Date:** 18 October 2026. **Project:** VAN / VATI; `Vanguduza/Van`; project UUID `16f2f43a-8d8b-4f18-a6ac-5bd8df620414`.
**Basis:** owner-supplied `VAN_VATI_CONSOLIDATED_RECOMMENDATIONS_AND_IMPROVEMENTS_REV1_20261018-1.md` (SRC-CONSOLIDATED); exact delivered Unified Rev 1.13 archive (SRC-PARENT); targeted immutable repository reads and primary external references recorded in `research/REV114_SOURCE_REGISTER.json`.
**Status:** proposed unified specification; not owner-signed, not independent F15, not Backend Complete, not economically qualified, not a deployment or live-trading instruction.

> **Core architectural objective:** VATI must be a single deterministic, continuously learning and self-optimizing execution system. It must measure and improve how it converts authorized trading objectives into reconciled economic outcomes, using automatic operational optimization inside qualified bounds and separately governed evolution of those bounds and algorithms. Financial authority, protection, reliability and reproducibility are hard constraints, not quantities that an optimizer can trade away for a better score.

The engineering outcome is a working observe–learn–choose–execute–reconcile–evaluate loop with genuine positive, adverse and recovery paths. Economic improvement is measured against a qualified fixed baseline and may be positive, negative or inconclusive. Software cannot promise monotonically increasing profit or manufacture a profitable strategy where evidence does not support one.

This revision **does not create a second trading engine, RiskAuthority, capital book, Jev service, model registry, experiment tracker or release authority**. It expands the contracts of existing owners. No new independently deployed services are mandated. All currently required model and research integrations remain in scope; whether a model influences consequential decisions is a separate question from whether its software integration is complete.

## 1. Review of the source recommendations

### 1.1 Best ideas retained

The source's most valuable idea is not a new model name: it is closing the real producer-to-consumer connections. Its §§14–16 describe durable parent/child execution, actual execution-policy observations, replayable evidence and a positive challenger lifecycle. Its §§3, 19 and 21 preserve financial owners, causal evaluation and noninterference. These form the new core contract rather than a collection of optional optimizations. [SRC-CONSOLIDATED §§3,14–21]

Retain these complementary strengths:

| Source idea | Decision | Upgrade in this revision |
|---|---|---|
| One VATI; strategies/models propose and RiskAuthority/router govern | RETAIN | Add an explicit authority table and proof-bound operational optimization grant; no privilege from learning. |
| Durable parent/child execution | RETAIN AND COMPLETE | Parent exposure accounting, in-flight reservations, cancel/replace races, policy epochs, outbox, per-fill protection and completion joins. |
| Actual `observe()` feedback for existing execution selector | CORE REQUIRED OUTCOME | Mature observations, evidence-version reducer, snapshots, reconstruction, source correction and a positive later-selection acceptance test. |
| Separate execution quality from strategy alpha | RETAIN AND STRENGTHEN | Separate objective cost, residual opportunity benchmark, markouts and whole-account value; no win-rate reward. |
| Governed candidate evolution | CORE REQUIRED OUTCOME | Complete trigger through shadow, independent qualification, authorized activation, monitoring, suspension, rollback and retirement contracts. |
| Asynchronous Jev/cognition | RETAIN | No LLM or research RPC on order/protection path; contribution measured by ablation and diagnostic accuracy. |
| Point-in-time datasets and realistic backtests | PREREQUISITE | Qualify the evaluator before using it to optimize policy; explicit data conventions, held-out studies and censored observations. |
| Forecast/model breadth under shared owners | RETAIN | Preserve Qlib/LightGBM, required NeuralForecast models and the existing feature/calibration/artifact contracts. |
| Prediction-market and chain research | RETAIN | Keep exact event semantics and read-only chain evidence; those laboratories do not receive order credentials. |
| Crypto beyond current markets | NEW OWNER SCOPE | Implement actual centralized-exchange spot execution under VATI, separate from read-only token research. |
| Full backend before frontend | RETAIN | Self-optimization and crypto positive-path integration feed the sole BG-001 before native UX begins. |
| Instrument-specific execution algorithms | RETAIN WITH COMPLEXITY CONTROL | Add capabilities as finite in-process executors; more algorithms must earn active usage through evidence, not more live bots. |

Detailed coverage of all 24 source sections and all 30 source gap IDs is in `traceability/SELF_OPTIMIZATION_SOURCE_CROSSWALK.json`. The source document remains verbatim in `research/source_inputs/` and retains its non-implementation status.

### 1.2 Corrections to scope and evidence

The supplied consolidation cites a Rev 1.13 candidate with 267 requirements and 1,377 tests. The exact delivered parent ZIP used here contains **237 machine-readable requirements and 1,328 planned application tests**, 131 units and 234 contexts. Do not invent missing rows to match prose. This revision uses those exact machine artifacts as its inherited denominator, records their hashes and adds its new objects separately. Counts are structural bookkeeping, not proof of semantic completeness. [SRC-PARENT actual JSON files]

The earlier restriction “crypto is read-only” continues to govern **chain discovery, wallet attribution, DEX/security research and event-market laboratories**. It no longer describes the whole VAN crypto product: the latest owner instruction adds exchange-traded crypto. That is software scope, not approval to open or fund accounts, place live orders, grant withdrawals, trade derivatives or sign blockchain transactions.

The two autonomy levels are not a rename of the existing reduce-only learning policy. Their boundaries must be implemented and independently tested. No old blanket refusal is removed to make adaptation work; the new qualified operation-selection pathway is narrowly defined.

### 1.3 Targeted source observations refreshed for this revision

At the checked PR #101 head `a39f241b0135cf92cc5a6b9a28af226aa294603d`, the PR is open/unmerged. Its accepted source fixes remain candidates subject to the inherited corrective tests. This pass is a targeted document/source review, **not a repeat of the all-branch audit or a historical backtest**. [SRC-PR101]

The inspected `ExecutionPolicyEngine` already has `observe()` and `select()`; `LearningBoundary` explicitly prohibits `EXECUTION_POLICY` and production-alias changes. Extend these owners, not bypass them. [SRC-POLICY, SRC-BOUNDARY]

Additional static issues to close in the affected source:

1. `expected_shortfall_estimate()` mixes medians for filled and non-filled cases and can use zero when information is missing. A weighted mixture of conditional medians is not generally an expected cost. Missing measurements are unknown, not free. Rename the estimator if retaining it as a heuristic, or qualify an estimator for the actual declared target.
2. The urgent filtering branch uses a filtered list **or the original scored list**. If no urgent-compatible candidate remains, it can reintroduce a slower policy. Hard urgency is a feasibility constraint: it must never silently widen back to infeasible choices.
3. An unlearned fallback in the inspected PR uses `eligible[0]` when the preferred fallback is incompatible. Registry insertion order is not an approved preference. Use a versioned explicit fallback order and stable tie-break, after capability, authority and urgency filtering.
4. Bucket identity and observations need quantity/liquidity/fee context, outcome maturity, revisions and durable persistence. An in-memory count of 20 observations is not a universal economic qualification threshold.
5. Decision records must bind the exact template definition/registry epoch used. Recovering order semantics through today's global template registry is not a faithful replay of an older selection.

These are source-derived review findings, not newly reproduced runtime failures. The historic missing production `observe()` connection remains a previously reported caller-review finding to revalidate across admitted source, not an absolute claim that no alias or untracked component exists.

## 2. Two autonomy levels, one financial authority

### 2.1 Level A — automatic operational optimization

With a current qualified policy binding and standing financial mandate, VATI may automatically choose among **already qualified** methods and adjust **already qualified parameter ranges** for an authorized objective. A fresh owner confirmation is not required merely to choose passive instead of immediate execution or to alter a permitted child schedule.

An `OperationalOptimizationGrant` binds account/environment, venue/product cohort, strategy/manual ownership, policy artifact and parameter bounds, allowed algorithm versions, approved fallback ordering, estimator/update-rule version, qualification IDs, freshness/expiry, emergency override rule, maximum switching behavior, and the existing risk/mandate identities. It grants no more risk than those parents.

Allowed operational examples:

- Choose the qualified lowest defensible execution-cost method among currently feasible candidates.
- Set a child limit offset, slice size, spacing or participation cap inside the authorized range and parent reservation.
- Stop working an entry because its deadline, approved limit, source freshness or qualified opportunity-expiry condition is no longer satisfied.
- Move to a still-valid qualified baseline after missing evidence, drift, service failure or revocation.
- Reduce or suppress new exposure under existing risk/protection rules while preserving mandatory exits.

Not allowed:

- New instruments, accounts, leverage, venue credentials, financial budgets, stop widening, ownership handover, new trading signals, new model aliases or new algorithm code.
- Changing estimator formula, training window rules, exploration rate, template parameter domain, utility weights or promotion criteria without the governed evolution path.
- Treating an economically successful but unauthorized action as a positive training example.
- Clearing an account halt, risk reservation or suspended strategy because the optimizer prefers to trade.

A state update under a qualified reducer is not a new policy version. A changed reducer, feature meaning, reward definition, scope or permitted action set **is** a new policy version. The implementation and tests must make that distinction inspectable.

### 2.2 Level B — governed policy evolution

VATI autonomously researches and tests candidate improvements under bounded research grants. Candidate creation, model fitting, simulations, report generation and qualification recommendations can be automatic. Consequential production activation of a new policy requires the existing authorized qualification/promotion process, including the relevant independent evidence and owner/mandate authority.

The default contract does **not** authorize self-promotion. A future standing automatic promotion policy would itself need explicit owner approval, independent qualification, constrained scope and its own amendment. No such policy is inferred here.

A new qualified binding applies to newly admitted objectives at an explicit activation barrier. Existing open parents remain pinned to their original policy unless a recorded migration is authorized, feasible, risk-revalidated and reconciled. Emergency safety response can preempt them under the pre-existing protection authority; normal policy rollout cannot quietly rewrite their history.

### 2.3 Authority priority and precedence

| Decision/effect | Sole authority owner | Optimizer responsibility |
|---|---|---|
| Create/amend strategy trading objective | Existing strategy/owner mandate and opportunity path | Consume only authorized objectives; no new signal from execution reward. |
| Size/exposure/collateral and reservation | Existing account coordinator + RiskAuthority transaction contract | Work within envelope; request fresh authorization for a changed envelope. |
| Broker send/cancel/amend | Existing ExecutionRouter + admitted adapter + fence | Submit exact child instructions via that route only. |
| Mandatory protection and risk reduction | Existing protection/lifecycle/risk owner | Yield priority; never wait for inference/retraining/LLM or cheapest-fill selection. |
| Observe market/order/account facts | Admitted data/venue/evidence owners | Preserve provenance, deduplicate, join and compute declared estimates. |
| Update learned state under approved formula | Qualified evidence reducer | Publish immutable versioned evidence state without touching financial permissions. |
| Select qualified execution method | OperationalOptimizationGrant-bound selector | Deterministic feasibility filter, cost comparison and logged fallback. |
| New policy research | Existing study/jobs/artifact owners | Produce candidate evidence and proposals, not live aliases. |
| Qualification/promotion/revocation | Existing independent qualification and financial promotion authorities | Verify artifact/scope/issuer; obey suspension and compatible fallback. |
| UI actions | Owner gateway with scoped proof | Navigation and status do not execute; consequential actions use existing gates. |

If priorities conflict, financial and safety constraints win. `DO_NOT_EXECUTE` is valid for an optional entry, but cannot be used to abandon required position protection or reconciliation. Failure to close through a venue leaves exposure unresolved; it is not magically safe because new entries are stopped.

### 2.4 Boundary implementation, not permission laundering

Preserve the existing `LearningBoundary`'s forbidden targets. Introduce a narrow typed evidence-update contract and a qualified operational selector contract at the existing execution owner. The reducer may write only its evidence projection; the selector may emit only a sealed decision for an already authorized objective. Only the promotion owner changes the active policy binding. Tests attempt the same forbidden operation through HTTP, queue events, direct method calls, persistence restores and forged snapshots.

This is an explicit extension to the authority map requiring admission. It is not “let the research process write policy because the owner asked for learning.” `signature_valid=true` and developer-supplied trust keys are not proof; trusted existing verifier identities and bound payloads are required.

## 3. Compact reference architecture

### 3.1 Preferred deployment shape

Use the current admitted VAN topology. Prefer four existing process groups: (1) time-critical VATI/account runtime, (2) market/provider ingestion where already isolated, (3) bounded research/training workers, and (4) owner gateway/read projections. Persistence, artifact storage and Jev are reused where already admitted. Logical module separation does not imply another service, queue technology or database.

Within the execution/account group, use these logical ports:

`ApprovedObjective → FeasibilityFilter → PolicySelector → ParentOrderSupervisor → ExecutionRouter → VenueAdapter`.

`Venue/account events → Reconciliation/Protection → ExecutionOutcomeBuilder → EvidenceReducer → immutable EvidenceSnapshot → later PolicySelector`.

`Mature evidence/drift → ResearchJob → CandidatePolicy → Evaluator → shadow/demo → IndependentQualification → AuthorizedBinding → monitored later objectives`.

The broker event path remains local and bounded. The research path runs asynchronously with CPU/memory/I/O limits and no order or withdrawal credentials. A queue backlog or model registry outage cannot stall protection.

### 3.2 Reuse and ownership obligations

Extend `execution/policy.py`, the existing template owner, router/base/venue adapters, account coordinator/service, trade lifecycle, TCA and learning evidence/replay components after function-level source admission. Retain PR101's useful fixes but close its inherited limit-price, pending protection, expiry, cancellation, terminal-state and lockout-policy gaps. Preserve richer canon/PR92/PR77 Jev, evidence and temperament contributions where compatible.

NautilusTrader contributes event/reconciliation patterns; Hummingbot contributes finite executor patterns; pysystemtrade/LEAN contribute targets and independent comparison. None receives a parallel live account owner. The current Nautilus documentation explicitly notes limits around durable persistence before transport, channel ordering and backpressure. Therefore installing it does not discharge VATI's own outbox, account isolation or bounded-queue requirements. [EXT-NAUTILUS, EXT-HUMMINGBOT]

### 3.3 Full units without a dependency cycle

BE-010 completes canonical order working with genuine static qualified-baseline behavior and tested selector/evidence ports. BE-012 completes outcome/TCA production. BE-036 completes the positive learned-state-to-selector integration and policy evolution, consuming those already working ports. BQ-007/009 verify the closed loop as a whole. BE-010 is not allowed to claim learned optimization complete before BE-036; BE-036 is not allowed to claim order correctness merely by injecting synthetic success.

This avoids a circular “router needs learning, learning needs fills, fills need router” graph. Ownership is explicit: base execution correctness is earlier; adaptive composition is later; every mandatory backend remains before BG-001.

## 4. Determinism and reproducibility

A decision is a pure, versioned mapping from sealed admissible inputs to a sealed output:

`D = f(policy artifact, grant, objective, account/reservation state, instrument/venue capabilities, information cutoff, market snapshot, evidence snapshot, prior parent state, ordered event cursor)`.

Record source commit, executable artifact hashes, dependency versions, numeric conventions, policy/calibration/update versions, action set, rejected alternatives/reasons, clocks, cutoff, decision reason and output fingerprint. Monetary quantities use instrument-correct fixed-point/Decimal conventions; do not round after risk approval and claim the approval covers a different price.

**Recorded decision replay:** identical sealed inputs and recorded event sequence yield identical decisions and projection digests. Live event delivery has no universal global order: assign an authoritative monotonic account/journal cursor at admission and record tie-break/watermark rules. Deduplicate source IDs; buffer/resync per provider sequence where applicable; quarantine unresolved gaps.

**Environment-bound model inference:** use pinned supported execution environments and explicit numerical tolerances. Floating-point nondeterminism cannot be dismissed when it changes a selected method; tie bands and quantized comparisons are policy parameters.

**Training reproducibility:** seed and log stochastic jobs, kernels, data order, attempts, threads and environment. Report statistical or tolerance-based reproducibility where byte equivalence is not established. Persist every issued candidate and prediction; never recompute a historical decision with new weights and replace the old evidence.

**Venue outcomes:** external fills are not deterministic. Replaying recorded outcomes reproduces VATI's reaction; replaying a simulator explores a declared model, not a claim that the exchange will repeat those fills.

**Two replay views:** `AS_DECIDED` uses evidence available at the original cutoff; `RESTATED_ANALYSIS` incorporates later corrections without altering the historical authorization or decision. Corrected facts invalidate affected analytical descendants, not the immutable history of what was actually sent.

## 5. Parent objectives, orders and protection

### 5.1 Objective envelope

An approved objective binds account, strategy/manual owner and environment; exact instrument/venue/contract version; side and base/quote quantity semantics; maximum total quantity/notional and risk; reservation identity and version; permitted order types and algorithms; limit/slippage boundaries; deadline, urgency and abandonment conditions; protective requirements; policy/mandate/grant hashes; and the current lease/fence.

Approval and reservation follow the existing transactional account contract. A recorded approval does not allow late reservation against a changed balance without validation. Do not implement a second reservation store in the execution optimizer.

### 5.2 Exposure invariant

For a buy-only parent in base units, a necessary invariant is:

`cumulative_net_filled + sum(max_remaining_executable(child)) <= approved_parent_quantity`.

Reservations additionally cover worst-case cash/notional, fees, collateral, current holdings, contingent children and all strategy/manual demands under the true product payoff. A cancelled-but-unconfirmed or submit-unknown child counts until reconciled. For two-sided, hedged, netting or multi-leg objectives, apply the admitted scenario-based account exposure calculation, not this scalar shortcut.

Sibling replacement orders cannot both assume the same residual allocation. Use atomic amend only when the venue's exact semantics are qualified; otherwise cancel/query/reconcile then replace, or reserve the feasible overlap under a separately authorized protocol. External manual fills and provider balance changes revalidate the aggregate state.

### 5.3 Durable command protocol

Commit the command identity, reservation/fence version, payload digest, retry/query policy and parent link before attempting its economic side effect. Transactional outbox, order state and account journal share the existing atomic boundary where needed. Delivery retries are not claims of exactly-once network execution.

On lost acknowledgement: mark `OUTCOME_UNKNOWN`, preserve maximum possible exposure, query by known durable client/venue identifiers and reconcile. Retry only if the venue's idempotency contract and current evidence justify the exact same economic instruction. A missing order from one endpoint, especially an open-order endpoint, is not proof it never filled.

**Facts survive revocation.** A genuine late, manual, external or over-limit fill must still be recorded and reconciled when a grant expires or is revoked. Reject the unauthorized *command*, not the fact that an economic effect occurred. Mark policy breaches explicitly; block new risk where required and run protective recovery. Training admission is separate and may exclude the violation without deleting financial history.

**Late facts can reopen a reconciled revision.** Authenticated late fills, busts or financial corrections append a new child/parent revision and reopen reconciliation, even after a previously terminal cancellation, expiry or evaluation. Preserve the prior history, invalidate affected analytical measurements and prevent duplicate effects or blind resubmission. A terminal UI label is not permission to discard reality.

Private-stream and REST observations can overlap; matching and reconciliation must share a fill-identity map. Record cumulative and incremental quantities distinctly; trade/fill ID correction or bust is a new revision with a compensating accounting path.

### 5.4 Order and protection state are separate dimensions

Do not combine “filled” with “protected” or “cash settled.” Track canonical order lifecycle, filled quantity, working remainder, protection state, account/cash reconciliation and analytical maturity separately.

For each fill requiring protection: confirm the actual venue stop/protective construct or enter the admitted protection-recovery sequence. Initial request with a stop is not confirmed protection. If an emergency close fails or is uncertain, preserve `UNRESOLVED_EXPOSURE`, block new risk as specified and keep recovery active. Do not mark a trade flat from a sent close request.

Urgent risk-reduction paths do not depend on execution-quality samples or Jev. An empty urgent-compatible action set requires the qualified emergency fallback or an explicit unresolved/refused condition with escalation—not a reintroduction of slow candidates.

### 5.5 Deadline, cancellation and terminal states

Propagate the approved policy expiry exactly through all layers; neither an adapter default nor a child restart may extend it. Track exchange expiry support separately from local supervision. Deadline expiry causes no new child, cancels working remainder where possible and reconciles races. A fill arriving after cancel request remains a fill to account for and protect.

Parent work ends only after each child is terminal or explicitly accounted as unresolved, all effects have reconciled and remaining exposure is known. `ECONOMICALLY_RECONCILED` does not require late research markouts to have matured; it does require actual order/position/cash/protection truth. Analytics may close later.

## 6. Qualified execution methods and automatic selection

### 6.1 Initial complete method family

Build and test: bounded immediate execution; marketable/nonmarketable limit with exact price protection and expiry; passive limit; passive-then-cross only under a separately permitted marketable phase; bounded chase/amend; TWAP-style child scheduling; volume/participation-aware scheduling only with qualified venue volume/depth; and portfolio target-delta working. Supported stops and conditional orders preserve the original strategy meaning. A stop-limit remains trigger-plus-limit, not market execution.

Grid, DCA, speculative inventory and cross-exchange hedge research remain separate strategy/research features. They cannot increase quantity or risk merely because a finite executor makes them convenient. Multi-leg algorithm qualification must model non-atomic legs, venue-specific collateral, failed hedges and emergency outcomes.

A method may exist as working software yet remain unqualified for a particular venue or cohort. Mandatory implementation includes supported positive cases and clear capability refusals; refusing everything is not completion.

### 6.2 Feasibility precedes optimization

Construct the eligible set by intersecting:

`qualified artifact scope ∩ operational grant ∩ authorized objective ∩ current risk/reservation ∩ venue capability ∩ instrument restrictions ∩ ownership ∩ current data validity ∩ urgency/deadline ∩ protective constraints`.

No score, probability, favorable history or model output can add an infeasible method back into the set. Candidate filtering also checks market status, fee/product revisions, rate-limit headroom and resource budgets. Lack of book evidence excludes book-dependent policies, not forces fabricated liquidity.

Score only feasible alternatives. The intended default is a conservative contextual cost estimator with uncertainty and explicit fallback—not unconstrained reinforcement learning. Selection records every eligible alternative and why it lost, the chosen parameter vector and the evidence used.

### 6.3 Simple deterministic learning first

Start with robust context-conditioned measurements or a small calibrated regression model that can outperform an explicit fixed-template baseline. Use a versioned hierarchy for sparse buckets (exact cohort → compatible broader cohort → qualified static fallback). Pool only if the permitted population and transfer evidence justify it; FX and crypto estimates cannot be pooled because both expose a `symbol` string.

Evidence sufficiency includes effective independent parent/objective count, mature labels, coverage by action/size/session, recency and uncertainty—not a universal `samples >= 20` rule. Children and repeated markouts from one parent are not independent samples. Existing reduce-only weighting rules remain distinct from this selector's approved evidence-use policy.

The update rule fixes aggregation, decay, trimming/robustness, window boundaries, caps, tie tolerance, maturity, correction and fallback. Update the learned state at recorded boundaries; pin each decision to a snapshot. Research changes to these rules are Level B policy evolution.

### 6.4 Switching and parameter churn

Use bounded switching with an admitted hysteresis/improvement margin and minimum persistence where appropriate. Avoid changing policy on every price tick or oscillating because two noisy estimates cross. Urgency, risk or invalidation can override a persistence preference to a safe route.

Parameter optimization remains within the grant's tested domain and joint constraints. Independent per-field ranges alone may permit an untested combination; record qualified joint parameter regions or enumerable profiles. Recheck the remaining parent envelope before any switch or additional child.

### 6.5 Exploration is not silently authorized

Deterministic exploitation within the qualified set is the default. A randomized contextual bandit or other deliberate exploration changes the experiment/authority contract even if it samples only qualified algorithms. It needs a separately admitted budget, assignment design, logged probabilities, seeded/replayable draws, stop rules and policy scope. No live exploration is added by this document.

For observational data, a method chosen with probability zero in a context provides no support for causal off-policy evaluation there. Logging a selection score is not logging a valid propensity. Doubly robust methods are a research option under their assumptions, not a cure for missing overlap or hidden confounding. [EXT-DR]

## 7. Execution economics and reward design

### 7.1 One objective definition with honest benchmarks

For a simple single-instrument spot objective with side `s=+1` for buy and `s=-1` for sell, approved base quantity `Q`, benchmark price `p0`, fills `(qi,pi)`, fixed evaluation horizon price `pH` and `Qf=sum(qi) <= Q`, define a benchmarked execution loss:

`L = s * [sum(qi * (pi - p0)) + (Q - Qf) * (pH - p0)] + explicit_nonembedded_net_costs`.

This is a proposed benchmark definition for the declared scenario—not a universal cash P&L identity. The residual term is opportunity cost against the frozen hypothetical objective, not an observed trade fill. Its price/horizon must be preregistered and independent of the chosen policy. Preserve the sign: not buying before a price falls can produce a negative opportunity term.

Normalize to basis points only with a positive fixed reference notional, and record quote/base/valuation currency. Use product-specific cash/payoff adapters for FX/CFD/futures/Deriv nonlinear instruments; do not impose the simple spot formula on incompatible products.

When the benchmark or future mark is unavailable, label that component missing; do not set it to zero or allow policies to win by inducing missingness. Report bounds/sensitivity or `INCONCLUSIVE` under the registered estimator.

### 7.2 Avoid double counting

Actual bid/ask execution prices already contain spread. Explicit fee debits/rebates, financing/borrow and conversion costs are added only when not embedded. Markouts, spread capture, delay and price impact are useful diagnostics; do not blindly add all of them to implementation shortfall if the same market movement is already represented.

Execution quality is not trade win rate. Strategy alpha, exit logic, position sizing, market drift and deposits can change account P&L without demonstrating a better execution algorithm. Compare the same eligible objective stream with identical resources and risk rules, then separately run whole-account policy arms because changed timing/non-fills may affect later feasible opportunities.

### 7.3 Utility and noninferiority

The research objective is evidence of incremental **net** utility after required costs and operational burden, at comparable risk and exposure. Hard safety conditions remain outside the optimizer's reward. A small cost improvement that degrades protection, reconciliation or tail outcomes beyond the approved constraint is not an improvement.

Report a vector, not a single flattering score: execution-cost distribution; residual opportunity term; fill/partial/reject/cancel rate; deadline behavior; adverse selection/markouts; fees/turnover; exposure/capital usage; mark-to-market drawdown; operational incidents; latency; data/compute cost; and uncertainty.

Preregister materiality, confidence method, dependence treatment, sample-power targets, stopping rules and noninferiority tolerances per cohort. Do not invent profitable production thresholds in a document. Runtime configuration with unbound economic thresholds cannot promote a candidate. Safety acceptance such as “no duplicate economic effect in the specified tests” is not a promise of zero real-world incidents.

### 7.4 Prevent reward hacking

The test set must include “never trade” appearing cheapest on fill-only metrics; passive orders with missed profitable opportunities; rebates offset by adverse selection; many child fills inflating sample size; removing bad data only after seeing the result; delaying evaluation until a favorable mark; changing the universe to survivors; and gains from higher exposure falsely attributed to better execution.

For an entry, not trading may be the correct qualified outcome when constraints or evidence warrant it. For an obligatory reduction, missed execution is a safety/recovery problem and cannot be rewarded as saved spread. Mark the objective's purpose explicitly.

## 8. Durable observations, evidence and continuous learning

### 8.1 What enters the evidence stream

Record all objectives, eligible sets, selected methods and decisions, including rejections and abstentions. For sent orders, retain submit/ack/working/partial/fill/cancel/expire/reject/unknown histories and their revisions. Join to source-bound quotes, depth, fee schedule, account scope, strategy and policy versions, approved quantity and actual costs.

An observation carries original environment: live, demo, paper, simulation, shadow or counterfactual. They can share schemas but do not become interchangeable training facts. Executable-quantity data and independent source quality remain explicit.

### 8.2 Maturity and censorship

Order finality, fee completion, cash reconciliation and each markout horizon have separate maturity flags. A partial fill can contribute immediately to operational protection but not masquerade as a completed parent outcome. Unknown outcomes remain unresolved and outside mature economic training until reconciled or explicitly censored by the registered statistical model.

Define parent-level sampling units and cluster identities. For a surviving active order, record censoring time and competing termination reason; no invented full-duration non-fill label. Decisions with no sent order may contribute to opportunity studies but not actual broker slippage statistics.

### 8.3 Deterministic reduction and reconstruction

The reducer consumes original record identity/version, context, admission and maturity. In one durable transaction, mark the event revision applied, update its contribution and advance the consumer cursor/snapshot. It rejects wrong scope, unauthenticated facts, immature required labels and duplicates.

To correct or bust an observation, reverse or recompute its prior contribution deterministically, preserve the old snapshot and publish a new revision. Drift windows and sample counts cannot double-count both versions. Snapshots bind cutoff, versioned source references, observation set digest, aggregation/update code, numeric precision and population definition.

Restart reconstructs the same learned-state fingerprint from checkpoint plus verified tail. Missing corrupt checkpoints trigger tested recovery, not empty “fresh” state that silently re-enables risk or pretends to have no bad history. Reconstruction does not resubmit orders.

### 8.4 Continuous does not mean unbounded or instantaneous

The system ingests outcomes continuously but updates only when the relevant evidence is admissible and mature. Fast execution selects from a prevalidated current snapshot; asynchronous jobs perform larger aggregation, calibration and diagnostics. Scheduled weekly research is a baseline cadence; drift or material incident triggers bounded jobs, not infinite retraining.

Track source-to-receipt, receipt-to-durability, durability-to-local-update, evidence-to-next-eligible-selection and research-trigger-to-candidate times separately. Thresholds derive from measured target workloads and are pinned before qualification. A low network timeout is not a measured latency result.

### 8.5 Positive feedback acceptance

A complete loop must pass this explicit application scenario:

1. Seal a permitted objective cohort, fixed policy alternatives and qualified static fallback.
2. Run the real decision/router/outcome path against an admitted test environment with known conditions; generate both fills and non-fills with measured costs.
3. Allow required horizons to mature; the actual registered consumer persists observations and publishes a new evidence snapshot.
4. On a later same-scope eligible objective, the actual selector changes to the method supported by that evidence **without requesting a new owner approval for that operational choice**.
5. Restart and replay the journal; the same snapshot and choice result.
6. Inject wrong-scope, duplicate, immature and corrected events; verify correct refusal or restatement without illegal financial effects.
7. Remove the production consumer subscription/call; an integration test fails because the later selection no longer changes.

A scripted fake function that calls `observe()` in a unit test does not satisfy step 3. A controlled synthetic improvement scenario proves the mechanism, not real-market profit.

## 9. Governed evolution: complete lifecycle

### 9.1 Candidate stages and invariants

A candidate follows `HYPOTHESIS_REGISTERED → BUILDING → OFFLINE_EVALUATING → OFFLINE_ACCEPTED → PROSPECTIVE_EVALUATING → QUALIFIED_CANDIDATE → AWAITING_AUTHORIZATION → AUTHORIZED → ACTIVE_BINDING`, with rejected, inconclusive, failed, cancelled, suspended and retired branches. Expiry and revocation invalidate the associated grant/binding; rollback activates a separate compatible qualified binding rather than inventing a candidate state or rewriting its history. The linked candidate and binding machines express these separate dimensions. Stage names are versioned contracts mapped to existing owners, not a second live policy database.

| Stage | Required producer and durable artifact | Exit evidence | Forbidden shortcut |
|---|---|---|---|
| Trigger/hypothesis | Existing diagnostics/jobs, full cohort and drift/incident evidence | Falsifiable question, target, comparator, budget and data cutoff | One losing trade directly rewrites execution. |
| Candidate build | Existing research worker and artifact store | Immutable code/model/config/feature/reward artifact; parent lineage; all attempts | Mutable `latest` alias or undeclared dependencies. |
| Offline study | Qualified evaluator, chronological data and matching oracle | Fold records, full trials, stress, costs, controls, negative/failure results | Calendar years relabelled as walk-forward folds. |
| Independent comparison | Verifier on separated outputs/source | Comparator parity, no leakage, uncertainty, materiality and operational limits | Author's self-score treated as independent qualification. |
| Prospective shadow/demo | Existing consumer, forward snapshots and actual permitted venue/demo evidence | Real timestamped path, differences and observed limits | Mocked API response sold as matching/latency proof. |
| Qualification | Existing qualifier and scope ledger | Exact scope, expiry, conditions, revocation and binding requirements | Software completion automatically creates financial permission. |
| Authorization | Existing owner/mandate promotion process | Authenticated approval of exact artifact/scope/risk/recovery plan | Research worker or UI label writes production alias. |
| Activation | Existing binding owner | Atomic epoch swap at declared boundary, compatibility and current proof readback | Mixed old/new policy components in one parent. |
| Monitoring | Existing health/economic/operational consumers | Cohort-specific drift, utility, incidents, cost and freshness | Positive P&L conceals unresolved safety errors. |
| Suspension/rollback | Existing safety/promotion owners | Entry halt or compatible qualified fallback, account reconciliation, pending-parent handling | Revoked policy resurrected on restart or old snapshots silently restored. |
| Retirement | Existing retention/source governance | No active consumers/open-parent dependence; auditable retained history | Deleting failure trials to improve the record. |

### 9.2 Training is not self-authorization

Models may propose algorithm candidates, parameter domains or features. The signed live artifact and its permitted state-update rule are immutable for that version. Qualified evidence may change **state**; governed authorization changes **policy**. Production code cannot be downloaded or generated mid-trade.

Independent qualification and final authority cannot be supplied by the same research identity. Hashes establish identity, not truth. Certificates are verified against the existing trusted issuer roots, correct project/account scope, time and revocation sources—not keys embedded in the request.

### 9.3 Candidate efficacy and comparison

Compare against: the incumbent production binding; the simplest feasible static baseline; method-specific baselines; and whole-account variants at equal information/resources/risk. Record every failed/pruned trial and candidate considered, including human/LLM revisions. Freeze holdouts before inspecting results; use prospective data for repeated retraining and account for selection/serial dependence.

Off-policy estimates require overlap, logged behavior policy and defensible estimator assumptions. Do not estimate unseen queue positions or missing execution paths as actual outcomes. A candidate may be `REJECTED` or `INCONCLUSIVE`; do not tune repeatedly until a green cell appears.

### 9.4 Monitoring and rollback semantics

Separate economic monitoring from safety monitoring. A positive safety violation triggers immediate predefined risk response independent of statistical power. Economic deterioration is evaluated using the registered repeated-monitoring method, not endless ordinary p-value peeking. Confidence-sequence methods may help under verified assumptions; otherwise use fixed review windows and justified sequential error control. [EXT-CS]

Rollback restores a **compatible still-qualified binding**, not a previous database state. Preserve actual positions, working orders, fees, source corrections and learned evidence. If no safe binding exists, stop new eligible entry risk and maintain protection/reconciliation. Risk reduction never waits for the prior strategy to become profitable again.

### 9.5 No impossible completion criterion

Engineering qualification must demonstrate the full successful candidate path using meaningful controlled fixtures and actual services, as well as rejection/rollback. Economic qualification for a real cohort may still conclude no challenger is better. A permanently rejecting integration is incomplete; a complete integration that honestly rejects real candidates is valid.

## 10. Backtesting that can improve the architecture

### 10.1 Repair the evaluator before optimizing against it

Retain every inherited simulator corrective contract: order type and price constraints, pending fills, trigger/gap behavior, actual bid/ask conventions, timestamp/timezone, approved expiry, fill/stop/cancel races, final liquidation and charges, complete equity path, common account reservations and manual/automatic interactions.

The historical research isolated strategy behavior using documented harness changes. Preserve those experiments as research; do not relabel them production-faithful evidence. Compare strategy-isolation and deployment-faithful runs separately. Reproducing a source calculation is not proof of venue behavior.

### 10.2 Mandatory causal tests

Run prefix-only versus full-history evaluation at identical decision cutoffs. Mutate only future prices, releases, revisions and labels; earlier features, eligible sets, decisions and commands must remain unchanged. Test negative shifts, centered windows, full-dataset scalers, future-vintage data, higher-timeframe bars not yet closed, mislabeled peer timestamps and artifact caches crossing epochs.

A deliberate peek that changes final P&L is a negative control, not a leakage-free certificate. The suite must identify a prohibited information path and fail on a deliberately poisoned implementation. Warmup/recursive-indicator stability uses explicit tolerances and data needs.

### 10.3 Statistical and economic discipline

Calendar-year tables are descriptive reporting, not walk-forward training/selection records. Keep actual fit/validation/calibration/test boundaries and artifact identities. Use dependent resampling, event/parent clusters, nested selection and enough independent information for the intended claim. DSR/PBO are scope-sensitive diagnostics, not literal general probabilities of skill. [EXT-DSR]

For crypto, include outages, thin books, fees and third-asset fee balances, stablecoin dislocations, token delistings and maintenance. Spot entry and exit need actual inventory and reserved quote/base assets. Do not port an FX fill or pip convention as a crypto oracle.

### 10.4 How results change the design

Each evidence-backed design recommendation produces a `DesignChangeProposal`: frozen hypothesis; source/code/data/evaluator identities; competing designs; outcome distributions and uncertainty; cost/latency/safety implications; affected contracts/units/surfaces; ablations; counterexamples; required authority; and acceptance/reversal conditions.

Astra may recommend removing duplicate services, reducing hot-path inference, changing a qualified estimator, strengthening order semantics, or simplifying a feature implementation. It must preserve the required capability or request an explicit scope change. No result may automatically mutate the canonical blueprint or financial mandate.

Maintain three findings: **implementation defect**, **insufficient economic evidence**, and **architectural complexity without demonstrated benefit**. They require different responses. A strategy's poor backtest does not justify deleting crypto order support or a required forecasting integration. It may justify keeping the relevant model dormant and choosing a simpler active baseline.

## 11. Crypto trading as an integrated VAN market

### 11.1 Required market scope and explicit exclusions

**Required engineering outcome:** VAN can discover, quote, analyze, draft, authorize, submit, manage, cancel, reconcile and report supported centralized-exchange **spot crypto** trades through the same VATI account/risk/router/protection/learning path used by its current markets. Both owner-manual and qualified automated strategies are supported under separate existing ownership and financial grants.

FX, indices, metals, Deriv's actual products and ZSE owner-ticket workflows remain preserved. BTC quoted in USD, USDT or USDC and crypto CFDs are different instruments. A futures/perpetual, leveraged margin, options or DEX transaction is not a spot trade.

Margin/perpetual/futures capabilities are explicitly future scope unless already separately admitted: they require liquidation, margin mode, index/mark/last trigger, funding, reduce-only, contract multiplier and ADL/insurance semantics. The application must show them unsupported until qualified—not implement them as spot with a different label. Existing prediction-market execution remains research-only unless separately authorized.

No funded wallet, blockchain transaction signer, custody withdrawal key, permissionless token order sender, exchange registration or live deposit is created by this blueprint. Chain security and wallet-flow research may contribute qualified evidence, never order authority. Automated crypto withdrawals are not part of operational optimization.

### 11.2 Venue selection and adapters

Build a complete capability-driven adapter contract and **at least one real supported spot venue integration**, selected from already permitted owner access and current documented API capabilities. Kraken Spot and Coinbase Advanced Trade are researched implementation candidates, not approved providers or assurances of owner/account eligibility. Select the target before its implementation packet; lack of an eligible provider remains a concrete gate, not permission for a refusal-only placeholder.

Use native adapters where exact semantics matter. CCXT can normalize discovery or supported methods if admitted, but every method's real venue behavior and credential isolation must be tested. Neither CCXT, Hummingbot nor another donor sends live orders outside ExecutionRouter.

The current Coinbase Advanced sandbox is static/mocked; it can support payload/schema tests but cannot qualify real matching, fees, depth, latency, cancellation races or funding settlement. Provider qualification must use an actually appropriate permitted environment, not re-label a mock. [EXT-COINBASE]

### 11.3 Product and instrument identity

A `CryptoVenueProfile` records exchange API family/version/environment; owner account/subaccount; market/product type; immutable native product ID; base/quote assets; network-qualified identities for external movements; price tick, base step, quote increment, minimum/maximum sizes/notional; supported order/TIF/post-only/stop/amend semantics; trading status and revision; fee role/currency/schedule; precision and rounding; clock/nonce constraints; and authenticated stream/query capabilities.

Never make ticker equality an identity join. Product filters can change while an order is being drafted; refresh, revalidate and re-approve any material envelope change before submission. A higher price cannot silently cause the newly rounded quantity or fee reservation to exceed the approved budget.

### 11.4 Spot accounting, fees and stablecoin exposure

A buy reserves quote plus applicable fee resources; a sell reserves owned base inventory plus fee resources. No naked short, borrowed quote or implicit leverage is created. Minimum-notional/dust handling is explicit; rounding down to zero is a refused order with released reservation only when no side effect exists.

Fees may be charged in base, quote or a third token and may alter saleable holdings. Maker/taker status and rebates come from actual fills. Reconcile actual fee assets, realized proceeds and mark-to-market conversion without pretending a stablecoin equals fiat cash under stress.

Deposits, withdrawals and venue transfers stay under Accounts & Funds, separate from trading. Pending external transfers do not fund new orders until the admitted finality/credit rules are met. Trading keys exclude withdrawal permissions; any funds workflow uses distinct credential scope, exact owner authorization and outcome reconciliation.

### 11.5 Books, streams, rates and outages

Maintain snapshot-plus-update order books with sequence/checksum rules from the admitted venue. Detect gaps, duplicates, stale messages and subscription loss. A connected socket or heartbeat does not prove market data is fresh or private order reconciliation is complete.

Reserve request budget and priority for cancel/query/protection; research polling cannot consume it. Persist durable client identities and reconstruct private order/fill histories after reconnect. Normalize errors precisely; rate limiting is not evidence an order failed before reaching the venue.

Crypto is commonly traded continuously, but no venue is assumed continuously available. Configure actual maintenance/halt/status signals, weekend liquidity, UTC clock integrity and funding intervals only for products that have them. On outage, preserve uncertain exposure and operator visibility. Never declare positions flat because REST or the exchange UI is unreachable.

### 11.6 Dead-man switches can remove protection

Kraken documents cancellation of all account orders when its timer expires. Therefore a dead-man switch is not automatically safe for an account that also holds protective stop orders or unrelated manual orders. It may cancel the very protection VAN is relying on. [EXT-KRAKEN-DMS]

Qualify cancellation scope and mitigation: dedicated permitted execution scope/subaccount where available; protection order exemptions only if genuinely supported; position policy that avoids an unprotected remainder; and explicit outage/recovery tests. Do not enable account-wide cancellation merely because an exchange exposes the endpoint. Failure response must preserve truthful protection state and residual risk.

### 11.7 Stop and amendment semantics

Native stop/conditional/order-amend and secondary close-order support are vendor capabilities, not universal abstractions. Kraken's documented order interface illustrates optional and conditional fields; exact product behavior must be bound to the selected profile. [EXT-KRAKEN-ORDER]

Local synthetic stops are a separate qualified protection mode with persistence, feed dependency, latency/outage risk and owner acceptance—not silently “broker protected.” Post-only rejection cannot be retried as a taker order without its own permitted phase. Amend priority/identity changes, cancel-and-replace and partially filled remainder are all tested.

### 11.8 Crypto positive-path qualification

Before crypto is marked usable, prove: metadata discovery; public feed snapshot/recovery; authenticated read; linked-account capability and non-withdraw key validation; real admissible order/partial/cancel/expiry flow in the appropriate permitted environment; fee/inventory/cash reconciliation; trigger/protection behavior where supported; restart and unknown-outcome handling; and policy outcome ingestion with correct crypto context.

Offline fixtures and genuine provider observations use distinct evidence grades. A mocked endpoint cannot satisfy real-provider requirements. BG-001 can only certify the actual declared target once those integrations work; separate financial activation still governs live money.

## 12. Owner experience after backend completion

Preserve the locked graphite/porcelain tactile style, metallic state-aware Home orb, compact notification/action sheet, and the rest of VAN's full product. Do not invent another global navigation tab or a busy machine-learning dashboard.

Extend existing contexts:

- **Trading Home / Markets / Watchlists:** crypto filters and authentic venue/product labels; normal market navigation remains unchanged.
- **Instrument / order review / positions:** exact base/quote size, balance and fees, venue status, order type/expiry, supported protection and known/unknown state. No “Buy” interpreted as profit.
- **Accounts & Funds:** linked crypto account, permission/capability state, separate trade versus funding permission, inventory/valuation currency, pending settlement and readback.
- **Execution details / TCA:** current parent/children, approved method and parameters, realized versus estimated costs, why an operational choice changed, evidence freshness, fallback and unresolved exposure.
- **Strategies / Research / Work:** candidate lifecycle, study/prospective evidence, failures/inconclusive results, exact policy diffs, improvement uncertainty, authorization/revocation status and one contextual promotion action.
- **Home orb / notifications:** small factual summaries such as policy fallback, open exposure requiring attention or candidate ready for review. No public color legend or new dense home panel.

A claim like “learning active” is allowed only when the full configured producer–reducer–snapshot–selector consumer is bound and current. “Improved by X” must specify cohort, period, comparator, metric, uncertainty and whether real, demo or simulated. Do not celebrate profits or show a green unqualified token badge.

Every new control maps to a real backend operation and proof scope before UI. This revision reuses the existing 234 context obligations and adds capability bindings inside them; it does not multiply pages merely to display internal services. Both themes, stale/empty/error/unsupported/recovery states, TalkBack and real S24 tests remain required after BG-001.

## 13. Lean engineering and anti-overengineering acceptance

### 13.1 Capability coverage is not active-complexity permission

Build all owner-required capabilities, but do not run every model, every signal, every algorithm and every external judge on each trade. Use the smallest qualified active stack that satisfies the required use case. Dormant/research-only integrations remain usable, tested and inspectable—not deleted or hidden behind refusal stubs.

The reference incremental topology has **zero mandatory new deployable services**. New requirements attach to existing plan units and ports. A new daemon/database/broker path requires evidence of a real isolation, scaling or correctness need plus maintenance, failure and migration accounting. Do not split a pure function into a network call because its name sounds like a subsystem.

### 13.2 Complexity ledger

For each proposed mechanism, record the problem, current owner, minimum complete implementation, alternatives, incremental operational states/credentials/queues/jobs, latency/resource cost, failure surface, recovery/test burden, measured economic or reliability contribution and a simplification path. Separate safety-essential complexity from speculative profit complexity; ablation must never remove mandatory authority or reconciliation to make P&L look better.

Use simple baselines before ensembles, optimizer overlays or deep RL. Extra models can qualify for offline research without qualifying for T0. Avoid duplicated feature transforms, model registries, calibration owners, ledgers, confidence scores, dashboards and packet schedules.

### 13.3 Minimum complete path, not a thin MVP

First establish the full fixed-policy order/outcome/evaluation path; then the qualified operational learning update; then the complete governed challenger loop. Each stage has real positive and negative behavior and honest scope. Backend-first does not mean all integration is delayed: headless service/API tests run throughout backend development.

Do not use “avoid overengineering” to waive crypto execution, policy evolution, account management, model integrations or any existing full-product requirement. Simplify the implementation structure while preserving the required outcomes.

## 14. Integrated development and acceptance contracts

This supplement is integrated into `plan/DEVELOPMENT_PLAN.json`, not a competing schedule. Stable unit identities remain; additive operations, consumer contracts, requirements, tests and dependency edges are recorded in `contracts/self_optimization/UNIT_EXTENSIONS.json`. Packet sequence remains mechanically derived; numbers are always revision-qualified.

| Existing owner unit | Required extension |
|---|---|
| PRE-001 / PRE-002 / PRE-003 | Refresh evidence; admit latest two-autonomy/crypto scope; resolve conflicts; independent F15 before code. |
| BE-002 | Operational authority/grant verification and protected promotion boundary, without changing owner-risk policy. |
| BE-003 | Durable objective/outcome/reducer cursor/snapshot protocol; corrected-event reconstruction. |
| BE-004 / 005 / 006 / 007 / 008 | Spot crypto capability, account authentication, balances/fees/funds boundary, product/feed semantics. |
| BE-009 | Parent and multi-account reservations; hard constraints, intent ownership and scoped grant enforcement. |
| BE-010 | Full parent/child matching/lifecycle/protection/cancel/amend integration and compatible venue adapters; qualified baseline selector port. |
| BE-012 | Objective-level TCA, mature outcomes, fees/cash and residual observation semantics. |
| BE-013 / BE-035 | Strategy/policy distinction and validated execution/economic evaluator. |
| BE-021 / BE-022 / BE-028 | Asynchronous Jev/diagnosis, falsifiable hypothesis intake and bounded research triggers. |
| BE-036 | End-to-end automatic qualified selection and governed execution-policy evolution; existing jobs, study and artifact owners. |
| VAN-ML-PKT-007/010/021/022/023/027 | Targets, independent account replay, all-trial experiments, immutable artifacts, schedules and outcome lineage. |
| BE-032 / 033 | Complete owner/API read models, capability status, deployment/resource isolation and recovery. |
| BQ-001 / 002 / 005 / 007 / 009 / 006 | Crypto/financial concurrency, fault injection, closed-loop efficacy/replay, policy authority and independent global completeness. |
| BG-001 | Every new backend operation and its real acceptance evidence required before UX. |
| Existing UX/FE/QA units | Crypto and execution-learning contexts with locked themes, exact action semantics and physical acceptance. |

### 14.1 Full lifecycle acceptance

The application test registry defines exact preconditions, action, expected positive path, adverse mutation, recovery scenario, authoritative proof and actual owning unit for every new requirement. All entries are `NOT_RUN` in this specification delivery.

The following are non-optional end-to-end proofs:

1. Real registered outcome producer updates the persistent selector evidence and changes a later authorized choice; replay matches.
2. A full candidate progresses from registered hypothesis to independently qualified result and authorized test-environment binding; unauthorized activation is refused.
3. Mid-parent updates, expiry, revocation, source correction and restart preserve financial state and the correct pinned policy.
4. Partial-fill/cancel/replace/close uncertainty never creates duplicate or unreserved economic exposure.
5. Crypto spot completes a genuine permitted venue lifecycle and its actual fees/inventory reconciliation; mock-only provenance cannot pass a real-venue gate.
6. Both old and new markets remain covered, with full backend and consumer bindings before any native frontend development.
7. Baseline, updated policy and simulated counterfactual outcomes remain separately attributable; a candidate with no real improvement is rejected or inconclusive, not forced into production.
8. Removing a production observer/caller, owner grant check, crypto capability binding, tested fallback or any inherited requirement causes an actual named test/gate to fail.

### 14.2 Verification layers and authority

Document/schema/graph checks prove shape, links, declared preconditions, no-loss inventories and candidate mutations. They cannot prove actual money, event delivery, mathematical efficacy, authentic signatures, deployed runtime health or profitable trading. Runtime enforcers resolve typed proof references from trusted journals and issuer stores; a nonempty string is not proof.

Independent F15 certifies prepared implementation scope; BG certifies complete backend for the declared target; policy economic qualification establishes scoped evidence; financial promotion grants consequential use; physical acceptance qualifies the Android experience. None substitutes for another.

### 14.3 Remaining owner or external decisions

Select the first eligible spot exchange/account and instruments; confirm any procurement or financial permissions separately; sign the relevant operational policy bounds and later promotion; choose whether any explicit live exploration, derivatives or DEX signing scope is desired in a later amendment. Engineering proposes evidence-backed defaults but does not choose live risk values on the owner's behalf.

All current administrative/VM/task authorities remain governed by existing typed controls. Research/code verification belongs on the admitted VM topology; local file packaging here is document processing only. No physical desktop, new tunnel, broad root workaround or silent alternative runtime is part of this specification.

## 15. Final acceptance statement

VATI is not accepted as self-optimizing because a dashboard says it is, because a class named `observe` exists, or because a backtest improves after changing cost assumptions. Acceptance requires an integrated deterministic operational loop and a separately governed evolution loop, both demonstrated through real producers, durable state, registered consumers, valid alternatives, failure/recovery and replay.

VAN must be able to trade admitted spot crypto alongside its current markets through that same system. It must tell the owner what is actually running, what changed, why, what evidence supports the change, what its authority permits and whether the observed benefit is positive, negative or inconclusive.

The desired product is **a coherent trading application with a disciplined learning engine**, not a collection of autonomous bots. Profits are the economic objective to test; reliable financial behavior, complete capabilities and honest evidence are the engineering obligations to deliver.

## 16. Specification qualification and exact delivery boundary

This revision preserves 237 parent requirement objects and 1,328 parent application-test contracts, adding 64 requirements and 192 explicit positive/adverse/recovery acceptance contracts. The resulting 301 requirements and 1,520 planned application tests are all unimplemented/unexecuted claims until actual receipts exist. The 131 stable plan units, 82 backend capabilities, 12 backend verifier units, 234 screen/context obligations and 349 historical owner-action entries are retained; four new Product Truth clauses make 22 truth atoms. These inventories overlap; never sum them into a fabricated feature count.

The machine-readable contracts specify 12 strict record variants, five linked lifecycle machines, their typed proof predicates and independent semantic invariants. Passing a JSON Schema, a graph mutation test or a hash check does not verify money, source truth, an authentic grant, selector correctness, simulation fidelity, backtest profitability, F15, BG or a live production loop. A receipt containing those claims must be independently resolved against actual source/runtime/venue evidence.

The current pack's checks are document-processing and synthetic contract tests only. They do not run VAN production code, execute a trading backtest, call a broker, change a mandate or publish an application. Source observations remain pinned and scoped. The new required architecture is ready for independent Astra review; it is not self-certified for implementation or financial use.
