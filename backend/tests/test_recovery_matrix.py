"""P3-OPS-008 — the partial-failure cells, one test each.

The audit's observation was that the suite is overwhelmingly happy-path: gateway restart
mid-command, Android process death while awaiting approval, duplicate provider callbacks,
connectivity loss after a mutation but before the receipt, and trading state changing while
an approval is pending were all unexercised. An unexercised cell is unshipped, because the
behaviour in it is whatever the code happens to do.

Writing the matrix found one of them was not merely untested. Cell 1 is now
P0-OPS-011: an IN_FLIGHT idempotency claim had no lease, so a gateway that died between
claiming a key and completing it made that command permanently unrepeatable — and because
the idempotency key is part of the signed request, the owner could not work around it by
changing it.

Each test names its cell, what fails, and what must be true afterwards. The bar is not
"does not crash": a recovery that silently repeats a mutation is worse than a refusal.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio

from van_gateway.idempotency.service import (
    STALE_CLAIM_SECONDS,
    IdempotencyConflict,
    IdempotencyInFlight,
    IdempotencyService,
    IdempotencyStatus,
)
from van_gateway.mission.models import (
    AuthorityEnvelope,
    MissionOrigin,
    MissionState,
)
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.models import ActionClass, CommandRequest, OriginChannel, PrincipalType
from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.storage.db import Store

PAYLOAD = {"command_id": "cmd-1", "text": "do the thing"}


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "recovery.sqlite3"))
    await s.migrate()
    return s


async def _age_claim(store, key, seconds):
    """Move a claim's clock back, which is what a crash looks like from the outside."""
    await store.execute(
        "UPDATE idempotency SET updated_at_unix = ? WHERE idempotency_key = ?",
        (int(time.time()) - seconds, key),
    )


# ---------------------------------------------------------------- cell 1: restart

@pytest.mark.asyncio
class TestCellGatewayRestartMidCommand:
    """The gateway claims an idempotency key, then the process dies."""

    async def test_a_fresh_claim_is_still_refused(self, store):
        """The lease must not weaken the guarantee it is bolted onto.

        Two copies of the same signed command arriving together is the case P1-SEC-005
        closed, and a lease that released a claim early would reopen it.
        """
        service = IdempotencyService(store)
        assert await service.begin("k", PAYLOAD) is None
        with pytest.raises(IdempotencyInFlight):
            await service.begin("k", PAYLOAD)

    async def test_a_claim_just_short_of_the_lease_is_still_refused(self, store):
        service = IdempotencyService(store)
        await service.begin("k", PAYLOAD)
        await _age_claim(store, "k", STALE_CLAIM_SECONDS - 5)
        with pytest.raises(IdempotencyInFlight):
            await service.begin("k", PAYLOAD)

    async def test_a_claim_whose_holder_is_gone_can_be_retaken(self, store):
        """The defect: without this the command is unrepeatable forever, and the key is
        part of the signed request so the owner cannot change it."""
        service = IdempotencyService(store)
        await service.begin("k", PAYLOAD)
        await _age_claim(store, "k", STALE_CLAIM_SECONDS + 1)
        assert await service.begin("k", PAYLOAD) is None

    async def test_a_retaken_claim_says_it_was_retaken(self, store):
        """A recovered claim that looks like a first attempt hides the crash that caused
        it, and a command being retried every fifteen minutes forever would look normal."""
        service = IdempotencyService(store)
        await service.begin("k", PAYLOAD)
        await _age_claim(store, "k", STALE_CLAIM_SECONDS + 1)
        await service.begin("k", PAYLOAD)
        row = await store.fetchone(
            "SELECT claim_count, status FROM idempotency WHERE idempotency_key = ?", ("k",)
        )
        assert int(row["claim_count"]) == 2
        assert str(row["status"]) == IdempotencyStatus.IN_FLIGHT.value

    async def test_retaking_resets_the_lease(self, store):
        service = IdempotencyService(store)
        await service.begin("k", PAYLOAD)
        await _age_claim(store, "k", STALE_CLAIM_SECONDS + 1)
        await service.begin("k", PAYLOAD)
        with pytest.raises(IdempotencyInFlight):
            await service.begin("k", PAYLOAD)

    async def test_a_completed_answer_is_never_retaken(self, store):
        """COMPLETED is an answer, not a claim. Age must not turn it back into work."""
        service = IdempotencyService(store)
        await service.begin("k", PAYLOAD)
        await service.complete("k", {"status": "accepted"})
        await _age_claim(store, "k", STALE_CLAIM_SECONDS * 10)
        assert await service.begin("k", PAYLOAD) == {"status": "accepted"}

    async def test_a_conflict_is_never_retaken(self, store):
        service = IdempotencyService(store)
        await service.begin("k", PAYLOAD)
        with pytest.raises(IdempotencyConflict):
            await service.begin("k", {"command_id": "cmd-1", "text": "something else"})
        await _age_claim(store, "k", STALE_CLAIM_SECONDS * 10)
        with pytest.raises(IdempotencyConflict):
            await service.begin("k", PAYLOAD)

    async def test_a_stale_claim_under_a_different_request_is_a_conflict(self, store):
        """Age does not make a different request the same request."""
        service = IdempotencyService(store)
        await service.begin("k", PAYLOAD)
        await _age_claim(store, "k", STALE_CLAIM_SECONDS + 1)
        with pytest.raises(IdempotencyConflict):
            await service.begin("k", {"command_id": "cmd-1", "text": "different"})


