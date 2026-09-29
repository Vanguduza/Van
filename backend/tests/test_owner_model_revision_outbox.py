"""Memory Fabric C2 (owner_model_revision), the correction outbox, and C3 capsules."""

from __future__ import annotations

import pytest
from conftest_automation import make_store

from van_gateway.context.forget import OwnerMemory
from van_gateway.understanding import owner_model_outbox as outbox_mod
from van_gateway.understanding.owner_model import (
    REVISION_SCHEMA,
    AssertionState,
    ObservationOrigin,
    OwnerCognitiveModel,
    OwnerModelField,
)
from van_gateway.understanding.owner_model_outbox import (
    OutboxDeliveryError,
    OutboxTarget,
    drain_outbox,
)
from van_gateway.understanding.personal_context import (
    CAPSULE_SCHEMA,
    build_personal_capsule,
    content_hash,
    verify_content_hash,
)

SYSTEM = ObservationOrigin.SYSTEM_OBSERVED
FIELD = OwnerModelField.COMMUNICATION_PREFERENCE


async def seed_episodes(store, *names: str) -> dict[str, str]:
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


async def _obs(model, ref, origin=SYSTEM, value="terse", field=FIELD, owner="owner"):
    return await model.observe(owner_principal_id=owner, field=field, value=value,
                               episode_ref=ref, origin=origin)


async def _outbox(store):
    return [dict(r) for r in await store.fetchall(
        "SELECT * FROM owner_model_outbox ORDER BY created_at_ms, outbox_id, target")]


# ------------------------------------------------------------------ C2 revision


async def test_revision_read_surface_shape(tmp_path):
    model = OwnerCognitiveModel(await make_store(tmp_path))
    assert await model.revision("owner", now_ms=123) == {
        "schema": REVISION_SCHEMA, "owner_principal_id": "owner",
        "owner_model_revision": 0, "as_of_ms": 123,
    }
    assert REVISION_SCHEMA == "van.owner_model.revision.v1"


async def test_revision_strictly_increases_on_every_mutation_type(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "s2", "s3", "d1")
    seen = [await model.current_revision("owner")]

    async def step(coro, expect_bump=True):
        result = await coro
        rev = await model.current_revision("owner")
        if expect_bump:
            assert rev > seen[-1], f"no bump after {result!r:.80}"
            assert rev == seen[-1] + 1
        else:
            assert rev == seen[-1], "no-op advanced the revision"
        seen.append(rev)
        return result

    a = await step(_obs(model, eps["s1"]))                       # insert
    await step(_obs(model, eps["s1"]), expect_bump=False)       # no-op re-observation
    await step(_obs(model, eps["s2"]))                          # ladder: -> CANDIDATE
    a = await step(_obs(model, eps["s3"]))                      # ladder: -> EVIDENCED
    assert a.state is AssertionState.EVIDENCED
    await step(_obs(model, eps["d1"], ObservationOrigin.HINDSIGHT_DERIVED))  # provenance row
    await step(_obs(model, eps["d1"], ObservationOrigin.HINDSIGHT_DERIVED), expect_bump=False)
    await step(model.confirm(a.assertion_id))                   # confirm
    b = await step(model.correct(a.assertion_id, new_value="verbose"))  # correct + supersede
    await step(model.contest(b.assertion_id))                   # contest
    await step(model.reject(b.assertion_id))                    # reject
    await step(_obs(model, eps["s1"], value="verbose"), expect_bump=False)  # rejected: no revive
    assert seen == sorted(seen) and seen[-1] == 8  # 8 mutations, 3 no-ops
    # Per owner: another owner's mutation does not move this one.
    before = await model.current_revision("owner")
    await _obs(model, eps["s1"], owner="someone-else")
    assert await model.current_revision("owner") == before
    assert await model.current_revision("someone-else") == 1


# ------------------------------------------------------------------ outbox


@pytest.mark.parametrize("action", ["correct", "reject", "contest"])
async def test_correction_writes_outbox_rows_at_the_new_revision(tmp_path, action):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1")
    a = await _obs(model, eps["s1"])
    if action == "correct":
        await model.correct(a.assertion_id, new_value="verbose")
    else:
        await getattr(model, action)(a.assertion_id)
    rev = await model.current_revision("owner")
    rows = await _outbox(store)
    assert {r["target"] for r in rows} == {t.value for t in OutboxTarget}
    assert len({r["outbox_id"] for r in rows}) == 1
    assert all(r["owner_model_revision"] == rev and r["status"] == "PENDING"
               and r["attempts"] == 0 for r in rows)
    assert all(a.assertion_id in r["payload_json"] and "terse" not in r["payload_json"]
               for r in rows), "ids only, never the owner's values"


