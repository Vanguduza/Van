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
    ContextGraphQuery,
    EpistemicState,
    GraphDirection,
    SensitivityClass,
    SourceTrust,
)
from van_gateway.context.service import OwnerContextService
from van_gateway.storage.db import Store


@pytest_asyncio.fixture
async def graph_runtime(tmp_path):
    store = Store(str(tmp_path / "graph.sqlite3"))
    await store.migrate()
    return store, OwnerContextService(store)


async def _edge(
    context: OwnerContextService,
    *,
    edge_id: str,
    from_node: str,
    predicate: str,
    to_node: str,
    now: int,
    scope: str = "global",
    authority: EpistemicState = EpistemicState.VERIFIED_HISTORY,
    confidence: int = 900,
    valid_from_ms: int | None = None,
    valid_until_ms: int | None = None,
    supersedes_edge_id: str | None = None,
):
    return await context.admit_edge(ContextEdgeCandidate(
        edge_id=edge_id,
        from_node=from_node,
        predicate=predicate,
        to_node=to_node,
        scope=scope,
        authority=authority,
        source_trust=SourceTrust.VERIFIED_SYSTEM,
        source_ref=f"test:{edge_id}",
        confidence_permille=confidence,
        valid_from_ms=now if valid_from_ms is None else valid_from_ms,
        valid_until_ms=valid_until_ms,
        observed_at_ms=now,
        supersedes_edge_id=supersedes_edge_id,
    ))


@pytest.mark.asyncio
async def test_graph_traversal_is_temporal_bounded_and_deterministic(graph_runtime):
    _store, context = graph_runtime
    now = int(time.time() * 1000)
    await _edge(context, edge_id="owner-van", from_node="OWNER", predicate="owns", to_node="VAN", now=now,
                authority=EpistemicState.CANONICAL_OWNER, confidence=1000)
    await _edge(context, edge_id="van-hermes", from_node="VAN", predicate="uses", to_node="HERMES", now=now,
                authority=EpistemicState.VERIFIED_LIVE_STATE, confidence=980)
    await _edge(context, edge_id="van-old-api", from_node="VAN", predicate="targets", to_node="API34", now=now,
                valid_from_ms=now - 10_000)
    await _edge(context, edge_id="van-api36", from_node="VAN", predicate="targets", to_node="API36", now=now + 1,
                authority=EpistemicState.PROJECT_TRUTH, confidence=1000, supersedes_edge_id="van-old-api")

    query = ContextGraphQuery(seed_nodes=["OWNER"], max_depth=2, max_edges=16)
    first = await context.traverse_graph(query, now_ms=now + 2)
    second = await context.traverse_graph(query, now_ms=now + 2)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert [edge.edge_id for edge in first.edges] == ["owner-van", "van-api36", "van-hermes"]
    assert "van-old-api" not in {edge.edge_id for edge in first.edges}
    assert first.visited_nodes == ["OWNER", "VAN", "API36", "HERMES"]
    assert first.evidence_refs == [
        "context-edge:owner-van:r1",
        "context-edge:van-api36:r4",
        "context-edge:van-hermes:r2",
    ]
    assert first.truncated is False


