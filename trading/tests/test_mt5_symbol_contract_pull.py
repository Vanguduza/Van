"""Real signed HTTP and SQL queue; native EA metadata is an explicit fixture."""
from copy import deepcopy
import threading,time
import pytest

from test_mt5_bound_poll import rig
from test_mt5_expected_margin_pull import prepared as margin_prepared
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_pull import format_commands

SUPPORT={'schema':'van.mt5.ea-symbol-constraints/1','required_op':'SYMBOL_CONTRACT',
    'framed_fields':18,'explicit_deadline':True}


def prepared(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=margin_prepared(rig,tmp_path)
    native['symbol_contract_constraints']=SUPPORT;assert poll().status_code==200
    return adapter,queue,poll,clock,native,context,ledger


def observation(fields,native,clock):
    lower=clock['now']//1000*1000
    account={k:native[k] for k in ('login','server','currency','demo','currency_digits')}
    contract={'symbol':fields[2],'currency_base':'EUR','currency_profit':'USD','currency_margin':'EUR',
        'digits':5,'trade_stops_level':5,'trade_freeze_level':0,'trade_mode':4,'trade_calc_mode':0,'spread':8}
    for key,value in {'volume_min':.01,'volume_step':.01,'volume_max':100.,'point':.00001,
            'trade_contract_size':100000.,'trade_tick_size':.00001,'trade_tick_value':1.1,
            'trade_tick_value_profit':1.1,'trade_tick_value_loss':1.3}.items():
        contract[key]=format(value,'.16e')
    return {'schema':'van.mt5.symbol-contract/1','request':{'symbol':fields[2]},
        'account_before':account,'account_after':deepcopy(account),'contract':contract,
        'requested_at_ms':lower,'received_at_ms':lower+999,'deadline_ms':int(fields[17]),
        'native_clock_basis':'UTC_SECOND_INTERVAL','native_numeric_format':'MQL_BINARY64_ROUNDTRIP',
        'tick_value_basis':'NATIVE_SYMBOL_ACCOUNT_CURRENCY_VALUES_NO_SEPARATE_FX_TIMESTAMP',
        'account_snapshot_atomic':False,'risk_terms_qualified':False,'execution_authority':False}


def roundtrip(adapter,queue,poll,clock,native,context,*,damage=None):
    values=[];errors=[]
    def read():
        try:values.append(adapter.symbol_contract('EURUSD',context=context,deadline_ms=clock['now']+5000))
        except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=read);thread.start()
    try:
        until=time.monotonic()+.8;count=0
        while time.monotonic()<until:
            with queue._lock:count=queue._conn.execute("SELECT count(*) FROM commands WHERE op='SYMBOL_CONTRACT'").fetchone()[0]
            if count:break
            time.sleep(.001)
        assert count==1,errors
        response=poll();assert response.status_code==200
        fields=response.text.strip().split('|');assert len(fields)==18 and fields[1]=='SYMBOL_CONTRACT'
        assert fields[17]==str(clock['now']+5000)
        assert bytes.fromhex(fields[14]).decode()==native['server']
        body=observation(fields,native,clock)
        if damage is not None:damage(body)
        assert poll(results=[{'id':int(fields[0]),'observation':body}]).status_code==200
    finally:
        thread.join(2);assert not thread.is_alive(),'owned native-symbol fixture thread was not joined'
    return values,errors


def test_real_signed_http_preserves_original_queue_scope_loss_values_and_unqualified_state(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    try:
        values,errors=roundtrip(adapter,queue,poll,clock,native,context)
        assert not errors and len(values)==1
        body=values[0].body()
        assert body['native_read_identity']['kind']=='EA_PULL_READ' and body['native_read_identity']['queue_id']>0
        assert body['observation']['contract']['trade_tick_value_loss']==format(1.3,'.16e')
        assert body['execution_authority'] is body['risk_terms_qualified'] is body['provider_qualified'] is False
        assert queue.native_entries(adapter.account_alias)==[] and ledger.verify_chain()[0]
    finally:ledger.close()


def test_real_signed_http_result_has_durable_original_query_bound_sql_readback(rig,tmp_path):
    from vati.core import Ledger
    from vati.market_data.mt5_symbol_book import NativeSymbolBook
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path);reopened=None
    try:
        values,errors=roundtrip(adapter,queue,poll,clock,native,context)
        assert not errors and len(values)==1
        receipt=NativeSymbolBook(ledger,clock=lambda:clock['now']).record(values[0])
        clock['now']+=10000;reopened=Ledger(ledger.path)
        original=NativeSymbolBook(reopened,clock=lambda:clock['now']).lookup(receipt['source_ref'])
        assert original['receipt']==receipt and original['observation']==values[0].body()
        assert receipt['source_query_ref']==context.source_query_ref
        assert queue.native_entries(adapter.account_alias)==[]
    finally:
        if reopened is not None:reopened.close()
        ledger.close()


@pytest.mark.parametrize('damage',['identity','units','symbol','clock','authority'])
def test_changed_native_ea_result_cannot_become_valid_symbol_source(rig,tmp_path,damage):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    def corrupt(body):
        if damage=='identity':body['account_after']['login']=999
        elif damage=='units':body['account_before']['currency_digits']=8
        elif damage=='symbol':body['contract']['symbol']='GBPUSD'
        elif damage=='clock':body['received_at_ms']=body['deadline_ms']
        elif damage=='authority':body['risk_terms_qualified']=True
    try:
        values,errors=roundtrip(adapter,queue,poll,clock,native,context,damage=corrupt)
        assert not values and len(errors)==1 and isinstance(errors[0],VenueUnavailable)
        assert queue.native_entries(adapter.account_alias)==[]
    finally:ledger.close()


def test_legacy_ea_capability_and_queued_expiry_refuse_before_native_handoff(rig,tmp_path):
    adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path)
    try:
        native.pop('symbol_contract_constraints');assert poll().status_code==200
        with pytest.raises(VenueUnavailable):adapter.symbol_contract('EURUSD',context=context,deadline_ms=clock['now']+5000)
        assert queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0
        cid=queue.enqueue(adapter.account_alias,'SYMBOL_CONTRACT',{'symbol':'EURUSD',
            'expected_account':adapter.identity.as_dict(),'expires_at_ms':clock['now']+1000},now_ms=clock['now'])
        clock['now']+=1000;response=poll();assert response.status_code==200 and not response.text.strip()
        result=queue.result(cid)
        assert result['status']=='REJECTED' and 'deadline' in result['reason']
        assert queue.native_entries(adapter.account_alias)==[]
    finally:ledger.close()
