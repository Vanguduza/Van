"""Rev 1 §§5, 33-34, 42-43, 45 — binding, the owner surface, and the red team.

Mission Core is only worth having if the work VAN actually does appears in it,
so the first half of this file proves the binding is a *reference* — idempotent,
reversible, and always deferring to the subsystem that owns the execution.

The second half is §45. Not every red-team case applies to what exists yet; the
ones that do are written as attacks and each must fail closed.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from conftest_automation import make_store, sample_artifact, sample_capability
from van_gateway.automation.models import WorkflowLifecycle
from van_gateway.automation.registry import AutomationRegistry
from van_gateway.automation.external_runtime import (
    ExternalRuntimeRegistry,
    ReadinessEvidence,
)
from van_gateway.capability.readiness import (
    AutomationReadiness,
    ExternalRuntimeReadiness,
)
from van_gateway.capability.models import ReadinessSource
from van_gateway.capability.registry import CapabilityRegistry
from van_gateway.capability.router import CapabilityRouter
from van_gateway.config import get_settings
from van_gateway.mission.api import MissionApi
from van_gateway.mission.binding import MissionBinder
from van_gateway.mission.models import (
    ActivityState,
    AuthorityEnvelope,
    MissionOrigin,
    MissionState,
    SuccessContract,
    VerificationRecord,
    VerificationStatus,
)
from van_gateway.mission.service import MissionService
from van_gateway.mission.verifiers import ObservationVerifier, VerifierRegistry
from van_gateway.models import ActionClass, OriginChannel

INTERNAL = "test-internal-token"
HEADERS = {"X-Van-Internal-Token": INTERNAL}


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "m.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "ingress-token-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _stack(tmp_path, *, automation_enabled=True):
    store = await make_store(tmp_path)
    runtime = ExternalRuntimeRegistry(store)
    # The browser worker is proven ready here so binding can be tested; the
    # registry refusing an unprobed source is its own test elsewhere.
    await runtime.record_evidence(
        ReadinessEvidence(
            capability="stagehand", evidence_pointer="gateway://cert/1",
            runtime_version="1.0.0",
        )
    )
    registry = CapabilityRegistry(
        store,
        probes={
            ReadinessSource.AUTOMATION_REGISTRY: AutomationReadiness(
                store, enabled=automation_enabled
            ),
            ReadinessSource.EXTERNAL_RUNTIME: ExternalRuntimeReadiness(runtime, enabled=True),
        },
    )
    registry.load()
    await registry.sync()
    # P0-VERIFY-001 — a registry whose adapter observes a world the test controls. The
    # adapter still writes the receipt, so a test can stage the world and still cannot
    # stage the verdict.
    async def _readback(context):
        return {"exists": True, "evidence_refs": ["readback://1"]}

    verifiers = VerifierRegistry()
    verifiers.register(
        "readback",
        ObservationVerifier(_readback, verifier_version="readback/1",
                            evidence_prefix="readback://"),
    )
    missions = MissionService(store, capabilities=registry, verifiers=verifiers)
    router = CapabilityRouter(store, registry)
    api = MissionApi(store, get_settings(), missions=missions, registry=registry, router=router)
    app = FastAPI()
    app.include_router(api.router)
    return store, missions, registry, api, app


@pytest_asyncio.fixture
async def stack(tmp_path):
    store, missions, registry, api, app = await _stack(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        yield ac, store, missions, registry, api


async def _mission(missions, **overrides):
    body = dict(
        owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE, title="Collect statements",
        goal="collect this month's broker statements",
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A3),
    )
    body.update(overrides)
    return await missions.create(**body)


async def _seed_browser_task(store, task_id="btask_1", status="PENDING"):
    await store.execute(
        "INSERT INTO browser_profiles(profile_alias, persistence, authentication, "
        "mutation_policy, secret_ref, created_at_ms, updated_at_ms) "
        "VALUES ('public_research','ephemeral','none','forbidden',NULL,1,1) "
        "ON CONFLICT(profile_alias) DO NOTHING", ()
    )
    await store.execute(
        """
        INSERT INTO browser_tasks(task_id, command_id, execution_id, capability_id,
          profile_alias, strategy, autonomy_tier, action_class, target_domain, goal,
          status, evidence_pointer, error_code, started_at_ms, completed_at_ms, updated_at_ms)
        VALUES (?, NULL, NULL, NULL, 'public_research', 'STAGEHAND', 'L4_STAGEHAND_ACT',
                'A2', 'x.example.com', 'read', ?, NULL, NULL, 1, NULL, 1)
        """,
        (task_id, status),
    )


# ------------------------------------------------------------------ binding


async def test_binding_is_a_reference_not_a_move(tmp_path):
    """§5 — the subsystem row stays; the Activity points at it."""
    store, missions, _registry, _api, _app = await _stack(tmp_path)
    mission = await _mission(missions)
    await _seed_browser_task(store)
    binder = MissionBinder(store, missions)

    activity_id = await binder.bind_browser_task(
        mission_id=mission.mission_id, task_id="btask_1"
    )
    assert activity_id is not None
    activities = await missions.activities(mission.mission_id)
    assert activities[0].executor_ref == "btask_1"
    # The browser task is untouched by being bound.
    row = await store.fetchone("SELECT status FROM browser_tasks WHERE task_id = 'btask_1'")
    assert row["status"] == "PENDING"


async def test_binding_the_same_row_twice_creates_one_activity(tmp_path):
    store, missions, _r, _a, _app = await _stack(tmp_path)
    mission = await _mission(missions)
    await _seed_browser_task(store)
    binder = MissionBinder(store, missions)

    first = await binder.bind_browser_task(mission_id=mission.mission_id, task_id="btask_1")
    second = await binder.bind_browser_task(mission_id=mission.mission_id, task_id="btask_1")
    assert first is not None and second is None
    assert len(await missions.activities(mission.mission_id)) == 1


async def test_the_subsystem_wins_when_the_activity_disagrees(tmp_path):
    """Pull, never push: browser_tasks was authoritative first and still is."""
    store, missions, _r, _a, _app = await _stack(tmp_path)
    mission = await _mission(missions)
    await _seed_browser_task(store)
    binder = MissionBinder(store, missions)
    await binder.bind_browser_task(mission_id=mission.mission_id, task_id="btask_1")

    await store.execute(
        "UPDATE browser_tasks SET status = 'COMPLETED', evidence_pointer = 'bevd://1' "
        "WHERE task_id = 'btask_1'"
    )
    synced = await binder.sync_from_subsystems(mission.mission_id)
    assert synced == 1
    assert (await missions.activities(mission.mission_id))[0].state is ActivityState.COMPLETED
    # Syncing again is a no-op rather than a second event.
    assert await binder.sync_from_subsystems(mission.mission_id) == 0


async def test_backfill_is_idempotent_and_reversible(tmp_path):
    """§42 — deterministic and reversible, proven rather than asserted."""
    store, missions, _r, _a, _app = await _stack(tmp_path)
    mission = await _mission(missions)
    for i in range(3):
        await _seed_browser_task(store, task_id=f"btask_{i}")
    binder = MissionBinder(store, missions)

    first = await binder.backfill(mission_id=mission.mission_id)
    assert first.browser_tasks_bound == 3
    second = await binder.backfill(mission_id=mission.mission_id)
    assert second.browser_tasks_bound == 0
    assert second.already_bound == 3

    removed = await binder.unbind_all(mission.mission_id)
    assert removed == 3
    assert await missions.activities(mission.mission_id) == []
    # Nothing was lost: the subsystem rows are still there to rebind from.
    rebuilt = await binder.backfill(mission_id=mission.mission_id)
    assert rebuilt.browser_tasks_bound == 3


async def test_backfill_will_not_attach_a_capability_the_envelope_forbids(tmp_path):
    """§7 holds during backfill too — adoption is not a way around policy."""
    store, missions, _r, _a, _app = await _stack(tmp_path, automation_enabled=True)
    automation = AutomationRegistry(store)
    await automation.upsert_capability(sample_capability())
    await automation.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))
    await store.execute(
        "INSERT INTO automation_runs(run_id, capability_id, artifact_id, status, action_class, "
        "input_digest, started_at_ms, updated_at_ms) "
        "VALUES ('wfrun_1','wfcap_statements','art','PENDING','A3','d',1,1)"
    )
    # An A2 mission cannot adopt A3 automation work.
    a2 = await _mission(
        missions, authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A2)
    )
    report = await MissionBinder(store, missions).backfill(mission_id=a2.mission_id)
    assert report.automation_runs_bound == 0
    assert report.unbindable == 1


# -------------------------------------------------------------- owner surface


async def test_needs_you_is_one_surface(stack):
    """§33 — missions waiting plus open decisions, counted together."""
    ac, store, missions, _r, _a = stack
    mission = await _mission(missions)
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING, MissionState.WAITING_FOR_OWNER):
        await missions.transition(mission.mission_id, target=target)
    await store.execute(
        "INSERT INTO decisions(id, title, body, source, status, created_at_unix, "
        "updated_at_unix) VALUES ('d1','Approve scope','body','browser','OPEN',1,1)"
    )
    body = (await ac.get("/v1/needs-you")).json()
    assert body["count"] == 2
    assert body["missions"][0]["needs_owner"] is True
    assert body["decisions"][0]["id"] == "d1"


async def test_home_can_answer_what_van_is_working_on(stack):
    """§33's five-second question, as one request."""
    ac, _store, missions, _r, _a = stack
    running = await _mission(missions, title="running one")
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING):
        await missions.transition(running.mission_id, target=target)
    done = await _mission(missions, title="finished one")
    await missions.transition(done.mission_id, target=MissionState.CANCELLED)

    active = (await ac.get("/v1/missions?active=true")).json()
    assert [m["title"] for m in active] == ["running one"]


