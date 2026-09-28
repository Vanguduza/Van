from __future__ import annotations

from fastapi import APIRouter,HTTPException,Query
from pydantic import BaseModel,Field

from .models import ThreadStatus
from .service import ConversationService,ConversationServiceError


class ThreadCreate(BaseModel):
    title:str=Field(min_length=1,max_length=300)
    project_id:str|None=None
class ThreadRename(BaseModel):
    title:str=Field(min_length=1,max_length=300)
class ThreadStatePatch(BaseModel):
    status:ThreadStatus
class DraftBody(BaseModel):
    text:str=Field(default="",max_length=20000)
class FollowUpCreate(BaseModel):
    prompt:str=Field(min_length=1,max_length=8000)
class FollowUpDecision(BaseModel):
    action:str=Field(pattern="^(promote|dismiss)$")
    command_id:str|None=None


class MessageBody(BaseModel):
    role:str
    body:str=Field(min_length=1,max_length=50000)
    command_id:str|None=None
    mission_id:str|None=None
    artifact_refs:list[str]=Field(default_factory=list,max_length=100)
    terminal:bool=False


def build_conversation_router(service:ConversationService)->APIRouter:
    router=APIRouter(prefix="/v1/conversations",tags=["conversations"])
    def fail(exc:ConversationServiceError)->None:
        raise HTTPException(status_code=404 if exc.code=="THREAD_UNKNOWN" else 409,detail=exc.code) from exc

    @router.get("/main")
    async def main():
        return (await service.ensure_main()).model_dump(mode="json")

    @router.post("")
    async def create(body:ThreadCreate):
        try:return (await service.create(body.title,body.project_id)).model_dump(mode="json")
        except ConversationServiceError as exc:fail(exc)

    @router.get("")
    async def listing(status:ThreadStatus|None=None,limit:int=Query(default=100,ge=1,le=500)):
        return [x.model_dump(mode="json") for x in await service.list(status,limit)]

    @router.get("/{thread_id}")
    async def get_one(thread_id:str):
        item=await service.get(thread_id)
        if item is None:raise HTTPException(status_code=404,detail="thread_unknown")
        return item.model_dump(mode="json")

    @router.patch("/{thread_id}/title")
    async def rename(thread_id:str,body:ThreadRename):
        try:return (await service.rename(thread_id,body.title)).model_dump(mode="json")
        except ConversationServiceError as exc:fail(exc)

    @router.patch("/{thread_id}/status")
    async def state(thread_id:str,body:ThreadStatePatch):
        try:return (await service.set_status(thread_id,body.status)).model_dump(mode="json")
        except ConversationServiceError as exc:fail(exc)

    @router.put("/{thread_id}/draft")
    async def draft(thread_id:str,body:DraftBody):
        try:return (await service.save_draft(thread_id,body.text)).model_dump(mode="json")
        except ConversationServiceError as exc:fail(exc)

    @router.post("/{thread_id}/followups")
    async def queue_followup(thread_id:str,body:FollowUpCreate):
        try:return (await service.queue_followup(thread_id,body.prompt)).model_dump(mode="json")
        except ConversationServiceError as exc:fail(exc)

    @router.post("/{thread_id}/followups/{followup_id}/decision")
    async def decide_followup(thread_id:str,followup_id:str,body:FollowUpDecision):
        try:return (await service.decide_followup(thread_id,followup_id,body.action,command_id=body.command_id)).model_dump(mode="json")
        except ConversationServiceError as exc:fail(exc)

    @router.post("/{thread_id}/messages")
    async def message(thread_id:str,body:MessageBody):
        try:
            return (await service.append_message(
                thread_id,role=body.role,body=body.body,command_id=body.command_id,
                mission_id=body.mission_id,artifact_refs=body.artifact_refs,terminal=body.terminal,
            )).model_dump(mode="json")
        except ConversationServiceError as exc:fail(exc)

    return router
