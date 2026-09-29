"""Memory Fabric contract C1 — only SYSTEM_OBSERVED episodes are evidence.

The defect this closes: `observe()` found the existing assertion by owner/field/value/
project and unioned the new episode ref into its support, whatever produced the
observation. A Hindsight-derived memory citing a real mission id was therefore a
legitimate-looking third episode, and three episodes make a non-autonomy assertion
EVIDENCED — which is actionable. Derived memory could make VAN act on its own guess.
"""

from __future__ import annotations

import pytest
from conftest_automation import make_store
from pydantic import ValidationError

from van_gateway.understanding.api import ObserveBody
from van_gateway.understanding.owner_model import (
    AssertionState,
    ObservationOrigin,
    OwnerCognitiveModel,
    OwnerModelError,
    OwnerModelField,
)

SYSTEM = ObservationOrigin.SYSTEM_OBSERVED
DERIVED = (
    ObservationOrigin.HINDSIGHT_DERIVED,
    ObservationOrigin.OPENVIKING_RETRIEVED,
    ObservationOrigin.MODEL_INFERRED,
)
FIELD = OwnerModelField.COMMUNICATION_PREFERENCE


async def seed_episodes(store, *names: str) -> dict[str, str]:
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    missions = MissionService(store)
    out: dict[str, str] = {}
    for name in names:
        mission = await missions.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title=name, goal=name,
        )
        out[name] = f"mission:{mission.mission_id}"
    return out


async def _observe(model, ref, origin, *, field=FIELD, value="terse", project_id=None):
    return await model.observe(
        owner_principal_id="owner", field=field, value=value, episode_ref=ref,
        origin=origin, project_id=project_id,
    )


async def _not_actionable(model, assertion) -> None:
    assert assertion.may_act_on is False
    assert assertion.state not in (AssertionState.EVIDENCED, AssertionState.CONFIRMED)
    assert assertion.assertion_id not in {a.assertion_id for a in await model.actionable("owner")}
    stored = await model.get(assertion.assertion_id)
    assert stored.state is assertion.state and stored.may_act_on is False


@pytest.mark.parametrize("derived", DERIVED, ids=lambda o: o.value)
async def test_two_system_then_derived_third_is_not_actionable(tmp_path, derived):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "s2", "cited")
    await _observe(model, eps["s1"], SYSTEM)
    await _observe(model, eps["s2"], SYSTEM)
    third = await _observe(model, eps["cited"], derived)

    assert third.evidencing_episode_count == 2
    assert third.state is AssertionState.CANDIDATE
    assert third.derived_episode_refs == [eps["cited"]]
    assert {(e.episode_ref, e.origin) for e in third.episodes} == {
        (eps["s1"], SYSTEM), (eps["s2"], SYSTEM), (eps["cited"], derived),
    }
    # The derived ref is provenance, not support.
    assert eps["cited"] not in third.supporting_episode_refs
    await _not_actionable(model, third)


@pytest.mark.parametrize("derived", DERIVED, ids=lambda o: o.value)
async def test_derived_first_then_two_system_is_at_most_candidate(tmp_path, derived):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "cited", "s1", "s2")
    first = await _observe(model, eps["cited"], derived)
    assert first.state is AssertionState.OBSERVED
    assert first.evidencing_episode_count == 0
    assert first.confidence == 0.0, "derived-only support earns no confidence"
    await _observe(model, eps["s1"], SYSTEM)
    last = await _observe(model, eps["s2"], SYSTEM)
    assert last.evidencing_episode_count == 2
    assert last.state is AssertionState.CANDIDATE
    await _not_actionable(model, last)


async def test_any_number_of_derived_episodes_never_advance(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, *(f"d{i}" for i in range(6)))
    for i, ref in enumerate(eps.values()):
        a = await _observe(model, ref, DERIVED[i % 3])
    assert a.evidencing_episode_count == 0
    assert a.state is AssertionState.OBSERVED
    await _not_actionable(model, a)


