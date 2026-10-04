"""VAN web acquisition core tests."""

from __future__ import annotations

from conftest_automation import make_store
from van_gateway.browser.acquisition import (
    AcquisitionFailure,
    AcquisitionFrontier,
    AcquisitionRoute,
    AcquisitionRouter,
    AcquisitionSessionPool,
    AcquisitionSignals,
    AcquisitionState,
    DomainSkillRegistry,
)


async def test_frontier_dedupes_and_promotes_priority(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    first = await frontier.enqueue(
        "https://Example.COM:443/catalog#top", priority=20, now_ms=1000
    )
    second = await frontier.enqueue(
        "https://example.com/catalog", priority=90, now_ms=2000
    )
    assert first.item_id == second.item_id
    assert second.priority == 90


async def test_claim_is_priority_ordered_and_lease_fenced(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.enqueue("https://a.example/low", priority=10, now_ms=1000)
    await frontier.enqueue("https://b.example/high", priority=90, now_ms=1001)
    item = await frontier.claim(worker_id="worker-a", now_ms=2000)
    assert item is not None
    assert item.canonical_url.endswith("/high")
    assert item.attempt_count == 1
    await frontier.start(
        item.item_id, worker_id="worker-a", lease_token=item.lease_token, now_ms=2001
    )
    await frontier.complete(
        item.item_id, worker_id="worker-a", lease_token=item.lease_token, now_ms=2002
    )
    row = await store.fetchone(
        "SELECT state FROM web_acquisition_items WHERE item_id=?", (item.item_id,)
    )
    assert row["state"] == "COMPLETED"


async def test_domain_concurrency_is_enforced(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.configure_domain("same.example", max_concurrency=1, now_ms=1000)
    await frontier.enqueue("https://same.example/a", priority=90, now_ms=1001)
    await frontier.enqueue("https://same.example/b", priority=80, now_ms=1002)

    first = await frontier.claim(worker_id="one", now_ms=2000)
    assert first is not None
    second = await frontier.claim(worker_id="two", now_ms=2001)
    assert second is None


async def test_expired_lease_is_reclaimable(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.enqueue("https://example.com/a", now_ms=1000)
    first = await frontier.claim(worker_id="one", lease_seconds=30, now_ms=2000)
    assert first is not None
    second = await frontier.claim(worker_id="two", now_ms=32_001)
    assert second is not None
    assert second.item_id == first.item_id
    assert second.lease_owner == "two"
    assert second.attempt_count == 2


async def test_bounded_retry_ends_in_existing_dead_letter_system(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.enqueue(
        "https://example.com/a", max_attempts=1, now_ms=1000
    )
    item = await frontier.claim(worker_id="one", now_ms=2000)
    assert item is not None
    state = await frontier.fail(
        item.item_id,
        worker_id="one",
        lease_token=item.lease_token,
        failure=AcquisitionFailure.RUNTIME,
        error_code="SCRAPLING_UNAVAILABLE",
        now_ms=2001,
    )
    assert state is AcquisitionState.DEAD_LETTER
    dl = await store.fetchone(
        "SELECT * FROM automation_dead_letter WHERE run_id=?", (item.item_id,)
    )
    assert dl is not None
    assert dl["capability_id"] == "van.web-acquisition"


async def test_rate_limit_backs_off_and_cools_domain(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.enqueue("https://example.com/a", max_attempts=3, now_ms=1000)
    item = await frontier.claim(worker_id="one", now_ms=2000)
    state = await frontier.fail(
        item.item_id,
        worker_id="one",
        lease_token=item.lease_token,
        failure=AcquisitionFailure.RATE_LIMIT,
        error_code="HTTP_429",
        retry_after_ms=60_000,
        now_ms=2001,
    )
    assert state is AcquisitionState.RETRY_WAIT
    control = await store.fetchone(
        "SELECT * FROM web_domain_controls WHERE domain='example.com'"
    )
    assert int(control["cooldown_until_ms"]) >= 62_001


async def test_router_prefers_cheapest_known_route():
    item = type("I", (), {"preferred_route": None})()
    decision = AcquisitionRouter.decide(
        item,
        AcquisitionSignals(structured_endpoint_available=True),
    )
    assert decision.route is AcquisitionRoute.DIRECT_HTTP


async def test_router_recon_then_domain_skill_then_semantic():
    item = type("I", (), {"preferred_route": None})()
    assert AcquisitionRouter.decide(
        item, AcquisitionSignals(unknown_site=True)
    ).route is AcquisitionRoute.KATANA_RECON
    assert AcquisitionRouter.decide(
        item, AcquisitionSignals(domain_skill_available=True)
    ).route is AcquisitionRoute.HARNESS
    assert AcquisitionRouter.decide(
        item, AcquisitionSignals(semantic_interaction_required=True)
    ).route is AcquisitionRoute.STAGEHAND


async def test_session_pool_reuses_metadata_identity_without_secrets(tmp_path):
    store = await make_store(tmp_path)
    pool = AcquisitionSessionPool(store)
    first = await pool.acquire(
        profile_alias="public_research", domain_scope="example.com",
        network_identity_ref="netref://default", now_ms=1000
    )
    second = await pool.acquire(
        profile_alias="public_research", domain_scope="example.com",
        network_identity_ref="netref://default", now_ms=2000
    )
    assert first.session_id == second.session_id
    assert second.use_count == 2


async def test_running_worker_can_renew_lease_without_changing_fence(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.enqueue("https://example.com/long", now_ms=1000)
    item = await frontier.claim(worker_id="worker-a", lease_seconds=30, now_ms=2000)
    assert item is not None
    await frontier.start(
        item.item_id, worker_id="worker-a", lease_token=item.lease_token, now_ms=2001
    )
    renewed = await frontier.renew_lease(
        item.item_id,
        worker_id="worker-a",
        lease_token=item.lease_token,
        lease_seconds=120,
        now_ms=20_000,
    )
    assert renewed.lease_token == item.lease_token
    assert renewed.lease_expires_at_ms == 140_000


async def test_expired_worker_cannot_renew_after_reclaim(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.enqueue("https://example.com/fenced", now_ms=1000)
    old = await frontier.claim(worker_id="old", lease_seconds=30, now_ms=2000)
    assert old is not None
    new = await frontier.claim(worker_id="new", now_ms=32_001)
    assert new is not None
    import pytest
    with pytest.raises(RuntimeError, match="not_renewable"):
        await frontier.renew_lease(
            old.item_id,
            worker_id="old",
            lease_token=old.lease_token,
            now_ms=32_002,
        )


async def test_stale_worker_cannot_fail_reclaimed_item(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    await frontier.enqueue("https://example.com/race", max_attempts=5, now_ms=1000)
    old = await frontier.claim(worker_id="old", lease_seconds=30, now_ms=2000)
    assert old is not None
    new = await frontier.claim(worker_id="new", now_ms=32_001)
    assert new is not None
    import pytest
    with pytest.raises(RuntimeError, match="active_lease"):
        await frontier.fail(
            old.item_id,
            worker_id="old",
            lease_token=old.lease_token,
            failure=AcquisitionFailure.RUNTIME,
            error_code="OLD_WORKER",
            now_ms=32_002,
        )
    row = await store.fetchone(
        "SELECT lease_owner, lease_token, state FROM web_acquisition_items WHERE item_id=?",
        (old.item_id,),
    )
    assert row["lease_owner"] == "new"
    assert row["lease_token"] == new.lease_token
    assert row["state"] == "CLAIMED"


async def test_jev_hint_cannot_create_semantic_route():
    item = type("I", (), {"preferred_route": None})()
    decision = AcquisitionRouter.decide(
        item,
        AcquisitionSignals(jev_hint=AcquisitionRoute.STAGEHAND),
    )
    assert decision.route is AcquisitionRoute.SCRAPLING_HTTP

    allowed = AcquisitionRouter.decide(
        item,
        AcquisitionSignals(
            semantic_interaction_required=True,
            jev_hint=AcquisitionRoute.STAGEHAND,
        ),
    )
    assert allowed.route is AcquisitionRoute.STAGEHAND


async def test_domain_skill_quarantine_falls_back_to_previous_qualified_version(tmp_path):
    store = await make_store(tmp_path)
    registry = DomainSkillRegistry(store)
    first = await registry.propose(
        domain="example.com",
        goal_class="catalog",
        route=AcquisitionRoute.HARNESS,
        artifact_ref="artifact://skill/v1",
        now_ms=1000,
    )
    first = await registry.qualify(
        first.skill_id, replay_passed=True, evidence_refs=["evidence://v1"], now_ms=1100
    )
    second = await registry.propose(
        domain="example.com",
        goal_class="catalog",
        route=AcquisitionRoute.HARNESS,
        artifact_ref="artifact://skill/v2",
        now_ms=2000,
    )
    second = await registry.qualify(
        second.skill_id, replay_passed=True, evidence_refs=["evidence://v2"], now_ms=2100
    )
    hot = await registry.hot(domain="example.com", goal_class="catalog")
    assert hot is not None and hot.skill_id == second.skill_id

    await registry.quarantine(
        second.skill_id, reason="site_fingerprint_changed", evidence_ref="evidence://drift", now_ms=3000
    )
    fallback = await registry.hot(domain="example.com", goal_class="catalog")
    assert fallback is not None and fallback.skill_id == first.skill_id
