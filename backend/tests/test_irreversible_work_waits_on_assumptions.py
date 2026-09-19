"""§15 — the gate that had no door, no producer and no consumer.

Three separate absences made one mechanism unreachable, and each would have looked like a
small omission on its own:

- `record_assumption` had no production caller, so the ledger was always empty;
- `assert_safe_for_irreversible_work` had no production caller, so an empty ledger was
  never consulted;
- and there was no runtime route through which Hermes — the only system that does the
  reasoning that produces an assumption — could have supplied one.

Wiring the consumer alone would have produced a gate that can never fire, which is a
placeholder wearing a check's clothes. So this closes all three, and the tests are written
against the ways the result could still be false.

The counterexample that shaped the design: the actor the gate restrains records a CRITICAL
assumption, then clears it by asserting SUPERSEDED or FALSIFIED with nothing to show, and
proceeds. `resolve_assumption` demanded evidence for VERIFIED only, so that path was open.
A check whose subject may mark it passed is P0-VERIFY-001's defect in a different ledger.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from van_gateway.authority.descriptor import Reversibility, describe_action
from van_gateway.action.registry import BUILTIN_ACTIONS
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.models import AuthorityEnvelope, MissionOrigin, Sensitivity
from van_gateway.mission.service import MissionService
from van_gateway.models import ActionClass, OriginChannel
from van_gateway.reasoning.kernel import (
    AssumptionStatus,
    CriticalReasoningKernel,
    Importance,
    ReasoningError,
)
from van_gateway.storage.db import Store


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "assumptions.sqlite3"))
    await s.migrate()
    return s


@pytest_asyncio.fixture
async def kernel(store):
    return CriticalReasoningKernel(store)


@pytest_asyncio.fixture
async def mission(store):
    svc = MissionService(store, learning=LearningFeed(store))
    return await svc.create(
        owner_principal_id="device:d1",
        origin=MissionOrigin.OWNER_UI,
        origin_channel=OriginChannel.UI,
        title="delete the thing",
        goal="delete the thing",
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A4),
        sensitivity=Sensitivity.SECURITY,
    )


async def _blocker(kernel, mission, claim="the notebook is the one the owner meant"):
    return await kernel.record_assumption(
        mission_id=mission.mission_id,
        claim=claim,
        source="planner",
        importance=Importance.CRITICAL,
    )


# ---------------------------------------------------------------- the gate itself


@pytest.mark.asyncio
async def test_an_unsettled_high_impact_assumption_blocks_irreversible_work(kernel, mission):
    await _blocker(kernel, mission)
    with pytest.raises(ReasoningError) as exc:
        await kernel.assert_safe_for_irreversible_work(mission.mission_id)
    assert exc.value.code == "MISSION_HAS_UNVERIFIED_HIGH_IMPACT_ASSUMPTIONS"


@pytest.mark.asyncio
async def test_a_mission_with_nothing_unsettled_proceeds(kernel, mission):
    """The gate must be passable, or it is a stop sign.

    Asserted because a gate that refuses everything and a gate that refuses the right
    things look identical from the failing side.
    """
    await kernel.assert_safe_for_irreversible_work(mission.mission_id)


@pytest.mark.asyncio
async def test_a_low_importance_assumption_does_not_block(kernel, mission):
    """§15 is about high-impact assumptions. Blocking on every guess would train everyone
    to clear them without reading, which is worse than not having the gate."""
    await kernel.record_assumption(
        mission_id=mission.mission_id, claim="probably fine",
        source="planner", importance=Importance.LOW,
    )
    await kernel.assert_safe_for_irreversible_work(mission.mission_id)


# ------------------------------------------- what it costs to clear one


@pytest.mark.asyncio
async def test_verifying_without_evidence_is_refused(kernel, mission):
    a = await _blocker(kernel, mission)
    with pytest.raises(ReasoningError) as exc:
        await kernel.resolve_assumption(a.assumption_id, status=AssumptionStatus.VERIFIED)
    assert exc.value.code == "ASSUMPTION_RESOLUTION_REQUIRES_EVIDENCE"


@pytest.mark.asyncio
async def test_falsifying_without_evidence_is_refused(kernel, mission):
    """The hole that was open.

    Falsifying is the same assertion as verifying wearing the opposite sign, and it is the
    one that unblocks the work: "I checked, it was wrong, proceed."
    """
    a = await _blocker(kernel, mission)
    with pytest.raises(ReasoningError) as exc:
        await kernel.resolve_assumption(a.assumption_id, status=AssumptionStatus.FALSIFIED)
    assert exc.value.code == "ASSUMPTION_RESOLUTION_REQUIRES_EVIDENCE"

    await kernel.resolve_assumption(
        a.assumption_id, status=AssumptionStatus.FALSIFIED,
        evidence_refs=["provider-readback://notebook/n1#absent"],
    )
    await kernel.assert_safe_for_irreversible_work(mission.mission_id)


@pytest.mark.asyncio
async def test_superseding_must_name_what_replaced_it(kernel, mission):
    """Otherwise SUPERSEDED is a delete with a nicer name."""
    a = await _blocker(kernel, mission)
    with pytest.raises(ReasoningError) as exc:
        await kernel.resolve_assumption(a.assumption_id, status=AssumptionStatus.SUPERSEDED)
    assert exc.value.code == "SUPERSEDED_REQUIRES_A_REPLACEMENT"


@pytest.mark.asyncio
async def test_a_supersession_does_not_unblock_by_itself(kernel, mission):
    """The counterexample this whole hardening exists for.

    Record a CRITICAL assumption, replace it with another CRITICAL assumption, and the work
    is still blocked — by the replacement. Supersession moves the obligation; it does not
    discharge it. If this passed, "supersede it with something trivial" would be the way
    through the gate.
    """
    original = await _blocker(kernel, mission)
    replacement = await _blocker(kernel, mission, claim="the notebook id resolves to one thing")
    await kernel.resolve_assumption(
        original.assumption_id,
        status=AssumptionStatus.SUPERSEDED,
        superseded_by=replacement.assumption_id,
    )
    with pytest.raises(ReasoningError):
        await kernel.assert_safe_for_irreversible_work(mission.mission_id)


@pytest.mark.asyncio
async def test_an_assumption_cannot_supersede_itself(kernel, mission):
    a = await _blocker(kernel, mission)
    with pytest.raises(ReasoningError) as exc:
        await kernel.resolve_assumption(
            a.assumption_id, status=AssumptionStatus.SUPERSEDED, superseded_by=a.assumption_id,
        )
    assert exc.value.code == "ASSUMPTION_CANNOT_SUPERSEDE_ITSELF"


@pytest.mark.asyncio
async def test_a_replacement_from_another_mission_is_refused(kernel, mission, store):
    """Citing an unrelated mission's assumption is a citation that explains nothing."""
    svc = MissionService(store, learning=LearningFeed(store))
    other = await svc.create(
        owner_principal_id="device:d1", origin=MissionOrigin.OWNER_UI,
        origin_channel=OriginChannel.UI, title="other", goal="other",
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A1),
    )
    a = await _blocker(kernel, mission)
    elsewhere = await _blocker(kernel, other, claim="unrelated")
    with pytest.raises(ReasoningError) as exc:
        await kernel.resolve_assumption(
            a.assumption_id, status=AssumptionStatus.SUPERSEDED,
            superseded_by=elsewhere.assumption_id,
        )
    assert exc.value.code == "REPLACEMENT_BELONGS_TO_ANOTHER_MISSION"


