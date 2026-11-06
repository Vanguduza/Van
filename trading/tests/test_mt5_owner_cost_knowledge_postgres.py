"""An independent SQL owner restores the original cost, without recapture."""
from test_postgres_ledger_isolation import pg_dsn
from test_mt5_owner_cost_knowledge import owner_cost_path
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger


def test_original_owner_cost_survives_postgres_reconnect_and_current_model_change(pg_dsn):
    writer = PostgresLedger(pg_dsn, ledger_name='owner-original-cost')
    try:
        receipt, original = owner_cost_path(writer, '.1')
        count = writer.count()
    finally:
        writer.close()
    reader = PostgresLedger(pg_dsn, ledger_name='owner-original-cost')
    other = PostgresLedger(pg_dsn, ledger_name='other-owner-cost')
    try:
        rows = list(reader.iter(EventKind.TCA_RECORD))
        assert len(rows) == 1 and rows[0].hash == original.hash
        from test_account_trade_lifecycle import _lifecycle
        from vati.execution.zse_ticket import OwnerTicketAdapter
        from decimal import Decimal as D
        from test_mt5_owner_cost_knowledge import ORDER
        life = _lifecycle(reader, OwnerTicketAdapter(equity=D('1000000'), csd_verified=True))
        life.modelled_costs['DELTA'] = D('.2')
        life.adopt_owner_buy_confirmation(receipt, order_payload=ORDER)
        assert life.entries['intent-1']['cost_ratio'] == D(str(rows[0].payload['cost_ratio']))
        assert reader.count() == count and other.count() == 0
    finally:
        other.close()
        reader.close()
