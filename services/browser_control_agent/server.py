"""Rev 1.5 §13.3 — the mTLS listener, and where a caller's name comes from.

One idea in this file matters more than the rest: **the caller's identity is the common
name in the verified client certificate, and it is read from the TLS layer, never from the
request.** A name in a JSON body is a field any caller can write. The agent authorises
against identities, so it has to get them from something the caller cannot choose.

The bind address is the other one. `require_private_bind` refuses `0.0.0.0` and refuses the
host's public address, because this process is the only bridge to a Chromium holding the
owner's logged-in sessions, and the difference between a private listener and a public one
is one character in a config file.
"""

from __future__ import annotations

import ipaddress
import json
import os
import ssl
import asyncio
import argparse
import math
from dataclasses import dataclass


class BindRefused(Exception):
    pass


def require_private_bind(address: str, *, public_addresses: frozenset[str] = frozenset()) -> str:
    """Refuse anything that is not a specific private address.

    Wildcards first because they are the common mistake and the worst outcome: `0.0.0.0`
    in a config file reads as "listen" and means "listen on the internet".
    """
    if address in {"", "0.0.0.0", "::", "*"}:
        raise BindRefused("control_agent_bind_is_a_wildcard")
    if address in public_addresses:
        raise BindRefused("control_agent_bind_is_the_public_address")
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise BindRefused("control_agent_bind_must_be_an_ip_literal") from exc
    if parsed.is_loopback:
        # Loopback would be safe and also useless: Trading Core is another host.
        raise BindRefused("control_agent_bind_is_loopback_and_unreachable_from_trading_core")
    if not parsed.is_private:
        raise BindRefused("control_agent_bind_is_not_private")
    return address


