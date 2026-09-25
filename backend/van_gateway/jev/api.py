from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.models import DegradedCode

from .client import JevProjectionClient, JevProjectionError


class JevProjectionApi:
    """Read-only owner-device projection of the shared DIAL Jev service.

    Mutations deliberately do not exist here. VAN Jev control buttons submit owner commands
    through the normal VAN command/Hermes authority path.
    """

    def __init__(self, client: JevProjectionClient, degraded: DegradedRegistry):
        self.client = client
        self.degraded = degraded
        self.router = APIRouter(prefix="/v1/jev", tags=["jev"])
        self.router.add_api_route("/health", self.health, methods=["GET"])
        self.router.add_api_route("/status", self.status, methods=["GET"])
        self.router.add_api_route("/provider", self.provider, methods=["GET"])
        self.router.add_api_route("/modules", self.modules, methods=["GET"])
        self.router.add_api_route("/modules/{module_id:path}", self.module, methods=["GET"])
        self.router.add_api_route("/activity", self.activity, methods=["GET"])
        self.router.add_api_route("/performance", self.performance, methods=["GET"])
        self.router.add_api_route("/contribution", self.contribution, methods=["GET"])
        self.router.add_api_route("/evaluation/packet", self.evaluation_packet, methods=["GET"])
        self.router.add_api_route("/evaluation/proposals", self.evaluation_proposals, methods=["GET"])
        self.router.add_api_route("/evaluation/reviews", self.evaluation_reviews, methods=["GET"])
        self.router.add_api_route("/evaluation/candidates", self.evaluation_candidates, methods=["GET"])

    async def _call(self, fn):
        try:
            payload = await fn()
            self.degraded.set(DegradedCode.JEV_UNAVAILABLE, False)
            return payload
        except (JevProjectionError, OSError, ValueError) as exc:
            self.degraded.set(DegradedCode.JEV_UNAVAILABLE, True)
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def health(self) -> dict:
        try:
            payload = await self.client.health()
            unavailable = payload.get("status") not in {"ok", "disabled"}
            self.degraded.set(DegradedCode.JEV_UNAVAILABLE, unavailable)
            return payload
        except (JevProjectionError, OSError, ValueError) as exc:
            self.degraded.set(DegradedCode.JEV_UNAVAILABLE, True)
            return {"status": "unavailable", "enabled": False, "detail": str(exc)}

    async def status(self) -> dict:
        return await self._call(self.client.status)

    async def provider(self) -> dict:
        return await self._call(self.client.provider)

    async def modules(self) -> dict:
        return await self._call(self.client.modules)

    async def module(self, module_id: str) -> dict:
        return await self._call(lambda: self.client.module(module_id))

    async def activity(
        self,
        project_id: str = Query(default="van", min_length=1, max_length=128),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        return await self._call(lambda: self.client.activity(project_id=project_id, limit=limit))

    async def performance(
        self,
        project_id: str = Query(default="van", min_length=1, max_length=128),
        module_id: str | None = Query(default=None, max_length=256),
    ) -> dict:
        return await self._call(lambda: self.client.performance(project_id=project_id, module_id=module_id))

    async def contribution(
        self,
        project_id: str = Query(default="van", min_length=1, max_length=128),
        module_id: str = Query(min_length=1, max_length=256),
    ) -> dict:
        return await self._call(lambda: self.client.contribution(project_id=project_id, module_id=module_id))

    async def evaluation_packet(
        self,
        project_id: str = Query(default="van", min_length=1, max_length=128),
        module_id: str = Query(min_length=1, max_length=256),
    ) -> dict:
        return await self._call(lambda: self.client.evaluation_packet(project_id=project_id, module_id=module_id))

    async def evaluation_proposals(
        self,
        module_id: str | None = Query(default=None, max_length=256),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        return await self._call(lambda: self.client.evaluation_proposals(module_id=module_id, limit=limit))

    async def evaluation_reviews(
        self,
        proposal_id: str | None = Query(default=None, max_length=256),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        return await self._call(
            lambda: self.client.evaluation_reviews(proposal_id=proposal_id, limit=limit)
        )

    async def evaluation_candidates(
        self,
        module_id: str | None = Query(default=None, max_length=256),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        return await self._call(
            lambda: self.client.evaluation_candidates(module_id=module_id, limit=limit)
        )


