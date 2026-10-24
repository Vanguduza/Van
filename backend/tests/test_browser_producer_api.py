"""Exercise producer authority over HTTP and against durable concurrent state."""
from __future__ import annotations

import asyncio
import json
import hashlib
import time
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from van_gateway.browser.control_lease import ControlLeaseService
from van_gateway.browser.interactive_models import BrowserControlHolder, InteractiveSessionState, Viewport
from van_gateway.browser.interactive_service import InteractiveSessionService, InteractiveSessionError
from van_gateway.browser.producer_api import build_browser_producer_router
from van_gateway.browser.producer_service import BrowserProducerService, ProducerError, credential_principal
from van_gateway.browser.service import BrowserSessionBroker
from van_gateway.browser.stream_grants import StreamGrantService, StreamGrantSigner, generate_signing_key
from van_gateway.browser.stream_routes import parse_profile_signal_urls, signal_url_for_profile
from van_gateway.storage.db import Store

NOW = 1_700_000_000_000
PROXY = "stream-producer-machine-credential-0123456789"
ISSUER = "browser-core-issuer-machine-credential-0123456789"
OTHER = "different-stream-machine-credential-0123456789"
PRINCIPAL = credential_principal(PROXY)
PID = "producer_0123456789abcdef"


@pytest_asyncio.fixture
async def fabric(tmp_path):
    store = Store(str(tmp_path / "producer.sqlite3"))
    await store.migrate()
    await store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES('phone','test-public-key',?)", (NOW // 1000,))
    broker = BrowserSessionBroker(store)
    await broker.register_profile(profile_alias="public_research", now_ms=NOW)
    control = ControlLeaseService(store)
    sessions = InteractiveSessionService(store, broker, control)
    session = await sessions.create(owner_device_id="phone", profile_alias="public_research", viewport=Viewport(width=1080, height=1920, device_scale_factor=1), now_ms=NOW)
    grants = StreamGrantService(store, StreamGrantSigner(generate_signing_key("test-stream")))
    producers = BrowserProducerService(store=store, sessions=sessions, grants=grants,
        control_proxy_bindings=json.dumps({PRINCIPAL: ["van-trading-core"]}))
    return SimpleNamespace(store=store, broker=broker, control=control, sessions=sessions,
                           session=session, grants=grants, producers=producers)


async def mint(f, *, scope=None, **extra):
    return await f.grants.mint(session_id=f.session.session_id, device_id="phone", profile_alias=f.session.profile_alias,
        scope=scope or ["browser.view", "webrtc.signal", "browser.owner_input"],
        max_width=1080, max_height=1920, max_fps=60, now_ms=NOW, **extra)


async def redeem(f, pid=PID):
    token, _ = await mint(f)
    return await f.producers.redeem(stream_grant=token, producer_session_id=pid, principal=PRINCIPAL, now_ms=NOW)


async def ready(f):
    result = await redeem(f)
    for event in ("allocated", "signaling", "connecting"):
        await f.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event=event, now_ms=NOW)
    await frame(f)
    await f.producers.acknowledge_frame(session_id=f.session.session_id, revision=1,
        frame_sequence=1, media_epoch=PID, now_ms=NOW)
    return result


async def frame(f, **extra):
    data = {"frame_sequence": 1, "viewport_revision": 1, "width": 1080, "height": 1920,
            "media_epoch": PID, "codec": "H264", "transport": "WEBRTC"}
    data.update(extra)
    return await f.producers.observe(producer_session_id=PID, principal=PRINCIPAL,
        event="first_frame", now_ms=NOW, **data)


async def authorize(f, **extra):
    data = {"producer_session_id": PID, "principal": PRINCIPAL,
            "session_id": f.session.session_id, "control_lease_id": f.session.control_lease_id,
            "control_generation": f.session.control_generation, "viewport_revision": 1, "now_ms": NOW}
    data.update(extra)
    return await f.producers.authorize_input(**data)


async def test_exact_grant_live_frame_and_device_ack_enable_owner_input(fabric):
    f = fabric
    redeemed = await ready(f)
    assert redeemed["owner_device_id"] == "phone"
    assert redeemed["authenticated_principal_kind"] == "STREAM_GRANT_BEARER"
    authority = await authorize(f)
    assert authority["control_holder"] == "OWNER"
    assert authority["media_epoch"] == authority["acked_media_epoch"] == PID
    assert authority["observed_frame_sequence"] == 1
    assert (await f.sessions.get(f.session.session_id)).state is InteractiveSessionState.INTERACTIVE


async def test_nonce_redemption_is_atomic_under_racing_producers(fabric):
    token, _ = await mint(fabric)
    results = await asyncio.gather(*[
        fabric.producers.redeem(stream_grant=token, producer_session_id=f"producer_racer_0123456789_{n}", principal=PRINCIPAL, now_ms=NOW)
        for n in range(2)
    ], return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, ProducerError) for r in results) == 1
    assert len(await fabric.store.fetchall("SELECT * FROM browser_stream_producers")) == 1


@pytest.mark.parametrize("field,value", [("device_id", "other"), ("profile_alias", "authenticated_owner"),
    ("session_id", "ibs_other"), ("nonce", "other-nonce"), ("scope", ["browser.view"]), ("expires_at_ms", NOW + 300_000)])
async def test_even_valid_signature_must_match_exact_minted_row(fabric, field, value):
    _, claims = await mint(fabric)
    claims[field] = value
    token = fabric.grants.signer.sign(claims)
    with pytest.raises(ProducerError, match="binding_mismatch"):
        await fabric.producers.redeem(stream_grant=token, producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW)
    row = await fabric.store.fetchone("SELECT redeemed_at_ms FROM browser_stream_grants")
    assert row["redeemed_at_ms"] is None


async def test_reconnect_fences_previous_producer_and_previous_epoch_ack(fabric):
    await ready(fabric)
    new_pid = "producer_new_0123456789abcdef"
    await redeem(fabric, new_pid)
    with pytest.raises(ProducerError, match="producer_revoked"):
        await fabric.producers.authority(producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW)
    with pytest.raises(ProducerError, match="ack_not_observed"):
        await fabric.producers.acknowledge_frame(session_id=fabric.session.session_id, revision=1, frame_sequence=1, media_epoch=PID, now_ms=NOW)
    with pytest.raises(ProducerError, match="epoch_not_acknowledged"):
        await authorize(fabric, producer_session_id=new_pid)


