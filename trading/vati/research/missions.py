"""ResearchMission / ResearchPacket contracts (TRD-REV51-118, G12).

Research is an offline evidence-producing plane. These contracts deliberately
contain no trading execution types and no mutable live configuration. Every
mission and worker packet is content-addressed so a synthesis can be replayed
against the exact question, authority budget and evidence set that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

MISSION_VERSION = "research-mission/5.1.0"
PACKET_VERSION = "research-packet/5.1.0"
PRODUCER = "vati-research-missions"


class MissionState(str, Enum):
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PacketState(str, Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ResearchContractError(ValueError):
    """A research artefact is incomplete, ambiguous or over-authorised."""


@dataclass(frozen=True)
class ResearchBudget:
    max_agents: int
    max_invocations: int
    max_cost_micros: int
    max_wall_ms: int

    def __post_init__(self) -> None:
        if min(self.max_agents, self.max_invocations, self.max_wall_ms) <= 0:
            raise ResearchContractError("agent, invocation and wall budgets must be positive")
        if self.max_cost_micros < 0:
            raise ResearchContractError("cost budget cannot be negative")

    def body(self) -> dict[str, int]:
        return {
            "max_agents": self.max_agents,
            "max_invocations": self.max_invocations,
            "max_cost_micros": self.max_cost_micros,
            "max_wall_ms": self.max_wall_ms,
        }


@dataclass(frozen=True)
class ResearchMission:
    mission_id: str
    hypothesis: str
    trigger: str
    parent_evidence_ids: tuple[str, ...]
    allowed_data_domains: tuple[str, ...]
    prohibited_live_actions: tuple[str, ...]
    required_roles: tuple[str, ...]
    budget: ResearchBudget
    deadline_ms: int
    source_policy: str
    output_schema: str
    model_policy: tuple[str, ...]
    created_ms: int
    state: MissionState = MissionState.OPEN
    mission_version: str = MISSION_VERSION
    seal: str = ""

    def __post_init__(self) -> None:
        if not self.mission_id or not self.hypothesis.strip():
            raise ResearchContractError("mission id and hypothesis are required")
        if not self.required_roles:
            raise ResearchContractError("a mission without specialist roles is not bounded research")
        if not self.allowed_data_domains:
            raise ResearchContractError("allowed data domains must be declared")
        if not self.source_policy or not self.output_schema:
            raise ResearchContractError("source policy and output schema are required")
        if self.deadline_ms <= self.created_ms:
            raise ResearchContractError("research deadline must be after mission creation")
        forbidden = {"ORDER", "SUBMIT_ORDER", "RISK_OVERRIDE", "LIVE_CONFIG_MUTATION"}
        if not forbidden.issubset({x.upper() for x in self.prohibited_live_actions}):
            raise ResearchContractError(
                "mission must explicitly prohibit order, risk override and live-config mutation")

    def body(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "hypothesis": self.hypothesis,
            "trigger": self.trigger,
            "parent_evidence_ids": list(self.parent_evidence_ids),
            "allowed_data_domains": list(self.allowed_data_domains),
            "prohibited_live_actions": list(self.prohibited_live_actions),
            "required_roles": list(self.required_roles),
            "budget": self.budget.body(),
            "deadline_ms": self.deadline_ms,
            "source_policy": self.source_policy,
            "output_schema": self.output_schema,
            "model_policy": list(self.model_policy),
            "created_ms": self.created_ms,
            "state": self.state.value,
            "mission_version": self.mission_version,
        }

    def sealed(self) -> "ResearchMission":
        return ResearchMission(**{**self.__dict__, "seal": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())

    def transition(self, state: MissionState) -> "ResearchMission":
        allowed = {
            MissionState.OPEN: {MissionState.RUNNING, MissionState.CANCELLED, MissionState.FAILED},
            MissionState.RUNNING: {MissionState.COMPLETE, MissionState.FAILED, MissionState.CANCELLED},
            MissionState.COMPLETE: set(),
            MissionState.FAILED: set(),
            MissionState.CANCELLED: set(),
        }
        if state not in allowed[self.state]:
            raise ResearchContractError(
                f"mission transition {self.state.value}->{state.value} is not allowed")
        return ResearchMission(**{**self.__dict__, "state": state, "seal": ""}).sealed()


@dataclass(frozen=True)
class ResearchClaim:
    claim_id: str
    statement: str
    evidence_ids: tuple[str, ...]
    confidence: str = "UNSPECIFIED"

    def body(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ResearchPacket:
    packet_id: str
    mission_id: str
    agent_role: str
    provider: str
    model_id: str
    source_ids: tuple[str, ...]
    retrieved_ms: tuple[int, ...]
    claims: tuple[ResearchClaim, ...]
    evidence_refs: tuple[str, ...]
    counterevidence: tuple[str, ...]
    limitations: tuple[str, ...]
    methods: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    reproducibility: Mapping[str, Any]
    created_ms: int
    state: PacketState = PacketState.COMPLETE
    failure_reason: str = ""
    packet_version: str = PACKET_VERSION
    seal: str = ""

    def __post_init__(self) -> None:
        if not self.packet_id or not self.mission_id or not self.agent_role:
            raise ResearchContractError("packet id, mission id and agent role are required")
        if self.state is PacketState.COMPLETE and not self.methods:
            raise ResearchContractError("complete research packets must name their method")
        if self.state is PacketState.FAILED and not self.failure_reason:
            raise ResearchContractError("failed research packets must name the failure")
        if self.retrieved_ms and len(self.retrieved_ms) != len(self.source_ids):
            raise ResearchContractError("each source id must have one retrieval timestamp")

    def body(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "mission_id": self.mission_id,
            "agent_role": self.agent_role,
            "provider": self.provider,
            "model_id": self.model_id,
            "source_ids": list(self.source_ids),
            "retrieved_ms": list(self.retrieved_ms),
            "claims": [c.body() for c in self.claims],
            "evidence_refs": list(self.evidence_refs),
            "counterevidence": list(self.counterevidence),
            "limitations": list(self.limitations),
            "methods": list(self.methods),
            "artifact_refs": list(self.artifact_refs),
            "reproducibility": dict(sorted(self.reproducibility.items())),
            "created_ms": self.created_ms,
            "state": self.state.value,
            "failure_reason": self.failure_reason,
            "packet_version": self.packet_version,
        }

    def sealed(self) -> "ResearchPacket":
        return ResearchPacket(**{**self.__dict__, "seal": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())

    @classmethod
    def failed(cls, *, mission_id: str, agent_role: str, model_id: str,
               reason: str, created_ms: int) -> "ResearchPacket":
        packet_id = canonical_hash({
            "mission_id": mission_id,
            "agent_role": agent_role,
            "model_id": model_id,
            "reason": reason,
            "created_ms": created_ms,
        })[:24]
        return cls(
            packet_id=packet_id,
            mission_id=mission_id,
            agent_role=agent_role,
            provider=model_id,
            model_id=model_id,
            source_ids=(),
            retrieved_ms=(),
            claims=(),
            evidence_refs=(),
            counterevidence=(),
            limitations=(),
            methods=("failure_record",),
            artifact_refs=(),
            reproducibility={"failure_recorded": True},
            created_ms=created_ms,
            state=PacketState.FAILED,
            failure_reason=reason,
        ).sealed()


class MissionLedger:
    """Durable in-process index mirrored into the VATI ledger for replay."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger, self._producer = ledger, producer
        self._missions: dict[str, ResearchMission] = {}
        self._packets: dict[str, ResearchPacket] = {}

    def open(self, mission: ResearchMission) -> ResearchMission:
        if mission.mission_id in self._missions:
            prior = self._missions[mission.mission_id]
            if prior.seal == mission.seal:
                return prior
            raise ResearchContractError(
                f"mission {mission.mission_id} already exists with different terms")
        if not mission.seal_ok():
            raise ResearchContractError("mission seal does not verify")
        self._missions[mission.mission_id] = mission
        self._emit(
            EventKind.RESEARCH_MISSION,
            mission.body() | {"seal": mission.seal},
            mission.created_ms,
            mission.mission_id,
        )
        return mission

    def transition(self, mission_id: str, state: MissionState, *, now_ms: int) -> ResearchMission:
        mission = self._missions[mission_id].transition(state)
        self._missions[mission_id] = mission
        self._emit(
            EventKind.RESEARCH_MISSION,
            mission.body() | {"seal": mission.seal},
            now_ms,
            mission_id,
        )
        return mission

    def add_packet(self, packet: ResearchPacket) -> ResearchPacket:
        if packet.mission_id not in self._missions:
            raise ResearchContractError(
                f"packet refers to unknown mission {packet.mission_id}")
        if not packet.seal_ok():
            raise ResearchContractError("packet seal does not verify")
        prior = self._packets.get(packet.packet_id)
        if prior is not None and prior.seal != packet.seal:
            raise ResearchContractError(f"packet {packet.packet_id} is immutable")
        self._packets[packet.packet_id] = packet
        self._emit(
            EventKind.RESEARCH_PACKET,
            packet.body() | {"seal": packet.seal},
            packet.created_ms,
            packet.mission_id,
        )
        return packet

    def mission(self, mission_id: str) -> ResearchMission:
        return self._missions[mission_id]

    def packets(self, mission_id: str) -> list[ResearchPacket]:
        return sorted(
            (p for p in self._packets.values() if p.mission_id == mission_id),
            key=lambda p: (p.agent_role, p.packet_id),
        )

    def rebuild(self, events) -> "MissionLedger":
        """Reconstruct the latest mission/packet projection from the VATI ledger."""
        self._missions.clear()
        self._packets.clear()
        for event in events:
            if event.kind is EventKind.RESEARCH_MISSION:
                body = dict(event.payload)
                budget = ResearchBudget(**body["budget"])
                mission = ResearchMission(
                    mission_id=str(body["mission_id"]),
                    hypothesis=str(body["hypothesis"]),
                    trigger=str(body["trigger"]),
                    parent_evidence_ids=tuple(body.get("parent_evidence_ids", ())),
                    allowed_data_domains=tuple(body.get("allowed_data_domains", ())),
                    prohibited_live_actions=tuple(body.get("prohibited_live_actions", ())),
                    required_roles=tuple(body.get("required_roles", ())),
                    budget=budget,
                    deadline_ms=int(body["deadline_ms"]),
                    source_policy=str(body["source_policy"]),
                    output_schema=str(body["output_schema"]),
                    model_policy=tuple(body.get("model_policy", ())),
                    created_ms=int(body["created_ms"]),
                    state=MissionState(str(body.get("state", MissionState.OPEN.value))),
                    mission_version=str(body.get("mission_version", MISSION_VERSION)),
                    seal=str(body.get("seal", "")),
                )
                if not mission.seal_ok():
                    mission = ResearchMission(**{**mission.__dict__, "seal": ""}).sealed()
                self._missions[mission.mission_id] = mission
            elif event.kind is EventKind.RESEARCH_PACKET:
                body = dict(event.payload)
                claims = tuple(
                    ResearchClaim(
                        claim_id=str(c["claim_id"]),
                        statement=str(c["statement"]),
                        evidence_ids=tuple(c.get("evidence_ids", ())),
                        confidence=str(c.get("confidence", "UNSPECIFIED")),
                    )
                    for c in body.get("claims", ())
                )
                packet = ResearchPacket(
                    packet_id=str(body["packet_id"]),
                    mission_id=str(body["mission_id"]),
                    agent_role=str(body["agent_role"]),
                    provider=str(body.get("provider", "")),
                    model_id=str(body.get("model_id", "")),
                    source_ids=tuple(body.get("source_ids", ())),
                    retrieved_ms=tuple(int(x) for x in body.get("retrieved_ms", ())),
                    claims=claims,
                    evidence_refs=tuple(body.get("evidence_refs", ())),
                    counterevidence=tuple(body.get("counterevidence", ())),
                    limitations=tuple(body.get("limitations", ())),
                    methods=tuple(body.get("methods", ())),
                    artifact_refs=tuple(body.get("artifact_refs", ())),
                    reproducibility=dict(body.get("reproducibility", {})),
                    created_ms=int(body["created_ms"]),
                    state=PacketState(str(body.get("state", PacketState.COMPLETE.value))),
                    failure_reason=str(body.get("failure_reason", "")),
                    packet_version=str(body.get("packet_version", PACKET_VERSION)),
                    seal=str(body.get("seal", "")),
                )
                if not packet.seal_ok():
                    packet = ResearchPacket(**{**packet.__dict__, "seal": ""}).sealed()
                self._packets[packet.packet_id] = packet
        return self

    def _emit(self, kind: EventKind, payload: dict, now_ms: int, corr: str) -> None:
        if self._ledger is not None:
            self._ledger.append(
                make_event(
                    kind,
                    self._producer,
                    payload,
                    event_time_ms=now_ms,
                    received_time_ms=now_ms,
                    correlation_id=corr,
                )
            )


__all__ = [
    "MISSION_VERSION",
    "PACKET_VERSION",
    "MissionLedger",
    "MissionState",
    "PacketState",
    "ResearchBudget",
    "ResearchClaim",
    "ResearchContractError",
    "ResearchMission",
    "ResearchPacket",
]