async def test_same_episode_cited_by_derivation_then_observed_by_system_counts_once(tmp_path):
    """A derived row for an episode does not block that episode's own SYSTEM row."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "s2", "s3")
    await _observe(model, eps["s1"], ObservationOrigin.HINDSIGHT_DERIVED)
    for name in ("s1", "s2", "s3"):
        a = await _observe(model, eps[name], SYSTEM)
    assert a.evidencing_episode_count == 3
    assert a.state is AssertionState.EVIDENCED


async def test_three_system_episodes_preserve_existing_behaviour(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "s2", "s3")
    states = [(await _observe(model, eps[n], SYSTEM)).state for n in ("s1", "s2", "s3")]
    assert states == [AssertionState.OBSERVED, AssertionState.CANDIDATE, AssertionState.EVIDENCED]
    a = await model.get((await model.actionable("owner"))[0].assertion_id)
    assert a.may_act_on is True and a.evidencing_episode_count == 3
    assert a.state.is_owner_stated is False


async def test_autonomy_field_never_auto_reaches_evidenced(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, *(f"s{i}" for i in range(5)))
    for ref in eps.values():
        a = await _observe(model, ref, SYSTEM, field=OwnerModelField.DELEGATION_PREFERENCE)
    assert a.evidencing_episode_count == 5
    assert a.state is AssertionState.CANDIDATE
    assert a.may_act_on is False


async def test_owner_confirm_remains_strongest_and_reject_is_not_revived(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "d", "s1", "s2", "s3")
    derived_only = await _observe(model, eps["d"], ObservationOrigin.MODEL_INFERRED)
    confirmed = await model.confirm(derived_only.assertion_id)
    assert confirmed.state is AssertionState.CONFIRMED and confirmed.may_act_on

    other = await _observe(model, eps["s1"], SYSTEM, value="verbose")
    await model.reject(other.assertion_id)
    for name in ("s2", "s3"):
        again = await _observe(model, eps[name], SYSTEM, value="verbose")
    assert again.state is AssertionState.REJECTED and again.may_act_on is False


async def test_origin_is_required(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1")
    with pytest.raises(TypeError, match="origin"):
        await model.observe(  # type: ignore[call-arg]
            owner_principal_id="owner", field=FIELD, value="terse", episode_ref=eps["s1"],
        )
    for bad in (None, "", "SYSTEM", "hindsight"):
        with pytest.raises(OwnerModelError) as err:
            await model.observe(
                owner_principal_id="owner", field=FIELD, value="terse",
                episode_ref=eps["s1"], origin=bad,  # type: ignore[arg-type]
            )
        assert err.value.code == "OWNER_MODEL_ORIGIN_REQUIRED"
    with pytest.raises(OwnerModelError) as err:
        await _observe(model, eps["s1"], ObservationOrigin.OWNER_EXPLICIT)
    assert err.value.code == "OWNER_MODEL_ORIGIN_OWNER_PATH_ONLY"
    assert await store.fetchall("SELECT * FROM owner_cognitive_model") == []


def test_http_observe_body_requires_origin():
    base = {"owner_principal_id": "owner", "field": FIELD.value, "value": "terse",
            "episode_ref": "mission:x"}
    with pytest.raises(ValidationError):
        ObserveBody(**base)
    assert ObserveBody(**base, origin="HINDSIGHT_DERIVED").origin is ObservationOrigin.HINDSIGHT_DERIVED


async def test_derived_evidence_refs_do_not_become_assertion_evidence(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "d1")
    await model.observe(owner_principal_id="owner", field=FIELD, value="terse",
                        episode_ref=eps["s1"], origin=SYSTEM, evidence_refs=["audit:real"])
    a = await model.observe(owner_principal_id="owner", field=FIELD, value="terse",
                            episode_ref=eps["d1"], origin=ObservationOrigin.HINDSIGHT_DERIVED,
                            evidence_refs=["hindsight://bank/owner/mem-1"])
    assert a.evidence_refs == ["audit:real"]
    derived = next(e for e in a.episodes if e.origin is ObservationOrigin.HINDSIGHT_DERIVED)
    assert derived.evidence_refs == ["hindsight://bank/owner/mem-1"]


UNDERSTANDING = "understanding-scoped-token-0123456789abcdef"


@pytest.fixture
async def http(tmp_path, monkeypatch):
    import httpx

    from van_gateway.app import create_app
    from van_gateway.config import get_settings

    monkeypatch.setenv("VAN_INGRESS_TOKEN", "ingress-token-0123456789abcdef0123456789")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", f"understanding:{UNDERSTANDING}")
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "http.sqlite3"))
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://t") as ac:
            yield ac, str(tmp_path / "http.sqlite3")
    get_settings.cache_clear()


async def test_http_observe_route_requires_origin_and_revision_route_is_not_public(http):
    from van_gateway.storage.db import Store

    client, path = http
    eps = await seed_episodes(Store(path), "s1")
    headers = {"X-Van-Internal-Token": UNDERSTANDING}
    body = {"owner_principal_id": "owner", "field": FIELD.value, "value": "terse",
            "episode_ref": eps["s1"]}
    missing = await client.post("/v1/understanding/observe", json=body, headers=headers)
    assert missing.status_code == 422, missing.text
    ok = await client.post("/v1/understanding/observe", headers=headers,
                           json={**body, "origin": "HINDSIGHT_DERIVED"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"] == "OBSERVED" and ok.json()["supporting_episode_refs"] == []
    owner_path = await client.post("/v1/understanding/observe", headers=headers,
                                   json={**body, "origin": "OWNER_EXPLICIT"})
    assert owner_path.status_code == 422
    assert owner_path.json()["detail"] == "OWNER_MODEL_ORIGIN_OWNER_PATH_ONLY"
    # Owner-device authenticated like the rest of /v1/understanding; not open to anyone.
    anonymous = await client.get("/v1/understanding/revision")
    assert anonymous.status_code in (401, 403), anonymous.text


async def test_revision_route_returns_the_c2_document(tmp_path):
    """The router alone (auth is the app middleware's, covered above)."""
    import httpx
    from fastapi import FastAPI

    from van_gateway.config import Settings
    from van_gateway.understanding.api import UnderstandingApi

    store = await make_store(tmp_path)
    api = UnderstandingApi(store, Settings())
    eps = await seed_episodes(store, "s1")
    await _observe(api.owner_model, eps["s1"], SYSTEM)
    app = FastAPI()
    app.include_router(api.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/understanding/revision", params={"owner_principal_id": "owner"})
    body = r.json()
    assert r.status_code == 200
    assert set(body) == {"schema", "owner_principal_id", "owner_model_revision", "as_of_ms"}
    assert body["schema"] == "van.owner_model.revision.v1"
    assert body["owner_principal_id"] == "owner" and body["owner_model_revision"] == 1
    assert isinstance(body["as_of_ms"], int)
