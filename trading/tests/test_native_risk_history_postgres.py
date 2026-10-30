"""Actual disposable PostgreSQL original-history replay, never native admission."""
from contextlib import contextmanager
from dataclasses import replace

import pytest

from conftest import NOW, snapshot
from test_postgres_ledger_isolation import pg_dsn
from test_mt5_funding_runtime import setup
from test_native_risk_history_inputs import record
from test_native_risk_history_index import other_context
from vati.core import EventKind
from vati.core.ledger import LedgerError
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.native_history import original_native_risk_history, NativeRiskSourceUnavailable


@pytest.mark.parametrize('lost_ack', [False, True])
def test_original_physical_history_survives_reopen_and_original_commit_ack_loss(pg_dsn, tmp_path, eurusd, lost_ack):
    unused, adapter, account = setup(tmp_path)
    unused.close()
    ledger = PostgresLedger(pg_dsn, ledger_name='physical-history')
    other = PostgresLedger(pg_dsn, ledger_name='unrelated-history')
    try:
        capture = capture_cached_mt5(ledger, account, now_ms=10000)
        context = context_for_account(ledger, adapter, account, now_ms=10000, mt5_capture=capture)
        facts = snapshot(eurusd, account_alias=account.account_alias,
            balance=account.balance, equity=account.equity, native_account_context=context)
        first = record(ledger, facts)
        current = other_context(ledger, adapter, account, facts, alias='another_label')
        atomic = ledger.atomic
        depth = 0
        @contextmanager
        def lose_original_reply():
            nonlocal depth
            outer = depth == 0
            depth += 1
            try:
                with atomic():
                    yield
            finally:
                depth -= 1
            if outer:
                raise OSError('isolated original commit reply lost')
        if lost_ack:
            ledger.atomic = lose_original_reply
            try:
                with pytest.raises(OSError, match='original commit reply lost'):
                    with ledger.atomic():
                        record(ledger, current)
            finally:
                ledger.atomic = atomic
            second = tuple(ledger.iter(EventKind.RISK_DECISION))[-1]
        else:
            second = record(ledger, current)
        count = ledger.count()
        original = original_native_risk_history(ledger, second.hash, available_at_ms=NOW*1000)
        assert [v.event_ref for v in original.original_inputs] == [first.hash, second.hash]
        assert original.unresolved_refs == ()
        with pytest.raises(NativeRiskSourceUnavailable, match='unavailable'):
            original_native_risk_history(other, second.hash, available_at_ms=NOW*1000)
        ledger.close()
        ledger = PostgresLedger(pg_dsn, ledger_name='physical-history')
        recovered = original_native_risk_history(ledger, second.hash, available_at_ms=(NOW+90*86400)*1000)
        assert recovered == original
        assert ledger.count() == count and other.count() == 0
        assert recovered.execution_authority is recovered.risk_capital_qualified is False
        assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0] == 0
        assert ledger.verify_chain()[0]
    finally:
        ledger.close()
        other.close()


def test_staged_postgres_rows_cannot_supply_committed_physical_history(pg_dsn, tmp_path, eurusd):
    unused, adapter, account = setup(tmp_path)
    unused.close()
    ledger = PostgresLedger(pg_dsn, ledger_name='physical-history-writer')
    try:
        capture = capture_cached_mt5(ledger, account, now_ms=10000)
        context = context_for_account(ledger, adapter, account, now_ms=10000, mt5_capture=capture)
        facts = snapshot(eurusd, account_alias=account.account_alias,
            balance=account.balance, equity=account.equity, native_account_context=context)
        first = record(ledger, facts)
        before = ledger.count()
        with pytest.raises(LedgerError, match='committed_source_read_requires'):
            with ledger.atomic():
                record(ledger, replace(facts, peak_equity=facts.peak_equity+1))
                original_native_risk_history(ledger, first.hash, available_at_ms=NOW*1000)
        assert ledger.count() == before and ledger.verify_chain()[0]
    finally:
        ledger.close()
