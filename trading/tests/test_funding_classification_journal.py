"""BE-006 owner assertions with actual SQLite owners; SOURCE fixtures, no venue effects."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import threading

import pytest
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.funding.native import NativeCashMovement,NativeCashStatement
from vati.funding.journal import FundingBook
from vati.funding.classification import classify
from vati.funding.classification_journal import ClassificationBook,ClassificationError


def original(path):
    with closing(Ledger(path)) as ledger:
        row=NativeCashMovement(17,'FUTURE_NATIVE_CODE',Decimal('12.34567890'),Decimal('90.00000000'),None,None,100,8)
        statement=NativeCashStatement('CTRADER','DEMO','fixture',33,9,'EUR',0,200,300,(row,))
        receipt=FundingBook(ledger,clock=lambda:300).record_statement(statement)
        body={'operation_id':'original_label_0001','scope_hash':statement.scope_hash,'native_id':17,
              'statement_ref':receipt['statement_ref'],'row_digest':canonical_hash(row.body()),
              'expected_revision':0,'action':'SET','label':'DEPOSIT'}
    return statement,body


def publish(book,body,**kw):
    return book.publish(body,device_id='device-original',received_at_ms=1000,**kw)


def test_actual_journal_create_correct_withdraw_original_replay_restart_and_native_invariance(tmp_path):
    path=tmp_path/'ledger.sqlite';statement,body=original(path)
    with closing(Ledger(path)) as ledger:
        book=ClassificationBook(ledger,clock=lambda:1000)
        native=FundingBook(ledger).observations(statement.scope_hash)
        first=publish(book,body)
        assert publish(book,body)==first
        assert book.lookup(body['operation_id'])['original']['movement']==statement.movements[0].body()
        corrected={**body,'operation_id':'corrected_label_0002','expected_revision':1,'label':'OTHER_INCOME'}
        second=publish(book,corrected)
        assert second['previous_ref']==first['receipt_ref']
        assert book.lookup(body['operation_id'])['current_assertion_state']=='SUPERSEDED'
        assert book.overlay(statement.scope_hash)['descriptive_totals']==[{'currency':'EUR','label':'OTHER_INCOME','delta':'12.34567890'}]
        assert book.overlay(statement.scope_hash,as_of=first['receipt_ref'])['assertions'][0]['label']=='DEPOSIT'
        third=publish(book,{**corrected,'operation_id':'withdraw_label_0003','action':'WITHDRAW','label':None,'expected_revision':2})
        assert third['state']=='WITHDRAWN' and not book.overlay(statement.scope_hash)['descriptive_totals']
        assert FundingBook(ledger).observations(statement.scope_hash)==native
        assert classify(statement.movements[0].operation,statement.movements[0].delta)['category']=='UNRESOLVED'
        assert ledger.count(EventKind.FINANCIAL_MOVEMENT)==0
        assert all(first[k] is False for k in ('execution_authority','risk_capital_qualified','provider_facts_changed','settlement_qualified'))
    with closing(Ledger(path)) as ledger:
        book=ClassificationBook(ledger,clock=lambda:999999999)
        assert publish(book,body)==first  # original expiry never refreshed
        assert book.lookup(body['operation_id'])['receipt']==first
        assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==3


@pytest.mark.parametrize('change,code',[
    ({'expected_revision':2},'REVISION_CONFLICT'),({'statement_ref':'0'*64},'SOURCE_UNKNOWN'),
    ({'row_digest':'0'*64},'SOURCE_UNKNOWN'),({'scope_hash':'0'*64},'SOURCE_UNKNOWN'),
    ({'native_id':18},'SOURCE_UNKNOWN'),({'action':'WITHDRAW','label':None},'NO_CURRENT_ASSERTION')])
def test_exact_original_source_and_generation_negative(tmp_path,change,code):
    path=tmp_path/'facts';_,body=original(path)
    with closing(Ledger(path)) as ledger:
        with pytest.raises(ClassificationError,match=code):publish(ClassificationBook(ledger,clock=lambda:1000),body|change)
        assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


def test_same_operation_changed_intent_or_actor_cannot_retarget(tmp_path):
    path=tmp_path/'facts';_,body=original(path)
    with closing(Ledger(path)) as ledger:
        book=ClassificationBook(ledger,clock=lambda:1000);first=publish(book,body)
        for changed in (body|{'label':'FEE'},body|{'expected_revision':1}):
            with pytest.raises(ClassificationError,match='ORIGINAL_CONFLICT'):publish(book,changed)
        with pytest.raises(ClassificationError,match='ORIGINAL_CONFLICT'):
            book.publish(body,device_id='other-device',received_at_ms=1000)
        assert book.lookup(body['operation_id'])['receipt']==first


@pytest.mark.parametrize('now,cancelled,code',[(301000,False,'EXPIRED'),(999,False,'EXPIRED'),(1000,True,'CANCELLED')])
def test_final_deadline_and_cancellation_no_append(tmp_path,now,cancelled,code):
    path=tmp_path/'facts';_,body=original(path)
    with closing(Ledger(path)) as ledger:
        with pytest.raises(ClassificationError,match=code):publish(ClassificationBook(ledger,clock=lambda:now),body,cancelled=lambda:cancelled)
        assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


def test_source_conflict_blocks_new_assertion_but_original_history_remains(tmp_path):
    path=tmp_path/'facts';statement,body=original(path)
    with closing(Ledger(path)) as ledger:
        book=ClassificationBook(ledger,clock=lambda:1000);receipt=publish(book,body)
        conflict=replace(statement,movements=(replace(statement.movements[0],delta=Decimal('13.00000000')),))
        assert FundingBook(ledger,clock=lambda:300).record_statement(conflict)['state']=='CONFLICT'
        read=book.lookup(body['operation_id'])
        assert read['receipt']==receipt and read['current_assertion_state']=='UNKNOWN'
        with pytest.raises(ClassificationError,match='SOURCE_CONFLICT'):
            publish(book,body|{'operation_id':'new_original_00002','expected_revision':1})
        assert publish(book,body)==receipt
        assert book.overlay(statement.scope_hash,as_of=receipt['receipt_ref'])['assertions'][0]['label']=='DEPOSIT'


def test_two_real_ledger_writers_cas_and_exact_replay(tmp_path):
    path=tmp_path/'facts';_,body=original(path);barrier=threading.Barrier(2);out=[]
    def run(op):
        with closing(Ledger(path)) as ledger:
            barrier.wait()
            try:out.append(publish(ClassificationBook(ledger,clock=lambda:1000),body|{'operation_id':op}))
            except ClassificationError as e:out.append(e.code)
    threads=[threading.Thread(target=run,args=(f'competing_label_000{i}',)) for i in range(2)]
    for t in threads:t.start()
    for t in threads:t.join(10);assert not t.is_alive()
    assert sum(isinstance(v,dict) for v in out)==1 and 'FUNDING_LABEL_REVISION_CONFLICT' in out
    with closing(Ledger(path)) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==1


@pytest.mark.parametrize('field,value',[('revision',900),('original',[]),('request',[]),('owner_id','foreign'),('previous_ref','0'*64)])
def test_tampered_label_history_holds_without_reconstruction(tmp_path,field,value):
    import json
    path=tmp_path/'facts';_,body=original(path)
    with closing(Ledger(path)) as ledger:
        book=ClassificationBook(ledger,clock=lambda:1000);publish(book,body)
        row=ledger._conn.execute('SELECT seq,payload_json FROM events WHERE kind=?',(EventKind.FUNDING_OWNER_CLASSIFICATION.value,)).fetchone()
        p=json.loads(row[1]);p[field]=value
        ledger._conn.execute('UPDATE events SET payload_json=? WHERE seq=?',(json.dumps(p),row[0]));ledger._conn.commit()
    with closing(Ledger(path)) as ledger:
        with pytest.raises(ClassificationError,match='HISTORY_UNKNOWN'):ClassificationBook(ledger).lookup(body['operation_id'])
        with pytest.raises(ClassificationError,match='HISTORY_UNKNOWN'):publish(ClassificationBook(ledger,clock=lambda:1000),body|{'operation_id':'no_replacement_0002'})


def test_actual_native_capture_owner_report_overlay_never_changes_raw_economic_view(tmp_path):
    from test_funding_runtime import setup
    from test_funding_owner_reports import profile,snapshot
    from vati.app.portfolio import account_states
    from vati.funding.runtime import capture_funding
    ledger,transport,adapter=setup(tmp_path)
    with closing(ledger):
        result=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
        snapshot(ledger,funding_observation=result)
        before=account_states(ledger,[profile()],now_ms=3000)[0]
        target=FundingBook(ledger).observations(before['funding']['scope_hash'])['movements'][0]
        body={'operation_id':'report_overlay_0001','scope_hash':before['funding']['scope_hash'],
              'native_id':target['movement']['native_id'],'statement_ref':target['original_statement_ref'],
              'row_digest':canonical_hash(target['movement']),'expected_revision':0,'action':'SET','label':'FEE'}
        receipt=publish(ClassificationBook(ledger,clock=lambda:1000),body)
        after=account_states(ledger,[profile()],now_ms=3000)[0]
        overlay=after['funding'].pop('owner_classification')
        before['funding'].pop('owner_classification')
        assert after==before
        assert overlay['assertions'][0]['receipt']==receipt
        assert overlay['descriptive_totals'][0]['label']=='FEE'
        assert overlay['execution_authority'] is overlay['risk_capital_qualified'] is False
        assert not any(name in {'ProtoOANewOrderReq','ProtoOAWithdrawReq'} for name,_ in transport.requests)


@pytest.mark.parametrize('source_body',[[],{}, {'statement':[]}])
def test_typed_original_source_corruption_is_explicit_unknown_not_reconstructed(tmp_path,source_body):
    from vati.core.events import make_event
    path=tmp_path/'facts';_,body=original(path)
    with closing(Ledger(path)) as ledger:
        # A modeled faulty producer with a valid chain still lacks original typed proof.
        event=make_event(EventKind.FUNDING_STATEMENT,'vati-native-funding',source_body,
                         event_time_ms=300,received_time_ms=300,correlation_id='funding:'+body['scope_hash'])
        ledger.append(event)
        with pytest.raises(ClassificationError,match='SOURCE_UNKNOWN'):
            publish(ClassificationBook(ledger,clock=lambda:1000),body)
        assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


def test_supported_postgres_owner_roundtrip_when_actual_isolated_fixture_available():
    import os,uuid
    if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
        pytest.skip('Actual owned PostgreSQL fixture unavailable; SQLite is not PostgreSQL qualification')
    from vati.core.ledger_pg import PostgresLedger
    name='owner-classification-'+uuid.uuid4().hex
    with closing(PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name=name)) as ledger:
        row=NativeCashMovement(17,'FUTURE_NATIVE_CODE',Decimal('12.34567890'),Decimal('90.00000000'),None,None,100,8)
        statement=NativeCashStatement('CTRADER','DEMO','fixture',33,9,'EUR',0,200,300,(row,))
        ref=FundingBook(ledger,clock=lambda:300).record_statement(statement)['statement_ref']
        body={'operation_id':'pg_classification_0001','scope_hash':statement.scope_hash,'native_id':17,'statement_ref':ref,
              'row_digest':canonical_hash(row.body()),'expected_revision':0,'action':'SET','label':'FEE'}
        receipt=publish(ClassificationBook(ledger,clock=lambda:1000),body)
    with closing(PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name=name)) as ledger:
        book=ClassificationBook(ledger,clock=lambda:999999999)
        assert publish(book,body)==receipt and book.lookup(body['operation_id'])['receipt']==receipt


def test_original_receipt_fresh_interpreter_readback(tmp_path):
    import os,json,subprocess,sys
    path=tmp_path/'facts';_,body=original(path)
    with closing(Ledger(path)) as ledger:receipt=publish(ClassificationBook(ledger,clock=lambda:1000),body)
    command=[sys.executable,'-B','-c',
        'import sys,json;from vati.core.ledger import Ledger;from vati.funding.classification_journal import ClassificationBook;l=Ledger(sys.argv[1]);print(json.dumps(ClassificationBook(l).lookup(sys.argv[2])["receipt"],sort_keys=True));l.close()',str(path),body['operation_id']]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==receipt


def test_existing_mt5_owner_original_scope_and_separate_native_components(tmp_path):
    from test_mt5_funding_contract import frame,cash
    from vati.funding.mt5 import Mt5CashFact
    from vati.funding.mt5_journal import Mt5FundingBook
    from dataclasses import replace
    f=replace(frame(),movements=(Mt5CashFact.from_body(cash()),))
    with closing(Ledger(tmp_path/'mt5')) as ledger:
        _,receipt=Mt5FundingBook(ledger,clock=lambda:10000).capture(f)
        body={'operation_id':'mt5_owner_label_0001','scope_hash':f.scope_hash,'native_id':f.movements[0].native_id,
              'statement_ref':receipt['statement_ref'],'row_digest':canonical_hash(f.movements[0].body()),
              'expected_revision':0,'action':'SET','label':'DEPOSIT'}
        book=ClassificationBook(ledger,clock=lambda:11000)
        result=book.publish(body,device_id='device-original',received_at_ms=11000)
        assert book.lookup(body['operation_id'])['receipt']==result
        overlay=book.overlay(f.scope_hash)
        assert overlay['descriptive_totals']==[]
        components={r['component']:r['amount'] for r in overlay['native_component_totals']}
        assert components=={'profit':'10000','commission':'0','swap':'0','fee':'-1.3E-7'}
        assert overlay['execution_authority'] is overlay['settlement_qualified'] is False
