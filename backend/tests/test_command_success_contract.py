"""P1-VERIFY-003 — an owner command carries its own success contract.

The spine was complete and one joint was missing, which is why this finding is not "the
verifier is wrong" but "nothing ever asked it anything".

`TypedCommandResolver` resolves an exact owner phrase to a registered action and copies
that action's declared `verifier_type` onto the resolution. `MissionService` picks a
verifier from the mission's success contract and refuses VERIFIED_SUCCESS without evidence.
`VerifierRegistry` holds adapters that observe the target system independently. Between
them, `CommandMissionLink.open` created every mission with `SuccessContract()`. So
`CommandResolution.verifier_type` was written by the resolver and read by nothing, and no
mission originating from an owner command could reach VERIFIED_SUCCESS — not the free-form
ones, which is correct, but not the exactly-resolved ones either.

These tests state the closure and its limits. The contract exists only where an independent
observation does; where it does not, the mission still cannot be verified and now says why.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.command.success_contracts import (
    NO_CONTRACT_REASONS,
    contract_for,
    no_contract_reason,
)
from van_gateway.mission.models import MissionState, VerificationStatus
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.models import ActionClass, CommandRequest, OriginChannel, PrincipalType
from van_gateway.storage.db import Store
from van_gateway.verification.production import (
    WIRED_MISSION_STRATEGIES,
    build_mission_registry,
)

RESOLVER = TypedCommandResolver(default_notebook_id="nb-default")


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "contract.sqlite3"))
    await s.migrate()
    return s


class HaltedLedger:
    """VATI after an owner halt: the kill switch is up and the chain verifies."""

    def __init__(self, *, active=True, triggers=("OWNER_HALT",), stale=False, chain_ok=True):
        self._payload = {
            "ledger_available": True, "chain_ok": chain_ok, "head": "abc123",
            "kill_switch_active": active, "kill_switch_triggers": list(triggers),
            "ledger_stale": stale, "ledger_stale_reason": "newest event is 4000s old",
        }
        self.reads = 0

    def status(self):
        self.reads += 1
        return dict(self._payload)

    def trade_detail(self, trade_intent_id):  # pragma: no cover - not this path
        return None


class Notebooks:
    class NotFound(RuntimeError):
        pass

    def __init__(self, known=()):
        self.known = set(known)
        self.asked: list[str] = []

    async def notebook_enterprise_get(self, notebook_id: str):
        self.asked.append(notebook_id)
        if notebook_id not in self.known:
            raise self.NotFound("notebook_enterprise_not_found")
        return {"name": notebook_id, "sources": [{"id": "s1"}]}


def _request(text: str, *, action_class=ActionClass.A4) -> CommandRequest:
    return CommandRequest(
        command_id=f"cmd-{abs(hash(text)) % 10**8}",
        device_id="dev-1",
        principal_type=PrincipalType.OWNER_DEVICE,
        origin_channel=OriginChannel.VOICE,
        action_class=action_class,
        text=text,
        issued_at_unix=1,
        nonce="n" * 16,
        signature="s" * 16,
        idempotency_key="idem-" + text[:8],
    )


async def _mission_for(store, text, *, trading, knowledge, action_class=ActionClass.A4):
    """Drive one command through the real translator to VERIFYING."""
    svc = MissionService(
        store, verifiers=build_mission_registry(
            store=store, trading=trading, knowledge=knowledge,
        ),
    )
    link = CommandMissionLink(svc)
    resolution = RESOLVER.resolve(text)
    mission = await link.open(
        _request(text, action_class=action_class),
        effective_action_class=action_class,
        owner_approved=True,
        resolution=resolution,
    )
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING, MissionState.VERIFYING):
        mission = await svc.transition(mission.mission_id, target=target)
    return svc, mission


# --------------------------------------------------------------- the finding itself

class TestTheResolverIsNoLongerWriteOnly:
    def test_an_exact_trading_halt_produces_a_checkable_contract(self):
        resolution = RESOLVER.resolve("halt trading")
        assert resolution.mode is ResolutionMode.EXACT_ACTION
        contract = contract_for(resolution)
        assert contract.is_checkable
        assert contract.verifier_class == "trading-halt"
        assert contract.postconditions == {
            "kill_switch_active": True, "owner_halt_active": True,
        }

    def test_free_form_text_produces_nothing_checkable(self):
        """The half of the old behaviour that was right, kept."""
        resolution = RESOLVER.resolve("sort out the thing with the roof")
        assert resolution.mode is ResolutionMode.HERMES_INTERPRETATION_REQUIRED
        assert not contract_for(resolution).is_checkable
        assert "not resolved to a known action" in no_contract_reason(resolution)

    def test_every_contract_names_a_strategy_the_registry_holds(self):
        """A contract naming an unregistered strategy is a mission that cannot be verified.

        This is the invariant that keeps the translator honest: it may only promise a check
        that something is registered to perform.
        """
        for text in ("halt trading", "delete the notebook enterprise notebook id nb-7",
                     "research quantum computing", "what do you know about the roof?"):
            contract = contract_for(RESOLVER.resolve(text))
            if contract.verifier_class is not None:
                assert contract.verifier_class in WIRED_MISSION_STRATEGIES, text

    def test_an_action_with_no_independent_source_says_why(self):
        """"VAN cannot confirm this" is a supported outcome; an unexplained one is not."""
        for text, action_id in (
            ("research quantum computing", "research.web.search"),
            ("what do you know about the roof?", "owner.context.read"),
        ):
            resolution = RESOLVER.resolve(text)
            assert resolution.action_id == action_id
            assert not contract_for(resolution).is_checkable
            assert no_contract_reason(resolution) == NO_CONTRACT_REASONS[action_id]

    def test_a_create_with_no_notebook_id_yet_is_not_given_a_contract(self):
        """The id does not exist until the provider assigns it, so there is nothing to read
        back at command time. Promising a readback that pointed at nothing would be the
        defect this whole finding is about, one level down."""
        resolution = RESOLVER.resolve("create a notebooklm note called Roof repair")
        assert resolution.action_id == "google.notebook.note.create"
        # The resolver seals the configured default notebook, which is a destination, not
        # the enterprise notebook this strategy reads back.
        contract = contract_for(resolution)
        assert not contract.is_checkable


# ------------------------------------------------------- end to end through the link

@pytest.mark.asyncio
class TestAnOwnerCommandCanNowBeVerified:
    async def test_a_halt_the_ledger_confirms_reaches_verified_success(self, store):
        trading = HaltedLedger()
        svc, mission = await _mission_for(
            store, "halt trading", trading=trading, knowledge=Notebooks(),
        )
        assert mission.success_contract.verifier_class == "trading-halt"
        done = await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        assert done.state is MissionState.VERIFIED_SUCCESS
        record = await svc.verification_record(mission.mission_id)
        assert record.status is VerificationStatus.VERIFIED
        assert record.evidence_refs == ["ledger://kill-switch/abc123"]
        # The ledger was actually read. Before this finding it never was.
        assert trading.reads >= 1

    async def test_a_halt_the_ledger_does_not_show_cannot_succeed(self, store):
        """The command returned; the runner never stopped. That is not success."""
        trading = HaltedLedger(active=False, triggers=())
        svc, mission = await _mission_for(
            store, "stop trading", trading=trading, knowledge=Notebooks(),
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        await svc.transition(mission.mission_id, target=MissionState.UNVERIFIABLE)
        record = await svc.verification_record(mission.mission_id)
        assert record.status is VerificationStatus.FAILED
        assert set(record.missing_postconditions) == {"kill_switch_active", "owner_halt_active"}
        # A record that failed must cite nothing. The ledger head is real and citing it
        # here would put a genuine-looking `ledger://` reference on a mission that did not
        # succeed — the kind of artefact an owner or an auditor reads as proof.
        assert record.evidence_refs == []

    async def test_a_halt_triggered_by_something_other_than_the_owner_is_not_this_halt(self, store):
        """A risk-limit trip also raises the kill switch. It did not come from this command,
        and reading it as confirmation would let an unrelated event certify an owner's."""
        trading = HaltedLedger(triggers=("DAILY_LOSS_LIMIT",))
        svc, mission = await _mission_for(
            store, "halt trading", trading=trading, knowledge=Notebooks(),
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        await svc.transition(mission.mission_id, target=MissionState.UNVERIFIABLE)
        record = await svc.verification_record(mission.mission_id)
        assert record.missing_postconditions == ["owner_halt_active"]

    async def test_a_stale_ledger_is_not_a_confirmation(self, store):
        """P0-TRADE-004 — a copy somebody left behind would confirm a stop that never
        reached the runner."""
        trading = HaltedLedger(stale=True)
        svc, mission = await _mission_for(
            store, "halt trading", trading=trading, knowledge=Notebooks(),
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        await svc.transition(mission.mission_id, target=MissionState.UNVERIFIABLE)
        record = await svc.verification_record(mission.mission_id)
        assert record.status is VerificationStatus.UNVERIFIABLE
        assert record.observed_postconditions["error"] == "ValueError"

    async def test_a_ledger_whose_chain_is_broken_cannot_speak_for_anything(self, store):
        trading = HaltedLedger(chain_ok=False)
        svc, mission = await _mission_for(
            store, "halt trading", trading=trading, knowledge=Notebooks(),
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        await svc.transition(mission.mission_id, target=MissionState.UNVERIFIABLE)
        assert (await svc.verification_record(mission.mission_id)).status is (
            VerificationStatus.UNVERIFIABLE
        )

    async def test_a_notebook_delete_is_confirmed_by_the_provider_saying_it_is_gone(self, store):
        knowledge = Notebooks(known=())
        svc, mission = await _mission_for(
            store,
            "delete the notebook enterprise notebook id nb-7",
            trading=HaltedLedger(), knowledge=knowledge,
        )
        assert mission.success_contract.postconditions == {
            "notebook_id": "nb-7", "notebook_exists": False,
        }
        done = await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        assert done.state is MissionState.VERIFIED_SUCCESS
        assert knowledge.asked == ["nb-7"]

    async def test_a_notebook_delete_the_provider_still_shows_is_not_done(self, store):
        knowledge = Notebooks(known=("nb-7",))
        svc, mission = await _mission_for(
            store,
            "delete the notebook enterprise notebook id nb-7",
            trading=HaltedLedger(), knowledge=knowledge,
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        await svc.transition(mission.mission_id, target=MissionState.UNVERIFIABLE)
        record = await svc.verification_record(mission.mission_id)
        assert record.missing_postconditions == ["notebook_exists"]

    async def test_a_provider_that_cannot_be_reached_is_not_a_deletion(self, store):
        """"Gone" and "I could not ask" are different answers and only one is a pass."""

        class Unreachable:
            async def notebook_enterprise_get(self, notebook_id):
                raise RuntimeError("notebook_enterprise_http_503")

        svc, mission = await _mission_for(
            store,
            "delete the notebook enterprise notebook id nb-7",
            trading=HaltedLedger(), knowledge=Unreachable(),
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        await svc.transition(mission.mission_id, target=MissionState.UNVERIFIABLE)
        assert (await svc.verification_record(mission.mission_id)).status is (
            VerificationStatus.UNVERIFIABLE
        )

    async def test_an_unverifiable_command_records_why_on_the_mission(self, store):
        """The owner sees COMPLETED_UNVERIFIED either way; the difference is whether they
        are told it was decided at the outset and for what reason."""
        svc, mission = await _mission_for(
            store, "research quantum computing",
            trading=HaltedLedger(), knowledge=Notebooks(), action_class=ActionClass.A2,
        )
        assert not mission.success_contract.is_checkable
        assert any(c.startswith("unverifiable: ") for c in mission.constraints), mission.constraints
        with pytest.raises(MissionError, match="SUCCESS_CONTRACT_NOT_CHECKABLE"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)

    async def test_a_verifiable_command_carries_no_such_note(self, store):
        svc, mission = await _mission_for(
            store, "halt trading", trading=HaltedLedger(), knowledge=Notebooks(),
        )
        assert not any(c.startswith("unverifiable: ") for c in mission.constraints)
