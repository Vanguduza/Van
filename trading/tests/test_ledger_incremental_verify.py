"""P1-TRADE-LEDGER-001 — the per-decision ledger check must not grow with the ledger.

`DecisionCycle._risk_store_ok` re-hashed the whole ledger from genesis on every risk
snapshot. A 2,000-bar backtest spent 149 of 164 s there; a live session slows the same
way. `verify_incremental` checks only new rows against an anchor, and each way of
tampering it must still catch is broken on purpose here.
"""
from __future__ import annotations

import hashlib
import json

from vati.core.canonical import canonical_json
from vati.core.events import EventKind, make_event
from vati.core.ledger import GENESIS, IncrementalChainVerifier, Ledger


def _ev(i: int):
    return make_event(EventKind.SESSION, "test", {"i": i}, event_time_ms=1_000 + i, received_time_ms=1_000 + i, correlation_id=f"c{i}")


def _ledger(n: int) -> Ledger:
    led = Ledger(":memory:")
    for i in range(n):
        led.append(_ev(i))
    return led


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_incremental_cost_tracks_new_rows_not_ledger_size():
    led = _ledger(500)
    v = IncrementalChainVerifier(led, clock=_Clock())
    assert v.verify() == (True, 500) and v.last_rows_checked == 500 and v.full_verifications == 1
    for i in range(500, 503):
        led.append(_ev(i))
    assert v.verify() == (True, 503)
    assert v.last_rows_checked == 3, "only the three new rows may be re-hashed"
    assert v.verify() == (True, 503) and v.last_rows_checked == 0
    assert v.full_verifications == 1


def test_result_matches_full_verification_on_an_honest_ledger():
    led = _ledger(50)
    assert led.verify_incremental() == led.verify_chain() == (True, 50)


def test_a_tampered_new_row_is_caught():
    led = _ledger(20)
    v = IncrementalChainVerifier(led, clock=_Clock())
    assert v.verify()[0]
    led.append(_ev(20))
    led._conn.execute("UPDATE events SET payload_json = ? WHERE seq = 21", (canonical_json({"i": 999}),))
    assert v.verify()[0] is False


def test_a_chain_recomputed_from_an_old_row_moves_the_anchor_and_is_caught():
    led = _ledger(30)
    v = IncrementalChainVerifier(led, clock=_Clock())
    assert v.verify()[0]
    # Rewrite row 5 and recompute every later chain hash so the chain is self-consistent.
    rows = led._conn.execute("SELECT seq, event_hash FROM events ORDER BY seq").fetchall()
    prev = GENESIS
    for seq, eh in rows:
        if seq == 5:
            eh = hashlib.sha256(b"forged").hexdigest()
        chain = hashlib.sha256((prev + eh).encode()).hexdigest()
        led._conn.execute("UPDATE events SET event_hash = ?, prev_hash = ?, chain_hash = ? WHERE seq = ?", (eh, prev, chain, seq))
        prev = chain
    assert v.verify()[0] is False


def test_a_deleted_old_row_is_caught():
    led = _ledger(30)
    v = IncrementalChainVerifier(led, clock=_Clock())
    assert v.verify()[0]
    led._conn.execute("DELETE FROM events WHERE seq = 7")
    assert v.verify()[0] is False


def test_an_in_place_edit_of_an_old_row_is_caught_by_the_periodic_full_check():
    clock = _Clock()
    led = _ledger(30)
    v = IncrementalChainVerifier(led, full_every_s=3600, clock=clock)
    assert v.verify()[0]
    led._conn.execute("UPDATE events SET payload_json = ? WHERE seq = 3", (canonical_json({"i": -1}),))
    # The anchor and count are unchanged, so the incremental check cannot see this edit...
    assert v.verify()[0] is True
    # ...and the bound on that blind spot is the full re-verification interval.
    clock.t = 3600
    assert v.verify()[0] is False and v.full_verifications == 2


def test_after_a_failure_the_next_check_is_a_full_verification():
    led = _ledger(10)
    v = IncrementalChainVerifier(led, clock=_Clock())
    assert v.verify()[0]
    led._conn.execute("DELETE FROM events WHERE seq = 2")
    assert v.verify()[0] is False
    before = v.full_verifications
    assert v.verify()[0] is False and v.full_verifications == before + 1


def test_the_decision_paths_use_the_incremental_check():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "vati" / "app"
    for name, attr in (("cycle.py", "self.ledger"), ("account_service.py", "self._ledger")):
        src = (root / name).read_text()
        assert f"{attr}.verify_incremental()" in src, name
        assert f"{attr}.verify_chain()" not in src, f"{name} re-verifies from genesis per decision"