async def test_the_evidence_route_gathers_receipt_and_route_decisions(stack):
    """§34 — the proof for a mission in one place."""
    ac, _store, missions, registry, api = stack
    mission = await _mission(
        missions,
        success_contract=SuccessContract(
            postconditions={"exists": True}, verifier_class="readback"
        ),
    )
    from van_gateway.capability.models import CapabilityClass

    await api.capability_router.route(
        goal_class="LOOKUP", candidate_classes=[CapabilityClass.NATIVE_READ],
        mission_id=mission.mission_id,
    )
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING, MissionState.VERIFYING):
        await missions.transition(mission.mission_id, target=target)
    await missions.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
    body = (await ac.get(f"/v1/missions/{mission.mission_id}/evidence")).json()
    assert body["verification"]["status"] == "VERIFIED"
    assert "readback://1" in body["evidence_refs"]
    assert len(body["route_decisions"]) == 1


async def test_capability_status_says_why_not(stack):
    """§43 — what VAN can do, and the reason where it cannot."""
    ac, _store, _m, registry, _a = stack
    body = (await ac.get("/v1/capabilities/status")).json()
    assert body["manifest_digest"] == registry.manifest_digest
    by_id = {c["capability_id"]: c for c in body["capabilities"]}
    assert by_id["trading.vati.submit_order"]["routable"] is False
    assert by_id["trading.vati.submit_order"]["reason"] == "NEVER_ROUTABLE"
    assert by_id["native.owner_context.read"]["routable"] is True


