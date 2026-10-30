from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .models import ArtifactKind
from .service import ArtifactService


def build_artifact_router(service: ArtifactService) -> APIRouter:
    router = APIRouter(prefix="/v1/artifacts", tags=["artifacts"])

    @router.get("")
    async def list_artifacts(
        project_id: str | None = None,
        mission_id: str | None = None,
        kind: ArtifactKind | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ):
        return [
            item.model_dump(mode="json")
            for item in await service.list(
                project_id=project_id, mission_id=mission_id, kind=kind, limit=limit
            )
        ]

    @router.get("/{artifact_id}")
    async def get_artifact(artifact_id: str):
        item = await service.get(artifact_id)
        if item is None:
            raise HTTPException(status_code=404, detail="artifact_unknown")
        return item.model_dump(mode="json")

    return router
