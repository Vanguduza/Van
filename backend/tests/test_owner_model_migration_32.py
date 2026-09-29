"""Migration 32 — reviewer D's M5/M4/O2 repairs reach a database whether or not it ran 31.

M5 — Migration 31 demoted only CANDIDATE/EVIDENCED. A legacy CONFIRMED row with no
owner confirmation, whose refs were all unresolvable, stayed CONFIRMED, and the personal
capsule then labelled it owner_stated at S0_OWNER_PROJECT_TRUTH with
evidencing_episode_count 0 (D's probe O3).
"""

from __future__ import annotations

import aiosqlite
from test_owner_model_migration import _insert_legacy, _v30_store

from van_gateway.storage import db as dbmod
from van_gateway.storage.db import MIGRATION_32_OWNER_MODEL_REPAIR, Store
from van_gateway.understanding.owner_model import AssertionState, OwnerCognitiveModel
from van_gateway.understanding.personal_context import build_personal_capsule


async def _missions(store, owner: str, *names: str, source_command_id: str | None = None):
    from van_gateway.mission.models import AuthorityEnvelope, MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    kw = {}
    if source_command_id:
        kw["authority_envelope"] = AuthorityEnvelope(source_command_id=source_command_id)
    out = []
    for name in names:
        m = await MissionService(store).create(
            owner_principal_id=owner, origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title=name, goal=name, **kw)
        out.append(m.mission_id)
    return out


async def _v31_store(tmp_path, monkeypatch) -> Store:
    """A database that already ran 31 — the case an edit of 31 would never reach."""
    store = Store(str(tmp_path / "v31.sqlite3"))
    monkeypatch.delitem(dbmod.MIGRATIONS, 32)
    await store.migrate()
    monkeypatch.undo()
    assert (await store.fetchone("SELECT MAX(version) AS v FROM schema_migrations"))["v"] == 31
    return store


async def _state(store, aid):
    return await store.fetchone(
        "SELECT state, confidence, owner_confirmed_at_ms, supporting_episode_refs_json "
        "FROM owner_cognitive_model WHERE assertion_id = ?", (aid,))


async def test_evidence_minted_confirmed_is_not_owner_stated_after_migration(tmp_path, monkeypatch):
    """D's probe O3, asserted."""
    store = await _v30_store(tmp_path, monkeypatch)
    await _insert_legacy(store, "oca_legacy_conf", "owner", "communication_preferences",
                         "terse", "CONFIRMED", ["typo1", "typo2", "hindsight://x"])
    await store.migrate()
    row = await _state(store, "oca_legacy_conf")
    assert row["state"] == "OBSERVED" and row["confidence"] == 0.0
    cap = await build_personal_capsule(OwnerCognitiveModel(store), "owner", purpose="probe")
    assert not any(i["owner_stated"] for i in cap["content"]["assertions"])
    assert all(i["state"] != "CONFIRMED" for i in cap["content"]["assertions"])


async def test_confirmed_is_kept_only_for_a_real_owner_confirmation(tmp_path, monkeypatch):
    store = await _v30_store(tmp_path, monkeypatch)
    a, b, c = await _missions(store, "owner", "a", "b", "c")
    real = [f"mission:{a}", f"mission:{b}", f"mission:{c}"]
    # Evidence-minted CONFIRMED with three real episodes: EVIDENCED is the ceiling.
    await _insert_legacy(store, "oca_ev", "owner", "communication_preferences", "t",
                         "CONFIRMED", real)
    # An autonomy-bearing field never passes CANDIDATE on evidence.
    await _insert_legacy(store, "oca_auto", "owner", "delegation_preferences", "d",
                         "CONFIRMED", real)
    # The owner really confirmed this one; its refs being garbage does not matter.
    await _insert_legacy(store, "oca_owner", "owner", "values", "v", "CONFIRMED", ["typo"])
    await store.execute("UPDATE owner_cognitive_model SET owner_confirmed_at_ms = 5, "
                        "confidence = 1.0 WHERE assertion_id = 'oca_owner'")
    await store.migrate()
    model = OwnerCognitiveModel(store)
    ev, auto, owner = [await model.get(x) for x in ("oca_ev", "oca_auto", "oca_owner")]
    assert ev.state is AssertionState.EVIDENCED and ev.confidence == 0.7
    assert ev.owner_confirmed_at_ms is None
    assert auto.state is AssertionState.CANDIDATE and not auto.may_act_on
    assert owner.state is AssertionState.CONFIRMED and owner.confidence == 1.0
    assert owner.owner_confirmed_at_ms == 5