@pytest.mark.parametrize("sql,params,code", [
    ("UPDATE devices SET revoked_at_unix=1 WHERE device_id='phone'", (), "device_not_active"),
    ("UPDATE browser_profiles SET lease_holder_id='another-session'", (), "profile_lease_lost"),
    ("UPDATE browser_profiles SET lease_generation=lease_generation+1", (), "generation_stale"),
    ("UPDATE browser_profiles SET lease_expires_at_ms=?", (NOW,), "profile_lease_expired"),
    ("UPDATE browser_interactive_sessions SET expires_at_ms=?", (NOW,), "session_expired"),
    ("UPDATE browser_stream_grants SET revoked_at_ms=?", (NOW,), "producer_revoked"),
    ("UPDATE browser_interactive_sessions SET state='TERMINATED'", (), "session_ended"),
])
async def test_every_current_authority_read_checks_revocation_and_profile_fence(fabric, sql, params, code):
    await redeem(fabric)
    await fabric.store.execute(sql, params)
    with pytest.raises(ProducerError, match=code):
        await fabric.producers.authority(producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW)


async def test_connection_grant_expiry_does_not_terminate_redeemed_live_session(fabric):
    await redeem(fabric)
    await fabric.store.execute("UPDATE browser_profiles SET lease_expires_at_ms=?", (NOW + 300_000,))
    result = await fabric.producers.authority(producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW + 130_000)
    assert result["session_id"] == fabric.session.session_id


async def test_frame_observation_alone_does_not_acknowledge_owner_render(fabric):
    await redeem(fabric)
    for event in ("allocated", "signaling", "connecting"):
        await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event=event, now_ms=NOW)
    await frame(fabric)
    with pytest.raises(InteractiveSessionError, match="not_acknowledged"):
        await authorize(fabric)


@pytest.mark.parametrize("extra", [{"width": 1079}, {"height": 1919}, {"viewport_revision": 2}, {"media_epoch": "other_epoch"}, {"frame_sequence": 0}])
async def test_wrong_frame_geometry_or_epoch_cannot_become_interactive(fabric, extra):
    await redeem(fabric)
    for event in ("allocated", "signaling", "connecting"):
        await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event=event, now_ms=NOW)
    with pytest.raises(ProducerError):
        await frame(fabric, **extra)
    assert (await fabric.sessions.get(fabric.session.session_id)).state is InteractiveSessionState.CONNECTING


async def test_stale_frame_sequence_is_refused(fabric):
    await ready(fabric)
    with pytest.raises(ProducerError, match="sequence_stale"):
        await frame(fabric)


async def test_resize_requires_new_frame_and_ack(fabric):
    await ready(fabric)
    await fabric.sessions.propose_viewport(session_id=fabric.session.session_id, viewport=Viewport(width=1920, height=1080, device_scale_factor=1), now_ms=NOW)
    with pytest.raises(InteractiveSessionError, match="revision_stale"):
        await authorize(fabric)
    with pytest.raises(ProducerError, match="ack_not_observed"):
        await fabric.producers.acknowledge_frame(session_id=fabric.session.session_id, revision=2, frame_sequence=1, media_epoch=PID, now_ms=NOW)
    await frame(fabric, frame_sequence=2, viewport_revision=2, width=1920, height=1080)
    await fabric.producers.acknowledge_frame(session_id=fabric.session.session_id, revision=2, frame_sequence=2, media_epoch=PID, now_ms=NOW)
    assert (await authorize(fabric, viewport_revision=2))["viewport"]["revision"] == 2


async def test_owner_stream_cannot_use_a_delegated_agent_lease(fabric):
    await ready(fabric)
    lease = await fabric.control.delegate(session_id=fabric.session.session_id, holder=BrowserControlHolder.HERMES_DETERMINISTIC, issued_for="van-trading-core", now_ms=NOW)
    with pytest.raises(ProducerError, match="subject_refused"):
        await authorize(fabric, control_lease_id=lease.control_lease_id, control_generation=lease.generation)


async def test_stale_owner_lease_generation_refused_after_preemption(fabric):
    await ready(fabric)
    await fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW)
    with pytest.raises(InteractiveSessionError, match="superseded"):
        await authorize(fabric)


async def test_target_navigation_observations_reach_digest_only_gateway_state(fabric):
    await redeem(fabric)
    await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target", target_id="real-tab", url="https://example.org/private?q=owner", title="Owner page", now_ms=NOW)
    session = await fabric.sessions.get(fabric.session.session_id)
    assert session.active_target_id == "real-tab"
    assert "example.org" not in session.active_url_digest
    await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target_closed", target_id="real-tab", now_ms=NOW)
    assert (await fabric.sessions.get(fabric.session.session_id)).active_target_id is None


async def test_http_issuer_and_media_credentials_are_separate(fabric):
    settings = SimpleNamespace(internal_control_token="", internal_control_scoped_tokens=f"browser_stream_producer:{PROXY};browser:{ISSUER};browser_stream_producer:{OTHER}")
    app = FastAPI()
    app.include_router(build_browser_producer_router(service=fabric.producers, settings=settings))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for token in (None, ISSUER):
            response = await client.post("/v1/browser/stream-producer/redeem", json={"stream_grant": "malformed", "producer_session_id": PID}, headers={} if token is None else {"X-Van-Internal-Token": token})
            assert response.status_code == 403
        response = await client.post("/v1/browser/control-producer/grants", json={"task_id": "t", "session_id": "s", "target_id": "target", "caller_common_name": "van-trading-core", "proxy_principal_sha256": PRINCIPAL, "scope": "browser.actuate", "step_budget": 1, "deadline_ms": NOW + 5000}, headers={"X-Van-Internal-Token": PROXY})
        assert response.status_code == 403
        for token in ("junk", "e30.e30.e30", "W10.W10.e30"):
            response = await client.post("/v1/browser/stream-producer/redeem", json={"stream_grant": token, "producer_session_id": PID}, headers={"X-Van-Internal-Token": PROXY})
            assert response.status_code == 403


async def test_unknown_or_wrong_producer_principal_is_not_admitted(fabric):
    await redeem(fabric)
    for pid, principal in (("unknown_producer_id", PRINCIPAL), (PID, credential_principal(OTHER))):
        with pytest.raises(ProducerError, match="producer_unknown"):
            await fabric.producers.authority(producer_session_id=pid, principal=principal, now_ms=NOW)


