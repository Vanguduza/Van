"""HTTPS single-offer SDP entry point. No shell, raw CDP or filesystem HTTP surface."""
from __future__ import annotations
import argparse
import asyncio
import ipaddress
import json
import os
import ssl
from pathlib import Path

from services.browser_stream_host.broker_client import BrokerClient, BrokerConfig, BrokerRefused
from services.browser_stream_host.runtime_check import check_runtime


def stream_context(environment):
    cert = environment.get('VAN_BROWSER_STREAM_TLS_CERT', '')
    key = environment.get('VAN_BROWSER_STREAM_TLS_KEY', '')
    if not cert or not key:
        raise ValueError('stream_tls_unbound')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(cert, key)
    return context


def build_application(runtime, signal_path='/rtc'):
    import re
    if not re.fullmatch(r'/rtc(?:/[A-Za-z0-9_-]+)*', signal_path):
        raise ValueError('stream_signal_path_invalid')
    from aiohttp import web
    from services.browser_stream_host.runtime import StreamRefused
    from services.browser_control_agent.cdp import CdpUnavailable
    from services.browser_stream_host.files import FileRefused
    application = web.Application(client_max_size=300_000)

    async def exchange(request):
        if request.content_type != 'application/json':
            return web.json_response({'error': 'stream_content_type_refused'}, status=415)
        authorization = request.headers.get('Authorization', '')
        if not authorization.startswith('Bearer '):
            return web.json_response({'error': 'stream_bearer_required'}, status=401)
        try:
            body = await request.json()
            answer = await runtime.exchange(authorization[7:], body)
            return web.json_response(answer, headers={'Cache-Control': 'no-store'})
        except (StreamRefused, BrokerRefused, FileRefused, ValueError, TypeError, KeyError):
            return web.json_response({'error': 'stream_offer_or_authority_refused'}, status=403)
        except CdpUnavailable:
            return web.json_response({'error': 'stream_browser_unavailable'}, status=503)
        except asyncio.TimeoutError:
            return web.json_response({'error': 'stream_negotiation_timeout'}, status=504)

    async def health(request):
        # Startup verifies bindings and CDP; a health report is never live qualification.
        socket = getattr(runtime.cdp, '_socket', None)
        ready = socket is not None and not socket.closed
        return web.json_response({'service': 'van-browser-stream', 'ready': ready, 'live_qualified': False}, status=200 if ready else 503)

    def file_request(request):
        authorization = request.headers.get('Authorization', '')
        producer = request.headers.get('X-Van-Producer-Session', '')
        session = runtime.sessions.get(producer)
        if not authorization.startswith('Bearer ') or session is None or session.closed or session.files is None:
            raise FileRefused('file_grant_or_peer_missing')
        return session, authorization[7:]

    async def download(request):
        descriptor = None
        response = None
        try:
            session, token = file_request(request)
            path, size, mime = await session.files.download(request.match_info['download_id'], token)
            # Opening the exact sealed, stream-owned file with NOFOLLOW closes the
            # stat/open symlink race. A generic FileResponse would follow a replacement.
            import stat
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                raise FileRefused('download_file_changed')
            response = web.StreamResponse(headers={'Content-Length': str(size), 'Content-Type': mime, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
            await response.prepare(request)
            while chunk := await asyncio.to_thread(os.read, descriptor, 65536):
                if session.closed or request.match_info['download_id'] in session.files.deleted:
                    raise FileRefused('download_peer_closed')
                await response.write(chunk)
            await response.write_eof()
            return response
        except (FileRefused, BrokerRefused, ValueError, OSError):
            if response is not None and response.prepared:
                response.force_close()
                return response
            return web.json_response({'error': 'file_transfer_refused'}, status=403)
        finally:
            if descriptor is not None:
                os.close(descriptor)

    async def analyse(request):
        try:
            session, token = file_request(request)
            if request.content_length not in {None, 0}:
                raise FileRefused('analysis_body_refused')
            result = await asyncio.wait_for(session.files.analyse(request.match_info['download_id'], token), 30)
            return web.json_response(result, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        except (FileRefused, BrokerRefused, ValueError, OSError, asyncio.TimeoutError):
            return web.json_response({'error': 'file_analysis_refused'}, status=403)

    async def upload(request):
        try:
            session, token = file_request(request)
            if request.content_type != 'application/octet-stream' or request.content_length is None:
                raise FileRefused('upload_framing_refused')
            result = await asyncio.wait_for(session.files.upload(
                request.match_info['chooser_id'], token, request.content.iter_chunked(65536),
                expected_size=request.content_length, expected_sha=request.headers.get('X-Van-Content-SHA256', ''),
            ), 120)
            return web.json_response(result, headers={'Cache-Control': 'no-store'})
        except (FileRefused, BrokerRefused, CdpUnavailable, ValueError, OSError, asyncio.TimeoutError):
            return web.json_response({'error': 'file_transfer_refused'}, status=403)

    async def import_file(request):
        try:
            session, token = file_request(request)
            if request.content_type != 'application/octet-stream' or request.content_length is None:
                raise FileRefused('import_framing_refused')
            result = await asyncio.wait_for(session.files.import_file(request.match_info['resource_id'], token,
                request.content.iter_chunked(65536), expected_size=request.content_length,
                expected_sha=request.headers.get('X-Van-Content-SHA256', '')), 120)
            return web.json_response(result, headers={'Cache-Control': 'no-store'})
        except (FileRefused, BrokerRefused, ValueError, OSError, asyncio.TimeoutError):
            return web.json_response({'error': 'file_import_refused'}, status=403)

    async def clipboard(request):
        try:
            if request.content_type != 'application/json':
                raise FileRefused('clipboard_content_type_refused')
            session, token = file_request(request)
            body = await request.json()
            operation = request.match_info['operation']
            allowed = {'target_id'} if operation == 'copy' else {'target_id', 'text'}
            if not isinstance(body, dict) or set(body) != allowed or body.get('target_id') != session.target_id:
                raise FileRefused('clipboard_body_refused')
            result = await session.files.clipboard(token, operation, text=body.get('text'))
            return web.json_response(result, headers={'Cache-Control': 'no-store'})
        except (FileRefused, BrokerRefused, CdpUnavailable, ValueError, OSError):
            return web.json_response({'error': 'clipboard_transfer_refused'}, status=403)

    application.router.add_post(signal_path, exchange)
    application.router.add_get('/health', health)
    application.router.add_get(signal_path + '/files/download/{download_id}', download)
    application.router.add_post(signal_path + '/files/upload/{chooser_id}', upload)
    application.router.add_post(signal_path + '/files/analyse/{download_id}', analyse)
    application.router.add_post(signal_path + '/files/import/{resource_id}', import_file)
    application.router.add_post(signal_path + '/clipboard/{operation:copy|paste}', clipboard)
    return application


async def serve(environment=None):
    from aiohttp import web
    from services.browser_control_agent.cdp import LoopbackCdp
    from services.browser_stream_host.runtime import StreamRuntime
    from van_gateway.browser.stream_grants import StreamGrantVerifier
    env = os.environ if environment is None else environment
    bind = env.get('VAN_BROWSER_STREAM_BIND', '')
    try:
        ipaddress.ip_address(bind)
    except ValueError as exc:
        raise ValueError('stream_bind_must_be_ip_literal') from exc
    port = int(env.get('VAN_BROWSER_STREAM_PORT', '8443'))
    if not 1 <= port <= 65535:
        raise ValueError('stream_port_invalid')
    profile = env.get('VAN_BROWSER_PROFILE_ALIAS', '')
    if not profile or len(profile) > 128:
        raise ValueError('stream_profile_unbound')
    kid = env.get('VAN_BROWSER_GRANT_KID', '')
    key_file = env.get('VAN_BROWSER_GRANT_PUBLIC_KEY', '')
    if not kid or not key_file:
        raise ValueError('stream_verifier_unbound')
    verifier = StreamGrantVerifier({kid: Path(key_file).read_text()})
    tls = stream_context(env)
    ice = json.loads(env.get('VAN_BROWSER_ICE_SERVERS_JSON', '[]'))
    if not isinstance(ice, list) or len(ice) > 8:
        raise ValueError('stream_ice_bindings_invalid')
    for entry in ice:
        if not isinstance(entry, dict) or set(entry) - {'urls', 'username', 'credential'}:
            raise ValueError('stream_ice_bindings_invalid')
        urls = entry.get('urls')
        urls = [urls] if isinstance(urls, str) else urls
        if not isinstance(urls, list) or not 1 <= len(urls) <= 4 or any(not isinstance(url, str) or not url.startswith(('stun:', 'stuns:', 'turn:', 'turns:')) for url in urls):
            raise ValueError('stream_ice_bindings_invalid')
    cdp = LoopbackCdp(env.get('VAN_BROWSER_CDP_WEBSOCKET', f"ws://127.0.0.1:{env.get('VAN_BROWSER_CDP_PORT', '9222')}"))
    broker = BrokerClient(BrokerConfig.from_environment(env, service='STREAM'))
    quarantine = env.get('VAN_BROWSER_QUARANTINE_ROOT', '')
    if not quarantine or not Path(quarantine).is_dir():
        raise ValueError('stream_confined_quarantine_unbound')
    runtime = StreamRuntime(cdp, broker, verifier, profile, tuple(ice), quarantine, env.get('VAN_BROWSER_CLIPBOARD_ENABLED', '1') == '1')
    runner = None
    try:
        await broker.start()
        await cdp.connect()
        if not await cdp.targets():
            raise ValueError('stream_no_chromium_page')
        runner = web.AppRunner(build_application(runtime, env.get('VAN_BROWSER_SIGNAL_PATH', '/rtc')), access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, bind, port, ssl_context=tls)
        await site.start()
        await asyncio.Future()
    finally:
        await runtime.close()
        if runner is not None:
            await runner.cleanup()
        await cdp.close()
        await broker.close()


def main(argv=None):
    from services.browser_control_agent.cdp import CdpUnavailable
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-runtime', action='store_true')
    args = parser.parse_args([] if argv is None else argv)
    report = check_runtime()
    if args.check_runtime or not report['ready']:
        print(json.dumps(report))
        return 0 if report['ready'] else 2
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, BrokerRefused, CdpUnavailable) as exc:
        print(json.dumps({'ready': False, 'error': 'RUNTIME_NOT_CONFIGURED', 'reason': str(exc)}))
        return 2
    return 0


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
