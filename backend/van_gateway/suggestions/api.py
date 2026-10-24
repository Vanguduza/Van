from __future__ import annotations

from fastapi import APIRouter,HTTPException,Query

from .models import SuggestionCreate,SuggestionDecision,SuggestionStatus
from .service import SuggestionService,SuggestionServiceError


def build_suggestion_router(service:SuggestionService)->APIRouter:
    router=APIRouter(prefix="/v1/suggestions",tags=["suggestions"])
    def fail(exc:SuggestionServiceError)->None:
        raise HTTPException(status_code=404 if exc.code=="SUGGESTION_UNKNOWN" else 409,detail=exc.code) from exc

    @router.post("")
    async def create(body:SuggestionCreate):
        try:return (await service.create(body)).model_dump(mode="json")
        except SuggestionServiceError as exc:fail(exc)

    @router.get("")
    async def listing(status:SuggestionStatus|None=None,limit:int=Query(default=100,ge=1,le=500)):
        return [x.model_dump(mode="json") for x in await service.list(status,limit)]

    @router.get("/{suggestion_id}")
    async def get_one(suggestion_id:str):
        item=await service.get(suggestion_id)
        if item is None: raise HTTPException(status_code=404,detail="suggestion_unknown")
        return item.model_dump(mode="json")

    @router.post("/{suggestion_id}/decision")
    async def decide(suggestion_id:str,body:SuggestionDecision):
        try:return await service.decide(suggestion_id,body)
        except SuggestionServiceError as exc:fail(exc)

    return router
