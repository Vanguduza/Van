# VATI — Deterministic Self-Optimizing Execution and Crypto Trading
## Revised architecture and complete lifecycle acceptance blueprint · Rev 5 / Unified Rev 1.17

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

Fresh HTTPS Git discovery and fetch materialized 67 branch heads and 101 PR heads at 121 distinct commits; PR open/merged state is not established by refs. PR101 remains `a39f241b0135cf92cc5a6b9a28af226aa294603d`; canon PR93 is `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`. The fetched review-input branch is `cbd059cfb1ddfb80766bdebc2c74d3b25302a992` and lacks several Opus source fixes. Tree inventories and selected file/function/caller evidence are retained in `evidence/rev115/source_review/`; this is bounded semantic review, not universal application qualification. Global DIAL access is authorized by the owner but no callable DIAL/Commander tool or configured connection was available in this session; native project/deployment identity remains unverified. No historical backtest or application test was run.

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

`cumulative_gross_executed_base + sum(max_remaining_executable(child)) <= approved_gross_parent_quantity`.

Gross executed quantity is reduced only by authenticated trade busts, never by base-asset fees, exits, internal netting or account inventory. Keep the multi-asset cash/inventory journal separate from the order budget. A buy of one base unit with a 0.01 base fee has 0.99 inventory and zero remaining buy allowance. A bust reopens factual reconciliation, not permission to retry; current objective, deadline, reservation and grant must be resolved again.

Reservations additionally cover worst-case cash/notional, fees, collateral, current holdings, contingent children and all strategy/manual demands under the true product payoff. A cancelled-but-unconfirmed or submit-unknown child counts until reconciled. For two-sided, hedged, netting or multi-leg objectives, apply the admitted scenario-based account exposure calculation, not this scalar shortcut.

Sibling replacement orders cannot both assume the same residual allocation. Use atomic amend only when the venue's exact semantics are qualified; otherwise cancel/query/reconcile then replace, or reserve the feasible overlap under a separately authorized protocol. External manual fills and provider balance changes revalidate the aggregate state.

### 5.3 Durable command protocol

Commit the command identity, reservation/fence version, payload digest, retry/query policy and parent link before attempting its economic side effect. Transactional outbox, order state and account journal share the existing atomic boundary where needed. Delivery retries are not claims of exactly-once network execution.

On lost acknowledgement: mark `OUTCOME_UNKNOWN`, preserve maximum possible exposure, query by known durable client/venue identifiers and reconcile. Retry only if the venue's idempotency contract and current evidence justify the exact same economic instruction. A missing order from one endpoint, especially an open-order endpoint, is not proof it never filled.

**Facts survive revocation.** A genuine late, manual, external or over-limit fill must still be recorded and reconciled when a grant expires or is revoked. Reject the unauthorized *command*, not the fact that an economic effect occurred. Mark policy breaches explicitly; block new risk where required and run protective recovery. Training admission is separate and may exclude the violation without deleting financial history.

**Late facts can reopen a reconciled revision.** Authenticated late fills, busts or financial corrections append a new child/parent revision and reopen reconciliation, even after a previously terminal cancellation, expiry or evaluation. Preserve the prior history, invalidate affected analytical measurements and prevent duplicate effects or blind resubmission. A terminal UI label is not permission to discard reality.

Unknown child recovery explicitly admits authenticated `OUTCOME_UNKNOWN → CANCELLED/EXPIRED` readback and `CANCEL_REQUESTED → OUTCOME_UNKNOWN` on lost replies. Terminal readback reconciles all partial fills and protection before releasing unused reservation. Cancellation requires exact ownership/scope authority, including its effect on manual and protective orders; authority to record a late fact remains separate.

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

Participation, slice count, lot/notional minimum, depth freshness and deadline are joint constraints. Clamping a required 80 slices to eight does not preserve participation. With quantity 200, depth 10 and cap 0.25, eight equal slices of 25 breach a 2.5 per-snapshot limit. Wait/replan only within the authorized lifetime using newly observed depth, or refuse the infeasible plan; never reuse the same displayed liquidity as independently replenished liquidity. Persist cumulative attempts, replacements and rate budgets across restart. Protective reduction uses its own qualified domain; urgency cannot override it.

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

**Accounting oracle:** the implementation must reconcile its decomposition to direct signed `sum(fill_qty × (fill_price − decision_reference))` in correct contract/quote units, plus only nonembedded charges. Do not add spread again when the fill/reference difference already includes it. With buy decision/arrival 100, submitted/fill 99, quantity 1 and spread 2, direct cost is −1 before fees; the inspected source formula yields +1. Separate submitted-to-arrival movement, execution residual, fee postings and residual opportunity benchmark. Every fee asset has an actual quantity and valuation provenance; unknown valuation remains unknown. Mature measurements cannot contain null required cost totals.

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

Revision precedence is source-defined and retained with source identity, scope, logical parent and revision chain. Arrival cursor controls availability; it does not rank competing revisions. A late older revision remains in history without replacing newer current truth. Equal revision/different payload is quarantined; a missing predecessor or incompatible private-stream/REST version requires authoritative reconciliation. No fabricated global venue sequence is assumed. Admission provenance must resolve the original authenticated environment; editing a LIVE enum cannot change it.

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

### 8.6 Learning from trading experience — complete owner requirement

