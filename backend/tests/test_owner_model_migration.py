"""Migration 31 — legacy supporting episodes become SYSTEM_OBSERVED, idempotently.

Why SYSTEM_OBSERVED: before this migration the only producer of `observe()` was the
internal-control observe route, every accepted episode had to resolve to a real mission
or audit row, and no derived-origin (Hindsight/OpenViking/model) producer existed.
"""

from __future__ import annotations

import aiosqlite
import pytest

from van_gateway.storage import db as dbmod
from van_gateway.storage.db import MEMORY_FABRIC_MIGRATION_31, Store
from van_gateway.understanding.owner_model import (
    AssertionState,
    ObservationOrigin,
    OwnerCognitiveModel,
    OwnerModelField,
)

# Legacy refs as the old code stored them. `{a}`/`{b}`/`{c}` are replaced by real mission
# ids and `{cmd}` by a real audit command id; everything else names nothing that happened.
LEGACY = [
    # assertion_id, owner, field, value, state, refs
    ("oca_ev", "owner", "communication_preferences", "terse", "EVIDENCED",
     ["mission:{a}", "mission:{b}", "mission:{c}"]),
    ("oca_cand", "owner", "reasoning_preferences", "thorough", "CANDIDATE",
     ["mission:{a}", "mission:{b}"]),
    ("oca_other", "someone-else", "values", "honesty", "OBSERVED", ["command:{cmd}"]),
]


async def _real_episodes(store) -> dict[str, str]:
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    missions = MissionService(store)
    ids = {}
    for name in ("a", "b", "c"):
        m = await missions.create(owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
                                  origin_channel=OriginChannel.VOICE, title=name, goal=name)
        ids[name] = m.mission_id
    ids["cmd"] = "cmd-legacy-1"
    await store.execute(
        "INSERT INTO audit(id, command_id, result, created_at_unix) VALUES (?, ?, 'ok', 1)",
        ("aud-legacy-1", ids["cmd"]))
    return ids


async def _v30_store(tmp_path, monkeypatch, name="legacy.sqlite3") -> Store:
    store = Store(str(tmp_path / name))
    # Every version after 30 is withheld, not only 31: a later version applied on its own
    # would record a higher schema version and 31 would then never run.
    for version in [v for v in dbmod.MIGRATIONS if v > 45]:
        monkeypatch.delitem(dbmod.MIGRATIONS, version)
    await store.migrate()
    monkeypatch.undo()
    assert 46 in dbmod.MIGRATIONS and 47 in dbmod.MIGRATIONS
    return store


async def _insert_legacy(store, aid, owner, field, value, state, refs):
    await store.execute(
        "INSERT INTO owner_cognitive_model(assertion_id, owner_principal_id, field, value, "
        "state, confidence, evidence_refs_json, supporting_episode_refs_json, "
        "created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, 0.5, '[]', ?, 1, 7)",
        (aid, owner, field, value, state, Store.dumps(refs)),
    )


async def _legacy_store(tmp_path, monkeypatch) -> Store:
    """A database migrated to v30 only, holding assertions written the old way."""
    store = await _v30_store(tmp_path, monkeypatch)
    ids = await _real_episodes(store)
    store.legacy_ids = ids  # type: ignore[attr-defined]
    for aid, owner, field, value, state, refs in LEGACY:
        await _insert_legacy(store, aid, owner, field, value, state,
                             [r.format(**ids) for r in refs])
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
    ids = store.legacy_ids
    expected = sorted((aid, ref.format(**ids), "SYSTEM_OBSERVED", 7)
                      for aid, *_, refs in LEGACY for ref in refs)
    assert eps == expected
    assert revs == [("owner", 1), ("someone-else", 1)]
    version = await store.fetchone("SELECT MAX(version) AS v FROM schema_migrations")
    assert version["v"] == dbmod.SCHEMA_VERSION

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
        (Store.dumps([f"mission:{store.legacy_ids['a']}", f"mission:{store.legacy_ids['b']}",
                      "mission:derived"]),))
    before = await _snapshot(store)
    async with aiosqlite.connect(store.path) as db:
        await db.executescript(MEMORY_FABRIC_MIGRATION_31)
        await db.executescript(MEMORY_FABRIC_MIGRATION_31)
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


