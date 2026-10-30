"""Caller arithmetic settings cannot change original native financial facts."""
from contextlib import contextmanager, closing
from dataclasses import replace
from decimal import (Decimal as D, localcontext, Inexact, Rounded, ROUND_UP,
                     ROUND_DOWN, DefaultContext)

import pytest
from test_funding_journal import statement as cash_statement
from test_native_deal_journal import statement as deal_statement
from test_mt5_funding_contract import frame
from test_ctrader_money_precision import NativeFunds
from test_retirement_venue_observations import ctrader
from test_postgres_ledger_isolation import pg_dsn
from vati.core.ledger import Ledger
from vati.core.ledger_pg import PostgresLedger
from vati.funding.journal import FundingBook
from vati.funding.deal_journal import DealBook


@contextmanager
def caller_context(mode):
    with localcontext() as ctx:
        ctx.clear_flags()
        if mode == 'narrow':
            ctx.prec=2;ctx.Emin=-2;ctx.Emax=2;ctx.rounding=ROUND_UP
        elif mode == 'trapping':
            ctx.prec=2;ctx.rounding=ROUND_DOWN
            ctx.traps[Inexact]=ctx.traps[Rounded]=True
        before=ctx.copy()
        yield ctx
        assert ctx.prec==before.prec and ctx.Emin==before.Emin and ctx.Emax==before.Emax
        assert ctx.rounding==before.rounding and ctx.traps==before.traps and ctx.flags==before.flags


@pytest.fixture(params=['sqlite','postgres'])
def ledger(request,tmp_path):
    value=(Ledger(tmp_path/'native-context.sqlite') if request.param=='sqlite' else
           PostgresLedger(request.getfixturevalue('pg_dsn'),ledger_name='native-context'))
    with closing(value):yield value


@pytest.mark.parametrize('mode',['narrow','trapping'])
@pytest.mark.parametrize('source_factory,book_type',[(cash_statement,FundingBook),(deal_statement,DealBook)],ids=['cash','deals'])
def test_original_native_source_record_read_and_replay_are_context_independent(ledger,mode,source_factory,book_type):
    source=source_factory()
    # Extra zeros are numerically exact at native precision; Rounded is not a source defect.
    if book_type is FundingBook:
        source=replace(source,movements=(replace(source.movements[0],delta=D('0.01234567000')),))
    else:
        source=replace(source,deals=(replace(source.deals[0],commission=D('-0.23000')),))
    original_body=source.body();book=book_type(ledger,clock=lambda:5000)
    with caller_context(mode):
        receipt=book.record_statement(source)
        facts=book.observations(source.scope_hash)
        assert book.record_statement(source)==receipt
    assert source.body()==original_body and facts['state']=='OBSERVED'
    assert facts[book.row_field][0][book.row_label]==original_body[book.row_field][0]
    assert receipt['execution_authority'] is False and ledger.count(book.kind)==1
    assert ledger.verify_chain()[0]


@pytest.mark.parametrize('mode',['narrow','trapping'])
def test_mt5_net_equity_preserves_native_decimal_text_without_caller_flags(mode):
    source=frame();body=source.body()
    with caller_context(mode):
        assert source.net_equity==D('10000')
        assert source.mark_body()['net_equity']=='10000'
    assert source.body()==body


@pytest.mark.parametrize('mode',['narrow','trapping'])
def test_ctrader_original_pnl_and_margin_are_independent_of_caller_context(mode):
    native=NativeFunds();native.trader['totalMarginCalculationType']='SUM'
    native.pnl['positionUnrealizedPnL'][0]['netUnrealizedPnL']=-25001
    native.positions[0].update(usedMargin=123456789,moneyDigits=8)
    adapter=ctrader(native)
    expected=adapter.sync_account()
    assert expected.equity==D('75.5299') and expected.used_margin==D('1.23456789')
    with caller_context(mode):
        actual=adapter.sync_account()
        assert (actual.equity,actual.balance,actual.used_margin,actual.free_margin,actual.margin_level_pct)==(
            expected.equity,expected.balance,expected.used_margin,expected.free_margin,expected.margin_level_pct)
    assert all(name.endswith('Req') and name not in {'ProtoOANewOrderReq','ProtoOAWithdrawReq'} for name,_ in native.requests)


@pytest.mark.parametrize('book_type,source_factory',[(FundingBook,cash_statement),(DealBook,deal_statement)],ids=['cash','deals'])
def test_unrepresentable_native_precision_remains_rejected(book_type,source_factory):
    source=source_factory()
    if book_type is FundingBook:source=replace(source,movements=(replace(source.movements[0],delta=D('0.000000001')),))
    else:source=replace(source,deals=(replace(source.deals[0],commission=D('0.000000001')),))
    with caller_context('trapping'):
        with pytest.raises(ValueError,match='precision_invalid'):book_type._validate(source)


def test_mutable_decimal_defaults_cannot_override_native_arithmetic(monkeypatch):
    source=frame();native=NativeFunds();native.trader['totalMarginCalculationType']='SUM'
    native.positions[0].update(usedMargin=123456789,moneyDigits=8)
    expected=ctrader(native).sync_account()
    with localcontext():
        monkeypatch.setattr(DefaultContext,'prec',2)
        monkeypatch.setattr(DefaultContext,'rounding',ROUND_UP)
        monkeypatch.setattr(DefaultContext,'Emin',-2)
        monkeypatch.setattr(DefaultContext,'Emax',2)
        monkeypatch.setitem(DefaultContext.traps,Inexact,True)
        monkeypatch.setitem(DefaultContext.traps,Rounded,True)
        FundingBook._validate(cash_statement());DealBook._validate(deal_statement())
        assert source.net_equity==D('10000')
        actual=ctrader(native).sync_account()
        assert actual.equity==expected.equity and actual.margin_level_pct==expected.margin_level_pct
