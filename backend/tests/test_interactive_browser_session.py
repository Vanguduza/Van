"""Rev 1.5 §§5.1-5.6 — the interactive browser session, its leases and its grants.

Three claims in this layer would each be invisible from outside if they were false, and each
is the kind of thing the audit found being asserted in prose:

* **exactly one control holder.** A generation that is not enforced by a unique index is a
  number two callers can both believe they hold.
* **actuation stops at lease expiry.** §0E.1 D7 gives a 30-second grace for cleanup and
  reconnect, and the failure mode is a grace that quietly extends the right to act.
* **a stale viewport is refused, never transformed.** A transform turns a stale tap into a
  confident wrong tap, which looks exactly like a working browser.

The grant tests deliberately include the attacks rather than only the happy path: `alg: none`,
an unknown `kid`, a tampered claim, a replayed nonce and a rotated-out key.
"""

from __future__ import annotations

import base64
import json

import pytest

from conftest_automation import make_store
from van_gateway.browser.control_lease import ControlLeaseError, ControlLeaseService
from van_gateway.browser.interactive_models import (
    BrowserControlHolder,
    InteractiveSessionState,
    ProfileLeaseHolderKind,
    Viewport,
    may_transition,
)
from van_gateway.browser.interactive_service import (
    InteractiveSessionError,
    InteractiveSessionService,
)
from van_gateway.browser.policy import BrowserPolicyError
from van_gateway.browser.service import BrowserSessionBroker
from van_gateway.browser.stream_grants import (
    GRANT_AUDIENCE,
    StreamGrantError,
    StreamGrantService,
    StreamGrantSigner,
    StreamGrantVerifier,
    generate_signing_key,
)
from van_gateway.events.bus import EventBus
from van_gateway.storage.db import SCHEMA_VERSION

DEVICE = "android-owner"
VIEWPORT = Viewport(width=1080, height=2016, device_scale_factor=1.0)


async def _stack(tmp_path):
    store = await make_store(tmp_path)
    broker = BrowserSessionBroker(store)
    await broker.register_profile(profile_alias="public_research")
    await broker.register_profile(profile_alias="authenticated_owner")
    control = ControlLeaseService(store)
    events = EventBus(store)
    service = InteractiveSessionService(store, broker, control, events)
    return store, broker, control, service, events


async def _session(tmp_path, **kwargs):
    store, broker, control, service, events = await _stack(tmp_path)
    session = await service.create(
        owner_device_id=DEVICE, profile_alias="authenticated_owner",
        viewport=VIEWPORT, now_ms=1_000, **kwargs,
    )
    return store, broker, control, service, events, session


# --------------------------------------------------------------------------- migration


class TestMigration27:
    @pytest.mark.asyncio
    async def test_the_schema_reaches_the_version_the_code_claims(self, tmp_path):
        """The rule, not the number.

        This asserted `== 27` and failed the moment migration 28 landed, which is a test
        pinning a snapshot rather than an invariant: what matters is that a fresh database
        reaches whatever version the code believes it is at, and that migration 27's tables
        are among what it got.
        """
        store = await make_store(tmp_path)
        row = await store.fetchone("SELECT MAX(version) AS v FROM schema_migrations")
        assert int(row["v"]) == SCHEMA_VERSION
        assert SCHEMA_VERSION >= 27, "migration 27 is the Remote Browser floor"
        tables = {
            r["name"]
            for r in await store.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"browser_interactive_sessions", "browser_control_leases",
                "browser_stream_grants"} <= tables

    @pytest.mark.asyncio
    async def test_the_events_table_is_extended_rather_than_replaced(self, tmp_path):
        store = await make_store(tmp_path)
        columns = {r["name"] for r in await store.fetchall("PRAGMA table_info(events)")}
        # The originals, still there. §5.6's whole point is that this is additive.
        assert {"seq", "event_type", "payload_json", "created_at_unix"} <= columns
        assert {"event_id", "target_device_id", "occurred_at_ms", "mission_id",
                "command_id", "correlation_id"} <= columns

    @pytest.mark.asyncio
    async def test_a_pre_migration_row_gets_a_deterministic_identity(self, tmp_path):
        """A client that de-duplicates on event_id must not meet a wall of NULLs."""
        store = await make_store(tmp_path)
        # Simulate a row written before the migration, then re-run the backfill statement.
        await store.execute(
            "INSERT INTO events(event_type, payload_json, created_at_unix) VALUES (?, ?, ?)",
            ("legacy.thing", "{}", 1_700_000_000),
        )
        await store.execute(
            "UPDATE events SET event_id = 'legacy-event:' || seq, "
            "occurred_at_ms = created_at_unix * 1000 WHERE event_id IS NULL"
        )
        row = await store.fetchone(
            "SELECT seq, event_id, occurred_at_ms, target_device_id FROM events "
            "WHERE event_type = 'legacy.thing'"
        )
        assert row["event_id"] == f"legacy-event:{row['seq']}"
        assert int(row["occurred_at_ms"]) == 1_700_000_000_000
        # NULL means broadcast, which is the semantics those rows already had.
        assert row["target_device_id"] is None


