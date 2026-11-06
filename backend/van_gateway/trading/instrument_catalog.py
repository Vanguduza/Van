"""Bounded owner discovery from a provisioned original catalog source."""
import asyncio
from contextlib import closing
from pathlib import Path
import re
import time
from typing import Any,Literal

from fastapi import APIRouter,HTTPException,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,Field,StrictInt

HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
HOSTS={'DEMO':'demo.ctraderapi.com','LIVE':'live.ctraderapi.com'}
MAX_TIME=253402300799000


class InstrumentCatalogError(ValueError):
    def __init__(self,code,status=503):self.code,self.status=code,status;super().__init__(code)


class InstrumentCatalogResponse(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['vati.native-instrument-catalog-view/1']=Field(alias='schema')
    state:Literal['NO_CAPTURE','EMPTY_CATALOG','CATALOG_OBSERVED_UNQUALIFIED']
    scope:dict[str,Any]
    receipt:dict[str,Any]|None
    requested_revision:StrictInt|None
    requested_as_of_ms:StrictInt|None
    requested_record_ref:str|None
    alias:str|None
    native_symbol_id:StrictInt|None
    resolution_state:Literal['NOT_REQUESTED','SOURCE_UNAVAILABLE','NOT_FOUND','RESOLVED_NATIVE_IDENTITY','AMBIGUOUS_NATIVE_ALIAS']
    total_matches:StrictInt
    # The catalog owner independently validates every original protobuf field;
    # this envelope retains full native rows, including omitted-name records.
    members:list[dict[str,Any]]=Field(max_length=256)
    next_cursor:str|None
    coverage:Literal['REQUESTED_ARCHIVED_ROWS','ARCHIVED_COVERAGE_NOT_REQUESTED']|None
    alias_matching:Literal['EXACT_ORIGINAL_NATIVE_NAME_NO_CASE_OR_PUNCTUATION_REWRITE']
    current_tradability:Literal['NOT_EVALUATED_HISTORICAL_LISTING']
    provider_qualified:Literal[False]
    execution_authority:Literal[False]
    authority_effect:Literal['NONE']


class InstrumentCatalogErrorResponse(BaseModel):
    detail:dict[str,str]


def read_catalog(*,path,max_bytes,**query):
    if not path:raise InstrumentCatalogError('NATIVE_CATALOG_SOURCE_UNCONFIGURED')
    try:
        if not Path(path).is_absolute() or not Path(path).is_file():
            raise InstrumentCatalogError('NATIVE_CATALOG_SOURCE_UNAVAILABLE')
        from van_gateway.trading.service import _import_vati
        _import_vati()
        from vati.core.ledger import Ledger
        from vati.market_data.catalog_store import NativeCatalogStore
        from vati.market_data.instrument_catalog import discover_instruments,CatalogSelectionConflict
        environment=query.pop('environment');account=query.pop('native_account_id')
        scope={'provider':'CTRADER','environment':environment,'transport_host':HOSTS[environment],
            'native_account_id':account}
        try:
            with closing(Ledger.open_read_only(path)) as ledger:
                result=discover_instruments(NativeCatalogStore(ledger,max_bytes=max_bytes),scope,**query)
        except CatalogSelectionConflict:
            raise InstrumentCatalogError('NATIVE_CATALOG_SELECTION_CHANGED',409) from None
        return InstrumentCatalogResponse.model_validate(result).model_dump(by_alias=True)
    except InstrumentCatalogError:raise
    except Exception:
        raise InstrumentCatalogError('NATIVE_CATALOG_SOURCE_UNAVAILABLE') from None


class PrivateCatalogRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def private(request):
            try:response=await original(request)
            except HTTPException as error:
                error.headers={**(error.headers or {}),**HEADERS};raise
            except RequestValidationError:
                return JSONResponse(status_code=422,content={'detail':{'code':'NATIVE_CATALOG_QUERY_INVALID'}},headers=HEADERS)
            response.headers.update(HEADERS);return response
        return private


def _number(value,maximum,minimum=0):
    if type(value) is not str or len(value)>19 or re.fullmatch(r'(?:0|[1-9][0-9]*)',value,re.ASCII) is None:
        raise InstrumentCatalogError('NATIVE_CATALOG_QUERY_INVALID',422)
    result=int(value)
    if not minimum<=result<=maximum:raise InstrumentCatalogError('NATIVE_CATALOG_QUERY_INVALID',422)
    return result


def build_instrument_catalog_router(service):
    router=APIRouter(prefix='/v1/trading/market',tags=['trading-native-sources'],route_class=PrivateCatalogRoute,
        responses={status:{'model':InstrumentCatalogErrorResponse} for status in (409,422,503)})
    gate=asyncio.Semaphore(2)

    @router.get('/instruments',response_model=InstrumentCatalogResponse)
    async def instruments(request:Request,environment:Literal['DEMO','LIVE'],native_account_id:str,
                          revision:str|None=None,as_of_ms:str|None=None,record_ref:str|None=None,
                          alias:str|None=None,native_symbol_id:str|None=None,limit:str='100',after:str|None=None):
        try:
            allowed={'environment','native_account_id','revision','as_of_ms','record_ref','alias','native_symbol_id','limit','after'}
            if set(request.query_params)-allowed or any(len(request.query_params.getlist(k))!=1 for k in request.query_params):
                raise InstrumentCatalogError('NATIVE_CATALOG_QUERY_INVALID',422)
            account=_number(native_account_id,2**63-1,1)
            selected=None if revision is None else _number(revision,10000,1)
            boundary=None if as_of_ms is None else _number(as_of_ms,MAX_TIME)
            identity=None if native_symbol_id is None else _number(native_symbol_id,2**63-1,1)
            size=_number(limit,256,1)
            if (selected is not None and boundary is not None
                    or boundary is not None and boundary>int(time.time()*1000)
                    or record_ref is not None and re.fullmatch('[a-f0-9]{64}',record_ref,re.ASCII) is None
                    or alias is not None and (not 1<=len(alias)<=4096 or not alias.strip() or any(ord(c)<32 or ord(c)==127 for c in alias))
                    or after is not None and (len(after)>149 or re.fullmatch('[a-f0-9]{64}:[a-f0-9]{64}:[1-9][0-9]{0,18}',after,re.ASCII) is None)):
                raise InstrumentCatalogError('NATIVE_CATALOG_QUERY_INVALID',422)
            if gate.locked():raise InstrumentCatalogError('NATIVE_CATALOG_READ_BUSY')
            await gate.acquire()
            task=asyncio.create_task(asyncio.to_thread(service.instrument_catalog,environment=environment,
                native_account_id=account,revision=selected,as_of_ms=boundary,record_ref=record_ref,
                alias=alias,native_symbol_id=identity,limit=size,after=after))
            def completed(original):
                gate.release()
                if not original.cancelled():original.exception()
            task.add_done_callback(completed)
            return await asyncio.shield(task)
        except InstrumentCatalogError as error:
            raise HTTPException(error.status,detail={'code':error.code}) from None
    return router