async def delegated_task(f, *, action_class="A1"):
    await ready(f)
    # This test's canonical Mission and task rows are issued through the actual services
    # in integration tests; the focused broker fixture supplies their persisted contract.
    await f.store.execute("INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,created_at_ms,updated_at_ms) VALUES('mission','phone','OWNER','CHAT','test mission','test goal','RUNNING',?,?)", (NOW, NOW))
    await f.store.execute("UPDATE browser_interactive_sessions SET mission_id='mission' WHERE session_id=?", (f.session.session_id,))
    await f.store.execute("INSERT INTO browser_tasks(task_id,profile_alias,strategy,autonomy_tier,action_class,target_domain,goal,status,started_at_ms,updated_at_ms) VALUES('task',?,'HARNESS','L1_HARNESS_DETERMINISTIC',?,'example.org','observe','RUNNING',?,?)", (f.session.profile_alias, action_class, NOW, NOW))
    await f.store.execute("INSERT INTO mission_activities(activity_id,mission_id,activity_type,capability_id,executor,executor_ref,started_at_ms) VALUES('activity','mission','browser.task','browser.interactive.session','BROWSER_FABRIC','task',?)", (NOW,))
    await f.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target", target_id="tab", url="https://example.org", now_ms=NOW)
    lease = await f.control.delegate(session_id=f.session.session_id, holder=BrowserControlHolder.HERMES_DETERMINISTIC, issued_for="van-trading-core", now_ms=NOW)
    await f.sessions.transition(session_id=f.session.session_id, target=InteractiveSessionState.AGENT_CONTROLLED, now_ms=NOW)
    return lease


async def control_grant(f, *, scope="browser.actuate", budget=2):
    return await f.producers.issue_control_grant(task_id="task", session_id=f.session.session_id, target_id="tab", caller_common_name="van-trading-core", proxy_principal_sha256=PRINCIPAL, scope=scope, step_budget=budget, deadline_ms=NOW + 50_000, now_ms=NOW)


async def control_call(f, lease, **extra):
    data = {"principal": PRINCIPAL, "caller_common_name": "van-trading-core", "operation": "navigate", "session_id": f.session.session_id, "target_id": "tab", "lease_id": lease.control_lease_id, "lease_generation": lease.generation, "task_id": "task", "now_ms": NOW}
    data.update(extra)
    return await f.producers.authorize_call(**data)


async def control_validate(f, lease, **extra):
    data = {"principal": PRINCIPAL, "caller_common_name": "van-trading-core", "operation": "navigate", "session_id": f.session.session_id, "target_id": "tab", "lease_id": lease.control_lease_id, "lease_generation": lease.generation, "task_id": "task", "now_ms": NOW}
    data.update(extra)
    return await f.producers.validate_call(**data)


async def test_control_validation_does_not_consume_or_reset_durable_budget(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric, budget=1)
    for _ in range(3):
        validated = await control_validate(fabric, lease)
        assert validated["authorization_consumed"] is False
        assert validated["steps_used"] == 0
        assert validated["steps_remaining"] == 1
    consumed = await control_call(fabric, lease)
    assert consumed["authorization_consumed"] is True
    assert consumed["steps_used"] == 1
    with pytest.raises(ProducerError, match="budget_exhausted"):
        await control_validate(fabric, lease)


async def test_result_validation_fences_spent_final_step_without_admitting_another(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric, budget=1)
    args = {"principal": PRINCIPAL, "caller_common_name": "van-trading-core",
        "operation": "navigate", "session_id": fabric.session.session_id, "target_id": "tab",
        "lease_id": lease.control_lease_id, "lease_generation": lease.generation, "task_id": "task", "now_ms": NOW}
    with pytest.raises(ProducerError, match="no_authorized_step"):
        await fabric.producers.validate_result(**args)
    await control_call(fabric, lease)
    result = await fabric.producers.validate_result(**args)
    assert result["result_validation"] is True
    assert result["authorization_consumed"] is False
    assert result["steps_used"] == 1 and result["steps_remaining"] == 0
    with pytest.raises(ProducerError, match="budget_exhausted"):
        await control_validate(fabric, lease)
    await fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW)
    with pytest.raises(ProducerError, match="superseded"):
        await fabric.producers.validate_result(**args)


@pytest.mark.parametrize("action_class", ["A1", "A2", "A3"])
async def test_autonomous_input_requires_immutable_mutation_admission(fabric, action_class):
    lease = await delegated_task(fabric, action_class=action_class)
    await control_grant(fabric)
    for resolve in (control_validate, control_call):
        with pytest.raises(ProducerError, match="mutation_admission_unavailable"):
            await resolve(fabric, lease, operation="dispatch_input")
    assert (await fabric.store.fetchone("SELECT steps_used FROM browser_control_producer_grants"))["steps_used"] == 0


async def test_owner_preemption_between_validation_and_consumption_preserves_budget(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric, budget=1)
    await control_validate(fabric, lease)
    await fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW)
    with pytest.raises(ProducerError, match="superseded"):
        await control_call(fabric, lease)
    row = await fabric.store.fetchone("SELECT steps_used FROM browser_control_producer_grants")
    assert row["steps_used"] == 0


@pytest.mark.parametrize("mutation,code", [("UPDATE browser_control_leases SET expires_at_ms=1", "expired"),
    ("UPDATE missions SET state='CANCELLED'", "mission_not_active"),
    ("UPDATE browser_control_producer_grants SET revoked_at_ms=1", "revoked"),
    ("UPDATE browser_profiles SET lease_generation=lease_generation+1", "generation_stale")])
async def test_validation_uses_the_same_current_authority_checks(fabric, mutation, code):
    lease = await delegated_task(fabric)
    await control_grant(fabric)
    await fabric.store.execute(mutation)
    with pytest.raises(ProducerError, match=code):
        await control_validate(fabric, lease)


