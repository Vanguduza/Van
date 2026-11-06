"""Actual aiortc video/datachannel exchange with deterministic local browser/authority doubles."""
import asyncio
import base64
import copy
import io
import json
import time
from types import SimpleNamespace

import pytest
from PIL import Image
from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription
from services.browser_stream_host.runtime import StreamRuntime, StreamPeer, StreamRefused, navigation_calls
from services.browser_stream_host.broker_client import BrokerRefused
from van_gateway.browser.input_protocol import InputAuthority, InputPacket, InputKind, Channel, encode
from van_gateway.browser.stream_grants import generate_signing_key, StreamGrantSigner, StreamGrantVerifier


def authority():
    now = int(time.time() * 1000)
    return {'session_id': 'ibs_test', 'profile_expires_at_ms': now + 60000, 'expires_at_ms': now + 60000,
            'control_expires_at_ms': now + 60000, 'control_lease_id': 'lease', 'control_generation': 1,
            'control_holder': 'OWNER', 'control_issued_for': 'phone', 'state': 'AUTHORIZED',
            'active_target_id': None, 'viewport': {'width': 128, 'height': 96, 'revision': 1, 'device_scale_factor': 1}}


class Broker:
    def __init__(self):
        self.current = authority()
        self.observations = []
        self.input_calls = []
        self.acked = False
    async def redeem(self, token, producer_id):
        return {'producer_session_id': producer_id, 'session_id': 'ibs_test', 'profile_alias': 'public_research',
                'grant_id': 'grant', 'owner_device_id': 'phone', 'authority': copy.deepcopy(self.current)}
    async def authority(self, producer_id):
        return copy.deepcopy(self.current)
    async def observe(self, producer_id, event, **fields):
        self.observations.append((event, fields))
        state = {'allocated': 'ALLOCATING', 'signaling': 'SIGNALING', 'connecting': 'CONNECTING', 'first_frame': 'INTERACTIVE', 'reconnecting': 'RECONNECTING'}
        if event in state:
            self.current['state'] = state[event]
        return {}
    async def authorize_input(self, producer_id, supplied):
        self.input_calls.append(supplied)
        if not self.acked or supplied.control_generation != self.current['control_generation'] or supplied.viewport_revision != self.current['viewport']['revision']:
            raise BrokerRefused('input_not_current')
        return copy.deepcopy(self.current)


class Browser:
    def __init__(self):
        self.calls = []
        output = io.BytesIO()
        Image.new('RGB', (128, 96), 'blue').save(output, 'JPEG')
        self.image = base64.b64encode(output.getvalue()).decode()
    async def targets(self):
        return [{'targetId': 'page', 'type': 'page', 'url': 'https://example.com', 'title': 'Example'}]
    async def send(self, target, method, params):
        self.calls.append((target, method, params))
        if method == 'Page.captureScreenshot':
            return {'data': self.image}
        if method == 'Page.getNavigationHistory':
            return {'entries': [{'id': 1, 'url': 'https://example.com'}], 'currentIndex': 0}
        return {}


def signed_token():
    key = generate_signing_key('test')
    now = int(time.time() * 1000)
    claims = {'version': 1, 'aud': 'van-browser-stream-runtime', 'grant_id': 'grant', 'session_id': 'ibs_test',
              'profile_alias': 'public_research', 'device_id': 'phone', 'scope': ['webrtc.signal', 'browser.view', 'browser.owner_input'],
              'issued_at_ms': now, 'expires_at_ms': now + 60000, 'max_width': 128, 'max_height': 96, 'max_fps': 30}
    return StreamGrantSigner(key).sign(claims), StreamGrantVerifier({'test': key.public_pem()})


