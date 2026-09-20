"""Rev 5.1 research mission and packet contracts (TRD-REV51-118).

Research is a slow-plane activity.  These contracts make a research request and every
worker result immutable, versioned, replayable and explicit about what it may *not* do.
Nothing in this module imports the execution or live-risk paths.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

MISSION_VERSION = "research-mission/5.1.0"
PACKET_VERSION = "research-packet/5.1.0"
DEFAULT_PROHIBITED_LIVE_ACTIONS = (
    "ORDER_SEND",
    "LIVE_RISK_CHANGE",
    "MANDATE_CHANGE",
    "STRATEGY_PROMOTION",
    "PROTECTED_PATH_EDIT",
)


class ResearchContractError(ValueError):
    pass


class MissionState(str, Enum):
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class PacketState(str, Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ResearchMission:
    mission_id: str
    hypothesis: str
    trigger: str
    parent_evidence_ids: tuple[str, ...]
    allowed_data_domains: tuple[str, ...]
    required_specialist_roles: tuple[str, ...]
    budget_micros: int
    deadline_ms: int
    source_policy: str
    output_schema: str
    model_provider_policy: str
    created_ms: int
    prohibited_live_actions: tuple[str, ...] = DEFAULT_PROHIBITED_LIVE_ACTIONS
    state: MissionState = MissionState.OPEN
    mission_version: str = MISSION_VERSION
    mission_hash: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "hypothesis": self.hypothesis,
            "trigger": self.trigger,
            "parent_evidence_ids": list(self.parent_evidence_ids),
            "allowed_data_domains": list(self.allowed_data_domains),
            "required_specialist_roles": list(self.required_specialist_roles),
            "budget_micros": self.budget_micros,
            "deadline_ms": self.deadline_ms,
            "source_policy": self.source_policy,
            "output_schema": self.output_schema,
            "model_provider_policy": self.model_provider_policy,
            "created_ms": self.created_ms,
            "prohibited_live_actions": list(self.prohibited_live_actions),
            "state": self.state.value,
            "mission_version": self.mission_version,
        }

    def validate(self) -> None:
        if not self.mission_id or not self.hypothesis or not self.trigger:
            raise ResearchContractError("mission id, hypothesis and trigger are required")
        if self.budget_micros <= 0:
            raise ResearchContractError("research budget must be positive")
        if self.deadline_ms <= self.created_ms:
            raise ResearchContractError("research deadline must be after creation")
        if not self.required_specialist_roles:
            raise ResearchContractError("research mission has no specialist roles")
        if not set(DEFAULT_PROHIBITED_LIVE_ACTIONS) <= set(self.prohibited_live_actions):
            raise ResearchContractError("research mission relaxes prohibited live actions")

    def sealed(self) -> "ResearchMission":
        self.validate()
        return replace(self, mission_hash=canonical_hash(self.body()))

    def seal_ok(self) -> bool:
        return bool(self.mission_hash) and self.mission_hash == canonical_hash(self.body())

    def transition(self, state: MissionState) -> "ResearchMission":
        if self.state in (MissionState.COMPLETE, MissionState.FAILED, MissionState.BUDGET_EXHAUSTED):
            if state is not self.state:
                raise ResearchContractError(f"terminal mission {self.mission_id} cannot move to {state.value}")
        return replace(self, state=state, mission_hash="").sealed()

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "ResearchMission":
        return cls(
            mission_id=str(body["mission_id"]),
            hypothesis=str(body["hypothesis"]),
            trigger=str(body["trigger"]),
            parent_evidence_ids=tuple(body.get("parent_evidence_ids", ())),
            allowed_data_domains=tuple(body.get("allowed_data_domains", ())),
            required_specialist_roles=tuple(body.get("required_specialist_roles", ())),
            budget_micros=int(body["budget_micros"]),
            deadline_ms=int(body["deadline_ms"]),
            source_policy=str(body["source_policy"]),
            output_schema=str(body["output_schema"]),
            model_provider_policy=str(body["model_provider_policy"]),
            created_ms=int(body["created_ms"]),
            prohibited_live_actions=tuple(body.get("prohibited_live_actions", DEFAULT_PROHIBITED_LIVE_ACTIONS)),
            state=MissionState(str(body.get("state", MissionState.OPEN.value))),
            mission_version=str(body.get("mission_version", MISSION_VERSION)),
        ).sealed()


@dataclass(frozen=True)
class ResearchPacket:
    mission_id: str
    agent_role: str
    model_id: str
    source_ids: tuple[str, ...]
    retrieval_timestamps_ms: tuple[int, ...]
    claims: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    counterevidence: tuple[str, ...]
    limitations: tuple[str, ...]
    methods: tuple[str, ...]
    code_data_artifacts: tuple[str, ...]
    reproducibility: tuple[str, ...]
    created_ms: int
    state: PacketState = PacketState.COMPLETE
    failure_reason: str = ""
    packet_version: str = PACKET_VERSION
    packet_hash: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "agent_role": self.agent_role,
            "model_id": self.model_id,
            "source_ids": list(self.source_ids),
            "retrieval_timestamps_ms": list(self.retrieval_timestamps_ms),
            "claims": list(self.claims),
            "evidence_refs": list(self.evidence_refs),
            "counterevidence": list(self.counterevidence),
            "limitations": list(self.limitations),
            "methods": list(self.methods),
            "code_data_artifacts": list(self.code_data_artifacts),
            "reproducibility": list(self.reproducibility),
            "created_ms": self.created_ms,
            "state": self.state.value,
            "failure_reason": self.failure_reason,
            "packet_version": self.packet_version,
        }

    def validate(self) -> None:
        if not self.mission_id or not self.agent_role:
            raise ResearchContractError("packet mission and role are required")
        if self.state is PacketState.COMPLETE:
            if not self.model_id:
                raise ResearchContractError("complete packet has no model id")
            if not self.claims:
                raise ResearchContractError("complete packet has no claims")
            if not self.source_ids or not self.evidence_refs:
                raise ResearchContractError("complete packet has no source/evidence references")
        elif not self.failure_reason:
            raise ResearchContractError("failed packet has no failure reason")

    def sealed(self) -> "ResearchPacket":
        self.validate()
        return replace(self, packet_hash=canonical_hash(self.body()))

    def seal_ok(self) -> bool:
        return bool(self.packet_hash) and self.packet_hash == canonical_hash(self.body())

    @classmethod
    def failed(cls, *, mission_id: str, agent_role: str, model_id: str,
               reason: str, created_ms: int) -> "ResearchPacket":
        return cls(
            mission_id=mission_id, agent_role=agent_role, model_id=model_id,
            source_ids=(), retrieval_timestamps_ms=(), claims=(), evidence_refs=(),
            counterevidence=(), limitations=(), methods=(), code_data_artifacts=(),
            reproducibility=(), created_ms=created_ms, state=PacketState.FAILED,
            failure_reason=reason,
        ).sealed()


class ResearchMissionStore:
    """Append-only mission/packet projection with ledger replay."""

    def __init__(self, *, ledger=None, producer: str = "vati-research-missions") -> None:
        self._ledger = ledger
        self._producer = producer
        self._missions: dict[str, ResearchMission] = {}
        self._packets: list[ResearchPacket] = []

    def create(self, mission: ResearchMission) -> ResearchMission:
        sealed = mission.sealed()
        if sealed.mission_id in self._missions:
            existing = self._missions[sealed.mission_id]
            if existing.mission_hash != sealed.mission_hash:
                raise ResearchContractError("mission id already exists with different terms")
            return existing
        self._missions[sealed.mission_id] = sealed
        self._emit_mission(sealed)
        return sealed

    def transition(self, mission_id: str, state: MissionState, *, now_ms: int) -> ResearchMission:
        mission = self._missions[mission_id].transition(state)
        self._missions[mission_id] = mission
        self._emit_mission(mission, now_ms=now_ms)
        return mission

    def add_packet(self, packet: ResearchPacket) -> ResearchPacket:
        sealed = packet.sealed()
        if sealed.mission_id not in self._missions:
            raise ResearchContractError("packet refers to unknown mission")
        if any(p.packet_hash == sealed.packet_hash for p in self._packets):
            return sealed
        self._packets.append(sealed)
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.RESEARCH_PACKET, self._producer,
                {**sealed.body(), "packet_hash": sealed.packet_hash},
                event_time_ms=sealed.created_ms, received_time_ms=sealed.created_ms,
                correlation_id=sealed.mission_id,
            ))
        return sealed

    def get(self, mission_id: str) -> Optional[ResearchMission]:
        return self._missions.get(mission_id)

    def packets(self, mission_id: Optional[str] = None) -> list[ResearchPacket]:
        return [p for p in self._packets if mission_id is None or p.mission_id == mission_id]

    def rebuild(self, events: Iterable) -> "ResearchMissionStore":
        self._missions.clear()
        self._packets.clear()
        for event in events:
            if event.kind is EventKind.RESEARCH_MISSION:
                body = dict(event.payload)
                mission = ResearchMission.from_body(body)
                self._missions[mission.mission_id] = mission
            elif event.kind is EventKind.RESEARCH_PACKET:
                body = dict(event.payload)
                packet = ResearchPacket(
                    mission_id=str(body["mission_id"]), agent_role=str(body["agent_role"]),
                    model_id=str(body.get("model_id", "")), source_ids=tuple(body.get("source_ids", ())),
                    retrieval_timestamps_ms=tuple(int(x) for x in body.get("retrieval_timestamps_ms", ())),
                    claims=tuple(body.get("claims", ())), evidence_refs=tuple(body.get("evidence_refs", ())),
                    counterevidence=tuple(body.get("counterevidence", ())), limitations=tuple(body.get("limitations", ())),
                    methods=tuple(body.get("methods", ())), code_data_artifacts=tuple(body.get("code_data_artifacts", ())),
                    reproducibility=tuple(body.get("reproducibility", ())), created_ms=int(body["created_ms"]),
                    state=PacketState(str(body.get("state", PacketState.COMPLETE.value))),
                    failure_reason=str(body.get("failure_reason", "")),
                    packet_version=str(body.get("packet_version", PACKET_VERSION)),
                ).sealed()
                self._packets.append(packet)
        return self

    def _emit_mission(self, mission: ResearchMission, *, now_ms: Optional[int] = None) -> None:
        if self._ledger is None:
            return
        at = mission.created_ms if now_ms is None else now_ms
        self._ledger.append(make_event(
            EventKind.RESEARCH_MISSION, self._producer,
            {**mission.body(), "mission_hash": mission.mission_hash},
            event_time_ms=at, received_time_ms=at, correlation_id=mission.mission_id,
        ))
