"""Real independently connected original fee-vintage readback and scope."""
from test_postgres_ledger_isolation import pg_dsn
from test_native_fee_terms import original_fee_entry
from vati.core.ledger_pg import PostgresLedger
from vati.risk.native_margin_book import NativeMarginBook


def test_postgres_original_fee_terms_survive_reconnect_and_do_not_cross_namespaces(pg_dsn,tmp_path,eurusd):
    owner=PostgresLedger(pg_dsn,ledger_name='native-fee-original')
    try:
        _,adapter,book,clock,command,receipt=original_fee_entry(tmp_path,eurusd,ledger=owner)
        original=book.lookup_entry_fee_terms(command.command_hash,receipt['source_ref']);count=owner.count()
    finally:owner.close()
    reader=PostgresLedger(pg_dsn,ledger_name='native-fee-original')
    other=PostgresLedger(pg_dsn,ledger_name='native-fee-other')
    try:
        assert NativeMarginBook(reader).lookup_entry_fee_terms(command.command_hash,receipt['source_ref'])==original
        assert NativeMarginBook(other).lookup_entry_fee_terms(command.command_hash,receipt['source_ref']) is None
        assert reader.count()==count and reader.verify_chain()[0] and other.count()==0
    finally:other.close();reader.close()
