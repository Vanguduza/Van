"""van-private-core service (owner decision 2026-09-29 §3): bounded authenticated API only."""

from __future__ import annotations

import httpx
import pytest
from conftest_automation import make_store

from van_gateway.config import Settings
from van_gateway.evolution.vaneval import EvalDimension, VanEval
from van_gateway.private_core.app import PRIVATE_CORE_ROUTES, create_private_core_app
from van_gateway.understanding.owner_model import (
    ObservationOrigin,
    OwnerCognitiveModel,
    OwnerModelField,
)
from van_gateway.understanding.personal_context_resolver import PERSONAL_CONTEXT_UNAVAILABLE

TOKEN = "private-core-understanding-0123456789abcdef"


async def _seed(store, *names):
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    missions = MissionService(store)
    out = {}
    for name in names:
        m = await missions.create(owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
                                  origin_channel=OriginChannel.VOICE, title=name, goal=name)
        out[name] = f"mission:{m.mission_id}"
    return out


async def _observed(store, value="terse"):
    model = OwnerCognitiveModel(store)
    eps = await _seed(store, "s1", "s2", "s3")
    for n in ("s1", "s2", "s3"):
        a = await model.observe(owner_principal_id="owner",
                                field=OwnerModelField.COMMUNICATION_PREFERENCE, value=value,
                                episode_ref=eps[n], origin=ObservationOrigin.SYSTEM_OBSERVED)
    return model, a


@pytest.fixture
async def client(tmp_path):
    store = await make_store(tmp_path)
    app = create_private_core_app(
        Settings(internal_control_scoped_tokens=f"understanding:{TOKEN}"), store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://pc") as c:
            yield c, store, app


async def test_only_the_declared_routes_exist(client):
    _, _, app = client
    routes = {(m, r.path) for r in app.routes if hasattr(r, "methods")
              for m in r.methods if m != "HEAD"}
    assert routes == set(PRIVATE_CORE_ROUTES)


@pytest.mark.parametrize("method,path", PRIVATE_CORE_ROUTES)
async def test_every_route_refuses_without_the_scoped_credential(client, method, path):
    c, _, _ = client
    params = {"owner_model_revision": 1, "purpose": "p"}
    for headers in ({}, {"X-Van-Internal-Token": "wrong-" + TOKEN}):
        r = await c.request(method, path, params=params, headers=headers)
        assert r.status_code == 403, (path, headers, r.text)


async def test_personal_context_is_fenced_through_the_private_core_api(client):
    c, store, _ = client
    model, a = await _observed(store)
    h = {"X-Van-Internal-Token": TOKEN}
    rev = (await c.get("/v1/private-core/owner-model/revision", headers=h)).json()
    assert rev["zone"] == "van-private-core"
    n = rev["owner_model_revision"]
    ok = await c.get("/v1/private-core/personal-context", headers=h,
                     params={"owner_model_revision": n, "purpose": "reply-style"})
    assert ok.status_code == 200, ok.text
    assert [i["value"] for i in ok.json()["content"]["assertions"]] == ["terse"]
    await model.correct(a.assertion_id, new_value="verbose")
    stale = await c.get("/v1/private-core/personal-context", headers=h,
                        params={"owner_model_revision": n, "purpose": "reply-style"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == PERSONAL_CONTEXT_UNAVAILABLE


async def test_missing_revision_row_is_409_not_zero(client):
    c, _, _ = client
    r = await c.get("/v1/private-core/owner-model/revision",
                    headers={"X-Van-Internal-Token": TOKEN})
    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "AUTHORITATIVE_REVISION_MISSING"


# VanEval's knowledge dimension now reads the Owner Model through `integrity_counts()`
# rather than its table; these pin the behaviour the refactor must preserve.


async def _knowledge(store):
    report = await VanEval(store).run(now_ms=1)
    [dim] = [d for d in report["dimensions"]
             if d["dimension"] == EvalDimension.KNOWLEDGE_MEMORY.value]
    return dim


async def test_vaneval_knowledge_unmeasured_without_assertions(tmp_path):
    dim = await _knowledge(await make_store(tmp_path))
    assert dim["measured"] is False


async def test_vaneval_knowledge_counts_through_the_owner_model(tmp_path):
    store = await make_store(tmp_path)
    await _observed(store)
    dim = await _knowledge(store)
    assert dim["measured"] is True and dim["score"] == 9.6
    assert dim["details"] == {"assertions": 1, "autonomy_traits_confirmed_without_owner": 0}
    # An autonomy-bearing CONFIRMED row with no owner confirmation zeroes the score.
    await store.execute(
        "INSERT INTO owner_cognitive_model(assertion_id, owner_principal_id, field, value, "
        "state, created_at_ms, updated_at_ms) VALUES ('oa_x','owner','delegation_preferences',"
        "'act','CONFIRMED',1,1)")
    dim = await _knowledge(store)
    assert dim["score"] == 0.0
    assert dim["details"] == {"assertions": 2, "autonomy_traits_confirmed_without_owner": 1}
