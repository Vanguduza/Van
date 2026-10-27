"""Original native account query bindings survive actual PostgreSQL recovery."""
from contextlib import contextmanager

import pytest

from test_postgres_ledger_isolation import pg_dsn
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account


@pytest.mark.parametrize('lost_ack', [False, True])
def test_original_query_is_recovered_without_cross_ledger_or_new_authority(pg_dsn, tmp_path, lost_ack):
    from test_mt5_funding_runtime import setup
    unused, adapter, account = setup(tmp_path)
    unused.close()
    ledger = PostgresLedger(pg_dsn, ledger_name='original-native-risk')
    other = PostgresLedger(pg_dsn, ledger_name='unrelated-native-risk')
    try:
        if lost_ack:
            atomic = ledger.atomic
            depth = 0
            @contextmanager
            def ack_lost():
                nonlocal depth
                outer = depth == 0
                depth += 1
                try:
                    with atomic():
                        yield
                finally:
                    depth -= 1
                if outer:
                    raise OSError('isolated original PostgreSQL commit acknowledgement lost')
            ledger.atomic = ack_lost
            try:
                with pytest.raises(OSError, match='acknowledgement lost'):
                    capture_cached_mt5(ledger, account, now_ms=10000)
            finally:
                ledger.atomic = atomic
        captured = capture_cached_mt5(ledger, account, now_ms=10000)
        query = next(ledger.iter(EventKind.FUNDING_MT5_QUERY))
        count = ledger.count()
        with ledger.read_snapshot():
            original = context_for_account(ledger, adapter, account, now_ms=10000,
                mt5_capture=captured)
        assert original.source_query_ref == query.hash == captured['query_ref']
        assert query.received_time_ms == 10000
        with pytest.raises(ValueError, match='does not bind current facts'):
            context_for_account(other, adapter, account, now_ms=10000, mt5_capture=captured)
        ledger.close()
        ledger = PostgresLedger(pg_dsn, ledger_name='original-native-risk')
        replayed = capture_cached_mt5(ledger, account, now_ms=15000)
        recovered = context_for_account(ledger, adapter, account, now_ms=15000,
            mt5_capture=replayed)
        assert recovered == original and ledger.count() == count and other.count() == 0
        assert ledger.count(EventKind.FUNDING_MT5_QUERY) == 1
        assert next(ledger.iter(EventKind.FUNDING_MT5_QUERY)).body() == query.body()
        assert ledger.verify_chain()[0]
        assert recovered.risk_capital_qualified is recovered.execution_authority is False
        assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0
    finally:
        ledger.close()
        other.close()