def build_ssl_context(*, ca_file: str, cert_file: str, key_file: str) -> ssl.SSLContext:
    """A server context that will not complete a handshake without a client certificate.

    `CERT_REQUIRED` plus a `ca_file` that contains only the private control CA is the whole
    mechanism. Loading the system trust store here would mean any publicly-issued
    certificate authenticated a caller, which is the failure `qualify.sh` tests for with a
    deliberately foreign certificate carrying a *correct* common name.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=ca_file)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    # Deliberately not calling load_default_certs(): see above.
    return context


def common_name_of(peer_certificate: dict | None) -> str:
    """The caller's identity, from the certificate the TLS layer has already verified.

    Returns "" when there is none. A caller with no certificate never gets here — the
    handshake fails first — so an empty result means the context was built wrongly, and the
    agent's own `authorize` will refuse it as an unknown caller rather than proceed.
    """
    if not peer_certificate:
        return ""
    for field in peer_certificate.get("subject", ()):  # a tuple of tuples
        for key, value in field:
            if key == "commonName":
                return value
    return ""


@dataclass(frozen=True)
class ServerConfig:
    bind: str
    port: int
    ca_file: str
    cert_file: str
    key_file: str
    cdp_websocket_url: str

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> "ServerConfig":
        env = os.environ if environment is None else environment
        pki = env.get("VAN_BROWSER_PKI_DIR", "/opt/van-browser-stream/pki")
        return cls(
            bind=require_private_bind(env.get("VAN_BROWSER_CONTROL_BIND", "")),
            port=int(env.get("VAN_BROWSER_CONTROL_PORT", "9443")),
            ca_file=f"{pki}/ca.crt",
            cert_file=f"{pki}/agent.crt",
            key_file=f"{pki}/agent.key",
            cdp_websocket_url=env.get(
                "VAN_BROWSER_CDP_WEBSOCKET",
                f"ws://127.0.0.1:{env.get('VAN_BROWSER_CDP_PORT', '9222')}",
            ),
        )


def validate_params(call, authority=None):
    """Narrow operation parameters; wire references are never task authority."""
    from services.browser_control_agent.authority import Operation
    params = call.params
    if call.operation == Operation.NAVIGATE:
        if set(params) != {'url'} or not isinstance(params['url'], str) or not 1 <= len(params['url']) <= 8192:
            raise ValueError('control_navigate_params_invalid')
    elif call.operation == Operation.DISPATCH_INPUT:
        allowed = {'type', 'x', 'y', 'button', 'buttons', 'clickCount', 'deltaX', 'deltaY', 'modifiers', 'timestamp'}
        if set(params) - allowed or params.get('type') not in {'mouseMoved', 'mousePressed', 'mouseReleased', 'mouseWheel'}:
            raise ValueError('control_input_params_invalid')
        for key in ('x', 'y'):
            if isinstance(params.get(key), bool) or not isinstance(params.get(key), (int, float)) or not math.isfinite(params[key]) or params[key] < 0:
                raise ValueError('control_input_coordinates_invalid')
        if authority:
            viewport = authority['viewport']
            if params['x'] >= viewport['width'] or params['y'] >= viewport['height']:
                raise ValueError('control_input_outside_viewport')
        for key in ('deltaX', 'deltaY', 'timestamp'):
            if key in params and (isinstance(params[key], bool) or not isinstance(params[key], (int, float)) or not math.isfinite(params[key]) or abs(params[key]) > (1e11 if key == 'timestamp' else 100000)):
                raise ValueError('control_input_params_invalid')
        for key in ('buttons', 'clickCount', 'modifiers'):
            if key in params and (type(params[key]) is not int or not 0 <= params[key] <= 16):
                raise ValueError('control_input_params_invalid')
        if 'button' in params and params['button'] not in {'left', 'right', 'middle', 'none'}:
            raise ValueError('control_input_button_invalid')
    elif call.operation == Operation.QUERY_DOM:
        if set(params) != {'selector'} or not isinstance(params['selector'], str) or not 1 <= len(params['selector']) <= 2048:
            raise ValueError('control_selector_invalid')
    elif call.operation in {Operation.CLICK_ELEMENT, Operation.FILL_ELEMENT, Operation.OBSERVE_EFFECT}:
        if set(params) != {'plan_id', 'plan_sha256', 'step_id'} or any(not isinstance(value, str) or not 1 <= len(value) <= 128 for value in params.values()):
            raise ValueError('control_sealed_effect_reference_invalid')
    elif params:
        raise ValueError('control_operation_params_refused')


async def dispatch_message(message, *, caller_common_name, broker, cdp):
    """Read verified TLS identity separately, resolve current authority, then act."""
    from services.browser_control_agent.agent import _HANDLERS
    from services.browser_control_agent.authority import Scope, TaskGrant, Operation
    from services.browser_control_agent.wire import decode_call, encode_result, encode_refusal, WireError
    from services.browser_control_agent.cdp import CdpUnavailable
    from services.browser_stream_host.broker_client import BrokerRefused
    from van_gateway.browser.agent_grant import domain_allowed
    import time
    request_id = ''
    try:
        request_id, call = decode_call(message)
        validate_params(call)
        resolved = await broker.validate_call(caller_common_name, call)
        for key in ('session_id', 'task_id', 'target_id'):
            if resolved.get(key) != getattr(call, key):
                raise ValueError('control_authority_binding_changed')
        if type(resolved.get('deadline_ms')) is not int or resolved['deadline_ms'] <= int(time.time() * 1000):
            raise ValueError('control_task_expired')
        validate_params(call, resolved.get('authority'))
        if call.operation == Operation.NAVIGATE and not domain_allowed(call.params['url'], tuple(resolved.get('allowed_domains', ()))):
            raise ValueError('control_navigation_outside_task_domains')
        if call.operation not in {Operation.NAVIGATE, Operation.ATTACH}:
            # Scope follows the real current page, including redirects. Neither the
            # caller's requested URL nor a broker URL digest proves its present domain.
            history = await cdp.send(call.target_id, 'Page.getNavigationHistory', {})
            entries = history.get('entries', [])
            index = history.get('currentIndex', -1)
            if type(index) is not int or not 0 <= index < len(entries) or not domain_allowed(entries[index].get('url', ''), tuple(resolved.get('allowed_domains', ()))):
                raise ValueError('control_current_page_outside_task_domains')
        # The readonly domain observation can await while the owner preempts control.
        # Debit exactly once, with a new complete fence immediately before the handler.
        authorized = await broker.authorize_call(caller_common_name, call)
        for key in ('session_id', 'task_id', 'target_id', 'scope', 'deadline_ms', 'allowed_domains'):
            if authorized.get(key) != resolved.get(key):
                raise ValueError('control_authority_binding_changed')
        resolved = authorized
        task = TaskGrant(
            task_id=resolved['task_id'], session_id=resolved['session_id'], scope=Scope(resolved['scope']),
            step_budget=resolved['step_budget'], steps_used=resolved['steps_used'],
            allowed_domains=tuple(resolved.get('allowed_domains', ())),
        )
        # The trusted broker has already consumed the durable step. Reconstructing its
        # result is not issuing a local grant and never calls the in-memory test authority.
        if call.operation == Operation.OBSERVE_DOWNLOAD:
            observed = resolved.get('observed_downloads', [])
            if not isinstance(observed, list) or len(observed) > 64:
                raise ValueError('control_download_observation_invalid')
            result = {
                'downloads': observed, 'observation_available': resolved.get('observation_available') is True,
                'complete_snapshot': False, 'observation_source': 'AUTHENTICATED_STREAM_PRODUCER_REPORTS',
                'transfer': 'not_through_this_agent',
            }
        elif call.operation in {Operation.CLICK_ELEMENT, Operation.FILL_ELEMENT, Operation.OBSERVE_EFFECT}:
            from services.browser_control_agent.effects import execute
            async def fence():
                current = await broker.validate_result(caller_common_name, call)
                for key in ('plan_id', 'plan_sha256', 'execution_id', 'planned_step'):
                    if current.get(key) != resolved.get(key):
                        raise ValueError('control_effect_authority_changed')
                # Re-read the current page at each effect boundary; redirects cannot
                # keep a scoped permission merely because the old page was allowed.
                history = await cdp.send(call.target_id, 'Page.getNavigationHistory', {})
                entries, index = history.get('entries', []), history.get('currentIndex', -1)
                if type(index) is not int or not 0 <= index < len(entries) or not domain_allowed(entries[index].get('url', ''), tuple(current.get('allowed_domains', ()))):
                    raise ValueError('control_current_page_outside_task_domains')
            result = await execute(cdp, call, resolved, fence)
        else:
            result = await _HANDLERS[call.operation](cdp, call, task)
        if call.operation == Operation.NAVIGATE:
            await broker.validate_result(caller_common_name, call)
        encoded = encode_result(request_id, result)
        if len(encoded.encode()) > 12 * 1024 * 1024:
            return encode_refusal(request_id, 'control_response_too_large')
        return encoded
    except (WireError, BrokerRefused, CdpUnavailable, ValueError, TypeError, KeyError):
        if not request_id:
            raise
        return encode_refusal(request_id, 'control_authority_or_operation_refused')


async def handle_client(reader, writer, *, broker, cdp):
    from services.browser_control_agent.wire import WireError, frame
    try:
        tls = writer.get_extra_info('ssl_object')
        caller = common_name_of(tls.getpeercert() if tls else None)
        if not caller:
            return
        for _ in range(100):
            message = await asyncio.wait_for(reader.readline(), timeout=30)
            if not message:
                break
            if len(message) > 65536 or not message.endswith(b'\n'):
                break
            response = await dispatch_message(message, caller_common_name=caller, broker=broker, cdp=cdp)
            writer.write(frame(response))
            await asyncio.wait_for(writer.drain(), timeout=10)
    except (OSError, ValueError, TypeError, KeyError, asyncio.TimeoutError, WireError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


async def serve(config):
    from services.browser_control_agent.cdp import LoopbackCdp
    from services.browser_stream_host.broker_client import BrokerClient, BrokerConfig
    context = build_ssl_context(ca_file=config.ca_file, cert_file=config.cert_file, key_file=config.key_file)
    cdp = LoopbackCdp(config.cdp_websocket_url)
    broker = BrokerClient(BrokerConfig.from_environment(service='CONTROL'))
    slots = asyncio.Semaphore(32)

    async def accepted(reader, writer):
        if slots.locked():
            writer.close()
            await writer.wait_closed()
            return
        async with slots:
            await handle_client(reader, writer, broker=broker, cdp=cdp)

    try:
        await broker.start()
        await cdp.connect()
        listener = await asyncio.start_server(accepted, config.bind, config.port, ssl=context, limit=65537, ssl_handshake_timeout=10)
        async with listener:
            await listener.serve_forever()
    finally:
        await cdp.close()
        await broker.close()


def main(argv=None) -> int:
    """The entry point the systemd unit names.

    It refuses to start rather than starting wrongly, and it says which of the four things
    it needs was missing. A control agent that comes up on the wrong interface and serves
    requests is worse than one that does not come up at all.
    """
    from services.browser_stream_host.runtime_check import check_runtime
    from services.browser_stream_host.broker_client import BrokerRefused
    from services.browser_control_agent.cdp import CdpUnavailable
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-runtime', action='store_true')
    args = parser.parse_args([] if argv is None else argv)
    report = check_runtime()
    if args.check_runtime or not report['ready']:
        print(json.dumps(report))
        return 0 if report['ready'] else 2
    try:
        config = ServerConfig.from_environment()
        if not 1 <= config.port <= 65535:
            raise ValueError('control_port_invalid')
        asyncio.run(serve(config))
    except KeyboardInterrupt:
        return 0
    except (BindRefused, ValueError, OSError, BrokerRefused, CdpUnavailable) as exc:
        print(json.dumps({'ready': False, 'error': 'RUNTIME_NOT_CONFIGURED', 'reason': str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
