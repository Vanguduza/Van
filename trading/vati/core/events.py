"""Event envelope (Rev 2.1 §E.5). Every event carries three clocks, a producer,
a schema version and a content hash; T0 events also carry decision_time."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from vati.core.canonical import canonical_hash


class EventKind(str, Enum):
    MARKET_TICK = "MARKET_TICK"
    MARKET_BAR = "MARKET_BAR"
    MARKET_STATE = "MARKET_STATE"
    INTEGRITY_STATE_CHANGE = "INTEGRITY_STATE_CHANGE"
    FEATURE_VECTOR = "FEATURE_VECTOR"
    OPPORTUNITY_ASSESSMENT = "OPPORTUNITY_ASSESSMENT"
    TRADE_INTENT = "TRADE_INTENT"
    RISK_DECISION = "RISK_DECISION"
    EXECUTION_POLICY_DECISION = "EXECUTION_POLICY_DECISION"
    CANDIDATE_OPPORTUNITY = "CANDIDATE_OPPORTUNITY"
    CANDIDATE_EXPIRED = "CANDIDATE_EXPIRED"
    ALLOCATION_EPOCH = "ALLOCATION_EPOCH"
    ALLOCATION_DECISION = "ALLOCATION_DECISION"
    ALLOCATION_EPISODE = "ALLOCATION_EPISODE"
    STRATEGY_OVERLAP = "STRATEGY_OVERLAP"
    EXIT_POLICY_RESEARCH = "EXIT_POLICY_RESEARCH"
    PORTFOLIO_DEPENDENCY = "PORTFOLIO_DEPENDENCY"
    STRATEGY_VALIDATION_CERTIFICATE = "STRATEGY_VALIDATION_CERTIFICATE"
    FEATURE_VALIDATION_CERTIFICATE = "FEATURE_VALIDATION_CERTIFICATE"
    CAPITAL_BUDGET_PROPOSAL = "CAPITAL_BUDGET_PROPOSAL"
    FEATURE_DRIFT = "FEATURE_DRIFT"
    EDGE_DRIFT = "EDGE_DRIFT"
    STRATEGY_COVERAGE = "STRATEGY_COVERAGE"
    TRADING_EVIDENCE = "TRADING_EVIDENCE"
    MARKET_DATA_DISAGREEMENT = "MARKET_DATA_DISAGREEMENT"
    ORDER_COMMAND = "ORDER_COMMAND"
    EXECUTION_RECEIPT = "EXECUTION_RECEIPT"
    POSITION_CHANGE = "POSITION_CHANGE"
    RECONCILIATION_RESULT = "RECONCILIATION_RESULT"
    TCA_RECORD = "TCA_RECORD"
    TRADE_REVIEW = "TRADE_REVIEW"
    TRADE_EXPERIENCE_ARTIFACT = "TRADE_EXPERIENCE_ARTIFACT"
    ACTIVATION_MANIFEST = "ACTIVATION_MANIFEST"
    KILL_SWITCH = "KILL_SWITCH"
    MANDATE = "MANDATE"
    CAPSULE_STATE = "CAPSULE_STATE"
    OWNER_TICKET = "OWNER_TICKET"
    SESSION = "SESSION"
    ACCOUNT_SNAPSHOT = "ACCOUNT_SNAPSHOT"   # equity/balance/margin as the venue reported them (portfolio truth for the owner surface)
    MARKET_DATA_HEALTH = "MARKET_DATA_HEALTH"

    # ---- Rev 5.1 (TRD-REV51-090..133). Every kind below is produced by the
    # offline-evolution or shadow-live path. None of them is an order.
    CALENDAR_SCHEDULE = "CALENDAR_SCHEDULE"          # 090 a release that is expected
    CALENDAR_RELEASE = "CALENDAR_RELEASE"            # 090 a release that happened
    COGNITIVE_CONTEXT = "COGNITIVE_CONTEXT"          # 093 the sealed input to one invocation
    COGNITIVE_ASSESSMENT = "COGNITIVE_ASSESSMENT"    # 094 the normalised model result
    BLIND_REVIEW = "BLIND_REVIEW"                    # 095 reviewer verdict + canary outcome
    COGNITIVE_BUDGET = "COGNITIVE_BUDGET"            # 096 spend and degradation rung
    MODEL_HANDOFF = "MODEL_HANDOFF"                  # 132 Fable -> Astra -> Opus -> Sol
    SHADOW_DECISION = "SHADOW_DECISION"              # 100 what cognition would have done
    PNL_ATTRIBUTION = "PNL_ATTRIBUTION"              # 101 realised difference at horizon
    COGNITIVE_PERFORMANCE = "COGNITIVE_PERFORMANCE"  # 103 per-model rolling record
    DECISION_EXAM = "DECISION_EXAM"                  # 102 qualification run result
    TRADE_HEALTH = "TRADE_HEALTH"                    # 099 post-entry health verdict
    ROUTE_REGISTRY = "ROUTE_REGISTRY"                # 104 resolved venue route/quantisation
    PRETRADE_CONTROL = "PRETRADE_CONTROL"            # 105 pre-trade control verdict
    POSITION_FAMILY = "POSITION_FAMILY"              # 106 root + children as one exposure
    POSITION_RISK_ENVELOPE = "POSITION_RISK_ENVELOPE"  # 107 family risk after haircut
    PRESERVATION_ACTION = "PRESERVATION_ACTION"      # 111 containment / preservation
    EXPANSION_ACTION = "EXPANSION_ACTION"            # 110 scale proposal (shadow first)
    EVENT_RELEASE = "EVENT_RELEASE"                  # 112 normalised release
    EVENT_REACTION = "EVENT_REACTION"                # 113 surprise + measured reaction
    MACRO_EVENT_EPISODE = "MACRO_EVENT_EPISODE"      # 114 closed episode record
    EXECUTION_STYLE = "EXECUTION_STYLE"              # 116 selected style, post-approval
    CONFORMAL_INTERVAL = "CONFORMAL_INTERVAL"        # 117 calibrated interval + coverage
    RESEARCH_MISSION = "RESEARCH_MISSION"            # 118 mission opened/closed
    RESEARCH_PACKET = "RESEARCH_PACKET"              # 118 one worker's sealed finding
    RESEARCH_SYNTHESIS = "RESEARCH_SYNTHESIS"        # 121 qualification + join
    RESEARCH_YIELD = "RESEARCH_YIELD"                # 122 portfolio yield of research
    EVOLUTION_CANDIDATE = "EVOLUTION_CANDIDATE"      # 123 archived strategy candidate
    IMPROVEMENT_PROPOSAL = "IMPROVEMENT_PROPOSAL"    # 124 system improvement proposal
    PROPOSAL_ADMISSION = "PROPOSAL_ADMISSION"        # 125 admission verdict + gate health
    GROWTH_DIAGNOSTIC = "GROWTH_DIAGNOSTIC"          # 127 growth-optimality reading
    REJECTION_ANALYTICS = "REJECTION_ANALYTICS"      # 128 aggregated rejection reasons


@dataclass(frozen=True)
class Event:
    kind: EventKind
    producer: str
    event_time_ms: int          # when it happened at the source
    received_time_ms: int       # when VATI received it
    payload: dict[str, Any]
    schema_version: int = 1
    decision_time_ms: Optional[int] = None  # T0 only
    correlation_id: str = ""    # trade_intent_id or session id that ties the chain together
    hash: str = ""

    def body(self) -> dict[str, Any]:
        d = {
            "kind": self.kind.value, "producer": self.producer, "event_time_ms": self.event_time_ms,
            "received_time_ms": self.received_time_ms, "payload": self.payload, "schema_version": self.schema_version,
            "decision_time_ms": self.decision_time_ms, "correlation_id": self.correlation_id,
        }
        return d


def make_event(kind: EventKind, producer: str, payload: dict[str, Any], *, event_time_ms: int, received_time_ms: int,
               decision_time_ms: Optional[int] = None, correlation_id: str = "", schema_version: int = 1) -> Event:
    e = Event(kind, producer, event_time_ms, received_time_ms, payload, schema_version, decision_time_ms, correlation_id)
    return Event(**{**e.__dict__, "hash": canonical_hash(e.body())})
