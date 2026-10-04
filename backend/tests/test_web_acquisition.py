"""VAN web acquisition core tests."""

from __future__ import annotations

from conftest_automation import make_store
from van_gateway.browser.acquisition import (
    AcquisitionEvidenceLedger,
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
    item = type("I", (), {"preferred_route": None, "profile_alias": "public_research"})()
    decision = AcquisitionRouter.decide(
        item,
        AcquisitionSignals(structured_endpoint_available=True),
    )
    assert decision.route is AcquisitionRoute.DIRECT_HTTP


async def test_router_recon_then_domain_skill_then_semantic():
    item = type("I", (), {"preferred_route": None, "profile_alias": "public_research"})()
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
    item = type("I", (), {"preferred_route": None, "profile_alias": "public_research"})()
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
        golden_case_refs=["golden://catalog/v1"],
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
        golden_case_refs=["golden://catalog/v2"],
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


async def test_skill_requires_replay_oracle_before_qualification(tmp_path):
    import pytest
    store = await make_store(tmp_path)
    registry = DomainSkillRegistry(store)
    skill = await registry.propose(
        domain="example.com",
        goal_class="catalog",
        route=AcquisitionRoute.HARNESS,
        artifact_ref="artifact://skill/no-oracle",
        now_ms=1000,
    )
    with pytest.raises(ValueError, match="golden_case_or_success_assertion"):
        await registry.qualify(
            skill.skill_id, replay_passed=True, evidence_refs=["evidence://run"], now_ms=1100
        )


async def test_failed_canary_quarantines_and_falls_back(tmp_path):
    store = await make_store(tmp_path)
    registry = DomainSkillRegistry(store)
    first = await registry.propose(
        domain="example.com", goal_class="catalog", route=AcquisitionRoute.HARNESS,
        artifact_ref="artifact://skill/v1", golden_case_refs=["golden://v1"], now_ms=1000,
    )
    await registry.qualify(
        first.skill_id, replay_passed=True, evidence_refs=["evidence://v1"], now_ms=1100
    )
    second = await registry.propose(
        domain="example.com", goal_class="catalog", route=AcquisitionRoute.HARNESS,
        artifact_ref="artifact://skill/v2", golden_case_refs=["golden://v2"], now_ms=2000,
    )
    await registry.qualify(
        second.skill_id, replay_passed=True, evidence_refs=["evidence://v2"], now_ms=2100
    )
    failed = await registry.record_canary(
        second.skill_id, passed=False, evidence_ref="evidence://canary-fail",
        observed_fingerprint="sha256:drift", now_ms=3000,
    )
    assert failed.state.value == "QUARANTINED"
    fallback = await registry.hot(domain="example.com", goal_class="catalog")
    assert fallback is not None and fallback.skill_id == first.skill_id


async def test_sensitive_query_credentials_are_not_persisted(tmp_path):
    import pytest
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    with pytest.raises(ValueError, match="sensitive_query"):
        await frontier.enqueue(
            "https://example.com/export?access_token=do-not-store",
            now_ms=1000,
        )
    with pytest.raises(ValueError, match="userinfo"):
        await frontier.enqueue(
            "https://user:password@example.com/export",
            now_ms=1000,
        )


async def test_evidence_chain_detects_manifest_tampering(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    item = await frontier.enqueue("https://example.com/catalog", now_ms=1000)
    ledger = AcquisitionEvidenceLedger(store)
    evidence = await ledger.record(
        item_id=item.item_id,
        kind="PUBLIC_WEB_ACQUISITION",
        content_digest="sha256:" + "a" * 64,
        source_url=item.canonical_url,
        byte_size=42,
        detail={"representation": "MARKDOWN_MAIN_CONTENT"},
        now_ms=2000,
    )
    assert (await ledger.verify_chain())["ok"] is True
    await store.execute(
        "UPDATE web_acquisition_evidence SET manifest_json=? WHERE evidence_id=?",
        ('{"tampered":true}', evidence.evidence_id),
    )
    verdict = await ledger.verify_chain()
    assert verdict["ok"] is False
    assert verdict["reason"] == "manifest_digest_mismatch"


async def test_router_uses_crawlee_only_for_public_bulk_crawl():
    public_item = type(
        "I", (), {"preferred_route": None, "profile_alias": "public_research"}
    )()
    decision = AcquisitionRouter.decide(
        public_item, AcquisitionSignals(bulk_crawl_required=True)
    )
    assert decision.route is AcquisitionRoute.CRAWLEE_CRAWL

    authenticated_item = type(
        "I", (), {"preferred_route": None, "profile_alias": "authenticated_owner"}
    )()
    managed = AcquisitionRouter.decide(
        authenticated_item, AcquisitionSignals(bulk_crawl_required=True)
    )
    assert managed.route is AcquisitionRoute.HARNESS


async def test_jev_cannot_select_crawlee_without_bulk_signal():
    item = type(
        "I", (), {"preferred_route": None, "profile_alias": "public_research"}
    )()
    decision = AcquisitionRouter.decide(
        item, AcquisitionSignals(jev_hint=AcquisitionRoute.CRAWLEE_CRAWL)
    )
    assert decision.route is AcquisitionRoute.SCRAPLING_HTTP


async def test_bulk_crawl_does_not_override_browser_or_semantic_requirement():
    item = type(
        "I", (), {"preferred_route": None, "profile_alias": "public_research"}
    )()
    browser = AcquisitionRouter.decide(
        item,
        AcquisitionSignals(
            bulk_crawl_required=True,
            javascript_required=True,
        ),
    )
    assert browser.route is AcquisitionRoute.SCRAPLING_BROWSER

    semantic = AcquisitionRouter.decide(
        item,
        AcquisitionSignals(
            bulk_crawl_required=True,
            semantic_interaction_required=True,
        ),
    )
    assert semantic.route is AcquisitionRoute.STAGEHAND


async def test_crawlee_batch_handoff_is_deduped_and_scope_checked(tmp_path):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    parent = await frontier.enqueue("https://example.com/catalog", now_ms=1000)
    stats = await frontier.enqueue_many(
        [
            "https://example.com/a",
            "https://example.com/a#fragment",
            "https://shop.example.com/b",
            "https://attacker.example.net/c",
            "https://example.com/x?access_token=do-not-store",
        ],
        profile_alias="public_research",
        source="CRAWLEE_DISCOVERY",
        parent_item_id=parent.item_id,
        depth=1,
        priority=49,
        expected_domain="example.com",
        now_ms=2000,
    )
    assert stats == {"received": 5, "unique_admitted": 2, "rejected": 2}
    rows = await store.fetchall(
        "SELECT canonical_url FROM web_acquisition_items WHERE parent_item_id=? "
        "ORDER BY canonical_url",
        (parent.item_id,),
    )
    assert [str(row["canonical_url"]) for row in rows] == [
        "https://example.com/a",
        "https://shop.example.com/b",
    ]
