"""Original selected-candidate validity must survive route/native preparation."""
from dataclasses import replace
from types import SimpleNamespace as N
from decimal import Decimal
import pytest
from conftest import NOW
from test_router_native_entry_deadline import flow
from test_account_coordinator import cand
from vati.app.account_service import AccountCoordinatorService
from vati.accounts import BrokerKind
from vati.core import EventKind
from vati.execution.policy import ExecutionPolicyEngine
from vati.execution.policy_templates import MARKET_WITH_SLIPPAGE_CAP
from vati.execution.router import RouterError


def execute_selected(tmp_path,eurusd,phase,*,ttl=50,window_patch=None,max_quote_age=100):
    sdk,worker,a,clock,m,trade,approved,ledger,router=flow(tmp_path,eurusd)
    started=clock['ms']
    candidate=replace(cand('original-selected','EURUSD',gen=started,ttl=ttl),
        account_alias=trade.account_alias,venue=trade.venue,strategy_id=trade.strategy_id,
        strategy_version=trade.strategy_version,entry=trade.entry,stop=trade.stop,
        direction=trade.direction,entry_type='MARKET',candidate_hash='').sealed()
    if window_patch:
        candidate=replace(candidate,**window_patch,candidate_hash='').sealed()
    state=N(session=N(value='LONDON'),regime=N(vol=N(value='NORMAL')),
        event_window=N(value='QUIET'),features=N(close=trade.entry),quote_age_ms=0,as_of_ms=started)
    refreshes=[];recorded=[]
    def route(**kwargs):
        refreshes.append(kwargs)
        if phase=='route_refresh':clock['ms']=started+51
    service=AccountCoordinatorService.__new__(AccountCoordinatorService)
    service.router=router;service.account=N(alias=trade.account_alias,broker=BrokerKind.MT5)
    service.mandate=m;service.evaluators={'EURUSD':N(last_state=state)}
    service.policy=ExecutionPolicyEngine(default_template_id=MARKET_WITH_SLIPPAGE_CAP);service.clock=lambda:clock['ms']
    service.routes=N(refresh=route);service.contracts={'EURUSD':eurusd}
    service.specs={'EURUSD':N(time_in_force='GTC',round_trip_cost_pct=Decimal('0'))}
    service.cfg=N(max_quote_age_ms=max_quote_age);service.lifecycle=N(record_entry=lambda **kw:recorded.append(kw))
    native=sdk.symbol_info_tick;quotes=[]
    def quote(symbol):
        result=native(symbol);quotes.append(symbol)
        if phase in {'native_quote','native_quote_after_quote','native_quote_after_mandate'} and len(quotes)==2:
            clock['ms']=started+{'native_quote':51,'native_quote_after_quote':101,'native_quote_after_mandate':1000}[phase]
        return result
    sdk.symbol_info_tick=quote
    try:
        receipt=service._execute(candidate,trade,approved,(),None)
        status=receipt.status
    except RouterError as exc:
        status='REJECTED:'+str(exc)
    return status,sdk,ledger,candidate,refreshes,quotes


def test_current_original_setup_still_reaches_the_native_sdk_once(tmp_path,eurusd):
    status,sdk,ledger,candidate,refreshes,quotes=execute_selected(tmp_path,eurusd,'current')
    assert status=='FILLED' and len(sdk.sent)==1 and len(quotes)>=2
    assert len(refreshes)==1 and refreshes[0]['source']=='pre_order_refresh'

@pytest.mark.parametrize('phase',['route_refresh','native_quote'])
def test_original_setup_expiry_is_not_renewed_by_current_quotes_or_route_preparation(tmp_path,eurusd,phase):
    status,sdk,ledger,candidate,refreshes,quotes=execute_selected(tmp_path,eurusd,phase)
    assert status.startswith('REJECTED') and sdk.sent==[], 'an expired selected setup reached the actual native entry'
    if phase=='native_quote':assert len(quotes)>=2


def test_actual_selected_setup_bound_is_sealed_into_the_native_command(tmp_path,eurusd):
    status,sdk,ledger,candidate,refreshes,quotes=execute_selected(tmp_path,eurusd,'current')
    command=next(ledger.iter(EventKind.ORDER_COMMAND))
    assert status=='FILLED' and len(sdk.sent)==1
    assert command.payload['expires_at_ms']==candidate.valid_until_ms


@pytest.mark.parametrize('ttl,quote_age,expected_delta',[(5000,100,101),(5000,5000,1000)])
def test_selected_setup_never_extends_original_quote_or_mandate(tmp_path,eurusd,ttl,quote_age,expected_delta):
    status,sdk,ledger,candidate,refreshes,quotes=execute_selected(tmp_path,eurusd,'current',ttl=ttl,max_quote_age=quote_age)
    assert status=='FILLED' and len(sdk.sent)==1
    command=next(ledger.iter(EventKind.ORDER_COMMAND))
    assert command.payload['expires_at_ms']==candidate.valid_from_ms+expected_delta


@pytest.mark.parametrize('bad',[None,True,False,'1800000000050',-1,0,2**63])
def test_unknown_or_malformed_selected_setup_time_never_reaches_native_entry(tmp_path,eurusd,bad):
    status,sdk,ledger,candidate,refreshes,quotes=execute_selected(tmp_path,eurusd,'current',window_patch={'valid_until_ms':bad})
    assert status.startswith('REJECTED') and sdk.sent==[]
    assert ledger.count(EventKind.ORDER_COMMAND)==0


@pytest.mark.parametrize('start',[None,True,False,-1,'1800000000000',NOW*1000+1,NOW*1000+50])
def test_unqualified_or_future_original_setup_window_cannot_dispatch(tmp_path,eurusd,start):
    status,sdk,ledger,candidate,refreshes,quotes=execute_selected(tmp_path,eurusd,'current',window_patch={'valid_from_ms':start})
    assert status.startswith('REJECTED') and sdk.sent==[]
    assert ledger.count(EventKind.ORDER_COMMAND)==0 and refreshes==[]


@pytest.mark.parametrize('phase,quote_age',[('native_quote_after_quote',100),('native_quote_after_mandate',5000)])
def test_longer_setup_cannot_authorize_an_entry_after_the_original_quote_or_grant(tmp_path,eurusd,phase,quote_age):
    status,sdk,ledger,candidate,refreshes,quotes=execute_selected(tmp_path,eurusd,phase,ttl=5000,max_quote_age=quote_age)
    assert status.startswith('REJECTED') and sdk.sent==[] and len(quotes)>=2