Van must learn from its actual trading experience and use defensible evidence to improve strategy decisions and execution. It must investigate profitable, losing, flat, rejected, missed and deliberately skipped opportunities; determine what is known about their outcomes; propose testable improvements; and apply independently qualified improvements through the existing operational and policy-evolution paths.

The objective is improved future net, risk-adjusted expectancy and operational reliability within the owner’s risk mandate. Similar setups cannot be guaranteed profitable. A single outcome cannot establish an edge or uniquely reveal its cause. Van must be able to conclude **expected loss under a still-supported strategy**, **lucky outcome without demonstrated edge**, **execution defect**, **regime-dependent evidence**, or **insufficient evidence**, with the strength and limitations of each conclusion visible.

The relevant loop is:

`point-in-time opportunity → decision and execution → reconciled outcome → evidence-based diagnosis → registered hypothesis → independent evaluation → qualified change → later decision → monitoring and restatement`

#### 8.6.1 Preserve what was knowable before the outcome

The existing event and outcome owners must retain a versioned experience record for every eligible opportunity, including those not traded. It must bind:

- Account, venue, instrument, opportunity/parent/child IDs, market-data source and revision, event time and availability time, and live/demo/paper/simulation provenance.
- Setup definition and version, features available at decision time, regime classification and its version, relevant missingness, liquidity, volatility, spread, session and available capital. A regime learned from later outcomes cannot be retroactively treated as known at entry.
- Strategy/model/policy/feature versions, evidence snapshot, calibrated predictive distribution where qualified, expected payoff and costs, uncertainty, admissible alternatives, selection/abstention reason, risk constraints and owner overrides. An uncalibrated score remains an uncalibrated score.
- Intended entry/exit/protection and quantity, actual order lifecycle, fills/non-fills, fees and financing where applicable, cash/exposure reconciliation, benchmark and evaluation horizons fixed before outcomes are examined.
- Original decision evidence and separately revised analytical evidence. Later source corrections may restate an analysis, but cannot rewrite what Van knew or decided at the time.

Setup similarity is a versioned, validated rule over available features, not a retrospective resemblance selected because two trades won. Feature selection, cohort discovery and similarity learning consume the research trial budget and may not inspect their held-out evaluation outcomes. Sparse or unsupported cohorts use an approved broader population or static fallback, with the transfer assumption disclosed.

#### 8.6.2 Diagnose outcomes without inventing causes

The trade review separates four questions:

| Question | Required treatment |
|---|---|
| What happened financially? | Reconcile actual prices, quantity, cash and charges; distinguish realized P&L, marked exposure and simulated opportunity costs. |
| Was the strategy decision supported? | Compare the ex-ante forecast, selection, sizing and exit hypothesis with its declared distribution and cohort evidence. A loss alone does not invalidate the strategy. |
| How did execution affect the outcome? | Attribute measurable delay, fill quality, missed execution, fees, venue failures and protection behaviour using consistent benchmarks. Avoid double-counting spread or confusing lower execution cost with profitable alpha. |
| What remains unexplained? | Retain residual variation, incomplete data, competing explanations and identification limits. Do not force every outcome into one confident causal story. |

Accounting decomposition, statistical association, simulated counterfactual and causally supported effect are distinct claim types. Every diagnosis carries source/evidence references, method/version, comparison population, uncertainty and explicit alternatives. Feature importance, a chart narrative or an LLM explanation is not causal proof. Residual P&L is not automatically proven luck.

Jev or another admitted reasoning component may summarize records and propose falsifiable hypotheses. It cannot turn narrative confidence into a win probability, independently qualify its own proposal, or change the live strategy merely by explaining a trade.

Examples of useful hypotheses are “this entry loses its apparent edge after fees in thin sessions,” “the signal remains supported but this order method suffers adverse selection,” and “the observed loss lies within the strategy’s expected drawdown distribution.” Each must state what evidence would refute it.

#### 8.6.3 Distinguish repeatable evidence from chance

Qualification must test incremental performance against appropriate baselines and plausible no-edge explanations. It must include:

1. A preregistered hypothesis, ex-ante cohort, comparator, economic materiality, risk/exposure constraints, evaluation horizons, sample unit, uncertainty method, stopping rule and complete trial budget.
2. Chronological development/validation and protected evaluation windows; purge or embargo overlapping labels where required. Outcomes used to discover a hypothesis cannot also count as its untouched confirmation. A consumed holdout becomes development evidence; future confirmation requires new protected data.
3. Dependence-aware uncertainty and effective independent sample size. Multiple fills, overlapping trades, repeated markouts and correlated instruments or regimes cannot be counted as independent repetitions merely to reach a threshold.
4. Complete retention of failed, pruned and human/LLM-proposed alternatives; an appropriate selection/multiple-testing adjustment. No repeated peeking with ordinary fixed-sample significance thresholds. Use registered review windows or a valid sequential procedure.
5. Justified null/control experiments that preserve the market, temporal dependence and opportunity structure relevant to the claim. Naively shuffling all prices or choosing a weak random baseline is insufficient. Evaluate false discoveries over a prespecified ensemble; an individual null realization can occasionally pass a statistical threshold.
6. Net economic results after realistic costs, missed fills, capacity constraints and stress, with downside/tail outcomes and capital usage. Higher win rate, gross return or exposure alone is not improvement. Compare complete independent account paths when changed decisions alter later opportunities.
7. Feature and mechanism ablations that retain mandatory risk/reconciliation controls. A more complex model must demonstrate incremental value against a simpler qualified alternative.
8. Prospective shadow/demo or otherwise admitted forward evidence, with its difference from actual live matching explicit. Cohort/regime coverage, drift and expiry limit transfer to future conditions.