async def test_the_activity_feed_groups_by_mission(stack):
    ac, _store, missions, _r, _a = stack
    first = await _mission(missions, title="one")
    second = await _mission(missions, title="two")
    await missions.transition(first.mission_id, target=MissionState.UNDERSTOOD)
    body = (await ac.get("/v1/activity")).json()
    ids = {m["mission_id"] for m in body["missions"]}
    assert {first.mission_id, second.mission_id} <= ids


# --------------------------------------------------------------- §45 red team


async def test_red_team_android_cannot_forge_a_transition(stack):
    """§45.6 — Android tampering with action class / planning state.

    Cancel and message are the owner's. Everything that changes what VAN will
    *do* is internal-control, so an owner-authenticated client cannot drive the
    state machine.
    """
    ac, _store, missions, _r, _a = stack
    mission = await _mission(missions)
    # Reaches the route without the internal token — and the app-level guard is
    # what rejects it in production; here the route itself must also refuse.
    response = await ac.post(
        f"/v1/missions/{mission.mission_id}/transition", json={"target": "RUNNING"}
    )
    assert response.status_code in (401, 403)
    assert (await missions.get(mission.mission_id)).state is MissionState.CAPTURED


async def test_red_team_a_mission_cannot_forge_verification(stack):
    """§45.11 — mission tries to forge verification."""
    ac, _store, missions, _r, _a = stack
    mission = await _mission(
        missions,
        success_contract=SuccessContract(
            postconditions={"exists": True}, verifier_class="readback"
        ),
    )
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING, MissionState.VERIFYING):
        await missions.transition(mission.mission_id, target=target)

    forged = await ac.post(
        f"/v1/missions/{mission.mission_id}/transition", headers=HEADERS,
        json={
            "target": "VERIFIED_SUCCESS",
            "verification": {
                "status": "VERIFIED", "evidence_refs": [], "verifier_version": "forged/1",
                "verified_at_ms": 1,
            },
        },
    )
    # P0-VERIFY-001 — the route no longer has a field to put a receipt in, and it rejects
    # the request rather than ignoring the extra key, so a client still sending one is
    # told rather than left believing it was honoured.
    assert forged.status_code == 422, forged.text
    assert (await missions.get(mission.mission_id)).state is MissionState.VERIFYING

    # The same mission does reach success once the registered verifier is the one asked,
    # which is what makes the refusal above about provenance rather than about strictness.
    honest = await ac.post(
        f"/v1/missions/{mission.mission_id}/transition", headers=HEADERS,
        json={"target": "VERIFIED_SUCCESS"},
    )
    assert honest.status_code == 200, honest.text
    stored = await missions.verification_record(mission.mission_id)
    assert stored.verifier_version == "readback/1"
    assert stored.evidence_refs == ["readback://1"]


