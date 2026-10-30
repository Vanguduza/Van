"""Downstream owner-adoption fixture, not owner authority or native execution."""
from decimal import Decimal as D
from dataclasses import replace
from test_account_trade_lifecycle import _lifecycle, _owner_receipt, _durable_receipt
from vati.execution.zse_ticket import OwnerTicketAdapter
from vati.core import Ledger, EventKind


def test_original_measured_cost_remains_in_reconstructed_owner_entry(tmp_path):
    ledger = Ledger(tmp_path/'owner-cost.sqlite3')
    try:
        life = _lifecycle(ledger, OwnerTicketAdapter(equity=D('1000000'), csd_verified=True))
        receipt = replace(_owner_receipt(price='24.90'), fees=D('1.25'), receipt_hash='').sealed()
        _durable_receipt(ledger, receipt)
        order = {'symbol':'DELTA','direction':'LONG','strategy_id':'ZSE-VALUE-ROTATION-01',
            'entry_price':'25.00','protective_stop':'22.50','targets':['30.00']}
        life.adopt_owner_buy_confirmation(receipt, order_payload=order)
        original = life.entries['intent-1']['cost_ratio']
        life.adopt_owner_buy_confirmation(receipt, order_payload=order)
        assert life.entries['intent-1'].get('cost_ratio') == original
        assert ledger.count(EventKind.TCA_RECORD) == 1
    finally:
        ledger.close()
