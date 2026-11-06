"""Actual durable authority, wire dispatch, native effects, and independent readback.

The CDP fixture supplies controlled page state; these are repository integration
tests and do not certify a deployed Chromium, host, or physical handset.
"""
import json
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from test_browser_producer_api import fabric, delegated_task, NOW, PRINCIPAL
from van_gateway.action.service import ActionRuntime
from van_gateway.browser.action_plans import BrowserActionPlanService, CreatePlan, PlanError, PLAN_ACTION, build_action_plan_router
from van_gateway.browser.producer_service import ProducerError
from van_gateway.command.authority import CommandAuthorityService, CommandAuthorityRecord
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from services.browser_control_agent.server import dispatch_message
from services.browser_control_agent.wire import encode_call, decode_response
from services.browser_stream_host.broker_client import BrokerRefused


class Page:
    def __init__(self):
        self.value, self.text = "before", "before"
        self.calls = []
        self.nodes = [4]
        self.type = "text"
        self.hook = None

    async def send(self, target, method, params):
        self.calls.append((method, params))
        if self.hook:
            await self.hook(method)
        if method == "Page.getNavigationHistory":
            return {"currentIndex": 0, "entries": [{"url": "https://example.org"}]}
        if method == "DOM.getDocument": return {"root": {"nodeId": 1}}
        if method == "DOM.querySelectorAll": return {"nodeIds": self.nodes}
        if method == "DOM.describeNode": return {"node": {"nodeName": "INPUT", "backendNodeId": 44, "attributes": ["type", self.type]}}
        if method == "DOM.getNodeForLocation": return {"backendNodeId": 44}
        if method == "DOM.resolveNode": return {"object": {"objectId": "node-4"}}
        if method == "Runtime.callFunctionOn":
            return {"result": {"value": self.value if "this.value" in params["functionDeclaration"] else self.text}}
        if method == "DOM.getContentQuads": return {"quads": [[10,10,40,10,40,40,10,40]]}
        if method == "Input.insertText": self.value = params["text"]
        if method == "Input.dispatchMouseEvent" and params["type"] == "mouseReleased": self.text = "after"
        return {}


class Broker:
    def __init__(self, f): self.f = f
    async def _call(self, name, caller, call):
        try:
            return await getattr(self.f.producers, name)(principal=PRINCIPAL, caller_common_name=caller,
                operation=call.operation.value, session_id=call.session_id, target_id=call.target_id,
                lease_id=call.lease_id, lease_generation=call.lease_generation,
                task_id=call.task_id, params=call.params, now_ms=NOW)
        except ProducerError as exc: raise BrokerRefused(str(exc)) from exc
    async def validate_call(self, caller, call): return await self._call("validate_call", caller, call)
    async def authorize_call(self, caller, call): return await self._call("authorize_call", caller, call)
    async def validate_result(self, caller, call): return await self._call("validate_result", caller, call)


class Client:
    def __init__(self, f, page): self.f, self.page, self.calls, self.drop = f, page, [], False
    async def invoke(self, call):
        self.calls.append(call)
        response = await dispatch_message(encode_call(call, request_id="effect"),
            caller_common_name="van-trading-core", broker=Broker(self.f), cdp=self.page)
        _, ok, result = decode_response(response)
        if self.drop: raise TimeoutError("reply lost after effect")
        if not ok: raise BrokerRefused(result)
        return result


def draft(operation="fill_element", **extra):
    step = {"step_id": "one", "operation": operation, "selector": "#owner-field",
        "postcondition": {"kind": "input_value_equals", "selector": "#owner-field", "value": "after"}, "text": "after"}
    if operation == "click_element":
        step.pop("text")
        step["postcondition"] = {"kind": "element_text_equals", "selector": "#result", "text": "after"}
    return CreatePlan.model_validate({"idempotency_key": "owner-request", "task_id": "task", "target_id": "tab",
        "deadline_ms": NOW+50000, "steps": [step], **extra})


