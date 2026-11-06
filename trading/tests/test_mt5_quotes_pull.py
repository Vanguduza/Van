"""Signed EA HTTP/queue and original quote readback over explicit tick fixtures."""
from copy import deepcopy
import threading,time
import pytest

from test_mt5_bound_poll import rig
from test_mt5_symbol_contract_pull import prepared as symbols_prepared,observation as symbol_observation
from vati.execution.base import VenueUnavailable
from vati.market_data.mt5_quote_book import NativeQuoteBook
from vati.execution.mt5_quotes import Mt5QuoteObservation
from vati.core import Ledger

SUPPORT={'schema':'van.mt5.ea-quote-constraints/1','required_op':'QUOTE_SNAPSHOT',
    'framed_fields':18,'explicit_deadline':True}


def prepared(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=symbols_prepared(rig,tmp_path)
    native['quote_snapshot_constraints']=SUPPORT;assert poll().status_code==200
    return adapter,queue,poll,clock,native,context,ledger


def observation(fields,native,clock):
    original=symbol_observation(fields,native,clock)
    at=clock['now']-10
    return {'schema':'van.mt5.quote-snapshot/1','request':original['request'],
        'account_before':original['account_before'],'account_after':original['account_after'],
        'contract_before':original['contract'],'contract_after':deepcopy(original['contract']),
        'tick':{'bid':format(1.1,'.16e'),'ask':format(1.10008,'.16e'),'last':'0',
            'volume_real':'0','volume':'9007199254740993','flags':'6','time':str(at//1000),'time_msc':str(at)},
        'symbol_selected':True,'subscription_delayed':False,
        'requested_at_ms':original['requested_at_ms'],'received_at_ms':original['received_at_ms'],
        'deadline_ms':original['deadline_ms'],'native_clock_basis':'UTC_SECOND_INTERVAL',
        'native_numeric_format':'MQL_BINARY64_ROUNDTRIP',
        'tick_time_basis':'BROKER_UTC_LATEST_FULL_TICK_SNAPSHOT_NOT_INDIVIDUAL_SIDE_TIMES',
        'volume_basis':'NATIVE_LAST_TRADE_VOLUME_NOT_LOTS_OR_GENUINE_DEPTH',
        'account_snapshot_atomic':False,'risk_terms_qualified':False,'execution_authority':False}


def roundtrip(adapter,queue,poll,clock,native,context,*,damage=None):
    values=[];errors=[]
    def read():
        try:values.append(adapter.quote_snapshot('EURUSD',context=context,deadline_ms=clock['now']+5000))
        except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=read);thread.start()
    try:
        until=time.monotonic()+.8;count=0
        while time.monotonic()<until:
            with queue._lock:count=queue._conn.execute("SELECT count(*) FROM commands WHERE op='QUOTE_SNAPSHOT'").fetchone()[0]
            if count:break
            time.sleep(.001)
        assert count==1,errors
        response=poll();assert response.status_code==200
        f=response.text.strip().split('|');assert len(f)==18 and f[1]=='QUOTE_SNAPSHOT'
        assert f[17]==str(clock['now']+5000) and bytes.fromhex(f[14]).decode()==native['server']
        raw=observation(f,native,clock)
        if damage is not None:damage(raw)
        assert poll(results=[{'id':int(f[0]),'observation':raw}]).status_code==200
    finally:
        thread.join(2);assert not thread.is_alive(),'owned native quote-read thread was not joined'
    return values,errors


def test_real_signed_quote_has_original_tick_time_volume_and_causal_sql_readback(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path);reopened=None
    try:
        values,errors=roundtrip(adapter,queue,poll,clock,native,context)
        assert not errors and len(values)==1
        q=values[0];body=q.body();view=q.snapshot(now_ms=clock['now'],max_age_ms=5000)
        assert view['state']=='OBSERVED_UNQUALIFIED' and view['age_ms']==10
        assert body['observation']['tick']['volume']=='9007199254740993'
        receipt=NativeQuoteBook(ledger,clock=lambda:clock['now']).record(q)
        clock['now']+=10000;reopened=Ledger(ledger.path)
        stored=NativeQuoteBook(reopened,clock=lambda:clock['now']).lookup(receipt['source_ref'])
        assert stored['receipt']==receipt and stored['observation']==body
        assert Mt5QuoteObservation.from_body(stored['observation']).snapshot(now_ms=clock['now'],max_age_ms=5000)['state']=='STALE_NATIVE_QUOTE'
        assert queue.native_entries(adapter.account_alias)==[] and ledger.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        ledger.close()


@pytest.mark.parametrize('damage',['identity','symbol','clock','units','depth','grant'])
def test_changed_ea_quote_source_is_not_valid_native_data(rig,tmp_path,damage):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    def corrupt(raw):
        if damage=='identity':raw['account_after']['login']=999
        elif damage=='symbol':raw['contract_after']['symbol']='GBPUSD'
        elif damage=='clock':raw['received_at_ms']=raw['deadline_ms']
        elif damage=='units':raw['contract_after']['currency_profit']='JPY'
        elif damage=='depth':raw['volume_basis']='GENUINE_DEPTH'
        elif damage=='grant':raw['execution_authority']=True
    try:
        values,errors=roundtrip(adapter,queue,poll,clock,native,context,damage=corrupt)
        assert not values and len(errors)==1 and isinstance(errors[0],VenueUnavailable)
        assert queue.native_entries(adapter.account_alias)==[]
    finally:ledger.close()


def test_legacy_quote_capability_and_expired_queue_do_not_reach_the_native_read(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    try:
        native.pop('quote_snapshot_constraints');assert poll().status_code==200
        with pytest.raises(VenueUnavailable):adapter.quote_snapshot('EURUSD',context=context,deadline_ms=clock['now']+5000)
        assert queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0
        cid=queue.enqueue(adapter.account_alias,'QUOTE_SNAPSHOT',{'symbol':'EURUSD',
            'expected_account':adapter.identity.as_dict(),'expires_at_ms':clock['now']+1000},now_ms=clock['now'])
        clock['now']+=1000;result=poll();assert result.status_code==200 and not result.text.strip()
        assert queue.result(cid)['status']=='REJECTED' and queue.native_entries(adapter.account_alias)==[]
    finally:ledger.close()
