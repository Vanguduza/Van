"""Existing account_remove pending-cleanup variant and distinct reauth DATA roles.

No provider effect is initiated here. One gateway SQL winner admits a new native
child; native outcome/resolution remain independently owned facts. Original
UNKNOWN/result=None is never rewritten or silently repeated.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import threading
import time
from typing import Literal

from fastapi import APIRouter,Request,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator

from van_gateway.approval.account_reauth import AccountReauthentication,ReauthError,ACTION,ADMISSIONS,EPHEMERAL,USED,digest
from van_gateway.approval.service import OwnerApprovalService,OwnerApprovalError
from van_gateway.trading.accounts import account_approval_text,LocalAccountControl,MAX_AGE_S
from van_gateway.trading.account_contracts import AccountCleanupReview,AccountCleanupSummary
from van_gateway.models import OwnerApprovalProof

HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
HASH=r'^[0-9a-f]{64}$'
ID=r'^[A-Za-z0-9_-]{20,128}$'


class CleanupArgs(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    alias:str=Field(pattern=r'^[a-z0-9_]{3,32}$')
    variant:Literal['PENDING_CLEANUP']
    parent_operation_id:str=Field(pattern=ID)
    plan_ref:str=Field(pattern=HASH)
    retire_parent_safety_obligation:bool
    reauth_fact_id:str|None=Field(default=None,pattern=ID)
    reauth_fact_digest:str|None=Field(default=None,pattern=HASH)
    @model_validator(mode='after')
    def both_fact_fields(self):
        if (self.reauth_fact_id is None)!=(self.reauth_fact_digest is None):raise ValueError('Original reauth fact incomplete')
        return self


class ReauthRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    device_id:str=Field(min_length=1,max_length=256)
    issued_at_unix:int
    signature:str=Field(min_length=32,max_length=256)
    action:Literal['account_remove']
    args:dict
    approval_proof:OwnerApprovalProof|None=None


class AccountCleanup:
    def __init__(self,store,onboarding,authenticate,authorize,*,clock=None):
        self.store,self.onboarding,self.authenticate,self.authorize=store,onboarding,authenticate,authorize
        self.reauth=AccountReauthentication(store,authorize,clock=clock)
        self.clock=clock or (lambda:int(time.time()))
        self.tasks=set()

    @staticmethod
    def arguments(args,*,with_fact=None):
        try:body=CleanupArgs.model_validate(args)
        except ValidationError:raise ReauthError('CLEANUP_INPUT_INVALID',422) from None
        values=body.model_dump(exclude_none=True)
        if with_fact is not None and (body.reauth_fact_id is not None)!=with_fact:raise ReauthError('CLEANUP_PURPOSE_INPUT_MISMATCH',422)
        return values

    @staticmethod
    def caller(request,req):
        return {'owner_id':'owner','device_id':req.device_id,
            'access_token_hash':hashlib.sha256(request.headers.get('X-Van-Device-Token','').encode()).hexdigest(),
            'proved':bool(getattr(request.state,'van_device_proved',False)),
            'verified_binding_identity':getattr(request.state,'van_device_proof_binding_identity',None),
            'request_deadline':req.issued_at_unix+MAX_AGE_S}

    def _read_guard(self,caller,loop,cancelled):
        def guard():
            if cancelled.is_set():raise HTTPException(409,'Cleanup request cancelled before native effect')
            async def verify_current():
                async with self.store.connection() as db:
                    await db.execute('BEGIN')
                    try:return await self.authorize(db,caller)
                    finally:await db.rollback()
            future=asyncio.run_coroutine_threadsafe(verify_current(),loop)
            try:future.result(timeout=5)
            except BaseException:
                future.cancel()
                raise HTTPException(403,'Current cleanup owner scope unavailable; HOLD') from None
            if self.clock()>=caller['request_deadline']:raise HTTPException(403,'Current cleanup request expired')
        return guard

    async def _finish(self,coroutine,cancelled):
        task=asyncio.create_task(coroutine);self.tasks.add(task);task.add_done_callback(self.tasks.discard)
        try:return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            while not task.done():
                try:await asyncio.shield(task)
                except asyncio.CancelledError:continue
                except Exception:break
            if task.done() and not task.cancelled():task.exception()
            raise

    async def review(self,request,req,*,with_fact=None,cancelled=None):
        args=self.arguments(req.args,with_fact=with_fact);caller=self.caller(request,req)
        cancelled=cancelled or threading.Event();loop=asyncio.get_running_loop()
        guard=self._read_guard(caller,loop,cancelled)
        control=self.onboarding.control
        method=getattr(control,'cleanup_review',None)
        if not callable(method):raise ReauthError('CLEANUP_NATIVE_REVIEW_UNAVAILABLE',503)
        try:review=await asyncio.to_thread(method,args,req.device_id,guard)
        except HTTPException as error:raise ReauthError('CLEANUP_NATIVE_HOLD',error.status_code) from None
        except (OSError,TimeoutError,ConnectionError):raise ReauthError('CLEANUP_NATIVE_UNAVAILABLE',503) from None
        try:
            AccountCleanupReview.model_validate(review)
            view=review['view']
            if (review['request_digest']!=digest(args) or review['context_digest']!=digest(view)
                    or review['review_digest']!=digest({k:v for k,v in review.items() if k!='review_digest'})
                    or view['alias']!=args['alias'] or view['parent_operation_id']!=args['parent_operation_id']
                    or view['plan_ref']!=args['plan_ref'] or view['original_device_id']!=req.device_id
                    or view['original_account']['alias']!=args['alias']
                    or view['retire_parent_safety_obligation']!=args['retire_parent_safety_obligation']):raise ValueError()
        except (ValidationError,KeyError,TypeError,ValueError):raise ReauthError('CLEANUP_NATIVE_REVIEW_UNVERIFIED',503) from None
        selected=request.headers.get('X-Van-Account-Control-Domain')
        if selected is not None and selected!=view['account_control_domain']:raise ReauthError('CLEANUP_DOMAIN_CHANGED')
        context={k:view[k] for k in ('alias','parent_operation_id','plan_ref','account_control_domain','original_device_id',
                                     'remaining_steps','retire_parent_safety_obligation')}
        context.update(review_digest=review['context_digest'],resource_version=review['resource_version'])
        return args,caller,review,context,guard

    async def issue_reauth(self,request,req):
        await self.authenticate(request,req)
        args,caller,review,context,_=await self.review(request,req,with_fact=False)
        result=await self.reauth.issue(caller,context)
        return {**result,'resolved_review':review}

    async def verify_reauth(self,request,req):
        await self.authenticate(request,req)
        if req.approval_proof is None or req.approval_proof.algorithm!=OwnerApprovalService.ALGORITHM:
            raise ReauthError('CLEANUP_REAUTH_PROOF_REQUIRED',403)
        _,caller,_,context,_=await self.review(request,req,with_fact=False)
        return await self.reauth.verify(caller,context,req.approval_proof.challenge_id,req.approval_proof.signature_b64)

    async def challenge(self,request,req):
        args,caller,review,context,_=await self.review(request,req,with_fact=True)
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor=await self.reauth.current_actor(db,caller)
                fact=await self.reauth.require_fact(db,caller,context,args['reauth_fact_id'],actor)
                if fact['fact_digest']!=args['reauth_fact_digest']:raise ReauthError('CLEANUP_REAUTH_FACT_CHANGED')
                text=account_approval_text(req.device_id,req.issued_at_unix,'account_remove',args,review['resource_version'],context['account_control_domain'])
                parameters={'cleanup_review':review,'reauth_fact_digest':fact['fact_digest']}
                issued=await self.reauth.approvals.issue(device_id=req.device_id,source_command_id='account:account_remove',
                    turn_id=None,action_id=ACTION,text=text,project_id=None,parameters=parameters,
                    ttl_seconds=OwnerApprovalService.DEFAULT_TTL_SECONDS,_expiry_cap=min(fact['expires_at_unix'],caller['request_deadline']),_db=db)
                await db.commit()
            except BaseException:await db.rollback();raise
        return {'approval_challenge_id':issued.challenge_id,'approval_challenge':issued.canonical,
            'issued_at_unix':req.issued_at_unix,'approval_expires_at_unix':issued.expires_at_unix,
            'resolved_action_id':ACTION,'resolved_review':review,'account_control_domain':context['account_control_domain']}

    async def action(self,request,req):
        cancelled=threading.Event()
        return await self._finish(self._action(request,req,cancelled),cancelled)

    async def _original_replay(self,request,req,proof):
        """Read the immutable exact admission; never select or dispatch a child."""
        row=await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+proof.challenge_id,))
        if row is not None:
            try:
                original=json.loads(row['value'])
                self.arguments(req.args,with_fact=True)
                expected=digest({'context':original['context'],'fact_id':req.args['reauth_fact_id'],
                    'challenge_id':proof.challenge_id,'text_digest':digest(account_approval_text(req.device_id,req.issued_at_unix,'account_remove',req.args,
                        original['context']['resource_version'],original['context']['account_control_domain'])),
                    'parameters_digest':original['approval_parameters_digest']})
                if original['admission_digest']!=digest({k:v for k,v in original.items() if k!='admission_digest'}):raise ValueError()
                if original['request_digest']!=expected or original['device_id']!=req.device_id:raise ValueError()
                selected=request.headers.get('X-Van-Account-Control-Domain')
                if selected is not None and selected!=original['context']['account_control_domain']:raise ReauthError('CLEANUP_DOMAIN_CHANGED')
            except (ValueError,TypeError,KeyError):raise ReauthError('CLEANUP_ORIGINAL_ADMISSION_CONFLICT') from None
            async with self.store.connection() as db:
                await db.execute('BEGIN');
                try:await self.authorize(db,self.caller(request,req))
                finally:await db.rollback()
            return await self.read_child(original)
        return None

    async def _action(self,request,req,cancelled):
        proof=req.approval_proof
        if proof is None or proof.algorithm!=OwnerApprovalService.ALGORITHM:raise ReauthError('CLEANUP_ACTION_PROOF_REQUIRED',403)
        # Exact original admission replay is read-only, before any fresh target
        # selection. It never submits a second native request.
        replay=await self._original_replay(request,req,proof)
        if replay is not None:return replay
        try:
            args,caller,review,context,guard=await self.review(request,req,with_fact=True,cancelled=cancelled)
        except ReauthError:
            # A concurrent winner can commit while this exact request waits on
            # the native review. Changed current target is never a new selection
            # or a contradictory result for that already-owned original.
            replay=await self._original_replay(request,req,proof)
            if replay is not None:return replay
            raise
        replay=await self._original_replay(request,req,proof)
        if replay is not None:return replay
        text=account_approval_text(req.device_id,req.issued_at_unix,'account_remove',args,review['resource_version'],context['account_control_domain'])
        parameters={'cleanup_review':review,'reauth_fact_digest':args['reauth_fact_digest']}
        admitted,winner=await self.reauth.admit(caller,context,args['reauth_fact_id'],challenge_id=proof.challenge_id,
            signature_b64=proof.signature_b64,text=text,parameters=parameters,current_request_deadline=caller['request_deadline'])
        if not winner:return await self.read_child(admitted)
        native_args={**args,'_expected_resource_version':review['resource_version'],'_expected_review_digest':review['review_digest'],
            '_expected_account_control_domain':context['account_control_domain'],
            '_native_operation':{'operation_id':admitted['operation_id'],'device_id':req.device_id,
                'request_digest':digest(args),'authority_ref':admitted['authority_ref']+'::review:'+review['review_digest'],
                'expires_at_unix':admitted['expires_at_unix']}}
        if isinstance(self.onboarding.control,LocalAccountControl):native_args['_account_dispatch_guard']=guard
        if cancelled.is_set():return await self.read_child(admitted)
        # Admission is already durable BEFORE any uncertain native call. Only
        # this single SQL winner sends; repeat/unknown callers only read original.
        try:
            await asyncio.to_thread(guard)
            await asyncio.to_thread(self.onboarding.control.run,'account_remove',native_args)
        except HTTPException:pass  # Exact original native readback owns the outcome.
        except (OSError,TimeoutError,ConnectionError):pass
        return await self.read_child(admitted)

    def read_caller(self,request):
        device=getattr(request.state,'van_device_id',None)
        if not isinstance(device,str) or not device:raise ReauthError('CLEANUP_CURRENT_OWNER_REFUSED',403)
        return {'owner_id':'owner','device_id':device,
            'access_token_hash':hashlib.sha256(request.headers.get('X-Van-Device-Token','').encode()).hexdigest()}

    async def read_admission(self,request,operation_id):
        caller=self.read_caller(request)
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            try:
                await self.authorize(db,caller,False)
                row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+operation_id,))).fetchone()
                if row is None:raise ReauthError('CLEANUP_ORIGINAL_ADMISSION_UNAVAILABLE',404)
                try:
                    record=json.loads(row['value'])
                    if (record['operation_id']!=operation_id or record['device_id']!=caller['device_id'] or record['owner_id']!='owner'
                            or record['admission_digest']!=digest({k:v for k,v in record.items() if k!='admission_digest'})):raise ValueError()
                    selected=request.headers.get('X-Van-Account-Control-Domain')
                    if selected is not None and selected!=record['context']['account_control_domain']:raise ReauthError('CLEANUP_DOMAIN_CHANGED')
                except (KeyError,TypeError,ValueError):raise ReauthError('CLEANUP_ORIGINAL_ADMISSION_UNKNOWN',503) from None
            finally:await db.rollback()
        return await self.read_child(record)

    async def read_fact(self,request,fact_id):
        caller=self.read_caller(request)
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            try:
                await self.authorize(db,caller,False)
                raw=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+fact_id,))).fetchone()
                used=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(USED+fact_id,))).fetchone()
                if raw is not None:
                    try:
                        fact=json.loads(raw['value']);proof=fact.pop('fact_digest')
                        if (fact['owner_id']!='owner' or fact['device_id']!=caller['device_id'] or proof!=digest(fact)
                                or fact['execution_authority'] is not False or type(fact['expires_at_unix']) is not int):raise ValueError()
                    except (KeyError,TypeError,ValueError):raise ReauthError('CLEANUP_REAUTH_FACT_UNKNOWN',503) from None
                    return {'reauth_fact_id':fact_id,'fact_digest':proof,'expires_at_unix':fact['expires_at_unix'],
                        'state':'EXPIRED' if self.clock()>=fact['expires_at_unix'] else 'UNSPENT_DATA','execution_authority':False}
                if used is not None:
                    try:
                        data=json.loads(used['value'])
                        if data['owner_id']!='owner' or data['device_id']!=caller['device_id']:raise ValueError()
                    except (KeyError,TypeError,ValueError):raise ReauthError('CLEANUP_REAUTH_FACT_UNKNOWN',503) from None
                    return {'reauth_fact_id':fact_id,'fact_digest':data['fact_digest'],'state':'SPENT_DATA',
                            'child_operation_id':data['child_operation_id'],'execution_authority':False}
                raise ReauthError('CLEANUP_REAUTH_FACT_UNAVAILABLE',404)
            finally:await db.rollback()

    async def read_child(self,admitted):
        context=admitted['context'];control=self.onboarding.control
        async def read(operation):
            try:
                value=await asyncio.to_thread(control.operation,operation,admitted['device_id'],context['account_control_domain'])
                required={'operation_id','action','effect_state','native_phase','reconciliation_required','result','native_event_ref','account_control_domain'}
                if (not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'cleanup_recovery'}
                        or value['operation_id']!=operation or value['action']!='account_remove'
                        or value['account_control_domain']!=context['account_control_domain']
                        or not isinstance(value['native_event_ref'],str) or __import__('re').fullmatch(HASH,value['native_event_ref']) is None
                        or value['native_phase'] not in {'IN_FLIGHT','UNKNOWN','APPLIED','REFUSED'}
                        or value['effect_state']!=('UNKNOWN' if value['native_phase']=='IN_FLIGHT' else value['native_phase'])
                        or value['reconciliation_required'] is not (value['effect_state']=='UNKNOWN')):return None
                if value['effect_state']=='UNKNOWN' and value['result'] is not None:return None
                if value['effect_state'] in {'APPLIED','REFUSED'} and not isinstance(value['result'],dict):return None
                if value['effect_state']=='APPLIED' and operation==admitted['operation_id']:
                    result=value['result']
                    if (set(result)!={'alias','removed','cleanup_parent_operation_id','plan_ref','postcondition_ref','remote_account_closed',
                            'historical_data_retained','retained_remote_funds','credential_cleanup','parent_original_unchanged'}
                            or result['alias']!=context['alias'] or result['removed'] is not True
                            or result['cleanup_parent_operation_id']!=context['parent_operation_id'] or result['plan_ref']!=context['plan_ref']
                            or result['remote_account_closed'] is not False or result['historical_data_retained'] is not True
                            or result['parent_original_unchanged'] is not True):return None
                if 'cleanup_recovery' in value:
                    AccountCleanupSummary.model_validate(value['cleanup_recovery'])
                    if (value['cleanup_recovery']['parent_operation_id']!=context['parent_operation_id']
                            or value['cleanup_recovery']['plan_ref']!=context['plan_ref']):return None
                return value
            except (HTTPException,OSError,TimeoutError,ConnectionError,ValidationError,KeyError,TypeError,ValueError):return None
        parent,child=await asyncio.gather(read(context['parent_operation_id']),read(admitted['operation_id']))
        resolution=(parent or {}).get('cleanup_recovery',{}).get('linked_resolution_ref')
        return {'schema':'van.account-pending-cleanup/1','operation_id':admitted['operation_id'],
            'resolution_state':('QUALIFIED_SEPARATE_FACT' if resolution else 'HELD') if context['retire_parent_safety_obligation'] else 'NOT_REQUESTED',
            'linked_resolution_ref':resolution,
            'resolution_child_operation_id':(parent or {}).get('cleanup_recovery',{}).get('linked_resolution_child_operation_id'),
            'gateway_admission':'ADMITTED_NOT_NATIVE_COMPLETION','original_parent':parent,
            'parent_state':'UNRESOLVED' if parent is None else parent['effect_state'],
            'child':child,'child_state':'UNRESOLVED' if child is None else child['effect_state'],
            'execution_authority':False,'automatic_resend_permitted':False}


def _distinct(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError()
        result[k]=v
    return result


class PrivateCleanupRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handle(request):
            try:
                if request.query_params:raise ReauthError('CLEANUP_INPUT_INVALID',422)
                raw=await request.body()
                if len(raw)>8192:raise ReauthError('CLEANUP_INPUT_CAPACITY',413)
                if request.method!='GET':
                    try:json.loads(raw,object_pairs_hook=_distinct,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
                    except (ValueError,RecursionError):raise ReauthError('CLEANUP_INPUT_INVALID',422) from None
                response=await original(request);response.headers.update(HEADERS);return response
            except ReauthError as error:
                headers={**HEADERS,**({'Retry-After':str(error.retry_after)} if error.retry_after else {})}
                return JSONResponse(status_code=error.status,content={'detail':{'code':error.code,'locked_until':error.locked_until,'retry_after':error.retry_after}},headers=headers)
            except HTTPException as error:
                error.headers={**(error.headers or {}),**HEADERS}
                raise
            except RequestValidationError:
                return JSONResponse(status_code=422,content={'detail':{'code':'CLEANUP_INPUT_INVALID'}},headers=HEADERS)
        return handle


def build_account_cleanup_router(service):
    router=APIRouter(prefix='/v1/trading/accounts/cleanup/reauth',route_class=PrivateCleanupRoute,tags=['account-cleanup'])
    @router.post('/challenge')
    async def challenge(request:Request,body:ReauthRequest):return await service.issue_reauth(request,body)
    @router.post('/verify')
    async def verify(request:Request,body:ReauthRequest):return await service.verify_reauth(request,body)
    @router.get('/facts/{fact_id}')
    async def fact(request:Request,fact_id:str):
        if __import__('re').fullmatch(ID,fact_id) is None:raise ReauthError('CLEANUP_INPUT_INVALID',422)
        return await service.read_fact(request,fact_id)
    return router


def build_cleanup_operation_router(service):
    router=APIRouter(prefix='/v1/trading/accounts/cleanup/operations',route_class=PrivateCleanupRoute,tags=['account-cleanup'])
    @router.get('/{operation_id}')
    async def original(request:Request,operation_id:str):
        if __import__('re').fullmatch(ID,operation_id) is None:raise ReauthError('CLEANUP_INPUT_INVALID',422)
        return await service.read_admission(request,operation_id)
    return router
