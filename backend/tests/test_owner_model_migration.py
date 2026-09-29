"""Migration 31 — legacy supporting episodes become SYSTEM_OBSERVED, idempotently.

Why SYSTEM_OBSERVED: before this migration the only producer of `observe()` was the
internal-control observe route, every accepted episode had to resolve to a real mission
or audit row, and no derived-origin (Hindsight/OpenViking/model) producer existed.
"""

from __future__ import annotations

import aiosqlite
import pytest

from van_gateway.storage import db as dbmod
from van_gateway.storage.db import MIGRATION_31, Store
from van_gateway.understanding.owner_model import (
    AssertionState,
    ObservationOrigin,
    OwnerCognitiveModel,
    OwnerModelField,
)

LEGACY = [
    # assertion_id, owner, field, value, state, refs
    ("oca_ev", "owner", "communication_preferences", "terse", "EVIDENCED",
     ["mission:a", "mission:b", "mission:c"]),
    ("oca_cand", "owner", "reasoning_preferences", "thorough", "CANDIDATE",
     ["mission:a", "mission:b"]),
    ("oca_other", "someone-else", "values", "honesty", "OBSERVED", ["command:z"]),
]


async def _legacy_store(tmp_path, monkeypatch) -> Store:
    """A database migrated to v30 only, holding assertions written the old way."""
    store = Store(str(tmp_path / "legacy.sqlite3"))
    monkeypatch.delitem(dbmod.MIGRATIONS, 31)
    await store.migrate()
    monkeypatch.undo()
    for aid, owner, field, value, state, refs in LEGACY:
        await store.execute(
            "INSERT INTO owner_cognitive_model(assertion_id, owner_principal_id, field, value, "
            "state, confidence, evidence_refs_json, supporting_episode_refs_json, "
            "created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, 0.5, '[]', ?, 1, 7)",
            (aid, owner, field, value, state, Store.dumps(refs)),
        )
    assert 31 in dbmod.MIGRATIONS
    return store


async def _snapshot(store):
    eps = [tuple(r) for r in await store.fetchall(
        "SELECT assertion_id, episode_ref, origin, recorded_at_ms FROM owner_model_episodes "
        "ORDER BY 1, 2, 3")]
    revs = [tuple(r) for r in await store.fetchall(
        "SELECT owner_principal_id, owner_model_revision FROM owner_model_revisions ORDER BY 1")]
    return eps, revs


async def test_migration_backfills_legacy_episodes_as_system_observed(tmp_path, monkeypatch):
    store = await _legacy_store(tmp_path, monkeypatch)
    assert await store.fetchall(
        "SELECT name FROM sqlite_master WHERE name = 'owner_model_episodes'") == []
    await store.migrate()
    eps, revs = await _snapshot(store)
    expected = sorted((aid, ref, "SYSTEM_OBSERVED", 7) for aid, *_, refs in LEGACY for ref in refs)
    assert eps == expected
    assert revs == [("owner", 1), ("someone-else", 1)]
    version = await store.fetchone("SELECT MAX(version) AS v FROM schema_migrations")
    assert version["v"] == dbmod.SCHEMA_VERSION == 31

    model = OwnerCognitiveModel(store)
    legacy = await model.get("oca_ev")
    assert legacy.evidencing_episode_count == 3
    assert legacy.state is AssertionState.EVIDENCED and legacy.may_act_on


async def test_migration_is_idempotent_and_never_relabels_an_existing_origin(tmp_path, monkeypatch):
    store = await _legacy_store(tmp_path, monkeypatch)
    await store.migrate()
    # A derived row recorded after migration, for an episode ref that is also present in
    # the legacy JSON of another assertion and absent from this one's JSON.
    await store.execute(
        "INSERT INTO owner_model_episodes(assertion_id, episode_ref, origin, recorded_at_ms) "
        "VALUES ('oca_cand', 'mission:derived', 'HINDSIGHT_DERIVED', 9)")
    # Simulate a stale JSON that names that ref (what a naive re-backfill would relabel).
    await store.execute(
        "UPDATE owner_cognitive_model SET supporting_episode_refs_json = ? "
        "WHERE assertion_id = 'oca_cand'",
        (Store.dumps(["mission:a", "mission:b", "mission:derived"]),))
    before = await _snapshot(store)
    async with aiosqlite.connect(store.path) as db:
        await db.executescript(MIGRATION_31)
        await db.executescript(MIGRATION_31)
    after = await _snapshot(store)
    assert after == before
    origins = {r["origin"] for r in await store.fetchall(
        "SELECT origin FROM owner_model_episodes WHERE episode_ref = 'mission:derived'")}
    assert origins == {"HINDSIGHT_DERIVED"}
    # Re-running migrate() at v31 is a no-op too.
    await store.migrate()
    assert await _snapshot(store) == before


async def test_legacy_candidate_continues_under_the_origin_rule(tmp_path, monkeypatch):
    """A migrated CANDIDATE (2 legacy system episodes) is promoted by a 3rd SYSTEM episode
    and not by a derived one."""
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    store = await _legacy_store(tmp_path, monkeypatch)
    await store.migrate()
    missions = MissionService(store)
    refs = []
    for name in ("x", "y"):
        m = await missions.create(owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
                                  origin_channel=OriginChannel.VOICE, title=name, goal=name)
        refs.append(f"mission:{m.mission_id}")
    model = OwnerCognitiveModel(store)
    kwargs = dict(owner_principal_id="owner", field=OwnerModelField.REASONING_PREFERENCE,
                  value="thorough")
    held = await model.observe(**kwargs, episode_ref=refs[0],
                               origin=ObservationOrigin.HINDSIGHT_DERIVED)
    assert held.assertion_id == "oca_cand"
    assert held.state is AssertionState.CANDIDATE and not held.may_act_on
    promoted = await model.observe(**kwargs, episode_ref=refs[1],
                                   origin=ObservationOrigin.SYSTEM_OBSERVED)
    assert promoted.state is AssertionState.EVIDENCED and promoted.evidencing_episode_count == 3


@pytest.mark.parametrize("table", ["owner_model_episodes", "owner_model_revisions",
                                   "owner_model_outbox"])
async def test_new_tables_exist_on_a_fresh_database(tmp_path, table):
    store = Store(str(tmp_path / "fresh.sqlite3"))
    await store.migrate()
    assert await store.fetchone(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
