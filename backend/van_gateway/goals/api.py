from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .models import GoalCreate, GoalPatch, GoalStatus, WatchCreate, WatchObservation, WatchStatus
from .service import GoalService, GoalServiceError


class MilestonePatch(BaseModel):
    done: bool


class MissionLink(BaseModel):
    mission_id: str


class WatchStatusPatch(BaseModel):
    status: WatchStatus


def build_goal_router(service: GoalService) -> APIRouter:
    router=APIRouter(tags=["goals"])

    def fail(exc: GoalServiceError) -> None:
        code=404 if exc.code.endswith("_UNKNOWN") else 409
        raise HTTPException(status_code=code, detail=exc.code) from exc

    @router.post("/v1/goals")
    async def create_goal(body: GoalCreate):
        return (await service.create(body)).model_dump(mode="json")

    @router.get("/v1/goals")
    async def list_goals(status: GoalStatus | None=None, limit:int=Query(default=100,ge=1,le=500)):
        return [x.model_dump(mode="json") for x in await service.list(status,limit)]

    @router.get("/v1/goals/{goal_id}")
    async def get_goal(goal_id:str):
        goal=await service.get(goal_id)
        if goal is None: raise HTTPException(status_code=404,detail="goal_unknown")
        return goal.model_dump(mode="json")

    @router.patch("/v1/goals/{goal_id}")
    async def patch_goal(goal_id:str,body:GoalPatch):
        try: return (await service.patch(goal_id,body)).model_dump(mode="json")
        except GoalServiceError as exc: fail(exc)

    @router.post("/v1/goals/{goal_id}/milestones/{milestone_id}")
    async def set_milestone(goal_id:str,milestone_id:str,body:MilestonePatch):
        try: return (await service.set_milestone(goal_id,milestone_id,body.done)).model_dump(mode="json")
        except GoalServiceError as exc: fail(exc)

    @router.post("/v1/goals/{goal_id}/missions")
    async def link_mission(goal_id:str,body:MissionLink):
        try: return (await service.link_mission(goal_id,body.mission_id)).model_dump(mode="json")
        except GoalServiceError as exc: fail(exc)

    @router.post("/v1/watches")
    async def create_watch(body:WatchCreate):
        try: return (await service.create_watch(body)).model_dump(mode="json")
        except GoalServiceError as exc: fail(exc)

    @router.get("/v1/watches")
    async def list_watches(status:WatchStatus|None=None,limit:int=Query(default=100,ge=1,le=500)):
        return [x.model_dump(mode="json") for x in await service.list_watches(status,limit)]

    @router.get("/v1/watches/{watch_id}")
    async def get_watch(watch_id:str):
        watch=await service.get_watch(watch_id)
        if watch is None: raise HTTPException(status_code=404,detail="watch_unknown")
        return watch.model_dump(mode="json")

    @router.patch("/v1/watches/{watch_id}")
    async def patch_watch(watch_id:str,body:WatchStatusPatch):
        try: return (await service.set_watch_status(watch_id,body.status)).model_dump(mode="json")
        except GoalServiceError as exc: fail(exc)

    @router.post("/v1/watches/{watch_id}/observations")
    async def record_watch_observation(watch_id:str,body:WatchObservation):
        try: return await service.record_observation(watch_id,body)
        except GoalServiceError as exc: fail(exc)

    return router