Insufficient power, poor support, disagreement, missing costs or nonidentifiable counterfactuals produce `INCONCLUSIVE` or a scoped unsupported claim—not “proven random” and not permission to trade. P-values, DSR, PBO, model confidence and trade-win probabilities retain their different meanings. No finite test guarantees that a detected pattern will persist.

#### 8.6.4 Improve both strategy and execution through their actual consumers

Strategy changes may concern entry filtering, abstention, supported regime selection, exits or risk inputs within the existing authority model. Execution changes may concern a qualified order method, scheduling, participation or other approved parameters. Keep their objectives and evidence separate so that an execution improvement is not misreported as a strategy edge.

For each proposed change, record the experience/cohort that motivated it, falsifiable hypothesis, exact artifact/configuration diff, expected mechanism, comparator, evidence, costs, uncertainty, affected scopes, rejection conditions and rollback/fallback.

- **Operational learning:** the approved update rule may update learned state and select among already qualified alternatives within current bounds, without a new owner prompt for each choice. Record the snapshot and the reason a later eligible choice changes or stays the same.
- **Policy/strategy evolution:** new logic, feature definitions, update rules or parameter domains follow the existing registered research, independent qualification and promotion process. Standing grants apply only within their actual scope; a profitable anecdote does not enlarge them.
- **Monitoring:** retain comparable before/after cohorts, selection effects, drawdown and drift monitoring. Suspended or expired evidence triggers the qualified fallback or abstention path as appropriate. Preserve urgent protection and reconciliation even if analytical services are unavailable.
- **Correction and replay:** duplicated or corrected events, crashes and restarts must reproduce the appropriate learned state and later selection without duplicating financial effects. A corrected observation can invalidate dependent conclusions and candidates; retain the lineage and original decisions.

A complete implementation must demonstrate a real producer-to-consumer strategy improvement loop and an execution improvement loop in controlled admitted environments. Refusing every candidate or producing review text without changing any qualified downstream decision is not completion. Controlled fixtures prove the mechanism; real economic efficacy still needs its own evidence.

#### 8.6.5 Owner-visible information and controls

Extend existing contexts; no new global tab or separate learning service is required.

| Existing context IDs | Required information / controls |
|---|---|
| `VNX-S-ORDERS-11`, `VNX-S-ORDERS-12` | “What happened?”, decision-time evidence, financial decomposition, execution contribution, competing explanations, data gaps and links to the exact supporting records. |
| `van.next.trading.pattern-candidates`, `VAN-S-CX-STRATEGY-DEVELOPMENT` | Proposed lesson, similarity/cohort definition, supporting and contradicting observations, research state and the difference between an anecdote and supported evidence. |
| `VAN-S-CX-CANDIDATE-COMPARISON`, `VAN-S-CX-EXPERIMENT-LEDGER` | Baseline versus candidate, net utility and uncertainty, complete trial history, prospective evidence, exact policy diff and why a candidate passed, failed or remained inconclusive. |
| `van.trading.strategies`, `VAN-S-CX-RISK-POLICY-ACTIVATION` | Active strategy/update-rule version, learning freshness, current fallback, what changed and why, and existing scoped pause/review/promote/revoke controls with authoritative readback. |

BE-032 must expose these as typed backend read/action contracts before frontend design acceptance. The read model needs stable trade/cohort/hypothesis/study/candidate/binding IDs, revision/cutoff, evidence grade, result/uncertainty, consumer impact and provenance. Commands need the existing actor/account scope, expected version, idempotency, authority checks and outcome reconciliation. Pagination and revision-aware updates must handle large histories and late corrections.

The typed records, logical operations and exact proposed HTTP mappings are specified in `contracts/self_optimization/EXPERIENCE_LEARNING_CONTRACT.json` and `EXPERIENCE_LEARNING_RECORDS.schema.json`; they are required implementation contracts, not deployed URLs. The concrete route/schema/caller mapping and backend positive/error/recovery tests must be entered into the existing service and screen registries before BG-001; an invented endpoint name is not acceptance evidence. The app must distinguish learning, pending maturity, insufficient evidence, stale evidence, service failure, suspended policy and no eligible method. It must not present those states as zero cost or successful improvement.

#### 8.6.6 Traceability to the existing implementation plan

| Existing unit | Additional explicit completion obligation |
|---|---|
| `PRE-002`, `PRE-003` | Verify the integrated VAN-EL-001…007 requirements, EL-AT-001…014 positive/adverse/recovery contracts and preserved inherited scope; independently admit the exact implementation boundary. |
| `BE-003`, `BE-012`, `VAN-ML-PKT-027` | Preserve point-in-time experience, reconciled outcome/attribution lineage, skipped opportunities and corrections. |
| `BE-013`, `BE-021`, `BE-022` | Versioned setup/cohort definitions, evidence-grounded diagnosis, calibrated interpretation and falsifiable hypotheses. |
| `BE-035`, `BQ-009` | Qualify evaluation, null controls, effective sample size, multiple-trial handling, prospective confirmation and uncertainty. |
| `BE-036`, `BE-028` | Complete bounded strategy and execution learning loops, research scheduling, promotion, monitoring and rollback. |
| `BE-032`, `UX-001`, `FE-011`, `FE-012`, `FE-014`, `FE-023` | Backend operation/read-model mappings and existing-context presentation of diagnoses, evidence and changes. |
| `BQ-005`, `BQ-007`, `BG-001` | Independent integration, fault/replay, anti-bypass and completeness evidence before frontend entry. |

