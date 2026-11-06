"""Account display currentness on real SQLite; no provider or trading effects."""
import importlib
import pytest
from vati.accounts import Account,AccountRegistry
from vati.core.events import EventKind,make_event
from vati.core.ledger import Ledger

pf=importlib.import_module('vati.app.portfolio')
BOUND=pf.ACCOUNT_SNAPSHOT_STALENESS_MS
NOW=2_000_000_000_000


def book(tmp_path,rows):
    registry=AccountRegistry(tmp_path/'accounts.json')
    ledger=Ledger(tmp_path/'native.sqlite')
    events={}
    for alias,source,connected in rows:
        registry.add(Account(alias=alias,broker='PAPER',mode='DEMO_TRADER',currency='USD'))
        if source is not None:
            event=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':alias,
                'mode':'DEMO_TRADER','currency':'USD','connected':connected,'verified':True,
                'equity':'12345.67','balance':'12000.00'},event_time_ms=source,
                received_time_ms=source,correlation_id=alias)
            ledger.append(event);events[alias]=event
    return registry,ledger,events


@pytest.mark.parametrize('age,connected,state,reason',[
    (0,True,'LIVE','SOURCE_SNAPSHOT_WITHIN_DISPLAY_BOUND'),
    (BOUND,True,'LIVE','SOURCE_SNAPSHOT_WITHIN_DISPLAY_BOUND'),
    (BOUND+1,True,'STALE','STALE_SOURCE_SNAPSHOT'),
    (-1,True,'STALE','FUTURE_SOURCE_TIME'),
    (NOW,True,'STALE','INVALID_SOURCE_TIME'),
    (NOW+1,True,'STALE','INVALID_SOURCE_TIME'),
    (0,False,'OFFLINE','SOURCE_SNAPSHOT_WITHIN_DISPLAY_BOUND'),
    (BOUND+1,False,'STALE','STALE_SOURCE_SNAPSHOT'),
])
def test_account_original_clock_boundary_and_recorded_values(tmp_path,age,connected,state,reason):
    registry,ledger,events=book(tmp_path,[('paper_one',NOW-age,connected)])
    try:
        before=ledger.count(),ledger.head()
        rows=pf.account_states(ledger,registry.public(),now_ms=NOW)
        projected=pf.portfolio(ledger,registry.public(),now_ms=NOW)
        assert rows==projected['accounts']
        row=rows[0];readback=row['snapshot_readback'];original=events['paper_one']
        assert row['connection_state']==state and row['connected'] is connected
        assert row['equity']=='12345.67' and row['balance']=='12000.00'
        assert projected['totals']['equity']=='12345.67'
        assert readback=={'state':'CURRENT' if state in {'LIVE','OFFLINE'} else 'LAST_KNOWN',
            'reason':reason,'source_revision':original.hash,'source_event_time_ms':NOW-age,
            'source_received_time_ms':NOW-age,'read_at_ms':NOW,'age_ms':age if age<NOW else None,
            'staleness_threshold_ms':BOUND,'execution_authority':False}
        assert (ledger.count(),ledger.head())==before
        assert list(ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[0]==original
    finally:ledger.close()


def test_each_account_owns_its_freshness_and_restart_preserves_evidence(tmp_path):
    registry,ledger,events=book(tmp_path,[('stale_one',NOW-BOUND-1,True),('fresh_two',NOW,True),('never_three',None,False)])
    ledger.append(make_event(EventKind.SESSION,'vati-service',{'event':'HEARTBEAT'},
        event_time_ms=NOW,received_time_ms=NOW,correlation_id='unrelated'))
    before=ledger.count(),ledger.head()
    rows=pf.account_states(ledger,registry.public(),now_ms=NOW)
    by_alias={r['alias']:r for r in rows}
    assert {alias:r['connection_state'] for alias,r in by_alias.items()}=={
        'stale_one':'STALE','fresh_two':'LIVE','never_three':'NEVER_SYNCED'}
    assert by_alias['never_three']['snapshot_readback']['source_revision'] is None
    assert by_alias['never_three']['snapshot_readback']['reason']=='NO_ACCOUNT_SNAPSHOT'
    ledger.close();ledger=Ledger(tmp_path/'native.sqlite')
    try:
        assert pf.account_states(ledger,AccountRegistry(tmp_path/'accounts.json').public(),now_ms=NOW)==rows
        assert pf.portfolio(ledger,registry.public(),now_ms=NOW)['accounts']==rows
        assert (ledger.count(),ledger.head())==before
        # Only a genuine new original snapshot advances this account revision.
        event=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'stale_one',
            'mode':'DEMO_TRADER','currency':'USD','connected':True,'balance':'12000.00','equity':'12345.67'},
            event_time_ms=NOW,received_time_ms=NOW,correlation_id='stale_one')
        ledger.append(event)
        current=next(r for r in pf.account_states(ledger,registry.public(),now_ms=NOW) if r['alias']=='stale_one')
        assert current['connection_state']=='LIVE' and current['snapshot_readback']['source_revision']==event.hash
        assert events['stale_one'] in list(ledger.iter(EventKind.ACCOUNT_SNAPSHOT))
    finally:ledger.close()


def test_one_snapshot_and_one_clock_even_if_concurrent_writer_appends(tmp_path,monkeypatch):
    registry,ledger,events=book(tmp_path,[('paper_one',NOW,True),('paper_two',NOW,True)])
    original=pf._latest_by;calls=[];clock=[]
    def newest(source,kind,key):
        rows=original(source,kind,key)
        if kind==EventKind.ACCOUNT_SNAPSHOT:
            writer=Ledger(tmp_path/'native.sqlite')
            try:writer.append(make_event(EventKind.SESSION,'vati-service',{'event':'HEARTBEAT'},event_time_ms=NOW,received_time_ms=NOW,correlation_id='later'))
            finally:writer.close()
        calls.append(kind)
        return rows
    monkeypatch.setattr(pf,'_latest_by',newest)
    from types import SimpleNamespace
    monkeypatch.setattr(pf,'time',SimpleNamespace(time=lambda:clock.append(True) or NOW/1000))
    try:
        result=pf.portfolio(ledger,registry.public())
        assert len(clock)==1 and calls.count(EventKind.ACCOUNT_SNAPSHOT)==1
        assert all(row['snapshot_readback']['read_at_ms']==NOW for row in result['accounts'])
        assert all(row['snapshot_readback']['source_revision']==events[row['alias']].hash for row in result['accounts'])
    finally:ledger.close()


def test_fresh_process_rereads_original_snapshot_without_ledger_mutation(tmp_path):
    import json,os,signal,subprocess,sys
    registry,ledger,events=book(tmp_path,[('stale_one',NOW-BOUND-1,True),('fresh_two',NOW,True)])
    before=ledger.count(),ledger.head()
    expected=pf.account_states(ledger,registry.public(),now_ms=NOW)
    code='''import json,sys
from vati.accounts import AccountRegistry
from vati.core.ledger import Ledger
from vati.app.portfolio import account_states
ledger=Ledger(sys.argv[1])
try: print(json.dumps(account_states(ledger,AccountRegistry(sys.argv[2]).public(),now_ms=int(sys.argv[3]))))
finally: ledger.close()
'''
    child=subprocess.Popen([sys.executable,'-c',code,str(tmp_path/'native.sqlite'),str(registry.path),str(NOW)],
        env=dict(os.environ),stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        try:out,error=child.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.communicate();raise
        assert child.returncode==0,error.decode()
        assert len(out)<65536 and json.loads(out)==expected
        assert (ledger.count(),ledger.head())==before
    finally:
        if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        ledger.close()