# --------------------------------------------------------------------------- profile lease


class TestRenewableProfileLease:
    @pytest.mark.asyncio
    async def test_a_session_lease_records_its_holder_kind(self, tmp_path):
        _, broker, *_ = await _stack(tmp_path)
        lease = await broker.acquire_lease(
            profile_alias="public_research",
            holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION,
            holder_id="ibs_1", now_ms=1_000,
        )
        assert lease.holder_kind is ProfileLeaseHolderKind.INTERACTIVE_SESSION
        assert lease.holder_id == "ibs_1"
        # §5.3's compatibility mapping: an interactive lease carries no task_id.
        assert lease.task_id is None

    @pytest.mark.asyncio
    async def test_an_existing_task_lease_is_unchanged(self, tmp_path):
        _, broker, *_ = await _stack(tmp_path)
        lease = await broker.acquire_lease(
            profile_alias="public_research", task_id="btask_1", now_ms=1_000
        )
        assert lease.holder_kind is ProfileLeaseHolderKind.TASK
        assert lease.task_id == "btask_1" == lease.holder_id

    @pytest.mark.asyncio
    async def test_the_generation_moves_when_the_profile_is_taken_again(self, tmp_path):
        _, broker, *_ = await _stack(tmp_path)
        first = await broker.acquire_lease(
            profile_alias="public_research", holder_id="a",
            holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION, now_ms=1_000,
        )
        second = await broker.acquire_lease(
            profile_alias="public_research", holder_id="b",
            holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION,
            now_ms=first.expires_at_ms + 1,
        )
        assert second.generation == first.generation + 1

    @pytest.mark.asyncio
    async def test_renewal_extends_exclusivity_without_moving_the_fence(self, tmp_path):
        """§5.3 — renewal is not a new authority. If it moved the generation, every
        heartbeat would invalidate the holder's own in-flight work."""
        _, broker, *_ = await _stack(tmp_path)
        lease = await broker.acquire_lease(
            profile_alias="public_research", holder_id="ibs_1",
            holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION, now_ms=1_000,
        )
        renewed = await broker.renew_lease(
            lease_id=lease.lease_id, holder_id="ibs_1",
            generation=lease.generation, now_ms=60_000,
        )
        assert renewed.generation == lease.generation
        assert renewed.expires_at_ms > lease.expires_at_ms

    @pytest.mark.asyncio
    async def test_a_stale_generation_cannot_renew(self, tmp_path):
        _, broker, *_ = await _stack(tmp_path)
        lease = await broker.acquire_lease(
            profile_alias="public_research", holder_id="ibs_1",
            holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION, now_ms=1_000,
        )
        with pytest.raises(BrowserPolicyError, match="not_renewable"):
            await broker.renew_lease(
                lease_id=lease.lease_id, holder_id="ibs_1",
                generation=lease.generation + 5, now_ms=60_000,
            )

    @pytest.mark.asyncio
    async def test_an_expired_lease_cannot_be_renewed_back_to_life(self, tmp_path):
        """Otherwise the 30-second cleanup grace becomes a way to keep acting."""
        _, broker, *_ = await _stack(tmp_path)
        lease = await broker.acquire_lease(
            profile_alias="public_research", holder_id="ibs_1",
            holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION, now_ms=1_000,
        )
        with pytest.raises(BrowserPolicyError, match="not_renewable"):
            await broker.renew_lease(
                lease_id=lease.lease_id, holder_id="ibs_1",
                generation=lease.generation, now_ms=lease.expires_at_ms + 1,
            )

    @pytest.mark.asyncio
    async def test_assert_lease_active_refuses_at_the_expiry_instant(self, tmp_path):
        """§0E.1 D7 — the grace is cleanup and reconnect. It never extends actuation."""
        _, broker, *_ = await _stack(tmp_path)
        lease = await broker.acquire_lease(
            profile_alias="public_research", holder_id="ibs_1",
            holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION, now_ms=1_000,
        )
        await broker.assert_lease_active(
            lease_id=lease.lease_id, holder_id="ibs_1",
            generation=lease.generation, now_ms=lease.expires_at_ms - 1,
        )
        with pytest.raises(BrowserPolicyError, match="lease_expired"):
            await broker.assert_lease_active(
                lease_id=lease.lease_id, holder_id="ibs_1",
                generation=lease.generation, now_ms=lease.expires_at_ms,
            )


