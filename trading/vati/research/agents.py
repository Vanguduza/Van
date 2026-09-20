"""Bounded specialist research agent factory (TRD-REV51-120)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from vati.cognition.handoff import ContinuityState, HandoffReason, HandoffRecorder
from vati.cognition.providers import QuotaScheduler
from vati.research.missions import PacketState, ResearchMission, ResearchPacket

InvokeResearch = Callable[[Any, ResearchMission, "ResearchAgentSpec"], Mapping[str, Any]]

DEFAULT_ROLES = (
    "technical", "repository", "architecture", "security", "ux", "frontend",
    "failure", "operability", "testing", "performance", "deployment",
    "integration", "sources", "contradiction", "anti-pattern", "official",
    "donor", "evidence",
)


@dataclass(frozen=True)
class ResearchAgentSpec:
    role: str
    allowed_tools: tuple[str, ...] = ("public_research", "repository_read")
    allowed_data_domains: tuple[str, ...] = ("external_web", "repository")
    max_tokens: int = 16_000
    max_runtime_ms: int = 120_000
    source_policy: str = "DIVERSE_PRIMARY_WHERE_AVAILABLE"

    def validate_for(self, mission: ResearchMission) -> None:
        if self.role not in mission.required_specialist_roles:
            raise ValueError(f"{self.role} is not required by mission {mission.mission_id}")
        if self.max_tokens <= 0 or self.max_runtime_ms <= 0:
            raise ValueError("agent budget must be positive")
        if mission.allowed_data_domains:
            extra = set(self.allowed_data_domains) - set(mission.allowed_data_domains)
            if extra:
                raise ValueError(f"agent {self.role} exceeds mission data domains: {sorted(extra)}")


class ResearchAgentFactory:
    def __init__(self, scheduler: QuotaScheduler, *,
                 specs: Optional[Mapping[str, ResearchAgentSpec]] = None,
                 handoffs: Optional[HandoffRecorder] = None) -> None:
        self.scheduler = scheduler
        self.specs = dict(specs or {
            role: ResearchAgentSpec(role=role) for role in DEFAULT_ROLES
        })
        self.handoffs = handoffs or HandoffRecorder()

    def run(self, mission: ResearchMission, role: str, *, invoke: InvokeResearch,
            now_ms: int) -> ResearchPacket:
        if not mission.seal_ok():
            raise ValueError("research mission seal is invalid")
        if now_ms >= mission.deadline_ms:
            return ResearchPacket.failed(
                mission_id=mission.mission_id, agent_role=role, model_id="",
                reason="mission_deadline_expired", created_ms=now_ms)
        spec = self.specs.get(role)
        if spec is None:
            return ResearchPacket.failed(
                mission_id=mission.mission_id, agent_role=role, model_id="",
                reason="agent_role_not_registered", created_ms=now_ms)
        spec.validate_for(mission)

        excluded: list[str] = []
        previous = None
        continuity = ContinuityState(
            context_hash=mission.mission_hash,
            open_mission_ids=(mission.mission_id,),
        )
        last_reason = "all_providers_unavailable"
        last_model = ""

        while True:
            lease = self.scheduler.acquire(
                now_ms=now_ms, exclude_model_ids=tuple(excluded))
            if lease is None:
                return ResearchPacket.failed(
                    mission_id=mission.mission_id, agent_role=role,
                    model_id=last_model, reason=last_reason, created_ms=now_ms)
            if previous is not None:
                self.handoffs.record(
                    previous=previous, nxt=lease,
                    reason=HandoffReason.TRANSPORT_ERROR,
                    continuity=continuity, now_ms=now_ms)
            last_model = lease.model_id
            try:
                raw = invoke(lease, mission, spec)
                claims = tuple(str(x) for x in raw.get("claims", ()))
                source_ids = tuple(str(x) for x in raw.get("source_ids", ()))
                evidence_refs = tuple(str(x) for x in raw.get("evidence_refs", ()))
                if not claims or not source_ids or not evidence_refs:
                    raise ValueError("research_result_missing_required_evidence")
                packet = ResearchPacket(
                    mission_id=mission.mission_id,
                    agent_role=role,
                    model_id=lease.model_id,
                    source_ids=source_ids,
                    retrieval_timestamps_ms=tuple(
                        int(x) for x in raw.get("retrieval_timestamps_ms", (now_ms,) * len(source_ids))),
                    claims=claims,
                    evidence_refs=evidence_refs,
                    counterevidence=tuple(str(x) for x in raw.get("counterevidence", ())),
                    limitations=tuple(str(x) for x in raw.get("limitations", ())),
                    methods=tuple(str(x) for x in raw.get("methods", ())),
                    code_data_artifacts=tuple(str(x) for x in raw.get("code_data_artifacts", ())),
                    reproducibility=tuple(str(x) for x in raw.get("reproducibility", ())),
                    created_ms=now_ms,
                ).sealed()
                self.scheduler.release(lease, ok=True, now_ms=now_ms)
                return packet
            except Exception as exc:  # research failure is data, never execution authority
                self.scheduler.release(lease, ok=False, now_ms=now_ms)
                excluded.append(lease.model_id)
                previous = lease
                last_reason = f"{type(exc).__name__}:{str(exc)[:160]}"
