"""The signed worker must verify the physical account before touching its terminal."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import threading,time

import pytest

from test_mt5_worker import FakeMt5,worker_mod,KEY
from vati.execution.mt5_bridge import Mt5BridgeClient


class PhysicalMt5(FakeMt5):
    def __init__(self):
        super().__init__();self.server='Broker-Demo';self.currency='USD';self.demo=True
    def account_info(self):
        a=super().account_info();a.server=self.server;a.currency=self.currency;a.trade_mode=0 if self.demo else 2
        return a


def build(tmp_path,**actual):
    fake=PhysicalMt5()
    for k,v in actual.items():setattr(fake,k,v)
    pw=tmp_path/'password';pw.write_text('s3cret')
    account={'login':12345678,'server':'Broker-Demo','currency':'USD','demo':True,'password_file':str(pw)}
    cfg={'accounts':{'fx_primary':account}}
    worker=worker_mod.Worker(cfg,worker_mod.Terminal(fake),KEY,clock=lambda:1000000)
    client=Mt5BridgeClient(signing_key=KEY,transport=worker.handle)
    return worker,client,fake


def send(client):
    return client.call('order_send',{'alias':'fx_primary','symbol':'EURUSD','type':'BUY','volume':'0.1',
        'price':'1.1','sl':'1.09','order_type':'MARKET'},now_ms=1000000)


@pytest.mark.parametrize('actual',[
    {'server':'Different-Live'},{'currency':'EUR'},{'demo':False},
    {'trade_allowed':'false'},{'trade_allowed':None}])
def test_a_signed_request_cannot_send_on_a_different_physical_identity_or_ambiguous_permission(tmp_path,actual):
    _,client,fake=build(tmp_path,**actual)
    result=send(client)
    assert result.get('status') in {'REJECTED',None} and len(fake.sent)==0,result


def test_matching_native_identity_remains_functional_and_read_only_permission_stays_readable(tmp_path):
    _,client,fake=build(tmp_path)
    assert send(client)['status']=='FILLED' and len(fake.sent)==1
    fake.trade_allowed=False
    account=client.call('sync_account',{'alias':'fx_primary'},now_ms=1000000)['account']
    assert account['verified'] is True and account['trade_allowed'] is False
    assert send(client)['status']=='REJECTED' and len(fake.sent)==1


def test_the_terminal_login_cache_cannot_transfer_a_login_number_across_servers():
    fake=PhysicalMt5();terminal=worker_mod.Terminal(fake)
    assert terminal.login(12345678,'Broker-Demo','s3cret')
    assert terminal.login(12345678,'Other-Server','s3cret')
    assert [row[1] for row in fake.login_calls]==['Broker-Demo','Other-Server']


def test_parallel_aliases_cannot_switch_the_terminal_between_identity_check_and_send(tmp_path):
    class Terminal:
        def __init__(self):
            self.selected=None;self.sends=[];self.first_sending=threading.Event();self.second_sending=threading.Event()
        def login(self,login,server,password):self.selected=server;return True
        def account(self):return {'login':12345678,'server':self.selected,'currency':'USD','demo':True,'trade_allowed':True}
        def order_send(self,body):
            if body['alias']=='account_one':
                self.first_sending.set();self.second_sending.wait(timeout=0.5)
            else:self.second_sending.set()
            self.sends.append((body['alias'],self.selected))
            return {'status':'FILLED'}
    terminal=Terminal();cfg={'accounts':{}}
    for alias in ['account_one','account_two']:
        cfg['accounts'][alias]={'login':12345678,'server':alias,'currency':'USD','demo':True}
    worker=worker_mod.Worker(cfg,terminal,KEY,clock=lambda:1000000)
    from vati.execution.mt5_bridge import BridgeRequest
    signer=Mt5BridgeClient(signing_key=KEY)
    requests=[signer.sign(BridgeRequest('order_send',index+1,1000000,{'alias':alias})).__dict__
        for index,alias in enumerate(cfg['accounts'])]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(worker.handle,requests[0])
        assert terminal.first_sending.wait(timeout=2)
        second=pool.submit(worker.handle,requests[1])
        results=[first.result(),second.result()]
    assert all(r.get('status')=='FILLED' for r in results)
    assert len(terminal.sends)==2 and all(alias==physical for alias,physical in terminal.sends)


def test_waiting_for_native_login_cannot_extend_a_signed_entry_request_lifetime(tmp_path):
    worker,client,fake=build(tmp_path);clock={'now':1000000};worker.clock=lambda:clock['now']
    login=worker.t.login
    def delayed(*args):
        result=login(*args);clock['now']+=worker_mod.SKEW_MS+1;return result
    worker.t.login=delayed
    from vati.execution.mt5_bridge import BridgeRequest
    request=client.sign(BridgeRequest('order_send',1,1000000,{'alias':'fx_primary','symbol':'EURUSD',
        'type':'BUY','volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET'}))
    result=worker.handle(request.__dict__)
    assert result.get('status')=='REJECTED' and not fake.sent,result


@pytest.mark.parametrize('raw_mode',[None,False,1,'0'])
def test_unknown_or_ambiguous_native_trade_mode_cannot_establish_demo_identity(tmp_path,raw_mode):
    _,client,fake=build(tmp_path);original=fake.account_info
    def account_info():
        a=original();a.trade_mode=raw_mode;return a
    fake.account_info=account_info
    result=send(client)
    assert 'identity' in result.get('error','') and not fake.sent


@pytest.mark.parametrize('field,value',[
    ('currency',None),('demo','true'),('demo',None),('server',''),
    ('login',True),('login',12345678.5),('login','１２３４５６７８')])
def test_incomplete_profile_cannot_open_credentials_or_log_into_a_terminal(tmp_path,field,value):
    worker,client,fake=build(tmp_path)
    worker.cfg['accounts']['fx_primary'][field]=value
    worker.cfg['accounts']['fx_primary']['password_file']=str(tmp_path/'not-created')
    result=send(client)
    assert 'identity' in result.get('error','') and not fake.login_calls and not fake.sent
