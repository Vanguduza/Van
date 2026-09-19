from __future__ import annotations

import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.context.models import (
    ContextEdgeCandidate,
    ContextRequirement,
    EpistemicState,
    OwnerFactCandidate,
    SourceTrust,
)
from van_gateway.context.retrieval import (
    ContextLexicalQuery,
    ContextRetrievalService,
    HotContextCapsuleRequest,
)
from van_gateway.context.service import OwnerContextService
from van_gateway.storage.db import Store


INGRESS = "retrieval-test-ingress-0123456789"
INTERNAL = "retrieval-test-hermes-internal"


@pytest_asyncio.fixture
async def retrieval_runtime(tmp_path):
    store = Store(str(tmp_path / "retrieval.sqlite3"))
    await store.migrate()
    context = OwnerContextService(store)
    retrieval = ContextRetrievalService(store, context)
    return store, context, retrieval


async def _seed_context(context: OwnerContextService, now: int) -> None:
    await context.admit_fact(OwnerFactCandidate(
        fact_id="sdk-34",
        subject="VAN",
        predicate="android.targetSdk",
        value=34,
        authority=EpistemicState.PROJECT_TRUTH,
        source_trust=SourceTrust.LOCKED_AUTHORITY,
        source_ref="project-truth:r1",
        scope="VAN_ANDROID",
        valid_from_ms=now - 20_000,
        observed_at_ms=now - 20_000,
        last_verified_at_ms=now - 20_000,
    ))
    await context.admit_fact(OwnerFactCandidate(
        fact_id="sdk-36",
        subject="VAN",
        predicate="android.targetSdk",
        value=36,
        authority=EpistemicState.PROJECT_TRUTH,
        source_trust=SourceTrust.LOCKED_AUTHORITY,
        source_ref="project-truth:r2",
        scope="VAN_ANDROID",
        valid_from_ms=now,
        observed_at_ms=now,
        last_verified_at_ms=now,
        supersedes_fact_id="sdk-34",
    ))
    await context.admit_fact(OwnerFactCandidate(
        fact_id="model-sdk",
        subject="VAN",
        predicate="android.targetSdk",
        value="36 model guess",
        authority=EpistemicState.INFERRED,
        source_trust=SourceTrust.MODEL_DERIVED,
        source_ref="hermes:guess",
        scope="VAN_ANDROID",
        valid_from_ms=now,
        observed_at_ms=now,
    ))
    await context.admit_fact(OwnerFactCandidate(
        fact_id="dial-sdk",
        subject="DIAL",
        predicate="android.targetSdk",
        value=36,
        authority=EpistemicState.PROJECT_TRUTH,
        source_trust=SourceTrust.LOCKED_AUTHORITY,
        source_ref="dial-truth:r1",
        scope="DIAL_ANDROID",
        valid_from_ms=now,
        observed_at_ms=now,
        last_verified_at_ms=now,
    ))
    await context.admit_edge(ContextEdgeCandidate(
        edge_id="van-hermes",
        from_node="VAN",
        predicate="is_a",
        to_node="HermesBot",
        authority=EpistemicState.CANONICAL_OWNER,
        source_trust=SourceTrust.OWNER_EXPLICIT,
        source_ref="owner:architecture",
        scope="VAN_ANDROID",
        valid_from_ms=now,
        observed_at_ms=now,
    ))
    await context.admit_edge(ContextEdgeCandidate(
        edge_id="van-inferred-tool",
        from_node="VAN",
        predicate="may_use",
        to_node="UnverifiedTool",
        authority=EpistemicState.INFERRED,
        source_trust=SourceTrust.MODEL_DERIVED,
        source_ref="hermes:guess",
        scope="VAN_ANDROID",
        valid_from_ms=now,
        observed_at_ms=now,
    ))


@pytest.mark.asyncio
async def test_lexical_retrieval_is_temporal_scoped_and_deterministic(retrieval_runtime):
    _store, context, retrieval = retrieval_runtime
    now = int(time.time() * 1000)
    await _seed_context(context, now)

    query = ContextLexicalQuery(query="VAN android targetSdk 36", scope="VAN_ANDROID")
    first = await retrieval.lexical_query(query, now_ms=now + 1)
    second = await retrieval.lexical_query(query, now_ms=now + 1)

    assert first.model_dump() == second.model_dump()
    ids = [hit.object_id for hit in first.hits]
    assert "sdk-36" in ids
    assert "sdk-34" not in ids
    assert "model-sdk" not in ids
    assert "dial-sdk" not in ids
    assert first.hits[0].score >= first.hits[-1].score
    assert first.kernel_revision == await context.kernel_revision()


