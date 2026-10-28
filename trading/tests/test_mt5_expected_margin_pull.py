"""Real signed HTTP/queue read path; EA calculations are explicit source fixtures.

Native MetaEditor compilation and terminal/runtime acceptance are separate.
"""
from copy import deepcopy
from decimal import Decimal as D
import threading
import time

import pytest

from test_mt5_bound_poll import rig
from test_mt5_funding_contract import account as native_account
from vati.core import Ledger
from vati.core.units import Money
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_pull import format_commands
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.contracts import Direction

SUPPORT={'schema':'van.mt5.ea-margin-constraints/1','required_op':'MARGIN_QUOTE',
    'framed_fields':18,'explicit_deadline':True}


def prepared(rig,tmp_path,*,ledger=None):
    reg,profile,queue,provider,adapter,command,poll,clock,native=rig
    raw=native_account();raw['server']=profile.server;raw['funding']['binding_before']['server']=profile.server
    native.update(raw,trade_allowed=True,hedging=True,leverage=30,margin_mode=2,expected_margin_constraints=SUPPORT)
    assert poll().status_code==200
    ledger=ledger or Ledger(tmp_path/'original-native.sqlite');acct=adapter.sync_account()
    captured=capture_cached_mt5(ledger,acct,now_ms=clock['now'])
    context=context_for_account(ledger,adapter,acct,now_ms=clock['now'],mt5_capture=captured)
    adapter.timeout_s=1;adapter.poll_s=.001
    return adapter,queue,poll,clock,native,context,ledger


def observation(fields,native,clock):
    # Matches the declared native MQL binary64/text + UTC-second protocol.
    # This is not a claim that the real OrderCalcMargin ran in this fixture.
    lower=clock['now']//1000*1000
    account={k:native[k] for k in ('login','server','currency','demo','currency_digits',
        'leverage','margin_mode','hedging','equity','balance','credit')}
    return {'schema':'van.mt5.expected-margin/1','state':'OBSERVED',
        'request':{'symbol':fields[2],'type':fields[3],'volume':fields[4],'price':fields[5]},
        'account_before':account,'account_after':deepcopy(account),
        'contract':{'symbol':fields[2],'volume_min':format(.01,'.16e'),
            'volume_step':format(.01,'.16e'),'volume_max':format(100.,'.16e'),
            'trade_tick_size':format(.00001,'.16e'),'native_numeric_format':'MQL_BINARY64_ROUNDTRIP'},
        'raw_margin':format(33.25,'.16e'),'currency_digits':2,'requested_at_ms':lower,
        'received_at_ms':lower+999,'deadline_ms':int(fields[17]),'native_clock_basis':'UTC_SECOND_INTERVAL',
        'valuation_basis':'ISOLATED_ORDER_AT_REQUEST_PRICE_EXCLUDES_EXISTING_POSITIONS_AND_PENDING_ORDERS',
        'account_snapshot_atomic':False,'reservation_qualified':False,'execution_authority':False}


def roundtrip(adapter,queue,poll,clock,native,context,*,damage=None):
    values=[];errors=[]
    def read():
        try:values.append(adapter.expected_margin('EURUSD',D('.10'),price=D('1.10000'),
            direction=Direction.LONG,context=context,deadline_ms=clock['now']+5000))
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=read);thread.start()
    try:
        until=time.monotonic()+.8
        while time.monotonic()<until:
            with queue._lock:count=queue._conn.execute("SELECT count(*) FROM commands WHERE op='MARGIN_QUOTE'").fetchone()[0]
            if count:break
            time.sleep(.001)
        assert count==1,errors
        response=poll();assert response.status_code==200
        fields=response.text.strip().split('|')
        assert len(fields)==18 and fields[1]=='MARGIN_QUOTE' and fields[17]==str(clock['now']+5000)
        assert bytes.fromhex(fields[14]).decode()==native['server']
        raw=observation(fields,native,clock)
        if damage is not None:damage(raw)
        assert poll(results=[{'id':int(fields[0]),'observation':raw}]).status_code==200
    finally:
        thread.join(2);assert not thread.is_alive(),'owned native-read fixture thread was not joined'
    return values,errors


def test_real_signed_http_queue_retains_original_read_identity_and_native_decimal_metadata(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    values,errors=roundtrip(adapter,queue,poll,clock,native,context)
    assert not errors and len(values)==1
    body=values[0].body();assert body['native_read_identity']['kind']=='EA_PULL_READ'
    assert body['native_read_identity']['queue_id']>0
    assert Money.from_body(body['estimate_money']).decimal==D('33.25')
    assert body['observation']['contract']['volume_step']==format(.01,'.16e')
    assert body['observation']['native_clock_basis']=='UTC_SECOND_INTERVAL'
    assert body['request']['volume']=='0.10' and body['request']['price']=='1.10000'
    assert body['execution_authority'] is body['reservation_qualified'] is False
    assert queue.native_entries(adapter.account_alias)==[]
    assert ledger.verify_chain()[0]


@pytest.mark.parametrize('change',['identity','contract','deadline','clock_basis','authority'])
def test_foreign_stale_or_changed_ea_data_never_supplies_an_estimate(rig,tmp_path,change):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    def damage(raw):
        if change=='identity':raw['account_after']['currency']='EUR'
        elif change=='contract':raw['contract']['volume_step']='0.03'
        elif change=='deadline':raw['deadline_ms']+=1
        elif change=='clock_basis':raw['native_clock_basis']='UNKNOWN'
        elif change=='authority':raw['execution_authority']=True
    values,errors=roundtrip(adapter,queue,poll,clock,native,context,damage=damage)
    assert values==[] and len(errors)==1 and isinstance(errors[0],VenueUnavailable)
    assert queue.native_entries(adapter.account_alias)==[]


@pytest.mark.parametrize('support',[None,{},dict(SUPPORT,explicit_deadline=1),dict(SUPPORT,framed_fields=18.)])
def test_legacy_or_untyped_ea_capability_refuses_before_native_query(rig,tmp_path,support):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    native['expected_margin_constraints']=support;assert poll().status_code==200
    with pytest.raises(VenueUnavailable):adapter.expected_margin('EURUSD',D('.10'),price=D('1.1'),
        direction=Direction.LONG,context=context,deadline_ms=clock['now']+5000)
    assert queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0


def test_expired_read_is_not_handed_to_native_ea_or_classified_as_an_entry(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    identity=adapter.identity.as_dict()
    cid=queue.enqueue(adapter.account_alias,'MARGIN_QUOTE',{'symbol':'EURUSD','type':'BUY','volume':'.1','price':'1.1',
        'expected_account':identity,'expires_at_ms':clock['now']},now_ms=clock['now'])
    assert poll().text==''
    assert queue.result(cid)['status']=='REJECTED' and queue.native_entries(adapter.account_alias)==[]


def test_margin_frame_cannot_drop_original_identity_or_deadline():
    with pytest.raises(VenueUnavailable):format_commands([{'id':1,'op':'MARGIN_QUOTE','symbol':'EURUSD'}])