Existing coverage being refined includes `VAN-NX-061`, `VAN-ML-REQ-048`, `VAN-CX-010`, `VAN-CX-013`, `VAN-HVA-025`, `VAN-HVA-028`, `VAN-SO-028`, `VAN-SO-030`, `VAN-SO-032`, `VAN-SO-038`, `VAN-RV-003` and `VAN-RV-006`. The identified gap is a unified, explicit experience-to-diagnosis-to-qualified-strategy/execution contract, not the absence of all learning or statistical safeguards in Rev1.15.

#### 8.6.7 Acceptance, typed records and consumer bindings

`traceability/REV116_REQUIREMENTS.json` adds seven requirements to the main requirement registry. `verification/REV116_ACCEPTANCE_CONTRACTS.json` adds all 42 positive/adverse/recovery contracts for the 14 retained owner scenario IDs to `verification/TEST_CONTRACTS.json`. Every test has an owning unit, prerequisites, action, expected result, independent oracle and receipt bindings; every one remains NOT_RUN. The generated plan names them explicitly. Actual application command bindings and execution receipts are required at unit acceptance, not fabricated here.

`contracts/self_optimization/EXPERIENCE_LEARNING_CONTRACT.json` defines existing owners, record and API operations, qualification invariants and consumer paths. Its strict record schema and examples specify typed evidence and unknown states. `design/EXPERIENCE_LEARNING_CONTEXT_BINDINGS.json` extends the existing screen registry through its explicit extension reference. BE-032 must resolve these proposed routes against admitted source, implement and qualify their concrete handlers and Android callers before BG-001. No backend completion follows from registering a route.

The experience-to-strategy and experience-to-execution paths each require their own later-decision proof. Disconnecting either actual observer must fail EL-AT-012-NEG. Statistical fixtures must show power on known controlled alternatives as well as measured false-discovery control on a registered no-edge ensemble; a blanket refusal is not acceptance. All software, economic, financial and device gates retain their separate meanings.

#### 8.6.8 Required records and acceptance scenario index

| Typed record | Required meaning |
|---|---|
| `TradeExperience` | Original decision, point-in-time features/setup/policy, every eligible opportunity, maturity, reconciled economics and correction lineage. |
| `TradeDiagnosis` | Financial decomposition, explicit claim type, evidence and method, alternatives, uncertainty and identification limits. |
| `LearningHypothesis` | Refutable question, strategy/execution target, cohort and comparator, development versus protected data, complete trial and statistical/economic protocol references. |
| `EvidenceAssessment` | Independent evaluation, effective sample definition, null and power controls, selection adjustment, net economics and prospective support; pending/supported/rejected/inconclusive/invalidated state. |
| `LearningChange` | Exact old/new artifact diff, learned-state versus policy change, binding state, qualified rule/authority, actual consumer receipt, monitoring and fallback. |
| `LearningCommand` / `LearningCommandReceipt` | Actor/account/target/revision/idempotency/authority-bound request and separate accepted/running/succeeded/rejected/unknown outcome; success requires native readback. |

The schema defines strict required fields and conditional evidence references. Native owners must resolve those references and enforce truth, scope and current authority; successful JSON validation never establishes a causal effect or grants promotion.

All scenarios below expand into distinct `-POS`, `-NEG` and `-REC` entries in the main test registry and generated unit contracts. All 42 remain NOT_RUN. PRE-002/003 perform documentary scope admission, not these application tests. These 42 backend contracts run headlessly before BG; frontend unit references identify later consumer obligations. Native UI, accessibility and S24 acceptance stay after BG under the existing frontend/QA contracts.