async def test_native_handler_refuses_owner_takeover_during_domain_observation(fabric, monkeypatch):
    from services.browser_control_agent.agent import Call
    from services.browser_control_agent.authority import Operation
    from services.browser_control_agent.server import dispatch_message
    from services.browser_control_agent.wire import encode_call, decode_response
    from services.browser_stream_host.broker_client import BrokerRefused

    monkeypatch.setattr(time, "time", lambda: NOW / 1000)
    lease = await delegated_task(fabric)
    await control_grant(fabric)
    class ActualStoreBroker:
        async def resolve(self, method, caller, call):
            try:
                return await method(principal=PRINCIPAL, caller_common_name=caller, operation=call.operation.value,
                    session_id=call.session_id, target_id=call.target_id, lease_id=call.lease_id,
                    lease_generation=call.lease_generation, task_id=call.task_id, now_ms=NOW)
            except ProducerError as exc:
                raise BrokerRefused(str(exc)) from exc
        async def validate_call(self, caller, call):
            return await self.resolve(fabric.producers.validate_call, caller, call)
        async def authorize_call(self, caller, call):
            return await self.resolve(fabric.producers.authorize_call, caller, call)
    class TakeoverDuringObservation:
        def __init__(self):
            self.methods = []
        async def send(self, target_id, method, params):
            self.methods.append(method)
            if method == "Page.getNavigationHistory":
                await fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW)
                return {"entries": [{"url": "https://example.org"}], "currentIndex": 0}
            return {"nodes": []}
    cdp = TakeoverDuringObservation()
    call = Call(operation=Operation.QUERY_ACCESSIBILITY, session_id=fabric.session.session_id,
        target_id="tab", lease_id=lease.control_lease_id, lease_generation=lease.generation, task_id="task", params={})
    response = await dispatch_message(encode_call(call, request_id="takeover-test"), caller_common_name="van-trading-core", broker=ActualStoreBroker(), cdp=cdp)
    _, ok, _ = decode_response(response)
    assert ok is False
    assert cdp.methods == ["Page.getNavigationHistory"]
    assert (await fabric.store.fetchone("SELECT steps_used FROM browser_control_producer_grants"))["steps_used"] == 0


@pytest.mark.parametrize("preempt_during_navigation", [False, True])
async def test_native_navigation_result_fences_the_final_spent_step(fabric, monkeypatch, preempt_during_navigation):
    from services.browser_control_agent.agent import Call
    from services.browser_control_agent.authority import Operation
    from services.browser_control_agent.server import dispatch_message
    from services.browser_control_agent.wire import encode_call, decode_response
    from services.browser_stream_host.broker_client import BrokerRefused

    monkeypatch.setattr(time, "time", lambda: NOW / 1000)
    lease = await delegated_task(fabric)
    await control_grant(fabric, budget=1)
    class ActualStoreBroker:
        async def resolve(self, method, caller, call):
            try:
                return await method(principal=PRINCIPAL, caller_common_name=caller, operation=call.operation.value,
                    session_id=call.session_id, target_id=call.target_id, lease_id=call.lease_id,
                    lease_generation=call.lease_generation, task_id=call.task_id, now_ms=NOW)
            except ProducerError as exc:
                raise BrokerRefused(str(exc)) from exc
        async def validate_call(self, caller, call):
            return await self.resolve(fabric.producers.validate_call, caller, call)
        async def authorize_call(self, caller, call):
            return await self.resolve(fabric.producers.authorize_call, caller, call)
        async def validate_result(self, caller, call):
            return await self.resolve(fabric.producers.validate_result, caller, call)
    class Navigation:
        def __init__(self):
            self.methods = []
        async def send(self, target_id, method, params):
            self.methods.append(method)
            assert method == "Page.navigate"
            return {"frameId": "actual-frame", "loaderId": "actual-loader"}
        async def wait_navigation(self, target_id, result, url, domains):
            if preempt_during_navigation:
                await fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW)
            return {"url": url, "history": [{"url": url}], "current": 0}
    cdp = Navigation()
    call = Call(operation=Operation.NAVIGATE, session_id=fabric.session.session_id,
        target_id="tab", lease_id=lease.control_lease_id, lease_generation=lease.generation,
        task_id="task", params={"url": "https://example.org"})
    response = await dispatch_message(encode_call(call, request_id="final-budget-nav"),
        caller_common_name="van-trading-core", broker=ActualStoreBroker(), cdp=cdp)
    _, ok, result = decode_response(response)
    assert ok is (not preempt_during_navigation)
    if ok:
        assert result["steps_remaining"] == 0
        assert result["navigation"]["url"] == "https://example.org"
    assert cdp.methods == ["Page.navigate"]
    assert (await fabric.store.fetchone("SELECT steps_used FROM browser_control_producer_grants"))["steps_used"] == 1


async def test_control_grants_spend_durable_budget_and_resolve_canonical_scope(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric)
    assert (await control_call(fabric, lease))["steps_remaining"] == 1
    restarted = BrowserProducerService(store=fabric.store, sessions=fabric.sessions, grants=fabric.grants, control_proxy_bindings=json.dumps({PRINCIPAL: ["van-trading-core"]}))
    fabric.producers = restarted
    result = await control_call(fabric, lease)
    assert result["steps_remaining"] == 0
    assert result["allowed_domains"] == ["example.org"]
    assert result["authenticated_principal_kind"] == "TRUSTED_PROXY_TLS_PEER_ATTESTATION"
    with pytest.raises(ProducerError, match="budget_exhausted"):
        await control_call(fabric, lease)
    with pytest.raises(ProducerError, match="already_issued"):
        await control_grant(fabric)


async def test_parallel_control_calls_cannot_overspend_budget(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric, budget=1)
    results = await asyncio.gather(control_call(fabric, lease), control_call(fabric, lease), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, ProducerError) for r in results) == 1


@pytest.mark.parametrize("scope,operation", [("browser.observe", "navigate"), ("browser.evidence", "dispatch_input"), ("browser.observe", "capture_evidence")])
async def test_control_task_scope_is_broker_resolved(fabric, scope, operation):
    lease = await delegated_task(fabric)
    await control_grant(fabric, scope=scope)
    with pytest.raises(ProducerError, match="out_of_scope"):
        await control_call(fabric, lease, operation=operation)


