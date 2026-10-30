"""Bounded multiplexed CDP transport. Every destination is literal loopback.

Target IDs are Chromium page IDs, not flattened CDP session IDs. Commands are never
retried after connection loss: replaying input could apply an action twice.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

LOOPBACK = ipaddress.ip_address('127.0.0.1')
MAX_MESSAGE_BYTES = 12 * 1024 * 1024
MAX_PENDING = 64


class CdpUnavailable(Exception):
    pass


@dataclass
class LoopbackCdp:
    websocket_url: str
    timeout_seconds: float = 10.0
    _next_id: int = 0
    _client: Any = field(default=None, init=False, repr=False)
    _socket: Any = field(default=None, init=False, repr=False)
    _reader: Any = field(default=None, init=False, repr=False)
    _pending: dict = field(default_factory=dict, init=False, repr=False)
    _sessions: dict = field(default_factory=dict, init=False, repr=False)
    _connect_lock: Any = field(default_factory=asyncio.Lock, init=False, repr=False)
    _attach_lock: Any = field(default_factory=asyncio.Lock, init=False, repr=False)
    _listeners: list = field(default_factory=list, init=False, repr=False)
    _downloads: dict = field(default_factory=dict, init=False, repr=False)
    _navigation: dict = field(default_factory=dict, init=False, repr=False)
    events: Any = field(default_factory=lambda: asyncio.Queue(maxsize=128), init=False, repr=False)

    def __post_init__(self) -> None:
        self._assert_loopback(self.websocket_url)

    @staticmethod
    def _assert_loopback(url: str) -> None:
        try:
            parsed = urlsplit(url)
            address = ipaddress.ip_address(parsed.hostname or '')
            if parsed.scheme not in {'ws', 'wss', 'http', 'https'}:
                raise ValueError('scheme')
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('components')
            if parsed.port is None or not 1 <= parsed.port <= 65535:
                raise ValueError('port')
        except ValueError as exc:
            raise CdpUnavailable('cdp_endpoint_must_be_a_loopback_literal') from exc
        if not address.is_loopback:
            raise CdpUnavailable('cdp_endpoint_not_loopback')

    async def connect(self) -> None:
        async with self._connect_lock:
            if self._socket is not None and not self._socket.closed:
                return
            import aiohttp
            self._client = aiohttp.ClientSession(
                trust_env=False, timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            )
            endpoint = self.websocket_url
            try:
                parsed = urlsplit(endpoint)
                if parsed.path in {'', '/'}:
                    scheme = 'https' if parsed.scheme in {'https', 'wss'} else 'http'
                    discover = f'{scheme}://{parsed.netloc}/json/version'
                    async with self._client.get(discover, allow_redirects=False) as response:
                        if response.status != 200:
                            raise CdpUnavailable('cdp_discovery_failed')
                        raw = await response.content.read(65537)
                        if len(raw) > 65536:
                            raise CdpUnavailable('cdp_discovery_too_large')
                        endpoint = json.loads(raw)['webSocketDebuggerUrl']
                    self._assert_loopback(endpoint)
                    found = urlsplit(endpoint)
                    if found.hostname != parsed.hostname or found.port != parsed.port:
                        raise CdpUnavailable('cdp_discovery_endpoint_changed')
                self._socket = await self._client.ws_connect(
                    endpoint, max_msg_size=MAX_MESSAGE_BYTES, heartbeat=15,
                    origin=f'http://{parsed.netloc}',
                )
                self._sessions.clear()
                self._navigation.clear()
                self._reader = asyncio.create_task(self._receive())
            except Exception as exc:
                await self._client.close()
                self._client = None
                if isinstance(exc, CdpUnavailable):
                    raise
                raise CdpUnavailable('cdp_connection_unavailable') from exc

    async def _receive(self) -> None:
        try:
            async for message in self._socket:
                if message.type.name != 'TEXT':
                    if message.type.name in {'CLOSE', 'CLOSED', 'ERROR'}:
                        break
                    continue
                payload = json.loads(message.data)
                if not isinstance(payload, dict):
                    raise CdpUnavailable('cdp_invalid_reply')
                message_id = payload.get('id')
                if message_id is not None:
                    future = self._pending.pop(message_id, None)
                    if future is not None and not future.done():
                        if 'error' in payload:
                            future.set_exception(CdpUnavailable('cdp_command_refused'))
                        else:
                            future.set_result(payload.get('result', {}))
                elif 'method' in payload:
                    if payload['method'] == 'Page.frameNavigated':
                        target = next((key for key, value in self._sessions.items() if value == payload.get('sessionId')), None)
                        frame = payload.get('params', {}).get('frame', {})
                        if target and not frame.get('parentId'):
                            self._navigation[target] = {'loaderId': frame.get('loaderId'), 'url': frame.get('url')}
                    if payload['method'] == 'Target.detachedFromTarget':
                        detached = payload.get('params', {}).get('sessionId')
                        self._sessions = {k: v for k, v in self._sessions.items() if v != detached}
                    if not self.events.full():
                        self.events.put_nowait(payload)
                    if payload['method'] in {'Page.downloadWillBegin', 'Browser.downloadWillBegin'}:
                        params = payload.get('params', {})
                        if len(self._downloads) < 64:
                            self._downloads[params.get('guid', '')] = {
                                'guid': params.get('guid'), 'suggested_filename': params.get('suggestedFilename', '')[:256],
                                'url': params.get('url', '')[:4096], 'state': 'STARTED',
                                'session_id': payload.get('sessionId'),
                            }
                    elif payload['method'] in {'Page.downloadProgress', 'Browser.downloadProgress'}:
                        params = payload.get('params', {})
                        if params.get('guid') in self._downloads:
                            self._downloads[params['guid']]['state'] = params.get('state', 'unknown')
                    for callback in tuple(self._listeners):
                        callback(payload)
        except (ValueError, TypeError, KeyError, CdpUnavailable):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(CdpUnavailable('cdp_connection_lost'))
            self._pending.clear()
            self._sessions.clear()
            self._navigation.clear()
            if self._socket is not None and not self._socket.closed:
                await self._socket.close()

    async def _command(self, method: str, params: dict, session_id: str | None = None) -> dict:
        await self.connect()
        if len(self._pending) >= MAX_PENDING:
            raise CdpUnavailable('cdp_concurrency_limit')
        self._next_id += 1
        command_id = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[command_id] = future
        envelope = {'id': command_id, 'method': method, 'params': params}
        if session_id is not None:
            envelope['sessionId'] = session_id
        try:
            await self._socket.send_json(envelope)
            return await asyncio.wait_for(future, self.timeout_seconds)
        except (asyncio.TimeoutError, OSError) as exc:
            raise CdpUnavailable('cdp_command_unavailable') from exc
        finally:
            self._pending.pop(command_id, None)

    async def targets(self) -> list[dict[str, Any]]:
        result = await self._command('Target.getTargets', {})
        return [info for info in result.get('targetInfos', []) if info.get('type') == 'page'][:64]

    async def attach(self, target_id: str) -> str:
        async with self._attach_lock:
            if target_id in self._sessions:
                return self._sessions[target_id]
            targets = await self.targets()
            if not any(target.get('targetId') == target_id for target in targets):
                raise CdpUnavailable('cdp_page_target_unknown')
            result = await self._command('Target.attachToTarget', {'targetId': target_id, 'flatten': True})
            session = result.get('sessionId')
            if not isinstance(session, str) or not session:
                raise CdpUnavailable('cdp_attach_invalid_reply')
            self._sessions[target_id] = session
            await self._command('Page.enable', {}, session)
            await self._command('Security.enable', {}, session)
            return session

    def add_listener(self, callback):
        if len(self._listeners) >= 64:
            raise CdpUnavailable('cdp_event_listener_limit')
        self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def observed_downloads(self, target_id):
        session = self._sessions.get(target_id)
        # Browser-global events without a page session cannot be attributed to a task.
        return [dict(item) for item in self._downloads.values() if session and item.get('session_id') == session]

    async def wait_navigation(self, target_id, result, requested_url, allowed_domains):
        from van_gateway.browser.agent_grant import domain_allowed
        deadline = asyncio.get_running_loop().time() + 10
        loader = result.get('loaderId')
        while asyncio.get_running_loop().time() < deadline:
            history = await self.send(target_id, 'Page.getNavigationHistory', {})
            index = history.get('currentIndex', -1)
            entries = history.get('entries', [])
            if type(index) is int and 0 <= index < len(entries):
                current_url = entries[index].get('url', '')
                committed = self._navigation.get(target_id, {}).get('loaderId') == loader if loader else current_url == requested_url
                if committed:
                    if not domain_allowed(current_url, allowed_domains):
                        raise CdpUnavailable('cdp_navigation_redirect_outside_task_domain')
                    return {'url': current_url, 'history': entries, 'current': index}
            await asyncio.sleep(0.05)
        raise CdpUnavailable('cdp_navigation_commit_timeout')

    async def send(self, target_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == 'Target.attachToTarget':
            return {'sessionId': await self.attach(target_id)}
        session = await self.attach(target_id)
        return await self._command(method, params, session)

    async def close(self) -> None:
        if self._socket is not None:
            await self._socket.close()
        if self._reader is not None:
            await self._reader
        if self._client is not None:
            await self._client.close()
        self._socket = self._client = self._reader = None

    def _envelope(self, target_id: str, method: str, params: dict[str, Any]) -> str:
        self._next_id += 1
        return json.dumps({'id': self._next_id, 'method': method, 'params': params, 'sessionId': target_id})


async def assert_no_public_cdp(port: int, interfaces: list[str]) -> list[str]:
    exposed = []
    for interface in interfaces:
        if ipaddress.ip_address(interface).is_loopback:
            continue
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(interface, port), timeout=2.0)
            writer.close()
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError):
            continue
        exposed.append(interface)
    return exposed