# ------------------------------------------------- cell 2: restart after dispatch

@pytest.mark.asyncio
class TestCellRestartAfterDispatchBeforeReceipt:
    """The gateway dispatched the work, then died. The retry must not dispatch again."""

    async def test_the_retry_gets_the_mission_already_open(self, store):
        service = MissionService(store)
        link = CommandMissionLink(service)
        request = CommandRequest(
            command_id="cmd-42", idempotency_key="k", device_id="d",
            issued_at_unix=1, signature="s", text="halt trading",
            principal_type=PrincipalType.OWNER_DEVICE,
            origin_channel=OriginChannel.VOICE, action_class=ActionClass.A4,
        )
        first = await link.open(
            request, effective_action_class=ActionClass.A4, owner_approved=True,
        )
        second = await link.open(
            request, effective_action_class=ActionClass.A4, owner_approved=True,
        )
        assert second.mission_id == first.mission_id
        rows = await store.fetchall("SELECT mission_id FROM missions")
        assert len(rows) == 1

    async def test_retaking_a_claim_does_not_open_a_second_mission(self, store):
        """The two halves together: the claim is recoverable and the work is not repeated.

        Retaking a claim is not a promise that nothing happened. It is a statement that
        whoever held it is not coming back, and the layer below has to be idempotent for
        that to be safe.
        """
        idempotency = IdempotencyService(store)
        service = MissionService(store)
        link = CommandMissionLink(service)
        request = CommandRequest(
            command_id="cmd-43", idempotency_key="k2", device_id="d",
            issued_at_unix=1, signature="s", text="halt trading",
            principal_type=PrincipalType.OWNER_DEVICE,
            origin_channel=OriginChannel.VOICE, action_class=ActionClass.A4,
        )
        await idempotency.begin("k2", PAYLOAD)
        first = await link.open(
            request, effective_action_class=ActionClass.A4, owner_approved=True,
        )
        # crash here
        await _age_claim(store, "k2", STALE_CLAIM_SECONDS + 1)
        assert await idempotency.begin("k2", PAYLOAD) is None
        second = await link.open(
            request, effective_action_class=ActionClass.A4, owner_approved=True,
        )
        assert second.mission_id == first.mission_id


# --------------------------------------- cell 3: connectivity lost before receipt

