# Prediction-market research protocols — Rev1.1

The JSON companion is a set of implementation/preregistration templates, **not executed studies**. Null cohort, data, holdout, adequacy and acceptance-threshold fields require an actual frozen study decision before evaluation. They are not defaults chosen after results. No new procurement is scheduled.

## PM-STUDY-01-RISK — RISK_FILTER

**Hypothesis:** Does event uncertainty identify adverse conditions beyond ordinary calendar caution?

**Inputs:** distribution_width, coherent_tail_mass, time_to_release, probability_change_same_event, quality_and_liquidity.

**Comparators:** INCUMBENT, CALENDAR_ONLY_BLACKOUT, UNIFORM_EXPOSURE_MATCHED, INCUMBENT_PLUS_EVENT_FEATURES.

**Metrics:** net_account_utility, drawdown_and_tail_noninferiority, gains_missed, losses_avoided, realized_exposure, abstention_by_event.

**Consumer boundary:** D1/D2/D3/D6 restrictive proposals only; D4/D5 only for permitted managed positions.

## PM-STUDY-02-SURPRISE — SURPRISE

**Hypothesis:** Does the frozen market distribution improve post-release interpretation beyond conventional consensus?

**Inputs:** frozen_pre_release_probabilities, first_official_actual, point_in_time_consensus, historical_conditional_response.

**Comparators:** CONSENSUS_ONLY, EXISTING_EVENT_HISTORY, CONSENSUS_PLUS_MARKET_DISTRIBUTION.

**Metrics:** proper_probability_score, conditional_asset_forecast_loss, delay_sensitivity, net_account_utility, event_cluster_uncertainty.

**Consumer boundary:** Existing history/research consumer first; new event trades only through separately admitted D7.

## PM-STUDY-03-VOLATILITY — VOLATILITY

**Hypothesis:** Do event-price changes and uncertainty add useful multi-horizon volatility information?

**Inputs:** historical_returns, historical_volatility, event_probability_history, event_uncertainty, market_state.

**Comparators:** TRAILING_VOLATILITY, HAR_GARCH_WHERE_APPROPRIATE, STRONGEST_INCUMBENT_MODEL, SAME_MODEL_PLUS_EVENT_FEATURES.

**Metrics:** original_domain_loss, QLIKE_WHERE_DOMAIN_VALID, coverage_and_violation_clustering, sizing_policy_utility, incremental_compute_cost.

**Consumer boundary:** Volatility research and bounded risk evidence, not directional certainty or size authority.

## PM-STUDY-04-RANKING — RANKING

**Hypothesis:** Does event information improve selection among otherwise eligible opportunities under fixed risk and capital?

**Inputs:** existing_setup_features, event_asset_response, calibrated_event_features, same_cutoff_universe.

**Comparators:** INCUMBENT_RANKING, STRONGEST_TABULAR_BASELINE, SAME_MODEL_PLUS_EVENT_FEATURES, EXPOSURE_MATCHED_CONTROL.

**Metrics:** rank_quality, turnover, full_account_net_utility, capacity, profit_concentration, worst_regime_performance.

**Consumer boundary:** Existing arbiter only; no new universe/account or enlarged mandate; preserve D6 versus D7 distinction.

## Shared experimental controls

Keep all quotes/thresholds/venues of an underlying event in the same chronological partition. Respect label maturity, official first-vintage availability and pre-release snapshot freezing. Calibrate on earlier data and compare with raw probabilities. All feature/model/horizon/calibrator choices count as trials. Keep a final untouched period and a separately sealed prospective shadow period.

Match information delay, feasible execution, cohort, exposure, capital and mandate. Replay the whole account. Measure missed winners as well as avoided losers and make claims conditional on source availability, quote quality and independent events. Out-of-sample improvement must survive its stated uncertainty and operating cost; no numerical adoption threshold is invented by this document.

## Research-lab acceptance is different from strategy success

Binary valuation must reconcile expected payout, executable acquisition, fees and maximum loss; early exits need their own exit-price model. Execution must include queue uncertainty, gap recovery, partial fills, cancellations, settlement and available cash. The arbitrage lab must enumerate reviewed payoff states and non-atomic hedge failures. The maker lab must measure fill-conditional value, inventory and cancel-pending exposure without assuming preferential venue privileges.

A correctly implemented lab can reject every economic candidate. That does not excuse a missing simulator, unbound producer or API with only refusal paths. Conversely, synthetic positive examples exercise the software but cannot establish profitability or real-provider qualification.