async def test_migration_32_repairs_a_database_that_already_ran_31(tmp_path, monkeypatch):
    """Rows written after 31 by the pre-fix code: a CONFIRMED legacy row 31 left alone, an
    assertion evidenced by another principal's missions (O2), and one evidenced by a
    mission plus the command that opened it (M4)."""
    store = await _v31_store(tmp_path, monkeypatch)
    await store.execute(
        "INSERT INTO audit(id, command_id, result, created_at_unix) VALUES ('a1', 'cmd-1', 'ok', 1)")
    opened, = await _missions(store, "owner", "opened", source_command_id="cmd-1")
    other, = await _missions(store, "owner", "other")
    m1, m2, m3 = await _missions(store, "mallory", "m1", "m2", "m3")
    rows = {
        "oca_conf": ("communication_preferences", "CONFIRMED", []),
        "oca_foreign": ("reasoning_preferences", "EVIDENCED",
                        [f"mission:{m1}", f"mission:{m2}", f"mission:{m3}"]),
        "oca_pair": ("evidence_preferences", "EVIDENCED",
                     [f"mission:{opened}", "command:cmd-1", f"mission:{other}"]),
    }
    for aid, (field, state, refs) in rows.items():
        await _insert_legacy(store, aid, "owner", field, "x", state, refs)
        for ref in refs:
            await store.execute(
                "INSERT INTO owner_model_episodes(assertion_id, episode_ref, origin, "
                "recorded_at_ms) VALUES (?, ?, 'SYSTEM_OBSERVED', 1)", (aid, ref))
    await store.execute("INSERT INTO owner_model_revisions VALUES ('owner', 4, 1), ('bystander', 9, 1)")

    await store.migrate()

    model = OwnerCognitiveModel(store)
    conf, foreign, pair = [await model.get(x) for x in ("oca_conf", "oca_foreign", "oca_pair")]
    assert conf.state is AssertionState.OBSERVED
    assert foreign.state is AssertionState.OBSERVED and foreign.evidencing_episode_count == 0
    assert foreign.supporting_episode_refs == []
    assert {(e.episode_ref, e.origin.value) for e in foreign.episodes} == {
        (f"mission:{m}", "MODEL_INFERRED") for m in (m1, m2, m3)}
    assert pair.state is AssertionState.CANDIDATE and pair.evidencing_episode_count == 2
    assert pair.confidence == 0.45 and not pair.may_act_on
    # C2: the owner's labels changed, so a capsule issued before the repair is refused;
    # an owner with nothing changed keeps its revision.
    assert await model.current_revision("owner") == 5
    assert await model.current_revision("bystander") == 9

    # Idempotent: re-running the repair changes nothing and bumps nothing.
    snapshot = [tuple(r) for r in await store.fetchall(
        "SELECT a.assertion_id, a.state, a.confidence, a.supporting_episode_refs_json, "
        "e.episode_ref, e.origin FROM owner_cognitive_model a "
        "LEFT JOIN owner_model_episodes e USING (assertion_id) ORDER BY 1, 5, 6")]
    async with aiosqlite.connect(store.path) as db:
        await db.executescript(MIGRATION_32_OWNER_MODEL_REPAIR)
        await db.executescript(MIGRATION_32_OWNER_MODEL_REPAIR)
    assert [tuple(r) for r in await store.fetchall(
        "SELECT a.assertion_id, a.state, a.confidence, a.supporting_episode_refs_json, "
        "e.episode_ref, e.origin FROM owner_cognitive_model a "
        "LEFT JOIN owner_model_episodes e USING (assertion_id) ORDER BY 1, 5, 6")] == snapshot
    assert await model.current_revision("owner") == 5


async def test_migration_32_reruns_after_a_crash_before_its_version_row(tmp_path, monkeypatch):
    """A-MIN-VAN (reviewer D2): 32's plain ALTER TABLE ADD COLUMNs were not re-runnable.
    `executescript` autocommits, so dying after the script but before the
    schema_migrations insert left version 31 recorded with the columns present, and every
    later migrate raised "duplicate column name: next_attempt_at_ms"."""
    from van_gateway.storage.db import MIGRATION_32, MIGRATION_32_OUTBOX_COLUMNS

    store = await _v31_store(tmp_path, monkeypatch)
    # Everything migration 32 does, as the pre-fix script did it, then the process dies.
    async with aiosqlite.connect(store.path) as db:
        for name, decl in MIGRATION_32_OUTBOX_COLUMNS:
            await db.execute(f"ALTER TABLE owner_model_outbox ADD COLUMN {name} {decl}")
        await db.commit()
        await db.executescript(MIGRATION_32)
    assert (await store.fetchone("SELECT MAX(version) AS v FROM schema_migrations"))["v"] == 31
    await store.migrate()
    assert (await store.fetchone("SELECT MAX(version) AS v FROM schema_migrations"))["v"] == 32
    cols = [r["name"] for r in await store.fetchall("PRAGMA table_info(owner_model_outbox)")]
    assert cols[-2:] == ["next_attempt_at_ms", "dead_lettered_at_ms"]
    assert cols.count("next_attempt_at_ms") == 1 and cols.count("dead_lettered_at_ms") == 1

    # ...and the recovered schema is the one a fresh database gets.
    fresh = Store(str(tmp_path / "fresh.sqlite3"))
    await fresh.migrate()
    q = "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    assert [tuple(r) for r in await store.fetchall(q)] == [tuple(r) for r in await fresh.fetchall(q)]


async def test_migration_32_reruns_after_a_crash_between_its_two_columns(tmp_path, monkeypatch):
    store = await _v31_store(tmp_path, monkeypatch)
    async with aiosqlite.connect(store.path) as db:
        await db.execute("ALTER TABLE owner_model_outbox ADD COLUMN next_attempt_at_ms INTEGER")
        await db.commit()
    await store.migrate()
    cols = [r["name"] for r in await store.fetchall("PRAGMA table_info(owner_model_outbox)")]
    assert cols[-2:] == ["next_attempt_at_ms", "dead_lettered_at_ms"]