async def test_unresolvable_legacy_refs_are_backfilled_non_evidencing(tmp_path, monkeypatch):
    """N2 — free text, a derived-memory URI and a mission that does not exist are not
    things VAN saw. They are kept for provenance as MODEL_INFERRED and never evidence."""
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    store = await _v30_store(tmp_path, monkeypatch)
    ids = await _real_episodes(store)
    garbage = ["hindsight://m1", "free text", "mission:nope", "command: ghost"]
    await _insert_legacy(store, "oca_g", "owner", "communication_preferences", "t",
                         "OBSERVED", garbage)
    # Pre-P1-SYM-001 shape: a ladder state built on refs that never resolved, plus two
    # spellings of one real mission and a real command with an upper-case kind.
    await _insert_legacy(store, "oca_gev", "owner", "evidence_preferences", "e", "EVIDENCED",
                         ["note:1", "note:2", f"mission:{ids['a']}", f" MISSION :\t{ids['a']} ",
                          f"COMMAND:{ids['cmd']}"])
    await store.migrate()

    rows = {(r["assertion_id"], r["episode_ref"]): r["origin"] for r in await store.fetchall(
        "SELECT * FROM owner_model_episodes WHERE assertion_id IN ('oca_g', 'oca_gev')")}
    assert rows == {
        **{("oca_g", g): "MODEL_INFERRED" for g in garbage},
        ("oca_gev", "note:1"): "MODEL_INFERRED",
        ("oca_gev", "note:2"): "MODEL_INFERRED",
        ("oca_gev", f"mission:{ids['a']}"): "SYSTEM_OBSERVED",
        ("oca_gev", f"command:{ids['cmd']}"): "SYSTEM_OBSERVED",
    }
    model = OwnerCognitiveModel(store)
    demoted = await model.get("oca_gev")
    assert demoted.evidencing_episode_count == 2
    assert demoted.state is AssertionState.CANDIDATE and not demoted.may_act_on
    assert demoted.supporting_episode_refs == sorted(
        [f"command:{ids['cmd']}", f"mission:{ids['a']}"])
    g = await model.get("oca_g")
    assert g.evidencing_episode_count == 0 and g.confidence == 0.0 and g.supporting_episode_refs == []

    # The reviewer's attack: one real observation after migration must not make it EVIDENCED.
    real = await MissionService(store).create(
        owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE, title="r", goal="r")
    after = await model.observe(owner_principal_id="owner",
                                field=OwnerModelField.COMMUNICATION_PREFERENCE, value="t",
                                episode_ref=f"mission:{real.mission_id}",
                                origin=ObservationOrigin.SYSTEM_OBSERVED)
    assert after.assertion_id == "oca_g"
    assert after.evidencing_episode_count == 1
    assert after.state is AssertionState.OBSERVED and not after.may_act_on

    # Idempotent and never-relabel, even once the missing mission comes to exist.
    before = await _snapshot(store)
    states = [tuple(r) for r in await store.fetchall(
        "SELECT assertion_id, state, confidence, supporting_episode_refs_json "
        "FROM owner_cognitive_model ORDER BY 1")]
    await store.execute(
        "INSERT INTO audit(id, command_id, result, created_at_unix) VALUES ('aud-g', 'ghost', 'ok', 2)")
    # A stale JSON still naming the unresolved spelling: the re-run must match the existing
    # MODEL_INFERRED row by its raw spelling, not insert a SYSTEM row under `command:ghost`.
    await store.execute("UPDATE owner_cognitive_model SET supporting_episode_refs_json = ? "
                        "WHERE assertion_id = 'oca_g'", (Store.dumps(garbage),))
    async with aiosqlite.connect(store.path) as db:
        await db.executescript(MEMORY_FABRIC_MIGRATION_31)
        await db.executescript(MEMORY_FABRIC_MIGRATION_31)
    assert await _snapshot(store) == before
    assert [tuple(r) for r in await store.fetchall(
        "SELECT assertion_id, state, confidence, supporting_episode_refs_json "
        "FROM owner_cognitive_model ORDER BY 1")] == states
    assert (await store.fetchone(
        "SELECT origin FROM owner_model_episodes WHERE assertion_id = 'oca_g' "
        "AND episode_ref = 'command: ghost'"))["origin"] == "MODEL_INFERRED"
    assert await store.fetchone(
        "SELECT 1 FROM owner_model_episodes WHERE episode_ref = 'command:ghost'") is None
