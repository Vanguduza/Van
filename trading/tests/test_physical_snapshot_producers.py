"""Both real native snapshot producers share original risk before first entry."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as N

import pytest

from conftest import NOW, mandate_dict, intent
from test_native_risk_history_inputs import native_facts, record
from test_native_risk_history_index import other_context
from test_physical_financial_history import approval, close
from test_physical_baselines import legacy
from test_physical_native_controls import cycle
from vati.core import EventKind
from vati.execution.base import Health
from vati.risk import TradingMandate
from vati.risk.contracts import MarketIntegrityState
from vati.risk.lockouts import LossStreakGovernor, LockoutPolicy


def producer(kind,ledger,adapter,account,facts):
    if kind=='single':
        return cycle(ledger,adapter,account,facts)
    from vati.app.account_service import AccountCoordinatorService
    service=AccountCoordinatorService.__new__(AccountCoordinatorService)
    service.adapter=adapter;service.account=N();service._ledger=ledger
    adapter.sync_account=lambda:account
    adapter.heartbeat=lambda **_:Health(True,0,NOW*1000)
    adapter.positions=lambda:[]
    service.clock=lambda:NOW*1000;service.contracts={'EURUSD':facts.symbol_contract}
    service.peak_equity=service.day_start_equity=service.week_start_equity=D('0')
    service._entries={};service.cfg=N(account_alias=facts.account_alias,max_quote_age_ms=5000)
    service._ledger_positions=lambda:[];service._risk_store_ok=lambda:True
    service._open_positions=lambda:();service._drawdown_top_state=lambda:None
    service.lifecycle=N(streaks=LossStreakGovernor(LockoutPolicy(5)),
        preservation_blocks_new_risk=False,preservation_reason='',consecutive_losses=0)
    service.mandate=TradingMandate.from_mapping(mandate_dict(account_alias=facts.account_alias,venue=adapter.venue))
    service.consecutive_losses=0;service.kill=N(active=[])
    service.evaluators={'EURUSD':N(last_state=N(as_of_ms=NOW*1000,quote_age_ms=17,
        event_window=None,integrity=MarketIntegrityState.NORMAL))}
    return service


def capture(service,kind):
    if kind=='single':return service.snapshot(now_ms=NOW*1000,quote_age_ms=17,strategy_id=intent().strategy_id)
    return service._snapshot_for(N(symbol='EURUSD',strategy_id=intent().strategy_id))


@pytest.mark.parametrize('kind',['single','account'])
def test_actual_native_producer_reads_other_alias_peak_and_loss_before_its_first_decision(tmp_path,eurusd,kind):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    first=approval(ledger,a,'original-loss');close(ledger,first,alias=a.account_alias)
    legacy(ledger,a,'old-peak','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    current=replace(account,account_alias=b.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=b.account_alias))
    service=producer(kind,ledger,adapter,current,b)
    result=capture(service,kind)
    assert not result.preservation_blocks_new_risk, result.preservation_reason
    assert result.peak_equity==D('15000') and result.consecutive_losses==1
    assert result.native_risk_basis_ref
    own=next(e for e in ledger.iter(EventKind.SESSION) if e.hash==result.native_risk_basis_ref)
    assert own.payload['account_alias']==b.account_alias
    assert D(own.payload['peak_equity'])==current.equity
    record(ledger,result,request=intent(trade_intent_id='first-b',account_alias=b.account_alias))
    again=capture(service,kind)
    assert again.peak_equity==result.peak_equity and again.consecutive_losses==1
    assert not again.preservation_blocks_new_risk
    assert ledger.count(EventKind.ORDER_COMMAND)==0


@pytest.mark.parametrize('kind',['single','account'])
def test_native_projection_read_failure_holds_entries_and_does_not_replace_known_baselines(tmp_path,eurusd,kind,monkeypatch):
    from vati.risk import physical_runtime
    ledger,adapter,account,_,facts=native_facts(tmp_path,eurusd)
    service=producer(kind,ledger,adapter,account,facts)
    service.peak_equity=service.day_start_equity=service.week_start_equity=D('12345')
    def unavailable(*args,**kwargs):raise OSError('private provider detail')
    monkeypatch.setattr(physical_runtime.PhysicalRiskRuntime,'observe',unavailable)
    result=capture(service,kind)
    assert result.preservation_blocks_new_risk
    assert result.preservation_reason=='NATIVE_PHYSICAL_RISK_UNAVAILABLE:OSError'
    assert result.peak_equity==result.day_start_equity==result.week_start_equity==D('12345')
    assert result.native_risk_basis_ref is None


@pytest.mark.parametrize('kind',['single','account'])
@pytest.mark.parametrize('failure',['read','lost_commit_reply'])
def test_held_shared_snapshot_never_becomes_an_own_peak_during_recovery(tmp_path,eurusd,kind,failure,monkeypatch):
    from contextlib import contextmanager
    from test_physical_control_history import original_control
    from vati.risk.physical_runtime import PhysicalRiskRuntime
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'original-a-peak','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    current=replace(account,account_alias=b.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=b.account_alias))
    service=producer(kind,ledger,adapter,current,b)
    first=capture(service,kind)
    assert first.peak_equity==D('15000') and first.native_risk_basis_ref
    record(ledger,first,request=intent(trade_intent_id='b-original-shared',account_alias=b.account_alias))
    before=ledger.count(EventKind.SESSION)
    with monkeypatch.context() as patch:
        if failure=='read':
            def unavailable(*args,**kwargs):raise OSError('isolated read unavailable')
            patch.setattr(PhysicalRiskRuntime,'observe',unavailable)
        else:
            state=service._physical_risk_runtime;plan=state.book.observation_event;atomic=ledger.atomic
            writer={'armed':False,'depth':0}
            def planned(*args,**kwargs):
                result=plan(*args,**kwargs);writer['armed']=True;return result
            @contextmanager
            def lost_reply():
                outer=writer['depth']==0;writer['depth']+=1
                try:
                    with atomic():yield
                finally:writer['depth']-=1
                if outer and writer['armed']:
                    writer['armed']=False
                    raise OSError('isolated basis commit acknowledgement lost')
            patch.setattr(state.book,'observation_event',planned)
            patch.setattr(ledger,'atomic',lost_reply)
        held=capture(service,kind)
        assert held.preservation_blocks_new_risk and held.native_risk_basis_ref is None
        assert held.peak_equity==D('15000')
    assert ledger.count(EventKind.SESSION)==before+(failure=='lost_commit_reply')
    record(ledger,held,request=intent(trade_intent_id='b-held-shared',account_alias=b.account_alias))
    original_control(ledger,a.native_account_context,action='resume_drawdown')
    recovered=capture(service,kind)
    assert not recovered.preservation_blocks_new_risk,recovered.preservation_reason
    assert recovered.peak_equity==current.equity
    assert service._physical_risk_runtime.book.origins[b.account_alias].peak==current.equity


@pytest.mark.parametrize('kind',['single','account'])
def test_held_projection_keeps_its_verified_native_equity_sample_without_borrowing_the_displayed_peak(tmp_path,eurusd,kind,monkeypatch):
    from test_physical_control_history import original_control
    from vati.risk.physical_runtime import PhysicalRiskRuntime
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'original-a-high','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    current=replace(account,account_alias=b.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=b.account_alias))
    service=producer(kind,ledger,adapter,current,b)
    first=capture(service,kind)
    record(ledger,first,request=intent(trade_intent_id='b-first',account_alias=b.account_alias))
    high=replace(current,equity=D('12000'),funding_mark=replace(current.funding_mark,
        reported_equity=D('12000')+current.funding_mark.credit,source_nonce='isolated-high-equity'))
    with monkeypatch.context() as patch:
        patch.setattr(adapter,'sync_account',lambda:high)
        def unavailable(*args,**kwargs):raise OSError('isolated projection read unavailable')
        patch.setattr(PhysicalRiskRuntime,'observe',unavailable)
        held=capture(service,kind)
    assert held.equity==D('12000') and held.peak_equity==D('15000')
    assert held.preservation_blocks_new_risk and held.native_risk_basis_ref is None
    record(ledger,held,request=intent(trade_intent_id='b-observed-high',account_alias=b.account_alias))
    original_control(ledger,a.native_account_context,action='resume_drawdown')
    recovered=capture(service,kind)
    assert not recovered.preservation_blocks_new_risk,recovered.preservation_reason
    assert recovered.equity==D('10000') and recovered.peak_equity==D('12000')
