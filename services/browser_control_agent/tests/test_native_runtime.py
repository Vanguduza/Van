"""Real loopback CDP wire and private mTLS dispatcher tests; no physical host claims."""
import asyncio
import json
import time
from pathlib import Path

import pytest

from services.browser_control_agent.agent import Call
from services.browser_control_agent.authority import Operation
from services.browser_control_agent.cdp import LoopbackCdp, CdpUnavailable
from services.browser_control_agent.server import dispatch_message
from services.browser_control_agent.wire import encode_call, decode_response
from services.browser_stream_host.broker_client import BrokerRefused


@pytest.mark.asyncio
async def test_discovery_attachment_and_multiplex_use_actual_cdp_sessions():
    from aiohttp import web
    seen = []
    async def discovery(request):
        return web.json_response({'webSocketDebuggerUrl': f'ws://127.0.0.1:{request.url.port}/devtools/browser/test'})
    async def socket(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            command = json.loads(message.data)
            seen.append(command)
            result = {}
            if command['method'] == 'Target.getTargets':
                result = {'targetInfos': [{'type': 'page', 'targetId': 'page-1'}]}
            if command['method'] == 'Target.attachToTarget':
                assert command['params'] == {'targetId': 'page-1', 'flatten': True}
                assert 'sessionId' not in command
                result = {'sessionId': 'flattened-1'}
            if command['method'] == 'Page.navigate':
                result = {'frameId': 'frame-1', 'loaderId': 'loader-1'}
                await ws.send_json({'method': 'Page.frameNavigated', 'sessionId': 'flattened-1', 'params': {'frame': {'id': 'frame-1', 'loaderId': 'loader-1', 'url': 'https://example.com'}}})
            if command['method'] == 'Page.getNavigationHistory':
                result = {'entries': [{'id': 1, 'url': 'https://example.com'}], 'currentIndex': 0}
            await ws.send_json({'id': command['id'], 'result': result})
        return ws
    app = web.Application()
    app.router.add_get('/json/version', discovery)
    app.router.add_get('/devtools/browser/test', socket)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    cdp = LoopbackCdp(f'ws://127.0.0.1:{port}')
    try:
        replies = await asyncio.gather(
            cdp.send('page-1', 'Page.navigate', {'url': 'https://example.com'}),
            cdp.send('page-1', 'Page.getNavigationHistory', {}),
        )
        assert replies[0] == {'frameId': 'frame-1', 'loaderId': 'loader-1'}
        committed = await cdp.wait_navigation('page-1', replies[0], 'https://example.com', ('example.com',))
        assert committed['url'] == 'https://example.com'
        assert sum(item['method'] == 'Target.attachToTarget' for item in seen) == 1
        assert all(item['sessionId'] == 'flattened-1' for item in seen if item['method'].startswith(('Page.', 'Security.')))
        with pytest.raises(CdpUnavailable, match='target_unknown'):
            await cdp.send('foreign-page', 'Input.insertText', {'text': 'deny'})
        assert not any(item['method'] == 'Input.insertText' for item in seen)
    finally:
        await cdp.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_discovery_cannot_redirect_to_remote_debugger():
    from aiohttp import web
    async def discovery(request):
        return web.json_response({'webSocketDebuggerUrl': 'ws://10.0.0.1:9222/devtools/browser/secret'})
    app = web.Application()
    app.router.add_get('/json/version', discovery)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    cdp = LoopbackCdp(f"ws://127.0.0.1:{site._server.sockets[0].getsockname()[1]}")
    try:
        with pytest.raises(CdpUnavailable, match='not_loopback'):
            await cdp.connect()
    finally:
        await cdp.close()
        await runner.cleanup()


class Authority:
    def __init__(self, refused=False):
        self.refused = refused
        self.calls = []
        self.deadline = int(time.time()*1000)+60000
    async def validate_call(self, caller, call):
        return await self.authorize_call(caller, call)
    async def validate_result(self, caller, call):
        return await self.authorize_call(caller, call)
    async def authorize_call(self, caller, call):
        self.calls.append((caller, call))
        if self.refused:
            raise BrokerRefused('current_lease_refused')
        return {'session_id': call.session_id, 'task_id': call.task_id, 'target_id': call.target_id,
                'scope': 'browser.actuate', 'step_budget': 5, 'steps_used': 1,
                'deadline_ms': self.deadline, 'allowed_domains': ['example.com'],
                'authority': {'viewport': {'width': 800, 'height': 600}}}


class Browser:
    def __init__(self, url='https://example.com'):
        self.calls = []
        self.url = url
    async def send(self, target, method, params):
        self.calls.append((target, method, params))
        if method == 'Page.getNavigationHistory':
            return {'currentIndex': 0, 'entries': [{'id': 1, 'url': self.url}]}
        if method == 'DOM.getDocument':
            return {'root': {'nodeId': 1}}
        if method == 'DOM.querySelector':
            return {'nodeId': 2}
        return {'outerHTML': '<h1>actual</h1>'}


def wire(operation=Operation.NAVIGATE, params=None):
    return encode_call(Call(operation, 'ibs_test', 'page-1', 'lease', 2, 'task-1', params or {'url': 'https://example.com'}), request_id='request-1')


@pytest.mark.asyncio
async def test_dispatcher_uses_separate_verified_peer_identity_and_broker_authority():
    broker, cdp = Authority(), Browser()
    result = decode_response(await dispatch_message(wire(), caller_common_name='verified-peer', broker=broker, cdp=cdp))
    assert result[1] is True
    assert broker.calls[0][0] == 'verified-peer'
    assert [item[1] for item in cdp.calls] == ['Page.navigate', 'Page.getNavigationHistory']


@pytest.mark.asyncio
async def test_current_broker_refusal_never_actuates():
    broker, cdp = Authority(refused=True), Browser()
    result = decode_response(await dispatch_message(wire(), caller_common_name='verified-peer', broker=broker, cdp=cdp))
    assert result[1] is False
    assert cdp.calls == []


@pytest.mark.asyncio
async def test_redirect_outside_task_domain_never_exposes_dom():
    broker, cdp = Authority(), Browser('https://outside.example.net')
    result = decode_response(await dispatch_message(wire(Operation.QUERY_DOM, {'selector': 'h1'}), caller_common_name='verified-peer', broker=broker, cdp=cdp))
    assert result[1] is False
    assert [item[1] for item in cdp.calls] == ['Page.getNavigationHistory']


@pytest.mark.asyncio
async def test_injected_caller_and_scope_are_not_authority():
    from services.browser_control_agent.wire import WireError
    for field in ('caller_common_name', 'scope', 'budget', 'grant'):
        message = json.loads(wire())
        message[field] = 'owner'
        broker, cdp = Authority(), Browser()
        with pytest.raises(WireError):
            await dispatch_message(json.dumps(message), caller_common_name='verified-peer', broker=broker, cdp=cdp)
        assert broker.calls == [] and cdp.calls == []


def test_check_runtime_has_no_socket_side_effect(monkeypatch, capsys):
    import socket
    from services.browser_control_agent.server import main
    monkeypatch.setattr(socket, 'socket', lambda *args, **kwargs: pytest.fail('runtime check opened a socket'))
    assert main(['--check-runtime']) == 0
    assert json.loads(capsys.readouterr().out)['check'] == 'dependencies_only_no_network_or_listener'

@pytest.mark.asyncio
async def test_navigation_error_does_not_report_the_old_in_scope_page_success():
    class FailedBrowser(Browser):
        async def send(self, target, method, params):
            if method == 'Page.navigate':
                self.calls.append((target, method, params))
                return {'frameId': 'old-frame', 'errorText': 'net::ERR_NAME_NOT_RESOLVED'}
            return await super().send(target, method, params)
    cdp = FailedBrowser('https://example.com/old')
    result = decode_response(await dispatch_message(wire(params={'url': 'https://example.com/new'}), caller_common_name='peer', broker=Authority(), cdp=cdp))
    assert result[1] is False
    assert [item[1] for item in cdp.calls] == ['Page.navigate']


@pytest.mark.asyncio
async def test_navigation_waits_for_delayed_real_history_commit_without_redispatch():
    class DelayedBrowser(Browser):
        def __init__(self):
            super().__init__('https://example.com/old')
            self.observations = 0
        async def send(self, target, method, params):
            if method == 'Page.getNavigationHistory':
                self.observations += 1
                if self.observations >= 3:
                    self.url = 'https://example.com/new'
            return await super().send(target, method, params)
    cdp = DelayedBrowser()
    result = decode_response(await dispatch_message(wire(params={'url': 'https://example.com/new'}), caller_common_name='peer', broker=Authority(), cdp=cdp))
    assert result[1] is True
    assert result[2]['navigation']['url'] == 'https://example.com/new'
    assert sum(item[1] == 'Page.navigate' for item in cdp.calls) == 1
    assert cdp.observations == 3


@pytest.mark.asyncio
async def test_navigation_foreign_redirect_is_typed_failure():
    cdp = Browser('https://outside.example.net')
    result = decode_response(await dispatch_message(wire(params={'url': 'https://example.com/new'}), caller_common_name='peer', broker=Authority(), cdp=cdp))
    assert result[1] is False
    assert sum(item[1] == 'Page.navigate' for item in cdp.calls) == 1


@pytest.mark.asyncio
async def test_real_private_tls_wire_derives_identity_from_certificate(tmp_path):
    import datetime
    import ipaddress
    import ssl
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from services.browser_control_agent.server import build_ssl_context, handle_client
    from services.browser_control_agent.wire import frame
    now = datetime.datetime.now(datetime.timezone.utc)
    def issue(name, ca=None, server=False):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca[0].subject if ca else subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=1))
                   .add_extension(x509.BasicConstraints(ca=ca is None, path_length=None), critical=True))
        if server:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        cert = builder.sign(ca[1] if ca else key, hashes.SHA256())
        cert_path, key_path = tmp_path/(name+'.crt'), tmp_path/(name+'.key')
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        return cert,key,str(cert_path),str(key_path)
    ca = issue('private-ca')
    agent = issue('agent', ca, server=True)
    client = issue('verified-trading-core', ca)
    context = build_ssl_context(ca_file=ca[2],cert_file=agent[2],key_file=agent[3])
    broker, cdp = Authority(), Browser()
    server = await asyncio.start_server(lambda r,w: handle_client(r,w,broker=broker,cdp=cdp),'127.0.0.1',0,ssl=context)
    client_context = ssl.create_default_context(cafile=ca[2])
    client_context.minimum_version = ssl.TLSVersion.TLSv1_3
    client_context.load_cert_chain(client[2], client[3])
    try:
        reader,writer = await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1],ssl=client_context,server_hostname='127.0.0.1')
        writer.write(frame(wire()))
        await writer.drain()
        response = await asyncio.wait_for(reader.readline(),2)
        assert decode_response(response)[1] is True
        assert all(peer == 'verified-trading-core' for peer,_ in broker.calls)
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

