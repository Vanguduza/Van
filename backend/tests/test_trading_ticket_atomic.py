"""Concurrent confirmations must record exactly one broker fill and preserve the chain."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from van_gateway.trading.service import TradingControlError, TradingService
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger


class SyntheticAuthority:
    def verify(self, token, **kwargs):
        return type("Authority", (), {"ref": "synthetic-verified:" + token})()


def service(path):
    return TradingService(str(path), owner_authority=SyntheticAuthority())


def seed(path, qty="1200"):
    led = Ledger(path)
    led.append(make_event(EventKind.OWNER_TICKET, "test", {"ticket": "T-1", "qty": qty},
        event_time_ms=1, received_time_ms=1, correlation_id="intent"))
    led.close()


@pytest.mark.parametrize("price,qty", [("NaN", "1"), ("sNaN", "1"), ("Infinity", "1"), ("1", "Infinity"), ("1", "-1")])
def test_nonfinite_or_negative_fill_never_records(tmp_path, price, qty):
    ledger_path = tmp_path / "ledger.sqlite"
    seed(ledger_path)
    with pytest.raises(ValueError):
        service(ledger_path).confirm_ticket("T-1", owner_signature_ref="test", fill_price=price,
            filled_qty=qty, contract_note_ref="CN")
    assert service(ledger_path).tickets()[0]["status"] == "OPEN"


def test_concurrent_confirmations_record_once(tmp_path):
    path = tmp_path / "ledger.sqlite"
    seed(path)
    barrier = Barrier(2)
    def confirm(index):
        barrier.wait()
        try:
            return service(path).confirm_ticket("T-1", owner_signature_ref=str(index), fill_price="25.1",
                filled_qty="1100", contract_note_ref="CN")
        except TradingControlError:
            return "CONFLICT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, (1, 2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert results.count("CONFLICT") == 1
    led = Ledger(path)
    try:
        assert led.verify_chain() == (True, 2)
        assert sum(ev.payload.get("action") == "CONFIRMED" for ev in led.iter(EventKind.OWNER_TICKET)) == 1
    finally:
        led.close()


def test_nested_append_rolls_back_with_atomic_validation(tmp_path):
    path = tmp_path / "ledger.sqlite"
    seed(path)
    led = Ledger(path)
    with pytest.raises(RuntimeError):
        with led.atomic():
            led.append(make_event(EventKind.SESSION, "test", {}, event_time_ms=2, received_time_ms=2))
            raise RuntimeError("abort")
    assert led.verify_chain() == (True, 1)
    led.close()
