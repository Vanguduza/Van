"""Bounded specialist research agent factory (TRD-REV51-120)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from vati.cognition.handoff import ContinuityState, HandoffReason, HandoffRecorder
from vati.cognition.providers import QuotaScheduler
from vati.core.canonical import canonical_hash
from vati.research.missions import ResearchClaim, ResearchMission, ResearchPacket

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
        if self.role not in mission.required_roles:
            raise ValueError(f"{self.role} is not required by mission {mission.mission_id}")
        if self.max_tokens <= 0 or self.max_runtime_ms <= 0:
            raise ValueError("agent budget must be positive")
        if set(self.allowed_data_domains) - set(mission.allowed_data_domains):
            raise ValueError(f"agent {self.role} exceeds mission data domains")


class ResearchAgentFactory:
    def __init__(self, scheduler: QuotaScheduler, *,
                 specs: Optional[Mapping[str, ResearchAgentSpec]] = None,
                 handoffs: Optional[HandoffRecorder] = None) -> None:
        self.scheduler = scheduler
        self.specs = dict(specs or {role: ResearchAgentSpec(role) for role in DEFAULT_ROLES})
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
            context_hash=mission.seal,
            open_mission_ids=(mission.mission_id,),
        )
        last_reason = "all_providers_unavailable"
        last_model = ""

        while True:
            lease = self.scheduler.acquire(now_ms=now_ms, exclude_model_ids=tuple(excluded))
            if lease is None:
                return ResearchPacket.failed(
                    mission_id=mission.mission_id, agent_role=role, model_id=last_model,
                    reason=last_reason, created_ms=now_ms)
            if previous is not None:
                self.handoffs.record(
                    previous=previous, nxt=lease, reason=HandoffReason.TRANSPORT_ERROR,
                    continuity=continuity, now_ms=now_ms)
            last_model = lease.model_id
            try:
                raw = invoke(lease, mission, spec)
                statements = tuple(str(x) for x in raw.get("claims", ()))
                sources = tuple(str(x) for x in raw.get("source_ids", ()))
                refs = tuple(str(x) for x in raw.get("evidence_refs", ()))
                methods = tuple(str(x) for x in raw.get("methods", ()))
                if not statements or not sources or not refs or not methods:
                    raise ValueError("research_result_missing_required_evidence")
                claims = tuple(
                    ResearchClaim(
                        claim_id=canonical_hash({
                            "mission": mission.mission_id, "role": role, "statement": statement,
                        })[:20],
                        statement=statement,
                        evidence_ids=refs,
                        confidence=str(raw.get("confidence", "UNSPECIFIED")),
                    )
                    for statement in statements
                )
                packet_id = canonical_hash({
                    "mission": mission.mission_id, "role": role,
                    "model": lease.model_id, "claims": [c.body() for c in claims],
                    "sources": sources, "refs": refs,
                })[:24]
                retrieved = tuple(int(x) for x in raw.get(
                    "retrieval_timestamps_ms", (now_ms,) * len(sources)))
                if len(retrieved) != len(sources):
                    raise ValueError("one retrieval timestamp is required per source")
                packet = ResearchPacket(
                    packet_id=packet_id,
                    mission_id=mission.mission_id,
                    agent_role=role,
                    provider=lease.model_id,
                    model_id=lease.model_id,
                    source_ids=sources,
                    retrieved_ms=retrieved,
                    claims=claims,
                    evidence_refs=refs,
                    counterevidence=tuple(str(x) for x in raw.get("counterevidence", ())),
                    limitations=tuple(str(x) for x in raw.get("limitations", ())),
                    methods=methods,
                    artifact_refs=tuple(str(x) for x in raw.get("code_data_artifacts", ())),
                    reproducibility=dict(raw.get("reproducibility", {})),
                    created_ms=now_ms,
                ).sealed()
                self.scheduler.release(lease, ok=True, now_ms=now_ms)
                return packet
            except Exception as exc:
                self.scheduler.release(lease, ok=False, now_ms=now_ms)
                excluded.append(lease.model_id)
                previous = lease
                last_reason = f"{type(exc).__name__}:{str(exc)[:160]}"
