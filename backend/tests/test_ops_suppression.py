"""P3-OPS-005 — a dismissal the owner made survives a restart.

`NotificationIntelligence._seen` was a `set()` on the instance. Restarting the
gateway re-showed notifications the owner had already dealt with, which is the
specific behaviour that teaches someone to stop reading their notifications.
"""

from __future__ import annotations

import time

import pytest

from conftest_automation import make_store
from van_gateway.attention.engine import AttentionEngine
from van_gateway.models import AttentionSeverity, AttentionState
from van_gateway.notifications.intelligence import (
    NotificationIntelligence,
    PhoneNotification,
)
from van_gateway.ops.suppression import SuppressionChannel, SuppressionStore


def _note(key="k1", text="Your parcel is out for delivery") -> PhoneNotification:
    return PhoneNotification(
        key=key, package="com.courier", title="Delivery", text=text,
        posted_at_unix=int(time.time()),
    )


@pytest.mark.asyncio
async def test_a_notification_already_shown_is_not_shown_again_after_a_restart(tmp_path):
    store = await make_store(tmp_path)
    suppressions = SuppressionStore(store)

    before = NotificationIntelligence(suppressions=suppressions)
    first = await before.ingest_durable(_note())
    assert first.suppressed is False

    # A brand-new instance: the process restarted and the set() is empty again.
    after = NotificationIntelligence(suppressions=suppressions)
    second = await after.ingest_durable(_note())
    assert second.suppressed is True
    assert second.reason == "duplicate"


@pytest.mark.asyncio
async def test_without_a_store_the_classifier_still_works_and_says_so(tmp_path):
    """The pure classifier stays constructible — several tests exercise only the
    redaction rules — but then dedupe is per-process, which is the old behaviour."""
    engine = NotificationIntelligence()
    assert (await engine.ingest_durable(_note())).suppressed is False
    assert (await engine.ingest_durable(_note())).suppressed is True
    assert (await NotificationIntelligence().ingest_durable(_note())).suppressed is False


@pytest.mark.asyncio
async def test_a_permanent_suppression_is_distinguishable_from_a_long_one(tmp_path):
    """A set entry is forever or gone, so "suppress this for an hour" had nowhere
    to live, and "never again" could not be told apart from a long expiry."""
    store = await make_store(tmp_path)
    suppressions = SuppressionStore(store)
    now = int(time.time())

    await suppressions.suppress(
        SuppressionChannel.ATTENTION, "forever", reason="owner said never", ttl_seconds=None
    )
    await suppressions.suppress(
        SuppressionChannel.ATTENTION, "an-hour", reason="snoozed", ttl_seconds=3600
    )

    far_future = now + 10 * 365 * 86_400
    assert await suppressions.is_suppressed(
        SuppressionChannel.ATTENTION, "forever", now_unix=far_future
    ) is not None
    assert await suppressions.is_suppressed(
        SuppressionChannel.ATTENTION, "an-hour", now_unix=now + 3601
    ) is None
    assert await suppressions.is_suppressed(
        SuppressionChannel.ATTENTION, "an-hour", now_unix=now + 1800
    ) is not None


@pytest.mark.asyncio
async def test_an_expired_suppression_leaves_its_record_behind(tmp_path):
    """So "I already told you about this yesterday" stays answerable."""
    store = await make_store(tmp_path)
    suppressions = SuppressionStore(store)
    now = int(time.time())
    await suppressions.suppress(
        SuppressionChannel.NOTIFICATION, "n1", reason="shown", ttl_seconds=60, now_unix=now
    )
    assert await suppressions.is_suppressed(
        SuppressionChannel.NOTIFICATION, "n1", now_unix=now + 61
    ) is None
    assert await suppressions.get(SuppressionChannel.NOTIFICATION, "n1") is not None


@pytest.mark.asyncio
async def test_channels_do_not_collide_on_the_same_subject(tmp_path):
    store = await make_store(tmp_path)
    suppressions = SuppressionStore(store)
    await suppressions.suppress(SuppressionChannel.ATTENTION, "x", reason="a")
    assert await suppressions.is_suppressed(SuppressionChannel.DEGRADED, "x") is None


@pytest.mark.asyncio
async def test_lifting_a_suppression_says_whether_there_was_one(tmp_path):
    store = await make_store(tmp_path)
    suppressions = SuppressionStore(store)
    await suppressions.suppress(SuppressionChannel.REMINDER, "r1", reason="a")
    assert await suppressions.release(SuppressionChannel.REMINDER, "r1") is True
    assert await suppressions.release(SuppressionChannel.REMINDER, "r1") is False


@pytest.mark.asyncio
async def test_a_re_reported_condition_does_not_reopen_what_the_owner_dismissed(tmp_path):
    """The other half of P3-OPS-005, and not restart-specific: `upsert` wrote the
    caller's `state` unconditionally, so any source re-reporting the same
    condition moved an acknowledged item back to OPEN."""
    store = await make_store(tmp_path)
    engine = AttentionEngine(store, budget_per_hour=100)
    item = await engine.upsert(
        title="Hermes is offline", severity=AttentionSeverity.BLOCKER,
        source="health", dedupe_key="degraded:hermes",
    )
    await engine.acknowledge(item.id)

    again = await engine.upsert(
        title="Hermes is offline", severity=AttentionSeverity.BLOCKER,
        source="health", dedupe_key="degraded:hermes",
    )
    assert again.state is AttentionState.ACKNOWLEDGED
    open_items = {row.id for row in await engine.list_open()}
    assert item.id in open_items  # still listed, but not re-opened
    row = await store.fetchone("SELECT state FROM attention WHERE id = ?", (item.id,))
    assert row["state"] == AttentionState.ACKNOWLEDGED.value


@pytest.mark.asyncio
async def test_van_can_still_resolve_an_acknowledged_item(tmp_path):
    """The override is on a *re-report*, not on a caller that explicitly finishes
    the item — "VAN fixed the thing" must be able to close it."""
    store = await make_store(tmp_path)
    engine = AttentionEngine(store, budget_per_hour=100)
    item = await engine.upsert(
        title="Hermes is offline", severity=AttentionSeverity.BLOCKER,
        source="health", dedupe_key="degraded:hermes",
    )
    await engine.acknowledge(item.id)
    resolved = await engine.upsert(
        title="Hermes is back", severity=AttentionSeverity.INFO, source="health",
        dedupe_key="degraded:hermes", state=AttentionState.AUTO_RESOLVED,
    )
    assert resolved.state is AttentionState.AUTO_RESOLVED