| Scenario | Required outcome | Primary unit |
|---|---|---|
| `EL-AT-001` | A controlled strategy with a specified positive expectancy has a valid losing trade. Diagnosis preserves the supported strategy, reports the loss in its distribution and does not rewrite policy from one outcome. | `BE-022` |
| `EL-AT-002` | A no-edge or negative-net-edge process produces lucky winners. Van does not infer skill from that streak alone; a preregistered null ensemble checks false-discovery control with declared statistical tolerance. | `BE-035` |
| `EL-AT-003` | A controlled supported signal is paired with a bad execution method. Independent cash/cost oracles identify the execution contribution; a qualified replacement improves execution under equal constraints without claiming new alpha. | `BE-036` |
| `EL-AT-004` | A repeatable controlled regime-specific strategy opportunity is discovered only in development data, confirmed on protected chronological data, qualified and bound in an admitted test environment; a later matching decision changes through the real strategy consumer. | `BE-036` |
| `EL-AT-005` | An attractive result caused by future data, post-outcome setup grouping or repeated holdout tuning fails qualification; correcting the pipeline requires genuinely protected re-evaluation. | `BE-035` |
| `EL-AT-006` | Thousands of variants, failed trials and correlated child fills cannot manufacture independent evidence or evade selection adjustment; incomplete trial provenance blocks promotion. | `BQ-009` |
| `EL-AT-007` | A regime shift, sparse cohort or incompatible market exposes unsupported transfer. The selector reports insufficient/stale support and uses a qualified fallback; later fresh qualifying evidence permits recovery. | `BE-036` |
| `EL-AT-008` | Gross gains disappear after fees, adverse selection, missed fills or increased exposure. The candidate fails net utility/noninferiority criteria; a no-trade comparator cannot erase obligatory protective work. | `BE-035` |
| `EL-AT-009` | Duplicate, corrected and conflicting observations plus crashes before/after persistence leave one valid contribution, invalidate dependent analytics where required, and replay the same snapshot/choice without new orders. | `BQ-005` |
| `EL-AT-010` | A plausible LLM explanation, feature importance or unsupported simulated alternative is never relabeled causal evidence or calibrated win probability; cited known facts remain separately inspectable. | `BE-022` |
| `EL-AT-011` | Unqualified, expired, revoked and wrong-account changes fail at the binding/consumer boundary; an authorized compatible fallback and open-parent reconciliation remain available. | `BQ-007` |
| `EL-AT-012` | Removing the actual strategy or execution outcome consumer makes the corresponding later-choice integration test fail. Restoring it recovers from the durable cursor; a direct test-only observe call cannot satisfy acceptance. | `BQ-007` |
| `EL-AT-013` | Android read models expose exact before/after state, uncertainty and provenance; stale/offline/partial/error views remain distinct. Commands enforce authority/version/idempotency and reconcile their results without optimistic false success. | `BE-032` |
| `EL-AT-014` | Skipped/rejected/missed opportunities and changed capital availability remain in complete cohort/account comparisons. Unobserved alternatives remain simulated or unidentified, never fabricated actual fills. | `VAN-ML-PKT-027` |

### 8.7 Hardened self-improvement with shared Jev and qualified model challengers

This section makes model-assisted improvement a required, testable research and integration capability. It grants no model, Jev judgment, benchmark score or generated explanation authority over the risk mandate or an order. Preserve all prior model integrations and required financial capabilities; evaluate which components deserve an active role through measured contribution. New models are challengers until their exact task, data, artifact and consumer scope qualify.

#### 8.7.1 Source findings that the implementation must resolve

The bounded source review is recorded in `research/REV117_MODEL_AND_PROFITABILITY_REVIEW.md` and `evidence/rev117/source_probes.json`. It is not a fresh whole-estate audit or deployed-runtime qualification.

- The current `ModelRecord.qualified` property can return true for 50 resolved disagreements with mean 0.021 R and missing calibration. It has no uncertainty, search-selection or model-cost inputs. Retain it only as an explicitly legacy diagnostic; it cannot satisfy the new economic admission contract.
- Existing calibration uses resolved disagreements and the target “this change helped.” That is not trade-win probability or overall strategy calibration. Measure each target on its eligible population, account for unresolved/missing outcomes and compare with an appropriate base-rate forecast, not merely a fixed Brier 0.25 cutoff.
- `blind_packet` copies caller context and narrative; injected author/model identity survives that function. Blind-review packet construction must use an allowlisted representation, strip structured identity and test narrative leakage. Independence must also be established through access separation and objective verification, not asserted from a different model name.
- `AccountCoordinatorService._risk` calls synchronous `cognition.wake` before returning its decision. Configured network inference can therefore delay the caller. Move research invocation behind the existing durable asynchronous work boundary, not just a shorter timeout. Source inspection establishes the call ordering; it does not establish deployed latency.
- The runtime cognitive budget is checked before a fallback loop and spent after successful normalization. Provider-scheduler counters separately count acquisitions. Unify admission/reservation/settlement across these owners so rejected answers, retries, unknown bills, restarts and parallel workers cannot escape the global research budget.

These are explicit implementation obligations in VAN-JM-001…008. This blueprint does not claim the source defects are repaired by writing those requirements.

#### 8.7.2 Responsibilities and the complete control boundary

Reuse the existing shared `dial-jev` service and VAN consumer-scoped credentials. Jev supplies bounded, typed judgments: evidence sufficiency, contradictory claims, hypothesis quality, data-quality concerns and whether an explanation supports its stated conclusion. It is a useful critic and evidence-processing component. Its Score/NouL primitives, `apply_effect` flag and result fingerprint are not calibrated trade-win probabilities, financial permission or independent qualification.

Proposed trading judgment modules must be admitted by the existing Jev module owner with exact input/output schemas, data policy, consumer, outcome target and evaluation protocol. Attention/browser judgment modules cannot be relabeled trading modules. SHADOW, disabled, expired, unsupported and failed responses preserve the qualified baseline. Native consumers verify module/project/account scope, input digest, availability cutoff, output type, calibration, revision, expiry and revocation before using an annotation.

A research model such as Gemini 4 Argon or DeepSeek may inspect admissible evidence, formulate/refute hypotheses, propose features or candidate code in an isolated workspace, and explain evaluated results. Existing numerical engines compute indicators, cash, sizing, execution and statistical tests. Independent verification evaluates the candidate; existing policy owners qualify/promote it; deterministic RiskAuthority and the router retain final financial enforcement. Generated code cannot execute in the live process or mutate a signed policy.