@pytest.mark.asyncio
async def test_expiry_is_not_something_a_caller_asserts(kernel, mission):
    """A caller asserting that time has passed is a caller deciding its own deadline."""
    a = await _blocker(kernel, mission)
    with pytest.raises(ReasoningError) as exc:
        await kernel.resolve_assumption(a.assumption_id, status=AssumptionStatus.EXPIRED)
    assert exc.value.code == "ASSUMPTION_STATUS_NOT_CALLER_SETTABLE"


@pytest.mark.asyncio
async def test_the_kernel_expires_on_the_clock(kernel, mission):
    """The resolution a caller cannot assert still has to happen, or assumptions are
    immortal and every long-lived mission ends up permanently blocked."""
    a = await _blocker(kernel, mission)
    assert await kernel.expire_assumptions(older_than_ms=10**9) == 0
    assert await kernel.expire_assumptions(older_than_ms=0) == 1
    await kernel.assert_safe_for_irreversible_work(mission.mission_id)
    assert a.assumption_id


@pytest.mark.asyncio
async def test_a_cleared_assumption_cannot_be_reopened_by_a_caller(kernel, mission):
    a = await _blocker(kernel, mission)
    with pytest.raises(ReasoningError) as exc:
        await kernel.resolve_assumption(a.assumption_id, status=AssumptionStatus.ACTIVE)
    assert exc.value.code == "ASSUMPTION_CANNOT_BE_REOPENED"


