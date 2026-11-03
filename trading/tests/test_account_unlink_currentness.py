"""Actual paired owner/A4 -> signed native route and protected unlink writers."""
import io,json,os,time,subprocess,sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from types import SimpleNamespace as NS
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.tests.test_account_unlink_review import client,_env,isolate,paper,challenge
from vati.accounts import AccountRegistry


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['key','transport_time','healthy_cached'])
async def test_actual_registered_unlink_rechecks_current_envelope_at_writer_and_retains_original_history(client,tmp_path,monkeypatch,fault):
    import commander.auth as auth_module
    import commander.account_effects as effects
    import vati.accounts.registry as storage
    from commander.app import CommanderSettings,create_app
    from commander.accounts import AccountControlSettings
    from commander.auth import sign_headers,SKEW_S
    from van_gateway.trading.accounts import CommanderAccountControl
    from van_gateway.config import get_settings
    ac,app=client;await paper(ac)
    token='owned-native-unlink-current-key-'*3;replacement='owned-replacement-unlink-current-key-'*3
    token_file=tmp_path/'native-current-token';token_file.write_text(token);token_file.chmod(0o600)
    import hashlib
    source=tmp_path/'disconnect-session.json'
    source.write_text(json.dumps({'account_alias':'paper_owner','symbol':'EURUSD','base':'EUR','quote':'USD','timeframe':'M5',
        'contract':{},'mandate':{},'capsules':['fx_trend_pullback-v1'],'registry_path':str(tmp_path/'accounts.json')}))
    sources=((str(source),hashlib.sha256(source.read_bytes()).hexdigest()),)
    settings=CommanderSettings(tokens={'van-gateway':token},ledger=get_settings().vati_ledger_path,
        log_dir=str(tmp_path/'native-log'),units=(),account_control=AccountControlSettings(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),lifecycle_session_sources=sources))
    native=TestClient(create_app(settings));calls=[]
    class Reply:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return self.data
    def controlled_http(request,**kw):
        path=urlsplit(request.full_url).path
        if path.endswith('/account_remove'):calls.append(json.loads(request.data)['args'])
        reply=native.post(path,content=request.data,headers=dict(request.header_items()))
        if reply.status_code>=400:raise HTTPError(request.full_url,reply.status_code,'owned native refusal',{},io.BytesIO(reply.content))
        return Reply(reply.content)
    monkeypatch.setattr('van_gateway.trading.accounts.urlopen',controlled_http)
    app.state.onboarding.control=CommanderAccountControl('https://native.fixture',str(token_file))
    with native:
        body,issued=await challenge(ac,'account_remove',{'alias':'paper_owner'});identity=body['approval_proof']['challenge_id']
        before=(tmp_path/'accounts.json').read_bytes();fsync=storage.os.fsync;reached=[]
        def delayed(fd):
            fsync(fd);marker=effects._effect_started.get()
            if marker is not None and marker[1].command=='account_remove' and not reached and '.accounts.json.' in os.readlink('/proc/self/fd/'+str(fd)):
                reached.append(True);assert marker[0] is False
                if fault=='key':settings.tokens['van-gateway']=replacement
                elif fault=='transport_time':monkeypatch.setattr(auth_module,'time',NS(time=lambda:time.time()+SKEW_S+1))
        monkeypatch.setattr(storage.os,'fsync',delayed)
        result=await ac.post('/v1/trading/accounts/action',json=body)
        assert reached
        if fault!='healthy_cached':
            expected='UNKNOWN' if fault=='key' else 'REFUSED'
            assert result.status_code==409 and result.json()['effect_state']==expected,result.text
            # Rotation invalidates Gateway's readback key. A shifted shared
            # transport clock also signs the independent readback afresh, so
            # that read can expose the native refusal without reopening it.
            if fault=='transport_time':
                assert result.json()['native']['result']['status_code']==401
                assert result.json()['native']['reconciliation_required'] is False
            assert (tmp_path/'accounts.json').read_bytes()==before
            from commander.account_effects import AccountEffectJournal
            from vati.core import Ledger
            ledger=Ledger(get_settings().vati_ledger_path)
            try:assert AccountEffectJournal(ledger).status(identity,'test-device').phase=='REFUSED'
            finally:ledger.close()
        else:
            assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
            assert result.json()['remote_account_closed'] is False
            marker_clock=issued['approval_expires_at_unix']+1
            monkeypatch.setattr(effects,'time',NS(time=lambda:marker_clock))
            path='/v1/cmd/account_remove';raw=json.dumps({'args':calls[0]}).encode()
            replay=native.post(path,content=raw,headers={**sign_headers(token,'POST',path,raw),'content-type':'application/json'})
            # A sealed cached outcome is read without opening another effect;
            # advancing only the journal's effect clock does not revoke the
            # current authenticated transport or change original history.
            assert replay.status_code==200 and replay.json()['result']['removed'] is True,replay.text
            path='/v1/cmd/account_operation'
            raw=json.dumps({'args':{'operation_id':identity,'device_id':'test-device',
                'account_control_domain':calls[0]['_expected_account_control_domain']}}).encode()
            original=native.post(path,content=raw,headers={**sign_headers(token,'POST',path,raw),'content-type':'application/json'})
            assert original.status_code==200 and original.json()['result']['effect_state']=='APPLIED',original.text
            assert len(reached)==1
            read=await ac.get('/v1/trading/accounts/operations/'+identity)
            assert read.status_code==200 and read.json()['effect_state']=='APPLIED' and read.json()['operation_id']==identity
            assert 'paper_owner' not in AccountRegistry(tmp_path/'accounts.json').accounts