The default live decision uses a current qualified snapshot. No synchronous model/LLM/Jev RPC, remote retrieval, model fallback cascade or training work may block submission, cancellation, stop/protection or reconciliation. Bounded asynchronous ingestion publishes durable work; an unavailable analytics queue must have a tested failure/overflow policy while urgent protection continues. Warmup, queue growth, total memory, concurrency and inference budgets are measured under declared target load. A stalled research process cannot hold an account execution lock.

#### 8.7.3 Model identities and recommended first comparison

Primary-source documentation retrieved on 2026-10-18 verifies Google **Gemini 4 Argon**, API identifier `gemini-4-argon`. It is a general reasoning/multimodal model, not a finance-profit oracle. DeepSeek’s current documentation lists `deepseek-v4-pro` served by DeepSeek-V4-Pro-0813 and `deepseek-flash` served by DeepSeek-V4.1-Flash-1017. Older Flash names are accepted but redirected to the newer served model. These are observed documentation identities, not proof of access, immutable weights, production readiness or superiority on VAN’s tasks.

Recommended offline/prospective comparison arms, all on the same frozen opportunity/data eligibility and economic constraints:

| Arm | Role and question |
|---|---|
| A — qualified quantitative baseline, no new reasoning model | Establish what existing rules/required forecasting models achieve after all costs. |
| B — A plus the existing admitted shared Jev path | Does structured evidence critique improve decisions or research quality beyond its operating cost? |
| C — B plus Gemini 4 Argon | Does deeper hypothesis generation, contradictory-evidence analysis and long-document reasoning yield independently confirmed incremental value? |
| D — B plus DeepSeek V4 Pro | Can a different general reasoning challenger deliver better net contribution, reliability or cost on the same task? |
| E — optional DeepSeek Flash allocation | Can bounded extraction/triage reduce research cost while retaining quality? Admit only if it beats the simpler routing baseline. |

Do not replace the current model hierarchy or remove existing forecasting integrations by this comparison. The current source model hierarchy is a distinct contract that requires explicit reconciliation at source admission. A challenger that wins a research task is not automatically eligible for a live predictive task. Select an active model by exact task/cohort evidence and total cost, not by brand or model size.

Preserve Qlib/LightGBM and required NeuralForecast models as numerical forecasting baselines. Google TimesFM is a separate forecasting research option, not the same product as Argon. Its currently documented 3.0 downloadable weights have a different license from the source code and earlier weights; use must satisfy the actual route-specific terms. Neither a financial-language benchmark nor a generic forecasting benchmark establishes net trading alpha.

#### 8.7.4 Provenance, replay and model-weight leakage

An invocation identity binds provider/account route, requested model, resolved served revision where available, endpoint/API version, prompt/template hash, system policy, retrieval/tool/data manifests, decision cutoff, inference parameters, all returned structured outputs, request/response hashes, timing, costs and consumer scope. Replay uses the recorded admissible response and downstream decision—not another paid inference call. Seeds or temperature zero do not guarantee identical provider output, and some reasoning APIs ignore sampling controls.

Treat model, prompt, retrieval index, feature transform, calibration, tool policy or served-version changes as new evidence epochs. Mutable aliases require observed revision binding where offered and continuous behavioural/contract checks. Unknown or changed identity cannot inherit old qualification; restrict it to nonconsequential research or the qualified fallback until requalified. Canary checks detect some changes but do not prove immutable weights.

A historical prompt can contain only pre-cutoff data while the model’s weights already encode later news, prices or outcomes. Retrieval time filters alone cannot solve this. Record training-cutoff/contamination uncertainty, apply identity/time masking and placebo tests as diagnostics, and label historical LLM backtests accordingly. Economic confirmation requires genuinely prospective, sealed outputs on outcomes not yet observed, or independently justified historical model/data availability. A model’s statement that it did not use future knowledge is not evidence.

#### 8.7.5 Untrusted evidence and independent review

Source documents, retrieved memories and model outputs are untrusted data. Validate provenance, source time, revision and citations against archived admissible material. Source deduplication must prevent copied articles, correlated agents and repeated model answers from becoming independent confirmations. A fluent explanation without supporting evidence remains a hypothesis.

Use an explicit data allowlist and tenant/account isolation before external inference. A caller-supplied `INTERNAL_SANITIZED` label alone proves nothing. Strip credentials, personal/account identifiers and unnecessary private positions; bind any allowed sensitive use to existing data policy. Research tools are scoped and audited; model text cannot authorize additional tools, network destinations, account reads or trades. Inject malicious instructions in news, filings, retrieved analogues and tool results; the resulting model output must not escape the typed consumer boundary.

Separate discovery, challenger construction, review and holdout custody. Allowlisted blind packets suppress structured author/model identity, confidence cues and accidental outcome clues; test free-text leaks and residual reviewer bias. Keep contradictory and uncertain reviews, reviewer canaries and access logs. Two providers sharing the same unsupported narrative are not independent evidence. A model reviewer never replaces mathematical, accounting, execution and holdout oracles.

#### 8.7.6 Economic qualification and profitable-use criteria