async def prepared(f, monkeypatch, operation="fill_element"):
    monkeypatch.setattr(time, "time", lambda: NOW/1000)
    await f.broker.register_profile(profile_alias="authenticated_owner", secret_ref="secretref://test-owner-profile", now_ms=NOW)
    from van_gateway.browser.interactive_models import Viewport
    f.session = await f.sessions.create(owner_device_id="phone", profile_alias="authenticated_owner", viewport=Viewport(width=1080,height=1920,device_scale_factor=1), now_ms=NOW)
    await delegated_task(f)
    authority, page = CommandAuthorityService(f.store), Page()
    client = Client(f, page)
    plans = BrowserActionPlanService(store=f.store, sessions=f.sessions, producers=f.producers,
        command_authority=authority, profile_clients={"authenticated_owner": (client, "van-trading-core", PRINCIPAL)})
    plan = await plans.create(session_id=f.session.session_id, owner_device_id="phone", body=draft(operation), now_ms=NOW)
    params = {key: plan[key] for key in ("session_id", "plan_id", "plan_sha256")}
    await authority.seal(CommandAuthorityRecord(command_id="approved", device_id="phone",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="phone", origin_channel=OriginChannel.TEXT,
        signed_action_class=ActionClass.A4, effective_action_class=ActionClass.A4,
        typed_action_id=PLAN_ACTION.action_id, typed_parameter_constraints=params, snapshot_id="snapshot",
        context_digest="digest", issued_at_unix=NOW//1000, expires_at_unix=NOW//1000+120,
        owner_approved=True, sealed_at_unix_ms=NOW))
    await f.store.execute("INSERT INTO context_snapshots(snapshot_id,command_id,kernel_revision,fact_ids_json,graph_evidence_refs_json,live_state_refs_json,policy_refs_json,compiled_at_ms,digest) VALUES('snapshot','approved',1,'[]','[]','[]','[]',?,'digest')", (NOW,))
    runtime = ActionRuntime(f.store)
    await runtime.register(PLAN_ACTION)
    execution = await runtime.begin(execution_id="execution", command_id="approved", turn_id=None,
        action_id=PLAN_ACTION.action_id, principal_type=PrincipalType.OWNER_DEVICE, requested_by="phone",
        idempotency_key="execution-key", parameters=params, snapshot_id="snapshot", owner_approved=True)
    await f.store.execute("UPDATE action_executions SET status='EXECUTING' WHERE execution_id='execution'")
    execution = await runtime.get_execution("execution")
    return plans, plan, params, execution, client, page


@pytest.mark.parametrize("operation", ["fill_element", "click_element"])
async def test_exact_owner_plan_native_effect_then_independent_readback(fabric, monkeypatch, operation):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch, operation)
    result = await plans.execute(execution, params)
    assert result["status"] == "VERIFIED_SUCCESS"
    receipt = result["step_states"]["one"]
    assert receipt["effect_receipt"]["verification"] == "REQUIRES_INDEPENDENT_READBACK"
    assert receipt["independent_readback"]["observation_source"] == "NATIVE_CDP_INDEPENDENT_READBACK"
    assert [call.operation.value for call in client.calls] == [operation, "observe_effect"]
    assert not any("expression" in args or method == "Runtime.evaluate" for method,args in page.calls)
    assert await plans.execute(execution, params) == result
    assert len(client.calls) == 2


