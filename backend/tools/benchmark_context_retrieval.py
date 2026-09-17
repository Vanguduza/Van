from __future__ import annotations

import argparse
import asyncio
import json
import math
import tempfile
import time
from pathlib import Path
from typing import Awaitable, Callable

from van_gateway.context.models import (
    ContextEdgeCandidate,
    ContextGraphQuery,
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


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile_value * len(ordered)) - 1))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float | int]:
    return {
        "samples": len(values),
        "min_ms": round(min(values), 3) if values else 0.0,
        "p50_ms": round(percentile(values, 0.50), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
        "max_ms": round(max(values), 3) if values else 0.0,
    }


async def timed(call: Callable[[], Awaitable[object]], iterations: int) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        await call()
        samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return samples


async def seed_context(
    context: OwnerContextService,
    *,
    now_ms: int,
    fact_count: int,
    edge_count: int,
) -> None:
    for index in range(fact_count):
        await context.admit_fact(
            OwnerFactCandidate(
                fact_id=f"bench-fact-{index:04d}",
                subject="VAN" if index % 4 == 0 else f"Project{index % 32}",
                predicate="runtime.capability" if index % 3 == 0 else "project.state",
                value={
                    "name": "owner context retrieval" if index % 5 == 0 else f"capability-{index}",
                    "revision_hint": index,
                },
                authority=EpistemicState.PROJECT_TRUTH if index % 2 == 0 else EpistemicState.VERIFIED_HISTORY,
                source_trust=SourceTrust.LOCKED_AUTHORITY if index % 2 == 0 else SourceTrust.VERIFIED_SYSTEM,
                source_ref=f"benchmark:fact:{index}",
                scope="VAN_BENCH",
                valid_from_ms=now_ms - 1_000,
                observed_at_ms=now_ms - 1_000,
                last_verified_at_ms=now_ms - 1_000,
            )
        )

    await context.admit_fact(
        OwnerFactCandidate(
            fact_id="bench-target",
            subject="VAN",
            predicate="android.targetSdk",
            value=36,
            authority=EpistemicState.PROJECT_TRUTH,
            source_trust=SourceTrust.LOCKED_AUTHORITY,
            source_ref="benchmark:target",
            scope="VAN_BENCH",
            valid_from_ms=now_ms,
            observed_at_ms=now_ms,
            last_verified_at_ms=now_ms,
        )
    )

    for index in range(edge_count):
        await context.admit_edge(
            ContextEdgeCandidate(
                edge_id=f"bench-edge-{index:04d}",
                from_node="VAN" if index < 24 else f"Node{index % 64}",
                predicate="uses" if index % 2 == 0 else "relates_to",
                to_node=f"Capability{index % 96}",
                authority=EpistemicState.CANONICAL_OWNER if index < 12 else EpistemicState.VERIFIED_HISTORY,
                source_trust=SourceTrust.OWNER_EXPLICIT if index < 12 else SourceTrust.VERIFIED_SYSTEM,
                source_ref=f"benchmark:edge:{index}",
                scope="VAN_BENCH",
                valid_from_ms=now_ms - 1_000,
                observed_at_ms=now_ms - 1_000,
            )
        )


async def benchmark(args: argparse.Namespace) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="van-context-bench-") as temp_dir:
        store = Store(str(Path(temp_dir) / "context.sqlite3"))
        await store.migrate()
        context = OwnerContextService(store)
        retrieval = ContextRetrievalService(store, context)
        now_ms = int(time.time() * 1000)
        await seed_context(
            context,
            now_ms=now_ms,
            fact_count=args.facts,
            edge_count=args.edges,
        )

        requirement = ContextRequirement(
            subject="VAN",
            predicate="android.targetSdk",
            scope="VAN_BENCH",
        )
        lexical_query = ContextLexicalQuery(
            query="VAN owner context retrieval",
            scope="VAN_BENCH",
            max_results=16,
        )
        graph_query = ContextGraphQuery(
            seed_nodes=["VAN"],
            scope="VAN_BENCH",
            max_depth=2,
            max_edges=48,
        )
        capsule_request = HotContextCapsuleRequest(
            scopes=["VAN_BENCH"],
            requirements=[requirement],
            seed_nodes=["VAN"],
            lexical_queries=["VAN owner context retrieval"],
            graph_depth=2,
            max_graph_edges=48,
            max_lexical_hits_per_query=16,
            ttl_ms=120_000,
        )

        readiness_samples = await timed(
            lambda: context.readiness("bench-command", [requirement], now_ms=now_ms + 1),
            args.iterations,
        )
        lexical_samples = await timed(
            lambda: retrieval.lexical_query(lexical_query, now_ms=now_ms + 1),
            args.iterations,
        )
        graph_samples = await timed(
            lambda: context.traverse_graph(graph_query, now_ms=now_ms + 1),
            args.iterations,
        )

        cold_samples: list[float] = []
        for _ in range(args.cold_iterations):
            cold_retrieval = ContextRetrievalService(store, context)
            started = time.perf_counter_ns()
            capsule = await cold_retrieval.compile_hot_capsule(capsule_request, now_ms=now_ms + 1)
            cold_samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
            if capsule.cache_hit:
                raise RuntimeError("cold capsule unexpectedly reported cache hit")

        primed = await retrieval.compile_hot_capsule(capsule_request, now_ms=now_ms + 1)
        if primed.cache_hit:
            raise RuntimeError("first hot capsule compile unexpectedly reported cache hit")

        hit_samples: list[float] = []
        for offset in range(args.iterations):
            started = time.perf_counter_ns()
            capsule = await retrieval.compile_hot_capsule(capsule_request, now_ms=now_ms + 2 + offset)
            hit_samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
            if not capsule.cache_hit:
                raise RuntimeError("primed hot capsule did not report cache hit")

        lexical_probe = await retrieval.lexical_query(lexical_query, now_ms=now_ms + 1)
        if not lexical_probe.hits:
            raise RuntimeError("benchmark lexical probe returned no evidence")
        graph_probe = await context.traverse_graph(graph_query, now_ms=now_ms + 1)
        if not graph_probe.edges:
            raise RuntimeError("benchmark graph probe returned no evidence")

        return {
            "schema": "van.context-latency.v1",
            "measured_at_unix_ms": int(time.time() * 1000),
            "environment": {
                "database": "sqlite-temp-local",
                "remote_calls": False,
                "model_calls": False,
                "semantic_embeddings": False,
            },
            "corpus": {
                "facts": args.facts + 1,
                "edges": args.edges,
                "kernel_revision": await context.kernel_revision(),
            },
            "iterations": {
                "steady_state": args.iterations,
                "cold_capsule": args.cold_iterations,
            },
            "metrics": {
                "exact_readiness": summarize(readiness_samples),
                "lexical_query": summarize(lexical_samples),
                "temporal_graph_query": summarize(graph_samples),
                "hot_capsule_cold": summarize(cold_samples),
                "hot_capsule_cache_hit": summarize(hit_samples),
            },
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Measure deterministic VAN local context retrieval latency.")
    parser.add_argument("--facts", type=int, default=320)
    parser.add_argument("--edges", type=int, default=160)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--cold-iterations", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.facts < 32 or args.edges < 16 or args.iterations < 5 or args.cold_iterations < 2:
        raise SystemExit("benchmark corpus/iteration bounds are too small for useful evidence")

    result = await benchmark(args)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
