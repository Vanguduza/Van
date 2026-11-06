"""Actual original statement journals and fixed deletion-boundary reads."""
import base64
import json
from dataclasses import replace

import pytest
from vati.core import Ledger,EventKind,make_event
from vati.core.ledger import LedgerError
from vati.funding.journal import FundingBook
from vati.funding.retained_history import read_history,RetainedHistoryError
from trading.tests.test_funding_journal import statement
from trading.tests.test_native_balance_reconciliation import mark
from trading.tests.test_funding_owner_reports import snapshot,profile


def original(tmp_path,count=205):
    ledger=Ledger(tmp_path/'original.sqlite')
    raw=statement()
    raw=replace(raw,movements=tuple(replace(raw.movements[0],native_id=i) for i in range(count,0,-1)))
    receipt=FundingBook(ledger,clock=lambda:5000).record_statement(raw)
    observation={'state':'OBSERVED','scope_hash':raw.scope_hash,'native_mark':mark(3000).body(),'statement':receipt}
    snap=snapshot(ledger,funding_observation=observation)
    cutoff=make_event(EventKind.SESSION,'test',{'event':'ORIGINAL_DELETION_BOUNDARY'},event_time_ms=1,received_time_ms=1)
    ledger.append(cutoff)
    row={'alias':'ctrader_primary','operation_id':'original_deletion_00000001','incarnation':'a'*64,'account_control_domain':'b'*64}
    args={'lifecycle':row,'plan_ref':'c'*64,'profile':profile(server=''),'cutoff_ref':cutoff.hash}
    return ledger,raw,snap,args


def test_pages_restart_and_later_same_physical_account_never_advance_original_prefix(tmp_path):
    ledger,raw,snap,args=original(tmp_path)
    first=read_history(ledger,**args,limit=100)
    assert [r['movement']['native_id'] for r in first['movements']]==list(range(1,101))
    assert first['movement_count']==205 and first['truncated']
    assert first['attribution']=='ORIGINAL_PHYSICAL_ACCOUNT_PRE_DELETION'
    assert first['generation_provenance']=='UNKNOWN' and first['execution_authority'] is False
    changed=replace(raw,movements=(replace(raw.movements[0],native_id=999),),observed_at_ms=6000)
    receipt=FundingBook(ledger,clock=lambda:6000).record_statement(changed)
    snapshot(ledger,funding_observation={'scope_hash':raw.scope_hash,'native_mark':mark(6000).body(),'statement':receipt})
    assert read_history(ledger,**args,limit=100)==first
    ledger.close();ledger=Ledger(tmp_path/'original.sqlite')
    second=read_history(ledger,**args,limit=100,cursor=first['next_cursor'])
    third=read_history(ledger,**args,limit=100,cursor=second['next_cursor'])
    assert [r['movement']['native_id'] for r in second['movements']]==list(range(101,201))
    assert [r['movement']['native_id'] for r in third['movements']]==list(range(201,206))
    assert third['next_cursor'] is None and not third['truncated']
    assert first['snapshot_ref']==snap.hash and '999' not in [str(r['movement']['native_id']) for r in second['movements']]
    assert ledger.verify_chain()[0]
    ledger.close()


@pytest.mark.parametrize('field',['view','alias','lifecycle_id','incarnation','account_control_domain','original_plan_ref','cutoff_ref','scope_hash','snapshot_ref','query_ref','statement_ref','source_observed_at_ms','limit','offset'])
def test_every_cursor_binding_is_checked_against_actual_original_source(tmp_path,field):
    ledger,_,_,args=original(tmp_path)
    first=read_history(ledger,**args,limit=2)
    decoded=json.loads(base64.urlsafe_b64decode(first['next_cursor']))
    decoded[field]=-1 if field in {'offset','limit','source_observed_at_ms'} else 'substituted'
    cursor=base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()
    with pytest.raises(RetainedHistoryError):read_history(ledger,**args,limit=2,cursor=cursor)
    ledger.close()


@pytest.mark.parametrize('change',[{'login':'different'},{'currency':'USD'},{'broker':'MT5'},{'demo':False}])
def test_no_alias_or_profile_metadata_backfill_without_original_native_identity(tmp_path,change):
    ledger,_,_,args=original(tmp_path)
    args['profile']=args['profile']|change
    result=read_history(ledger,**args)
    assert result['state']=='UNOBSERVED' and result['movements']==[]
    assert result['reason']=='ORIGINAL_PRE_DELETION_NATIVE_SOURCE_UNOBSERVED'
    ledger.close()


def test_missing_cutoff_and_staged_writes_are_not_committed_history(tmp_path):
    ledger,_,_,args=original(tmp_path)
    with pytest.raises(LedgerError):read_history(ledger,**(args|{'cutoff_ref':'f'*64}))
    with ledger.atomic():
        with pytest.raises(LedgerError):read_history(ledger,**args)
    ledger.close()


def test_duplicate_and_malformed_cursor_never_exposes_a_page(tmp_path):
    ledger,_,_,args=original(tmp_path)
    for raw in (b'{"offset":1,"offset":2}',b'[]',b'not-json'):
        with pytest.raises(RetainedHistoryError):
            read_history(ledger,**args,cursor=base64.urlsafe_b64encode(raw).decode())
    ledger.close()


def test_mt5_original_query_precedes_snapshot_and_cutoff_with_exact_decimal_rows(tmp_path):
    from trading.tests.test_mt5_funding_contract import frame,cash
    from vati.funding.mt5 import Mt5CashFact
    from vati.funding.mt5_journal import Mt5FundingBook
    ledger=Ledger(tmp_path/'mt5.sqlite')
    f=replace(frame(),movements=tuple(Mt5CashFact.from_body(cash(native_id=i)) for i in range(1,104)))
    query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(f)
    snap=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native',
        'native_account_mark':f.mark_body(),'funding_observation':{'query_ref':query,'statement':receipt,'scope_hash':f.scope_hash}},
        event_time_ms=11000,received_time_ms=11000)
    ledger.append(snap)
    cutoff=make_event(EventKind.SESSION,'test',{'event':'boundary'},event_time_ms=1,received_time_ms=1);ledger.append(cutoff)
    row={'alias':'native','operation_id':'old_mt5_deletion_00000001','incarnation':'a'*64,'account_control_domain':'b'*64}
    args={'lifecycle':row,'plan_ref':'c'*64,'cutoff_ref':cutoff.hash,
        'profile':{'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}}
    before=ledger.count();first=read_history(ledger,**args)
    assert first['movement_count']==103 and first['query_ref']==query
    assert first['movements'][0]['movement']['fee']=='-1.3E-7'
    assert read_history(ledger,**args,cursor=first['next_cursor'])['movements'][-1]['movement']['native_id']==103
    assert ledger.count()==before
    args['profile']=args['profile']|{'server':'different'}
    assert read_history(ledger,**args)['state']=='UNOBSERVED'
    ledger.close()