async def test_lost_effect_reply_is_durable_unknown_and_never_replays(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    client.drop = True
    result = await plans.execute(execution, params)
    assert result["status"] == "UNKNOWN" and result["step_states"]["one"]["status"] == "IN_FLIGHT"
    assert page.value == "after"
    assert (await plans.execute(execution, params))["status"] == "UNKNOWN"
    assert len(client.calls) == 1


async def test_owner_preemption_during_focus_fences_insert_text(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    async def takeover(method):
        if method == "DOM.focus":
            await fabric.control.owner_preempt(session_id=fabric.session.session_id, device_id="phone", now_ms=NOW)
    page.hook = takeover
    result = await plans.execute(execution, params)
    assert result["status"] == "UNKNOWN"
    assert page.value == "before"
    assert not any(method == "Input.insertText" for method,_ in page.calls)


@pytest.mark.parametrize("bad", ["password", "hidden", "file"])
async def test_credential_and_unsupported_fields_refused_before_focus(fabric, monkeypatch, bad):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    page.type = bad
    assert (await plans.execute(execution, params))["status"] == "UNKNOWN"
    assert not any(method.startswith("Input.") or method == "DOM.focus" for method,_ in page.calls)


async def test_selector_ambiguity_refused_without_effect(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    page.nodes = [4,5]
    assert (await plans.execute(execution, params))["status"] == "UNKNOWN"
    assert not any(method.startswith("Input.") for method,_ in page.calls)


async def test_draft_idempotency_binding_and_cancel_confer_no_authority(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    assert await plans.create(session_id=fabric.session.session_id, owner_device_id="phone", body=draft(), now_ms=NOW) == plan
    with pytest.raises(PlanError, match="idempotency_conflict"):
        await plans.create(session_id=fabric.session.session_id, owner_device_id="phone", body=draft(deadline_ms=NOW+1000), now_ms=NOW)
    with pytest.raises(PlanError, match="unknown"):
        await plans.get(session_id=fabric.session.session_id, owner_device_id="other", plan_id=plan["plan_id"])
    await plans.cancel(session_id=fabric.session.session_id, owner_device_id="phone", plan_id=plan["plan_id"])
    assert (await plans.execute(execution, params))["status"] == "CANCELLED" and not client.calls


async def test_unsigned_or_changed_digest_refuses_before_native_client(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    with pytest.raises(ValueError, match="typed_parameter_mismatch"):
        await plans.execute(execution, {**params, "plan_sha256": "0"*64})
    await fabric.store.execute("UPDATE runtime_meta SET value=json_set(value,'$.owner_approved',json('false')) WHERE key='command_authority:approved'")
    with pytest.raises(PlanError, match="owner_approval"):
        await plans.execute(execution, params)
    assert not client.calls


async def test_owner_projection_lists_only_exact_mission_tasks(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    app = FastAPI()
    @app.middleware("http")
    async def proof(request, call_next):
        request.state.van_device_id = "phone"
        return await call_next(request)
    app.include_router(build_action_plan_router(plans))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        result = await ac.get(f"/v1/browser/interactive-sessions/{plan['session_id']}/action-plans")
        assert result.status_code == 200
        assert result.json()["task_candidates"][0]["task_id"] == "task"
        assert result.json()["plans"][0]["idempotency_key"] == "owner-request"


async def test_postsubmission_observer_does_new_readback_and_detects_changed_state(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    assert (await plans.execute(execution, params))["status"] == "VERIFIED_SUCCESS"
    await fabric.store.execute("UPDATE action_executions SET status='VERIFYING' WHERE execution_id='execution'")
    receipt = await plans.verify(execution, params)
    assert receipt["success"] is True and len(client.calls) == 3
    # The action is terminal before the Mission verifier performs its separate
    # final readback. This permits observation, never another mutation.
    await fabric.store.execute("UPDATE action_executions SET status='VERIFIED_SUCCESS' WHERE execution_id='execution'")
    page.value = "changed later"
    mission_receipt = await plans.verify(execution, params)
    assert mission_receipt["success"] is False and len(client.calls) == 4
    # Both independent verifiers consume their finite reserved budget. Further
    # observation attempts cannot become unlimited mutation qualification.
    with pytest.raises(BrokerRefused): await plans.verify(execution, params)


async def test_verified_action_cannot_reactuate_during_final_observer_budget(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    assert (await plans.execute(execution, params))["status"] == "VERIFIED_SUCCESS"
    await fabric.store.execute("UPDATE action_executions SET status='VERIFIED_SUCCESS' WHERE execution_id='execution'")
    before = list(page.calls)
    with pytest.raises(BrokerRefused):
        await client.invoke(client.calls[0])
    assert page.calls == before and page.value == "after"
    assert (await plans.verify(execution, params))["success"] is True


async def test_false_native_postcondition_is_unverifiable(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch, "click_element")
    async def no_confirmation(method):
        if method == "Runtime.callFunctionOn": page.text = "not confirmed"
    page.hook = no_confirmation
    assert (await plans.execute(execution, params))["status"] == "UNVERIFIABLE"
    assert (await plans.verify(execution, params))["success"] is False


async def test_cancel_during_native_focus_fences_later_input(fabric, monkeypatch):
    plans, plan, params, execution, client, page = await prepared(fabric, monkeypatch)
    async def cancelled(method):
        if method == "DOM.focus":
            await plans.cancel(session_id=plan["session_id"], owner_device_id="phone", plan_id=plan["plan_id"])
    page.hook = cancelled
    assert (await plans.execute(execution, params))["status"] == "CANCELLED"
    assert not any(method == "Input.insertText" for method,_ in page.calls)


def test_plan_schema_refuses_unbounded_script_and_unsealed_fill_readback():
    with pytest.raises(ValidationError): draft(steps=[{"step_id": "one", "operation": "eval", "script": "arbitrary"}])
    bad = draft().model_dump()
    bad["steps"][0]["postcondition"]["value"] = "other"
    with pytest.raises(ValidationError): CreatePlan.model_validate(bad)
