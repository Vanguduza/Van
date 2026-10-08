"""van-private-core service: the bounded authenticated API into the VAN private plane.

Owner decision 2026-09-29 §3 places the Owner Cognitive Model, ``owner_model_revision``,
the correction/invalidation outbox, owner-private Hindsight, the owner-private OpenViking
projection and the personal-context resolver in a dedicated trust zone,
``van-private-core``. This module is what that zone runs
(``deploy/van-private-core/systemd/van-private-core.service``).

It exposes exactly the routes in ``PRIVATE_CORE_ROUTES`` and nothing else, every one of
them behind the scoped internal credential (``understanding`` scope) — the store itself
(SQLite file, and later the owner-private Hindsight bank and OpenViking projection) is
never reachable from another zone except through these routes.

Import discipline (enforced by ``tests/contracts/test_van_private_core_topology.py``):
this module and everything it imports must not pull in browser automation, Stagehand,
Chromium/Playwright, Jev, VATI order execution or broker adapters. Keep imports narrow —
do not import ``van_gateway.app``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from van_gateway.auth.control_scopes import ControlScope, require_scoped_internal
from van_gateway.config import Settings, get_settings
from van_gateway.storage.db import Store
from van_gateway.understanding.owner_model import OwnerCognitiveModel
from van_gateway.understanding.personal_context_resolver import (
    PersonalContextResolver,
    PersonalContextUnavailable,
    RevisionFencedCapsuleCache,
)

ZONE = "van-private-core"
PRIVATE_CORE_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/v1/private-core/owner-model/revision"),
    ("GET", "/v1/private-core/personal-context"),
)


def create_private_core_app(
    settings: Settings | None = None, store: Store | None = None
) -> FastAPI:
    settings = settings or get_settings()
    store = store or Store(settings.database_path)
    model = OwnerCognitiveModel(store)
    resolver = PersonalContextResolver(model, cache=RevisionFencedCapsuleCache())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await store.migrate()
        yield

    app = FastAPI(title="VAN private core", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.zone = ZONE
    app.state.resolver = resolver

    def authorize(token: str | None) -> None:
        require_scoped_internal(settings, token, ControlScope.UNDERSTANDING)

    @app.get("/v1/private-core/owner-model/revision")
    async def owner_model_revision(
        owner_principal_id: str = "owner",
        x_van_internal_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        authorize(x_van_internal_token)
        try:
            revision = await resolver.authoritative_revision(owner_principal_id)
        except PersonalContextUnavailable as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        return {"zone": ZONE, "owner_principal_id": owner_principal_id,
                "owner_model_revision": revision}

    @app.get("/v1/private-core/personal-context")
    async def personal_context(
        owner_model_revision: int,
        purpose: str,
        owner_principal_id: str = "owner",
        project_id: str | None = None,
        x_van_internal_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        authorize(x_van_internal_token)
        try:
            return await resolver.resolve(
                owner_principal_id, requested_revision=owner_model_revision,
                purpose=purpose, project_id=project_id,
            )
        except PersonalContextUnavailable as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


__all__ = ["PRIVATE_CORE_ROUTES", "ZONE", "create_private_core_app"]
