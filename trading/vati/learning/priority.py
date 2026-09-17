"""Research priority engine (integration doc §29, §41): deterministic scoring
by expected economic value × tractability. Produces a ResearchTask queue that
Hermes / Deep Research / NotebookLM consume; results come back as
ResearchPackets into VTIL admission."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

ZERO = Decimal("0")


@dataclass(frozen=True)
class ResearchTask:
    task_id: str
    trigger: str            # LARGE_LOSS | DECAY | REGIME_CHANGE | MISSED_OPPORTUNITY | EXECUTION_INEFFICIENCY | BROKER_DEGRADATION | NEW_OPPORTUNITY | ANOMALY
    subject: str            # strategy_id / instrument / broker
    question: str
    economic_value: Decimal
    tractability: Decimal   # 0..1
    priority: Decimal
    suggested_tools: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass
class ResearchPriorityEngine:
    tool_value: dict[str, Decimal] = field(default_factory=lambda: {"ANALOGUE_STUDY": Decimal("1.0"), "DEEP_RESEARCH": Decimal("0.7"), "NOTEBOOK_QUERY": Decimal("0.8"), "REPLAY": Decimal("0.9"), "COUNTERFACTUAL_BATCH": Decimal("0.6")})
    history: list = field(default_factory=list)  # (tool, cost, realised_value) for meta-learning

    def score(self, *, task_id: str, trigger: str, subject: str, question: str, loss_or_value: Decimal, recurrence: int, tractability: Decimal, evidence_refs: Iterable[str]) -> ResearchTask:
        ev = abs(loss_or_value) * Decimal(max(1, recurrence))
        tr = min(Decimal(1), max(ZERO, tractability))
        tools = tuple(sorted(self.tool_value, key=lambda t: -self.tool_value[t])[:3])
        return ResearchTask(task_id, trigger, subject, question, ev, tr, (ev * tr).quantize(Decimal("0.01")), tools, tuple(evidence_refs))

    def rank(self, tasks: Iterable[ResearchTask]) -> list[ResearchTask]:
        return sorted(tasks, key=lambda t: (-t.priority, t.task_id))

    def record_outcome(self, tool: str, cost: Decimal, realised_value: Decimal) -> None:
        """Meta-learning: tools that keep paying off rank higher next time; bounded [0.1, 1.5]."""
        self.history.append((tool, cost, realised_value))
        cur = self.tool_value.get(tool, Decimal("0.5"))
        ratio = (realised_value / cost) if cost > ZERO else Decimal(1)
        new = cur * Decimal("0.8") + min(Decimal("1.5"), max(Decimal("0.1"), ratio)) * Decimal("0.2")
        self.tool_value[tool] = new.quantize(Decimal("0.001"))
