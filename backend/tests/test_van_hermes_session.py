"""Rev 1.5 §§0B, 20 — the durable logical session.

Everything here is about a claim that is easy to make and hard to keep: that VAN's features
depend on a session rather than on a socket. The tests are therefore mostly failures —
a path dying, a frame arriving late from a path that has been retired, a command resubmitted
after an acknowledgement was lost, and two carriers over one ingress being described as
redundancy.

The last one is the one §0B calls out by name. `MULTIPATH_HEALTHY` while both carriers share
a route would tell the owner they are covered for the failure that is actually going to
happen, and the honest status is the unflattering one.
"""

from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.session.models import (
    CommandAdmission,
    Direction,
    PROTOCOL_VERSION,
    PathClass,
    PathHealth,
    ResumeRequest,
    SessionEnvelope,
    SessionState,
    SupervisorState,
    TransportPathDescriptor,
)
from van_gateway.session.router import (
    REJECT_CONFLICT,
    REJECT_EXPIRED,
    REJECT_UNKNOWN_KIND,
    RoutedResult,
    SessionDelegates,
    SessionRouter,
)
from van_gateway.session.service import (
    REJECT_PAYLOAD_DIGEST_MISMATCH,
    REJECT_STALE_PATH_EPOCH,
    REJECT_STALE_SESSION_EPOCH,
    REJECT_WRONG_DEVICE,
    SessionError,
    VanHermesSessionService,
)

DEVICE = "android-owner"


def _path(path_id="primary", route_id="oracle-ingress", cls=PathClass.A_REALTIME):
    return TransportPathDescriptor(
        path_id=path_id, path_class=cls, protocol="WSS",
        endpoint="/v1/session/ws", route_id=route_id,
    )


def _envelope(session, path_epoch, **kwargs):
    base = dict(
        protocol_version=PROTOCOL_VERSION,
        message_id=f"msg_{kwargs.get('message_id_suffix', '1')}",
        van_session_id=session.van_session_id,
        session_epoch=session.session_epoch,
        path_epoch=path_epoch,
        device_id=DEVICE,
        direction=Direction.UPSTREAM,
        kind="command.submit",
        created_at_ms=1_000,
        payload={"text": "what is on my calendar"},
    )
    base.pop("message_id_suffix", None)
    kwargs.pop("message_id_suffix", None)
    base.update(kwargs)
    return SessionEnvelope(**base)


async def _service(tmp_path):
    store = await make_store(tmp_path)
    return VanHermesSessionService(store), store


# --------------------------------------------------------------------------- identity


@pytest.mark.asyncio
class TestSessionIdentity:
    async def test_a_session_outlives_the_path_that_opened_it(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, first_epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)

        result = await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id,
                session_epoch=session.session_epoch,
                device_id=DEVICE, last_event_seq=42,
            ),
            path=_path("fallback", "alt-ingress", PathClass.B_STREAMING),
            now_ms=2_000,
        )
        assert result.accepted
        # The identity every feature binds to is unchanged; only the carrier moved.
        assert result.session_epoch == session.session_epoch
        assert result.new_path_epoch > first_epoch

    async def test_the_client_replays_from_the_event_after_the_one_it_holds(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, _ = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        result = await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1,
                device_id=DEVICE, last_event_seq=18_430,
            ),
            now_ms=2_000,
        )
        assert result.replay_from_seq == 18_431

    async def test_another_device_cannot_resume_this_session(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, _ = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        result = await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1,
                device_id="someone-elses-phone",
            ),
            now_ms=2_000,
        )
        assert result.accepted is False
        assert result.refusal == REJECT_WRONG_DEVICE

    async def test_an_older_session_epoch_cannot_be_resurrected(self, tmp_path):
        """A client resuming an older epoch has missed a deliberate invalidation."""
        service, _ = await _service(tmp_path)
        session, _ = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        result = await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id,
                session_epoch=session.session_epoch - 1, device_id=DEVICE,
            ),
            now_ms=2_000,
        )
        assert result.refusal == REJECT_STALE_SESSION_EPOCH

    async def test_a_closed_session_does_not_resume(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, _ = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await service.close(session.van_session_id, now_ms=1_500)
        result = await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE
            ),
            now_ms=2_000,
        )
        assert result.accepted is False


