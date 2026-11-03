"""Typed paired-owner lifecycle source composition; no provider effect or issuer.

Separate purpose-bound reauthentication DATA and substantive A4 admission use the
existing Store writer/enrolled verifier. Native effects and SQL are separate
commit owners: uncertain admissions are read, never blindly sent again.
"""
import asyncio,threading,json,time
from types import SimpleNamespace
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from fastapi import APIRouter,Request,HTTPException
from van_gateway.approval.account_lifecycle_reauth import AccountLifecycleReauthentication,ReauthError,ACTION,ADMISSIONS,EPHEMERAL,USED,digest
from van_gateway.approval.service import OwnerApprovalService
from van_gateway.trading.account_cleanup_api import AccountCleanup,ReauthRequest,PrivateCleanupRoute
from van_gateway.trading.account_contracts import AccountLifecycleReview,AccountLifecycleState
from van_gateway.trading.accounts import LocalAccountControl,account_approval_text
from van_gateway.trading.oauth_effects import fingerprint

VARIANTS={'DELETE_GRACE','CANCEL_DELETE','IMMEDIATE_DISCONNECT'}
HASH=r'^[0-9a-f]{64}$'

class DeleteArgs(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    alias:str=Field(pattern=r'^[a-z0-9_]{3,32}$')
    variant:Literal['DELETE_GRACE']
    grace_seconds:int=Field(gt=0,lt=2**31)
    oauth_discard_digest:str=Field(pattern=HASH)
    reauth_fact_id:str|None=None
    reauth_fact_digest:str|None=Field(default=None,pattern=HASH)

class DisconnectArgs(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    alias:str=Field(pattern=r'^[a-z0-9_]{3,32}$')
    variant:Literal['IMMEDIATE_DISCONNECT']
    oauth_discard_digest:str=Field(pattern=HASH)
    reauth_fact_id:str|None=None
    reauth_fact_digest:str|None=Field(default=None,pattern=HASH)

class CancelArgs(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    alias:str=Field(pattern=r'^[a-z0-9_]{3,32}$')
    variant:Literal['CANCEL_DELETE']
    lifecycle_id:str=Field(min_length=20,max_length=128)
    expected_revision:int=Field(gt=0)
    expected_digest:str=Field(pattern=HASH)
    reauth_fact_id:str|None=None
    reauth_fact_digest:str|None=Field(default=None,pattern=HASH)

def semantic(args):return {k:v for k,v in args.items() if k not in {'reauth_fact_id','reauth_fact_digest'}}

class AccountLifecycle(AccountCleanup):
    def __init__(self,store,onboarding,authenticate,authorize,*,clock=None):
        super().__init__(store,onboarding,authenticate,authorize,clock=clock)
        self.reauth=AccountLifecycleReauthentication(store,authorize,clock=clock)
        self._native_callers={}
        self.bind_local_admission_verifier()

    def bind_local_admission_verifier(self):
        control=self.onboarding.control
        if isinstance(control,LocalAccountControl):
            control.settings.lifecycle_admission_verifier=self.verify_local_admission

    def verify_local_admission(self,args):
        # This bound service method is configured on the native settings during
        # trusted composition. Neither a request label nor a callback in args
        # can select its Store, enrolled verifier, principal, or original row.
        try:
            record=args['_lifecycle_admission']
            admitted,caller,guard,loop=self._native_callers[record['operation_id']]
            if admitted!=record:raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise HTTPException(403,'Current durable lifecycle admission unavailable') from None
        async def current():
            async with self.store.connection() as db:
                await db.execute('BEGIN')
                try:
                    actor=await self.reauth.current_actor(db,caller)
                    saved=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                        (ADMISSIONS+admitted['operation_id'],))).fetchone()
                    if (saved is None or json.loads(saved['value'])!=admitted
                        or actor!=admitted['actor_key_ref'] or self.reauth.clock()>=admitted['expires_at_unix']):
                        raise HTTPException(403,'Current durable lifecycle admission unavailable')
                finally:await db.rollback()
        pending=asyncio.run_coroutine_threadsafe(current(),loop)
        try:pending.result(5)
        except BaseException:
            pending.cancel();raise HTTPException(403,'Current durable lifecycle admission unavailable') from None
        guard()
        return admitted
    @staticmethod
    def arguments(args,*,with_fact=None):
        try:
            model={'DELETE_GRACE':DeleteArgs,'CANCEL_DELETE':CancelArgs,'IMMEDIATE_DISCONNECT':DisconnectArgs}.get(args.get('variant'),CancelArgs)
            body=model.model_validate(args)
        except (ValidationError,AttributeError):raise ReauthError('LIFECYCLE_INPUT_INVALID',422) from None
        values=body.model_dump(exclude_none=True)
        if ('reauth_fact_id' in values)!=('reauth_fact_digest' in values) or with_fact is not None and ('reauth_fact_id' in values)!=with_fact:
            raise ReauthError('LIFECYCLE_PURPOSE_INPUT_MISMATCH',422)
        return values
    async def prepare(self,request,req):
        await self.authenticate(request,req)
        raw=dict(req.args)
        if (raw.get('variant') not in {'DELETE_GRACE','IMMEDIATE_DISCONNECT'} or set(raw)!=({'alias','variant','grace_seconds'} if raw.get('variant')=='DELETE_GRACE' else {'alias','variant'})):
            raise ReauthError('LIFECYCLE_INPUT_INVALID',422)
        # Pairing and current policy checked before any private native read.
        caller=self.caller(request,req)
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            try:await self.authorize(db,caller)
            finally:await db.rollback()
        domain=await asyncio.to_thread(self.onboarding.control.domain)
        plan=await self.onboarding.pending.effects.lifecycle_plan(raw['alias'],req.device_id,domain)
        raw['oauth_discard_digest']=fingerprint(plan)
        args=self.arguments(raw,with_fact=False)
        return {'args':args,'oauth_scope':plan,'execution_authority':False,'OQ15_policy_acceptance':'NOT_ISSUED'}
    async def review(self,request,req,*,with_fact=None,cancelled=None):
        args=self.arguments(req.args,with_fact=with_fact);caller=self.caller(request,req)
        guard=self._read_guard(caller,asyncio.get_running_loop(),cancelled or threading.Event())
        domain=await asyncio.to_thread(self.onboarding.control.domain)
        selected=request.headers.get('X-Van-Account-Control-Domain')
        if selected is not None and selected!=domain:raise ReauthError('LIFECYCLE_DOMAIN_CHANGED')
        if args['variant'] in {'DELETE_GRACE','IMMEDIATE_DISCONNECT'}:
            plan=await self.onboarding.pending.effects.lifecycle_plan(args['alias'],req.device_id,domain)
            if fingerprint(plan)!=args['oauth_discard_digest']:raise ReauthError('LIFECYCLE_OAUTH_SCOPE_CHANGED')
        control=self.onboarding.control
        payload={'action':'account_remove','args':args,'owner_device_id':req.device_id}
        if isinstance(control,LocalAccountControl):payload['_account_dispatch_guard']=guard
        review=await asyncio.to_thread(control.run,'account_review',payload)
        try:
            parsed=AccountLifecycleReview.model_validate(review)
            if (review['semantic_digest']!=digest(semantic(args)) or review['request_digest']!=digest(args)
                or review['view']['account_control_domain']!=domain or review['view']['owner_device_id']!=req.device_id
                or review['context_digest']!=digest({k:v for k,v in review.items() if k not in {'context_digest','review_digest','request_digest'}})):
                raise ValueError()
            if args['variant'] in {'DELETE_GRACE','IMMEDIATE_DISCONNECT'}:
                unlink=review['view']['unlink_review']
                if review['review_digest']!=unlink['review_digest'] or unlink['review_digest']!=digest({k:v for k,v in unlink.items() if k!='review_digest'}):raise ValueError()
            elif review['review_digest']!=digest({k:v for k,v in review.items() if k not in {'review_digest','request_digest'}}):raise ValueError()
        except (ValidationError,ValueError,KeyError,TypeError):raise ReauthError('LIFECYCLE_NATIVE_REVIEW_UNVERIFIED',503) from None
        original=(review['view'].get('original') or {})
        context={'alias':args['alias'],'lifecycle_id':args.get('lifecycle_id','proposed:'+review['resource_version']),
            'incarnation':review['view'].get('incarnation',original.get('incarnation')),
            'account_control_domain':domain,'original_device_id':req.device_id,'review_digest':review['context_digest'],
            'resource_version':review['resource_version'],'variant':args['variant'],'semantic_digest':review['semantic_digest']}
        return args,caller,review,context,guard
    async def issue_reauth(self,request,req):
        await self.authenticate(request,req)
        _,caller,review,context,_=await self.review(request,req,with_fact=False)
        return {**await self.reauth.issue(caller,context),'resolved_review':review}
    async def verify_reauth(self,request,req):
        await self.authenticate(request,req)
        if req.approval_proof is None or req.approval_proof.algorithm!=OwnerApprovalService.ALGORITHM:
            raise ReauthError('LIFECYCLE_REAUTH_PROOF_REQUIRED',403)
        _,caller,_,context,_=await self.review(request,req,with_fact=False)
        return await self.reauth.verify(caller,context,req.approval_proof.challenge_id,req.approval_proof.signature_b64)
    async def challenge(self,request,req):
        args,caller,review,context,_=await self.review(request,req,with_fact=True)
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor=await self.reauth.current_actor(db,caller)
                fact=await self.reauth.require_fact(db,caller,context,args['reauth_fact_id'],actor)
                if fact['fact_digest']!=args['reauth_fact_digest']:raise ReauthError('LIFECYCLE_REAUTH_FACT_CHANGED')
                text=account_approval_text(req.device_id,req.issued_at_unix,'account_remove',args,review['resource_version'],context['account_control_domain'])
                parameters={'lifecycle_review':review,'reauth_fact_digest':fact['fact_digest']}
                issued=await self.reauth.approvals.issue(device_id=req.device_id,source_command_id='account:account_remove',
                    turn_id=None,action_id=ACTION,text=text,project_id=None,parameters=parameters,
                    ttl_seconds=OwnerApprovalService.DEFAULT_TTL_SECONDS,_expiry_cap=min(fact['expires_at_unix'],caller['request_deadline']),_db=db)
                await db.commit()
            except BaseException:await db.rollback();raise
        return {'approval_challenge_id':issued.challenge_id,'approval_challenge':issued.canonical,
            'issued_at_unix':req.issued_at_unix,'approval_expires_at_unix':issued.expires_at_unix,
            'resolved_action_id':ACTION,'resolved_review':review,'account_control_domain':context['account_control_domain']}
    async def _action(self,request,req,cancelled):
        proof=req.approval_proof
        if proof is None or proof.algorithm!=OwnerApprovalService.ALGORITHM:raise ReauthError('LIFECYCLE_ACTION_PROOF_REQUIRED',403)
        original=await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+proof.challenge_id,))
        if original is not None:
            old=json.loads(original['value']);self.arguments(req.args,with_fact=True)
            expected=digest({'context':old['context'],'fact_id':req.args['reauth_fact_id'],'challenge_id':proof.challenge_id,
                'text_digest':digest(account_approval_text(req.device_id,req.issued_at_unix,'account_remove',req.args,
                    old['context']['resource_version'],old['context']['account_control_domain'])),
                'parameters_digest':old['approval_parameters_digest']})
            if old['admission_digest']!=digest({k:v for k,v in old.items() if k!='admission_digest'}) or old['device_id']!=req.device_id or old['request_digest']!=expected:
                raise ReauthError('LIFECYCLE_ORIGINAL_ADMISSION_CONFLICT')
            caller=self.caller(request,req)
            async with self.store.connection() as db:
                await db.execute('BEGIN')
                try:await self.authorize(db,caller)
                finally:await db.rollback()
            domain=request.headers.get('X-Van-Account-Control-Domain')
            if domain is not None and domain!=old['context']['account_control_domain']:raise ReauthError('LIFECYCLE_DOMAIN_CHANGED')
            return await self.read_child(old)
        try:args,caller,review,context,guard=await self.review(request,req,with_fact=True,cancelled=cancelled)
        except (ReauthError,HTTPException):
            won=await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+proof.challenge_id,))
            if won is not None:return await self._action(request,req,cancelled)
            raise
        text=account_approval_text(req.device_id,req.issued_at_unix,'account_remove',args,review['resource_version'],context['account_control_domain'])
        parameters={'lifecycle_review':review,'reauth_fact_digest':args['reauth_fact_digest']}
        admitted,winner=await self.reauth.admit(caller,context,args['reauth_fact_id'],challenge_id=proof.challenge_id,
            signature_b64=proof.signature_b64,text=text,parameters=parameters,current_request_deadline=caller['request_deadline'])
        if not winner:return await self.read_child(admitted)
        native={**args,'_lifecycle_admission':admitted,'_expected_resource_version':review['resource_version'],'_expected_review_digest':review['review_digest'],
            '_expected_lifecycle_context_digest':review['context_digest'],
            '_expected_account_control_domain':context['account_control_domain'],
            '_native_operation':{'operation_id':admitted['operation_id'],'device_id':req.device_id,'request_digest':digest(args),
                'authority_ref':admitted['authority_ref']+'::review:'+review['review_digest'],'expires_at_unix':admitted['expires_at_unix']}}
        if isinstance(self.onboarding.control,LocalAccountControl):native['_account_dispatch_guard']=guard
        if cancelled.is_set():return await self.read_child(admitted)
        self._native_callers[admitted['operation_id']]=(admitted,caller,guard,asyncio.get_running_loop())
        # SQL winner first, discard only exact independently observed OAuth state.
        # A failed/lost native submission is NEVER retried by a replay.
        try:
            await asyncio.to_thread(guard)
            # Recheck the admitted current native scope before Gateway's first
            # local OAuth effect. A changed resource never reaches discard.
            _,_,fresh,_,_=await self.review(request,req,with_fact=True,cancelled=cancelled)
            if fresh!=review:raise HTTPException(409,'Lifecycle review changed before OAuth discard')
            if args['variant'] in {'DELETE_GRACE','IMMEDIATE_DISCONNECT'}:
                stamp=await self.onboarding.pending.effects.lifecycle_discard(args['alias'],req.device_id,context['account_control_domain'],args['oauth_discard_digest'])
                native['_lifecycle_oauth']={'digest':stamp,'request_digest':digest(semantic(args))}
            await asyncio.to_thread(guard)
            await asyncio.to_thread(self.onboarding.control.run,'account_remove',native)
        except (HTTPException,OSError,TimeoutError,ConnectionError):pass
        finally:self._native_callers.pop(admitted['operation_id'],None)
        return await self.read_child(admitted)
    async def read_child(self,admitted):
        try:
            value=await asyncio.to_thread(self.onboarding.control.operation,admitted['operation_id'],admitted['device_id'],admitted['context']['account_control_domain'])
            import re
            if (value['operation_id']!=admitted['operation_id'] or value['account_control_domain']!=admitted['context']['account_control_domain']
                    or value['action']!='account_remove' or value['native_phase'] not in {'IN_FLIGHT','UNKNOWN','APPLIED','REFUSED'}
                    or value['effect_state']!=('UNKNOWN' if value['native_phase']=='IN_FLIGHT' else value['native_phase'])
                    or value['reconciliation_required'] is not (value['effect_state']=='UNKNOWN')
                    or not isinstance(value['native_event_ref'],str) or re.fullmatch(HASH,value['native_event_ref']) is None
                    or value['effect_state']=='UNKNOWN' and value['result'] is not None
                    or value['effect_state'] in {'APPLIED','REFUSED'} and not isinstance(value['result'],dict)):
                raise ValueError()
            if value['effect_state']=='APPLIED':
                result=value['result'];row=result['lifecycle'];public_lifecycle=AccountLifecycleState.model_validate(row).model_dump(by_alias=True)
                context=admitted['context'];deletion=context['variant'] in {'DELETE_GRACE','IMMEDIATE_DISCONNECT'}
                if (row['alias']!=context['alias'] or row['account_control_domain']!=context['account_control_domain']
                        or row['operation_id']!=(admitted['operation_id'] if deletion else context['lifecycle_id'])
                        or row['phase']!=('DISCONNECTED' if context['variant']=='IMMEDIATE_DISCONNECT' else 'PENDING_ARCHIVE' if deletion else 'RELINK_REQUIRED')
                        or result['removed'] is not deletion or result['remote_account_closed'] is not False
                        or result['historical_data_retained'] is not True):raise ValueError()
            return {**({**value['result'],'lifecycle':public_lifecycle} if value['effect_state']=='APPLIED' else {}),'schema':'van.account-lifecycle-operation/1','operation_id':admitted['operation_id'],'native':value,
                'effect_state':value['effect_state'],'execution_authority':False}
        except (HTTPException,OSError,TimeoutError,ConnectionError,ValidationError,KeyError,ValueError,TypeError):
            return {'schema':'van.account-lifecycle-operation/1','operation_id':admitted['operation_id'],'native':None,
                'effect_state':'UNKNOWN','execution_authority':False}
    async def read_record(self,request,alias,lifecycle_id=None):
        caller=self.read_caller(request)
        domain=await asyncio.to_thread(self.onboarding.control.domain)
        selected=request.headers.get('X-Van-Account-Control-Domain')
        if selected is not None and selected!=domain:raise ReauthError('LIFECYCLE_DOMAIN_CHANGED')
        caller.update(proved=bool(getattr(request.state,'van_device_proved',False)),
            verified_binding_identity=getattr(request.state,'van_device_proof_binding_identity',None),request_deadline=int(time.time())+300)
        loop=asyncio.get_running_loop()
        def guard():
            async def current():
                async with self.store.connection() as db:
                    await db.execute('BEGIN')
                    try:await self.authorize(db,caller,False)
                    finally:await db.rollback()
            future=asyncio.run_coroutine_threadsafe(current(),loop)
            try:future.result(5)
            except BaseException:
                future.cancel();raise HTTPException(403,'Current lifecycle read owner unavailable') from None
        payload={'action':'account_lifecycle_read','args':{'alias':alias,**({'lifecycle_id':lifecycle_id} if lifecycle_id is not None else {})},'owner_device_id':caller['device_id']}
        if isinstance(self.onboarding.control,LocalAccountControl):payload['_account_dispatch_guard']=guard
        value=await asyncio.to_thread(self.onboarding.control.run,'account_review',payload)
        parsed=AccountLifecycleState.model_validate(value)
        if (parsed.alias!=alias or parsed.device_id!=caller['device_id'] or parsed.account_control_domain!=domain
            or lifecycle_id is not None and parsed.operation_id!=lifecycle_id):
            raise ReauthError('LIFECYCLE_ORIGINAL_SCOPE_UNVERIFIED',503)
        return parsed.model_dump(by_alias=True)
    async def archive_due(self):
        # Existing retention runner invokes a native data CAS, never an old A4
        # permission or a deferred credential/provider effect.
        return await asyncio.to_thread(self.onboarding.control.run,'account_review',{'action':'account_lifecycle_archive_due','args':{}})

