# Owner requirement: learning from trading experience

Recorded: 2026-10-18. Requirement ID: `VAN-OWNER-EL-001`.

**State: OWNER_REQUESTED; REQUIRED_FOR_IMPLEMENTATION; APPLICATION_ACCEPTANCE_NOT_RUN.**

This companion requirement applies alongside the Rev1.15 specification, corrective delivery 1.15.1 at commit `270d077b978d785b186b46b208a97ba188fad1a2`. It makes the owner’s latest intended outcome explicit. It is outside that sealed archive: its 309 requirements / 1,544 test contracts remain the archive’s counts. The additional scenarios below are not represented as already integrated registry entries or executed tests. PRE-002 must incorporate this requirement and its scenarios into the next consolidated machine registry, generated plan and sealed delivery; PRE-003 and BG-001 must resolve that incorporation before accepting the affected work. This is an addition to the existing plan, not another development schedule or a financial activation grant.

## Required product outcome

Van must learn from its actual trading experience and use defensible evidence to improve strategy decisions and execution. It must investigate profitable, losing, flat, rejected, missed and deliberately skipped opportunities; determine what is known about their outcomes; propose testable improvements; and apply independently qualified improvements through the existing operational and policy-evolution paths.

The objective is improved future net, risk-adjusted expectancy and operational reliability within the owner’s risk mandate. Similar setups cannot be guaranteed profitable. A single outcome cannot establish an edge or uniquely reveal its cause. Van must be able to conclude **expected loss under a still-supported strategy**, **lucky outcome without demonstrated edge**, **execution defect**, **regime-dependent evidence**, or **insufficient evidence**, with the strength and limitations of each conclusion visible.

The relevant loop is:

`point-in-time opportunity → decision and execution → reconciled outcome → evidence-based diagnosis → registered hypothesis → independent evaluation → qualified change → later decision → monitoring and restatement`

## 1. Preserve what was knowable before the outcome

The existing event and outcome owners must retain a versioned experience record for every eligible opportunity, including those not traded. It must bind:

- Account, venue, instrument, opportunity/parent/child IDs, market-data source and revision, event time and availability time, and live/demo/paper/simulation provenance.
- Setup definition and version, features available at decision time, regime classification and its version, relevant missingness, liquidity, volatility, spread, session and available capital. A regime learned from later outcomes cannot be retroactively treated as known at entry.
- Strategy/model/policy/feature versions, evidence snapshot, calibrated predictive distribution where qualified, expected payoff and costs, uncertainty, admissible alternatives, selection/abstention reason, risk constraints and owner overrides. An uncalibrated score remains an uncalibrated score.
- Intended entry/exit/protection and quantity, actual order lifecycle, fills/non-fills, fees and financing where applicable, cash/exposure reconciliation, benchmark and evaluation horizons fixed before outcomes are examined.
- Original decision evidence and separately revised analytical evidence. Later source corrections may restate an analysis, but cannot rewrite what Van knew or decided at the time.

Setup similarity is a versioned, validated rule over available features, not a retrospective resemblance selected because two trades won. Feature selection, cohort discovery and similarity learning consume the research trial budget and may not inspect their held-out evaluation outcomes. Sparse or unsupported cohorts use an approved broader population or static fallback, with the transfer assumption disclosed.

## 2. Diagnose outcomes without inventing causes

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

## 3. Distinguish repeatable evidence from chance

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

## 4. Improve both strategy and execution through their actual consumers

Strategy changes may concern entry filtering, abstention, supported regime selection, exits or risk inputs within the existing authority model. Execution changes may concern a qualified order method, scheduling, participation or other approved parameters. Keep their objectives and evidence separate so that an execution improvement is not misreported as a strategy edge.

For each proposed change, record the experience/cohort that motivated it, falsifiable hypothesis, exact artifact/configuration diff, expected mechanism, comparator, evidence, costs, uncertainty, affected scopes, rejection conditions and rollback/fallback.

- **Operational learning:** the approved update rule may update learned state and select among already qualified alternatives within current bounds, without a new owner prompt for each choice. Record the snapshot and the reason a later eligible choice changes or stays the same.
- **Policy/strategy evolution:** new logic, feature definitions, update rules or parameter domains follow the existing registered research, independent qualification and promotion process. Standing grants apply only within their actual scope; a profitable anecdote does not enlarge them.
- **Monitoring:** retain comparable before/after cohorts, selection effects, drawdown and drift monitoring. Suspended or expired evidence triggers the qualified fallback or abstention path as appropriate. Preserve urgent protection and reconciliation even if analytical services are unavailable.
- **Correction and replay:** duplicated or corrected events, crashes and restarts must reproduce the appropriate learned state and later selection without duplicating financial effects. A corrected observation can invalidate dependent conclusions and candidates; retain the lineage and original decisions.