@pytest.mark.parametrize("extra,code", [({"caller_common_name": "forged-caller"}, "not_admitted"), ({"target_id": "other-tab"}, "target_not_bound"), ({"lease_generation": 99}, "lease_mismatch"), ({"task_id": "other-task"}, "grant_unknown"), ({"principal": credential_principal(OTHER)}, "not_admitted")])
async def test_control_exact_caller_task_target_and_lease_binding(fabric, extra, code):
    lease = await delegated_task(fabric)
    await control_grant(fabric)
    with pytest.raises(ProducerError, match=code):
        await control_call(fabric, lease, **extra)


async def test_owner_preemption_invalidates_live_control_grant(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric)
    await fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW)
    with pytest.raises(ProducerError, match="superseded"):
        await control_call(fabric, lease)


async def test_finished_task_is_not_reactivated_by_existing_grant(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric)
    await fabric.store.execute("UPDATE browser_tasks SET status='COMPLETED' WHERE task_id='task'")
    with pytest.raises(ProducerError, match="not_active"):
        await control_call(fabric, lease)


async def test_present_owner_heartbeat_keeps_same_control_fence_over_thirty_minutes(fabric):
    await ready(fabric)
    original = await fabric.control.current(fabric.session.session_id)
    for elapsed in range(40_000, 1_900_001, 40_000):
        await fabric.sessions.heartbeat(session_id=fabric.session.session_id, now_ms=NOW + elapsed)
    current = await fabric.control.current(fabric.session.session_id)
    assert current.control_lease_id == original.control_lease_id
    assert current.generation == original.generation
    assert current.expires_at_ms > NOW + 1_900_000
    session = await fabric.sessions.get(fabric.session.session_id)
    assert session.expires_at_ms > NOW + 1_900_000
    assert (await authorize(fabric, now_ms=NOW + 1_900_000))["control_generation"] == original.generation


async def test_heartbeat_does_not_revive_expired_owner_control(fabric):
    await ready(fabric)
    await fabric.store.execute("UPDATE browser_control_leases SET expires_at_ms=?", (NOW,))
    with pytest.raises(InteractiveSessionError, match="not_renewable"):
        await fabric.sessions.heartbeat(session_id=fabric.session.session_id, now_ms=NOW)


async def make_download(f, *, name="receipt.txt", mime="text/plain", download_id="download1"):
    await f.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target", target_id="tab", url="https://example.org", now_ms=NOW)
    await f.producers.report_download(producer_session_id=PID, principal=PRINCIPAL, event="started", download_id=download_id, target_id="tab", suggested_name=name, declared_mime=mime, url_digest="a" * 64, now_ms=NOW)
    return await f.producers.report_download(producer_session_id=PID, principal=PRINCIPAL, event="finished", download_id=download_id, target_id="tab", byte_size=4, content_sha256=hashlib.sha256(b"test").hexdigest(), observed_mime=mime, now_ms=NOW)


async def test_download_observation_uses_exact_target_and_actual_producer_reports(fabric):
    lease = await delegated_task(fabric)
    await make_download(fabric)
    await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target",
        target_id="other-tab", url="https://example.org/other", now_ms=NOW)
    await fabric.producers.report_download(producer_session_id=PID, principal=PRINCIPAL,
        event="started", download_id="other-download", target_id="other-tab",
        suggested_name="other.txt", declared_mime="text/plain", url_digest="b" * 64, now_ms=NOW)
    await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target",
        target_id="tab", url="https://example.org", now_ms=NOW)
    await control_grant(fabric, scope="browser.observe", budget=1)
    result = await control_call(fabric, lease, operation="observe_download")
    assert result["observation_available"] is True
    assert result["complete_snapshot"] is False
    assert result["observation_source"] == "AUTHENTICATED_STREAM_PRODUCER_REPORTS"
    assert result["observed_downloads"] == [{"download_id": "download1",
        "session_id": fabric.session.session_id, "target_id": "tab", "state": "COMPLETED",
        "suggested_name": "receipt.txt", "mime_type": "text/plain", "byte_size": 4,
        "content_sha256": hashlib.sha256(b"test").hexdigest(),
        "producer_session_id": PID, "host_deleted_at_ms": None}]
    assert result["steps_remaining"] == 0
    assert "transfer_grant" not in result and "url" not in result["observed_downloads"][0]


async def test_missing_producer_download_reports_never_claim_an_available_empty_snapshot(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric, scope="browser.observe", budget=2)
    result = await control_call(fabric, lease, operation="observe_download")
    assert result["observed_downloads"] == []
    assert result["observation_available"] is False and result["complete_snapshot"] is False
    # Legacy metadata is not evidence of an authenticated native producer event.
    await fabric.producers.downloads.create(download_id="legacy", session_id=fabric.session.session_id,
        target_id="tab", suggested_name="legacy.txt", declared_mime="text/plain", url_digest="a" * 64, now_ms=NOW)
    result = await control_call(fabric, lease, operation="observe_download")
    assert result["observed_downloads"] == [] and result["observation_available"] is False


async def test_native_download_observation_returns_broker_reports_without_file_bytes(fabric, monkeypatch):
    from services.browser_control_agent.agent import Call
    from services.browser_control_agent.authority import Operation
    from services.browser_control_agent.server import dispatch_message
    from services.browser_control_agent.wire import encode_call, decode_response
    from services.browser_stream_host.broker_client import BrokerRefused
    monkeypatch.setattr(time, "time", lambda: NOW / 1000)
    lease = await delegated_task(fabric)
    await make_download(fabric)
    await control_grant(fabric, scope="browser.observe", budget=1)
    class ActualStoreBroker:
        async def resolve(self, method, caller, call):
            try:
                return await method(principal=PRINCIPAL, caller_common_name=caller,
                    operation=call.operation.value, session_id=call.session_id, target_id=call.target_id,
                    lease_id=call.lease_id, lease_generation=call.lease_generation,
                    task_id=call.task_id, now_ms=NOW)
            except ProducerError as exc:
                raise BrokerRefused(str(exc)) from exc
        async def validate_call(self, caller, call):
            return await self.resolve(fabric.producers.validate_call, caller, call)
        async def authorize_call(self, caller, call):
            return await self.resolve(fabric.producers.authorize_call, caller, call)
    class TargetDomain:
        def __init__(self):
            self.methods = []
        async def send(self, target, method, params):
            self.methods.append(method)
            assert method == "Page.getNavigationHistory"
            return {"entries": [{"url": "https://example.org"}], "currentIndex": 0}
    cdp = TargetDomain()
    call = Call(operation=Operation.OBSERVE_DOWNLOAD, session_id=fabric.session.session_id,
        target_id="tab", lease_id=lease.control_lease_id, lease_generation=lease.generation, task_id="task", params={})
    response = await dispatch_message(encode_call(call, request_id="observed-download"),
        caller_common_name="van-trading-core", broker=ActualStoreBroker(), cdp=cdp)
    _, ok, result = decode_response(response)
    assert ok is True and result["observation_available"] is True
    assert [r["download_id"] for r in result["downloads"]] == ["download1"]
    assert result["transfer"] == "not_through_this_agent"
    assert cdp.methods == ["Page.getNavigationHistory"]
    assert "data" not in result and "transfer_grant" not in result


