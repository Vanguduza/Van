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
