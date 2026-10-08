"""Owner decision 2026-09-29 §3 — the personal-context resolver's revision fence.

requested owner revision == authoritative current owner_model_revision, read from the
authoritative store at resolve time; otherwise PERSONAL_CONTEXT_UNAVAILABLE. Never stale
cached owner context.
"""

from __future__ import annotations

import sqlite3

import pytest
from conftest_automation import make_store

from van_gateway.understanding.owner_model import (
    ObservationOrigin,
    OwnerCognitiveModel,
    OwnerModelField,
)
from van_gateway.understanding.owner_model_outbox import OutboxTarget, drain_outbox
from van_gateway.understanding.personal_context import verify_content_hash
from van_gateway.understanding.personal_context_resolver import (
    PERSONAL_CONTEXT_UNAVAILABLE,
    PersonalContextResolver,
    PersonalContextUnavailable,
    RevisionFencedCapsuleCache,
    UnavailableReason,
)

SYSTEM = ObservationOrigin.SYSTEM_OBSERVED
FIELD = OwnerModelField.COMMUNICATION_PREFERENCE


async def _seed(store, *names: str) -> dict[str, str]:
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


async def _evidenced(tmp_path):
    """An Owner Model with one EVIDENCED assertion ("terse") and a warm-able resolver."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    eps = await _seed(store, "s1", "s2", "s3")
    for n in ("s1", "s2", "s3"):
        a = await model.observe(owner_principal_id="owner", field=FIELD, value="terse",
                                episode_ref=eps[n], origin=SYSTEM)
    cache = RevisionFencedCapsuleCache()
    return store, model, a, PersonalContextResolver(model, cache=cache), cache


def _values(capsule) -> list[str]:
    return [i["value"] for i in capsule["content"]["assertions"]]


async def _unavailable(coro) -> PersonalContextUnavailable:
    with pytest.raises(PersonalContextUnavailable) as info:
        await coro
    assert info.value.code == PERSONAL_CONTEXT_UNAVAILABLE
    return info.value


class _UnreachableStore:
    """Wraps the real store; every authoritative read raises like a dead database."""

    def __init__(self, real):
        self._real = real
        self.down = False

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def fetchone(self, *a, **kw):
        if self.down:
            raise sqlite3.OperationalError("unable to open database file")
        return await self._real.fetchone(*a, **kw)

    def connection(self):
        if self.down:
            raise sqlite3.OperationalError("unable to open database file")
        return self._real.connection()


# ------------------------------------------------------------------ the four regressions


async def test_matching_revision_is_served(tmp_path):
    _, model, _, resolver, cache = await _evidenced(tmp_path)
    rev = await model.current_revision("owner")
    capsule = await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    assert _values(capsule) == ["terse"]
    assert capsule["owner_model_revision"] == rev
    assert capsule["fence"]["requested_owner_model_revision"] == rev
    assert capsule["fence"]["authoritative_owner_model_revision"] == rev
    assert verify_content_hash(capsule) and len(cache) == 1
    # Served again from the cache at the same verified revision.
    again = await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    assert again["context_capsule_id"] == capsule["context_capsule_id"]


async def test_stale_requested_revision_is_unavailable(tmp_path):
    _, model, a, resolver, _ = await _evidenced(tmp_path)
    old = await model.current_revision("owner")
    await model.correct(a.assertion_id, new_value="verbose")
    new = await model.current_revision("owner")
    assert new > old
    exc = await _unavailable(resolver.resolve("owner", requested_revision=old, purpose="p"))
    assert exc.reason is UnavailableReason.REVISION_MISMATCH
    assert exc.as_detail() == {
        "code": PERSONAL_CONTEXT_UNAVAILABLE, "reason": "REVISION_MISMATCH",
        "requested_owner_model_revision": old, "authoritative_owner_model_revision": new,
    }
    # A requested revision from the future is equally unverifiable.
    exc = await _unavailable(resolver.resolve("owner", requested_revision=new + 1, purpose="p"))
    assert exc.reason is UnavailableReason.REVISION_MISMATCH


async def test_store_unavailable_is_unavailable_even_with_a_warm_cache(tmp_path):
    store, _, _, _, _ = await _evidenced(tmp_path)
    flaky = _UnreachableStore(store)
    model = OwnerCognitiveModel(flaky)
    cache = RevisionFencedCapsuleCache()
    resolver = PersonalContextResolver(model, cache=cache)
    rev = await model.current_revision("owner")
    warm = await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    assert _values(warm) == ["terse"] and len(cache) == 1  # the cache is warm at `rev`

    flaky.down = True
    exc = await _unavailable(resolver.resolve("owner", requested_revision=rev,
                                              purpose="reply-style"))
    assert exc.reason is UnavailableReason.AUTHORITATIVE_STORE_UNREACHABLE
    assert exc.authoritative_revision is None


async def test_revision_bumped_between_cache_fill_and_read_is_unavailable(tmp_path):
    _, model, a, resolver, cache = await _evidenced(tmp_path)
    rev = await model.current_revision("owner")
    await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    assert len(cache) == 1  # filled at `rev`
    await model.correct(a.assertion_id, new_value="verbose")  # bump, outbox not drained
    exc = await _unavailable(resolver.resolve("owner", requested_revision=rev,
                                              purpose="reply-style"))
    assert exc.reason is UnavailableReason.REVISION_MISMATCH
    # At the new revision the stale entry is not served; a fresh capsule is built.
    fresh = await resolver.resolve("owner", requested_revision=rev + 1, purpose="reply-style")
    assert _values(fresh) == ["verbose"] and fresh["owner_model_revision"] == rev + 1


async def test_revision_bumped_after_the_check_but_before_serving_is_unavailable(tmp_path):
    """The race form: the first authoritative read matches and the cache holds a capsule
    at that revision, then a correction commits before the capsule is handed out."""
    _, model, a, resolver, cache = await _evidenced(tmp_path)
    rev = await model.current_revision("owner")
    await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    real_candidate = cache.candidate
    fired = []

    def racing_candidate(key, authoritative_revision):
        entry = real_candidate(key, authoritative_revision)
        if not fired:
            fired.append(True)
            import asyncio
            loop = asyncio.get_running_loop()
            fired.append(loop.create_task(model.correct(a.assertion_id, new_value="verbose")))
        return entry

    cache.candidate = racing_candidate
    # Let the correction task run before the serve-time re-read.
    real_read = resolver.authoritative_revision
    calls = []

    async def read_after_race(owner, *, requested=None):
        calls.append(owner)
        if len(calls) == 2:
            await fired[1]
        return await real_read(owner, requested=requested)

    resolver.authoritative_revision = read_after_race
    exc = await _unavailable(resolver.resolve("owner", requested_revision=rev,
                                              purpose="reply-style"))
    assert exc.reason is UnavailableReason.REVISION_CHANGED_DURING_RESOLVE
    assert exc.authoritative_revision == rev + 1
    assert len(cache) == 0  # the stale candidate was dropped, not kept for next time


# ------------------------------------------------------------------ edges


async def test_missing_authoritative_revision_row_is_unavailable_not_zero(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    assert await model.current_revision("owner") == 0  # display default
    resolver = PersonalContextResolver(model, cache=RevisionFencedCapsuleCache())
    exc = await _unavailable(resolver.resolve("owner", requested_revision=0, purpose="p"))
    assert exc.reason is UnavailableReason.AUTHORITATIVE_REVISION_MISSING


@pytest.mark.parametrize("requested", [None, -1, "3", 3.0, True])
async def test_invalid_requested_revision_is_unavailable(tmp_path, requested):
    _, _, _, resolver, _ = await _evidenced(tmp_path)
    exc = await _unavailable(resolver.resolve("owner", requested_revision=requested,
                                              purpose="p"))
    assert exc.reason is UnavailableReason.REQUESTED_REVISION_INVALID


async def test_tampered_cache_entry_is_unavailable_and_evicted(tmp_path):
    _, model, _, resolver, cache = await _evidenced(tmp_path)
    rev = await model.current_revision("owner")
    first = await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    [entry] = cache._entries.values()  # noqa: SLF001
    entry["content"]["assertions"][0]["value"] = "forged"
    exc = await _unavailable(resolver.resolve("owner", requested_revision=rev,
                                              purpose="reply-style"))
    assert exc.reason is UnavailableReason.CAPSULE_INTEGRITY_FAILED
    assert len(cache) == 0
    rebuilt = await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    assert _values(rebuilt) == ["terse"] and rebuilt["context_capsule_id"] != first["context_capsule_id"]


async def test_outbox_personal_context_cache_target_drops_cached_capsules(tmp_path):
    store, model, a, resolver, cache = await _evidenced(tmp_path)
    rev = await model.current_revision("owner")
    await resolver.resolve("owner", requested_revision=rev, purpose="reply-style")
    await model.correct(a.assertion_id, new_value="verbose")
    report = await drain_outbox(store, {OutboxTarget.PERSONAL_CONTEXT_CACHE: cache.outbox_handler})
    assert report.failed == [] and len(report.delivered) == 1
    assert len(cache) == 0


async def test_http_route_is_fenced_and_internal_only(tmp_path):
    import httpx
    from fastapi import FastAPI

    from van_gateway.config import Settings
    from van_gateway.understanding.api import UnderstandingApi

    store = await make_store(tmp_path)
    settings = Settings(internal_control_scoped_tokens="understanding:tok-understanding-0123456789abcdef0123456789")
    api = UnderstandingApi(store, settings)
    eps = await _seed(store, "s1", "s2", "s3")
    for n in ("s1", "s2", "s3"):
        a = await api.owner_model.observe(owner_principal_id="owner", field=FIELD,
                                          value="terse", episode_ref=eps[n], origin=SYSTEM)
    rev = await api.owner_model.current_revision("owner")
    app = FastAPI()
    app.include_router(api.router)
    h = {"X-Van-Internal-Token": "tok-understanding-0123456789abcdef0123456789"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        url = "/v1/understanding/personal-context"
        anon = await c.get(url, params={"owner_model_revision": rev, "purpose": "p"})
        assert anon.status_code in (401, 403), anon.text
        ok = await c.get(url, headers=h, params={"owner_model_revision": rev, "purpose": "p"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["fence"]["authoritative_owner_model_revision"] == rev
        await api.owner_model.correct(a.assertion_id, new_value="verbose")
        stale = await c.get(url, headers=h, params={"owner_model_revision": rev, "purpose": "p"})
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == PERSONAL_CONTEXT_UNAVAILABLE
        assert stale.json()["detail"]["reason"] == "REVISION_MISMATCH"


async def test_a_consumer_cannot_rewrite_the_cached_envelope_for_the_next_consumer(tmp_path):
    """A-MIN-VAN (reviewer D2 probe RES2): the cache served a shallow copy, so a consumer
    that appended to `provenance_refs` or rewrote `source_revisions` changed what the next
    consumer was served. Neither field is under `content_hash`, so integrity never failed."""
    store, model, a, resolver, cache = await _evidenced(tmp_path)
    rev = await model.current_revision("owner")
    first = await resolver.resolve("owner", requested_revision=rev, purpose="p")
    pristine_refs = list(first["provenance_refs"])
    first["provenance_refs"].append("mission:FORGED-BY-CONSUMER-1")
    first["source_revisions"]["owner_model_revision"] = 999
    first["content"]["assertions"].clear()
    second = await resolver.resolve("owner", requested_revision=rev, purpose="p")
    assert second["provenance_refs"] == pristine_refs
    assert second["source_revisions"] == {"owner_model_revision": rev}
    assert _values(second) == ["terse"]
    # a served capsule never aliases the cached entry, nor another served capsule
    second["provenance_refs"].append("x")
    third = await resolver.resolve("owner", requested_revision=rev, purpose="p")
    assert third["provenance_refs"] == pristine_refs and len(cache) == 1