async def test_red_team_a_mission_cannot_reach_vati_execution(stack):
    """§45.9 — browser/generic fabric attempts a broker order bypassing VATI."""
    ac, _store, missions, _r, _a = stack
    mission = await _mission(
        missions, authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A4)
    )
    response = await ac.post(
        f"/v1/missions/{mission.mission_id}/activities", headers=HEADERS,
        json={
            "activity_type": "trade", "capability_id": "trading.vati.submit_order",
            "executor": "BROWSER_FABRIC",
        },
    )
    assert response.status_code == 403
    assert "NEVER_ROUTABLE" in response.json()["detail"]["error"]


async def test_red_team_an_undeclared_capability_cannot_become_work(stack):
    """§7 — not in the registry, not routable, therefore not an Activity."""
    ac, _store, missions, _r, _a = stack
    mission = await _mission(missions)
    response = await ac.post(
        f"/v1/missions/{mission.mission_id}/activities", headers=HEADERS,
        json={
            "activity_type": "anything", "capability_id": "shadow.capability",
            "executor": "MYSTERY",
        },
    )
    assert response.status_code == 403
    assert "NOT_DECLARED" in response.json()["detail"]["error"]


async def test_red_team_a_mission_cannot_self_escalate_its_envelope(stack):
    """§45.16 — inferred preference / execution history widening autonomy.

    The envelope is set once from the authority that granted it. Asking for an
    A4 capability from an A2 mission is refused on the mission's own terms.
    """
    ac, _store, missions, _r, _a = stack
    mission = await _mission(
        missions, authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A2)
    )
    response = await ac.post(
        f"/v1/missions/{mission.mission_id}/activities", headers=HEADERS,
        json={
            "activity_type": "send", "capability_id": "google.gmail.send",
            "executor": "GOOGLE_MESH",
        },
    )
    assert response.status_code == 403
    assert "ABOVE_AUTHORITY_CEILING" in response.json()["detail"]["error"]


async def test_red_team_an_owner_message_does_not_move_the_mission(stack):
    """§2.3 — Android is not a planner. A note is a note."""
    ac, _store, missions, _r, _a = stack
    mission = await _mission(missions)
    response = await ac.post(
        f"/v1/missions/{mission.mission_id}/message", json={"message": "just do it"}
    )
    assert response.status_code == 200
    assert (await missions.get(mission.mission_id)).state is MissionState.CAPTURED


# ------------------------------------------------- execution binds itself