@pytest.mark.asyncio
class TestCellConnectivityLostAfterMutation:
    """VAN handed the work out and never heard back."""

    async def test_a_mission_with_no_word_back_expires_rather_than_working_forever(self, store):
        service = MissionService(store)
        mission = await service.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
            authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A2),
        )
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING):
            mission = await service.transition(mission.mission_id, target=target)
        await service.set_deadline(mission.mission_id, int(time.time() * 1000) - 1)

        assert await service.expire_overdue() == [mission.mission_id]
        assert (await service.get(mission.mission_id)).state is MissionState.EXPIRED

    async def test_a_mission_still_inside_its_deadline_is_left_alone(self, store):
        """Expiring early would tell the owner the work failed while it is running."""
        service = MissionService(store)
        mission = await service.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING):
            mission = await service.transition(mission.mission_id, target=target)
        await service.set_deadline(mission.mission_id, int(time.time() * 1000) + 60_000)
        assert await service.expire_overdue() == []

    async def test_an_expired_mission_is_not_a_verified_success(self, store):
        """The point of expiring: it is terminal and it is not success."""
        service = MissionService(store)
        mission = await service.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING):
            mission = await service.transition(mission.mission_id, target=target)
        await service.set_deadline(mission.mission_id, int(time.time() * 1000) - 1)
        await service.expire_overdue()
        with pytest.raises(MissionError, match="MISSION_TERMINAL"):
            await service.transition(
                mission.mission_id, target=MissionState.VERIFIED_SUCCESS,
            )


# ------------------------------------------------- cell 4: duplicate callbacks

@pytest.mark.asyncio
class TestCellDuplicateProviderCallback:
    """A provider delivers the same callback twice, which every provider eventually does."""

    async def test_a_second_transition_to_the_same_terminal_state_is_refused(self, store):
        service = MissionService(store)
        mission = await service.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING,
                       MissionState.FAILED):
            mission = await service.transition(mission.mission_id, target=target)
        # MISSION_TERMINAL, not MISSION_ILLEGAL_TRANSITION. Both refuse, and an operator
        # reading the second would go looking for a state-machine bug rather than seeing
        # that the provider delivered twice. The transition table would refuse this on its
        # own, so without asserting the code the terminal guard is untested.
        with pytest.raises(MissionError, match="MISSION_TERMINAL"):
            await service.transition(mission.mission_id, target=MissionState.FAILED)

    async def test_a_duplicate_non_terminal_callback_is_refused(self, store):
        """The cell the terminal-state check does not cover.

        A provider re-delivering "started" lands on a mission that is already RUNNING and
        is not terminal, so the refusal has to come from the transition table rather than
        from the terminal guard. Writing only the terminal case left this one resting on a
        check that happens to fire first — which a mutation of the transition table shows
        by surviving.
        """
        service = MissionService(store)
        mission = await service.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING):
            mission = await service.transition(mission.mission_id, target=target)
        assert mission.state is MissionState.RUNNING
        with pytest.raises(MissionError, match="ILLEGAL_TRANSITION"):
            await service.transition(mission.mission_id, target=MissionState.RUNNING)
        with pytest.raises(MissionError, match="ILLEGAL_TRANSITION"):
            await service.transition(mission.mission_id, target=MissionState.AUTHORIZED)
        assert (await service.get(mission.mission_id)).state is MissionState.RUNNING

    async def test_a_racing_writer_with_a_stale_expectation_is_refused(self, store):
        """Two callbacks arriving together, each believing it saw the current state.

        Without the precondition one silently clobbers the other, and the mission ends up
        in whichever state lost the race — which is the worst possible outcome, because
        both writers think they succeeded.
        """
        service = MissionService(store)
        mission = await service.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        mission = await service.transition(mission.mission_id, target=MissionState.UNDERSTOOD)
        mission = await service.transition(mission.mission_id, target=MissionState.PLANNED)
        with pytest.raises(MissionError, match="PRECONDITION_FAILED"):
            await service.transition(
                mission.mission_id, target=MissionState.AUTHORIZED,
                expected=MissionState.UNDERSTOOD,
            )

    async def test_a_duplicate_callback_does_not_add_a_second_outcome(self, store):
        """A learning store that counted the same mission twice would weigh one run as two."""
        from van_gateway.learning.feed import LearningFeed

        feed = LearningFeed(store)
        service = MissionService(store, learning=feed)
        mission = await service.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING,
                       MissionState.FAILED):
            mission = await service.transition(mission.mission_id, target=target)
        # The provider calls back again; the transition is refused, so nothing is recorded
        # a second time either.
        with pytest.raises(MissionError, match="MISSION_TERMINAL"):
            await service.transition(mission.mission_id, target=MissionState.FAILED)
        rows = await store.fetchall(
            "SELECT * FROM learning_outcomes WHERE mission_id = ?", (mission.mission_id,)
        )
        assert len(rows) == 1

    async def test_replaying_an_outcome_row_overwrites_rather_than_duplicates(self, store):
        """The row is keyed on the mission, so even a direct replay cannot double-count."""
        from van_gateway.learning.feed import LearningFeed

        feed = LearningFeed(store)
        for _ in range(3):
            await feed.record_mission_outcome(
                mission_id="m-1", state=MissionState.FAILED, goal="g",
            )
        rows = await store.fetchall("SELECT * FROM learning_outcomes WHERE mission_id = 'm-1'")
        assert len(rows) == 1


