"""Offline research/evolution coordinator for Rev 5.1 G12/G13.

The coordinator has no execution imports and no route to live authority.  It consumes
sealed missions, invokes bounded specialist workers through the shared model hierarchy,
qualifies/synthesises evidence and may create *proposals*.  Proposals remain proposals
until independent gate evidence and any required owner review are supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional

from vati.cognition.providers import QuotaScheduler, default_registry
from vati.evolution.admission import ProposalAdmissionControl
from vati.evolution.archive import EvolutionArchive, EvolutionRecord
from vati.evolution.proposals import (
    SystemImprovementProposal, SystemImprovementProposalEngine,
)
from vati.research.agents import InvokeResearch, ResearchAgentFactory
from vati.research.missions import MissionLedger, MissionState, PacketState
from vati.research.synthesis import ResearchSynthesiser, ResearchSynthesis
from vati.research.yield_ledger import ResearchYieldLedger, ResearchYieldRecord

ProposalBuilder = Callable[[ResearchSynthesis], Iterable[SystemImprovementProposal]]
GateProvider = Callable[[SystemImprovementProposal], Optional[Mapping[str, bool]]]


@dataclass(frozen=True)
class EvolutionRunResult:
    mission_id: str
    state: str
    blocked_reason: str
    packets_complete: int
    packets_failed: int
    synthesis_hash: str
    supported_claims: int
    proposal_ids: tuple[str, ...]
    admission_states: tuple[str, ...]


class OfflineEvolutionRuntime:
    """One deterministic orchestration surface for G12/G13.

    Missing external model/research transport is BLOCKED, not silently replaced by fake
    evidence.  A mission remains OPEN in that case so a later worker can resume it.
    """

    def __init__(self, *, ledger, invoke: Optional[InvokeResearch] = None,
                 proposal_builder: Optional[ProposalBuilder] = None,
                 gate_provider: Optional[GateProvider] = None) -> None:
        self.ledger = ledger
        self.invoke = invoke
        self.proposal_builder = proposal_builder
        self.gate_provider = gate_provider
        self.missions = MissionLedger(ledger=ledger).rebuild(ledger.iter())
        self.scheduler = QuotaScheduler(default_registry())
        self.agents = ResearchAgentFactory(self.scheduler)
        self.synthesiser = ResearchSynthesiser(ledger=ledger)
        self.yield_ledger = ResearchYieldLedger(ledger=ledger)
        self.proposals = SystemImprovementProposalEngine(ledger=ledger)
        self.admission = ProposalAdmissionControl(ledger=ledger)
        self.archive = EvolutionArchive(ledger=ledger)

    def refresh(self) -> None:
        self.missions.rebuild(self.ledger.iter())

    def run_open(self, *, now_ms: int, limit: int = 10) -> list[EvolutionRunResult]:
        self.refresh()
        open_ids = [
            m.mission_id for m in self.missions.missions()
            if m.state in (MissionState.OPEN, MissionState.RUNNING)
        ][:max(0, limit)]
        return [self.run_mission(mid, now_ms=now_ms) for mid in open_ids]

    def run_mission(self, mission_id: str, *, now_ms: int) -> EvolutionRunResult:
        self.refresh()
        mission = self.missions.mission(mission_id)
        if mission.state not in (MissionState.OPEN, MissionState.RUNNING):
            packets = self.missions.packets(mission_id)
            return EvolutionRunResult(
                mission_id, mission.state.value, "TERMINAL",
                sum(p.state is PacketState.COMPLETE for p in packets),
                sum(p.state is PacketState.FAILED for p in packets),
                "", 0, (), (),
            )
        if now_ms >= mission.deadline_ms:
            if mission.state is MissionState.OPEN:
                mission = self.missions.transition(
                    mission_id, MissionState.FAILED, now_ms=now_ms)
            elif mission.state is MissionState.RUNNING:
                mission = self.missions.transition(
                    mission_id, MissionState.FAILED, now_ms=now_ms)
            return EvolutionRunResult(
                mission_id, mission.state.value, "DEADLINE_EXPIRED",
                0, 0, "", 0, (), (),
            )
        if self.invoke is None:
            return EvolutionRunResult(
                mission_id, mission.state.value, "MODEL_INVOKER_UNAVAILABLE",
                0, 0, "", 0, (), (),
            )

        if mission.state is MissionState.OPEN:
            mission = self.missions.transition(
                mission_id, MissionState.RUNNING, now_ms=now_ms)

        existing = {p.agent_role: p for p in self.missions.packets(mission_id)}
        roles = mission.required_roles[:mission.budget.max_agents]
        for role in roles:
            if role in existing:
                continue
            packet = self.agents.run(
                mission, role, invoke=self.invoke, now_ms=now_ms)
            self.missions.add_packet(packet)
            existing[role] = packet

        packets = self.missions.packets(mission_id)
        synthesis = self.synthesiser.synthesise(
            mission, packets, now_ms=now_ms)

        complete_roles = {
            p.agent_role for p in packets if p.state is PacketState.COMPLETE
        }
        all_required = set(roles) <= complete_roles
        mission = self.missions.transition(
            mission_id,
            MissionState.COMPLETE if all_required else MissionState.FAILED,
            now_ms=now_ms,
        )

        proposal_ids: list[str] = []
        admission_states: list[str] = []
        if self.proposal_builder is not None:
            for proposal in self.proposal_builder(synthesis):
                sealed = self.proposals.propose(proposal)
                proposal_ids.append(sealed.proposal_id)
                gates = (
                    None if self.gate_provider is None
                    else self.gate_provider(sealed)
                )
                # Missing independent gate evidence is not converted into a
                # synthetic rejection/pass. The proposal simply remains pending.
                if gates is not None:
                    rec = self.admission.assess(
                        sealed, gate_evidence=gates,
                        owner_approved=False, now_ms=now_ms)
                    admission_states.append(rec.state.value)

        provider_cost = {}
        for provider in self.scheduler.registry:
            provider_cost[provider.model_id] = provider.cost_per_request_micros
        total_cost = sum(
            provider_cost.get(p.model_id, 0)
            for p in packets if p.state is PacketState.COMPLETE
        )
        rejected = sum(
            c.status.value != "SUPPORTED" for c in synthesis.claims)
        self.yield_ledger.record(ResearchYieldRecord(
            mission_id=mission_id,
            cost_micros=total_cost,
            admitted_findings=len(synthesis.admitted_claims),
            duplicate_findings=0,
            rejected_findings=rejected,
            invalidated_findings=0,
            improvement_proposals=len(proposal_ids),
            downstream_value="UNMEASURED",
            measured_ms=now_ms,
        ))

        return EvolutionRunResult(
            mission_id=mission_id,
            state=mission.state.value,
            blocked_reason="",
            packets_complete=sum(
                p.state is PacketState.COMPLETE for p in packets),
            packets_failed=sum(
                p.state is PacketState.FAILED for p in packets),
            synthesis_hash=synthesis.digest,
            supported_claims=len(synthesis.admitted_claims),
            proposal_ids=tuple(proposal_ids),
            admission_states=tuple(admission_states),
        )

    def archive_candidate(self, record: EvolutionRecord) -> EvolutionRecord:
        """Archive a separately qualified candidate. Never manufactures one."""
        return self.archive.append(record)
