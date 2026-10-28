"""Actual independent SQL readback and pending-risk refusal after late facts."""
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_native_entry_volume import dispatched,observe
from vati.core.ledger_pg import PostgresLedger
from vati.risk.contracts import NativeAccountRiskContext
from vati.risk.native_margin_book import NativeMarginBook
from vati.risk.native_entry_volume import NativeEntryVolumeError
from vati.risk.physical_pending import project_pending_risk


def test_postgres_original_gross_entry_readback_survives_reconnect_without_cross_namespace_borrowing(pg_dsn,tmp_path,eurusd):
    owner=PostgresLedger(pg_dsn,ledger_name='gross-entry-original')
    try:
        _,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd,ledger=owner)
        observe(owner,clock,[(1,2,7,200000,None),(2,2,7,300000,D('-.01'))])
        original=book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
        count=owner.count()
    finally:owner.close()
    reader=PostgresLedger(pg_dsn,ledger_name='gross-entry-original')
    other=PostgresLedger(pg_dsn,ledger_name='gross-entry-empty')
    try:
        assert NativeMarginBook(reader).lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])==original
        with pytest.raises(NativeEntryVolumeError,match='ORIGINAL_ENTRY_MARGIN_UNAVAILABLE'):
            NativeMarginBook(other).lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
        assert reader.count()==count and reader.verify_chain()[0] and other.count()==0
    finally:other.close();reader.close()


def test_postgres_pending_owner_invalidates_cached_no_effect_after_independent_native_fill(pg_dsn,tmp_path,eurusd):
    writer=PostgresLedger(pg_dsn,ledger_name='gross-entry-late')
    reader=PostgresLedger(pg_dsn,ledger_name='gross-entry-late')
    try:
        _,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd,ledger=writer,
            receipt_changes={'status':'REJECTED','filled_qty':D('0'),'average_fill':None})
        q=book.lookup_entry(command.command_hash,binding['source_ref'])['observation']
        context=NativeAccountRiskContext(**q['native_account_context']);runtime=SimpleNamespace()
        assert project_pending_risk(runtime,reader,context,(),now_ms=clock['ms'],contracts={})==((), '')
        observe(writer,clock,[(1,2,7,200000,None)])
        pending,issue=project_pending_risk(runtime,reader,context,(),now_ms=clock['ms'],contracts={})
        assert pending==() and issue.startswith('NATIVE_PENDING_RISK_UNAVAILABLE:')
        assert NativeMarginBook(reader).lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])['observed_gross_filled_volume_cents']==200000
    finally:reader.close();writer.close()
