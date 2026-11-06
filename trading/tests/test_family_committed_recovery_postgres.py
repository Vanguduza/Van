"""Native recovery inside an owner transaction reads only original commits."""
from contextlib import closing

import pytest

from test_postgres_ledger_isolation import pg_dsn, event
from test_account_lifecycle import _command, _append_command
from vati.core.ledger import LedgerError, committed_source_snapshot
from vati.core.ledger_pg import PostgresLedger
from vati.execution.recovery_scope import NativePositionHistory


def test_native_recovery_inside_writer_excludes_staged_original_commands(pg_dsn):
    with closing(PostgresLedger(pg_dsn, ledger_name='native-book')) as writer, closing(
        PostgresLedger(pg_dsn, ledger_name='foreign-book')
    ) as foreign:
        original = _command('original-committed')
        staged = _command('original-not-committed')
        unrelated = _command('foreign-committed')
        _append_command(writer, original)
        _append_command(foreign, unrelated)
        head = writer.head()
        with pytest.raises(RuntimeError, match='rollback original writer'):
            with writer.atomic():
                _append_command(writer, staged)
                with pytest.raises(LedgerError, match='requires_idle_or_readonly'):
                    with committed_source_snapshot(writer):
                        pytest.fail('writer must not become committed source')
                history = NativePositionHistory(writer, account_alias='acct', venue='paper')
                assert set(history.commands) == {original.trade_intent_id}
                assert writer._atomic_depth == 1
                assert writer.count() == 2  # the reader did not roll back the caller
                assert writer.head() != head
                raise RuntimeError('rollback original writer')
        assert writer.head() == head and writer.count() == 1
        assert writer.verify_chain() == (True, 1)
        _append_command(writer, staged)
        assert set(NativePositionHistory(writer, account_alias='acct', venue='paper').commands) == {
            original.trade_intent_id, staged.trade_intent_id,
        }


def test_independent_committed_reader_is_repeatable_read_only_and_closes(pg_dsn):
    with closing(PostgresLedger(pg_dsn, ledger_name='native-book')) as writer:
        writer.append(event(1))
        with pytest.raises(RuntimeError, match='consumer failure'):
            with writer.committed_reader() as reader:
                connection = reader._conn
                with connection.cursor() as cursor:
                    cursor.execute('SHOW transaction_read_only')
                    assert cursor.fetchone() == ('on',)
                    cursor.execute('SHOW transaction_isolation')
                    assert cursor.fetchone() == ('repeatable read',)
                with committed_source_snapshot(reader):
                    assert reader.verify_chain() == (True, 1)
                    assert [row.hash for row in reader.iter()] == [event(1).hash]
                    writer.append(event(2))
                    assert reader.verify_chain() == (True, 1)
                    assert [row.hash for row in reader.iter()] == [event(1).hash]
                    with pytest.raises(LedgerError, match='cannot append'):
                        reader.append(event(3))
                    raise RuntimeError('consumer failure')
        assert connection.closed
        assert writer.verify_chain() == (True, 2)
        assert [row.hash for row in writer.iter()] == [event(1).hash, event(2).hash]