# --------------------------------------------------------------------------- the fence


@pytest.mark.asyncio
class TestPathEpochFencing:
    async def test_the_current_path_may_do_work(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        accepted = await service.accept_upstream(_envelope(session, epoch))
        assert accepted.van_session_id == session.van_session_id

    async def test_a_frame_from_a_retired_path_cannot_become_a_command(self, tmp_path):
        """§20.10 step 9, which is the whole reason a failover is a transaction.

        Without this, a delayed envelope from the dying path arrives after the owner has
        been told the command failed, and does it again.
        """
        service, _ = await _service(tmp_path)
        session, old_epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE
            ),
            path=_path("fallback", "alt-ingress"), now_ms=2_000,
        )
        with pytest.raises(SessionError) as caught:
            await service.accept_upstream(_envelope(session, old_epoch))
        assert caught.value.reason == REJECT_STALE_PATH_EPOCH

    async def test_a_downstream_envelope_is_not_fenced_by_the_path_epoch(self, tmp_path):
        """§20.9 — downstream duplicates are safe because events de-duplicate by id.

        Fencing them would drop legitimate traffic from a warm standby while it is being
        promoted, which is the moment continuity matters most.
        """
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE
            ),
            now_ms=2_000,
        )
        downstream = _envelope(
            session, epoch, direction=Direction.DOWNSTREAM, kind="event.delivery"
        )
        assert await service.accept_upstream(downstream) is not None

    async def test_an_envelope_carrying_an_old_session_epoch_is_refused(self, tmp_path):
        """The session-epoch check on the envelope, not on resume.

        A first pass tested this only through `resume`, so deleting the check in
        `accept_upstream` changed nothing — the two live in different places and only one
        was driven. A client that kept a socket open across a deliberate invalidation is
        exactly the case the envelope check exists for: it never calls resume at all.
        """
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        with pytest.raises(SessionError) as caught:
            await service.accept_upstream(
                _envelope(session, epoch, session_epoch=session.session_epoch + 1)
            )
        assert caught.value.reason == REJECT_STALE_SESSION_EPOCH

    async def test_a_protocol_version_mismatch_is_refused(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        with pytest.raises(SessionError):
            await service.accept_upstream(
                _envelope(session, epoch, protocol_version=PROTOCOL_VERSION + 1)
            )


# --------------------------------------------------------------------------- once-ness


@pytest.mark.asyncio
class TestEffectivelyOnce:
    async def test_a_new_key_is_admitted(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        admission, existing = await service.admit(
            _envelope(session, epoch, idempotency_key="k1")
        )
        assert admission is CommandAdmission.ADMITTED
        assert existing is None

    async def test_the_same_key_and_payload_returns_the_first_result(self, tmp_path):
        """§20.12 — the client lost the acknowledgement, not the command."""
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        first = _envelope(session, epoch, idempotency_key="k1")
        await service.admit(first)
        await service.record_result(first, {"command_id": "cmd_1", "status": "accepted"})

        # The retry arrives on the same path epoch; what it lost was the acknowledgement.
        retry = _envelope(session, epoch, idempotency_key="k1", message_id="msg_retry")
        admission, existing = await service.admit(retry)
        assert admission is CommandAdmission.ALREADY_KNOWN
        assert existing == {"command_id": "cmd_1", "status": "accepted"}

    async def test_the_same_key_with_a_different_payload_is_a_conflict(self, tmp_path):
        """One of the two is not what the owner asked for, and nothing here can tell which."""
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await service.admit(_envelope(session, epoch, idempotency_key="k1"))
        admission, _ = await service.admit(
            _envelope(
                session, epoch, idempotency_key="k1", message_id="msg_2",
                payload={"text": "transfer the money"},
            )
        )
        assert admission is CommandAdmission.CONFLICT

    async def test_a_conflicting_payload_leaves_no_trace_that_could_be_mistaken_for_accepted(
        self, tmp_path
    ):
        service, store = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await service.admit(_envelope(session, epoch, idempotency_key="k1"))
        await service.admit(
            _envelope(
                session, epoch, idempotency_key="k1", message_id="msg_conflict",
                payload={"text": "something else"},
            )
        )
        rows = await store.fetchall(
            "SELECT message_id FROM van_session_messages WHERE van_session_id = ?",
            (session.van_session_id,),
        )
        assert [r["message_id"] for r in rows] == ["msg_1"]

    async def test_a_payload_that_does_not_match_its_own_digest_is_refused(self, tmp_path):
        """The envelope must not be able to vouch for its own payload.

        The first version of `admit` read `envelope.payload_digest or envelope.digest()`,
        so a client could send payload A carrying B's digest and have the pair recorded
        under B's fingerprint. The immediate effect is mild — A does not execute — but the
        stored digest is then wrong, and the *real* B arriving later is treated as a
        duplicate and silently never runs. A command the owner sent, was acknowledged, and
        which never happened is precisely what this table exists to prevent.
        """
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        first = _envelope(session, epoch, idempotency_key="k1")
        await service.admit(first)

        forged = _envelope(
            session, epoch, idempotency_key="k1", message_id="msg_forged",
            payload={"text": "delete everything"},
            payload_digest=first.digest(),
        )
        with pytest.raises(SessionError) as caught:
            await service.admit(forged)
        assert caught.value.reason == REJECT_PAYLOAD_DIGEST_MISMATCH

    async def test_a_matching_digest_from_the_client_is_accepted(self, tmp_path):
        """The cross-check must not refuse an honest client that sends its own digest."""
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        honest = _envelope(session, epoch, idempotency_key="k1")
        admission, _ = await service.admit(
            _envelope(
                session, epoch, idempotency_key="k1", payload_digest=honest.digest()
            )
        )
        assert admission is CommandAdmission.ADMITTED


# --------------------------------------------------------------------------- continuity


@pytest.mark.asyncio
class TestHonestContinuity:
    async def test_two_carriers_on_one_route_are_not_route_diversity(self, tmp_path):
        """§0B — the flattering status is the wrong one."""
        service, _ = await _service(tmp_path)
        session, _ = await service.open(
            device_id=DEVICE, path=_path("primary", "oracle-ingress"), now_ms=1_000
        )
        await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE
            ),
            # Same route_id, different protocol: protocol diversity only.
            path=_path("fallback", "oracle-ingress", PathClass.B_STREAMING),
            now_ms=2_000,
        )
        state, reason = await service.continuity(session.van_session_id)
        assert state is SupervisorState.SINGLE_PATH
        assert "protocol diversity" in reason

    async def test_two_independent_routes_are_multipath(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, _ = await service.open(
            device_id=DEVICE, path=_path("primary", "oracle-ingress"), now_ms=1_000
        )
        await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE
            ),
            path=_path("fallback", "alternate-relay", PathClass.B_STREAMING),
            now_ms=2_000,
        )
        state, reason = await service.continuity(session.van_session_id)
        assert state is SupervisorState.MULTIPATH_HEALTHY
        assert "2 independent routes" in reason

    async def test_a_failed_path_does_not_count_towards_redundancy(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, first = await service.open(
            device_id=DEVICE, path=_path("primary", "oracle-ingress"), now_ms=1_000
        )
        resumed = await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE
            ),
            path=_path("fallback", "alternate-relay"), now_ms=2_000,
        )
        await service.mark_path_health(
            session.van_session_id, first, PathHealth.FAILED, now_ms=2_100
        )
        state, _ = await service.continuity(session.van_session_id)
        assert state is SupervisorState.SINGLE_PATH

    async def test_no_usable_path_is_reported_as_offline_rather_than_degraded(self, tmp_path):
        service, _ = await _service(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await service.mark_path_health(
            session.van_session_id, epoch, PathHealth.FAILED, now_ms=2_000
        )
        state, _ = await service.continuity(session.van_session_id)
        assert state is SupervisorState.OFFLINE_LOCAL


# --------------------------------------------------------------------------- the router


@pytest.mark.asyncio
class TestSessionRouter:
    async def _router(self, tmp_path, submitted=None):
        service, _ = await _service(tmp_path)

        async def submit(payload, device_id):
            if submitted is not None:
                submitted.append((payload, device_id))
            return {"command_id": "cmd_1", "status": "accepted"}

        return service, SessionRouter(service, SessionDelegates(submit_command=submit))

    async def test_a_command_is_delegated_to_the_existing_authority(self, tmp_path):
        submitted: list = []
        service, router = await self._router(tmp_path, submitted)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        routed = await router.route(_envelope(session, epoch, idempotency_key="k1"))
        assert routed.accepted
        assert submitted == [({"text": "what is on my calendar"}, DEVICE)]

    async def test_a_resubmission_does_not_execute_twice(self, tmp_path):
        submitted: list = []
        service, router = await self._router(tmp_path, submitted)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await router.route(_envelope(session, epoch, idempotency_key="k1"))
        again = await router.route(
            _envelope(session, epoch, idempotency_key="k1", message_id="msg_again")
        )
        assert again.accepted
        assert again.admission is CommandAdmission.ALREADY_KNOWN
        assert len(submitted) == 1, "the command ran twice after a lost acknowledgement"

    async def test_a_conflicting_resubmission_executes_nothing(self, tmp_path):
        submitted: list = []
        service, router = await self._router(tmp_path, submitted)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await router.route(_envelope(session, epoch, idempotency_key="k1"))
        conflicting = await router.route(
            _envelope(
                session, epoch, idempotency_key="k1", message_id="msg_c",
                payload={"text": "pay the invoice"},
            )
        )
        assert conflicting.accepted is False
        assert conflicting.refusal == REJECT_CONFLICT
        assert len(submitted) == 1

    async def test_an_unknown_kind_is_refused_rather_than_interpreted(self, tmp_path):
        """A permissive default here would be a second ingress into the command path."""
        service, router = await self._router(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        routed = await router.route(_envelope(session, epoch, kind="command.run_shell"))
        assert routed.accepted is False
        assert routed.refusal == REJECT_UNKNOWN_KIND

    async def test_an_unknown_kind_does_not_consume_an_idempotency_key(self, tmp_path):
        """Why the kind is checked before admission rather than after.

        A second refusal exists further down, where the delegate lookup fails, so deleting
        the early check refuses the same message and every test still passed. The
        difference only shows when the unknown kind carries an idempotency key: refused
        late, the key has already been recorded, and the owner's *real* command arriving
        under it is then answered ALREADY_KNOWN and silently never runs.
        """
        service, router = await self._router(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        refused = await router.route(
            _envelope(session, epoch, kind="command.run_shell", idempotency_key="k1")
        )
        assert refused.accepted is False

        admission, _ = await service.admit(
            _envelope(session, epoch, idempotency_key="k1", message_id="msg_real")
        )
        assert admission is CommandAdmission.ADMITTED, (
            "a refused message burned the key its replacement needed"
        )

    async def test_an_expired_envelope_is_not_executed_late(self, tmp_path):
        """§20.14 — a command worth doing twenty minutes ago may not be worth doing now."""
        service, router = await self._router(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        routed = await router.route(
            _envelope(session, epoch, expires_at_ms=5_000), now_ms=6_000
        )
        assert routed.accepted is False
        assert routed.refusal == REJECT_EXPIRED

    async def test_a_heartbeat_does_not_occupy_an_idempotency_key(self, tmp_path):
        service, router = await self._router(tmp_path)
        session, epoch = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        routed = await router.route(
            _envelope(session, epoch, kind="session.heartbeat", idempotency_key="k1")
        )
        assert routed.accepted
        # The key is still free for the command that follows.
        admission, _ = await service.admit(
            _envelope(session, epoch, idempotency_key="k1", message_id="msg_cmd")
        )
        assert admission is CommandAdmission.ADMITTED

    async def test_a_stale_path_epoch_is_refused_at_the_router(self, tmp_path):
        service, router = await self._router(tmp_path)
        session, old = await service.open(device_id=DEVICE, path=_path(), now_ms=1_000)
        await service.resume(
            ResumeRequest(
                van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE
            ),
            now_ms=2_000,
        )
        routed = await router.route(_envelope(session, old, idempotency_key="k9"))
        assert routed.accepted is False
        assert routed.refusal == REJECT_STALE_PATH_EPOCH