Distinguish execution cost, strategy alpha, calibrated outcome probability, explanation quality and model contribution. All have different denominators and targets. The primary model-use comparison is incremental **net whole-account utility** versus the simpler qualified baseline at comparable capital, exposure and risk, with explicit downside and operational noninferiority. If model/data/compute costs are already posted to the account view, do not deduct them again.

Register the allowed search space, complete trial census, dataset and model availability cutoffs, cohort/similarity rule, comparator, cost model, sample/cluster unit, minimum economic materiality, uncertainty procedure, selection adjustment, review windows and stopping rule before observing confirmation outcomes. Use dependence-aware uncertainty, leakage controls, risk-matched account replay and fresh prospective confirmation. A lower uncertainty bound exceeding a prespecified materiality threshold is meaningful only under its stated assumptions and selection scope; no universal sample count or p-value is sufficient.

Calibration must specify the exact prediction target and horizon, score all eligible predictions with honest maturity/missingness accounting, and compare proper scores with an appropriate base-rate/reference model. A disagreement-only “change helped” score cannot be relabeled trade probability. Missing calibration blocks probability-dependent use; it need not prohibit a separately qualified non-probabilistic explanation task.

Accept one of: scoped benefit supported; simpler baseline retained; inconclusive; or rejected. A feature can be correctly implemented yet add no economic value. Known controlled alternatives must demonstrate evaluator power; registered null ensembles measure false discoveries. A model cannot qualify by refusing every useful task, deleting losses, increasing leverage, omitting costs or issuing confident narratives.

#### 8.7.7 Prioritized profitability research programme

These are falsifiable experiments, not promised profit. Run them through the existing evaluator, experiment ledger and bounded scheduler. No new live exploration, paid provider usage or procurement is inferred beyond current grants.

1. **Execution drag first:** locate economically material spread/slippage/adverse-selection, missed-fill and timing costs on matched objectives; compare qualified order/scheduling policies with realistic depth, fees and deadlines. Retain required protection. Owner benefit must survive whole-account effects.
2. **Better trade selection and abstention:** test whether point-in-time event, liquidity and regime information identifies negative-net-expectancy opportunities. Compare opportunity coverage, false abstentions, drawdown and net utility; a higher hit rate alone is insufficient. Jev critiques evidence; numerical models estimate the registered target.
3. **Reasoning-assisted strategy research:** compare the A–D arms on sealed tasks with the same accessible information, declared compute budgets and independent confirmation. Freeze each proposed lesson before holdout access; all human/LLM prompt and code revisions count as trials.
4. **Event/filing information extraction:** test verified release timing, source quality and factual extraction before testing an economic signal. Measure latency, already-priced information and corrections. Broad access to text is not itself an informational advantage.
5. **Capital efficiency and exits:** test approved sizing inputs, correlated exposure, exits and turnover at equal risk constraints through the existing risk owner. Reject improvements driven only by higher leverage or altered accounting. Never widen stops or alter live mandates to make the comparison win.
6. **Research economics:** route expensive reasoning only when preregistered expected value of information and task impact justify it. Measure cost per valid hypothesis, independently confirmed improvement, time to decision and total lifecycle maintenance cost. Selective escalation cannot use future outcomes or evade logging unsuccessful work.

The experiment register defines exact arms, estimands, false-positive controls, required dataset/cost/qualification bindings and continuation criteria. Results stay NOT_RUN until actual admitted execution receipts exist. Prefer the least complex active design that demonstrates incremental value, while preserving the required software capabilities.

#### 8.7.8 Durable budgets, retries and failure isolation

Reserve a conservative maximum monetary/token/tool-call allowance atomically before every provider attempt across all workers, providers and retry paths. Settlement records actual usage or a conservatively retained unknown liability. Failed parsing, timeouts, rejected answers, fallback and cancelled requests may still cost money; do not charge only accepted outputs. Provider quota counters and the research financial budget must reconcile without double counting.

Use durable operation/attempt IDs, per-run and per-window limits, bounded concurrency/deadlines/backoff, cache keys bound to complete context/policy identities, and restart-safe reservations. Cached results cannot bypass scope/expiry checks. Recovery queries the original attempt where supported; otherwise preserve outcome/cost uncertainty. Exhaustion degrades to the admitted cheaper or no-model route and cannot relax safety, reset counters or spawn unlimited alternative agents.

#### 8.7.9 Controlled adaptation, drift and owner visibility

Maintain separate procedural health, economic health, calibration health, data health and provider health. A policy-compliant losing strategy can still have a decaying edge. One ordinary loss must not provoke a rewrite, but repeated evidence of degradation must not be ignored merely because each trade obeyed the rules. Use registered sequential/windowed monitoring, hysteresis, minimum persistence, maximum change rate and compatible fallback. Sudden data/authority/safety invalidity can require immediate suspension independently of statistical patience.

Preserve original decisions and every policy/evidence epoch. Restatements invalidate dependent studies and bindings according to their scope; recovery needs qualified, current evidence. Neither a fallback nor a restart may resurrect revoked policy. All urgent risk-reduction and reconciliation paths continue independently of model health.

Existing model-registry, calibration, candidate-comparison, experiment-ledger and judgment-provenance screens show requested versus served model, Jev module/effect state, role, evidence/cost/latency, calibration target, incomplete outcomes, task-specific qualification, budget/retries, drift/fallback and precise changes. Expose provider failure, insufficient evidence, unknown identity and inconclusive economic value distinctly. Use existing backend read/control contracts; native authority remains required for consequential changes.