@pytest.mark.asyncio
async def test_real_queued_unlink_writer_refuses_expiry_without_original_mutation(client,tmp_path,monkeypatch):
    from contextlib import contextmanager
    from threading import Thread,Event
    import commander.account_effects as effects
    from vati.accounts.registry import AccountRegistry as Registry
    ac,app=client;await paper(ac);body,issued=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    before=(tmp_path/'accounts.json').read_bytes();clock=[int(time.time())]
    monkeypatch.setattr(effects,'time',NS(time=lambda:clock[0]))
    lock=Registry._mutation_lock;acquired=Event();attempt=Event();threads=[];errors=[]
    def holder():
        try:
            with lock(Registry(tmp_path/'accounts.json')):
                acquired.set();assert attempt.wait(5)
                # Keep the real lock held while the caller enters its wait.
                Event().wait(.03);clock[0]=issued['approval_expires_at_unix']
        except BaseException as error:errors.append(error)
    # cmd_account_remove already owns the global writer lock around remove;
    # therefore queue at its first protected global-lock acquisition instead.
    @contextmanager
    def first_global(self):
        marker=effects._effect_started.get()
        if marker is not None and marker[1].command=='account_remove' and not threads:
            worker=Thread(target=holder,name='owned-unlink-writer-holder');threads.append(worker);worker.start();assert acquired.wait(5)
        if marker is not None and threads:attempt.set()
        with lock(self):yield
    monkeypatch.setattr(Registry,'_mutation_lock',first_global)
    try:result=await ac.post('/v1/trading/accounts/action',json=body)
    finally:
        attempt.set()
        for worker in threads:worker.join(timeout=6)
    assert threads and all(not t.is_alive() for t in threads) and not errors
    assert result.status_code==409 and (tmp_path/'accounts.json').read_bytes()==before,result.text
    assert result.json()['effect_state']=='REFUSED' and result.json()['native']['result']['status_code']==403
    read=await ac.get('/v1/trading/accounts/operations/'+body['approval_proof']['challenge_id'])
    assert read.json()['effect_state']=='REFUSED'


@pytest.mark.asyncio
async def test_real_child_death_after_unlink_cannot_reopen_original_or_grant_cleanup(client,tmp_path,monkeypatch):
    from van_gateway.trading.accounts import LocalAccountControl
    ac,app=client;await paper(ac);body,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    identity=body['approval_proof']['challenge_id'];original=app.state.onboarding.control.run;children=[]
    source='''import json,os,sys
from commander.accounts import AccountControlSettings,build_account_handlers
from commander.account_effects import AccountEffectJournal
root=sys.argv[1]
def die(*a,**kw):os._exit(74)
AccountEffectJournal.complete=die
sys.path.insert(0,str(__import__('pathlib').Path(__import__('commander').__file__).resolve().parents[1]/'tests'))
from trading.tests.test_commander import dispatch_admitted_gateway_test_body
dispatch_admitted_gateway_test_body(root,json.loads(sys.argv[2]))
'''
    def killed(command,args):
        if command!='account_remove':return original(command,args)
        child=subprocess.run([sys.executable,'-c',source,str(tmp_path),json.dumps({k:v for k,v in args.items() if k!='_account_dispatch_guard'})],capture_output=True,timeout=12)
        children.append(child.returncode);assert child.returncode==74,child.stderr.decode()[:400]
        raise ConnectionError('owned original process died before completion receipt')
    monkeypatch.setattr(app.state.onboarding.control,'run',killed)
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert result.status_code==409 and result.json()['effect_state']=='UNKNOWN' and children==[74]
    assert 'paper_owner' not in AccountRegistry(tmp_path/'accounts.json').accounts
    app.state.onboarding.control=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'vati.sqlite'))
    for _ in range(2):
        read=await ac.get('/v1/trading/accounts/operations/'+identity)
        assert read.status_code==200 and read.json()['effect_state']=='UNKNOWN' and read.json()['result'] is None
    assert children==[74]