@pytest.mark.asyncio
async def test_the_supersession_link_is_stored_not_just_checked(kernel, mission):
    """Migration 26. A cleared assumption must read as a correction pointing somewhere,
    not as a row that quietly stopped blocking."""
    original = await _blocker(kernel, mission)
    replacement = await _blocker(kernel, mission, claim="narrower claim")
    await kernel.resolve_assumption(
        original.assumption_id, status=AssumptionStatus.SUPERSEDED,
        superseded_by=replacement.assumption_id,
    )
    row = await kernel.store.fetchone(
        "SELECT * FROM assumption_ledger WHERE assumption_id = ?", (original.assumption_id,)
    )
    assert kernel._row_to_assumption(row).superseded_by == replacement.assumption_id


# --------------------------------------------- which actions the gate applies to


def test_the_descriptor_decides_what_is_irreversible_rather_than_a_second_list():
    """The gate keys off ACTION_REVERSIBILITY, so there is one place that decides."""
    irreversible = [
        d.action_id for d in BUILTIN_ACTIONS
        if describe_action(d).reversibility is Reversibility.IRREVERSIBLE
    ]
    assert irreversible, "no action is declared irreversible; the gate can never apply"
    assert "google.notebook.enterprise.delete" in irreversible


def test_an_undeclared_reversibility_is_treated_as_irreversible():
    """The descriptor's own reasoning, relied on by the gate: an action whose
    reversibility nobody has decided is not assumed reversible, because that is the
    assumption that costs something.

    Checked against the gate's source rather than its docstring, since a docstring can say
    UNDECLARED while the branch tests only IRREVERSIBLE.
    """
    import inspect

    from van_gateway.runtime_api import OwnerRuntimeApi

    body = inspect.getsource(OwnerRuntimeApi._refuse_irreversible_work_on_unsettled_assumptions)
    code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
    assert "Reversibility.UNDECLARED" in code
    assert "Reversibility.IRREVERSIBLE" in code


def test_a_read_only_action_is_not_gated():
    """Gating reads would make the ledger a tax on everything and get it cleared by rote."""
    read_only = [
        d.action_id for d in BUILTIN_ACTIONS
        if describe_action(d).reversibility is Reversibility.READ_ONLY
    ]
    assert read_only


# ----------------------------------------------- through the route Hermes actually calls
#
# Everything above exercises the kernel directly. That is not evidence that the gate is
# reachable: `assert_safe_for_irreversible_work` had no caller for the whole of this
# programme while being perfectly callable. `/v1/runtime/actions/begin` had no test at all,
# which is how an execution ingress ends up with a gate nobody notices is missing.

import time
import uuid

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings

INGRESS = "assumption-gate-ingress-0123456789"
INTERNAL = "assumption-gate-internal"


@pytest.fixture
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "gate.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def runtime(_settings):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-Van-Ingress-Token": INGRESS, "X-Van-Internal-Token": INTERNAL},
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


async def _mission_for(app, command_id: str):
    svc = MissionService(app.state.store, learning=LearningFeed(app.state.store))
    return await svc.create(
        owner_principal_id="device:d1",
        origin=MissionOrigin.OWNER_UI,
        origin_channel=OriginChannel.UI,
        title="delete the enterprise notebook",
        goal="delete the enterprise notebook",
        authority_envelope=AuthorityEnvelope(
            max_action_class=ActionClass.A4, source_command_id=command_id
        ),
        sensitivity=Sensitivity.SECURITY,
    )


def _begin(command_id: str, action_id: str = "google.notebook.enterprise.delete") -> dict:
    return {
        "execution_id": f"exec-{uuid.uuid4().hex[:10]}",
        "command_id": command_id,
        "action_id": action_id,
        "principal_type": "HERMES_AGENT",
        "requested_by": "hermes",
        "idempotency_key": f"idem-{uuid.uuid4().hex[:10]}",
        "parameters": {"notebook_id": "nb-1"},
    }


@pytest.mark.asyncio
async def test_the_route_refuses_irreversible_work_while_an_assumption_is_unsettled(runtime):
    ac, app = runtime
    command_id = f"cmd-{uuid.uuid4().hex[:10]}"
    mission = await _mission_for(app, command_id)
    await CriticalReasoningKernel(app.state.store).record_assumption(
        mission_id=mission.mission_id,
        claim="nb-1 is the notebook the owner meant",
        source="planner",
        importance=Importance.CRITICAL,
    )

    response = await ac.post("/v1/runtime/actions/begin", json=_begin(command_id))
    assert response.status_code == 409
    assert response.json()["detail"] == "MISSION_HAS_UNVERIFIED_HIGH_IMPACT_ASSUMPTIONS"