# --------------------------------------------------------------------------- control lease


class TestControlLease:
    @pytest.mark.asyncio
    async def test_taking_control_revokes_the_previous_holder(self, tmp_path):
        _, _, control, _, _, session = await _session(tmp_path)
        agent = await control.delegate(
            session_id=session.session_id,
            holder=BrowserControlHolder.HERMES_STAGEHAND,
            issued_for="hermes:van", now_ms=2_000,
        )
        owner = await control.owner_preempt(
            session_id=session.session_id, device_id=DEVICE, now_ms=3_000
        )
        assert owner.generation > agent.generation
        current = await control.current(session.session_id)
        assert current is not None and current.holder is BrowserControlHolder.OWNER

    @pytest.mark.asyncio
    async def test_the_agents_in_flight_input_is_invalid_the_instant_the_owner_touches(
        self, tmp_path
    ):
        """ADR-RB-007 — preemption is not a request the agent may finish its action first.

        This is the test the whole generation mechanism exists for: the agent's packet is
        well-formed, correctly signed for its lease, and refused.
        """
        _, _, control, _, _, session = await _session(tmp_path)
        agent = await control.delegate(
            session_id=session.session_id,
            holder=BrowserControlHolder.HERMES_STAGEHAND,
            issued_for="hermes:van", now_ms=2_000,
        )
        await control.owner_preempt(
            session_id=session.session_id, device_id=DEVICE, now_ms=3_000
        )
        with pytest.raises(ControlLeaseError, match="superseded|stale"):
            await control.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=agent.control_lease_id,
                control_generation=agent.generation,
                now_ms=3_001,
            )

    @pytest.mark.asyncio
    async def test_the_right_lease_with_the_wrong_generation_is_still_refused(self, tmp_path):
        """The generation check, on its own.

        A first version of this suite tested preemption only, where the lease id *and* the
        generation both change — so a mutation deleting the generation comparison survived,
        because the lease-id comparison caught every case the tests drove. Two guards that
        always fire together are one guard, and nobody knows which one.

        A client holding the correct lease id and a stale generation is the case that tells
        them apart: a cached number, a retried packet, or a caller guessing.
        """
        _, _, control, _, _, session = await _session(tmp_path)
        current = await control.current(session.session_id)
        assert current is not None
        with pytest.raises(ControlLeaseError, match="generation_stale"):
            await control.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=current.control_lease_id,
                control_generation=current.generation + 1,
                now_ms=2_000,
            )

    @pytest.mark.asyncio
    async def test_a_fabricated_lease_id_with_the_right_generation_is_refused(self, tmp_path):
        """And the lease-id check, on its own.

        The generation is a small integer, so guessing it is not an achievement: the first
        lease in a session is generation 1. Without this case the lease-id comparison was
        never the reason any test passed, because every scenario that changed one changed
        both.
        """
        _, _, control, _, _, session = await _session(tmp_path)
        current = await control.current(session.session_id)
        assert current is not None
        with pytest.raises(ControlLeaseError, match="superseded"):
            await control.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id="bctl_invented",
                control_generation=current.generation,
                now_ms=2_000,
            )

    @pytest.mark.asyncio
    async def test_an_agent_cannot_delegate_control_onward(self, tmp_path):
        _, _, control, _, _, session = await _session(tmp_path)
        await control.delegate(
            session_id=session.session_id,
            holder=BrowserControlHolder.HERMES_STAGEHAND,
            issued_for="hermes:van", now_ms=2_000,
        )
        with pytest.raises(ControlLeaseError, match="requires_owner_control"):
            await control.delegate(
                session_id=session.session_id,
                holder=BrowserControlHolder.HERMES_DETERMINISTIC,
                issued_for="harness", now_ms=2_500,
            )

    @pytest.mark.asyncio
    async def test_delegation_requires_an_agent_holder(self, tmp_path):
        _, _, control, _, _, session = await _session(tmp_path)
        with pytest.raises(ControlLeaseError, match="requires_an_agent_holder"):
            await control.delegate(
                session_id=session.session_id,
                holder=BrowserControlHolder.SYSTEM_RECOVERY,
                issued_for="recovery", now_ms=2_000,
            )

    @pytest.mark.asyncio
    async def test_a_revoked_session_has_no_control_holder_and_fails_closed(self, tmp_path):
        _, _, control, _, _, session = await _session(tmp_path)
        current = await control.current(session.session_id)
        assert current is not None
        await control.revoke(session_id=session.session_id, reason="test", now_ms=4_000)
        with pytest.raises(ControlLeaseError, match="revoked"):
            await control.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=current.control_lease_id,
                control_generation=current.generation,
                now_ms=4_001,
            )

    @pytest.mark.asyncio
    async def test_an_expired_control_lease_cannot_act(self, tmp_path):
        _, _, control, _, _, session = await _session(tmp_path)
        lease = await control.issue(
            session_id=session.session_id, holder=BrowserControlHolder.HERMES_DETERMINISTIC,
            issued_for="harness", ttl_ms=1_000, now_ms=5_000,
        )
        with pytest.raises(ControlLeaseError, match="expired"):
            await control.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=lease.control_lease_id,
                control_generation=lease.generation,
                now_ms=6_000,
            )

    @pytest.mark.asyncio
    async def test_one_generation_is_issued_once(self, tmp_path):
        """The unique index is the mechanism; this is what it means."""
        store, _, control, _, _, session = await _session(tmp_path)
        await control.issue(
            session_id=session.session_id, holder=BrowserControlHolder.OWNER,
            issued_for=DEVICE, now_ms=2_000,
        )
        rows = await store.fetchall(
            "SELECT generation FROM browser_control_leases WHERE session_id = ?",
            (session.session_id,),
        )
        generations = [int(r["generation"]) for r in rows]
        assert len(generations) == len(set(generations))