@pytest.mark.asyncio
async def test_graph_scope_direction_inferred_and_caps_are_fail_closed(graph_runtime):
    _store, context = graph_runtime
    now = int(time.time() * 1000)
    await _edge(context, edge_id="global-a", from_node="VAN", predicate="uses", to_node="A", now=now,
                authority=EpistemicState.VERIFIED_HISTORY, confidence=900)
    await _edge(context, edge_id="global-b", from_node="VAN", predicate="uses", to_node="B", now=now,
                authority=EpistemicState.INFERRED, confidence=1000)
    await _edge(context, edge_id="dde-only", from_node="VAN", predicate="uses", to_node="DDE", now=now, scope="dde")
    await _edge(context, edge_id="incoming", from_node="OWNER", predicate="owns", to_node="VAN", now=now,
                authority=EpistemicState.CANONICAL_OWNER, confidence=1000)

    out = await context.traverse_graph(ContextGraphQuery(
        seed_nodes=["VAN"], direction=GraphDirection.OUT, max_depth=1, max_edges=8,
    ), now_ms=now + 1)
    assert [edge.edge_id for edge in out.edges] == ["global-a"]

    incoming = await context.traverse_graph(ContextGraphQuery(
        seed_nodes=["VAN"], direction=GraphDirection.IN, max_depth=1, max_edges=8,
    ), now_ms=now + 1)
    assert [edge.edge_id for edge in incoming.edges] == ["incoming"]

    inferred = await context.traverse_graph(ContextGraphQuery(
        seed_nodes=["VAN"], direction=GraphDirection.OUT, max_depth=1, max_edges=8, allow_inferred=True,
    ), now_ms=now + 1)
    assert [edge.edge_id for edge in inferred.edges] == ["global-a", "global-b"]

    capped = await context.traverse_graph(ContextGraphQuery(
        seed_nodes=["VAN"], direction=GraphDirection.BOTH, max_depth=1, max_edges=1,
    ), now_ms=now + 1)
    assert len(capped.edges) == 1
    assert capped.edges[0].edge_id == "incoming"
    assert capped.truncated is True

    dde = await context.traverse_graph(ContextGraphQuery(
        seed_nodes=["VAN"], scope="dde", direction=GraphDirection.OUT, max_depth=1,
    ), now_ms=now + 1)
    assert [edge.edge_id for edge in dde.edges] == ["dde-only"]


@pytest.mark.asyncio
async def test_graph_query_preserves_competing_edges(graph_runtime):
    _store, context = graph_runtime
    now = int(time.time() * 1000)
    for edge_id, target in (("mode-a", "MODE_A"), ("mode-b", "MODE_B")):
        await _edge(
            context,
            edge_id=edge_id,
            from_node="VAN",
            predicate="active_mode",
            to_node=target,
            now=now,
            authority=EpistemicState.VERIFIED_LIVE_STATE,
            confidence=1000,
        )
    result = await context.traverse_graph(ContextGraphQuery(
        seed_nodes=["VAN"], predicates=["active_mode"], direction=GraphDirection.OUT,
    ), now_ms=now + 1)
    assert {edge.edge_id for edge in result.edges} == {"mode-a", "mode-b"}


INGRESS = "graph-test-ingress-0123456789abcdef"
INTERNAL = "graph-test-hermes-internal"


@pytest.fixture
def graph_api_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "graph-api.sqlite3"))
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
async def test_graph_query_is_hermes_internal_only(graph_api_settings):
    app = create_app()
    async with app.router.lifespan_context(app):
        now = int(time.time() * 1000)
        await app.state.owner_runtime.context.admit_edge(ContextEdgeCandidate(
            edge_id="api-edge",
            from_node="OWNER",
            predicate="owns",
            to_node="VAN",
            authority=EpistemicState.CANONICAL_OWNER,
            source_trust=SourceTrust.OWNER_EXPLICIT,
            source_ref="owner:test",
            valid_from_ms=now,
            observed_at_ms=now,
            sensitivity=SensitivityClass.OWNER_PRIVATE,
        ))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Van-Ingress-Token": INGRESS},
        ) as client:
            body = {"seed_nodes": ["OWNER"], "max_depth": 1, "max_edges": 8}
            # P0-SEC-001 — an owner ingress bearer is authenticated but holds no
            # privileged scope, and this route is Hermes-only. It used to fall through to
            # device authentication, which meant an owner device token reached it.
            denied = await client.post("/v1/runtime/context/graph/query", json=body)
            assert denied.status_code == 403
            assert denied.json()["required_scope"] == "runtime"

            allowed = await client.post(
                "/v1/runtime/context/graph/query",
                json=body,
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            assert allowed.status_code == 200
            result = allowed.json()
            assert [edge["edge_id"] for edge in result["edges"]] == ["api-edge"]
            assert result["evidence_refs"] == ["context-edge:api-edge:r1"]
