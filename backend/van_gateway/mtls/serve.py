"""Gateway process entry point: loopback listener plus the public mutual-TLS listener.

    python -m van_gateway.mtls.serve

* Loopback ``VAN_LOOPBACK_HOST:VAN_LOOPBACK_PORT`` (default 127.0.0.1:8787): exactly what the
  unit ran before (Hermes, the owner-runtime MCP, local tools and probes). It owns the app's
  lifespan.
* Public ``VAN_MTLS_BIND:VAN_MTLS_PORT`` (default 0.0.0.0:8443), only when ``VAN_MTLS_ENABLED``:
  TLS 1.3, client certificates verified against the device CA, every route behind
  `MutualTLSGate`. It starts after the app's startup has completed and stops with the
  loopback listener. It shares the one app instance, so sessions, event cursors and the
  Hermes bridge are the same objects on both.
"""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from van_gateway.mtls.transport import (
    MutualTLSGate,
    PeerCertificateH11Protocol,
    PeerCertificateWebSocketProtocol,
    build_ssl_context,
)

log = logging.getLogger("van_gateway.mtls")


def _public_config(app, settings) -> uvicorn.Config:
    directory = settings.mtls_dir
    gate = MutualTLSGate(app, lambda: getattr(app.state, "device_ca", None))
    return uvicorn.Config(
        gate,
        host=settings.mtls_bind,
        port=int(settings.mtls_port),
        lifespan="off",  # the loopback server runs the app's lifespan once
        http=PeerCertificateH11Protocol,
        ws=PeerCertificateWebSocketProtocol,
        ssl_context_factory=lambda _config, _default: build_ssl_context(directory),
        ws_ping_interval=float(settings.mtls_ws_ping_seconds),
        ws_ping_timeout=float(settings.mtls_ws_ping_seconds),
        proxy_headers=False,  # nothing sits in front of this listener; never trust X-Forwarded-*
        server_header=False,
        date_header=False,
        timeout_keep_alive=75,
        log_level=os.environ.get("VAN_LOG_LEVEL", "info"),
    )


async def _run() -> None:
    # Imported here, not at module level: building the app reads the environment, and tests
    # build a public config around their own app without starting a process.
    from van_gateway.app import app
    from van_gateway.config import get_settings

    settings = get_settings()

    loopback = uvicorn.Server(uvicorn.Config(
        app,
        host=settings.loopback_host,
        port=int(settings.loopback_port),
        log_level=os.environ.get("VAN_LOG_LEVEL", "info"),
    ))
    tasks = [asyncio.create_task(loopback.serve(), name="van-loopback")]

    public: uvicorn.Server | None = None
    if settings.mtls_enabled:
        if getattr(app.state, "device_ca", None) is None:
            raise SystemExit("VAN_MTLS_ENABLED is set but the device CA did not load (VAN_MTLS_DIR)")
        public = uvicorn.Server(_public_config(app, settings))

        async def run_public() -> None:
            while not loopback.started:  # never serve before the app's startup has completed
                if loopback.should_exit or tasks[0].done():
                    return
                await asyncio.sleep(0.05)
            await public._serve()  # the loopback server owns signal handling

        async def follow_loopback() -> None:
            await tasks[0]
            public.should_exit = True

        tasks += [asyncio.create_task(run_public(), name="van-mtls"),
                  asyncio.create_task(follow_loopback(), name="van-mtls-follow")]
        log.info("VAN mutual-TLS listener enabled on %s:%s", settings.mtls_bind, settings.mtls_port)

    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for task in done:
        if task.exception() is not None:
            loopback.should_exit = True
            if public is not None:
                public.should_exit = True
            raise task.exception()
    await asyncio.gather(*tasks)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