async def test_confirm_and_observe_write_no_outbox_row(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1")
    a = await _obs(model, eps["s1"])
    await model.confirm(a.assertion_id)
    assert await _outbox(store) == []


@pytest.mark.parametrize("action", ["correct", "reject", "contest"])
async def test_failure_after_outbox_write_rolls_back_everything(tmp_path, monkeypatch, action):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1")
    a = await _obs(model, eps["s1"])
    rev_before = await model.current_revision("owner")
    rows_before = [dict(r) for r in await store.fetchall("SELECT * FROM owner_cognitive_model")]
    original = model._write_outbox
    written = []

    async def write_then_crash(db, **kwargs):
        written.append(await original(db, **kwargs))
        raise RuntimeError("crash before commit")

    monkeypatch.setattr(model, "_write_outbox", write_then_crash)
    with pytest.raises(RuntimeError, match="crash before commit"):
        if action == "correct":
            await model.correct(a.assertion_id, new_value="verbose")
        else:
            await getattr(model, action)(a.assertion_id)
    assert written, "the outbox write itself ran before the failure"
    assert await _outbox(store) == []
    assert await model.current_revision("owner") == rev_before
    assert [dict(r) for r in await store.fetchall("SELECT * FROM owner_cognitive_model")] == rows_before
    assert (await model.get(a.assertion_id)).superseded_by is None


class FakeTarget:
    def __init__(self, name, fail_times=0, receipt="ok"):
        self.name, self.fail_times, self.receipt, self.calls = name, fail_times, receipt, []

    async def __call__(self, event):
        self.calls.append((event.outbox_id, event.target, event.owner_model_revision))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("target down: owner said 'terse'")
        return self.receipt if self.receipt is None else f"{self.name}:{event.outbox_id}"


async def _one_correction(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1")
    a = await _obs(model, eps["s1"])
    await model.reject(a.assertion_id)
    return store


async def test_drain_delivers_each_target_once_and_redelivery_is_idempotent(tmp_path):
    store = await _one_correction(tmp_path)
    fakes = {t: FakeTarget(t.value) for t in OutboxTarget}
    first = await drain_outbox(store, fakes, now_ms=10)
    assert len(first.delivered) == 3 and not first.failed
    second = await drain_outbox(store, fakes, now_ms=20)
    assert second.delivered == [] and second.failed == []
    assert all(len(f.calls) == 1 for f in fakes.values())
    rows = await _outbox(store)
    assert all(r["status"] == "DELIVERED" and r["attempts"] == 1 and r["delivered_at_ms"] == 10
               and r["receipt"] == f"{r['target']}:{r['outbox_id']}" for r in rows)


async def test_a_failing_target_stays_pending_and_the_others_are_delivered(tmp_path):
    store = await _one_correction(tmp_path)
    fakes = {t: FakeTarget(t.value) for t in OutboxTarget}
    fakes[OutboxTarget.OPENVIKING_OWNER_PROJECTION].fail_times = 2
    for n in (1, 2):
        report = await drain_outbox(store, fakes, now_ms=n)
        rows = {r["target"]: r for r in await _outbox(store)}
        ov = rows["OPENVIKING_OWNER_PROJECTION"]
        assert ov["status"] == "PENDING" and ov["attempts"] == n
        assert ov["last_error"] == "ConnectionError", "error code only, never handler text"
        assert rows["HINDSIGHT_OWNER"]["status"] == "DELIVERED"
        assert rows["PERSONAL_CONTEXT_CACHE"]["status"] == "DELIVERED"
        assert [f[1] for f in report.failed] == ["OPENVIKING_OWNER_PROJECTION"]
    report = await drain_outbox(store, fakes, now_ms=3)
    assert report.delivered == [(rows["HINDSIGHT_OWNER"]["outbox_id"], "OPENVIKING_OWNER_PROJECTION")]
    rows = {r["target"]: r for r in await _outbox(store)}
    assert rows["OPENVIKING_OWNER_PROJECTION"]["status"] == "DELIVERED"
    assert rows["OPENVIKING_OWNER_PROJECTION"]["attempts"] == 3
    assert len(fakes[OutboxTarget.HINDSIGHT_OWNER].calls) == 1


async def test_an_empty_receipt_is_a_failure_and_a_missing_handler_is_not_attempted(tmp_path):
    store = await _one_correction(tmp_path)
    report = await drain_outbox(
        store, {OutboxTarget.HINDSIGHT_OWNER: FakeTarget("h", receipt=None)}, now_ms=1)
    assert report.failed == [(report.failed[0][0], "HINDSIGHT_OWNER", "OUTBOX_HANDLER_NO_RECEIPT")]
    assert sorted(t for _, t in report.unhandled) == [
        "OPENVIKING_OWNER_PROJECTION", "PERSONAL_CONTEXT_CACHE"]
    rows = {r["target"]: r for r in await _outbox(store)}
    assert all(r["status"] == "PENDING" for r in rows.values())
    assert rows["PERSONAL_CONTEXT_CACHE"]["attempts"] == 0
    assert isinstance(OutboxDeliveryError("X"), RuntimeError)
    assert outbox_mod.ALL_TARGETS == tuple(OutboxTarget)


async def test_owner_forget_advances_the_revision_and_queues_invalidation(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "s2")
    await _obs(model, eps["s1"])
    await _obs(model, eps["s2"], value="verbose")
    rev = await model.current_revision("owner")
    await OwnerMemory(store).forget_all("owner")
    assert await model.current_revision("owner") == rev + 2
    assert await store.fetchall("SELECT * FROM owner_model_episodes") == []
    rows = await _outbox(store)
    assert {r["event_kind"] for r in rows} == {"FORGOTTEN"} and len(rows) == 6
    assert all("terse" not in r["payload_json"] and "verbose" not in r["payload_json"]
               for r in rows)


# ------------------------------------------------------------------ C3 capsule


async def test_capsule_carries_current_revision_and_a_verifiable_hash(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "s2", "s3")
    for n in ("s1", "s2", "s3"):
        a = await _obs(model, eps[n])
    capsule = await build_personal_capsule(model, "owner", purpose="reply-style", now_ms=5)
    assert capsule["schema"] == CAPSULE_SCHEMA
    assert capsule["privacy_class"] == "OWNER_PRIVATE"
    assert capsule["context_capsule_id"].startswith("cc_")
    rev = await model.current_revision("owner")
    assert capsule["owner_model_revision"] == rev == capsule["source_revisions"]["owner_model_revision"]
    assert capsule["content_hash"].startswith("sha256:") and verify_content_hash(capsule)
    tampered = {**capsule, "content": {**capsule["content"], "assertions": []}}
    assert not verify_content_hash(tampered)
    assert content_hash(capsule["content"]) == capsule["content_hash"]
    [item] = capsule["content"]["assertions"]
    assert item["assertion_id"] == a.assertion_id and item["owner_stated"] is False
    assert f"van-owner-model:assertion:{a.assertion_id}" in capsule["provenance_refs"]
    assert set(eps.values()) <= set(capsule["provenance_refs"])

    # The fence: a correction moves the revision, so the capsule no longer matches.
    await model.correct(a.assertion_id, new_value="verbose")
    assert capsule["owner_model_revision"] != await model.current_revision("owner")
    fresh = await build_personal_capsule(model, "owner", purpose="reply-style")
    [item] = fresh["content"]["assertions"]
    assert item["value"] == "verbose" and item["owner_stated"] is True


async def test_capsule_excludes_derived_only_and_non_actionable_assertions(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1", "s2", "d1", "d2", "d3")
    await _obs(model, eps["s1"], value="candidate")
    await _obs(model, eps["s2"], value="candidate")
    await _obs(model, eps["d1"], ObservationOrigin.HINDSIGHT_DERIVED, value="candidate")
    for n, o in (("d1", ObservationOrigin.HINDSIGHT_DERIVED),
                 ("d2", ObservationOrigin.OPENVIKING_RETRIEVED),
                 ("d3", ObservationOrigin.MODEL_INFERRED)):
        await _obs(model, eps[n], o, value="derived-only")
    capsule = await build_personal_capsule(model, "owner", purpose="p")
    assert capsule["content"]["assertions"] == []
    assert "derived-only" not in str(capsule) and "candidate" not in str(capsule)
    assert not any(eps[d] in capsule["provenance_refs"] for d in ("d1", "d2", "d3"))


async def test_capsule_project_scope_and_purpose(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await seed_episodes(store, "s1")
    g = await _obs(model, eps["s1"], value="global")
    p = await model.observe(owner_principal_id="owner", field=FIELD, value="proj",
                            episode_ref=eps["s1"], origin=SYSTEM, project_id="van")
    await model.confirm(g.assertion_id)
    await model.confirm(p.assertion_id)
    no_project = await build_personal_capsule(model, "owner", purpose="p")
    in_project = await build_personal_capsule(model, "owner", purpose="p", project_id="van")
    assert [i["value"] for i in no_project["content"]["assertions"]] == ["global"]
    assert sorted(i["value"] for i in in_project["content"]["assertions"]) == ["global", "proj"]
    assert in_project["project_scope"] == "van"
    with pytest.raises(ValueError):
        await build_personal_capsule(model, "owner", purpose=" ")