def build_lifecycle_router(service):
    router=APIRouter(prefix='/v1/trading/accounts/lifecycle',route_class=PrivateCleanupRoute,tags=['account-lifecycle'])
    @router.post('/prepare')
    async def prepare(request:Request,body:ReauthRequest):return await service.prepare(request,body)
    @router.post('/reauth/challenge')
    async def challenge(request:Request,body:ReauthRequest):return await service.issue_reauth(request,body)
    @router.post('/reauth/verify')
    async def verify(request:Request,body:ReauthRequest):return await service.verify_reauth(request,body)
    @router.get('/records/{alias}',response_model=AccountLifecycleState)
    async def read(request:Request,alias:str):
        import re
        if re.fullmatch(r'[a-z0-9_]{3,32}',alias) is None:raise ReauthError('LIFECYCLE_INPUT_INVALID',422)
        return await service.read_record(request,alias)
    @router.get('/records/{alias}/{lifecycle_id}',response_model=AccountLifecycleState)
    async def read_exact(request:Request,alias:str,lifecycle_id:str):
        import re
        if (re.fullmatch(r'[a-z0-9_]{3,32}',alias) is None
            or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',lifecycle_id) is None):raise ReauthError('LIFECYCLE_INPUT_INVALID',422)
        return await service.read_record(request,alias,lifecycle_id)
    @router.get('/operations/{operation_id}')
    async def original(request:Request,operation_id:str):
        import re
        if re.fullmatch(r'[A-Za-z0-9_-]{20,128}',operation_id) is None:raise ReauthError('LIFECYCLE_INPUT_INVALID',422)
        caller=service.read_caller(request)
        async with service.store.connection() as db:
            await db.execute('BEGIN')
            try:
                await service.authorize(db,caller,False)
                row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+operation_id,))).fetchone()
                if row is None:raise ReauthError('LIFECYCLE_ORIGINAL_UNAVAILABLE',404)
                admitted=json.loads(row['value'])
                selected=request.headers.get('X-Van-Account-Control-Domain')
                if selected is not None and selected!=admitted['context']['account_control_domain']:raise ReauthError('LIFECYCLE_DOMAIN_CHANGED')
                if admitted['device_id']!=caller['device_id'] or admitted['admission_digest']!=digest({k:v for k,v in admitted.items() if k!='admission_digest'}):raise ReauthError('LIFECYCLE_ORIGINAL_SCOPE_REFUSED',403)
            finally:await db.rollback()
        return await service.read_child(admitted)
    return router