async def test_a_mission_scoped_browser_task_binds_itself(tmp_path):
    """§5 — the gap this closes: before, a browser task only became an Activity
    if someone ran backfill by hand, so the Missions page showed intentions
    while the real execution sat in browser_tasks.
    """
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from van_gateway.browser.api import BrowserApi

    store, missions, registry, _api, _app = await _stack(tmp_path)
    binder = MissionBinder(store, missions)
    browser = BrowserApi(store, get_settings(), binder=binder)
    app = FastAPI()
    app.include_router(browser.router)

    mission = await _mission(missions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await ac.post("/v1/browser/profiles", headers=HEADERS,
                      json={"profile_alias": "public_research"})
        response = await ac.post(
            "/v1/browser/tasks", headers=HEADERS,
            json={
                "profile_alias": "public_research", "strategy": "STAGEHAND",
                "autonomy_tier": "L4_STAGEHAND_ACT", "action_class": "A2",
                "target_domain": "portal.example.com", "goal": "read the statement",
                "mission_id": mission.mission_id,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["mission_binding"]["mission_id"] == mission.mission_id
        assert body["mission_binding"]["activity_id"]

    activities = await missions.activities(mission.mission_id)
    assert len(activities) == 1
    assert activities[0].executor == "BROWSER_FABRIC"
    assert activities[0].executor_ref == body["task_id"]


async def test_a_task_without_a_mission_still_works(tmp_path):
    """Binding is additive: the browser fabric does not require a Mission."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from van_gateway.browser.api import BrowserApi

    store, missions, _r, _a, _app = await _stack(tmp_path)
    browser = BrowserApi(store, get_settings(), binder=MissionBinder(store, missions))
    app = FastAPI()
    app.include_router(browser.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await ac.post("/v1/browser/profiles", headers=HEADERS,
                      json={"profile_alias": "public_research"})
        response = await ac.post(
            "/v1/browser/tasks", headers=HEADERS,
            json={
                "profile_alias": "public_research", "strategy": "STAGEHAND",
                "autonomy_tier": "L4_STAGEHAND_ACT", "action_class": "A2",
                "target_domain": "portal.example.com", "goal": "read",
            },
        )
        assert response.status_code == 200
        assert response.json()["mission_binding"] is None


async def test_a_binding_refusal_never_loses_the_task(tmp_path):
    """The browser task is already created and valid. A bookkeeping failure
    must be reported beside it, not raised over the top of it."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from van_gateway.browser.api import BrowserApi

    store, missions, _r, _a, _app = await _stack(tmp_path)
    browser = BrowserApi(store, get_settings(), binder=MissionBinder(store, missions))
    app = FastAPI()
    app.include_router(browser.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await ac.post("/v1/browser/profiles", headers=HEADERS,
                      json={"profile_alias": "public_research"})
        response = await ac.post(
            "/v1/browser/tasks", headers=HEADERS,
            json={
                "profile_alias": "public_research", "strategy": "STAGEHAND",
                "autonomy_tier": "L4_STAGEHAND_ACT", "action_class": "A2",
                "target_domain": "portal.example.com", "goal": "read",
                "mission_id": "msn_does_not_exist",
            },
        )
        assert response.status_code == 200
        binding = response.json()["mission_binding"]
        assert binding["activity_id"] is None
        assert "MISSION_UNKNOWN" in binding["detail"]
        # The task itself exists and is usable.
        task_id = response.json()["task_id"]
        assert (await ac.get(f"/v1/browser/tasks/{task_id}", headers=HEADERS)).status_code == 200


async def test_the_authority_surface_answers_what_van_may_do(stack):
    """P1-COH-003 — one page for the question seven vocabularies each answered partly.

    The rows are derived from the registries rather than stored, so `derived_from` names
    the authority each came from and a reader can go and check rather than taking this
    page's word for it.
    """
    ac, _store, _m, registry, _a = stack
    body = (await ac.get("/v1/authority")).json()
    assert body["manifest_digest"] == registry.manifest_digest
    by_subject = {row["subject"]: row for row in body["subjects"]}

    # Both registries are projected through the same descriptor, which is the point.
    assert {row["derived_from"] for row in body["subjects"]} == {
        "action.registry", "capability.registry",
    }

    # An A4 delete: owner in the loop, and not undoable.
    delete = by_subject["google.notebook.enterprise.delete"]
    assert delete["action_class"] == "A4"
    assert delete["gate"] == "OWNER_APPROVAL"
    assert delete["needs_owner_in_the_loop"] is True
    assert delete["reversibility"] == "IRREVERSIBLE"

    # An A5: refused whatever anyone signs, and reported as disabled rather than absent —
    # a forbidden action that simply vanished from the page would be indistinguishable
    # from one nobody declared.
    exfiltrate = by_subject["secret.exfiltrate"]
    assert exfiltrate["gate"] == "FORBIDDEN"
    assert exfiltrate["enabled"] is False

    # A read: nothing to ask, nothing to undo, nothing leaves.
    read = by_subject["owner.context.read"]
    assert read["gate"] == "DEVICE_SIGNATURE"
    assert read["needs_owner_in_the_loop"] is False
    assert read["reversibility"] == "READ_ONLY"
    assert read["egress"] == "NONE"


async def test_every_gate_the_authority_surface_uses_is_explained(stack):
    """A gate name with no explanation is a fifth vocabulary for the owner to learn."""
    ac, _store, _m, _r, _a = stack
    body = (await ac.get("/v1/authority")).json()
    used = {row["gate"] for row in body["subjects"]}
    assert used <= set(body["gates"])
    assert all(body["gates"][name].strip() for name in used)
