"""Keep the supported ASGI import inert; initialize on use, once per process."""
from __future__ import annotations

from threading import Lock
from typing import Callable

from fastapi import FastAPI
from starlette.types import Receive, Scope, Send


class LazyGateway:
    def __init__(self, factory: Callable[[], FastAPI]) -> None:
        self._factory = factory
        self._application: FastAPI | None = None
        self._initialization_lock = Lock()

    def _get_application(self) -> FastAPI:
        with self._initialization_lock:
            if self._application is None:
                # A failed construction is not cached as a partial application.
                self._application = self._factory()
            return self._application

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._get_application()(scope, receive, send)

    def __getattr__(self, name: str):
        # Preserve inspection tools using app.routes/state/openapi. Merely importing
        # app does not enter this path or construct any services.
        return getattr(self._get_application(), name)