# --------------------------------------------------------------------------- stream grants


class TestStreamGrants:
    def _signer(self, kid="browser-stream-signing-2026-01"):
        key = generate_signing_key(kid)
        return key, StreamGrantSigner(key)

    @pytest.mark.asyncio
    async def test_a_minted_grant_verifies_and_carries_its_session(self, tmp_path):
        store, *_ , session = await _session(tmp_path)
        key, signer = self._signer()
        grants = StreamGrantService(store, signer)
        token, claims = await grants.mint(
            session_id=session.session_id, device_id=DEVICE,
            profile_alias="authenticated_owner", scope=["webrtc.signal", "browser.view"],
            max_width=1080, max_height=2400, max_fps=60, now_ms=10_000,
        )
        verified = StreamGrantVerifier({key.kid: key.public_pem()}).verify(token, now_ms=10_500)
        assert verified["session_id"] == session.session_id
        assert verified["aud"] == GRANT_AUDIENCE
        assert verified["nonce"] == claims["nonce"]

    @pytest.mark.asyncio
    async def test_an_unsigned_token_is_refused(self, tmp_path):
        """`alg: none` is the oldest attack on this envelope and needs no key at all."""
        store, *_, session = await _session(tmp_path)
        key, signer = self._signer()
        grants = StreamGrantService(store, signer)
        token, _ = await grants.mint(
            session_id=session.session_id, device_id=DEVICE,
            profile_alias="authenticated_owner", scope=["browser.view"],
            max_width=1080, max_height=2400, max_fps=60, now_ms=10_000,
        )
        _, claims_b64, _ = token.split(".")
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "kid": key.kid}).encode()
        ).rstrip(b"=").decode()
        with pytest.raises(StreamGrantError, match="algorithm_not_accepted"):
            StreamGrantVerifier({key.kid: key.public_pem()}).verify(
                f"{header}.{claims_b64}.", now_ms=10_500
            )

    @pytest.mark.asyncio
    async def test_a_tampered_claim_is_refused(self, tmp_path):
        store, *_, session = await _session(tmp_path)
        key, signer = self._signer()
        grants = StreamGrantService(store, signer)
        token, claims = await grants.mint(
            session_id=session.session_id, device_id=DEVICE,
            profile_alias="public_research", scope=["browser.view"],
            max_width=1080, max_height=2400, max_fps=60, now_ms=10_000,
        )
        header_b64, _, signature = token.split(".")
        forged = dict(claims, profile_alias="authenticated_owner")
        claims_b64 = base64.urlsafe_b64encode(
            json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        with pytest.raises(StreamGrantError, match="signature_invalid"):
            StreamGrantVerifier({key.kid: key.public_pem()}).verify(
                f"{header_b64}.{claims_b64}.{signature}", now_ms=10_500
            )

    @pytest.mark.asyncio
    async def test_an_unknown_kid_is_refused_rather_than_tried_against_every_key(self, tmp_path):
        store, *_, session = await _session(tmp_path)
        key, signer = self._signer("rotated-out")
        grants = StreamGrantService(store, signer)
        token, _ = await grants.mint(
            session_id=session.session_id, device_id=DEVICE,
            profile_alias="public_research", scope=["browser.view"],
            max_width=1080, max_height=2400, max_fps=60, now_ms=10_000,
        )
        current = generate_signing_key("current")
        with pytest.raises(StreamGrantError, match="unknown_kid"):
            StreamGrantVerifier({"current": current.public_pem()}).verify(token, now_ms=10_500)

    @pytest.mark.asyncio
    async def test_rotation_keeps_the_previous_verifier_and_then_stops(self, tmp_path):
        """§5.5 — overlap, then mandatory rejection. Both halves are the requirement."""
        store, *_, session = await _session(tmp_path)
        old_key, old_signer = self._signer("2026-01")
        new_key = generate_signing_key("2026-02")
        grants = StreamGrantService(store, old_signer)
        token, _ = await grants.mint(
            session_id=session.session_id, device_id=DEVICE,
            profile_alias="public_research", scope=["browser.view"],
            max_width=1080, max_height=2400, max_fps=60, now_ms=10_000,
        )
        during_overlap = StreamGrantVerifier(
            {"2026-02": new_key.public_pem(), "2026-01": old_key.public_pem()}
        )
        assert during_overlap.verify(token, now_ms=10_500)["session_id"] == session.session_id

        after_overlap = StreamGrantVerifier({"2026-02": new_key.public_pem()})
        with pytest.raises(StreamGrantError, match="unknown_kid"):
            after_overlap.verify(token, now_ms=10_500)

    @pytest.mark.asyncio
    async def test_an_expired_grant_is_refused(self, tmp_path):
        store, *_, session = await _session(tmp_path)
        key, signer = self._signer()
        grants = StreamGrantService(store, signer)
        token, _ = await grants.mint(
            session_id=session.session_id, device_id=DEVICE,
            profile_alias="public_research", scope=["browser.view"],
            max_width=1080, max_height=2400, max_fps=60, ttl_ms=1_000, now_ms=10_000,
        )
        with pytest.raises(StreamGrantError, match="expired"):
            StreamGrantVerifier({key.kid: key.public_pem()}).verify(token, now_ms=11_001)

    @pytest.mark.asyncio
    async def test_a_grant_is_redeemable_exactly_once(self, tmp_path):
        """The signature says who issued it. Only the nonce row says it has not been used."""
        store, *_, session = await _session(tmp_path)
        _, signer = self._signer()
        grants = StreamGrantService(store, signer)
        _, claims = await grants.mint(
            session_id=session.session_id, device_id=DEVICE,
            profile_alias="public_research", scope=["browser.view"],
            max_width=1080, max_height=2400, max_fps=60, now_ms=10_000,
        )
        assert await grants.redeem(nonce=claims["nonce"], now_ms=10_100) == session.session_id
        with pytest.raises(StreamGrantError, match="not_redeemable"):
            await grants.redeem(nonce=claims["nonce"], now_ms=10_200)

    @pytest.mark.asyncio
    async def test_an_unknown_scope_is_refused_at_minting(self, tmp_path):
        store, *_, session = await _session(tmp_path)
        _, signer = self._signer()
        grants = StreamGrantService(store, signer)
        with pytest.raises(StreamGrantError, match="unknown_scope"):
            await grants.mint(
                session_id=session.session_id, device_id=DEVICE,
                profile_alias="public_research", scope=["browser.everything"],
                max_width=1080, max_height=2400, max_fps=60, now_ms=10_000,
            )


# --------------------------------------------------------------------------- the session


class TestInteractiveSession:
    @pytest.mark.asyncio
    async def test_creating_a_session_takes_the_profile_lease(self, tmp_path):
        store, _, _, _, _, session = await _session(tmp_path)
        row = await store.fetchone(
            "SELECT lease_holder, lease_holder_kind, lease_holder_id FROM browser_profiles "
            "WHERE profile_alias = 'authenticated_owner'"
        )
        assert row["lease_holder"] == session.profile_lease_id
        assert row["lease_holder_kind"] == ProfileLeaseHolderKind.INTERACTIVE_SESSION.value
        assert row["lease_holder_id"] == session.session_id

    @pytest.mark.asyncio
    async def test_a_second_session_cannot_take_a_leased_profile(self, tmp_path):
        _, _, _, service, _, _ = await _session(tmp_path)
        with pytest.raises(InteractiveSessionError, match="leased"):
            await service.create(
                owner_device_id=DEVICE, profile_alias="authenticated_owner",
                viewport=VIEWPORT, now_ms=1_100,
            )

    @pytest.mark.asyncio
    async def test_a_retried_creation_returns_the_same_session(self, tmp_path):
        """§6.1 sends an idempotency key because the phone retries after an ambiguous
        failure. Without this each retry would leak another profile lease."""
        _, _, _, service, _, first = await _session(tmp_path, idempotency_key="key-1")
        second = await service.create(
            owner_device_id=DEVICE, profile_alias="authenticated_owner",
            viewport=VIEWPORT, idempotency_key="key-1", now_ms=1_500,
        )
        assert second.session_id == first.session_id

    @pytest.mark.asyncio
    async def test_an_unknown_profile_alias_is_refused(self, tmp_path):
        """§0A/B3 — an implementation agent may not invent aliases."""
        _, _, _, service, _ = await _stack(tmp_path)
        with pytest.raises(BrowserPolicyError):
            await service.create(
                owner_device_id=DEVICE, profile_alias="dial-development",
                viewport=VIEWPORT, now_ms=1_000,
            )

    @pytest.mark.asyncio
    async def test_a_viewport_larger_than_any_screen_is_refused(self, tmp_path):
        _, _, _, service, _ = await _stack(tmp_path)
        with pytest.raises(InteractiveSessionError, match="viewport_too_large"):
            await service.create(
                owner_device_id=DEVICE, profile_alias="public_research",
                viewport=Viewport(width=16000, height=16000, device_scale_factor=1.0),
                now_ms=1_000,
            )

    @pytest.mark.asyncio
    async def test_the_owner_holds_control_from_the_first_instant(self, tmp_path):
        _, _, control, _, _, session = await _session(tmp_path)
        current = await control.current(session.session_id)
        assert current is not None
        assert current.holder is BrowserControlHolder.OWNER
        assert current.issued_for == DEVICE

    @pytest.mark.asyncio
    async def test_the_state_ladder_refuses_a_skipped_rung(self, tmp_path):
        _, _, _, service, _, session = await _session(tmp_path)
        with pytest.raises(InteractiveSessionError, match="transition_forbidden"):
            await service.transition(
                session_id=session.session_id,
                target=InteractiveSessionState.INTERACTIVE, now_ms=2_000,
            )

    @pytest.mark.asyncio
    async def test_a_terminated_session_cannot_be_revived_or_retro_failed(self, tmp_path):
        """§5.2 — nothing is reachable from a terminal state, in either direction."""
        assert not may_transition(InteractiveSessionState.TERMINATED, InteractiveSessionState.FAILED)
        assert not may_transition(InteractiveSessionState.FAILED, InteractiveSessionState.TERMINATED)
        assert not may_transition(
            InteractiveSessionState.TERMINATED, InteractiveSessionState.INTERACTIVE
        )

    @pytest.mark.asyncio
    async def test_interactive_is_not_a_claim_that_anything_succeeded(self, tmp_path):
        """§5.2 — no surface may read completion out of a session state.

        `P0-EXEC-003` was this defect one layer up: a state that means "running" being
        painted in the colour of "done".
        """
        _, _, _, service, _, session = await _session(tmp_path)
        live = await _to_interactive(service, session.session_id)
        assert live.state is InteractiveSessionState.INTERACTIVE
        assert live.owner_readable_state == "Ready"
        assert "success" not in live.owner_readable_state.lower()
        assert live.final_reason is None

    @pytest.mark.asyncio
    async def test_ending_a_session_gives_the_profile_back(self, tmp_path):
        store, _, _, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        await service.transition(
            session_id=session.session_id,
            target=InteractiveSessionState.TERMINATING, now_ms=5_000,
        )
        await service.transition(
            session_id=session.session_id,
            target=InteractiveSessionState.TERMINATED, reason="owner closed it", now_ms=5_100,
        )
        row = await store.fetchone(
            "SELECT lease_holder FROM browser_profiles WHERE profile_alias = 'authenticated_owner'"
        )
        assert row["lease_holder"] is None

    @pytest.mark.asyncio
    async def test_the_url_is_stored_as_a_digest_not_as_the_owners_browsing(self, tmp_path):
        store, _, _, service, _, session = await _session(tmp_path)
        await service.record_active_url(
            session_id=session.session_id, target_id="t1",
            url="https://example.com/private/page?token=abc", title="Example", now_ms=3_000,
        )
        row = await store.fetchone(
            "SELECT active_url_digest FROM browser_interactive_sessions WHERE session_id = ?",
            (session.session_id,),
        )
        assert row["active_url_digest"]
        assert "example.com" not in row["active_url_digest"]
        targets = await store.fetchall(
            "SELECT url_digest FROM browser_session_targets WHERE session_id = ?",
            (session.session_id,),
        )
        assert all("token=abc" not in (t["url_digest"] or "") for t in targets)

    @pytest.mark.asyncio
    async def test_only_durable_events_reach_the_ledger(self, tmp_path):
        """ADR-RB-008 — an event store carrying pointer motion stops being readable."""
        _, _, _, service, _, session = await _session(tmp_path)
        with pytest.raises(InteractiveSessionError, match="not_durable"):
            await service.record_event(
                session_id=session.session_id, event_type="session.pointer_moved",
                severity="INFO", summary="x=10 y=20", now_ms=3_000,
            )


# --------------------------------------------------------------------------- actuation gate


async def _to_interactive(service, session_id):
    for state in (
        InteractiveSessionState.ALLOCATING,
        InteractiveSessionState.SIGNALING,
        InteractiveSessionState.CONNECTING,
        InteractiveSessionState.INTERACTIVE,
    ):
        await service.transition(session_id=session_id, target=state, now_ms=2_000)
    return await service.get(session_id)


class TestActuationGate:
    @pytest.mark.asyncio
    async def test_input_is_accepted_once_the_viewport_is_acknowledged(self, tmp_path):
        _, _, control, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        await service.acknowledge_viewport(session_id=session.session_id, revision=1)
        current = await control.current(session.session_id)
        assert current is not None
        ok = await service.assert_may_actuate(
            session_id=session.session_id,
            control_lease_id=current.control_lease_id,
            control_generation=current.generation,
            viewport_revision=1, now_ms=2_500,
        )
        assert ok.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_input_is_withheld_until_the_device_acknowledges_the_layout(self, tmp_path):
        """§8.1 — the client withholds actuation until viewport.ack for the layout shown."""
        _, _, control, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        current = await control.current(session.session_id)
        assert current is not None
        with pytest.raises(InteractiveSessionError, match="not_acknowledged"):
            await service.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=current.control_lease_id,
                control_generation=current.generation,
                viewport_revision=1, now_ms=2_500,
            )

    @pytest.mark.asyncio
    async def test_a_stale_viewport_revision_is_refused_not_transformed(self, tmp_path):
        """The defect this prevents is a confident wrong tap, which looks like a working
        browser to everyone including the owner."""
        _, _, control, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        await service.acknowledge_viewport(session_id=session.session_id, revision=1)
        await service.propose_viewport(
            session_id=session.session_id,
            viewport=Viewport(width=2016, height=1080, device_scale_factor=1.0),
            now_ms=2_600,
        )
        current = await control.current(session.session_id)
        assert current is not None
        with pytest.raises(InteractiveSessionError, match="revision_stale"):
            await service.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=current.control_lease_id,
                control_generation=current.generation,
                viewport_revision=1, now_ms=2_700,
            )

    @pytest.mark.asyncio
    async def test_acknowledging_an_old_revision_does_not_re_enable_input(self, tmp_path):
        _, _, _, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        await service.propose_viewport(
            session_id=session.session_id,
            viewport=Viewport(width=2016, height=1080, device_scale_factor=1.0),
            now_ms=2_600,
        )
        with pytest.raises(InteractiveSessionError, match="ack_stale"):
            await service.acknowledge_viewport(session_id=session.session_id, revision=1)

    @pytest.mark.asyncio
    async def test_a_suspended_session_cannot_be_actuated(self, tmp_path):
        _, _, control, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        await service.acknowledge_viewport(session_id=session.session_id, revision=1)
        current = await control.current(session.session_id)
        assert current is not None
        await service.transition(
            session_id=session.session_id,
            target=InteractiveSessionState.SUSPENDED, now_ms=3_000,
        )
        with pytest.raises(InteractiveSessionError, match="not_actuatable"):
            await service.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=current.control_lease_id,
                control_generation=current.generation,
                viewport_revision=1, now_ms=3_100,
            )

    @pytest.mark.asyncio
    async def test_an_expired_profile_lease_stops_input_immediately(self, tmp_path):
        """§0E.1 D7, at the level the owner feels it."""
        store, _, control, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        await service.acknowledge_viewport(session_id=session.session_id, revision=1)
        current = await control.current(session.session_id)
        assert current is not None
        await store.execute(
            "UPDATE browser_profiles SET lease_expires_at_ms = ? WHERE lease_holder = ?",
            (2_000, session.profile_lease_id),
        )
        with pytest.raises(InteractiveSessionError, match="lease_expired"):
            await service.assert_may_actuate(
                session_id=session.session_id,
                control_lease_id=current.control_lease_id,
                control_generation=current.generation,
                viewport_revision=1, now_ms=2_001,
            )

    @pytest.mark.asyncio
    async def test_a_lost_lease_suspends_the_session_and_drops_control(self, tmp_path):
        store, _, control, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        await store.execute(
            "UPDATE browser_profiles SET lease_expires_at_ms = ? WHERE lease_holder = ?",
            (2_000, session.profile_lease_id),
        )
        with pytest.raises(InteractiveSessionError, match="lease_expired"):
            await service.heartbeat(session_id=session.session_id, now_ms=2_500)
        after = await service.get(session.session_id)
        assert after is not None and after.state is InteractiveSessionState.SUSPENDED
        current = await control.current(session.session_id)
        assert current is not None and current.revoked_at_ms is not None

    @pytest.mark.asyncio
    async def test_a_heartbeat_renews_the_lease_when_it_is_due(self, tmp_path):
        store, broker, _, service, _, session = await _session(tmp_path)
        await _to_interactive(service, session.session_id)
        before = await store.fetchone(
            "SELECT lease_expires_at_ms FROM browser_profiles WHERE lease_holder = ?",
            (session.profile_lease_id,),
        )
        # Inside the renewal window: 120s lease, renew when under 80s remain.
        await service.heartbeat(session_id=session.session_id, now_ms=1_000 + 50_000)
        after = await store.fetchone(
            "SELECT lease_expires_at_ms FROM browser_profiles WHERE lease_holder = ?",
            (session.profile_lease_id,),
        )
        assert int(after["lease_expires_at_ms"]) > int(before["lease_expires_at_ms"])


