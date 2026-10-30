"""Production paper P&L must use each configured contract's account units."""
from dataclasses import replace
from decimal import Decimal as D
import os

import pytest

from test_single_session_lease import config
from vati.app.service import SessionService
from vati.execution.base import OrderCommand,StopMode
from vati.execution.paper import PaperAdapter
from vati.risk.contracts import Direction,LossModel
from vati.risk.serde import contract_to_dict


def order(adapter,symbol,*,intent='fixture-entry',direction=Direction.LONG,entry='100',qty='2'):
    return OrderCommand(intent,'fixture-decision',intent,adapter.account_alias,adapter.venue,
        symbol,direction,'MARKET',D(qty),D(entry),D('90') if direction is Direction.LONG else D('110'),
        StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()


@pytest.mark.parametrize('direction',[Direction.LONG,Direction.SHORT])
def test_actual_single_runtime_marks_and_closes_using_its_symbol_contract(tmp_path,eurusd,direction):
    contract=replace(eurusd,symbol='XAUUSD',base_currency='XAU',tick_size=D('.01'),tick_value=D('1'),contract_size=D('100'))
    cfg=config(tmp_path,contract);cfg.symbol=contract.symbol;cfg.base='XAU'
    service=SessionService(cfg,lambda now:[],clock=lambda:1000).build()
    adapter=service.adapter
    try:
        adapter.spread=adapter.slippage=D('0')
        rec=adapter.submit(order(adapter,contract.symbol,direction=direction),now_ms=1000)
        assert rec.status=='FILLED'
        price=D('101') if direction is Direction.LONG else D('99')
        adapter.mark(contract.symbol,price,price,now_ms=1100)
        assert adapter.sync_account().equity-adapter.equity==D('200')
        adapter.close(rec.broker_position_id,D('.5'),now_ms=1200,reason='partial-owner-exit')
        assert adapter.realised_pnl==D('50')
        assert adapter.sync_account().equity==D('10200')
        adapter.close(rec.broker_position_id,None,now_ms=1300,reason='owner-exit')
        assert adapter.realised_pnl==D('200') and not adapter.positions()
    finally:service.close();service._ledger.close()


def test_real_runtime_refuses_an_unknown_symbol_before_it_can_open_or_rest(tmp_path,eurusd):
    service=SessionService(config(tmp_path,eurusd),lambda now:[],clock=lambda:1000).build()
    try:
        adapter=service.adapter
        result=adapter.submit(order(adapter,'UNCONFIGURED'),now_ms=1000)
        assert result.status=='REJECTED' and not adapter.positions() and not adapter.pending
    finally:service.close();service._ledger.close()


def test_runtime_does_not_label_foreign_currency_contract_pnl_as_account_currency(tmp_path,eurusd):
    contract=replace(eurusd,account_currency='EUR')
    cfg=config(tmp_path,contract)
    with pytest.raises((ValueError,RuntimeError),match='currency'):
        service=SessionService(cfg,lambda now:[],clock=lambda:1000).build()
        service.close();service._ledger.close()


@pytest.mark.parametrize('tick_value',['0','-1','NaN','Infinity'])
def test_invalid_contract_money_units_are_refused_before_runtime_storage(tmp_path,eurusd,tick_value):
    cfg=config(tmp_path,replace(eurusd,tick_value=D(tick_value)))
    with pytest.raises(ValueError,match='valuation'):
        SessionService(cfg,lambda now:[],clock=lambda:1000).build()
    assert not (tmp_path/'native.sqlite').exists()


def test_pending_entries_keep_their_admitted_money_units_and_reject_contract_rebinding(eurusd):
    contract=replace(eurusd,venue='paper',tick_value=D('.5'))
    original={contract.symbol:contract}
    adapter=PaperAdapter(spread=D('0'),slippage=D('0'),symbol_contracts=original)
    adapter.mark(contract.symbol,D('101'),D('101'),now_ms=1000)
    command=replace(order(adapter,contract.symbol),entry_type='PASSIVE_LIMIT')
    assert adapter.submit(command,now_ms=1100).status=='ACCEPTED'
    original[contract.symbol]=replace(contract,tick_value=D('1000'))
    adapter.symbol_contracts[contract.symbol]=original[contract.symbol]
    with pytest.raises(ValueError,match='rescale'):
        adapter.bind_contracts(original)
    adapter.mark(contract.symbol,D('100'),D('100'),now_ms=1200)
    adapter.mark(contract.symbol,D('101'),D('101'),now_ms=1300)
    assert adapter.sync_account().equity==D('110000')  # 2 lots * 1 * (.5/.00001)


def test_backtest_account_reports_its_configured_contract_currency(eurusd,monkeypatch):
    import vati.backtest.engine as module
    from test_backtest_runner_cli import fx_cfg,fx_engine,synthetic_bars
    from vati.intelligence.events import EventMatrix
    from vati.market_data import FX_CALENDAR
    currencies=[]
    class ObservedPaper(PaperAdapter):
        def sync_account(self):
            account=super().sync_account();currencies.append(account.currency);return account
    monkeypatch.setattr(module,'PaperAdapter',ObservedPaper)
    cfg=fx_cfg(replace(eurusd,account_currency='EUR'))
    result=module.BacktestEngine(cfg=cfg,engine=fx_engine(cfg),cost_fn=lambda state:D('.0003'),
        calendar=FX_CALENDAR,events=EventMatrix()).run(synthetic_bars())
    assert result.trades>0 and currencies and set(currencies)=={'EUR'}


@pytest.mark.skipif(not os.environ.get('VATI_TEST_PG_DSN'),reason='requires isolated PostgreSQL fixture')
def test_actual_book_factory_uses_each_instruments_own_money_units(tmp_path,eurusd):
    from vati.app.account_service import AccountCoordinatorService
    first=replace(eurusd,tick_size=D('.01'),tick_value=D('1'))
    second=replace(first,symbol='XAUUSD',base_currency='XAU',tick_value=D('2'))
    cfg=config(tmp_path,first,ledger=os.environ['VATI_TEST_PG_DSN'])
    cfg.lake_root=str(tmp_path/'lake')
    cfg.instruments=[{'symbol':second.symbol,'base':second.base_currency,'quote':'USD','contract':contract_to_dict(second)}]
    service=AccountCoordinatorService(cfg,clock=lambda:1000).build()
    try:
        adapter=service.adapter;adapter.spread=adapter.slippage=D('0')
        for contract in (first,second):
            result=adapter.submit(order(adapter,contract.symbol,intent='fixture-'+contract.symbol),now_ms=1000)
            assert result.status=='FILLED'
            adapter.mark(contract.symbol,D('101'),D('101'),now_ms=1100)
            adapter.close(result.broker_position_id,None,now_ms=1200,reason='owner-exit')
        assert adapter.realised_pnl==D('600') and adapter.equity==D('10600')
    finally:service._lease_store.close();service._ledger.close()
