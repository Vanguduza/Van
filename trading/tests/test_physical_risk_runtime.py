"""Native risk projections consume committed tails and retain recovery scopes."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW, intent
from test_native_risk_history_inputs import native_facts, record
from test_native_risk_history_index import other_context
from test_physical_financial_history import approval, close
from test_physical_baselines import legacy
from test_physical_control_history import original_control
from vati.core import EventKind, make_event
from vati.core.ledger import LedgerError
from vati.risk.lockouts import LockoutPolicy, ACCOUNT_SCOPE
from vati.risk.physical_runtime import PhysicalRiskRuntime


def runtime(ledger,facts):
    return PhysicalRiskRuntime(ledger,facts.native_account_context,LockoutPolicy(5),now_ms=NOW*1000)


def observe(state,facts,trade):
    ref,p=state.observe(facts.native_account_context,now_ms=NOW*1000,producer='vati-cycle')
    assert ref and not p.issue
    event=record(state.ledger,replace(facts,peak_equity=p.peak,day_start_equity=p.day,
        week_start_equity=p.week,native_risk_basis_ref=ref),
        request=intent(trade_intent_id=trade,account_alias=facts.account_alias))
    return ref,event


def test_incremental_shared_decisions_never_full_rebuild_the_history_each_tick(tmp_path,eurusd,monkeypatch):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'old-a','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    state=runtime(ledger,b)
    def forbidden(*args,**kwargs):
        pytest.fail('an ordinary decision tick must not rehash/reload full history')
    monkeypatch.setattr(state,'_reload',forbidden)
    monkeypatch.setattr(ledger,'verify_chain',forbidden)
    for k in range(12):
        _,event=observe(state,b,'b-'+str(k))
        p=state.refresh(b.native_account_context,now_ms=NOW*1000)
        assert p.peak==D('15000') and not p.issue
        assert state.book.origins[b.account_alias].peak == b.equity
    assert ledger.count(EventKind.ORDER_COMMAND)==0


def test_new_close_rebuilds_original_all_alias_loss_attribution_once(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    first=approval(ledger,a,'old-a');close(ledger,first,alias=a.account_alias)
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    state=runtime(ledger,b)
    assert state.streaks._scopes[ACCOUNT_SCOPE].losses==1
    _,event=observe(state,b,'new-b')
    close(ledger,event,alias=b.account_alias)
    state.refresh(b.native_account_context,now_ms=NOW*1000)
    assert state.streaks._scopes[ACCOUNT_SCOPE].losses==2
    original_control(ledger,a.native_account_context)
    state.refresh(b.native_account_context,now_ms=NOW*1000)
    assert state.streaks._scopes[ACCOUNT_SCOPE].losses==1
    assert state.streaks.original_contributors(ACCOUNT_SCOPE)==(b.account_alias,)


def test_new_control_rebuild_does_not_resurrect_shared_peak(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'a','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    legacy(ledger,b,'b','13000')
    state=runtime(ledger,b);observe(state,b,'shared-b')
    original_control(ledger,a.native_account_context,action='resume_drawdown')
    assert state.refresh(b.native_account_context,now_ms=NOW*1000).peak==D('13000')
    observe(state,b,'shared-b-again')
    original_control(ledger,b.native_account_context,action='resume_drawdown')
    assert state.refresh(b.native_account_context,now_ms=NOW*1000).peak==b.equity
    observe(state,b,'after-all-resets')
    assert runtime(ledger,b).book.projection(NOW*1000).peak==b.equity


def test_original_basis_writer_compare_and_swap_rejects_changed_head(tmp_path,eurusd,monkeypatch):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    state=runtime(ledger,facts)
    original=state.book.observation_event
    def competing(*args,**kwargs):
        event=original(*args,**kwargs)
        ledger.append(make_event(EventKind.SESSION,'vati-cycle',{'diagnostic':'competing-writer'},
            event_time_ms=NOW*1000,received_time_ms=NOW*1000))
        return event
    monkeypatch.setattr(state.book,'observation_event',competing)
    with pytest.raises(LedgerError,match='changed before append'):
        state.observe(facts.native_account_context,now_ms=NOW*1000,producer='vati-cycle')
    assert not [e for e in ledger.iter(EventKind.SESSION) if e.payload.get('event')=='NATIVE_RISK_BASIS']


def test_incremental_unbound_rejection_does_not_poison_native_recovery(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    state=runtime(ledger,facts)
    bad=record(ledger,replace(facts,native_account_context=None,preservation_blocks_new_risk=True,
        preservation_reason='FUNDING_RISK_UNAVAILABLE:SOURCE'))
    assert bad.payload['decision']['decision']=='REJECTED'
    assert not state.refresh(facts.native_account_context,now_ms=NOW*1000).issue
    observe(state,facts,'recovered')


def test_incremental_corrupted_original_input_remains_explicitly_unresolved(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    state=runtime(ledger,facts)
    bad=record(ledger,facts,damage=lambda p:p['decision'].update(approved_size='9999'))
    p=state.refresh(facts.native_account_context,now_ms=NOW*1000)
    assert bad.hash in p.unresolved_refs and p.issue
    ref,p=state.observe(facts.native_account_context,now_ms=NOW*1000,producer='vati-cycle')
    assert ref is None and p.issue


def test_ledger_tail_rejects_invalid_cursor_and_retains_original_order(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    rows=list(ledger.iter_after(0))
    assert [e.body() for _,e in rows]==[e.body() for e in ledger.iter()]
    assert list(ledger.iter_after(rows[-1][0]))==[]
    for bad in (True,-1,'0',0.0):
        with pytest.raises(ValueError):list(ledger.iter_after(bad))
