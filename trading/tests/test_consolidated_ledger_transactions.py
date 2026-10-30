"""Integration regression: incremental verification must preserve atomic writer work.

These transaction doubles exercise the PostgreSQL ledger's real reader methods;
this is source regression evidence, not a claim of live PostgreSQL qualification.
"""
import hashlib

import pytest

from vati.core.canonical import canonical_json
from vati.core.events import EventKind, make_event
from vati.core.ledger import GENESIS
from vati.core.ledger_pg import PostgresLedger


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, args=()):
        self.query = query

    def fetchone(self):
        return (1,) if "COUNT(*)" in self.query else (self.connection.chain,)

    def __iter__(self):
        return iter([self.connection.row])


class Connection:
    def __init__(self):
        event = make_event(EventKind.SESSION, "regression", {"event": "pending"}, event_time_ms=1, received_time_ms=1)
        self.chain = hashlib.sha256((GENESIS + event.hash).encode()).hexdigest()
        self.row = (event.hash, GENESIS, self.chain, canonical_json(event.payload), event.kind.value,
                    event.producer, event.correlation_id, event.event_time_ms, event.received_time_ms,
                    event.decision_time_ms, event.schema_version, 1)
        self.pending = ["writer-effect"]
        self.committed = []
        self.rollbacks = 0

    def cursor(self):
        return Cursor(self)

    def rollback(self):
        self.rollbacks += 1
        self.pending.clear()

    def commit(self):
        self.committed.extend(self.pending)
        self.pending.clear()


def ledger():
    value = object.__new__(PostgresLedger)
    value.name = "vati"
    value._atomic_depth = 0
    value._conn = Connection()
    return value


READERS = (
    lambda led: led._verify_from(0, GENESIS),
    lambda led: led._chain_at(1),
    lambda led: led._count_upto(1),
    lambda led: led.verify_chain(),
)


@pytest.mark.parametrize("read", READERS)
def test_verification_read_preserves_atomic_pending_work(read):
    led = ledger()
    with led.atomic():
        read(led)
        assert led._conn.pending == ["writer-effect"]
        assert led._conn.rollbacks == 0
    assert led._conn.committed == ["writer-effect"]


@pytest.mark.parametrize("read", READERS)
def test_standalone_verification_read_finishes_its_transaction(read):
    led = ledger()
    read(led)
    assert led._conn.rollbacks >= 1
    assert not led._conn.pending


def test_corrupt_chain_refusal_does_not_abort_the_callers_transaction():
    led = ledger()
    led._conn.row = ("corrupt",) + led._conn.row[1:]
    with led.atomic():
        assert led._verify_from(0, GENESIS)[0] is False
        assert led._conn.pending == ["writer-effect"]
        assert led._conn.rollbacks == 0