@pytest.mark.asyncio
@pytest.mark.parametrize('wait_point',['history','lease_read','final_domain'])
async def test_held_retirement_lease_cannot_expire_during_final_validation(client,tmp_path,monkeypatch,wait_point):
    import commander.account_effects as effects
    import commander.account_retirement as retirement
    import vati.accounts.registry as storage
    from vati.app.account_lease import AccountRuntimeLease as ActualLease
    from vati.app.sqlite_lease import SQLiteLeaseStore
    ac,app=client;await paper(ac);body,issued=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    identity=body['approval_proof']['challenge_id'];before=(tmp_path/'accounts.json').read_bytes()
    offset=[0];armed=[False];history_seen=[False];advanced=[]
    # An actually persisted short SOURCE-fixture lease makes lease expiry
    # independent of the unchanged30s readback bound. Production TTL is untouched.
    monkeypatch.setattr(retirement,'AccountRuntimeLease',lambda *a,**kw:ActualLease(*a,ttl_ms=5000,**kw))
    monkeypatch.setattr(retirement,'time',NS(time=lambda:time.time()+offset[0]))
    def advance():
        marker=effects._effect_started.get()
        assert marker is not None and marker[1].operation_id==identity and marker[0] is False
        assert int(time.time())<marker[1].expires_at_unix
        offset[0]=6;advanced.append(True)
    history=retirement._history
    def delayed_history(*a,**kw):
        value=history(*a,**kw)
        if armed[0]:
            history_seen[0]=True
            if wait_point=='history' and not advanced:advance()
        return value
    monkeypatch.setattr(retirement,'_history',delayed_history)
    read=SQLiteLeaseStore.read
    def delayed_lease(self,*a,**kw):
        value=read(self,*a,**kw)
        if wait_point=='lease_read' and armed[0] and not advanced:advance()
        return value
    monkeypatch.setattr(SQLiteLeaseStore,'read',delayed_lease)
    load=storage.load_secret_file
    def delayed_domain(path):
        value=load(path)
        if wait_point=='final_domain' and armed[0] and not advanced and str(path).endswith('/.account-control-domain.env'):advance()
        return value
    monkeypatch.setattr(storage,'load_secret_file',delayed_domain)
    fsync=storage.os.fsync
    def stage(fd):
        fsync(fd);marker=effects._effect_started.get()
        if marker is not None and marker[1].command=='account_remove' and '.accounts.json.' in os.readlink('/proc/self/fd/'+str(fd)):armed[0]=True
    monkeypatch.setattr(storage.os,'fsync',stage)
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert advanced and offset[0]==6 and int(time.time())<issued['approval_expires_at_unix']
    assert result.status_code==409 and (tmp_path/'accounts.json').read_bytes()==before,result.text
    original=await ac.get('/v1/trading/accounts/operations/'+identity)
    assert original.status_code==200 and original.json()['effect_state']=='REFUSED' and not original.json()['reconciliation_required']
    assert 'paper_owner' in AccountRegistry(tmp_path/'accounts.json').accounts


@pytest.mark.asyncio
async def test_expiry_during_last_shred_identity_wait_preserves_credentials_as_partial_unknown(client,tmp_path,monkeypatch):
    import commander.accounts as native
    import commander.account_retirement as retirement
    from backend.tests.test_account_unlink_review import native_funds
    ac,app=client;_,secret,account=native_funds(tmp_path,monkeypatch)
    body,issued=await challenge(ac,'account_remove',{'alias':account.alias})
    identity=body['approval_proof']['challenge_id'];before=secret.read_bytes();offset=[0];armed=[False];seen=[]
    monkeypatch.setattr(retirement,'time',NS(time=lambda:time.time()+offset[0]))
    shred=native._shred
    def guarded(path,**kw):
        guard=kw['before_write']
        def after_guard():guard();armed[0]=True
        return shred(path,**{**kw,'before_write':after_guard})
    monkeypatch.setattr(native,'_shred',guarded);generation=native._file_generation
    def delayed_identity(stat):
        value=generation(stat)
        if armed[0] and not seen:
            assert int(time.time())<issued['approval_expires_at_unix']
            offset[0]=31;seen.append(True)
        return value
    monkeypatch.setattr(native,'_file_generation',delayed_identity)
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert seen and result.status_code==409 and result.json()['effect_state']=='UNKNOWN',result.text
    assert secret.read_bytes()==before and account.alias not in AccountRegistry(tmp_path/'accounts.json').accounts
    original=await ac.get('/v1/trading/accounts/operations/'+identity)
    assert original.status_code==200 and original.json()['effect_state']=='UNKNOWN' and original.json()['result'] is None