async def consume(f, grant, **extra):
    data = {"producer_session_id": PID, "principal": PRINCIPAL, "transfer_grant": grant["transfer_grant"], "operation": grant["operation"], "resource_id": grant["resource_id"], "now_ms": NOW}
    data.update(extra)
    return await f.producers.consume_transfer_grant(**data)


async def test_download_bytes_are_granted_once_with_canonical_hash_and_identity(fabric):
    await ready(fabric)
    report = await make_download(fabric)
    assert report["state"] == "COMPLETED"
    grant = await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation="download", target_id="tab", download_id="download1", content_sha256="forged-client-hash", byte_size=999, now_ms=NOW)
    assert grant["byte_size"] == 4
    result = await consume(fabric, grant)
    assert result["content_sha256"] == hashlib.sha256(b"test").hexdigest()
    assert result["artifact_producer_session_id"] == PID
    with pytest.raises(ProducerError, match="consumed"):
        await consume(fabric, grant)


@pytest.mark.parametrize("name,mime", [("danger.exe", "text/plain"), ("archive.zip", "application/zip"), ("innocent.txt", "application/x-executable")])
async def test_quarantined_file_cannot_receive_owner_transfer_grant(fabric, name, mime):
    await ready(fabric)
    result = await make_download(fabric, name=name, mime=mime)
    assert result["state"] == "QUARANTINED"
    with pytest.raises(ProducerError, match="not_permitted"):
        await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation="download", target_id="tab", download_id="download1", now_ms=NOW)


async def test_upload_exact_chooser_and_content_hash_are_consumed_once(fabric):
    await ready(fabric)
    await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target", target_id="tab", url="https://example.org", now_ms=NOW)
    await fabric.producers.register_chooser(producer_session_id=PID, principal=PRINCIPAL, chooser_id="chooser1", target_id="tab", now_ms=NOW)
    digest = hashlib.sha256(b"test").hexdigest()
    grant = await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation="upload", target_id="tab", chooser_id="chooser1", content_sha256=digest, byte_size=4, suggested_name="input.txt", now_ms=NOW)
    with pytest.raises(ProducerError, match="content_mismatch"):
        await consume(fabric, grant, content_sha256="a" * 64, byte_size=4)
    result = await consume(fabric, grant, content_sha256=digest, byte_size=4)
    assert result["resource_id"] == "chooser1"
    assert (await fabric.producers.authority(producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW))["pending_chooser_id"] is None


@pytest.mark.parametrize("mutation,code", [("UPDATE browser_downloads SET state='DELETED'", "not_permitted"), ("UPDATE browser_control_leases SET revoked_at_ms=1", "revoked"), ("UPDATE devices SET revoked_at_unix=1", "not_active"), ("UPDATE browser_downloads SET target_id='other-target'", "not_permitted"), ("UPDATE browser_interactive_sessions SET viewport_revision=2", "stale")])
async def test_transfer_redemption_checks_current_revocation_and_target(fabric, mutation, code):
    await ready(fabric)
    await make_download(fabric)
    grant = await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation="download", target_id="tab", download_id="download1", now_ms=NOW)
    await fabric.store.execute(mutation)
    with pytest.raises(ProducerError, match=code):
        await consume(fabric, grant)


async def test_transfer_one_use_is_atomic_under_racing_fetches(fabric):
    await ready(fabric)
    await make_download(fabric)
    grant = await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation="download", target_id="tab", download_id="download1", now_ms=NOW)
    results = await asyncio.gather(consume(fabric, grant), consume(fabric, grant), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, ProducerError) for r in results) == 1


async def test_download_grant_preserves_original_target_after_owner_switches_tabs(fabric):
    await ready(fabric)
    await make_download(fabric)
    await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target", target_id="new-tab", url="https://example.org/new", now_ms=NOW)
    grant = await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation="download", target_id="tab", download_id="download1", now_ms=NOW)
    result = await consume(fabric, grant)
    assert result["target_id"] == "tab"
    assert result["authority"]["active_target_id"] == "new-tab"


async def test_record_deletion_is_not_file_cleanup_until_real_host_acknowledges(fabric):
    await ready(fabric)
    await make_download(fabric)
    await fabric.producers.downloads.delete("download1", now_ms=NOW)
    authority = await fabric.producers.authority(producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW)
    assert authority["download_deletion_requests"] == [{"download_id": "download1", "artifact_producer_session_id": PID, "target_id": "tab"}]
    row = await fabric.store.fetchone("SELECT host_deleted_at_ms FROM browser_downloads WHERE download_id='download1'")
    assert row["host_deleted_at_ms"] is None
    await fabric.producers.report_download(producer_session_id=PID, principal=PRINCIPAL, event="deleted", download_id="download1", target_id="tab", now_ms=NOW)
    authority = await fabric.producers.authority(producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW)
    assert authority["download_deletion_requests"] == []


async def test_cancelled_mission_stops_control_task_even_if_task_row_still_running(fabric):
    lease = await delegated_task(fabric)
    await control_grant(fabric)
    await fabric.store.execute("UPDATE missions SET state='CANCELLED' WHERE mission_id='mission'")
    with pytest.raises(ProducerError, match="mission_not_active"):
        await control_call(fabric, lease)


async def test_transfer_expiry_and_resource_swap_never_consume_owner_grant(fabric):
    await ready(fabric)
    await make_download(fabric)
    grant = await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation="download", target_id="tab", download_id="download1", now_ms=NOW)
    with pytest.raises(ProducerError, match="resource_mismatch"):
        await consume(fabric, grant, resource_id="different-download")
    with pytest.raises(ProducerError, match="expired"):
        await consume(fabric, grant, now_ms=NOW + 60_000)


