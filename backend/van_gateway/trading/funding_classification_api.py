"""BE-006 §7.9.5 paired-owner structured assertions, not payment authority.

Lock order is Auth Store writer -> VATI Ledger writer. The Auth transaction is
read-only but reserves the current device/binding writer until the worker ends.
Only VATI commits annotation state: this is not a cross-store atomic commit.
"""
from __future__ import annotations
import asyncio
from contextlib import closing
import hashlib
import json
import sqlite3
import threading
import time
from typing import Literal

import aiosqlite
from fastapi import APIRouter,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,Field

HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
HEX=r'^[0-9a-f]{64}$'


class LabelError(ValueError):
    def __init__(self,code,status=503):self.code,self.status=code,status;super().__init__(code)


class LabelInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    operation_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{16,80}$')
    scope_hash:str=Field(pattern=HEX)
    native_id:int=Field(ge=1,le=2**64-1)
    statement_ref:str=Field(pattern=HEX)
    row_digest:str=Field(pattern=HEX)
    expected_revision:int=Field(ge=0,lt=2**31)
    action:Literal['SET','WITHDRAW']
    label:Literal['DEPOSIT','WITHDRAWAL','INTERNAL_TRANSFER','CREDIT','BONUS','FEE','OTHER_INCOME','OTHER_EXPENSE','UNRESOLVED']|None


class FundingClassifications:
    def __init__(self,store,trading,authorize,*,clock=None):
        self.store,self.trading,self.authorize=store,trading,authorize
        self.clock=clock or (lambda:int(time.time()*1000))
        self.tasks=set()
        self.gate=asyncio.Semaphore(2)

    def _worker(self,operation,caller,body,operation_id,received,cancelled):
        # Keep trading/private-core imports lazy, inside the existing source owner.
        if not self.trading.available() or self.trading.ledger_path==':memory:':
            raise LabelError('FUNDING_LABEL_DURABLE_STORE_UNAVAILABLE')
        from .service import _import_vati
        _import_vati()
        from vati.funding.classification_journal import ClassificationBook,ClassificationError
        from vati.core.ledger import LedgerError
        database_errors=(LedgerError,sqlite3.Error,OSError)
        if self.trading.ledger_path.startswith(('postgres://','postgresql://')):
            try:
                import psycopg
            except ImportError:raise LabelError('FUNDING_LABEL_STORE_IMPLEMENTATION_UNAVAILABLE') from None
            database_errors=(*database_errors,psycopg.Error)
        try:
            _,_,ledger=self.trading._open()
            with closing(ledger):
                book=ClassificationBook(ledger,clock=self.clock)
                if operation=='inspect':return book.lookup(operation_id)
                return book.publish(body,device_id=caller['device_id'],received_at_ms=received,cancelled=cancelled.is_set)
        except ClassificationError as error:raise LabelError(error.code,error.status) from None
        except database_errors:
            # A commit ACK may be lost. Only independently verified original state
            # resolves it; never repeat the append or fabricate a failed outcome.
            if operation=='publish':
                try:
                    _,_,ledger=self.trading._open()
                    with closing(ledger):
                        result=ClassificationBook(ledger,clock=self.clock).lookup(body['operation_id'])
                        from vati.core.canonical import canonical_hash
                        if (result['receipt']['request_digest']==canonical_hash(body)
                                and result['actor_device_id']==caller['device_id']):return result['receipt']
                except (ClassificationError,*database_errors):pass
            raise LabelError('FUNDING_LABEL_OUTCOME_UNKNOWN') from None

    async def _call(self,operation,caller,*,body=None,operation_id=None,received=None,cancelled):
        async with self.gate:
            async with self.store.connection() as db:
                # Current AuthService device/binding writers use this same Store.
                await db.execute('BEGIN IMMEDIATE')
                try:
                    await self.authorize(db,caller,operation=='publish')
                    if cancelled.is_set():raise LabelError('FUNDING_LABEL_CANCELLED',409)
                    result=await asyncio.to_thread(self._worker,operation,caller,body,operation_id,received,cancelled)
                    return result
                finally:
                    await db.rollback()  # no auth-side label state exists to commit

    async def call(self,operation,caller,*,body=None,operation_id=None):
        received=self.clock();cancelled=threading.Event()
        task=asyncio.create_task(self._call(operation,caller,body=body,operation_id=operation_id,received=received,cancelled=cancelled))
        self.tasks.add(task);task.add_done_callback(self.tasks.discard)
        try:return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            # Do not release the Auth fence while an owned Ledger worker runs.
            while not task.done():
                try:await asyncio.shield(task)
                except asyncio.CancelledError:continue
                except Exception:break
            if task.done() and not task.cancelled():task.exception()
            raise


def _distinct(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result


class PrivateLabelRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handle(request):
            try:
                if request.query_params:raise LabelError('FUNDING_LABEL_INPUT_INVALID',422)
                if request.method=='POST':
                    raw=await request.body()
                    if len(raw)>2048:raise LabelError('FUNDING_LABEL_INPUT_CAPACITY',413)
                    try:json.loads(raw,object_pairs_hook=_distinct,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
                    except (ValueError,RecursionError):raise LabelError('FUNDING_LABEL_INPUT_INVALID',422) from None
                response=await original(request);response.headers.update(HEADERS);return response
            except LabelError as error:
                return JSONResponse(status_code=error.status,content={'detail':{'code':error.code}},headers=HEADERS)
            except RequestValidationError:
                return JSONResponse(status_code=422,content={'detail':{'code':'FUNDING_LABEL_INPUT_INVALID'}},headers=HEADERS)
            except (sqlite3.Error,aiosqlite.Error,OSError):
                return JSONResponse(status_code=503,content={'detail':{'code':'FUNDING_LABEL_OUTCOME_UNKNOWN'}},headers=HEADERS)
        return handle


def build_funding_classification_router(service):
    router=APIRouter(prefix='/v1/trading/funding/classifications',tags=['funding-classifications'],route_class=PrivateLabelRoute)
    def caller(request):
        device=getattr(request.state,'van_device_id',None)
        if not device:raise LabelError('FUNDING_LABEL_OWNER_REQUIRED',403)
        return {'owner_id':'owner','device_id':device,'access_token_hash':hashlib.sha256(request.headers.get('X-Van-Device-Token','').encode()).hexdigest(),
                'proved':bool(getattr(request.state,'van_device_proved',False)),
                'verified_binding_identity':getattr(request.state,'van_device_proof_binding_identity',None)}
    @router.post('')
    async def publish(request:Request,body:LabelInput):
        return await service.call('publish',caller(request),body=body.model_dump())
    @router.get('/{operation_id}')
    async def inspect(request:Request,operation_id:str):
        if not 16<=len(operation_id)<=80:raise LabelError('FUNDING_LABEL_INPUT_INVALID',422)
        return await service.call('inspect',caller(request),operation_id=operation_id)
    return router