@pytest.mark.asyncio
async def test_real_peer_video_metadata_and_fenced_input_then_resize_closure():
    token, verifier = signed_token()
    broker, cdp = Broker(), Browser()
    runtime = StreamRuntime(cdp, broker, verifier, 'public_research')
    viewer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    viewer.addTransceiver('video', direction='recvonly')
    fast = viewer.createDataChannel('input-fast', ordered=False, maxRetransmits=0)
    reliable = viewer.createDataChannel('input-reliable', ordered=True)
    markers = []
    decoded = asyncio.Event()
    geometry = []
    tasks = []
    @viewer.on('datachannel')
    def channel_open(channel):
        assert channel.label == 'browser-state'
        @channel.on('message')
        def state(message):
            markers.append(json.loads(message))
    @viewer.on('track')
    def video(track):
        async def consume():
            frame = await track.recv()
            geometry.append((frame.width, frame.height))
            decoded.set()
        tasks.append(asyncio.create_task(consume()))
    try:
        offer = await viewer.createOffer()
        await viewer.setLocalDescription(offer)
        body = {'protocol': 1, 'session_id': 'ibs_test', 'control_generation': 1, 'viewport_revision': 1,
                'width': 128, 'height': 96, 'type': 'offer', 'sdp': viewer.localDescription.sdp,
                'data_channels': ['input-fast', 'input-reliable']}
        answer = await runtime.exchange(token, body)
        assert answer['media_epoch'].startswith('prod_')
        assert answer['authenticated_principal_kind'] == 'STREAM_GRANT_BEARER'
        await viewer.setRemoteDescription(RTCSessionDescription(answer['sdp'], 'answer'))
        await asyncio.wait_for(decoded.wait(), 10)
        await asyncio.sleep(0.1)
        assert geometry == [(128, 96)]
        frame_markers = [marker for marker in markers if marker['event_type'] == 'viewport.frame']
        assert len(frame_markers) == 1
        assert frame_markers[0]['media_epoch'] == answer['media_epoch']
        assert frame_markers[0]['frame_sequence'] == 1
        assert any(event == 'first_frame' for event, _ in broker.observations)
        packet = InputPacket(InputAuthority('ibs_test', 'lease', 1, 1), InputKind.TEXT_COMMIT, Channel.RELIABLE, reliable_seq=1, text='owner text')
        reliable.send(encode(packet))
        await asyncio.sleep(0.1)
        assert not any(method == 'Input.insertText' for _, method, _ in cdp.calls)
        broker.acked = True
        reliable.send(encode(InputPacket(packet.authority, packet.kind, packet.channel, reliable_seq=2, text='owner text')))
        for _ in range(20):
            if any(method == 'Input.insertText' for _, method, _ in cdp.calls):
                break
            await asyncio.sleep(0.05)
        assert any(method == 'Input.insertText' and params['text'] == 'owner text' for _, method, params in cdp.calls)
        assert len(broker.input_calls) >= 3
        broker.current['viewport']['revision'] = 2
        await asyncio.sleep(0.65)
        assert not runtime.sessions
    finally:
        await runtime.close()
        await viewer.close()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_initial_frame_marker_survives_long_sctp_open_delay():
    broker, cdp = Broker(), Browser()
    runtime = StreamRuntime(cdp, broker, None, 'public_research')
    redemption = await broker.redeem('', 'prod_' + 'a' * 32)
    session = StreamPeer(runtime, redemption['producer_session_id'], redemption, {'max_fps': 30})
    messages = []
    session.metadata = SimpleNamespace(readyState='connecting', bufferedAmount=0, send=messages.append)
    session.emit('viewport.frame', frame_sequence=1, width=128, height=96)
    for _ in range(20):
        session.emit('session.state', state='CONNECTING')
    session.metadata.readyState = 'open'
    session.flush_metadata()
    parsed = [json.loads(message) for message in messages]
    assert len(parsed) == 9
    assert parsed[0]['event_type'] == 'viewport.frame'
    assert [message['event_seq'] for message in parsed] == sorted(message['event_seq'] for message in parsed)
    await session.close('test', report=False)


@pytest.mark.parametrize('kind,method', [(InputKind.NAVIGATE,'Page.navigate'),(InputKind.SEARCH,'Page.navigate'),(InputKind.HISTORY_BACK,'Page.navigateToHistoryEntry'),(InputKind.HISTORY_FORWARD,'Page.navigateToHistoryEntry'),(InputKind.RELOAD,'Page.reload'),(InputKind.STOP_LOADING,'Page.stopLoading')])
def test_navigation_kinds_have_fixed_cdp_conversations(kind, method):
    packet = InputPacket(InputAuthority('session','lease',1,1), kind, Channel.RELIABLE, text='https://example.com' if kind == InputKind.NAVIGATE else 'query' if kind == InputKind.SEARCH else '')
    history = {'currentIndex':1,'entries':[{'id':3,'url':'https://example.com/a'},{'id':4,'url':'https://example.com/b'},{'id':5,'url':'https://example.com/c'}]}
    assert navigation_calls(packet, history)[0][0] == method

@pytest.mark.asyncio
async def test_signal_prefix_http_endpoint_is_typed_and_does_not_expose_cdp():
    from aiohttp import web, ClientSession
    from services.browser_stream_host.server import build_application
    class Runtime:
        def __init__(self):
            self.calls = []
            self.sessions = {}
            self.cdp = SimpleNamespace(_socket=SimpleNamespace(closed=False))
        async def exchange(self, token, offer):
            self.calls.append((token,offer))
            return {'sdp':'answer','type':'answer','protocol':1}
    runtime = Runtime()
    runner = web.AppRunner(build_application(runtime, '/rtc/public'))
    await runner.setup()
    site = web.TCPSite(runner,'127.0.0.1',0)
    await site.start()
    origin = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    try:
        async with ClientSession() as client:
            response = await client.post(origin+'/rtc/public',json={'type':'offer'})
            assert response.status == 401 and runtime.calls == []
            response = await client.post(origin+'/rtc/public',json={'type':'offer'},headers={'Authorization':'Bearer test-grant'})
            assert response.status == 200 and (await response.json())['type'] == 'answer'
            assert runtime.calls == [('test-grant',{'type':'offer'})]
            for path in ('/rtc','/cdp','/shell','/files/download/id'):
                response = await client.get(origin+path)
                assert response.status == 404
            response = await client.get(origin+'/rtc/public/files/download/id',headers={'Authorization':'Bearer unrelated'})
            assert response.status == 403
            runtime.cdp._socket.closed = True
            response = await client.get(origin+'/health')
            assert response.status == 503 and (await response.json())['ready'] is False
    finally:
        await runner.cleanup()

def test_history_cannot_open_profile_host_files_or_browser_settings():
    packet = InputPacket(InputAuthority('session','lease',1,1),InputKind.HISTORY_BACK,Channel.RELIABLE)
    for url in ('file:///etc/passwd','chrome://settings','javascript:alert(1)'):
        with pytest.raises(StreamRefused,match='history_scheme_refused'):
            navigation_calls(packet,{'currentIndex':1,'entries':[{'id':1,'url':url},{'id':2,'url':'https://example.com'}]})