async def test_owner_resume_renews_profile_and_fences_previous_media(fabric):
    await ready(fabric)
    before = fabric.session.control_generation
    await fabric.sessions.transition(session_id=fabric.session.session_id, target=InteractiveSessionState.SUSPENDED, now_ms=NOW)
    resumed = await fabric.sessions.resume(session_id=fabric.session.session_id, now_ms=NOW + 1000)
    assert resumed.state is InteractiveSessionState.CONNECTING
    assert resumed.control_holder is BrowserControlHolder.OWNER
    assert resumed.control_generation > before
    assert resumed.acked_viewport_revision is None
    assert resumed.viewport == fabric.session.viewport
    with pytest.raises(ProducerError, match="revoked"):
        await fabric.producers.authority(producer_session_id=PID, principal=PRINCIPAL, now_ms=NOW + 1000)


async def test_owner_resume_reacquires_expired_available_profile_with_new_generation(fabric):
    await ready(fabric)
    old = await fabric.store.fetchone("SELECT lease_holder,lease_generation FROM browser_profiles")
    await fabric.sessions.transition(session_id=fabric.session.session_id, target=InteractiveSessionState.SUSPENDED, now_ms=NOW)
    resumed = await fabric.sessions.resume(session_id=fabric.session.session_id, now_ms=NOW + 130_000)
    new = await fabric.store.fetchone("SELECT lease_holder,lease_generation FROM browser_profiles")
    assert resumed.profile_lease_id == new["lease_holder"] != old["lease_holder"]
    assert new["lease_generation"] > old["lease_generation"]


async def test_owner_resume_cannot_steal_a_profile_acquired_by_another_session(fabric):
    await ready(fabric)
    await fabric.sessions.transition(session_id=fabric.session.session_id, target=InteractiveSessionState.SUSPENDED, now_ms=NOW)
    await fabric.broker.acquire_lease(profile_alias="public_research", task_id="other-task", now_ms=NOW + 130_000)
    with pytest.raises(InteractiveSessionError, match="profile_leased"):
        await fabric.sessions.resume(session_id=fabric.session.session_id, now_ms=NOW + 130_000)
    assert (await fabric.sessions.get(fabric.session.session_id)).state is InteractiveSessionState.SUSPENDED


async def test_owner_resume_refuses_expired_session_instead_of_reviving_stale_authority(fabric):
    await ready(fabric)
    await fabric.sessions.transition(session_id=fabric.session.session_id, target=InteractiveSessionState.SUSPENDED, now_ms=NOW)
    with pytest.raises(InteractiveSessionError, match="session_expired"):
        await fabric.sessions.resume(session_id=fabric.session.session_id, now_ms=NOW + 1_800_000)


async def test_racing_owner_preemptions_get_ordered_control_generations(fabric):
    await ready(fabric)
    leases = await asyncio.gather(*[fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW) for _ in range(2)])
    assert sorted(l.generation for l in leases) == [2, 3]
    assert (await fabric.control.current(fabric.session.session_id)).generation == 3


async def test_transfer_size_limits_and_foreign_owner_are_refused(fabric):
    await ready(fabric)
    await fabric.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target", target_id="tab", url="https://example.org", now_ms=NOW)
    for operation, limit in (("paste", 64 * 1024), ("upload", 64 * 1024 * 1024)):
        with pytest.raises(ProducerError, match="metadata_invalid"):
            await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="phone", operation=operation, target_id="tab", content_sha256="a" * 64, byte_size=limit + 1, now_ms=NOW)
    with pytest.raises(ProducerError, match="session_unknown"):
        await fabric.producers.issue_transfer_grant(session_id=fabric.session.session_id, owner_device_id="other-phone", operation="copy", target_id="tab", now_ms=NOW)