@pytest.mark.asyncio
async def test_download_observation_comes_from_canonical_producer_broker_not_call_params():
    class DownloadAuthority(Authority):
        async def authorize_call(self, caller, call):
            resolved = await super().authorize_call(caller,call)
            resolved.update(observation_available=True,observed_downloads=[{'download_id':'actual-guid','state':'COMPLETED','byte_size':18,'content_sha256':'a'*64}])
            return resolved
    call = Call(Operation.OBSERVE_DOWNLOAD,'ibs_test','page-1','lease',2,'task-1',{})
    cdp = Browser()
    result = decode_response(await dispatch_message(encode_call(call,request_id='observed'),caller_common_name='peer',broker=DownloadAuthority(),cdp=cdp))
    assert result[1] is True
    assert result[2]['downloads'][0]['download_id'] == 'actual-guid'
    assert result[2]['observation_available'] is True
    assert result[2]['transfer'] == 'not_through_this_agent'
    assert [entry[1] for entry in cdp.calls] == ['Page.getNavigationHistory']

def test_scoped_agent_history_does_not_expose_previous_unrelated_profile_urls():
    from services.browser_control_agent.agent import _scoped_history
    entries = [{'id':1,'url':'https://private.example.net/previous'},{'id':2,'url':'https://example.com/current'}]
    selected,current = _scoped_history(entries,1,('example.com',))
    assert selected == [entries[1]] and current == 0
