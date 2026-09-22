"""The trading event bridge publishes each closed trade once, with its quadrant."""
from __future__ import annotations

import pytest

from van_gateway.events.bus import EventBus
from van_gateway.storage.db import Store
from van_gateway.trading.bridge import EVENT_TYPE, TradingEventBridge


class _Trading:
    def __init__(self, rows, available=True):
        self.rows = rows
        self.available = available

    def history(self, limit=50):
        return {"ledger_available": self.available, "history": self.rows[:limit]}


def _row(tid, quadrant="GOOD_DECISION_GOOD_OUTCOME", r="1.8"):
    return {"trade_intent_id": tid, "strategy_id": "fx_trend_pullback", "outcome": "WIN",
            "r_multiple": r, "exit_reason": "TARGET", "closed_ms": 1000,
            "quadrant": {"quadrant": quadrant}}


@pytest.mark.asyncio
async def test_publishes_each_closed_trade_once(tmp_path):
    store = Store(str(tmp_path / "b.sqlite3")); await store.migrate()
    bus = EventBus(store, 50)
    bridge = TradingEventBridge(store, _Trading([_row("t1"), _row("t2", "BAD_DECISION_GOOD_OUTCOME")]), bus)
    first = await bridge.run()
    assert first == {"published": 2, "ledger_available": True}
    second = await bridge.run()
    assert second["published"] == 0
    rows = await store.fetchall("SELECT event_type, payload_json FROM events WHERE event_type = ?", (EVENT_TYPE,))
    assert len(rows) == 2
    joined = " ".join(r["payload_json"] for r in rows)
    assert "GOOD_DECISION_GOOD_OUTCOME" in joined and "BAD_DECISION_GOOD_OUTCOME" in joined


@pytest.mark.asyncio
async def test_unavailable_ledger_publishes_nothing(tmp_path):
    store = Store(str(tmp_path / "c.sqlite3")); await store.migrate()
    bridge = TradingEventBridge(store, _Trading([_row("t1")], available=False), EventBus(store, 50))
    assert await bridge.run() == {"published": 0, "ledger_available": False}
    assert await store.fetchall("SELECT 1 FROM events WHERE event_type = ?", (EVENT_TYPE,)) == []
