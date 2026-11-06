"""Native chart configuration persistence, not a renderer or execution service."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any
from pydantic import ValidationError
from van_gateway.storage.db import Store
from .chart_models import (ChartCapability, CreateWorkspace, DeleteWorkspace, ReplaceWorkspace,
    RestoreWorkspace, RevisionList, RevisionSummary, WorkspaceList, WorkspaceRevision,
    WorkspaceState, WorkspaceSummary, WorkspaceWrite)



class ChartWorkspaceError(ValueError):
    def __init__(self,code:str,status:int=409,**details):
        super().__init__(code);self.code=code;self.status=status;self.details=details

def encoded(value:Any)->str:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)

def sha(text:str)->str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

class ChartWorkspaceService:
    def __init__(self,store:Store):self.store=store

    @staticmethod
    def capability()->ChartCapability:return ChartCapability()

    @staticmethod
    def _state(state:WorkspaceState)->tuple[str,str]:
        text=encoded(state.model_dump(mode='json'))
        if len(text.encode('utf-8'))>ChartCapability().max_state_bytes:
            raise ChartWorkspaceError('CHART_STATE_TOO_LARGE',413)
        return text,sha(text)

    async def _head(self,db:Any,owner_id:str,workspace_id:str):
        row=await(await db.execute('SELECT * FROM chart_workspaces WHERE owner_id=? AND workspace_id=?',(owner_id,workspace_id))).fetchone()
        if row is None:raise ChartWorkspaceError('CHART_WORKSPACE_UNKNOWN',404)
        return row

    async def _revision(self,db:Any,owner_id:str,workspace_id:str,revision:int)->WorkspaceRevision:
        row=await(await db.execute('SELECT * FROM chart_workspace_revisions WHERE owner_id=? AND workspace_id=? AND revision=?',(owner_id,workspace_id,revision))).fetchone()
        if row is None:raise ChartWorkspaceError('CHART_REVISION_UNKNOWN',404)
        if sha(row['state_json'])!=row['state_sha256']:raise ChartWorkspaceError('CHART_STATE_INTEGRITY_FAILED',503)
        try:state=WorkspaceState.model_validate_json(row['state_json'])
        except ValidationError as exc:raise ChartWorkspaceError('CHART_STATE_INTEGRITY_FAILED',503) from exc
        return WorkspaceRevision(workspace_id=workspace_id,revision=revision,
            state=state,state_sha256=row['state_sha256'],
            recorded_at_ms=row['recorded_at_ms'],restored_from_revision=row['restored_from_revision'])

    async def get(self,owner_id:str,workspace_id:str,revision:int|None=None)->WorkspaceRevision:
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            head=await self._head(db,owner_id,workspace_id)
            return await self._revision(db,owner_id,workspace_id,head['revision'] if revision is None else revision)

    async def listing(self,owner_id:str,*,limit:int=100,after_id:str|None=None)->WorkspaceList:
        limit=min(max(1,limit),128)
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            if after_id is not None:await self._head(db,owner_id,after_id)
            rows=await(await db.execute('SELECT * FROM chart_workspaces WHERE owner_id=? AND workspace_id>? ORDER BY workspace_id LIMIT ?',
                (owner_id,after_id or '',min(max(1,limit),128)+1))).fetchall()
            count=await(await db.execute('SELECT count(*) n FROM chart_workspaces WHERE owner_id=?',(owner_id,))).fetchone()
            visible=rows[:limit];more=len(rows)>limit
            return WorkspaceList(workspaces=[WorkspaceSummary(workspace_id=r['workspace_id'],revision=r['revision'],name=r['name'],updated_at_ms=r['updated_at_ms']) for r in visible],
                total_count=count['n'],next_after_id=visible[-1]['workspace_id'] if more and visible else None)

    async def revisions(self,owner_id:str,workspace_id:str,*,limit:int=100,before_revision:int|None=None)->RevisionList:
        limit=min(max(1,limit),128)
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            await self._head(db,owner_id,workspace_id)
            if before_revision is not None:await self._revision(db,owner_id,workspace_id,before_revision)
            rows=await(await db.execute('SELECT revision,state_sha256,recorded_at_ms,restored_from_revision FROM chart_workspace_revisions '
                'WHERE owner_id=? AND workspace_id=? AND revision<? ORDER BY revision DESC LIMIT ?',
                (owner_id,workspace_id,before_revision if before_revision is not None else 2**63-1,min(max(1,limit),128)+1))).fetchall()
            count=await(await db.execute('SELECT count(*) n FROM chart_workspace_revisions WHERE owner_id=? AND workspace_id=?',(owner_id,workspace_id))).fetchone()
            visible=rows[:limit];more=len(rows)>limit
            return RevisionList(workspace_id=workspace_id,revisions=[RevisionSummary(**dict(r)) for r in visible],
                total_count=count['n'],next_before_revision=visible[-1]['revision'] if more and visible else None)

    async def operation(self,owner_id:str,request_id:str)->WorkspaceWrite:
        row=await self.store.fetchone('SELECT result_json FROM chart_workspace_operations WHERE owner_id=? AND request_id=?',(owner_id,request_id))
        if row is None:raise ChartWorkspaceError('CHART_OPERATION_UNKNOWN',404)
        return WorkspaceWrite.model_validate_json(row['result_json'])

    async def create(self,owner_id:str,body:CreateWorkspace)->WorkspaceWrite:
        return await self._write(owner_id,None,'CREATE',body)

    async def replace(self,owner_id:str,workspace_id:str,body:ReplaceWorkspace)->WorkspaceWrite:
        return await self._write(owner_id,workspace_id,'REPLACE',body)

    async def restore(self,owner_id:str,workspace_id:str,body:RestoreWorkspace)->WorkspaceWrite:
        return await self._write(owner_id,workspace_id,'RESTORE',body)

    async def delete(self,owner_id:str,workspace_id:str,body:DeleteWorkspace)->WorkspaceWrite:
        return await self._write(owner_id,workspace_id,'DELETE',body)

    async def _write(self,owner_id:str,workspace_id:str|None,kind:str,body:Any)->WorkspaceWrite:
        # No state snapshot enters the receipt table: deletion removes private settings
        # and all revision bodies, while a minimal original outcome remains queryable.
        request_sha=sha(encoded({'workspace_id':workspace_id,'kind':kind,'body':body.model_dump(mode='json')}))
        state_tuple=self._state(body.state) if kind in {'CREATE','REPLACE'} else None
        attempted_commit=False
        try:
            async with self.store.connection() as db:
                await db.execute('BEGIN IMMEDIATE')
                old=await(await db.execute('SELECT request_sha256,result_json FROM chart_workspace_operations WHERE owner_id=? AND request_id=?',(owner_id,body.request_id))).fetchone()
                if old is not None:
                    if old['request_sha256']!=request_sha:raise ChartWorkspaceError('CHART_OPERATION_SCOPE_CONFLICT')
                    return WorkspaceWrite.model_validate_json(old['result_json'])
                now=int(time.time()*1000)
                if kind=='CREATE':
                    count=await(await db.execute('SELECT count(*) n FROM chart_workspaces WHERE owner_id=?',(owner_id,))).fetchone()
                    if count['n']>=self.capability().max_workspaces:raise ChartWorkspaceError('CHART_WORKSPACE_CAPACITY_REACHED',429)
                    workspace_id='cws_'+uuid.uuid4().hex
                    revision=1
                    await db.execute('INSERT INTO chart_workspaces(owner_id,workspace_id,revision,name,updated_at_ms) VALUES(?,?,?,?,?)',
                        (owner_id,workspace_id,revision,body.state.name,now))
                else:
                    head=await self._head(db,owner_id,workspace_id)
                    if head['revision']!=body.expected_revision:
                        raise ChartWorkspaceError('CHART_REVISION_CONFLICT',current_revision=head['revision'])
                    revision=head['revision']+1
                restored_from=None
                if kind=='DELETE':
                    await db.execute('DELETE FROM chart_workspaces WHERE owner_id=? AND workspace_id=?',(owner_id,workspace_id))
                    state_hash=None
                else:
                    if kind=='RESTORE':
                        previous=await self._revision(db,owner_id,workspace_id,body.target_revision)
                        state_tuple=self._state(previous.state);state=previous.state;restored_from=body.target_revision
                    else:state=body.state
                    if revision>self.capability().max_revisions:raise ChartWorkspaceError('CHART_REVISION_CAPACITY_REACHED',429)
                    text,state_hash=state_tuple
                    await db.execute('INSERT INTO chart_workspace_revisions(owner_id,workspace_id,revision,state_json,state_sha256,recorded_at_ms,restored_from_revision) VALUES(?,?,?,?,?,?,?)',
                        (owner_id,workspace_id,revision,text,state_hash,now,restored_from))
                    await db.execute('UPDATE chart_workspaces SET revision=?,name=?,updated_at_ms=? WHERE owner_id=? AND workspace_id=?',
                        (revision,state.name,now,owner_id,workspace_id))
                result=WorkspaceWrite(request_id=body.request_id,workspace_id=workspace_id,revision=revision,
                    state_sha256=state_hash,status='DELETED' if kind=='DELETE' else 'SAVED')
                await db.execute('INSERT INTO chart_workspace_operations(owner_id,request_id,request_sha256,result_json,created_at_ms) VALUES(?,?,?,?,?)',
                    (owner_id,body.request_id,request_sha,result.model_dump_json(),now))
                attempted_commit=True
                await db.commit()
                return result
        except ChartWorkspaceError:
            raise
        except Exception as exc:
            if not attempted_commit:raise
            # Query exactly this operation after the failed connection has closed. A
            # newer workspace head cannot stand in for the original write result.
            try:
                observed=await self.store.fetchone('SELECT request_sha256,result_json FROM chart_workspace_operations WHERE owner_id=? AND request_id=?',(owner_id,body.request_id))
                if observed is None:raise ChartWorkspaceError('CHART_OPERATION_UNKNOWN',404)
                if observed['request_sha256']!=request_sha:raise ChartWorkspaceError('CHART_OPERATION_SCOPE_CONFLICT')
                original=WorkspaceWrite.model_validate_json(observed['result_json'])
            except ChartWorkspaceError as read_error:
                if read_error.code=='CHART_OPERATION_UNKNOWN':
                    raise ChartWorkspaceError('CHART_WRITE_NOT_APPLIED',503,request_id=body.request_id) from exc
                raise ChartWorkspaceError('CHART_WRITE_OUTCOME_UNKNOWN',503,request_id=body.request_id) from exc
            except Exception:
                raise ChartWorkspaceError('CHART_WRITE_OUTCOME_UNKNOWN',503,request_id=body.request_id) from exc
            return original
