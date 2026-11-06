"""A working native order can still fill even when its current gross is zero."""
from decimal import Decimal as D

import pytest

from test_native_order_book import setup_order,capture
from vati.risk.physical_pending import PhysicalPendingRisk


def test_live_zero_fill_order_contradicts_original_no_effect_receipt(tmp_path,eurusd):
    parts=setup_order(tmp_path,eurusd,receipt_changes={'status':'REJECTED','filled_qty':D(0),'average_fill':None})
    ledger,adapter,book,clock,command,binding,context=parts
    try:
        warm=PhysicalPendingRisk(ledger,context,now_ms=clock['ms'])
        assert warm.refresh((),now_ms=clock['ms'])==()
        adapter.transport.order_reply['order']['orderStatus']='ORDER_STATUS_ACCEPTED'
        adapter.transport.order_reply['order']['executedVolume']=0
        adapter.transport.order_reply['deal']=[]
        capture(parts)
        with pytest.raises(ValueError,match='native order'):
            warm.refresh((),now_ms=clock['ms'])
        with pytest.raises(ValueError,match='native order'):
            PhysicalPendingRisk(ledger,context,now_ms=clock['ms'])
    finally:ledger.close()