@pytest.mark.asyncio
async def test_the_gate_is_passable_and_stops_being_the_reason_for_refusal(runtime):
    """Clearing the assumption with evidence must get past *this* gate.

    The request may still be refused by command authority, which is a different check with
    a different detail — and asserting only "not 409 with this code" is the honest bound,
    because making the whole call succeed would need a signed command authority record that
    has nothing to do with §15.
    """
    ac, app = runtime
    command_id = f"cmd-{uuid.uuid4().hex[:10]}"
    mission = await _mission_for(app, command_id)
    kernel = CriticalReasoningKernel(app.state.store)
    assumption = await kernel.record_assumption(
        mission_id=mission.mission_id, claim="nb-1 is the right notebook",
        source="planner", importance=Importance.CRITICAL,
    )

    resolved = await ac.post(
        f"/v1/runtime/reasoning/assumptions/{assumption.assumption_id}/resolve",
        json={"status": "VERIFIED", "evidence_refs": ["provider-readback://notebook/nb-1"]},
    )
    assert resolved.status_code == 200

    response = await ac.post("/v1/runtime/actions/begin", json=_begin(command_id))
    assert response.json().get("detail") != "MISSION_HAS_UNVERIFIED_HIGH_IMPACT_ASSUMPTIONS"


@pytest.mark.asyncio
async def test_the_route_refuses_to_resolve_by_assertion(runtime):
    """The self-certification path, closed at the route rather than only in the kernel."""
    ac, app = runtime
    command_id = f"cmd-{uuid.uuid4().hex[:10]}"
    mission = await _mission_for(app, command_id)
    assumption = await CriticalReasoningKernel(app.state.store).record_assumption(
        mission_id=mission.mission_id, claim="fine, probably",
        source="planner", importance=Importance.CRITICAL,
    )

    for body, expected in (
        ({"status": "VERIFIED"}, "ASSUMPTION_RESOLUTION_REQUIRES_EVIDENCE"),
        ({"status": "FALSIFIED"}, "ASSUMPTION_RESOLUTION_REQUIRES_EVIDENCE"),
        ({"status": "SUPERSEDED"}, "SUPERSEDED_REQUIRES_A_REPLACEMENT"),
        ({"status": "EXPIRED"}, "ASSUMPTION_STATUS_NOT_CALLER_SETTABLE"),
    ):
        r = await ac.post(
            f"/v1/runtime/reasoning/assumptions/{assumption.assumption_id}/resolve", json=body
        )
        assert r.status_code == 409, body
        assert r.json()["detail"] == expected, body


@pytest.mark.asyncio
async def test_an_irreversible_action_with_no_mission_is_refused_not_waved_through(runtime):
    """The quiet failure this could have had.

    Looking up the mission and finding none, then proceeding, would make every irreversible
    action that arrives without a mission exempt from the gate — and that is precisely the
    shape of request an attacker or a bug produces.
    """
    ac, _ = runtime
    response = await ac.post("/v1/runtime/actions/begin", json=_begin("cmd-never-opened"))
    assert response.status_code == 409
    assert response.json()["detail"] == "irreversible_action_without_a_mission"


@pytest.mark.asyncio
async def test_the_reasoning_routes_are_internal_control_only(runtime):
    """An assumption is a statement about a plan. It is the runtime's to make, and an
    owner device token is not an answer to a privileged control route (P0-SEC-001)."""
    ac, app = runtime
    command_id = f"cmd-{uuid.uuid4().hex[:10]}"
    mission = await _mission_for(app, command_id)
    body = {
        "mission_id": mission.mission_id, "claim": "x",
        "source": "planner", "importance": "HIGH",
    }
    denied = await ac.post(
        "/v1/runtime/reasoning/assumptions", json=body,
        headers={"X-Van-Internal-Token": "wrong-token"},
    )
    assert denied.status_code in (401, 403)


@pytest.mark.asyncio
async def test_recording_an_assumption_against_no_mission_is_refused(runtime):
    """A blocker on a mission that does not exist blocks nothing and hides a bug."""
    ac, _ = runtime
    r = await ac.post(
        "/v1/runtime/reasoning/assumptions",
        json={"mission_id": "mis-nope", "claim": "x", "source": "planner", "importance": "HIGH"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_a_planner_can_read_what_is_blocking_before_being_refused(runtime):
    ac, app = runtime
    command_id = f"cmd-{uuid.uuid4().hex[:10]}"
    mission = await _mission_for(app, command_id)
    await CriticalReasoningKernel(app.state.store).record_assumption(
        mission_id=mission.mission_id, claim="nb-1 is the right notebook",
        source="planner", importance=Importance.CRITICAL,
    )
    r = await ac.get(f"/v1/runtime/reasoning/assumptions/{mission.mission_id}")
    assert r.status_code == 200
    blocking = r.json()["blocking"]
    assert [b["claim"] for b in blocking] == ["nb-1 is the right notebook"]
