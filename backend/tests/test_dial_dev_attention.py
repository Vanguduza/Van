"""VAN-DEV-002 — DIAL approvals and blockers in VAN's one Attention queue.

DIAL VAN-DEVCC-R1 §2.2 and §8 ("Attention: dedupe per §2.2; closes only on projection
APPLIED"). The failure this exists to prevent is the one a triage queue drifts into by
default: an item that closes because the owner tapped it, or because the source stopped
mentioning it, while the decision it stood for was never applied.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import pytest_asyncio

from conftest_automation import make_store
from dial_dev_fakes import DIAL_BASE_URL, DIAL_TOKEN, FakeDial, envelope
from van_gateway.attention.engine import AttentionEngine
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.dial_dev.attention import DialDevAttentionIngest, parse_sse, severity_for
from van_gateway.dial_dev.client import DialDevClient
from van_gateway.dial_dev.config import DialDevConfig
from van_gateway.models import AttentionSeverity, AttentionState

PROJECT = "dial-development-system"
NEEDS_ME = f"/v1/dev/projects/{PROJECT}/tasks"


@pytest_asyncio.fixture
async def world(tmp_path):
    token = tmp_path / "dial-dev.token"
    token.write_text(DIAL_TOKEN)
    store = await make_store(tmp_path)
    attention = AttentionEngine(store, budget_per_hour=100)
    dial = FakeDial()
    client = DialDevClient(
        DialDevConfig(enabled=True, base_url=DIAL_BASE_URL, token_file=str(token), timeout_s=2),
        transport=dial.transport(),
    )
    degraded = DegradedRegistry()
    ingest = DialDevAttentionIngest(
        client, attention, degraded=degraded, backoff_initial_s=0.01, backoff_max_s=0.05,
    )
    dial.json("GET", "/v1/dev/projects", envelope({"projects": [{"project_id": PROJECT}]}))
    yield ingest, dial, attention, degraded
    await ingest.stop()


def serve_needs_me(dial: FakeDial, tasks: list[dict], revision: str) -> None:
    dial.json("GET", NEEDS_ME, envelope({"view": "needs_me", "tasks": tasks}, revision=revision))


def serve_task(dial: FakeDial, task_id: str, owner_items: list[dict], revision: str) -> None:
    dial.json("GET", f"/v1/dev/tasks/{task_id}",
              envelope({"task_id": task_id, "owner_items": owner_items}, revision=revision))


def approval(task_id="HOT-DU-021", decision_id="DEC-1", **extra) -> dict:
    return {
        "task_id": task_id, "title": "Approve lease widening", "state": "WAITING_OWNER",
        "critical_path": False,
        "owner_items": [{"kind": "approval", "decision_id": decision_id, **extra}],
    }


async def rows(attention: AttentionEngine) -> list[dict]:
    found = await attention.store.fetchall(
        "SELECT dedupe_key, severity, state, source, project_id, payload_json FROM attention "
        "WHERE source = 'dial-dev' ORDER BY created_at_unix, dedupe_key"
    )
    return [{**dict(r), "payload": json.loads(r["payload_json"])} for r in found]


# ------------------------------------------------------------------- severity


@pytest.mark.parametrize("item,task,expected", [
    ({"kind": "approval"}, {"state": "WAITING_OWNER"}, AttentionSeverity.FOLLOW_UP),
    ({"kind": "blocker", "critical_path": True}, {}, AttentionSeverity.BLOCKER),
    ({"kind": "blocker"}, {"critical_path": True}, AttentionSeverity.BLOCKER),
    ({"kind": "blocker", "critical_path": False}, {}, AttentionSeverity.FOLLOW_UP),
    ({"kind": "finding", "finding_domain": "security"}, {}, AttentionSeverity.URGENT),
    ({"kind": "finding", "finding_domain": "MONEY"}, {}, AttentionSeverity.URGENT),
    ({"kind": "finding", "finding_domain": "health"}, {}, AttentionSeverity.URGENT),
    ({"kind": "approval", "finding_domain": "security"}, {}, AttentionSeverity.URGENT),
    ({"kind": "lease_bypass"}, {}, AttentionSeverity.URGENT),
    ({"kind": "finding", "finding_domain": "style"}, {}, AttentionSeverity.FOLLOW_UP),
])
def test_severity_follows_section_2_2(item, task, expected):
    assert severity_for(item, task) is expected


# ---------------------------------------------------------------------- dedupe


@pytest.mark.asyncio
async def test_an_owner_item_becomes_one_attention_item_with_the_contract_shape(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    counts = await ingest.sync()
    assert counts["upserted"] == 1
    [row] = await rows(attention)
    assert row["dedupe_key"] == "dial-dev:approval:DEC-1:sha256:rev-10"
    assert row["source"] == "dial-dev"
    assert row["project_id"] == PROJECT
    assert row["severity"] == "FOLLOW_UP"
    assert row["state"] == "OPEN"
    payload = row["payload"]
    assert payload["task_id"] == "HOT-DU-021"
    assert payload["kind"] == "approval"
    assert payload["deep_link"] == "van://work/dev/tasks/HOT-DU-021"
    # Only GETs: the ingest never acts on DIAL.
    assert {r.method for r in dial.requests} == {"GET"}
    assert all(r.headers["authorization"] == f"Bearer {DIAL_TOKEN}" for r in dial.requests)


@pytest.mark.asyncio
async def test_rereading_the_same_condition_at_a_later_revision_is_the_same_item(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    serve_needs_me(dial, [approval()], "sha256:rev-11")
    await ingest.sync()
    serve_needs_me(dial, [approval()], "sha256:rev-12")
    await ingest.sync()
    found = await rows(attention)
    assert [r["dedupe_key"] for r in found] == ["dial-dev:approval:DEC-1:sha256:rev-10"]
    assert found[0]["payload"]["last_seen_projection_revision"] == "sha256:rev-12"


@pytest.mark.asyncio
async def test_dials_own_origin_revision_is_the_key_when_it_states_one(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval(origin_projection_revision="sha256:rev-3")], "sha256:rev-10")
    await ingest.sync()
    [row] = await rows(attention)
    assert row["dedupe_key"] == "dial-dev:approval:DEC-1:sha256:rev-3"


@pytest.mark.asyncio
async def test_a_blocker_without_a_decision_is_keyed_by_task(world):
    ingest, dial, attention, _ = world
    blocker = {"task_id": "HOT-DU-030", "critical_path": True,
               "owner_items": [{"kind": "blocker", "title": "External credential missing"}]}
    serve_needs_me(dial, [blocker], "sha256:rev-5")
    await ingest.sync()
    [row] = await rows(attention)
    assert row["dedupe_key"] == "dial-dev:blocker:HOT-DU-030:sha256:rev-5"
    assert row["severity"] == "BLOCKER"


@pytest.mark.asyncio
async def test_an_unknown_kind_is_skipped_rather_than_guessed(world):
    ingest, dial, attention, _ = world
    odd = {"task_id": "HOT-DU-040", "owner_items": [{"kind": "run_this_now"}, "not-a-dict"]}
    serve_needs_me(dial, [odd, {"task_id": "../x", "owner_items": [{"kind": "approval"}]}], "sha256:r")
    counts = await ingest.sync()
    assert counts["skipped"] == 3
    assert await rows(attention) == []


# ----------------------------------------------------------------- closing rule


@pytest.mark.asyncio
async def test_a_tap_does_not_close_the_item(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    [row] = await rows(attention)
    item_id = (await attention.store.fetchone(
        "SELECT id FROM attention WHERE dedupe_key = ?", (row["dedupe_key"],)))["id"]
    await attention.acknowledge(item_id)
    serve_needs_me(dial, [approval()], "sha256:rev-11")
    await ingest.sync()
    [row] = await rows(attention)
    assert row["state"] == AttentionState.ACKNOWLEDGED.value
    assert any(i.id == item_id for i in await attention.list_open())


@pytest.mark.asyncio
async def test_disappearing_from_needs_me_without_applied_evidence_leaves_it_open(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    serve_needs_me(dial, [], "sha256:rev-11")
    for state in ("OPEN", "ACCEPTED", "REJECTED", "SUPERSEDED"):
        serve_task(dial, "HOT-DU-021",
                   [{"kind": "approval", "decision_id": "DEC-1", "resolution_state": state}],
                   "sha256:rev-11")
        counts = await ingest.sync()
        assert counts["left_open"] == 1, state
        [row] = await rows(attention)
        assert row["state"] == "OPEN", state


@pytest.mark.asyncio
async def test_a_task_dial_no_longer_knows_leaves_the_item_open(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    serve_needs_me(dial, [], "sha256:rev-11")  # task detail route unset → DIAL answers 404
    await ingest.sync()
    [row] = await rows(attention)
    assert row["state"] == "OPEN"


@pytest.mark.asyncio
async def test_the_item_closes_when_the_task_projection_shows_applied(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    serve_needs_me(dial, [], "sha256:rev-12")
    serve_task(dial, "HOT-DU-021",
               [{"kind": "approval", "decision_id": "DEC-1", "resolution_state": "APPLIED"}],
               "sha256:rev-12")
    counts = await ingest.sync()
    assert counts["closed"] == 1
    [row] = await rows(attention)
    assert row["state"] == AttentionState.AUTO_RESOLVED.value
    assert row["payload"]["closed_reason"] == "APPLIED"
    assert row["payload"]["closed_at_projection_revision"] == "sha256:rev-12"
    assert await attention.list_open() == []


@pytest.mark.asyncio
async def test_the_item_closes_when_needs_me_itself_reports_applied(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    serve_needs_me(dial, [approval(resolution_state="APPLIED")], "sha256:rev-11")
    await ingest.sync()
    [row] = await rows(attention)
    assert row["state"] == AttentionState.AUTO_RESOLVED.value


@pytest.mark.asyncio
async def test_a_closed_item_is_not_reopened_by_a_late_reread(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval(origin_projection_revision="sha256:rev-3")], "sha256:rev-10")
    await ingest.sync()
    serve_needs_me(dial, [approval(origin_projection_revision="sha256:rev-3",
                                   resolution_state="APPLIED")], "sha256:rev-11")
    await ingest.sync()
    serve_needs_me(dial, [approval(origin_projection_revision="sha256:rev-3")], "sha256:rev-12")
    await ingest.sync()
    [row] = await rows(attention)
    assert row["state"] == AttentionState.AUTO_RESOLVED.value


@pytest.mark.asyncio
async def test_a_new_decision_after_one_applied_is_a_new_item(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    serve_needs_me(dial, [approval(resolution_state="APPLIED")], "sha256:rev-11")
    await ingest.sync()
    serve_needs_me(dial, [approval(decision_id="DEC-2")], "sha256:rev-12")
    await ingest.sync()
    found = await rows(attention)
    assert [(r["dedupe_key"], r["state"]) for r in found] == [
        ("dial-dev:approval:DEC-1:sha256:rev-10", "AUTO_RESOLVED"),
        ("dial-dev:approval:DEC-2:sha256:rev-12", "OPEN"),
    ]


# ------------------------------------------------------------- the event stream


def sse(*events: dict) -> httpx.Response:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


@pytest.mark.asyncio
async def test_parse_sse_decodes_frames_and_ignores_comments():
    async def lines():
        for line in [": keepalive", "", "data: {\"changed\": [\"tasks\"]}", "", "data: nope", ""]:
            yield line

    assert [e async for e in parse_sse(lines())] == [{"changed": ["tasks"]}, None]


async def _until(predicate, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_the_worker_rehydrates_on_connect_and_resyncs_on_task_changes(world):
    ingest, dial, attention, _ = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    dial.raw("GET", "/v1/dev/events", sse(
        {"projection_revision": "sha256:rev-11", "changed": ["workspaces"]},
        {"projection_revision": "sha256:rev-12", "changed": ["tasks"]},
    ))
    ingest.start()
    # One sync on connect, one for the `tasks` change, none for `workspaces`; then the
    # stream ends and the worker reconnects and rehydrates again.
    await _until(lambda: ingest.syncs >= 3)
    await ingest.stop()
    paths = [r.url.path for r in dial.requests]
    first, second = [i for i, p in enumerate(paths) if p == "/v1/dev/events"][:2]
    between = paths[first + 1:second]
    assert between.count(NEEDS_ME) == 2, between
    assert len(await rows(attention)) == 1
    assert not ingest.running


@pytest.mark.asyncio
async def test_a_workspace_only_change_does_not_resync(world):
    ingest, dial, _attention, _ = world
    serve_needs_me(dial, [], "sha256:rev-10")

    async def lines():
        for line in ['data: {"projection_revision": "r", "changed": ["workspaces", "ci"]}', ""]:
            yield line

    events = [e async for e in parse_sse(lines())]
    assert [ingest._should_sync(e) for e in events] == [False]
    assert ingest._should_sync({"changed": ["decisions"]}) is True
    assert ingest._should_sync({"no": "changed"}) is True


@pytest.mark.asyncio
async def test_a_dropped_stream_is_degraded_and_reconnects_with_backoff(world):
    ingest, dial, _attention, degraded = world
    serve_needs_me(dial, [], "sha256:rev-10")
    attempts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] <= 3:
            raise httpx.ConnectError("dial-control down")
        return sse({"projection_revision": "sha256:rev-10", "changed": []})

    dial.raw("GET", "/v1/dev/events", flaky)
    ingest.start()
    await _until(lambda: "DIAL_DEV_EVENT_STREAM_DOWN" in degraded.codes())
    await _until(lambda: ingest.connects >= 1)
    await ingest.stop()
    assert attempts["n"] >= 4
    # Stopped mid-cycle: whatever the last observation was, the worker is no longer running.
    assert not ingest.running


@pytest.mark.asyncio
async def test_a_connected_stream_clears_the_degraded_entry(world):
    ingest, dial, _attention, degraded = world
    serve_needs_me(dial, [], "sha256:rev-10")
    gate = asyncio.Event()

    class Held(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"changed": []}\n\n'
            await gate.wait()

    dial.raw("GET", "/v1/dev/events", lambda r: httpx.Response(
        200, stream=Held(), headers={"content-type": "text/event-stream"}))
    degraded.set(__import__("van_gateway.models", fromlist=["DegradedCode"]).DegradedCode.DIAL_DEV_EVENT_STREAM_DOWN, True)
    ingest.start()
    await _until(lambda: ingest.connects == 1 and ingest.syncs == 1)
    assert "DIAL_DEV_EVENT_STREAM_DOWN" not in degraded.codes()
    gate.set()
    await ingest.stop()


@pytest.mark.asyncio
async def test_sync_while_dial_is_down_marks_it_unavailable_and_changes_nothing(world):
    ingest, dial, attention, degraded = world
    serve_needs_me(dial, [approval()], "sha256:rev-10")
    await ingest.sync()
    dial.fail_with = httpx.ConnectError("down")
    assert await ingest.sync_safely() is None
    assert "DIAL_DEV_UNAVAILABLE" in degraded.codes()
    [row] = await rows(attention)
    assert row["state"] == "OPEN"


@pytest.mark.asyncio
async def test_the_app_starts_and_stops_the_worker_only_when_enabled(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    from van_gateway.app import create_app
    from van_gateway.config import get_settings

    token = tmp_path / "dial-dev.token"
    token.write_text(DIAL_TOKEN)
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "w.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("VAN_DIAL_DEV_ENABLED", "true")
    monkeypatch.setenv("VAN_DIAL_DEV_BASE_URL", DIAL_BASE_URL)
    monkeypatch.setenv("VAN_DIAL_DEV_TOKEN_FILE", str(token))
    get_settings.cache_clear()
    try:
        app = create_app()
        dial = FakeDial()
        dial.fail_with = httpx.ConnectError("not in this test")
        app.state.dial_dev_client.transport = dial.transport()
        async with app.router.lifespan_context(app):
            assert app.state.dial_dev_attention.running
        assert not app.state.dial_dev_attention.running
    finally:
        get_settings.cache_clear()