async def test_actual_gateway_middleware_admits_only_producer_scope_and_owner_session(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    from van_gateway.app import create_app
    from van_gateway.config import get_settings

    key = generate_signing_key("gateway-test")
    key_path = tmp_path / "stream.pem"
    key_path.write_text(key.private_pem)
    env = {"VAN_DATABASE_PATH": str(tmp_path / "gateway.sqlite"),
        "VAN_HERMES_BASE_URL": "http://hermes.invalid", "VAN_GOOGLE_TOKEN_FERNET_KEY": Fernet.generate_key().decode(),
        "VAN_DEVICE_SECRET_FERNET_KEY": Fernet.generate_key().decode(), "VAN_INGRESS_TOKEN": ISSUER,
        "VAN_INTERNAL_CONTROL_SCOPED_TOKENS": f"browser:{ISSUER};browser_stream_producer:{PROXY}",
        "VAN_BROWSER_CONTROL_PROXY_BINDINGS": json.dumps({PRINCIPAL: ["van-trading-core"]}),
        "VAN_BROWSER_STREAM_SIGNING_KEY_FILE": str(key_path), "VAN_BROWSER_STREAM_SIGNAL_URL": "https://stream.example/rtc"}
    env["VAN_BROWSER_STREAM_PROFILE_SIGNAL_URLS"] = json.dumps({"public_research": "https://stream.example/rtc/public", "authenticated_owner": "https://stream.example/rtc/owner"})
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    try:
        app = create_app()
        async with app.router.lifespan_context(app):
            await app.state.browser.broker.register_profile(profile_alias="public_research")
            ticket = await app.state.auth.create_pairing_ticket("phone")
            phone = await app.state.auth.pair_device(ticket.token, "phone", "s" * 32, "PEM", "phone")
            owner = {"X-Van-Ingress-Token": ISSUER, "X-Van-Device-Token": phone.access_token}
            producer = {"X-Van-Internal-Token": PROXY}
            issuer = {"X-Van-Internal-Token": ISSUER}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                created = await client.post("/v1/browser/interactive-sessions", json={"profile_alias": "public_research", "viewport": {"width": 1080, "height": 1920}}, headers=owner)
                assert created.status_code == 200, created.text
                sid = created.json()["session_id"]
                minted = await client.post(f"/v1/browser/interactive-sessions/{sid}/stream-grant", headers=owner)
                assert minted.status_code == 200, minted.text
                assert minted.json()["signal_url"] == "https://stream.example/rtc/public"
                for denied in (issuer, owner):
                    response = await client.post("/v1/browser/stream-producer/redeem", json={"stream_grant": minted.json()["stream_grant"], "producer_session_id": PID}, headers=denied)
                    assert response.status_code == 403
                redeemed = await client.post("/v1/browser/stream-producer/redeem", json={"stream_grant": minted.json()["stream_grant"], "producer_session_id": PID}, headers=producer)
                assert redeemed.status_code == 200, redeemed.text
                for event in ("allocated", "signaling", "connecting"):
                    response = await client.post(f"/v1/browser/stream-producer/{PID}/observe", json={"event": event}, headers=producer)
                    assert response.status_code == 200, response.text
                observed = await client.post(f"/v1/browser/stream-producer/{PID}/observe", json={"event": "first_frame", "frame_sequence": 1, "viewport_revision": 1, "width": 1080, "height": 1920, "media_epoch": PID}, headers=producer)
                assert observed.status_code == 200, observed.text
                legacy_ack = await client.post(f"/v1/browser/interactive-sessions/{sid}/viewport/ack", json={"revision": 1}, headers=owner)
                assert legacy_ack.status_code == 409
                ack = await client.post(f"/v1/browser/interactive-sessions/{sid}/viewport/ack", json={"revision": 1, "frame_sequence": 1, "media_epoch": PID}, headers=owner)
                assert ack.status_code == 200, ack.text
                assert ack.json()["media_epoch"] == PID
                authority = created.json()
                authorized = await client.post(f"/v1/browser/stream-producer/{PID}/authorize-input", json={"session_id": sid, "control_lease_id": authority["control_lease_id"], "control_generation": authority["control_generation"], "viewport_revision": 1}, headers=producer)
                assert authorized.status_code == 200, authorized.text
                target = await client.post(f"/v1/browser/stream-producer/{PID}/observe", json={"event": "target", "target_id": "tab", "url": "https://example.org"}, headers=producer)
                assert target.status_code == 200
                copy = await client.post(f"/v1/browser/interactive-sessions/{sid}/transfer-grants", json={"operation": "copy", "target_id": "tab"}, headers=owner)
                assert copy.status_code == 200, copy.text
                assert copy.json()["host_url"] == "https://stream.example/rtc/public/clipboard/copy"
                # A runtime credential never becomes an owner-device principal.
                blocked = await client.post(f"/v1/browser/interactive-sessions/{sid}/transfer-grants", json={"operation": "copy", "target_id": "tab"}, headers=producer)
                assert blocked.status_code in {401, 403}
                blocked = await client.post("/v1/browser/control-producer/grants", json={"task_id": "t", "session_id": sid, "target_id": "tab", "caller_common_name": "van-trading-core", "proxy_principal_sha256": PRINCIPAL, "scope": "browser.observe", "step_budget": 1, "deadline_ms": int(time.time() * 1000) + 1000}, headers=producer)
                assert blocked.status_code == 403
                # Both phases use the private consumer boundary, never the owner
                # or grant-issuer boundary. The admitted consumer reaches the
                # canonical missing-task check rather than acquiring authority.
                call_body = {"operation": "query_dom", "session_id": sid,
                    "target_id": "tab", "lease_id": authority["control_lease_id"],
                    "lease_generation": authority["control_generation"],
                    "task_id": "missing-task", "caller_common_name": "van-trading-core"}
                for phase in ("validate-call", "authorize-call", "validate-result"):
                    for denied in (owner, issuer):
                        refused = await client.post(f"/v1/browser/control-producer/{phase}", json=call_body, headers=denied)
                        assert refused.status_code == 403
                    missing = await client.post(f"/v1/browser/control-producer/{phase}", json=call_body, headers=producer)
                    assert missing.status_code == 404, missing.text
                    assert missing.json()["detail"] == "control_grant_unknown"
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("url", ["http://stream.example/rtc/public", "https://foreign.example/rtc/public",
    "https://stream.example/elsewhere", "https://stream.example/rtc/../private", "https://stream.example/rtc/%2e%2e/private",
    "https://owner:password@stream.example/rtc/public", "https://stream.example/rtc/public?token=bad", "https://stream.example/rtc/public#fragment"])
def test_profile_routes_cannot_expand_the_apks_signed_browser_route(url):
    with pytest.raises(ValueError, match="profile_signal_urls_invalid"):
        parse_profile_signal_urls(json.dumps({"public_research": url}), manifest_base_url="https://stream.example/rtc")


def test_profile_route_map_is_strict_and_legacy_fallback_is_only_for_empty_map():
    routes = parse_profile_signal_urls(json.dumps({"public_research": "https://stream.example/rtc/public"}), manifest_base_url="https://stream.example/rtc")
    assert signal_url_for_profile("public_research", profile_urls=routes, fallback_url="https://stream.example/rtc") == "https://stream.example/rtc/public"
    assert signal_url_for_profile("authenticated_owner", profile_urls=routes, fallback_url="https://stream.example/rtc") == ""
    assert signal_url_for_profile("public_research", profile_urls={}, fallback_url="https://stream.example/rtc") == "https://stream.example/rtc"


async def test_session_projection_supplies_configured_delegate_identity_and_refuses_substitution(fabric):
    from van_gateway.browser.interactive_api import build_interactive_router
    app = FastAPI()
    @app.middleware("http")
    async def fixture_device_identity(request, call_next):
        request.state.van_device_id = "phone"
        return await call_next(request)
    app.include_router(build_interactive_router(sessions=fabric.sessions, control=fabric.control, grants=fabric.grants,
        signal_url="https://stream.example/rtc", ice_servers=[], delegate_issued_for="van-trading-core"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        projection = await client.get(f"/v1/browser/interactive-sessions/{fabric.session.session_id}")
        assert projection.json()["control_delegate_issued_for"] == "van-trading-core"
        refused = await client.post(f"/v1/browser/interactive-sessions/{fabric.session.session_id}/delegate-control", json={"holder": "HERMES_DETERMINISTIC", "issued_for": "mission-id-is-not-a-service"})
        assert refused.status_code == 403
        accepted = await client.post(f"/v1/browser/interactive-sessions/{fabric.session.session_id}/delegate-control", json={"holder": "HERMES_DETERMINISTIC"})
        assert accepted.status_code == 200, accepted.text
        assert (await fabric.control.current(fabric.session.session_id)).issued_for == "van-trading-core"
