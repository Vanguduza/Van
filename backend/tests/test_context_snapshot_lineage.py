from __future__ import annotations

import json
import time

import pytest

from van_gateway.context.models import (
    ContextRequirement,
    EpistemicState,
    OwnerFactCandidate,
    SourceTrust,
)
from van_gateway.context.service import OwnerContextService
from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_context_snapshot_seals_graph_and_lexical_evidence_separately(tmp_path):
    store = Store(str(tmp_path / "snapshot-lineage.sqlite3"))
    await store.migrate()
    context = OwnerContextService(store)
    now = int(time.time() * 1000)

    await context.admit_fact(
        OwnerFactCandidate(
            fact_id="target-sdk-36",
            subject="VAN",
            predicate="android.targetSdk",
            value=36,
            authority=EpistemicState.PROJECT_TRUTH,
            source_trust=SourceTrust.LOCKED_AUTHORITY,
            source_ref="project-truth:van",
            scope="VAN_ANDROID",
            valid_from_ms=now,
            observed_at_ms=now,
            last_verified_at_ms=now,
        )
    )

    snapshot = await context.compile_snapshot(
        "snapshot-lineage-command",
        [ContextRequirement(subject="VAN", predicate="android.targetSdk", scope="VAN_ANDROID")],
        graph_evidence_refs=["context-edge:van-hermes:r2"],
        lexical_evidence_refs=["context-fact:target-sdk-36:r1"],
        live_state_refs=["repo:van@abc123"],
        policy_refs=["security-policy:A1-A5"],
        now_ms=now + 1,
    )

    assert snapshot.graph_evidence_refs == ["context-edge:van-hermes:r2"]
    assert snapshot.lexical_evidence_refs == ["context-fact:target-sdk-36:r1"]

    row = await store.fetchone(
        "SELECT graph_evidence_refs_json, digest FROM context_snapshots WHERE snapshot_id = ?",
        (snapshot.snapshot_id,),
    )
    assert row is not None
    stored = json.loads(str(row["graph_evidence_refs_json"]))
    assert stored == {
        "graph": ["context-edge:van-hermes:r2"],
        "lexical": ["context-fact:target-sdk-36:r1"],
        "knowledge": [],
    }
    assert row["digest"] == snapshot.digest

    without_lexical = await context.compile_snapshot(
        "snapshot-lineage-command-2",
        [ContextRequirement(subject="VAN", predicate="android.targetSdk", scope="VAN_ANDROID")],
        graph_evidence_refs=["context-edge:van-hermes:r2"],
        now_ms=now + 1,
    )
    assert without_lexical.digest != snapshot.digest