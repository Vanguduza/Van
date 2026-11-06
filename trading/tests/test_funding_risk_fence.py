"""Capital changes cannot launder native loss limits into new order permission."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as N

import pytest

from test_native_balance_reconciliation import mark, snapshot, observe, cash
from test_native_cash_history import NativeCash
from test_retirement_venue_observations import ctrader
from vati.core import EventKind, Ledger, make_event
from vati.execution.base import Health
from vati.funding.risk_fence import funding_risk_fence as native_fence
from vati.risk.contracts import MarketIntegrityState


def funding_risk_fence(ledger, adapter, account, *, now_ms=7000):
    return native_fence(ledger, adapter, account, now_ms=now_ms)


def native(point):
    adapter = ctrader(NativeCash())
    original = adapter.sync_account()
    current = replace(original, account_alias=point.account_alias, currency=point.currency,
        balance=point.balance, equity=point.net_equity, funding_mark=point)
    adapter.sync_account = lambda: current
    adapter.heartbeat = lambda **_: Health(True, 0, point.observed_at_ms)
    adapter.positions = lambda: []
    return adapter, current


def book(tmp_path, *, cash_rows=(), closing=None):
    ledger = Ledger(tmp_path/'risk.sqlite')
    first = snapshot(ledger, mark(1000))
    last = snapshot(ledger, closing or mark(3000, equity='98'))
    observe(ledger, cash=cash_rows)
    return ledger, first, last


def test_no_capital_change_uses_original_versions_without_freezing_current_unrealized_pnl(tmp_path):
    ledger, first, last = book(tmp_path)
    adapter, current = native(mark(3500, equity='97'))
    count = ledger.count(); requests = list(adapter.transport.requests)
    result = funding_risk_fence(ledger, adapter, current)
    assert result.available and first.hash in result.reason and last.hash in result.reason
    assert ledger.count() == count and adapter.transport.requests == requests


@pytest.mark.parametrize('delta,balance', [('100','200'),('-50','50')])
def test_reconciled_deposit_or_withdrawal_never_resets_raw_risk_baselines(tmp_path,delta,balance):
    point = mark(3000,balance=balance,equity=balance,version=2)
    operation = 'BALANCE_DEPOSIT' if D(delta)>0 else 'BALANCE_WITHDRAW'
    ledger,_,_ = book(tmp_path,cash_rows=[cash(delta=delta,balance=balance,operation=operation)],closing=point)
    adapter, current = native(point)
    result = funding_risk_fence(ledger,adapter,current)
    assert not result.available and result.reason.endswith('FLOW_ADJUSTED_RISK_NOT_QUALIFIED')


def test_earlier_covered_statement_does_not_hide_a_new_native_deposit(tmp_path):
    ledger,_,_ = book(tmp_path)
    adapter,current = native(mark(3500,balance='200',equity='200',version=2))
    result = funding_risk_fence(ledger,adapter,current)
    assert not result.available and result.reason.endswith('CURRENT_NATIVE_BALANCE_CHANGES_NOT_COVERED')


def test_unrelated_ib_income_cannot_remove_a_daily_loss_limit(tmp_path):
    point = mark(3000,balance='110',equity='110',version=2)
    ledger,_,_ = book(tmp_path,cash_rows=[cash(delta='10',balance='110',operation='BALANCE_DEPOSIT_IB_COMMISSIONS')],closing=point)
    adapter,current = native(point)
    result = funding_risk_fence(ledger,adapter,current)
    assert not result.available and result.reason.endswith('BUSINESS_INCOME_REQUIRES_RISK_NORMALIZATION')


@pytest.mark.parametrize('case',['missing_mark','wrong_id','wrong_realm','wrong_balance','clock_rollback','missing_version','future_mark','account_equity_mismatch'])
def test_unknown_or_incoherent_current_native_facts_hold_new_risk(tmp_path,case):
    ledger,_,_ = book(tmp_path)
    point=mark(3500,equity='98')
    if case=='wrong_id': point=replace(point,native_account_id=99999)
    if case=='wrong_realm':point=replace(point,environment='LIVE')
    if case=='wrong_balance':point=replace(point,balance=D('99'))
    if case=='clock_rollback':point=replace(point,observed_at_ms=2999)
    if case=='missing_version':point=replace(point,balance_version=None)
    if case=='future_mark':point=replace(point,observed_at_ms=8000)
    adapter,current=native(point)
    if case=='missing_mark':current=replace(current,funding_mark=None)
    if case=='account_equity_mismatch':current=replace(current,equity=D('500'))
    assert not funding_risk_fence(ledger,adapter,current).available


@pytest.mark.parametrize('decision,held',[('APPROVED',True),('REJECTED',False)])
def test_preexisting_native_risk_cannot_be_rebaselined_from_later_first_observation(tmp_path,decision,held):
    ledger,_,_ = book(tmp_path)
    ledger.append(make_event(EventKind.RISK_DECISION,'vati-cycle',{
        'inputs':{'intent':{'account_alias':'ctrader_primary','trade_intent_id':'original'}},
        'decision':{'decision':decision}},event_time_ms=999,received_time_ms=999,correlation_id='original'))
    adapter,current=native(mark(3500,equity='98'))
    result=funding_risk_fence(ledger,adapter,current)
    assert (not result.available)==held
    if held:assert result.reason.endswith('ORIGINAL_RISK_PREDATES_NATIVE_FUNDING_BASELINE')


def test_explicit_paper_cohort_is_preserved_but_a_venue_label_cannot_bypass_native_evidence(tmp_path):
    from vati.execution import PaperAdapter
    ledger=Ledger(tmp_path/'paper.sqlite');paper=PaperAdapter()
    assert funding_risk_fence(ledger,paper,paper.sync_account()).available
    result=funding_risk_fence(ledger,N(venue='paper'),paper.sync_account())
    assert not result.available and result.reason.endswith('NATIVE_PROVIDER_ACCOUNTING_NOT_IMPLEMENTED')


@pytest.mark.parametrize('producer',['single','account'])
def test_both_original_native_snapshot_producers_hold_capital_changed_risk(tmp_path,eurusd,producer):
    point=mark(3000,balance='200',equity='200',version=2)
    ledger,_,_=book(tmp_path,cash_rows=[cash()],closing=point)
    adapter,_=native(point)
    if producer=='single':
        from test_recoverable_lockouts import _cycle
        service=_cycle(eurusd,ledger);service.adapter=adapter
        service.peak_equity=service.day_start_equity=service.week_start_equity=D("100")
        value=service.snapshot(now_ms=7000,quote_age_ms=0)
    else:
        from vati.app.account_service import AccountCoordinatorService
        service=AccountCoordinatorService.__new__(AccountCoordinatorService)
        service.adapter=adapter;service.account=N();service._ledger=ledger;service.clock=lambda:7000
        service.contracts={'EURUSD':eurusd};service.peak_equity=D('100');service.day_start_equity=D('100');service.week_start_equity=D('100')
        service._entries={};service.cfg=N(account_alias='ctrader_primary',max_quote_age_ms=5000)
        service._ledger_positions=lambda:[];service._open_positions=lambda:();service._risk_store_ok=lambda:True
        service._drawdown_top_state=lambda:None;service.lifecycle=None;service.consecutive_losses=0;service.kill=N(active=[])
        service.evaluators={'EURUSD':N(last_state=N(quote_age_ms=0,event_window=None,integrity=MarketIntegrityState.NORMAL))}
        value=service._snapshot_for(N(symbol='EURUSD',strategy_id=''))
    assert value.preservation_blocks_new_risk
    assert 'FLOW_ADJUSTED_RISK_NOT_QUALIFIED' in value.preservation_reason
    assert value.day_start_equity==100 and value.equity==200


def test_evidence_failure_is_held_without_leaking_provider_error_notes(tmp_path):
    ledger,_,_=book(tmp_path);adapter,current=native(mark(3500,equity='98'))
    ledger.close()
    result=funding_risk_fence(ledger,adapter,current)
    assert not result.available and result.reason.startswith('FUNDING_RISK_EVIDENCE_UNAVAILABLE:')


@pytest.mark.parametrize('decision_ms,reason',[(2999,'CURRENT_NATIVE_MARK_AFTER_DECISION_TIME'),(5999,'NATIVE_FUNDING_AFTER_DECISION_TIME')])
def test_original_availability_cannot_be_used_before_the_risk_decision(tmp_path,decision_ms,reason):
    ledger,_,_=book(tmp_path);adapter,current=native(mark(3500,equity='98'))
    result=funding_risk_fence(ledger,adapter,current,now_ms=decision_ms)
    assert not result.available and result.reason.endswith(reason)


def test_actual_authority_cannot_admit_raw_equity_profit_created_by_a_deposit(tmp_path,eurusd):
    from conftest import mandate_dict,snapshot as risk_snapshot,intent as make_intent
    from vati.risk import RiskAuthority,TradingMandate,Decision
    point=mark(3000,balance='200',equity='200',version=2)
    ledger,_,_=book(tmp_path,cash_rows=[cash()],closing=point)
    adapter,current=native(point)
    fence=funding_risk_fence(ledger,adapter,current)
    mandate=TradingMandate.from_mapping(mandate_dict(account_alias='ctrader_primary',venue='ctrader'))
    intent=replace(make_intent(),account_alias='ctrader_primary',venue='ctrader',entry=D('1.1'),stop=D('1.0995'))
    raw=risk_snapshot(replace(eurusd,venue='ctrader',account_currency='EUR'),account_alias='ctrader_primary',equity=D('200'),balance=D('200'),
        peak_equity=D('200'),day_start_equity=D('100'),week_start_equity=D('100'),used_margin=D('0'),free_margin=D('200'),margin_level_pct=None)
    unguarded=RiskAuthority(mandate).evaluate_safe(intent,raw)
    assert unguarded.decision in {Decision.APPROVED,Decision.REDUCED},unguarded
    guarded=RiskAuthority(mandate).evaluate_safe(intent,replace(raw,preservation_blocks_new_risk=not fence.available,preservation_reason=fence.reason))
    assert guarded.decision is Decision.REJECTED and guarded.reason_code=='PRESERVATION_BLOCK'
    assert 'FLOW_ADJUSTED_RISK_NOT_QUALIFIED' in guarded.reason_detail



def test_original_order_before_the_new_native_baseline_cannot_be_forgotten(tmp_path):
    ledger,_,_=book(tmp_path);adapter,current=native(mark(3500,equity='98'))
    ledger.append(make_event(EventKind.ORDER_COMMAND,'vati-execution-router',{'account_alias':'ctrader_primary','trade_intent_id':'original-order'},
        event_time_ms=999,received_time_ms=999,correlation_id='original-order'))
    result=funding_risk_fence(ledger,adapter,current)
    assert not result.available and result.reason.endswith('ORIGINAL_ORDER_PREDATES_NATIVE_FUNDING_BASELINE')


def test_future_native_risk_history_does_not_supply_decision_time_evidence(tmp_path):
    ledger,_,_=book(tmp_path);adapter,current=native(mark(3500,equity='98'))
    ledger.append(make_event(EventKind.RISK_DECISION,'vati-cycle',{'inputs':{'intent':{'account_alias':'ctrader_primary','trade_intent_id':'future'}},
        'decision':{'decision':'APPROVED'}},event_time_ms=8000,received_time_ms=8000,correlation_id='future'))
    result=funding_risk_fence(ledger,adapter,current)
    assert not result.available and result.reason.endswith('ORIGINAL_RISK_AFTER_DECISION_TIME')


def test_owner_ticket_drafting_does_not_gain_a_native_accounting_certificate(tmp_path):
    from vati.execution import OwnerTicketAdapter
    adapter=OwnerTicketAdapter(equity=D('100'),csd_verified=True)
    result=funding_risk_fence(Ledger(tmp_path/'ticket.sqlite'),adapter,adapter.sync_account())
    assert result.available and result.reason=='OWNER_TICKET_DRAFT_ONLY_NO_NATIVE_SUBMISSION'
    assert not adapter.tickets and not adapter.positions()



def clocked_native(point):
    adapter,current=native(point);clock={'now':7000}
    def account():clock['now']=8000;return current
    def heartbeat(**_):clock['now']=9000;return Health(True,0,9000)
    def positions():clock['now']+=500;return []
    adapter.sync_account=account;adapter.heartbeat=heartbeat;adapter.positions=positions
    return adapter,clock


@pytest.mark.parametrize('producer,quote_age',[('single',17),('account',17),('single',-1)])
def test_risk_capture_uses_post_native_io_clock_and_ages_quotes(tmp_path,eurusd,producer,quote_age):
    ledger,_,_=book(tmp_path);adapter,clock=clocked_native(mark(8000,equity='98'))
    if producer=='single':
        from test_recoverable_lockouts import _cycle
        service=_cycle(eurusd,ledger);service.adapter=adapter;service._lease_clock=lambda:clock['now']
        value=service.snapshot(now_ms=7000,quote_age_ms=quote_age)
    else:
        from vati.app.account_service import AccountCoordinatorService
        service=AccountCoordinatorService.__new__(AccountCoordinatorService)
        service.adapter=adapter;service.account=N();service._ledger=ledger;service.clock=lambda:clock['now']
        service.contracts={'EURUSD':eurusd};service.peak_equity=D('100');service.day_start_equity=D('100');service.week_start_equity=D('100')
        service._entries={};service.cfg=N(account_alias='ctrader_primary',max_quote_age_ms=5000)
        service._ledger_positions=lambda:[];service._risk_store_ok=lambda:True
        def opened():clock['now']+=500;return ()
        service._open_positions=opened;service._drawdown_top_state=lambda:None
        service.lifecycle=None;service.consecutive_losses=0;service.kill=N(active=[])
        from conftest import mandate_dict
        from vati.risk import TradingMandate
        service.mandate=TradingMandate.from_mapping(mandate_dict(account_alias='ctrader_primary',
            venue=adapter.venue,signed_at_unix=1,expires_at_unix=3600))
        service.evaluators={'EURUSD':N(last_state=N(as_of_ms=7000,quote_age_ms=quote_age,event_window=None,integrity=MarketIntegrityState.NORMAL))}
        value=service._snapshot_for(N(symbol='EURUSD',strategy_id=''))
    assert clock['now']==10000 and value.now_unix==10
    assert value.quote_age_ms==(quote_age+3000 if quote_age>=0 else quote_age)
    assert not value.preservation_blocks_new_risk,value.preservation_reason


def test_single_runtime_records_risk_after_the_facts_it_waited_for(tmp_path,eurusd):
    from conftest import mandate_dict,intent as make_intent
    from test_intelligence import mk_bars
    from vati.app import DecisionCycle,SessionConfig
    from vati.intelligence.events import EventMatrix
    from vati.market_data import FX_CALENDAR
    from vati.risk import StrategyState
    ledger,_,_=book(tmp_path,cash_rows=[cash()],closing=mark(3000,balance='200',equity='200',version=2))
    adapter,clock=clocked_native(mark(8000,balance='200',equity='200',version=2))
    mandate=mandate_dict(account_alias='ctrader_primary',venue='ctrader',mode='DEMO_TRADER',signed_at_unix=1,expires_at_unix=10000)
    cfg=SessionConfig(symbol='EURUSD',base='EUR',quote='USD',venue='ctrader',account_alias='ctrader_primary',
        contract=replace(eurusd,venue='ctrader',account_currency='EUR'),mandate_dict=mandate,session_id='source-clock')
    intent=make_intent(account_alias='ctrader_primary',venue='ctrader',strategy_state=StrategyState.DEMO)
    engine=N(assess=lambda *a,**k:N(intent=intent,decision='CANDIDATE',abstain_reason='',candidates=(),assessment_hash='a'*64))
    cycle=DecisionCycle(cfg=cfg,adapter=adapter,ledger=ledger,engine=engine,cost_fn=lambda _:D('.0003'),
        calendar=FX_CALENDAR,events=EventMatrix(),lease_clock=lambda:clock['now'])
    bars=mk_bars([1.1]*70,start=0,step=100)
    result=cycle.step(bars,now_ms=7000,last_quote_ms=7000)
    assert result.decision=='REJECTED:PRESERVATION_BLOCK' and 'FLOW_ADJUSTED_RISK_NOT_QUALIFIED' in result.reason
    event=list(ledger.iter(EventKind.RISK_DECISION))[-1]
    assert event.event_time_ms==event.received_time_ms==10000
    assert event.payload['inputs']['snapshot']['now_unix']==10
    assert event.payload['inputs']['snapshot']['quote_age_ms']==3000
