"""Paired-owner immutable funding drafts. No native payment/provider dispatch."""
import asyncio
from contextlib import closing
import json
import time
from typing import Any,Literal

from fastapi import APIRouter,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,Field,StrictInt

from .payment_draft_policy import guard_payment_draft

PRIVATE_HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
MAX_DRAFT_BODY_BYTES=512*1024


def _distinct_keys(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON field')
        result[key]=value
    return result


def _invalid_constant(value):raise ValueError('non-JSON numeric constant')


class FundingDraftError(ValueError):
    def __init__(self,code,status=503,**details):self.code,self.status,self.details=code,status,details;super().__init__(code)


class FundingDraftCreate(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    # The versioned native value owner validates this complete original shape,
    # including exact minor-unit strings. It never accepts an approval flag.
    intent:dict[str,Any]


class FundingDraftReceipt(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['vati.payment-draft-receipt/1']=Field(alias='schema')
    record_ref:str
    request_id:str
    owner_ref:str
    account_scope_ref:str
    intent_hash:str
    quote_hash:str
    available_at_ms:StrictInt
    state:Literal['DRAFT_STORED_NOT_APPROVED']
    provider_qualified:Literal[False]
    execution_authority:Literal[False]


class FundingDraftView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    receipt:FundingDraftReceipt
    intent:dict[str,Any]
    claimed_quote_time_state:Literal['NOT_YET_ISSUED','EXPIRED','WITHIN_CLAIMED_WINDOW']
    current_payment_eligibility:Literal['NOT_ADMITTED']
    execution_authority:Literal[False]


class FundingDraftErrorResponse(BaseModel):
    detail:dict[str,str]


class FundingDraftService:
    def __init__(self,trading,*,clock=None):
        self.trading=trading;self.clock=clock or (lambda:int(time.time()*1000))

    def call(self,operation,owner,*,body=None,request_id=None):
        if operation not in ('create','receipt','inspect'):
            raise FundingDraftError('FUNDING_DRAFT_OPERATION_UNSUPPORTED',422)
        # A new connection is opened inside the actual worker. SQLite handles
        # are never handed from the request loop to another thread.
        if not self.trading.available() or self.trading.ledger_path==':memory:':
            raise FundingDraftError('FUNDING_DRAFT_DURABLE_STORE_UNAVAILABLE')
        from .service import _import_vati
        try:
            _import_vati()
            from vati.funding.payment_contracts import PaymentIntent,PaymentContractError,_identity
            from vati.funding.payment_drafts import PaymentDraftBook,PaymentDraftError,PaymentDraftUnknown
        except ImportError:raise FundingDraftError('FUNDING_DRAFT_IMPLEMENTATION_UNAVAILABLE') from None
        try:
            intent=PaymentIntent.from_body(body) if operation=='create' else None
            if intent is None:_identity(request_id)
            if intent is not None and intent.quote.beneficiary.owner_ref!=owner:
                raise FundingDraftError('FUNDING_DRAFT_OWNER_SCOPE_REFUSED',403)
            _,_,ledger=self.trading._open()
            with closing(ledger):
                book=PaymentDraftBook(ledger,privacy_guard=guard_payment_draft,clock=self.clock)
                if operation=='create':result=book.publish(owner,intent)
                elif operation=='receipt':result=book.lookup(owner,request_id)
                elif operation=='inspect':result=book.inspect(owner,request_id)
                else:raise FundingDraftError('FUNDING_DRAFT_OPERATION_UNSUPPORTED',422)
            if result is None:raise FundingDraftError('FUNDING_DRAFT_NOT_FOUND',404)
            return result
        except FundingDraftError:raise
        except PaymentDraftUnknown as error:
            raise FundingDraftError('FUNDING_DRAFT_OUTCOME_UNKNOWN',503,request_id=error.request_id) from None
        except PaymentContractError as error:
            if str(error)=='PAYMENT_QUOTE_EXPIRED':raise FundingDraftError('FUNDING_DRAFT_QUOTE_EXPIRED',409) from None
            raise FundingDraftError('FUNDING_DRAFT_INPUT_INVALID',422,field='intent' if operation=='create' else 'request_id') from None
        except PaymentDraftError as error:
            if 'ORIGINAL_REQUEST_CONFLICT' in str(error):raise FundingDraftError('FUNDING_DRAFT_ORIGINAL_REQUEST_CONFLICT',409) from None
            if 'RETENTION_BOUNDARY_REFUSED' in str(error):raise FundingDraftError('FUNDING_DRAFT_RETENTION_REFUSED',422,field='intent') from None
            raise FundingDraftError('FUNDING_DRAFT_HISTORY_UNAVAILABLE') from None
        except Exception:raise FundingDraftError('FUNDING_DRAFT_STORE_UNAVAILABLE') from None


class PrivateFundingDraftRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def private(request):
            if request.query_params:
                return JSONResponse(status_code=422,content={'detail':{'code':'FUNDING_DRAFT_QUERY_INVALID','field':'query'}},headers=PRIVATE_HEADERS)
            if request.method=='POST':
                raw=await request.body()
                if len(raw)>MAX_DRAFT_BODY_BYTES:
                    return JSONResponse(status_code=413,content={'detail':{'code':'FUNDING_DRAFT_BODY_CAPACITY'}},headers=PRIVATE_HEADERS)
                try:json.loads(raw,object_pairs_hook=_distinct_keys,parse_constant=_invalid_constant)
                except (ValueError,RecursionError):
                    return JSONResponse(status_code=422,content={'detail':{'code':'FUNDING_DRAFT_INPUT_INVALID','field':'intent'}},headers=PRIVATE_HEADERS)
            try:response=await original(request)
            except HTTPException as error:
                error.headers={**(error.headers or {}),**PRIVATE_HEADERS};raise
            except RequestValidationError:
                # Never reflect a rejected instrument/token value in validation.
                return JSONResponse(status_code=422,content={'detail':{'code':'FUNDING_DRAFT_INPUT_INVALID','field':'intent'}},headers=PRIVATE_HEADERS)
            response.headers.update(PRIVATE_HEADERS);return response
        return private


def build_funding_draft_router(service):
    router=APIRouter(prefix='/v1/trading/funding/drafts',tags=['funding-drafts'],route_class=PrivateFundingDraftRoute,
        responses={status:{'model':FundingDraftErrorResponse} for status in (403,404,409,413,422,503)})
    gate=asyncio.Semaphore(2)
    async def call(operation,**kwargs):
        if gate.locked():raise HTTPException(503,detail={'code':'FUNDING_DRAFT_BUSY'})
        await gate.acquire()
        task=asyncio.create_task(asyncio.to_thread(service.call,operation,'owner',**kwargs))
        def completed(original):
            gate.release()
            if not original.cancelled():original.exception()
        task.add_done_callback(completed)
        try:return await asyncio.shield(task)
        except FundingDraftError as error:
            raise HTTPException(error.status,detail={'code':error.code,**error.details}) from None

    @router.post('',response_model=FundingDraftReceipt)
    async def create(body:FundingDraftCreate):return await call('create',body=body.intent)

    @router.get('/{request_id}',response_model=FundingDraftView)
    async def inspect(request_id:str):return await call('inspect',request_id=request_id)

    @router.get('/{request_id}/receipt',response_model=FundingDraftReceipt)
    async def receipt(request_id:str):return await call('receipt',request_id=request_id)

    return router
