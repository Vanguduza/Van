"""Native Chromium-to-WebRTC producer with broker-fenced binary owner input.

Media never passes through Trading Core. Authority is polled and expires locally;
input obtains a fresh typed broker authorization immediately before every CDP effect.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import io
import json
import time
import uuid
from dataclasses import dataclass, replace
from fractions import Fraction
from urllib.parse import quote, urlsplit

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame
from PIL import Image

from services.browser_control_agent.cdp import CdpUnavailable
from services.browser_stream_host.broker_client import BrokerRefused
from services.browser_stream_host.input_router import CdpInputRouter, InputRouterRefused, Viewport
from van_gateway.browser.flood_bounds import InputRateLimiter
from van_gateway.browser.input_protocol import Channel, InputKind, InputProtocolError, PointerStateMachine, decode
from van_gateway.browser.stream_grants import StreamGrantError

MAX_INPUT_BYTES = 16_384
MAX_SDP_BYTES = 262_144
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
MAX_SESSIONS = 4
MAX_INPUT_QUEUE = 128


class StreamRefused(Exception):
    pass


def validate_offer(body):
    keys = {'protocol', 'session_id', 'control_generation', 'viewport_revision', 'width', 'height', 'sdp', 'type', 'data_channels'}
    if not isinstance(body, dict) or set(body) != keys or body.get('protocol') != 1:
        raise StreamRefused('stream_offer_invalid')
    if body.get('type') != 'offer' or body.get('data_channels') != ['input-fast', 'input-reliable']:
        raise StreamRefused('stream_offer_contract_mismatch')
    if not isinstance(body.get('session_id'), str) or not 1 <= len(body['session_id']) <= 128:
        raise StreamRefused('stream_offer_session_invalid')
    if not isinstance(body.get('sdp'), str) or not 1 <= len(body['sdp'].encode()) <= MAX_SDP_BYTES:
        raise StreamRefused('stream_offer_sdp_invalid')
    for key in ('control_generation', 'viewport_revision', 'width', 'height'):
        if isinstance(body.get(key), bool) or not isinstance(body.get(key), int) or body[key] < 1:
            raise StreamRefused('stream_offer_binding_invalid')
    if body['width'] > 2400 or body['height'] > 2400:
        raise StreamRefused('stream_offer_viewport_too_large')
    return body


def check_authority(authority, *, expected_session=None):
    now = int(time.time() * 1000)
    if not isinstance(authority, dict):
        raise StreamRefused('stream_authority_invalid')
    if expected_session is not None and authority.get('session_id', expected_session) != expected_session:
        raise StreamRefused('stream_authority_session_changed')
    for key in ('profile_expires_at_ms', 'expires_at_ms'):
        value = authority.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= now:
            raise StreamRefused('stream_authority_expired')
    if authority.get('state') in {'FAILED', 'TERMINATED', 'TERMINATING', 'SUSPENDED'}:
        raise StreamRefused('stream_session_not_live')
    viewport = authority.get('viewport')
    if not isinstance(viewport, dict):
        raise StreamRefused('stream_viewport_missing')
    for key in ('width', 'height', 'revision'):
        value = viewport.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= (2400 if key != 'revision' else 0xffffffff):
            raise StreamRefused('stream_viewport_invalid')
    return authority


def navigation_calls(packet, history=None):
    kind = packet.kind
    if kind in {InputKind.NAVIGATE, InputKind.SEARCH}:
        url = packet.text if kind == InputKind.NAVIGATE else 'https://www.google.com/search?q=' + quote(packet.text, safe='')
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise StreamRefused('stream_navigation_url_refused')
        return [('Page.navigate', {'url': url})]
    if kind in {InputKind.HISTORY_BACK, InputKind.HISTORY_FORWARD}:
        if history is None:
            return [('Page.getNavigationHistory', {})]
        delta = -1 if kind == InputKind.HISTORY_BACK else 1
        index = history.get('currentIndex', -1) + delta
        entries = history.get('entries', [])
        if index < 0 or index >= len(entries):
            return []
        destination = entries[index].get('url', '')
        if destination != 'about:blank' and urlsplit(destination).scheme not in {'http', 'https'}:
            raise StreamRefused('stream_history_scheme_refused')
        return [('Page.navigateToHistoryEntry', {'entryId': entries[index]['id']})]
    if kind == InputKind.RELOAD:
        return [('Page.reload', {'ignoreCache': False})]
    if kind == InputKind.STOP_LOADING:
        return [('Page.stopLoading', {})]
    raise StreamRefused('stream_navigation_kind_invalid')


class ChromiumVideoTrack(VideoStreamTrack):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self._started = time.monotonic()
        self._next_at = self._started
        self.sequence = 0

    async def recv(self):
        session = self.session
        if session.closed:
            raise MediaStreamError
        await asyncio.sleep(max(0, self._next_at - time.monotonic()))
        self._next_at = time.monotonic() + 1 / session.fps
        try:
            authority = check_authority(session.authority, expected_session=session.session_id)
            session.check_binding(authority)
            viewport = authority['viewport']
            result = await session.cdp.send(session.target_id, 'Page.captureScreenshot', {
                'format': 'jpeg', 'quality': 80, 'fromSurface': True,
                'captureBeyondViewport': False,
                'clip': {'x': 0, 'y': 0, 'width': viewport['width'], 'height': viewport['height'], 'scale': 1},
            })
            raw = base64.b64decode(result.get('data', ''), validate=True)
            if not raw or len(raw) > MAX_SCREENSHOT_BYTES:
                raise StreamRefused('stream_capture_size_invalid')
            image = Image.open(io.BytesIO(raw))
            if image.size != (viewport['width'], viewport['height']):
                raise StreamRefused('stream_capture_geometry_mismatch')
            # Bound decompression before converting; source dimensions are already exact.
            image.load()
            frame = VideoFrame.from_image(image.convert('RGB'))
            frame.pts = max(1, int((time.monotonic() - self._started) * 90_000))
            frame.time_base = Fraction(1, 90_000)
            self.sequence += 1
            marker = {
                'frame_sequence': self.sequence, 'frame_timestamp_us': int(frame.pts * 1_000_000 / 90_000),
                'width': frame.width, 'height': frame.height, 'active_target_id': session.target_id,
            }
            # Capture is an actual observed image; INTERACTIVE remains distinct from task
            # completion and from Android's independent decoded-frame acknowledgement.
            if self.sequence == 1:
                await session.broker.observe(
                    session.producer_id, 'first_frame', viewport_revision=viewport['revision'],
                    frame_sequence=self.sequence, media_epoch=session.producer_id,
                    width=frame.width, height=frame.height, codec=session.codec, transport='WEBRTC',
                )
                session.first_frame = True
                session.emit('viewport.frame', **marker)
            return frame
        except (BrokerRefused, CdpUnavailable, StreamRefused, ValueError, OSError, KeyError) as exc:
            asyncio.create_task(session.close('stream_capture_failed'))
            raise MediaStreamError from exc


@dataclass
class StreamRuntime:
    cdp: object
    broker: object
    verifier: object
    profile_alias: str
    ice_servers: tuple = ()
    quarantine_root: str | None = None
    clipboard_enabled: bool = True
    sessions: dict = None

    def __post_init__(self):
        self.sessions = {}
        self._allocation = asyncio.Lock()

    async def exchange(self, token, offer):
        offer = validate_offer(offer)
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise StreamRefused('stream_bearer_invalid')
        try:
            claims = self.verifier.verify(token)
        except (StreamGrantError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise StreamRefused('stream_grant_invalid') from exc
        required = {'webrtc.signal', 'browser.view', 'browser.owner_input'}
        if claims.get('session_id') != offer['session_id'] or claims.get('profile_alias') != self.profile_alias:
            raise StreamRefused('stream_grant_binding_mismatch')
        if not required.issubset(set(claims.get('scope') or [])):
            raise StreamRefused('stream_grant_scope_missing')
        if offer['width'] > claims.get('max_width', 0) or offer['height'] > claims.get('max_height', 0):
            raise StreamRefused('stream_grant_viewport_exceeded')
        async with self._allocation:
            if len(self.sessions) >= MAX_SESSIONS:
                raise StreamRefused('stream_session_limit')
            producer_id = 'prod_' + uuid.uuid4().hex
            redemption = await self.broker.redeem(token, producer_id)
            if (redemption.get('producer_session_id') != producer_id or redemption.get('session_id') != offer['session_id']
                    or redemption.get('profile_alias') != self.profile_alias or redemption.get('grant_id') != claims.get('grant_id')
                    or redemption.get('owner_device_id') != claims.get('device_id')):
                raise StreamRefused('stream_redemption_binding_mismatch')
            authority = check_authority(redemption.get('authority'), expected_session=offer['session_id'])
            viewport = authority['viewport']
            if any(offer[k] != viewport[k2] for k,k2 in [('width','width'),('height','height'),('viewport_revision','revision')]) or offer['control_generation'] != authority.get('control_generation'):
                raise StreamRefused('stream_offer_current_binding_mismatch')
            old = [session for session in self.sessions.values() if session.session_id == offer['session_id']]
            for session in old:
                await session.close('stream_peer_replaced', report=False)
            session = StreamPeer(self, producer_id, redemption, claims)
            self.sessions[producer_id] = session
            try:
                return await asyncio.wait_for(session.start(offer), 30)
            except BaseException:
                await session.close('stream_negotiation_failed')
                raise

    async def close(self):
        for session in list(self.sessions.values()):
            await session.close('stream_runtime_shutdown', report=False)


class StreamPeer:
    def __init__(self, runtime, producer_id, redemption, claims):
        self.runtime = runtime
        self.cdp = runtime.cdp
        self.broker = runtime.broker
        self.producer_id = producer_id
        self.session_id = redemption['session_id']
        self.owner_device_id = redemption['owner_device_id']
        self.authority = redemption['authority']
        self.viewport = dict(self.authority['viewport'])
        self.control_generation = self.authority['control_generation']
        self.fps = min(30, max(1, int(claims.get('max_fps', 30))))
        self.closed = False
        self.first_frame = False
        self.target_id = ''
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[RTCIceServer(**entry) for entry in runtime.ice_servers]))
        self.metadata = None
        self.event_seq = 0
        self.pending_metadata = []
        self.first_frame_metadata = None
        self.channels = set()
        self.pointer = PointerStateMachine(self.session_id)
        self.router = CdpInputRouter(viewport=Viewport(self.viewport['width'], self.viewport['height'], self.viewport['revision']), control_generation=self.control_generation)
        self.rate = InputRateLimiter()
        self.queue = asyncio.Queue(maxsize=MAX_INPUT_QUEUE)
        self.last_reliable_seq = -1
        self.last_pointer_packets = {}
        self.tasks = []
        self.track = None
        self.codec = 'UNKNOWN'
        self.files = None
        self.loading = {}
        self.security = {}
        if hasattr(self.cdp, 'add_listener'):
            self.cdp.add_listener(self.on_cdp_event)

    def on_cdp_event(self, event):
        if self.files is not None:
            self.files.event(event)
        target_id = next((key for key, value in self.cdp._sessions.items() if value == event.get('sessionId')), None)
        if target_id is None:
            return
        if event.get('method') == 'Page.frameStartedLoading':
            self.loading[target_id] = True
        elif event.get('method') == 'Page.frameStoppedLoading':
            self.loading[target_id] = False
        elif event.get('method') == 'Security.visibleSecurityStateChanged':
            state = event.get('params', {}).get('visibleSecurityState', {}).get('securityState', 'unknown')
            self.security[target_id] = state if state in {'unknown', 'neutral', 'insecure', 'secure', 'info', 'insecure-broken'} else 'unknown'

    def check_binding(self, authority):
        if authority['viewport'] != self.viewport or authority['control_generation'] != self.control_generation:
            raise StreamRefused('stream_peer_binding_changed_reconnect_required')

    async def start(self, offer):
        targets = await self.cdp.targets()
        requested = self.authority.get('active_target_id')
        target = next((entry for entry in targets if entry['targetId'] == requested), None) if requested else (targets[0] if targets else None)
        if target is None:
            raise StreamRefused('stream_active_page_unavailable')
        self.target_id = target['targetId']
        await self.cdp.send(self.target_id, 'Emulation.setDeviceMetricsOverride', {
            'width': self.viewport['width'], 'height': self.viewport['height'], 'deviceScaleFactor': 1, 'mobile': False,
        })
        await self.broker.observe(self.producer_id, 'target', target_id=self.target_id, url=target.get('url', ''), title=target.get('title', '')[:512])
        if self.runtime.quarantine_root:
            from services.browser_stream_host.files import FilePlane
            self.files = FilePlane(self, self.runtime.quarantine_root, clipboard_enabled=self.runtime.clipboard_enabled)
            await self.files.start()
        state = self.authority['state']
        if state == 'AUTHORIZED':
            await self.broker.observe(self.producer_id, 'allocated')
            state = 'ALLOCATING'
        if state == 'ALLOCATING':
            await self.broker.observe(self.producer_id, 'signaling')
            state = 'SIGNALING'
        if state in {'INTERACTIVE', 'AGENT_CONTROLLED'}:
            await self.broker.observe(self.producer_id, 'reconnecting')
        self.metadata = self.pc.createDataChannel('browser-state', ordered=True)
        self.metadata.on('open', self.flush_metadata)

        @self.pc.on('datachannel')
        def on_channel(channel):
            expected = {'input-fast': Channel.FAST, 'input-reliable': Channel.RELIABLE}
            kind = expected.get(channel.label)
            if kind is None or channel.label in self.channels or channel.ordered != (kind == Channel.RELIABLE):
                channel.close()
                return
            if kind == Channel.FAST and channel.maxRetransmits != 0:
                channel.close()
                return
            self.channels.add(channel.label)

            @channel.on('message')
            def on_message(message):
                if self.closed:
                    return
                if not isinstance(message, bytes) or len(message) > MAX_INPUT_BYTES:
                    self.emit('input.refused', reason='stream_input_not_bounded_binary')
                    return
                if self.queue.full():
                    self.emit('input.refused', reason='stream_input_queue_full')
                    return
                self.queue.put_nowait((kind, message))

        @self.pc.on('connectionstatechange')
        async def on_connection():
            if self.pc.connectionState in {'failed', 'closed'}:
                await self.close('stream_connection_ended')

        self.track = ChromiumVideoTrack(self)
        self.pc.addTrack(self.track)
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=offer['sdp'], type='offer'))
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)  # aiortc completes bounded ICE gathering
        from aiortc.sdp import SessionDescription
        negotiated = SessionDescription.parse(self.pc.localDescription.sdp)
        video = next((entry for entry in negotiated.media if entry.kind == 'video'), None)
        if video is None or not video.rtp.codecs:
            raise StreamRefused('stream_video_codec_unavailable')
        self.codec = video.rtp.codecs[0].mimeType.split('/', 1)[-1].upper()
        if state == 'SIGNALING':
            await self.broker.observe(self.producer_id, 'connecting')
        current = check_authority(await self.broker.authority(self.producer_id), expected_session=self.session_id)
        self.check_binding(current)
        self.authority = current
        self.tasks = [asyncio.create_task(self._input_loop()), asyncio.create_task(self._watch())]
        return {
            'protocol': 1, 'session_id': self.session_id,
            'control_generation': self.control_generation, 'viewport_revision': self.viewport['revision'],
            'width': self.viewport['width'], 'height': self.viewport['height'],
            'media_epoch': self.producer_id, 'sdp': self.pc.localDescription.sdp, 'type': 'answer',
            'authenticated_principal_kind': 'STREAM_GRANT_BEARER',
        }

    def emit(self, event_type, **fields):
        self.event_seq += 1
        message = {
            'protocol': 1, 'session_id': self.session_id, 'media_epoch': self.producer_id,
            'control_generation': self.control_generation, 'viewport_revision': self.viewport['revision'],
            'width': self.viewport['width'], 'height': self.viewport['height'],
            'event_seq': self.event_seq, 'event_type': event_type, **fields,
        }
        encoded = json.dumps(message, separators=(',', ':'))
        if len(encoded.encode()) > 65536:
            return
        if self.metadata is not None and self.metadata.readyState == 'open' and self.metadata.bufferedAmount < 262144:
            self.metadata.send(encoded)
        else:
            # Keep bounded state while SCTP opens; preserve first frame marker but never
            # accumulate one marker per frame indefinitely.
            if event_type == 'viewport.frame':
                self.first_frame_metadata = encoded
                return
            self.pending_metadata.append(encoded)
            self.pending_metadata = self.pending_metadata[-8:]

    def flush_metadata(self):
        pending, self.pending_metadata = self.pending_metadata, []
        if self.first_frame_metadata is not None:
            pending.append(self.first_frame_metadata)
            self.first_frame_metadata = None
        # The retained marker predates later state records; preserve monotonic event_seq
        # on the wire so Android's replay fence can still admit it.
        pending.sort(key=lambda encoded: json.loads(encoded)['event_seq'])
        for message in pending:
            if self.metadata.readyState == 'open':
                self.metadata.send(message)

    async def _authorize(self, packet):
        if packet.authority.session_id != self.session_id:
            raise StreamRefused('stream_input_session_mismatch')
        authority = check_authority(await self.broker.authorize_input(self.producer_id, packet.authority), expected_session=self.session_id)
        self.check_binding(authority)
        self.authority = authority

    async def _dispatch(self, packet):
        await self._authorize(packet)
        if packet.kind.is_navigation:
            calls = navigation_calls(packet)
            if packet.kind in {InputKind.HISTORY_BACK, InputKind.HISTORY_FORWARD}:
                history = await self.cdp.send(self.target_id, calls[0][0], calls[0][1])
                calls = navigation_calls(packet, history)
        else:
            calls = [(call.method, call.params) for call in self.router.route(packet)]
        for method, params in calls:
            # A pair of mouse calls is two effects. Do not reuse authorization across an
            # awaited network operation where ownership could have changed.
            await self._authorize(packet)
            await self.cdp.send(self.target_id, method, params)

    async def accept_input(self, channel, message):
        packet = decode(message)
        if packet.channel != channel or (packet.kind.is_navigation and channel != Channel.RELIABLE):
            raise StreamRefused('stream_input_channel_mismatch')
        if channel == Channel.FAST and packet.kind not in {InputKind.POINTER_DOWN, InputKind.POINTER_MOVE, InputKind.POINTER_UP, InputKind.POINTER_CANCEL}:
            raise StreamRefused('stream_input_reliable_kind_on_fast_channel')
        if len(packet.text.encode()) > 8192 or packet.pointer_id > 15:
            raise StreamRefused('stream_input_fields_too_large')
        if channel == Channel.RELIABLE:
            if packet.reliable_seq <= self.last_reliable_seq:
                raise StreamRefused('stream_input_reliable_replay')
            self.last_reliable_seq = packet.reliable_seq
        now = int(time.time() * 1000)
        if not self.rate.admit(self.session_id, now):
            raise StreamRefused('stream_input_rate_limit')
        await self._authorize(packet)
        if len(self.pointer._seen_edges) >= 4096:
            if self.pointer.open_pointers():
                raise StreamRefused('stream_gesture_history_limit')
            self.pointer = PointerStateMachine(self.session_id)
        self.last_pointer_packets[packet.pointer_id] = packet
        accepted = self.pointer.offer(packet, now_ms=now)
        for output in accepted.packets:
            if output.authority.control_lease_id == '':
                output = replace(output, authority=packet.authority, pointer_id=packet.pointer_id, x=packet.x, y=packet.y)
            await self._dispatch(output)
        for state in self.pointer._pointers.values():
            state.pending = state.pending[-8:]

    async def _input_loop(self):
        while not self.closed:
            channel, message = await self.queue.get()
            try:
                await self.accept_input(channel, message)
            except (InputProtocolError, InputRouterRefused, StreamRefused, BrokerRefused, CdpUnavailable, ValueError, KeyError):
                self.emit('input.refused', reason='stream_input_authority_or_protocol_refused')
            finally:
                self.queue.task_done()

    async def _watch(self):
        last_tabs = ''
        try:
            while not self.closed:
                await asyncio.sleep(0.5)
                current = check_authority(await self.broker.authority(self.producer_id), expected_session=self.session_id)
                self.check_binding(current)
                self.authority = current
                if self.files is not None:
                    await self.files.apply_deletions(current.get('download_deletion_requests', []))
                # Server-side orphan-gesture cleanup uses the same current authority as
                # normal input; expiry never opens an unleased release primitive.
                before = {state.gesture_id: pointer_id for pointer_id, state in self.pointer._pointers.items()}
                for cancel in self.pointer.sweep(now_ms=int(time.time() * 1000)):
                    pointer_id = before.get(cancel.gesture_id, 0)
                    previous = self.last_pointer_packets.get(pointer_id)
                    if previous is not None:
                        await self._dispatch(replace(cancel, authority=previous.authority, pointer_id=pointer_id, x=previous.x, y=previous.y))
                targets = await self.cdp.targets()
                if not any(target['targetId'] == self.target_id for target in targets):
                    raise StreamRefused('stream_active_target_closed')
                history = await self.cdp.send(self.target_id, 'Page.getNavigationHistory', {})
                tabs = []
                for target in targets[:64]:
                    url = target.get('url', '')[:4096]
                    is_active = target['targetId'] == self.target_id
                    tabs.append({
                        'target_id': target['targetId'], 'title': target.get('title', '')[:512],
                        'url': url, 'url_digest': 'sha256:' + hashlib.sha256(url.encode()).hexdigest(),
                        'loading': self.loading.get(target['targetId'], False),
                        'can_go_back': is_active and history.get('currentIndex', 0) > 0,
                        'can_go_forward': is_active and history.get('currentIndex', 0) + 1 < len(history.get('entries', [])),
                        'security_state': self.security.get(target['targetId'], 'unknown'),
                    })
                tab_key = json.dumps(tabs, sort_keys=True)
                if tab_key != last_tabs:
                    last_tabs = tab_key
                    active = next(target for target in targets if target['targetId'] == self.target_id)
                    await self.broker.observe(self.producer_id, 'target', target_id=self.target_id, url=active.get('url', ''), title=active.get('title', '')[:512])
                    self.emit('tab.snapshot', tabs=tabs, active_target_id=self.target_id)
                self.emit('session.state', state=current['state'])
        except (BrokerRefused, StreamRefused, CdpUnavailable, ValueError, KeyError):
            await self.close('stream_current_authority_lost')

    async def close(self, reason, *, report=True):
        if self.closed:
            return
        self.closed = True
        if hasattr(self.cdp, 'remove_listener'):
            self.cdp.remove_listener(self.on_cdp_event)
        self.emit('session.state', state='RECONNECTING', reason=reason)
        current_task = asyncio.current_task()
        for task in self.tasks:
            if task is not current_task:
                task.cancel()
        if self.track is not None:
            self.track.stop()
        if self.files is not None:
            await self.files.close()
        await self.pc.close()
        self.rate.forget(self.session_id)
        self.runtime.sessions.pop(self.producer_id, None)
        if report:
            try:
                await self.broker.observe(self.producer_id, 'reconnecting', reason=reason)
            except (BrokerRefused, OSError, asyncio.TimeoutError):
                pass
