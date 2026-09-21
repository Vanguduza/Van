"""Fable research director (TRD-REV51-119).

The director formulates bounded research missions. It cannot trade, change a mandate,
promote a strategy, or mutate a protected live path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from vati.core.canonical import canonical_hash
from vati.research.missions import (
    MissionLedger, ResearchBudget, ResearchMission,
)


@dataclass(frozen=True)
class ResearchTrigger:
    trigger_id: str
    question: str
    evidence_ids: tuple[str, ...] = ()
    data_domains: tuple[str, ...] = ("external_web", "repository")
    specialist_roles: tuple[str, ...] = ("evidence", "contradiction")
    source_policy: str = "DIVERSE_PRIMARY_WHERE_AVAILABLE"
    output_schema: str = "research-packet/5.1.0"

    @property
    def digest(self) -> str:
        return canonical_hash(self.__dict__)


class FableResearchDirector:
    MODEL_POLICY = ("Fable 5.1", "GPT-6 Astra", "Claude Opus 5", "GPT-5.6 Sol")
    PROHIBITED = (
        "ORDER", "SUBMIT_ORDER", "RISK_OVERRIDE", "LIVE_CONFIG_MUTATION",
        "STRATEGY_PROMOTION", "PROTECTED_PATH_EDIT",
    )

    def __init__(self, ledger: MissionLedger, *, default_budget_micros: int = 250_000,
                 default_duration_ms: int = 3_600_000) -> None:
        self.ledger = ledger
        self.default_budget_micros = default_budget_micros
        self.default_duration_ms = default_duration_ms
        self._seq = 0

    def open(self, trigger: ResearchTrigger, *, now_ms: int,
             budget_micros: Optional[int] = None,
             duration_ms: Optional[int] = None) -> ResearchMission:
        self._seq += 1
        duration = duration_ms or self.default_duration_ms
        roles = tuple(dict.fromkeys(trigger.specialist_roles))
        mission = ResearchMission(
            mission_id=f"research-{now_ms}-{self._seq}-{trigger.digest[:10]}",
            hypothesis=trigger.question,
            trigger=trigger.trigger_id,
            parent_evidence_ids=trigger.evidence_ids,
            allowed_data_domains=trigger.data_domains,
            prohibited_live_actions=self.PROHIBITED,
            required_roles=roles,
            budget=ResearchBudget(
                max_agents=len(roles),
                max_invocations=max(len(roles), 1) * 4,
                max_cost_micros=budget_micros or self.default_budget_micros,
                max_wall_ms=duration,
            ),
            deadline_ms=now_ms + duration,
            source_policy=trigger.source_policy,
            output_schema=trigger.output_schema,
            model_policy=self.MODEL_POLICY,
            created_ms=now_ms,
        ).sealed()
        return self.ledger.open(mission)

    def follow_up(self, parent: ResearchMission, *, question: str,
                  roles: Iterable[str], now_ms: int) -> ResearchMission:
        return self.open(
            ResearchTrigger(
                trigger_id=f"follow-up:{parent.mission_id}",
                question=question,
                evidence_ids=(parent.seal,),
                data_domains=parent.allowed_data_domains,
                specialist_roles=tuple(roles),
                source_policy=parent.source_policy,
                output_schema=parent.output_schema,
            ),
            now_ms=now_ms,
        )
