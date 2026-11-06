"""Owner historical source reads. No broker I/O, refresh, price or rights grant."""
import asyncio
from pathlib import Path
import re
import time
from typing import Any,Literal

from fastapi import APIRouter,HTTPException,Query,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,Field,StrictInt,model_validator

PRIVATE_HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
HOSTS={'DEMO':'demo.ctraderapi.com','LIVE':'live.ctraderapi.com'}
INTEGER=re.compile(r'(?:0|[1-9][0-9]*)',re.ASCII)
MAX_TIME=253402300799000


class DepthHistoryError(ValueError):
    def __init__(self,code,status=503):self.code,self.status=code,status;super().__init__(code)


class NativeDepthScope(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    provider:Literal['CTRADER']
    environment:Literal['DEMO','LIVE']
    transport_host:Literal['demo.ctraderapi.com','live.ctraderapi.com']
    native_account_id:StrictInt=Field(ge=1,le=2**63-1)
    native_symbol_id:StrictInt=Field(ge=1,le=2**63-1)

    @model_validator(mode='after')
    def native_host(self):
        if HOSTS[self.environment]!=self.transport_host:raise ValueError('native source realm differs')
        return self


class NativeDepthHistoryResponse(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['van.trading.native-depth-history/1']=Field(alias='schema')
    state:Literal['NO_CAPTURE','HISTORICAL_PARTIAL_DEPTH_CAPTURE_UNQUALIFIED']
    scope:NativeDepthScope
    requested_revision:StrictInt|None
    requested_as_of_ms:StrictInt|None
    # This retains the original versioned core contract/capture and receipt.
    # The actual archive owner independently validates their complete schemas.
    snapshot:dict[str,Any]|None
    current_freshness:Literal['NOT_EVALUATED_HISTORICAL_RECORD']
    normalized_prices_available:Literal[False]
    provider_qualified:Literal[False]
    authority_effect:Literal['NONE']

    @model_validator(mode='after')
    def original_capture(self):
        if (self.state=='NO_CAPTURE')!=(self.snapshot is None):raise ValueError('native depth state differs')
        if self.snapshot is not None:
            if (self.snapshot['receipt']['scope']!=self.scope.model_dump()
                    or self.snapshot['observation']['depth']['scope']!=self.scope.model_dump()):
                raise ValueError('native depth original scope differs')
        return self


class NativeDepthHistoryErrorResponse(BaseModel):
    detail:dict[str,str]


def read_history(*,root,max_history_bytes,environment,native_account_id,native_symbol_id,
                 revision=None,as_of_ms=None):
    if (type(environment) is not str or environment not in HOSTS or type(native_account_id) is not int or type(native_symbol_id) is not int
            or not 1<=native_account_id<=2**63-1 or not 1<=native_symbol_id<=2**63-1):
        raise DepthHistoryError('NATIVE_DEPTH_SCOPE_INVALID',422)
    if ((revision is not None and (type(revision) is not int or not 1<=revision<=10000))
            or (as_of_ms is not None and (type(as_of_ms) is not int or not 0<=as_of_ms<=MAX_TIME))
            or (revision is not None and as_of_ms is not None)):
        raise DepthHistoryError('NATIVE_DEPTH_SELECTOR_INVALID',422)
    if as_of_ms is not None and as_of_ms>int(time.time()*1000):
        raise DepthHistoryError('NATIVE_DEPTH_SELECTOR_FUTURE',422)
    scope=NativeDepthScope(provider='CTRADER',environment=environment,transport_host=HOSTS[environment],
        native_account_id=native_account_id,native_symbol_id=native_symbol_id)
    if not root:raise DepthHistoryError('NATIVE_DEPTH_SOURCE_UNCONFIGURED')
    try:
        if not Path(root).is_absolute() or not Path(root).is_dir():
            raise DepthHistoryError('NATIVE_DEPTH_SOURCE_UNAVAILABLE')
    except OSError:raise DepthHistoryError('NATIVE_DEPTH_SOURCE_UNAVAILABLE') from None
    try:
        from van_gateway.trading.service import _import_vati
        _import_vati()
        from vati.market_data.native_depth import NativeDepthArchive
        from vati.market_data.native_archive import NativeArchiveError
    except ImportError:raise DepthHistoryError('NATIVE_DEPTH_IMPLEMENTATION_UNAVAILABLE') from None
    try:
        # Only the provisioned server root can be read. The request supplies no
        # filesystem path, provider URL, credentials, collection or repair action.
        result=NativeDepthArchive(root,max_history_bytes=max_history_bytes).snapshot(
            scope.model_dump(),'DEPTH',revision=revision,as_of_ms=as_of_ms)
    except (NativeArchiveError,OSError,ValueError):
        raise DepthHistoryError('NATIVE_DEPTH_HISTORY_UNAVAILABLE') from None
    try:
        return NativeDepthHistoryResponse.model_validate({
            'schema':'van.trading.native-depth-history/1','state':'NO_CAPTURE' if result is None else 'HISTORICAL_PARTIAL_DEPTH_CAPTURE_UNQUALIFIED',
            'scope':scope.model_dump(),'requested_revision':revision,'requested_as_of_ms':as_of_ms,'snapshot':result,
            'current_freshness':'NOT_EVALUATED_HISTORICAL_RECORD','normalized_prices_available':False,
            'provider_qualified':False,'authority_effect':'NONE'}).model_dump(by_alias=True)
    except (KeyError,TypeError,ValueError):raise DepthHistoryError('NATIVE_DEPTH_HISTORY_UNAVAILABLE') from None


class PrivateDepthHistoryRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def private(request):
            try:response=await original(request)
            except HTTPException as error:
                error.headers={**(error.headers or {}),**PRIVATE_HEADERS};raise
            except RequestValidationError:
                return JSONResponse(status_code=422,content={'detail':{'code':'NATIVE_DEPTH_QUERY_INVALID'}},headers=PRIVATE_HEADERS)
            response.headers.update(PRIVATE_HEADERS);return response
        return private


def _number(text,maximum,*,minimum=0):
    if not isinstance(text,str) or len(text)>19 or INTEGER.fullmatch(text) is None:
        raise DepthHistoryError('NATIVE_DEPTH_QUERY_INVALID',422)
    value=int(text)
    if not minimum<=value<=maximum:raise DepthHistoryError('NATIVE_DEPTH_QUERY_INVALID',422)
    return value


def build_depth_history_router(service):
    router=APIRouter(prefix='/v1/trading/market',tags=['trading-native-sources'],route_class=PrivateDepthHistoryRoute,
        responses={status:{'model':NativeDepthHistoryErrorResponse} for status in (422,503)})
    gate=asyncio.Semaphore(2)

    @router.get('/depth-history',response_model=NativeDepthHistoryResponse)
    async def history(request:Request,environment:Literal['DEMO','LIVE'],native_account_id:str=Query(min_length=1,max_length=19),
                      native_symbol_id:str=Query(min_length=1,max_length=19),revision:str|None=None,as_of_ms:str|None=None):
        try:
            allowed={'environment','native_account_id','native_symbol_id','revision','as_of_ms'}
            if set(request.query_params)-allowed or any(len(request.query_params.getlist(k))!=1 for k in request.query_params):
                raise DepthHistoryError('NATIVE_DEPTH_QUERY_INVALID',422)
            account=_number(native_account_id,2**63-1,minimum=1);symbol=_number(native_symbol_id,2**63-1,minimum=1)
            selected=_number(revision,10000,minimum=1) if revision is not None else None
            boundary=_number(as_of_ms,MAX_TIME) if as_of_ms is not None else None
            if selected is not None and boundary is not None:raise DepthHistoryError('NATIVE_DEPTH_SELECTOR_INVALID',422)
            if gate.locked():raise DepthHistoryError('NATIVE_DEPTH_HISTORY_BUSY')
            await gate.acquire()
            task=asyncio.create_task(asyncio.to_thread(service.native_depth_history,environment=environment,
                native_account_id=account,native_symbol_id=symbol,revision=selected,as_of_ms=boundary))
            def completed(original):
                gate.release()
                if not original.cancelled():original.exception()
            task.add_done_callback(completed)
            # A disconnected caller must not release capacity while its original
            # file verification is still running. No replacement worker is made.
            return await asyncio.shield(task)
        except DepthHistoryError as error:
            raise HTTPException(error.status,detail={'code':error.code}) from None
    return router
