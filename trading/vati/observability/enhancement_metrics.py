"""Metric and degraded-state names for the enhancement (§41/§42, TRD-ENH-086/087).

Names are the contract, so they live in one place rather than being spelled out
at each call site. Two rules the existing registry already implies:

* **Bounded cardinality.** No candidate id, URL, hash or free-text reason ever
  becomes a label. A metric with unbounded cardinality is a memory leak with a
  dashboard attached.
* **Degraded states are diagnostic truth.** `FEATURE_DEGRADED` and
  `EXECUTION_INTELLIGENCE_INSUFFICIENT` are different facts with different
  responses, and collapsing them into one red icon loses the response.
"""

from __future__ import annotations

from typing import Mapping

# --- metric names ---------------------------------------------------------

FEATURE_CONTRACT_FAILURES = "vati_feature_contract_failures_total"
MTF_BUILD_SECONDS = "vati_mtf_state_build_seconds"
MTF_MISSING_TIMEFRAME = "vati_mtf_missing_timeframe_total"

CANDIDATES_ACTIVE = "vati_candidates_active"
CANDIDATE_EXPIRATIONS = "vati_candidate_expirations_total"
CANDIDATE_SUPERSESSIONS = "vati_candidate_supersessions_total"

ALLOCATION_EPOCHS = "vati_allocation_epochs_total"
ALLOCATOR_SELECTED = "vati_allocator_selected_total"
ALLOCATOR_DEFERRED = "vati_allocator_deferred_total"
ALLOCATOR_REJECTED = "vati_allocator_rejected_total"
ALLOCATION_REGRET_R = "vati_allocation_regret_R"

PORTFOLIO_INCREMENTAL_ES = "vati_portfolio_incremental_es"
CORRELATION_MULTIPLIER = "vati_correlation_multiplier"

STRATEGY_CERTIFICATE_STATE = "vati_strategy_certificate_state"
FEATURE_CERTIFICATE_STATE = "vati_feature_certificate_state"

EXECUTION_POLICY_SELECTED = "vati_execution_policy_selected_total"
EXECUTION_FILL_PROBABILITY = "vati_execution_fill_probability_estimate"
EXECUTION_SHORTFALL = "vati_execution_shortfall"

CAPITAL_PROPOSALS = "vati_capital_proposals_total"
CAPITAL_PROPOSAL_EXPIRED = "vati_capital_proposal_expired_total"

FEATURE_DRIFT_ALERTS = "vati_feature_drift_alerts_total"
EDGE_DRIFT_ALERTS = "vati_edge_drift_alerts_total"
STRATEGY_COVERAGE_GAPS = "vati_strategy_coverage_gaps"
DATA_DISAGREEMENTS = "vati_data_disagreements_total"

LEASE_OUTCOMES = "vati_account_lease_outcomes_total"

ALL_METRICS = (
    FEATURE_CONTRACT_FAILURES, MTF_BUILD_SECONDS, MTF_MISSING_TIMEFRAME,
    CANDIDATES_ACTIVE, CANDIDATE_EXPIRATIONS, CANDIDATE_SUPERSESSIONS,
    ALLOCATION_EPOCHS, ALLOCATOR_SELECTED, ALLOCATOR_DEFERRED, ALLOCATOR_REJECTED,
    ALLOCATION_REGRET_R, PORTFOLIO_INCREMENTAL_ES, CORRELATION_MULTIPLIER,
    STRATEGY_CERTIFICATE_STATE, FEATURE_CERTIFICATE_STATE,
    EXECUTION_POLICY_SELECTED, EXECUTION_FILL_PROBABILITY, EXECUTION_SHORTFALL,
    CAPITAL_PROPOSALS, CAPITAL_PROPOSAL_EXPIRED,
    FEATURE_DRIFT_ALERTS, EDGE_DRIFT_ALERTS, STRATEGY_COVERAGE_GAPS,
    DATA_DISAGREEMENTS, LEASE_OUTCOMES,
)

#: Labels permitted on any enhancement metric. Everything else is unbounded.
ALLOWED_LABELS = frozenset({
    "account_alias", "symbol", "strategy_id", "venue", "broker", "timeframe",
    "template_id", "state", "outcome", "decision", "feature_id", "regime",
    "session", "policy_version", "environment",
})

#: Never a label. Each of these has unbounded range.
FORBIDDEN_LABELS = frozenset({
    "candidate_id", "trade_intent_id", "decision_hash", "candidate_hash",
    "source_uri", "reason", "detail", "evidence_id", "proposal_id",
    "allocation_epoch_id", "validation_hash", "mtf_state_hash",
})


class MetricCardinalityError(ValueError):
    """A label that would make the series unbounded."""


def check_labels(labels: Mapping[str, str]) -> None:
    """Raise on any label that is not on the allow-list."""
    bad_forbidden = sorted(set(labels) & FORBIDDEN_LABELS)
    if bad_forbidden:
        raise MetricCardinalityError(
            f"unbounded label(s) {bad_forbidden}: use an id in the ledger, not in a metric")
    unknown = sorted(set(labels) - ALLOWED_LABELS)
    if unknown:
        raise MetricCardinalityError(f"unknown label(s) {unknown}; add to ALLOWED_LABELS deliberately")


# --- degraded states ------------------------------------------------------