@pytest.mark.asyncio
async def test_lexical_exact_entity_and_inferred_policy(retrieval_runtime):
    _store, context, retrieval = retrieval_runtime
    now = int(time.time() * 1000)
    await _seed_context(context, now)

    default = await retrieval.lexical_query(
        ContextLexicalQuery(query="UnverifiedTool", scope="VAN_ANDROID"),
        now_ms=now + 1,
    )
    assert all(hit.object_id != "van-inferred-tool" for hit in default.hits)

    opted_in = await retrieval.lexical_query(
        ContextLexicalQuery(query="UnverifiedTool", scope="VAN_ANDROID", allow_inferred=True),
        now_ms=now + 1,
    )
    assert opted_in.hits[0].object_id == "van-inferred-tool"
    assert opted_in.hits[0].matched_fields == ["to_node"]


@pytest.mark.asyncio
async def test_lexical_result_cap_is_explicit(retrieval_runtime):
    _store, context, retrieval = retrieval_runtime
    now = int(time.time() * 1000)
    for index in range(4):
        await context.admit_fact(OwnerFactCandidate(
            fact_id=f"project-{index}",
            subject=f"Project{index}",
            predicate="kind",
            value="project",
            authority=EpistemicState.VERIFIED_HISTORY,
            source_trust=SourceTrust.VERIFIED_SYSTEM,
            source_ref=f"history:{index}",
            scope="global",
            valid_from_ms=now,
            observed_at_ms=now,
            last_verified_at_ms=now,
        ))
    result = await retrieval.lexical_query(
        ContextLexicalQuery(query="project", max_results=2),
        now_ms=now + 1,
    )
    assert len(result.hits) == 2
    assert result.truncated is True
    assert [hit.object_id for hit in result.hits] == ["project-3", "project-2"]


@pytest.mark.asyncio
async def test_hot_capsule_is_revision_sealed_cached_and_non_authoritative(retrieval_runtime):
    _store, context, retrieval = retrieval_runtime
    now = int(time.time() * 1000)
    await _seed_context(context, now)
    revision_before = await context.kernel_revision()
    request = HotContextCapsuleRequest(
        scopes=["VAN_ANDROID"],
        requirements=[ContextRequirement(subject="VAN", predicate="android.targetSdk", scope="VAN_ANDROID")],
        seed_nodes=["VAN"],
        lexical_queries=["VAN android 36"],
        graph_depth=1,
        ttl_ms=60_000,
    )

    first = await retrieval.compile_hot_capsule(request, now_ms=now + 2)
    second = await retrieval.compile_hot_capsule(request, now_ms=now + 3)
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.capsule_id == second.capsule_id
    assert first.digest == second.digest
    assert first.kernel_revision == revision_before
    assert "context-fact:sdk-36:r2" in first.fact_refs
    assert any(ref.startswith("context-edge:van-hermes:") for ref in first.graph_evidence_refs)
    assert all("model-sdk" not in ref and "van-inferred-tool" not in ref for ref in first.lexical_evidence_refs + first.graph_evidence_refs)
    assert await context.kernel_revision() == revision_before

    await context.admit_fact(OwnerFactCandidate(
        fact_id="new-live",
        subject="VAN",
        predicate="foreground",
        value="voice",
        authority=EpistemicState.VERIFIED_LIVE_STATE,
        source_trust=SourceTrust.VERIFIED_SYSTEM,
        source_ref="device:foreground",
        scope="VAN_ANDROID",
        valid_from_ms=now + 4,
        observed_at_ms=now + 4,
        last_verified_at_ms=now + 4,
    ))
    refreshed = await retrieval.compile_hot_capsule(request, now_ms=now + 5)
    assert refreshed.cache_hit is False
    assert refreshed.kernel_revision > first.kernel_revision
    assert refreshed.digest != first.digest


@pytest.fixture(autouse=False)
def api_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "retrieval-api.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_retrieval_routes_are_hermes_internal_only(api_settings):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Van-Ingress-Token": INGRESS},
        ) as client:
            denied = await client.post(
                "/v1/runtime/context/lexical/query",
                json={"query": "VAN"},
            )
            # P0-SEC-001 — an owner ingress bearer is authenticated but holds no
            # privileged scope, and this route is Hermes-only. It used to fall through to
            # device authentication, which meant an owner device token reached it.
            assert denied.status_code == 403
            assert denied.json()["required_scope"] == "runtime"

            allowed = await client.post(
                "/v1/runtime/context/lexical/query",
                json={"query": "VAN"},
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            assert allowed.status_code == 200
            assert allowed.json()["hits"] == []

            capsule = await client.post(
                "/v1/runtime/context/hot-capsules",
                json={"scopes": ["global"]},
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            assert capsule.status_code == 200
            body = capsule.json()
            assert body["readiness_state"] == "CURRENT"
            assert body["kernel_revision"] == 0