#### 8.7.10 Implementation and acceptance binding

`traceability/REV117_REQUIREMENTS.json` and `verification/REV117_ACCEPTANCE_CONTRACTS.json` are merged into the main registries and generated plan. The machine model-use contract is `contracts/self_optimization/MODEL_USE_CONTRACT.json`; the source-grounded model comparison and profitability experiments are in `research/REV117_MODEL_AND_PROFITABILITY_REVIEW.md` and `research/PROFITABILITY_EXPERIMENTS.json`. Context additions are explicitly referenced from the main surface registry.

BE-003 owns durable invocation/budget/response lineage; BE-021/022 own typed Jev evidence and hypothesis consumers; BE-013/035/036 own task-specific numerical calibration, evaluation and adaptation; BE-002 owns existing authority; BE-028 owns bounded scheduling; BE-032 owns exposed contracts. BQ-005/007/009 require isolation, failure/replay and independent economic evidence before BG. PRE admission remains documentary; frontend/device proof remains after BG.

Acceptance must exercise favourable evidence and actual later consumers, adversarial identity/leakage/calibration/budget/reviewer failures, and crash/correction/fallback recovery. Document verification can reject omitted obligations and malformed claims; it cannot establish that a hosted model is profitable, licensed for an account, reachable or implemented.


## 9. Governed evolution: complete lifecycle

### 9.1 Candidate stages and invariants

A candidate follows `HYPOTHESIS_REGISTERED → BUILDING → OFFLINE_EVALUATING → OFFLINE_ACCEPTED → PROSPECTIVE_EVALUATING → QUALIFIED_CANDIDATE → AWAITING_AUTHORIZATION → AUTHORIZED → ACTIVE_BINDING`, with rejected, inconclusive, failed, cancelled, suspended and retired branches. Expiry and revocation invalidate the associated grant/binding at every relevant preactivation, active and draining state; explicit EXPIRED/REVOKED transitions persist the cause. Failed/cancelled offline and prospective work retains its complete trial record. Stopping research due to expiry or revoked budget never requires fresh permission to continue research; rollback activates a separate compatible qualified binding rather than inventing a candidate state or rewriting its history. The linked candidate and binding machines express these separate dimensions. Stage names are versioned contracts mapped to existing owners, not a second live policy database.

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

The inspected historical harness uses fixed bid-to-quote offsets, fixed USDJPY conversion, deterministic open-low-high-close marks, raw versus governed account modes, a 400-bar window and earlier integrity/tick/slippage workarounds. Qualify bid/mid interpretation, feasible intrabar ambiguity, conversion at each cash/valuation event and warmup sensitivity before using its results as a deployment oracle. Yearly summaries are not walk-forward fits and the peek-P&L difference is only a negative control. Full source/data versions, licensing, trial census and preregistered evaluation remain required. The historical research isolated strategy behavior using documented harness changes. Preserve those experiments as research; do not relabel them production-faithful evidence. Compare strategy-isolation and deployment-faithful runs separately. Reproducing a source calculation is not proof of venue behavior.

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

Provider selection must resolve owner jurisdiction/account eligibility, access, fee tier, real matching target, instrument scope and the required protection semantics before adapter acceptance. Mandatory attached broker-side protection for manual entries is not relaxed for convenience: unsupported products/order paths remain ineligible and cannot close the mandatory integration. A real matching target with authorized balances may be necessary; this review does not authorize creating/funding accounts or sending live orders. The target is unresolved until evidence establishes an eligible venue, not silently defaulted to a named exchange.

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
7. Both strategy and execution experience loops satisfy §8.6 and all EL-AT scenarios. Baseline, updated policy and simulated counterfactual outcomes remain separately attributable; a candidate with no real improvement is rejected or inconclusive, not forced into production.
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

Rev1.17 preserves all 316 Rev1.16 requirement objects and all 1,586 Rev1.16 application-test contracts, adding eight Jev/model self-improvement hardening requirements and 24 positive/adverse/recovery contracts. The active totals are 324 requirements and 1,610 planned application tests; every test has execution_state NOT_RUN. The 131 stable plan units, 82 backend capabilities, 12 backend verifier units, 234 screen/context obligations, 349 historical owner-action entries and 22 Product Truth atoms are retained. Rev1.17 retains §8.6 experience learning and adds §8.7 Jev/model profitability hardening, typed records, service/context bindings and the single generated plan; it claims no application result. These inventories overlap; never sum them into a fabricated feature count.

The machine-readable contracts specify 12 strict record variants, five linked lifecycle machines, their typed proof predicates and independent semantic invariants. Passing a JSON Schema, a graph mutation test or a hash check does not verify money, source truth, an authentic grant, selector correctness, simulation fidelity, backtest profitability, F15, BG or a live production loop. A receipt containing those claims must be independently resolved against actual source/runtime/venue evidence.

The current pack's checks are document-processing and synthetic contract tests only. They do not run VAN production code, execute a trading backtest, call a broker, change a mandate or publish an application. Source observations remain pinned and scoped. The new required architecture is ready for independent Astra review; it is not self-certified for implementation or financial use.