FEATURE_DEGRADED = "FEATURE_DEGRADED"
MTF_INCOMPLETE = "MTF_INCOMPLETE"
ALLOCATION_DEGRADED = "ALLOCATION_DEGRADED"
DEPENDENCY_MODEL_DEGRADED = "DEPENDENCY_MODEL_DEGRADED"
EXECUTION_INTELLIGENCE_INSUFFICIENT = "EXECUTION_INTELLIGENCE_INSUFFICIENT"
TRADING_EVIDENCE_STALE = "TRADING_EVIDENCE_STALE"
REFERENCE_FEED_DISAGREEMENT = "REFERENCE_FEED_DISAGREEMENT"
CAPITAL_PROPOSAL_EXPIRED_STATE = "CAPITAL_PROPOSAL_EXPIRED"
ACCOUNT_LEASE_UNAVAILABLE = "ACCOUNT_LEASE_UNAVAILABLE"
ACCOUNT_LEASE_HELD_ELSEWHERE = "ACCOUNT_LEASE_HELD_ELSEWHERE"

DEGRADED_STATES = (
    FEATURE_DEGRADED, MTF_INCOMPLETE, ALLOCATION_DEGRADED, DEPENDENCY_MODEL_DEGRADED,
    EXECUTION_INTELLIGENCE_INSUFFICIENT, TRADING_EVIDENCE_STALE,
    REFERENCE_FEED_DISAGREEMENT, CAPITAL_PROPOSAL_EXPIRED_STATE,
    ACCOUNT_LEASE_UNAVAILABLE, ACCOUNT_LEASE_HELD_ELSEWHERE,
)

#: What each state means for new risk. Insufficient execution evidence falls
#: back to a certified default and keeps trading; an unavailable lease does not.
BLOCKS_NEW_RISK: Mapping[str, bool] = {
    FEATURE_DEGRADED: True,
    MTF_INCOMPLETE: True,
    ALLOCATION_DEGRADED: False,
    DEPENDENCY_MODEL_DEGRADED: False,
    EXECUTION_INTELLIGENCE_INSUFFICIENT: False,
    TRADING_EVIDENCE_STALE: False,
    REFERENCE_FEED_DISAGREEMENT: True,
    CAPITAL_PROPOSAL_EXPIRED_STATE: False,
    ACCOUNT_LEASE_UNAVAILABLE: True,
    ACCOUNT_LEASE_HELD_ELSEWHERE: True,
}

#: Owner-facing explanation. "What broke, what still works, what VAN will not do."
OWNER_LANGUAGE: Mapping[str, str] = {
    FEATURE_DEGRADED: "A strategy's declared input is missing or stale; that strategy abstains, others continue.",
    MTF_INCOMPLETE: "A required timeframe has too little closed history; affected strategies abstain.",
    ALLOCATION_DEGRADED: "Candidates are ranked on reduced evidence; sizing and risk checks are unchanged.",
    DEPENDENCY_MODEL_DEGRADED: "Correlation is estimated conservatively rather than measured; positions are smaller, not larger.",
    EXECUTION_INTELLIGENCE_INSUFFICIENT: "Not enough fill data yet; orders use the certified default shape.",
    TRADING_EVIDENCE_STALE: "Research evidence has expired; it no longer reduces confidence.",
    REFERENCE_FEED_DISAGREEMENT: "Price feeds disagree; no new risk until they reconcile.",
    CAPITAL_PROPOSAL_EXPIRED_STATE: "A capital proposal aged out; the current signed budget still applies.",
    ACCOUNT_LEASE_UNAVAILABLE: "The authority store is unreachable; no new orders. This is fail-closed, not a fence.",
    ACCOUNT_LEASE_HELD_ELSEWHERE: "Another process holds this account; no new orders here.",
}


#: Constant *names*, not their values — a metric name string is not a module
#: attribute, and exporting the values would make `from ... import *` fail.
__all__ = [
    "ALLOWED_LABELS", "ALL_METRICS", "BLOCKS_NEW_RISK", "DEGRADED_STATES",
    "FORBIDDEN_LABELS", "OWNER_LANGUAGE", "MetricCardinalityError", "check_labels",
    "FEATURE_CONTRACT_FAILURES", "MTF_BUILD_SECONDS", "MTF_MISSING_TIMEFRAME",
    "CANDIDATES_ACTIVE", "CANDIDATE_EXPIRATIONS", "CANDIDATE_SUPERSESSIONS",
    "ALLOCATION_EPOCHS", "ALLOCATOR_SELECTED", "ALLOCATOR_DEFERRED",
    "ALLOCATOR_REJECTED", "ALLOCATION_REGRET_R", "PORTFOLIO_INCREMENTAL_ES",
    "CORRELATION_MULTIPLIER", "STRATEGY_CERTIFICATE_STATE", "FEATURE_CERTIFICATE_STATE",
    "EXECUTION_POLICY_SELECTED", "EXECUTION_FILL_PROBABILITY", "EXECUTION_SHORTFALL",
    "CAPITAL_PROPOSALS", "CAPITAL_PROPOSAL_EXPIRED", "FEATURE_DRIFT_ALERTS",
    "EDGE_DRIFT_ALERTS", "STRATEGY_COVERAGE_GAPS", "DATA_DISAGREEMENTS", "LEASE_OUTCOMES",
    "FEATURE_DEGRADED", "MTF_INCOMPLETE", "ALLOCATION_DEGRADED",
    "DEPENDENCY_MODEL_DEGRADED", "EXECUTION_INTELLIGENCE_INSUFFICIENT",
    "TRADING_EVIDENCE_STALE", "REFERENCE_FEED_DISAGREEMENT",
    "CAPITAL_PROPOSAL_EXPIRED_STATE", "ACCOUNT_LEASE_UNAVAILABLE",
    "ACCOUNT_LEASE_HELD_ELSEWHERE",
]