# ------------------------------------------- cell 5: approval outliving its asker

@pytest.mark.asyncio
class TestCellProcessDeathWhileAwaitingApproval:
    """The phone dies between VAN issuing an A4 challenge and the owner signing it.

    The property that matters is that the challenge's validity is a function of time and
    of what it is bound to, never of a session either side happens to be holding. A
    challenge that survived because a process was still running would be a challenge the
    owner could be walked back to hours later.
    """

    @staticmethod
    def _device():
        from cryptography.hazmat.primitives.asymmetric import ec

        return ec.generate_private_key(ec.SECP256R1())

    async def _enrol(self, store, key, device_id="d-1"):
        from cryptography.hazmat.primitives import serialization

        pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        await store.execute(
            "INSERT INTO devices(device_id, public_key_pem, enrolled_at_unix) "
            "VALUES (?, ?, ?)",
            (device_id, pem, int(time.time())),
        )

    @staticmethod
    def _sign(key, canonical: str) -> str:
        import base64

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec

        return base64.b64encode(
            key.sign(canonical.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        ).decode()

    async def _challenge(self, store, *, now_unix, ttl_seconds=120):
        from van_gateway.approval.service import OwnerApprovalService

        service = OwnerApprovalService(store)
        challenge = await service.issue(
            device_id="d-1", source_command_id="cmd-1", turn_id=None,
            action_id="trading.halt", text="halt trading", project_id=None,
            ttl_seconds=ttl_seconds, now_unix=now_unix,
        )
        return service, challenge

    async def test_a_challenge_survives_the_process_that_asked_for_it(self, store):
        """It lives in the database, so a restart does not invalidate the owner's decision."""
        key = self._device()
        await self._enrol(store, key)
        now = int(time.time())
        _, challenge = await self._challenge(store, now_unix=now)

        # A completely new service instance: nothing in memory carried over.
        from van_gateway.approval.service import OwnerApprovalService

        await OwnerApprovalService(store).verify_and_consume(
            challenge_id=challenge.challenge_id, source_command_id="cmd-1",
            signature_b64=self._sign(key, challenge.canonical), device_id="d-1",
            turn_id=None, action_id="trading.halt", text="halt trading",
            project_id=None, now_unix=now + 1,
        )

    async def test_a_challenge_expires_on_the_clock_not_on_the_session(self, store):
        from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService

        key = self._device()
        await self._enrol(store, key)
        now = int(time.time())
        _, challenge = await self._challenge(store, now_unix=now, ttl_seconds=30)
        with pytest.raises(OwnerApprovalError, match="expired"):
            await OwnerApprovalService(store).verify_and_consume(
                challenge_id=challenge.challenge_id, source_command_id="cmd-1",
                signature_b64=self._sign(key, challenge.canonical), device_id="d-1",
                turn_id=None, action_id="trading.halt", text="halt trading",
                project_id=None, now_unix=now + 31,
            )

    async def test_an_expired_challenge_is_removed_rather_than_left_to_be_retried(self, store):
        from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService

        key = self._device()
        await self._enrol(store, key)
        now = int(time.time())
        service, challenge = await self._challenge(store, now_unix=now, ttl_seconds=30)
        signature = self._sign(key, challenge.canonical)
        with pytest.raises(OwnerApprovalError, match="expired"):
            await service.verify_and_consume(
                challenge_id=challenge.challenge_id, source_command_id="cmd-1",
                signature_b64=signature, device_id="d-1", turn_id=None,
                action_id="trading.halt", text="halt trading", project_id=None,
                now_unix=now + 31,
            )
        # Second attempt: gone, not merely expired. An expired row left behind is a row an
        # implementation bug could later read as valid.
        with pytest.raises(OwnerApprovalError, match="unknown_or_consumed"):
            await service.verify_and_consume(
                challenge_id=challenge.challenge_id, source_command_id="cmd-1",
                signature_b64=signature, device_id="d-1", turn_id=None,
                action_id="trading.halt", text="halt trading", project_id=None,
                now_unix=now + 31,
            )

    async def test_a_challenge_is_consumed_once_even_across_restarts(self, store):
        """The duplicate-delivery case on the approval path: the owner taps twice, or the
        phone retries after the reply was lost."""
        from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService

        key = self._device()
        await self._enrol(store, key)
        now = int(time.time())
        _, challenge = await self._challenge(store, now_unix=now)
        signature = self._sign(key, challenge.canonical)
        await OwnerApprovalService(store).verify_and_consume(
            challenge_id=challenge.challenge_id, source_command_id="cmd-1",
            signature_b64=signature, device_id="d-1", turn_id=None,
            action_id="trading.halt", text="halt trading", project_id=None,
            now_unix=now + 1,
        )
        with pytest.raises(OwnerApprovalError, match="unknown_or_consumed"):
            await OwnerApprovalService(store).verify_and_consume(
                challenge_id=challenge.challenge_id, source_command_id="cmd-1",
                signature_b64=signature, device_id="d-1", turn_id=None,
                action_id="trading.halt", text="halt trading", project_id=None,
                now_unix=now + 2,
            )

    async def test_a_device_revoked_while_the_approval_was_pending_cannot_approve(self, store):
        """The revocation window. The owner lost the phone between the prompt and the tap."""
        from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService

        key = self._device()
        await self._enrol(store, key)
        now = int(time.time())
        _, challenge = await self._challenge(store, now_unix=now)
        await store.execute(
            "UPDATE devices SET revoked_at_unix = ? WHERE device_id = ?", (now, "d-1")
        )
        with pytest.raises(OwnerApprovalError, match="revoked"):
            await OwnerApprovalService(store).verify_and_consume(
                challenge_id=challenge.challenge_id, source_command_id="cmd-1",
                signature_b64=self._sign(key, challenge.canonical), device_id="d-1",
                turn_id=None, action_id="trading.halt", text="halt trading",
                project_id=None, now_unix=now + 1,
            )


# ----------------------------------- cell 6: the world changes while approval waits

@pytest.mark.asyncio
class TestCellTradingStateChangesWhileApprovalIsPending:
    """VATI halts between VAN asking the owner and the owner answering.

    The honest statement of the boundary, rather than a gate the gateway does not have:
    an approval proves the owner asked for *this* action on *this* device. Whether the
    world still permits it is VATI's decision, because VATI is the risk authority and
    neither the gateway nor Hermes ever places an order. A gateway that tried to
    re-evaluate trading state at approval time would be a second risk authority, and two
    risk authorities is worse than one.
    """

    async def test_the_approval_binds_to_the_intent_not_to_the_world(self, store):
        from van_gateway.approval.service import OwnerApprovalService

        service = OwnerApprovalService(store)
        first = service.intent_digest(
            device_id="d-1", action_id="trading.halt", text="halt trading", project_id=None,
        )
        # Nothing about market or ledger state is in the digest, and that is deliberate.
        second = service.intent_digest(
            device_id="d-1", action_id="trading.halt", text="halt trading", project_id=None,
        )
        assert first == second

    async def test_a_different_intent_cannot_reuse_the_approval(self, store):
        """What the binding does protect: the approval the owner gave is the approval that
        is used, so a change of action between prompt and tap is refused."""
        from van_gateway.approval.service import OwnerApprovalService

        service = OwnerApprovalService(store)
        halt = service.intent_digest(
            device_id="d-1", action_id="trading.halt", text="halt trading", project_id=None,
        )
        resume = service.intent_digest(
            device_id="d-1", action_id="trading.halt", text="resume trading", project_id=None,
        )
        assert halt != resume

    async def test_the_gateway_never_places_an_order(self, store):
        """The invariant that makes the boundary above the right one."""
        from van_gateway.trading.service import TradingService

        surface = {
            name for name in dir(TradingService)
            if not name.startswith("_") and callable(getattr(TradingService, name))
        }
        forbidden = {"place_order", "submit_order", "send_order", "execute_trade", "buy", "sell"}
        assert surface & forbidden == set()
