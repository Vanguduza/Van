"""Independent short-side source checks; no native financial effect."""
from dataclasses import replace
from decimal import Decimal as D
import pytest
from conftest import NOW,intent,snapshot,eurusd
from conftest import _register_owner_authority_key,_reap_ctrader_fixture_sockets
from test_mt5_expected_margin import source as mt5_source
from test_native_margin_book import setup_book
from test_native_risk_history_inputs import record
from test_entry_margin_binding import entry_command
from vati.core import EventKind
from vati.risk.contracts import Direction
from vati.risk.native_margin_book import NativeMarginBook


@pytest.mark.parametrize('provider',['mt5','ctrader'])
def test_original_short_selects_actual_sell_estimate_and_never_sends(tmp_path,eurusd,provider):
    if provider=='mt5':
        sdk,worker,adapter,now,ledger,context=mt5_source(tmp_path,at=NOW*1000)
        facts=snapshot(eurusd,account_alias=adapter.account_alias,balance=D('10000'),equity=D('10000'),
            used_margin=D('0'),free_margin=D('10000'),margin_level_pct=None,native_account_context=context)
        book=NativeMarginBook(ledger,clock=lambda:now['ms']);quantity=D('.10')
    else:
        ledger,adapter,old,book,now,facts=setup_book(tmp_path,eurusd)
        facts=replace(facts,used_margin=D('0'),free_margin=D('10000'),margin_level_pct=None)
        quantity=D('.123')
    try:
        request=intent(venue=provider,account_alias=adapter.account_alias,direction=Direction.SHORT,stop=D('1.10230'))
        original=record(ledger,facts,request=request)
        cmd=replace(entry_command(original),quantity=quantity,command_hash='').sealed()
        assert quantity<=D(original.payload['decision']['approved_size'])
        receipt=book.capture_entry(adapter,original.hash,cmd,deadline_ms=NOW*1000+2000)
        read=book.lookup_entry(cmd.command_hash,receipt['source_ref'])
        assert read['command']['direction']=='SHORT'
        assert read['receipt']['execution_authority'] is read['receipt']['reservation_qualified'] is False
        if provider=='mt5':
            assert read['observation']['request']['type']=='SELL'
            assert sdk.margin_calls[-1][0]==sdk.ORDER_TYPE_SELL and not sdk.sent
        else:
            assert read['estimate_money']==read['observation']['sell_margin']
            assert read['estimate_money']!=read['observation']['buy_margin']
        assert ledger.count(EventKind.ORDER_COMMAND)==0
    finally:ledger.close()