A complete implementation must demonstrate a real producer-to-consumer strategy improvement loop and an execution improvement loop in controlled admitted environments. Refusing every candidate or producing review text without changing any qualified downstream decision is not completion. Controlled fixtures prove the mechanism; real economic efficacy still needs its own evidence.

## 5. Owner-visible information and controls

Extend existing contexts; no new global tab or separate learning service is required.

| Existing context IDs | Required information / controls |
|---|---|
| `VNX-S-ORDERS-11`, `VNX-S-ORDERS-12` | “What happened?”, decision-time evidence, financial decomposition, execution contribution, competing explanations, data gaps and links to the exact supporting records. |
| `van.next.trading.pattern-candidates`, `VAN-S-CX-STRATEGY-DEVELOPMENT` | Proposed lesson, similarity/cohort definition, supporting and contradicting observations, research state and the difference between an anecdote and supported evidence. |
| `VAN-S-CX-CANDIDATE-COMPARISON`, `VAN-S-CX-EXPERIMENT-LEDGER` | Baseline versus candidate, net utility and uncertainty, complete trial history, prospective evidence, exact policy diff and why a candidate passed, failed or remained inconclusive. |
| `van.trading.strategies`, `VAN-S-CX-RISK-POLICY-ACTIVATION` | Active strategy/update-rule version, learning freshness, current fallback, what changed and why, and existing scoped pause/review/promote/revoke controls with authoritative readback. |

BE-032 must expose these as typed backend read/action contracts before frontend design acceptance. The read model needs stable trade/cohort/hypothesis/study/candidate/binding IDs, revision/cutoff, evidence grade, result/uncertainty, consumer impact and provenance. Commands need the existing actor/account scope, expected version, idempotency, authority checks and outcome reconciliation. Pagination and revision-aware updates must handle large histories and late corrections.

This document specifies required capabilities, not deployed URL paths. The concrete route/schema/caller mapping and backend positive/error/recovery tests must be entered into the existing service and screen registries before BG-001; an invented endpoint name is not acceptance evidence. The app must distinguish learning, pending maturity, insufficient evidence, stale evidence, service failure, suspended policy and no eligible method. It must not present those states as zero cost or successful improvement.

## 6. Traceability to the existing implementation plan

| Existing unit | Additional explicit completion obligation |
|---|---|
| `PRE-002`, `PRE-003` | Incorporate and independently review this owner requirement and acceptance scenarios in the next consolidated registries without losing inherited scope. |
| `BE-003`, `BE-012`, `VAN-ML-PKT-027` | Preserve point-in-time experience, reconciled outcome/attribution lineage, skipped opportunities and corrections. |
| `BE-013`, `BE-021`, `BE-022` | Versioned setup/cohort definitions, evidence-grounded diagnosis, calibrated interpretation and falsifiable hypotheses. |
| `BE-035`, `BQ-009` | Qualify evaluation, null controls, effective sample size, multiple-trial handling, prospective confirmation and uncertainty. |
| `BE-036`, `BE-028` | Complete bounded strategy and execution learning loops, research scheduling, promotion, monitoring and rollback. |
| `BE-032`, `UX-001`, `FE-011`, `FE-012`, `FE-014`, `FE-023` | Backend operation/read-model mappings and existing-context presentation of diagnoses, evidence and changes. |
| `BQ-005`, `BQ-007`, `BG-001` | Independent integration, fault/replay, anti-bypass and completeness evidence before frontend entry. |

Existing coverage being refined includes `VAN-NX-061`, `VAN-ML-REQ-048`, `VAN-CX-010`, `VAN-CX-013`, `VAN-HVA-025`, `VAN-HVA-028`, `VAN-SO-028`, `VAN-SO-030`, `VAN-SO-032`, `VAN-SO-038`, `VAN-RV-003` and `VAN-RV-006`. The identified gap is a unified, explicit experience-to-diagnosis-to-qualified-strategy/execution contract, not the absence of all learning or statistical safeguards in Rev1.15.

## 7. Required additional acceptance scenarios

All scenarios are **NOT_RUN**. They are prospective application acceptance obligations, not documentary tests passed by creating this file. During incorporation, retain these stable IDs and map each to positive/adverse/recovery fixtures, exact commands, independent oracles and owning units in the canonical registry.

| Scenario ID | Required observable result | Primary unit |
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

The implementation passes only when the actual integrated mechanisms and adverse/recovery cases work. Financial profitability, production qualification and physical S24 acceptance remain separate evidence obligations.
