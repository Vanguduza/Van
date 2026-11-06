"""Real PostgreSQL recovery and consistent reads of original source history."""
from test_postgres_ledger_isolation import pg_dsn
from test_current_entry_risk_source import current_entry
from vati.core import EventKind,make_event
from vati.core.ledger_pg import PostgresLedger
from vati.risk.current_entry_source import current_entry_source,CurrentEntrySourceError
import pytest


def restore_original_history(target,original):
    # Explicit source-history migration, not a fresh native observation.
    for event in original.iter():target.append(event)
    assert target.verify_chain()[0]
    assert [e.hash for e in target.iter()]==[e.hash for e in original.iter()]


def test_postgres_original_source_reopens_without_renewal_or_other_namespace_access(pg_dsn,tmp_path,eurusd):
    sdk,clock,original,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    ledger=PostgresLedger(pg_dsn,ledger_name='current-entry-source');reopened=None;other=None
    try:
        restore_original_history(ledger,original);before=ledger.count()
        first=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
        reopened=PostgresLedger(pg_dsn,ledger_name='current-entry-source')
        old=current_entry_source(reopened,command,margin_ref,current_ref,available_at_ms=command.expires_at_ms).body()
        assert old['current_risk_ref']==first['current_risk_ref'] and old['available_at_ms']==first['available_at_ms']
        assert old['quote_valid_until_ms']==first['quote_valid_until_ms'] and old['quote_time_state']=='EXPIRED'
        other=PostgresLedger(pg_dsn,ledger_name='current-entry-source-other')
        with pytest.raises(CurrentEntrySourceError):
            current_entry_source(other,command,margin_ref,current_ref,available_at_ms=clock['ms'])
        assert ledger.count()==before and other.count()==0 and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        if other is not None:other.close()
        ledger.close();original.close()


def test_source_snapshot_retains_original_head_while_independent_postgres_writer_commits(pg_dsn,tmp_path,eurusd):
    sdk,clock,original,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    ledger=PostgresLedger(pg_dsn,ledger_name='current-entry-snapshot');writer=None
    try:
        restore_original_history(ledger,original)
        writer=PostgresLedger(pg_dsn,ledger_name='current-entry-snapshot')
        with ledger.read_snapshot():
            head=ledger.head()
            writer.append(make_event(EventKind.SESSION,'source-fixture',{'event':'SOURCE_SNAPSHOT_TEST_OBSERVATION'},
                event_time_ms=clock['ms'],received_time_ms=clock['ms']))
            source=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
            assert source['source_head']==head and ledger.head()==head
        current=current_entry_source(ledger,command,margin_ref,current_ref,available_at_ms=clock['ms']).body()
        assert current['source_head']==writer.head()!=head
        assert current['current_risk_ref']==source['current_risk_ref']
        assert current['entry_margin_ref']==source['entry_margin_ref'] and not sdk.sent
    finally:
        if writer is not None:writer.close()
        ledger.close();original.close()