# --------------------------------------------------------------------------- event targeting


class TestDeviceTargetedEvents:
    @pytest.mark.asyncio
    async def test_a_device_does_not_see_another_devices_events(self, tmp_path):
        store = await make_store(tmp_path)
        bus = EventBus(store)
        await bus.publish("session.created", {"a": 1}, target_device_id="phone-a")
        await bus.publish("session.created", {"b": 2}, target_device_id="phone-b")
        await bus.publish("mission.updated", {"broadcast": True})

        page = await bus.replay("phone-a", 0)
        kinds = [(e["event_type"], e["payload"]) for e in page["events"]]
        assert {"a": 1} in [p for _, p in kinds]
        assert {"b": 2} not in [p for _, p in kinds]
        assert {"broadcast": True} in [p for _, p in kinds]

    @pytest.mark.asyncio
    async def test_the_cursor_does_not_rescan_another_devices_rows_forever(self, tmp_path):
        """The subtle one. Leaving the cursor at the last *visible* row means every poll
        re-reads everything addressed to the other phone, and the gap grows with use."""
        store = await make_store(tmp_path)
        bus = EventBus(store)
        await bus.publish("session.created", {"mine": True}, target_device_id="phone-a")
        for _ in range(5):
            await bus.publish("session.created", {"theirs": True}, target_device_id="phone-b")

        page = await bus.replay("phone-a", 0)
        assert len(page["events"]) == 1
        row = await store.fetchone("SELECT MAX(seq) AS s FROM events")
        assert page["next_cursor"] == int(row["s"])

        nothing_new = await bus.replay("phone-a", page["next_cursor"])
        assert nothing_new["events"] == []

    @pytest.mark.asyncio
    async def test_a_full_page_stops_at_the_last_row_it_returned(self, tmp_path):
        store = await make_store(tmp_path)
        bus = EventBus(store, page_size=2)
        for i in range(5):
            await bus.publish("session.created", {"i": i}, target_device_id="phone-a")
        page = await bus.replay("phone-a", 0)
        assert page["truncated"] is True
        assert page["next_cursor"] == page["events"][-1]["seq"]

    @pytest.mark.asyncio
    async def test_publishing_the_same_event_id_twice_writes_one_row(self, tmp_path):
        """ADR-RB-011 — transport is at-least-once; the owner's ledger is not."""
        store = await make_store(tmp_path)
        bus = EventBus(store)
        first = await bus.publish("session.created", {"x": 1}, event_id="evt_fixed")
        second = await bus.publish("session.created", {"x": 1}, event_id="evt_fixed")
        assert first == second
        rows = await store.fetchall("SELECT seq FROM events WHERE event_id = 'evt_fixed'")
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_an_existing_caller_that_passes_only_two_arguments_still_works(self, tmp_path):
        """§5.6 — the signature is additive. Every existing publisher passes (type, payload)."""
        store = await make_store(tmp_path)
        bus = EventBus(store)
        seq = await bus.publish("mission.updated", {"mission_id": "m1"})
        row = await store.fetchone("SELECT event_id, target_device_id FROM events WHERE seq = ?", (seq,))
        assert row["event_id"] is not None
        assert row["target_device_id"] is None
