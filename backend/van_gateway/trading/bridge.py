"""Trading → device event bridge.

The embodiment reducer (Android `VanEmbodimentReducer`) celebrates only on a
`trading.trade.closed` event whose `quadrant` is GOOD_DECISION_GOOD_OUTCOME, and
the Activity feed shows closed trades with their attribution. Nothing produced
that event: the ledger is on the trading host and the device event stream is the
gateway's. This bridge reads the trading history read model on the scheduler
cadence and publishes one owner-visible event per newly closed trade.

It is a projection, not an authority: it never writes to the ledger, never sizes,
never sends. Publication is idempotent across restarts because the events table
itself is the cursor: a trade already published is found there and skipped.
"""
from __future__ import annotations

import json
from typing import Any

from van_gateway.events.bus import EventBus
from van_gateway.storage.db import Store

EVENT_TYPE = "trading.trade.closed"


class TradingEventBridge:
    def __init__(self, store: Store, trading: Any, events: EventBus, *, batch: int = 50) -> None:
        self.store = store
        self.trading = trading
        self.events = events
        self.batch = batch

    async def _published(self) -> set[str]:
        rows = await self.store.fetchall(
            "SELECT payload_json FROM events WHERE event_type = ?", (EVENT_TYPE,)
        )
        seen: set[str] = set()
        for row in rows:
            try:
                seen.add(str(json.loads(row["payload_json"]).get("trade_intent_id", "")))
            except (TypeError, ValueError):
                continue
        seen.discard("")
        return seen

    async def run(self, now_ms: int | None = None) -> dict[str, Any]:
        history = self.trading.history(limit=self.batch)
        if not history.get("ledger_available", False):
            return {"published": 0, "ledger_available": False}
        seen = await self._published()
        published = 0
        for trade in reversed(history.get("history", [])):
            trade_id = str(trade.get("trade_intent_id") or "")
            if not trade_id or trade_id in seen:
                continue
            quadrant = trade.get("quadrant") or {}
            await self.events.publish(EVENT_TYPE, {
                "trade_intent_id": trade_id,
                "strategy_id": trade.get("strategy_id"),
                "outcome": trade.get("outcome"),
                "r_multiple": trade.get("r_multiple"),
                "exit_reason": trade.get("exit_reason"),
                "closed_ms": trade.get("closed_ms"),
                "quadrant": quadrant.get("quadrant") if isinstance(quadrant, dict) else quadrant,
                "summary": _summary(trade),
            })
            seen.add(trade_id)
            published += 1
        return {"published": published, "ledger_available": True}


def _summary(trade: dict[str, Any]) -> str:
    strategy = trade.get("strategy_id") or "a strategy"
    r = trade.get("r_multiple")
    quadrant = trade.get("quadrant") or {}
    q = quadrant.get("quadrant") if isinstance(quadrant, dict) else quadrant
    parts = [f"Closed a {strategy} trade"]
    if r is not None:
        parts.append(f"at {r}R")
    if q:
        parts.append(f"({str(q).replace('_', ' ').lower()})")
    return " ".join(parts) + "."
