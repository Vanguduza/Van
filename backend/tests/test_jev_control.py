import pytest

from van_gateway.action.registry import BUILTIN_ACTIONS
from van_gateway.command.local_executors import (
    JevGlobalControlExecutor,
    JevModuleTransitionExecutor,
    LocalExecutionContext,
)
from van_gateway.command.resolver import TypedCommandResolver
from van_gateway.command.success_contracts import JEV_READBACK, contract_for
from van_gateway.models import ActionClass


def test_jev_module_transition_resolves_as_owner_approved_a4():
    resolved = TypedCommandResolver().resolve(
        "set jev module van.attention.fields.v1 to ACTIVE_GATED"
    )
    assert resolved.action_id == "jev.module.transition"
    assert resolved.action_class == ActionClass.A4
    assert resolved.no_stale_replay is True
    assert resolved.parameters == {
        "module_id": "van.attention.fields.v1",
        "target_state": "ACTIVE_GATED",
    }


def test_jev_global_and_project_controls_resolve_exactly():
    resolver = TypedCommandResolver()
    assert resolver.resolve("bypass jev").action_id == "jev.global.control"
    project = resolver.resolve("disable jev for project van")
    assert project.action_id == "jev.global.control"
    assert project.parameters == {"operation": "disable", "project_id": "van"}


def test_jev_actions_are_registered_a4_mutations():
    by_id = {action.action_id: action for action in BUILTIN_ACTIONS}
    for action_id in ("jev.module.transition", "jev.global.control"):
        action = by_id[action_id]
        assert action.action_class == ActionClass.A4
        assert action.mutates_state is True
        assert action.no_stale_replay is True


def test_jev_success_contracts_name_real_readback_state():
    resolver = TypedCommandResolver()
    module = contract_for(
        resolver.resolve("set jev module van.attention.fields.v1 to SHADOW")
    )
    assert module.verifier_class == JEV_READBACK
    assert module.postconditions["status"] == "SHADOW"

    global_control = contract_for(resolver.resolve("restore jev"))
    assert global_control.verifier_class == JEV_READBACK
    assert global_control.postconditions["owner_active"] is True
    assert global_control.postconditions["bypassed"] is False


class FakeJev:
    def __init__(self):
        self.module_state = "DISABLED"
        self.global_state = {"owner_active": True, "bypassed": False, "projects": {}}

    async def transition_module(self, *, module_id, target_state, **_kwargs):
        self.module_state = target_state
        return {"module_id": module_id, "to": target_state}

    async def module(self, module_id):
        return {"module_id": module_id, "status": self.module_state}

    async def global_control(self, **kwargs):
        if "owner_active" in kwargs:
            self.global_state["owner_active"] = kwargs["owner_active"]
        if "bypassed" in kwargs:
            self.global_state["bypassed"] = kwargs["bypassed"]
        if kwargs.get("project_id") is not None:
            self.global_state["projects"][kwargs["project_id"]] = kwargs["project_enabled"]
        return dict(self.global_state)


def ctx(jev, parameters):
    return LocalExecutionContext(
        store=None,
        context=None,
        owner_fact_author=None,
        reminders=None,
        trading=None,
        jev=jev,
        device_id="device-1",
        command_id="cmd-1",
        mission_id="mission-1",
        parameters=parameters,
        client_context={},
        now_ms=1,
    )


@pytest.mark.asyncio
async def test_module_executor_reads_back_the_transition():
    fake = FakeJev()
    result = await JevModuleTransitionExecutor().execute(
        ctx(fake, {"module_id": "van.attention.fields.v1", "target_state": "SHADOW"})
    )
    assert result.observed_postcondition["status"] == "SHADOW"
    assert result.evidence_ref == "jev-module:van.attention.fields.v1:SHADOW"


@pytest.mark.asyncio
async def test_global_executor_applies_project_switch():
    fake = FakeJev()
    result = await JevGlobalControlExecutor().execute(
        ctx(fake, {"operation": "disable", "project_id": "van"})
    )
    assert result.observed_postcondition["state"]["projects"]["van"] is False
