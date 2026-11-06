"""Actual paper owner constraints remain distinct from entry-size constraints."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_paper_contract_valuation import order
from vati.execution.paper import PaperAdapter, PaperCloseContract


def test_paper_close_capture_is_bound_to_original_position_and_enforced_grid():
    contract = PaperCloseContract(D('.01'), partial_min=D('.02'), minimum_remaining=D('.01'))
    adapter = PaperAdapter(close_contracts={'EURUSD': contract})
    receipt = adapter.submit(order(adapter, 'EURUSD', qty='.055'), now_ms=1000)
    pid = receipt.broker_position_id
    capture = adapter.close_capability_capture(pid)
    assert capture['scope']['position_id'] == pid
    assert capture['scope']['trade_intent_id'] == receipt.trade_intent_id
    assert capture['contract_ref'] == contract.digest
    assert capture['contract']['provider_qualified'] is False
    assert capture['partial_allowed'] and capture['full_close_allowed']
    for qty in ('.015', '.01', '.05'):
        refused = adapter.close(pid, D(qty), now_ms=1100, reason='test')
        assert refused.status == 'REJECTED' and refused.filled_qty == 0
        assert adapter.positions()[0].quantity == D('.055')
    partial = adapter.close(pid, D('.02'), now_ms=1200, reason='test')
    assert partial.filled_qty == D('.02')
    # Exact odd-lot full close does not round down to the partial grid/minimum.
    full = adapter.close(pid, None, now_ms=1300, reason='test')
    assert full.filled_qty == D('.035') and not adapter.positions()
    assert adapter.close_capability_capture(pid) is None


def test_paper_close_binding_cannot_rewrite_an_open_or_pending_original_contract():
    contract = PaperCloseContract(D('.01'))
    config = {'EURUSD': contract}
    adapter = PaperAdapter(close_contracts=config)
    receipt = adapter.submit(order(adapter, 'EURUSD', qty='.05'), now_ms=1000)
    config['EURUSD'] = replace(contract, quantity_quantum=D('.001'))
    adapter.close_contracts['EURUSD'] = config['EURUSD']
    assert adapter.close_capability_capture(receipt.broker_position_id)['contract_ref'] == contract.digest
    with pytest.raises(ValueError, match='original open position'):
        adapter.bind_close_contracts(config)
    adapter = PaperAdapter(close_contracts={'EURUSD': contract})
    adapter.mark('EURUSD', D('101'), D('101'), now_ms=1000)
    cmd = replace(order(adapter, 'EURUSD'), entry_type='PASSIVE_LIMIT')
    assert adapter.submit(cmd, now_ms=1100).status == 'ACCEPTED'
    with pytest.raises(ValueError, match='original pending order'):
        adapter.bind_close_contracts(config)


def test_legacy_continuous_paper_owner_does_not_invent_an_automatic_partial_quantum():
    adapter = PaperAdapter()
    receipt = adapter.submit(order(adapter, 'EURUSD', qty='.035'), now_ms=1000)
    capture = adapter.close_capability_capture(receipt.broker_position_id)
    assert capture['contract']['quantity_quantum'] is None
    assert not capture['partial_allowed'] and capture['full_close_allowed']
    adapter.inject_disconnect = True
    assert adapter.close_capability_capture(receipt.broker_position_id) is None


def test_service_close_configuration_is_explicit_and_does_not_reinterpret_entry_limits():
    from vati.app.service import paper_close_contracts_from_config
    assert paper_close_contracts_from_config({})=={}
    config={'EURUSD':{'quantity_quantum':'.01','partial_min':'.02','revision':'source-simulator-close/2'}}
    owned=paper_close_contracts_from_config(config)
    adapter=PaperAdapter(close_contracts=owned)
    receipt=adapter.submit(order(adapter,'EURUSD',qty='.055'),now_ms=1000)
    assert adapter.close(receipt.broker_position_id,D('.015'),now_ms=1100,reason='test').status=='REJECTED'
    assert adapter.close(receipt.broker_position_id,None,now_ms=1200,reason='test').filled_qty==D('.055')
    for invalid in ({'EURUSD':{'quantity_quantum':'.01'}},
                    {'EURUSD':{'quantity_quantum':'.01','revision':'x','provider_qualified':True}},
                    {'eurusd':{'quantity_quantum':'.01','revision':'x'}}):
        with pytest.raises(ValueError):paper_close_contracts_from_config(invalid)
