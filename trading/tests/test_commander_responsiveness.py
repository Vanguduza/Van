"""The real native HTTP dispatcher must remain readable during provider IO."""
import asyncio
import json
from threading import Event

import pytest
from httpx import ASGITransport,AsyncClient

from commander.accounts import AccountControlSettings,_write_secrets
from commander.app import CommanderSettings,create_app
from commander.auth import sign_headers
from test_commander import FakeRunner,TOKEN
from test_deriv_native_identity import Socket,native
from vati.accounts import Account,AccountRegistry,CredentialRef


@pytest.mark.asyncio
async def test_native_health_and_status_remain_available_while_broker_verification_waits(tmp_path):
    entered,release=Event(),Event()
    class WaitingSocket(Socket):
        def recv(self):
            if self.requests and 'authorize' in self.requests[-1]:
                entered.set()
                if not release.wait(2):raise TimeoutError('fixture watchdog released a blocked server')
            return super().recv()
    registry=AccountRegistry(tmp_path/'accounts.json');secret=tmp_path/'secrets/deriv_demo.env'
    _write_secrets(secret,{'DERIV_API_TOKEN':'fixture-token'})
    registry.add(Account(alias='deriv_demo',broker='DERIV',mode='DEMO_TRADER',currency='USD',login='VRTC900',credential_ref=CredentialRef(secrets_file=str(secret))))
    control=AccountControlSettings(str(registry.path),str(secret.parent),deriv_connector=lambda url:WaitingSocket(native()))
    settings=CommanderSettings(tokens={'van-gateway':TOKEN},ledger=str(tmp_path/'vati.sqlite'),heartbeat_dir=str(tmp_path/'hb'),
        log_dir=str(tmp_path/'logs'),data_dir=str(tmp_path),accounts_registry=str(registry.path),secrets_dir=str(secret.parent),runner=FakeRunner(),account_control=control)
    app=create_app(settings)
    def request(command,args):
        body=json.dumps({'args':args}).encode()
        return dict(content=body,headers={**sign_headers(TOKEN,'POST','/v1/cmd/'+command,body),'content-type':'application/json'})
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://native.test') as client:
        pending=asyncio.create_task(client.post('/v1/cmd/account_verify',**request('account_verify',{'alias':'deriv_demo'})))
        try:
            assert await asyncio.to_thread(entered.wait,3)
            health=await asyncio.wait_for(client.get('/health'),0.5)
            assert health.status_code==200 and not pending.done(),'blocking provider IO occupied the native event loop'
            listing=await asyncio.wait_for(client.post('/v1/cmd/accounts',**request('accounts',{})),0.5)
            assert listing.status_code==200 and listing.json()['result']['accounts'][0]['alias']=='deriv_demo'
        finally:
            release.set()
            response=await asyncio.wait_for(pending,4)
        assert response.status_code==200 and response.json()['result']['ok'] is True


def settings_for(tmp_path,runner):
    return CommanderSettings(tokens={'van-gateway':TOKEN},ledger=str(tmp_path/'vati.sqlite'),heartbeat_dir=str(tmp_path/'hb'),
        log_dir=str(tmp_path/'logs'),data_dir=str(tmp_path),accounts_registry=str(tmp_path/'accounts.json'),secrets_dir=str(tmp_path/'secrets'),runner=runner)


def restart_request(unit):
    body=json.dumps({'args':{'unit':unit}}).encode()
    return dict(content=body,headers={**sign_headers(TOKEN,'POST','/v1/cmd/restart_service',body),'content-type':'application/json'})


@pytest.mark.asyncio
async def test_cancelled_http_waiter_cannot_let_a_second_native_write_overtake_the_first(tmp_path):
    entered,release,second=Event(),Event(),Event()
    class WaitingRunner(FakeRunner):
        def __call__(self,argv,timeout):
            if argv[:2]==['systemctl','restart']:
                if argv[2].endswith('@first.service'):
                    entered.set();assert release.wait(3)
                else:second.set()
            return super().__call__(argv,timeout)
    app=create_app(settings_for(tmp_path,WaitingRunner()))
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://native.test') as client:
        first=asyncio.create_task(client.post('/v1/cmd/restart_service',**restart_request('vati-session@first.service')))
        assert await asyncio.to_thread(entered.wait,2)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):await first
        following=asyncio.create_task(client.post('/v1/cmd/restart_service',**restart_request('vati-session@second.service')))
        try:
            assert not await asyncio.to_thread(second.wait,0.15),'HTTP cancellation released the native write serialization'
            assert (await client.get('/health')).status_code==200
        finally:release.set()
        assert (await asyncio.wait_for(following,3)).status_code==200
        assert second.is_set()


