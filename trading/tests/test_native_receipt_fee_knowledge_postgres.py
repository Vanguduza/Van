"""The original unknown-fee receipt remains unknown across PostgreSQL owners."""
from test_postgres_ledger_isolation import pg_dsn
from test_native_receipt_fee_knowledge import durable_unknown_fee_path
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.app.trade_lifecycle import AccountTradeLifecycle


def test_original_unknown_native_charge_survives_independent_postgres_readback(pg_dsn):
    writer = PostgresLedger(pg_dsn, ledger_name='native-unknown-charge')
    try:
        receipt_hash, event_hash = durable_unknown_fee_path(writer)
    finally:
        writer.close()
    reader = PostgresLedger(pg_dsn, ledger_name='native-unknown-charge')
    other = PostgresLedger(pg_dsn, ledger_name='other-native-account')
    try:
        event = next(reader.iter(EventKind.EXECUTION_RECEIPT))
        assert event.hash == event_hash
        receipt = AccountTradeLifecycle._receipt_from_payload(event.payload)
        assert receipt.receipt_hash == receipt_hash and receipt.fees is None
        assert reader.count(EventKind.TCA_RECORD) == 0 and reader.verify_chain()[0]
        assert other.count() == 0
    finally:
        other.close()
        reader.close()
