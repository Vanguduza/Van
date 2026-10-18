# Evaluator qualification and registered comparison protocol

State: NOT_RUN. This is the required procedure for BE-035/036 and BQ-009, not a completed experiment. Approval of this specification does not authorize a funded live study.

## Qualification before optimization

Use an independent event oracle with exact instrument and fee units. Cover market/limit/stop/stop-limit and pending fills, eligible timestamps, no fill before submit, gaps, bid versus ask, sell direction, latency, cancel/fill/replace races, queue/volume constraints, partial fees, immediate and pending protection, account cash/MTM, terminal liquidation and external flows. Include counterexamples that the current paper adapter cannot legitimately pass. An ambiguous bar supports a bounded set of feasible paths; a chosen low-before-high path is not known market history. Do not use application output as its own oracle.

Freeze event-source interpretation (bid/mid/trade), conversion series, contract multiplier, quote/account/fee assets, tick/lot rounding, calendars/timezones, halted/delisted periods and final valuation/liquidation policy. Reconcile fill-based benchmark to cash ledger. Financing/funding costs apply only when the product permits them; unlevered CEX spot does not acquire derivative funding merely to populate a table. Data/compute costs enter the registered economic view once, with a declared allocation.

## Immutable study registration

Before examining the evaluation window, seal dataset content hashes, rights/access basis, raw source revisions, availability timestamps, split/fold IDs, warmup, feature/target definitions, actual fit/selection/calibration intervals, holdout custodian, seed/config/code/dependencies, evaluator certificate, objective/account stream, comparator and all trial budgets. Preserve every attempted/pruned/failed/loss-making model or human/LLM revision. Calendar-year reports are descriptive unless actual chronological fitting and validation records establish walk-forward evaluation.

Primary comparison: net objective execution cost of qualified fixed policy versus approved operational adaptation on the identical ex-ante objective stream. Report fills, misses, cancellations, uncertainty and operational burden alongside mean cost. If timing/exposure/capital differs, use separate whole-account simulations at equal initial capital, information and permissions; opportunity sets must be generated endogenously in each arm. Do not cherry-pick the common filled trades. Report account risk/exposure and action overlap; off-policy results require logged behavior probabilities and defensible support or remain unidentifiable.

Preregister an economically meaningful minimum net saving, cost/liquidity stress grid, sample/cluster unit, maximum study duration/trials and stop conditions before access to held-out outcomes. Values are not invented by this review; set them from approved deployment economics and calibration data, then seal before running. Use parent/objective and temporal dependence-aware resampling or another justified uncertainty method, nested selection where needed, and fixed review windows or valid sequential control. No optional stopping on ordinary p-values; DSR is not a universal probability of skill. Inconclusive stays inconclusive.

Run prefix invariance and poisoned-future tests against both feature construction and selection/artifact caches. Deliberate future leaks must fail named checks. Short/full window parity must cover recursive warmup tolerance across assets/regimes; one small run cannot certify all settings. Compare raw strategy-isolation and governed-account arms explicitly; never label disabling lockouts a deployment-faithful comparison.

## Mandatory output tables for actually executed runs

- Dataset manifest: exact content identity, source/rights, time span, missing/outage intervals, bid/ask convention, acquisition and availability.
- Trial census: attempt ID, parent proposal, artifact/evaluator hashes, train/validation/calibration/test windows, status, failure/prune reason and complete costs.
- Per opportunity: ID/account/objective, cutoff, features, eligible set/rejections, chosen binding/method/snapshot, size/deadline/limit and counterfactual grade.
- Per order/fill: original command/outbox/idempotency ID, venue/account/product, lifecycle times, gross quantity, actual price, fees/assets, cancellation/replacement and protection facts, revisions and unknown state.
- Per account/time: cash/assets/reservations/positions, conversions, external flows, MTM, drawdown, terminal exposure/liquidation, data/compute/operating costs.
- Comparison: complete matched objectives and whole-account arms where required, net distribution, uncertainty, failures, stress, negative results and materiality/stopping decision.
- Raw receipt: actual admitted host/job, exact command, timestamps, exit, stdout/stderr and artifact hashes. Independent verifier and promotion owner remain separate.

A successful controlled causal loop proves its mechanism. It does not demonstrate live profitability, authorize exploration, or permit silently replacing a policy.

## Rev1.16 experience-learning qualification

Focused blueprint §8.6 and VAN-EL-001…007 are mandatory extensions. Register the setup/similarity/regime rule using information available at decision time; keep accounting, association, simulation and supported causation separate. Hypothesis-discovery observations cannot also be protected confirmation. Preserve all human/LLM trials, treat overlap/dependence, qualify null controls and power on controlled alternatives, and preregister sequential or fixed-window inference. Null-control tolerances apply to ensembles, not a demand that every random realization be rejected. No p-value or single profitable outcome is proof of skill.

Run both EL-AT-003 execution and EL-AT-004 strategy positive loops through actual registered producers and consumers. EL-AT-012 removes each real consumer independently. The evaluator must detect economically known improvements in controlled fixtures as well as reject induced leakage, false attribution, omitted costs and invalid authority. Indefinite refusal or a narrative report alone cannot pass. Controlled mechanism tests and prospective economic qualification remain separate.

Required run artifacts additionally include immutable experience and diagnosis revisions, registered hypotheses, trial/split manifests, dependence and selection adjustment, null/power controls, exact policy diffs, consumer receipts, before/after snapshots and stale/corrected evidence propagation. Source/cost corrections invalidate affected claims; earlier AS_DECIDED evidence remains unchanged.