@pytest.mark.asyncio
async def test_a_queued_signed_command_is_rechecked_before_actual_dispatch(tmp_path,monkeypatch):
    import commander.app as module
    entered,release,admitted=Event(),Event(),Event();clock={'now':1_800_000_000}
    class WaitingRunner(FakeRunner):
        def __call__(self,argv,timeout):
            if argv[:2]==['systemctl','restart'] and argv[2].endswith('@first.service'):
                entered.set();assert release.wait(3)
            return super().__call__(argv,timeout)
    runner=WaitingRunner();app=create_app(settings_for(tmp_path,runner))
    monkeypatch.setattr('commander.auth.time.time',lambda:clock['now'])
    native_verify=module.verify_request_principal
    def observed(*args,**kwargs):
        result=native_verify(*args,**kwargs)
        if result[0] and b'@second.service' in args[4]:admitted.set()
        return result
    monkeypatch.setattr(module,'verify_request_principal',observed)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://native.test') as client:
        first=asyncio.create_task(client.post('/v1/cmd/restart_service',**restart_request('vati-session@first.service')))
        assert await asyncio.to_thread(entered.wait,2)
        following=asyncio.create_task(client.post('/v1/cmd/restart_service',**restart_request('vati-session@second.service')))
        try:
            assert await asyncio.to_thread(admitted.wait,2)
            clock['now']+=61
        finally:release.set()
        assert (await asyncio.wait_for(first,3)).status_code==200
        expired=await asyncio.wait_for(following,3)
        assert expired.status_code==401,expired.text
        assert not any(argv[:2]==['systemctl','restart'] and argv[2].endswith('@second.service') for argv in runner.calls)


@pytest.mark.asyncio
async def test_lost_queued_http_waiters_do_not_reopen_capacity_for_unbounded_work(tmp_path,monkeypatch):
    import commander.app as module
    import threading
    entered,release,admitted=Event(),Event(),Event();count={'value':0}
    class WaitingRunner(FakeRunner):
        def __call__(self,argv,timeout):
            if argv[:2]==['systemctl','restart'] and argv[2].endswith('@first.service'):
                entered.set();assert release.wait(4)
            return super().__call__(argv,timeout)
    runner=WaitingRunner();app=create_app(settings_for(tmp_path,runner))
    native_verify=module.verify_request_principal
    def observed(*args,**kwargs):
        result=native_verify(*args,**kwargs)
        if result[0] and threading.current_thread() is threading.main_thread():
            count['value']+=1
            if count['value']==module.MAX_NATIVE_PENDING_COMMANDS:admitted.set()
        return result
    monkeypatch.setattr(module,'verify_request_principal',observed)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://native.test') as client:
        first=asyncio.create_task(client.post('/v1/cmd/restart_service',**restart_request('vati-session@first.service')))
        assert await asyncio.to_thread(entered.wait,2)
        queued=[asyncio.create_task(client.post('/v1/cmd/restart_service',**restart_request(f'vati-session@queued_{n}.service'))) for n in range(module.MAX_NATIVE_PENDING_COMMANDS-1)]
        try:
            assert await asyncio.to_thread(admitted.wait,2)
            for task in queued:task.cancel()
            await asyncio.gather(*queued,return_exceptions=True)
            try:
                overload=await asyncio.wait_for(client.post('/v1/cmd/restart_service',**restart_request('vati-session@overflow.service')),0.5)
            except TimeoutError:
                raise AssertionError('native queue admitted overflow after cancelled HTTP waiters') from None
            assert overload.status_code==503,overload.text
            assert not first.done()
            assert (await client.get('/health')).status_code==200
        finally:release.set()
        assert (await asyncio.wait_for(first,3)).status_code==200
        # Native work remains owned by the executor after its HTTP waiters end.
        for _ in range(100):
            if sum(argv[:2]==['systemctl','restart'] for argv in runner.calls)==module.MAX_NATIVE_PENDING_COMMANDS:break
            await asyncio.sleep(0.01)
        assert sum(argv[:2]==['systemctl','restart'] for argv in runner.calls)==module.MAX_NATIVE_PENDING_COMMANDS
        assert not any('overflow' in arg for argv in runner.calls for arg in argv)


@pytest.mark.asyncio
async def test_closed_native_lifecycle_refuses_new_writes_without_invoking_the_runner(tmp_path):
    runner=FakeRunner();app=create_app(settings_for(tmp_path,runner))
    async with app.router.lifespan_context(app):pass
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://native.test') as client:
        response=await client.post('/v1/cmd/restart_service',**restart_request('vati-session@first.service'))
    assert response.status_code==503,response.text
    assert runner.calls==[]
