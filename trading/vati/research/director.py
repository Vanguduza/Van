"""Fable research director (TRD-REV51-119).

The director formulates bounded research missions.  It has no authority to execute trades,
change mandates, promote strategies or edit protected paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from vati.core.canonical import canonical_hash
from vati.research.missions import ResearchMission, ResearchMissionStore


@dataclass(frozen=True)
class ResearchTrigger:
    trigger_id: str
    question: str
    evidence_ids: tuple[str, ...] = ()
    data_domains: tuple[str, ...] = ("trading_ledger",)
    specialist_roles: tuple[str, ...] = ("evidence", "contradiction")
    source_policy: str = "DIVERSE_PRIMARY_WHERE_AVAILABLE"
    output_schema: str = "research-packet/5.1.0"

    @property
    def digest(self) -> str:
        return canonical_hash(self.__dict__)


class FableResearchDirector:
    """Turns anomalies/questions into replayable missions; never into live actions."""

    MODEL_POLICY = "Fable 5.1 -> GPT-6 Astra -> Claude Opus 5 -> GPT-5.6 Sol"

    def __init__(self, store: ResearchMissionStore, *, default_budget_micros: int = 250_000,
                 default_duration_ms: int = 3_600_000) -> None:
        self.store = store
        self.default_budget_micros = default_budget_micros
        self.default_duration_ms = default_duration_ms
        self._seq = 0

    def open(self, trigger: ResearchTrigger, *, now_ms: int,
             budget_micros: Optional[int] = None,
             duration_ms: Optional[int] = None) -> ResearchMission:
        self._seq += 1
        mission = ResearchMission(
            mission_id=f"research-{now_ms}-{self._seq}-{trigger.digest[:10]}",
            hypothesis=trigger.question,
            trigger=trigger.trigger_id,
            parent_evidence_ids=trigger.evidence_ids,
            allowed_data_domains=trigger.data_domains,
            required_specialist_roles=trigger.specialist_roles,
            budget_micros=budget_micros or self.default_budget_micros,
            deadline_ms=now_ms + (duration_ms or self.default_duration_ms),
            source_policy=trigger.source_policy,
            output_schema=trigger.output_schema,
            model_provider_policy=self.MODEL_POLICY,
            created_ms=now_ms,
        )
        return self.store.create(mission)

    def follow_up(self, parent: ResearchMission, *, question: str,
                  roles: Iterable[str], now_ms: int) -> ResearchMission:
        trigger = ResearchTrigger(
            trigger_id=f"follow-up:{parent.mission_id}",
            question=question,
            evidence_ids=(parent.mission_hash,),
            data_domains=parent.allowed_data_domains,
            specialist_roles=tuple(roles),
            source_policy=parent.source_policy,
            output_schema=parent.output_schema,
        )
        return self.open(trigger, now_ms=now_ms)
