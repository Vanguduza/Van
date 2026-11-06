"""Authenticated owner chart configuration only; no broker or renderer delegation."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler

PRIVATE_HEADERS = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}

class PrivateChartRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def private(request):
            try:response=await original(request)
            except HTTPException as exc:
                exc.headers={**(exc.headers or {}),**PRIVATE_HEADERS}
                raise
            except RequestValidationError as exc:
                response=await request_validation_exception_handler(request,exc)
            response.headers.update(PRIVATE_HEADERS)
            return response
        return private
from .chart_models import (ChartCapability, CreateWorkspace, DeleteWorkspace, ReplaceWorkspace,
    RestoreWorkspace, RevisionList, WorkspaceList, WorkspaceRevision, WorkspaceWrite, ChartErrorResponse)
from .chart_workspaces import ChartWorkspaceService,ChartWorkspaceError

def build_chart_router(service:ChartWorkspaceService)->APIRouter:
    router=APIRouter(prefix='/v1/trading/charts',tags=['chart-workspaces'],route_class=PrivateChartRoute,responses={status:{'model':ChartErrorResponse} for status in (404,409,413,429,503)})
    def fail(exc:ChartWorkspaceError):
        raise HTTPException(exc.status,detail={'code':exc.code,**exc.details}) from exc
    @router.get('/capabilities',response_model=ChartCapability)
    async def capability():return service.capability()
    @router.get('/operations/{request_id}',response_model=WorkspaceWrite)
    async def operation(request_id:str):
        try:return await service.operation('owner',request_id)
        except ChartWorkspaceError as exc:fail(exc)
    @router.get('/workspaces',response_model=WorkspaceList)
    async def listing(limit:int=Query(100,ge=1,le=128),after_id:str|None=None):
        try:return await service.listing('owner',limit=limit,after_id=after_id)
        except ChartWorkspaceError as exc:fail(exc)
    @router.post('/workspaces',response_model=WorkspaceWrite)
    async def create(body:CreateWorkspace):
        try:return await service.create('owner',body)
        except ChartWorkspaceError as exc:fail(exc)
    @router.get('/workspaces/{workspace_id}',response_model=WorkspaceRevision)
    async def get(workspace_id:str,revision:int|None=Query(None,ge=1,le=1024)):
        try:return await service.get('owner',workspace_id,revision)
        except ChartWorkspaceError as exc:fail(exc)
    @router.put('/workspaces/{workspace_id}',response_model=WorkspaceWrite)
    async def replace(workspace_id:str,body:ReplaceWorkspace):
        try:return await service.replace('owner',workspace_id,body)
        except ChartWorkspaceError as exc:fail(exc)
    @router.delete('/workspaces/{workspace_id}',response_model=WorkspaceWrite)
    async def delete(workspace_id:str,body:DeleteWorkspace):
        try:return await service.delete('owner',workspace_id,body)
        except ChartWorkspaceError as exc:fail(exc)
    @router.get('/workspaces/{workspace_id}/revisions',response_model=RevisionList)
    async def revisions(workspace_id:str,limit:int=Query(100,ge=1,le=128),before_revision:int|None=Query(None,ge=1,le=1024)):
        try:return await service.revisions('owner',workspace_id,limit=limit,before_revision=before_revision)
        except ChartWorkspaceError as exc:fail(exc)
    @router.post('/workspaces/{workspace_id}/restore',response_model=WorkspaceWrite)
    async def restore(workspace_id:str,body:RestoreWorkspace):
        try:return await service.restore('owner',workspace_id,body)
        except ChartWorkspaceError as exc:fail(exc)
    return router
