"""Paired-device restriction controls using the existing Store/A4 owners.

The new restriction profile is separate from unlink purposes and financial
permission. Native source observations and historical admissions are DATA only.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
import secrets
import threading
from typing import Literal

from fastapi import APIRouter,Request,HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator

from van_gateway.models import OwnerApprovalProof
from van_gateway.approval.service import OwnerApprovalService
from van_gateway.approval.account_lifecycle_reauth import AccountRestrictionReauthentication,ReauthError,digest
from van_gateway.trading.account_cleanup_api import AccountCleanup,_distinct,HEADERS
from van_gateway.trading.accounts import LocalAccountControl,account_approval_text,MAX_AGE_S

HASH=r'^[0-9a-f]{64}$'
ID=r'^[A-Za-z0-9_-]{20,128}$'
ALIAS=r'^[a-z0-9_]{3,32}$'
REASONS={'OWNER_REQUEST':'Owner requested a restriction.',
    'CREDENTIALS_EXPIRED':'Owner reports credential re-verification is required.',
    'BROKER_DISABLED':'Owner reports the broker account is disabled.',
    'KILL_SWITCH':'Owner activated the entry restriction.',
    'VERIFICATION_FAILED':'Owner reports account verification failed.'}
TRANSITIONS={'REAUTH_PENDING':'Owner requested fresh reauthentication; entries remain blocked.',
             'LINKED_READ_ONLY':'Fresh native identity was verified for read-only recovery; no mode or mandate granted.'}

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class RestrictionRequest(Strict):
    device_id:str=Field(min_length=1,max_length=128)
    issued_at_unix:int
    signature:str=Field(min_length=32,max_length=256)
    action:Literal['account_restrict']
    args:dict
    approval_proof:OwnerApprovalProof|None=None

class PriorUnobserved(Strict):
    observed:Literal[False]
    reason:Literal['PRIOR_CANONICAL_PHASE_NOT_OBSERVED']
    source_ref:str=Field(pattern=HASH)

class PriorObserved(Strict):
    observed:Literal[True]
    phase:Literal['LINKED_READ_ONLY','KYC_PENDING','ACTIVE_ELIGIBLE']
    proof_ref:str=Field(pattern=HASH)

class RestrictionState(Strict):
    schema_name:Literal['vati.account-restriction/1']=Field(alias='schema')
    alias:str=Field(pattern=ALIAS)
    restriction_id:str=Field(pattern=ID)
    incarnation:str=Field(pattern=HASH)
    device_id:str=Field(min_length=1,max_length=128)
    account_control_domain:str=Field(pattern=HASH)
    revision:int=Field(gt=0)
    phase:Literal['RESTRICTED','REAUTH_PENDING','LINKED_READ_ONLY']
    reason_code:Literal['OWNER_REQUEST','CREDENTIALS_EXPIRED','BROKER_DISABLED','KILL_SWITCH','VERIFICATION_FAILED']
    reason:str
    created_at_unix:int=Field(gt=0)
    updated_at_unix:int=Field(gt=0)
    record_digest:str=Field(pattern=HASH)
    entry_permitted:Literal[False]
    mode_or_mandate_granted:Literal[False]
    protection_or_manual_exit_cancelled:Literal[False]
    transition_reason:str
    prior_phase_observation:PriorUnobserved|PriorObserved
    @model_validator(mode='after')
    def fixed_reasons(self):
        if (self.reason!=REASONS[self.reason_code] or self.updated_at_unix<self.created_at_unix
                or self.transition_reason!=(self.reason if self.phase=='RESTRICTED' else TRANSITIONS[self.phase])):
            raise ValueError('restriction public state is incoherent')
        return self

class OperationRef(Strict):
    operation_id:str=Field(pattern=ID)
    intent_hash:str=Field(pattern=HASH)
    event_ref:str=Field(pattern=HASH)
    request_digest:str=Field(pattern=HASH)
    authority_ref:str=Field(min_length=1,max_length=512)
    native_review_digest:str=Field(pattern=HASH)
    admission_digest:str=Field(pattern=HASH)
    alias:str=Field(pattern=ALIAS)
    incarnation:str=Field(pattern=HASH)
    device_id:str=Field(min_length=1,max_length=128)
    account_control_domain:str=Field(pattern=HASH)
    parent_operation_id:str|None=Field(default=None,pattern=ID)
    parent_admission_digest:str|None=Field(default=None,pattern=HASH)

class RestrictionView(Strict):
    alias:str=Field(pattern=ALIAS)
    owner_device_id:str=Field(min_length=1,max_length=128)
    account_control_domain:str=Field(pattern=HASH)
    restriction_id:str=Field(min_length=20,max_length=128)
    incarnation:str=Field(pattern=HASH)
    expected_revision:int=Field(ge=0)
    expected_digest:str|None=Field(pattern=HASH)
    reason_code:Literal['OWNER_REQUEST','CREDENTIALS_EXPIRED','BROKER_DISABLED','KILL_SWITCH','VERIFICATION_FAILED']
    before:RestrictionState|None
    enabled:bool
    mode:Literal['OBSERVE','ADVISOR','DEMO_TRADER','SHADOW_TRADER','LIMITED_LIVE','AUTONOMOUS_LIVE']
    mode_or_mandate_granted:Literal[False]
    entry_permitted:Literal[False]
    protective_exits_preserved:Literal[True]
    native_identity_required:bool
    native_identity_scope_ref:str|None=Field(pattern=HASH)
    parent_admission_digest:str|None=Field(pattern=HASH)
    related_operations:list[OperationRef]

class RestrictionReview(Strict):
    schema_name:Literal['vati.account-restriction-review/1']=Field(alias='schema')
    semantic_digest:str=Field(pattern=HASH)
    resource_version:str=Field(pattern=HASH)
    view:RestrictionView
    context_digest:str=Field(pattern=HASH)
    request_digest:str=Field(pattern=HASH)
    review_digest:str=Field(pattern=HASH)

class IdentityFacts(Strict):
    schema_name:Literal['vati.account-restriction-identity-observation/1']=Field(alias='schema')
    account_alias:str=Field(pattern=ALIAS)
    broker:Literal['PAPER','MT5','MT5_EA','DERIV','CTRADER']
    identity_scope_ref:str=Field(pattern=HASH)
    source_kind:Literal['INTERNAL_PAPER_SIMULATION','MT5_SIGNED_EA_POLL','MT5_SIGNED_MTLS_READ','DERIV_NATIVE_AUTHORIZE_READ','CTRADER_AUTHENTICATED_NATIVE_ACCOUNT_READ']
    source_nonce_ref:str|None=Field(pattern=HASH)
    source_received_at_ms:int=Field(ge=0)
    observed_at_ms:int=Field(ge=0)
    execution_authority:Literal[False]
    mode_or_mandate_granted:Literal[False]
    observation_ref:str=Field(pattern=HASH)

    @model_validator(mode='after')
    def source_pair(self):
        sources={'PAPER':'INTERNAL_PAPER_SIMULATION','MT5':'MT5_SIGNED_MTLS_READ',
            'MT5_EA':'MT5_SIGNED_EA_POLL','DERIV':'DERIV_NATIVE_AUTHORIZE_READ','CTRADER':'CTRADER_AUTHENTICATED_NATIVE_ACCOUNT_READ'}
        if (self.source_kind!=sources[self.broker] or (self.broker in {'MT5','MT5_EA'})!=(self.source_nonce_ref is not None)):
            raise ValueError('native identity source pairing differs')
        return self

class RestrictionResolution(Strict):
    resolution_child_operation_id:str=Field(pattern=ID)
    resolution_ref:str=Field(pattern=HASH)
    outcome:Literal['TRANSITION_OBSERVED','CURRENT_PREIMAGE_OBSERVED']
    alias:str=Field(pattern=ALIAS)
    restriction_id:str|None=Field(pattern=ID)
    incarnation:str|None=Field(pattern=HASH)
    revision:int=Field(ge=0)
    record_digest:str|None=Field(pattern=HASH)
    event_ref:str|None=Field(pattern=HASH)
    admission_digest:str=Field(pattern=HASH)
    resource_version:str=Field(pattern=HASH)
    resolved_operations:list[str]
    selected_parent_operation_id:str=Field(pattern=ID)
    anchor_operation_id:str=Field(pattern=ID)
    anchor_outcome:Literal['TRANSITION_OBSERVED','CURRENT_PREIMAGE_OBSERVED']
    anchor_event_ref:str|None=Field(pattern=HASH)
    @model_validator(mode='after')
    def coherent(self):
        import re
        if (not self.resolved_operations or self.resolved_operations!=sorted(set(self.resolved_operations))
                or self.selected_parent_operation_id not in self.resolved_operations
                or any(type(v) is not str or re.fullmatch(ID,v) is None for v in self.resolved_operations)
                or (self.outcome=='TRANSITION_OBSERVED')!=(self.event_ref is not None)
                or (self.anchor_outcome=='TRANSITION_OBSERVED')!=(self.anchor_event_ref is not None)
                or (self.revision==0)!=(self.restriction_id is None)
                or (self.revision==0)!=(self.incarnation is None) or (self.revision==0)!=(self.record_digest is None)):
            raise ValueError('restriction resolution public evidence differs')
        return self

class RestrictionResult(Strict):
    schema_name:Literal['vati.account-restriction-result/1']=Field(alias='schema')
    action:Literal['account_restrict']
    variant:Literal['RESTRICT','BEGIN_REAUTH','COMPLETE_REAUTH','RECONCILE_DATA']
    restriction:RestrictionState|None
    native_identity:IdentityFacts|None
    data_resolution:RestrictionResolution|None
    entry_permitted:Literal[False]
    mode_or_mandate_granted:Literal[False]
    protective_exits_preserved:Literal[True]


def semantic(args):return {k:v for k,v in args.items() if k not in {'reauth_fact_id','reauth_fact_digest'}}

def approval_text(req,args,review,domain):
    return (account_approval_text(req.device_id,req.issued_at_unix,'account_restrict',args,review['resource_version'],domain)
            +'|restriction-context:'+review['context_digest']
            +'|selected-parent:'+str(args.get('parent_operation_id'))
            +'|causal-anchor:'+str(next((r['operation_id'] for r in review['view']['related_operations'] if r['parent_operation_id'] is None),None))
            +'|related-operations:'+json.dumps(review['view']['related_operations'],sort_keys=True,separators=(',',':')))


class AccountRestriction(AccountCleanup):
    def __init__(self,store,onboarding,authenticate,authorize,*,clock=None):
        super().__init__(store,onboarding,authenticate,authorize,clock=clock)
        self.reauth=AccountRestrictionReauthentication(store,authorize,clock=clock)
        self._native_calls={};self._native_reads={}
        self.bind_local_verifiers()

    def bind_local_verifiers(self):
        control=self.onboarding.control
        if isinstance(control,LocalAccountControl):
            control.settings.restriction_admission_verifier=self.verify_local_admission
            control.settings.restriction_read_verifier=self.verify_local_read

    @staticmethod
    def arguments(raw,*,with_fact=None):
        if type(raw) is not dict or any(type(k) is not str or k.startswith('_') for k in raw):
            raise ReauthError('RESTRICTION_INPUT_INVALID',422)
        from commander.account_restrictions import arguments
        try:args=arguments(raw)
        except HTTPException as error:raise ReauthError(error.detail['code'],error.status_code) from None
        present='reauth_fact_id' in args
        if with_fact is not None and present!=with_fact:raise ReauthError('RESTRICTION_REAUTH_INPUT_MISMATCH',422)
        return args

    def _guard(self,caller,loop,cancelled,*,mutating=True):
        def guard():
            if cancelled.is_set():raise HTTPException(409,{'code':'RESTRICTION_REQUEST_CANCELLED'})
            async def current():
                async with self.store.connection() as db:
                    await db.execute('BEGIN')
                    try:return await self.authorize(db,caller,mutating)
                    finally:await db.rollback()
            future=asyncio.run_coroutine_threadsafe(current(),loop)
            try:future.result(5)
            except BaseException:
                future.cancel();raise HTTPException(403,{'code':'RESTRICTION_CURRENT_OWNER_UNVERIFIED'}) from None
            if self.clock()>=caller['request_deadline']:raise HTTPException(403,{'code':'RESTRICTION_REQUEST_EXPIRED'})
        return guard

    async def _verify_current_records(self,db,caller,records,*,mutating):
        actor=await self.authorize(db,caller,mutating)
        for record in records:
            row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                (self.reauth.ADMISSIONS+record['operation_id'],))).fetchone()
            if row is None or json.loads(row['value'])!=record:
                raise ReauthError('RESTRICTION_ADMISSION_SOURCE_CHANGED',403)
        return actor

    def _wait_current(self,caller,records,loop,*,mutating,admitted=None):
        async def current():
            async with self.store.connection() as db:
                await db.execute('BEGIN')
                try:
                    actor=await self._verify_current_records(db,caller,records,mutating=mutating)
                    if admitted is not None and (actor!=admitted['actor_key_ref'] or self.clock()>=admitted['expires_at_unix']):
                        raise ReauthError('RESTRICTION_ADMISSION_EXPIRED_OR_ACTOR_CHANGED',403)
                finally:await db.rollback()
        future=asyncio.run_coroutine_threadsafe(current(),loop)
        try:future.result(5)
        except BaseException:
            future.cancel();raise HTTPException(403,{'code':'RESTRICTION_CURRENT_ADMISSION_UNVERIFIED'}) from None

    def verify_local_admission(self,args):
        try:
            record=args['_restriction_admission'];saved,caller,guard,loop,sources=self._native_calls[record['operation_id']]
            if saved!=record or sources!=args.get('_restriction_related_admissions',[]):raise ValueError()
            original=args.get('_restriction_original_admission')
            if (record['context']['variant']=='RECONCILE_DATA'
                    and (original is None or original['admission_digest']!=record['context']['parent_admission_digest']
                         or original not in sources)):raise ValueError()
        except (KeyError,TypeError,ValueError):raise HTTPException(403,{'code':'RESTRICTION_DURABLE_ADMISSION_REQUIRED'}) from None
        self._wait_current(caller,[saved,*sources],loop,mutating=True,admitted=saved);guard()
        return saved

    def verify_local_read(self,payload):
        try:
            expected,caller,guard,loop,sources,mutating=self._native_reads[payload['_restriction_read_id']]
            observed={k:v for k,v in payload.items() if k not in {'_account_dispatch_guard','_restriction_read_id'}}
            if digest(observed)!=expected:raise ValueError()
        except (KeyError,TypeError,ValueError):raise HTTPException(403,{'code':'RESTRICTION_CURRENT_READ_SCOPE_REQUIRED'}) from None
        self._wait_current(caller,sources,loop,mutating=mutating);guard()
        return caller['device_id']

    async def _read_native(self,action,args,caller,*,sources=(),mutating=True,cancelled=None):
        cancelled=cancelled or threading.Event();guard=self._guard(caller,asyncio.get_running_loop(),cancelled,mutating=mutating)
        payload={'action':action,'args':args,'owner_device_id':caller['device_id']}
        if sources:
            payload['_restriction_related_admissions']=list(sources)
            selected=args.get('parent_operation_id')
            payload['_restriction_original_admission']=next((r for r in sources if r['operation_id']==selected),None)
        request_id=secrets.token_urlsafe(24)
        expected=digest(payload);self._native_reads[request_id]=(expected,caller,guard,asyncio.get_running_loop(),deepcopy(list(sources)),mutating)
        if isinstance(self.onboarding.control,LocalAccountControl):
            payload['_restriction_read_id']=request_id;payload['_account_dispatch_guard']=guard
        try:return await asyncio.to_thread(self.onboarding.control.run,'account_review',payload)
        finally:self._native_reads.pop(request_id,None)

    async def review(self,request,req,*,with_fact=None,cancelled=None):
        args=self.arguments(req.args,with_fact=with_fact);caller=self.caller(request,req)
        domain=await asyncio.to_thread(self.onboarding.control.domain)
        selected=request.headers.get('X-Van-Account-Control-Domain')
        if selected is not None and selected!=domain:raise ReauthError('RESTRICTION_DOMAIN_CHANGED')
        sources=await self._source_bundle(args,caller,domain) if args['variant']=='RECONCILE_DATA' else []
        review=await self._read_native('account_restriction_review',args,caller,sources=sources,cancelled=cancelled)
        try:
            parsed=RestrictionReview.model_validate(review);view=review['view']
            if (review['request_digest']!=digest(args) or review['semantic_digest']!=digest(semantic(args))
                    or view['alias']!=args['alias'] or view['owner_device_id']!=req.device_id or view['account_control_domain']!=domain
                    or review['context_digest']!=digest({k:v for k,v in review.items() if k not in {'review_digest','context_digest','request_digest'}})
                    or review['review_digest']!=digest({k:v for k,v in review.items() if k!='review_digest'})):
                raise ValueError()
        except (ValidationError,KeyError,TypeError,ValueError):raise ReauthError('RESTRICTION_NATIVE_REVIEW_UNVERIFIED',503) from None
        context={'alias':args['alias'],'restriction_id':view['restriction_id'],'incarnation':view['incarnation'],
            'account_control_domain':domain,'original_device_id':req.device_id,'review_digest':review['context_digest'],
            'resource_version':review['resource_version'],'variant':args['variant'],'semantic_digest':review['semantic_digest'],
            'expected_revision':view['expected_revision'],'expected_digest':view['expected_digest'],
            'reason_code':view['reason_code'],'parent_operation_id':args.get('parent_operation_id'),
            'parent_admission_digest':view['parent_admission_digest']}
        self.reauth.context(context,caller)
        return args,caller,review,context,sources

    async def _source_bundle(self,args,caller,domain):
        pending=await self._read_native('account_restriction_pending',{'alias':args['alias']},caller)
        try:
            if (type(pending) is not dict or set(pending)!={'schema','operation_ids','execution_authority'}
                    or pending['schema']!='vati.account-restriction-pending/1' or pending['execution_authority'] is not False
                    or type(pending['operation_ids']) is not list or not 1<=len(pending['operation_ids'])<=64
                    or pending['operation_ids']!=sorted(set(pending['operation_ids']))):raise ValueError()
            from commander.account_effects import AccountEffectJournal
            async with self.store.connection() as db:
                await db.execute('BEGIN')
                try:
                    await self.authorize(db,caller)
                    # Hard capacity is explicit. No truncated query can be
                    # mistaken for a complete causal component.
                    rows=await (await db.execute('SELECT value FROM runtime_meta WHERE key LIKE ? ORDER BY key LIMIT 1025',
                        (self.reauth.ADMISSIONS+'%',))).fetchall()
                    if len(rows)>1024:raise ReauthError('RESTRICTION_CAUSAL_PROOF_CAPACITY')
                    records={}
                    for raw in rows:
                        record=json.loads(raw['value'])
                        c=record.get('context',{})
                        if c.get('alias')==args['alias'] and c.get('account_control_domain')==domain:
                            AccountEffectJournal._restriction_admission_shape(record)
                            if record['admission_digest']!=digest({k:v for k,v in record.items() if k!='admission_digest'}):raise ValueError()
                            records[record['operation_id']]=record
                    selected=args['parent_operation_id']
                    if selected not in pending['operation_ids'] or selected not in records:raise ValueError()
                    incarnation=records[selected]['context']['incarnation'];included=set(pending['operation_ids'])
                    included.add(selected)
                    while True:
                        previous=set(included)
                        for op in tuple(included):
                            record=records[op];c=record['context']
                            if record['device_id']!=caller['device_id'] or c['incarnation']!=incarnation:raise ValueError()
                            parent=c['parent_operation_id']
                            if parent is not None:
                                if parent not in records or records[parent]['admission_digest']!=c['parent_admission_digest']:raise ValueError()
                                included.add(parent)
                        if len(included)>64:raise ReauthError('RESTRICTION_CAUSAL_PROOF_CAPACITY')
                        if included==previous:break
                    anchors=[op for op in included if records[op]['native_request']['variant']!='RECONCILE_DATA']
                    if len(anchors)!=1:raise ValueError()
                    anchor=anchors[0]
                    for op in included:
                        cursor=op;seen=set()
                        while cursor!=anchor:
                            if cursor in seen:raise ValueError()
                            seen.add(cursor);cursor=records[cursor]['context']['parent_operation_id']
                            if cursor not in included:raise ValueError()
                    return [records[op] for op in sorted(included)]
                finally:await db.rollback()
        except (KeyError,TypeError,ValueError):raise ReauthError('RESTRICTION_CAUSAL_SOURCE_UNAVAILABLE') from None

    async def issue_reauth(self,request,req):
        await self.authenticate(request,req)
        args,caller,review,context,_=await self.review(request,req,with_fact=False)
        if args['variant']=='RESTRICT':raise ReauthError('RESTRICTION_NARROWING_USES_SUBSTANTIVE_A4',422)
        return {**await self.reauth.issue(caller,context),'resolved_review':review}

    async def verify_reauth(self,request,req):
        await self.authenticate(request,req)
        if req.approval_proof is None or req.approval_proof.algorithm!=OwnerApprovalService.ALGORITHM:
            raise ReauthError('RESTRICTION_REAUTH_PROOF_REQUIRED',403)
        args,caller,_,context,_=await self.review(request,req,with_fact=False)
        if args['variant']=='RESTRICT':raise ReauthError('RESTRICTION_NARROWING_USES_SUBSTANTIVE_A4',422)
        return await self.reauth.verify(caller,context,req.approval_proof.challenge_id,req.approval_proof.signature_b64)

    @staticmethod
    def parameters(args,review):
        return {'restriction_review':review,'native_request':args,'reauth_fact_digest':args.get('reauth_fact_digest')}

    async def challenge(self,request,req):
        await self.authenticate(request,req)
        raw=self.arguments(req.args);recovery=raw['variant']!='RESTRICT'
        args,caller,review,context,sources=await self.review(request,req,with_fact=recovery)
        parameters=self.parameters(args,review);text=approval_text(req,args,review,context['account_control_domain'])
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor=await self.reauth.current_actor(db,caller)
                await self.reauth.validate_admission_sources(db,caller,context,parameters)
                expiry=caller['request_deadline']
                if recovery:
                    fact=await self.reauth.require_fact(db,caller,context,args['reauth_fact_id'],actor)
                    if fact['fact_digest']!=args['reauth_fact_digest']:raise ReauthError('RESTRICTION_REAUTH_FACT_CHANGED')
                    expiry=min(expiry,fact['expires_at_unix'])
                issued=await self.reauth.approvals.issue(device_id=req.device_id,source_command_id=self.reauth.ACTION_SOURCE,
                    turn_id=None,action_id=self.reauth.ACTION,text=text,project_id=None,parameters=parameters,
                    ttl_seconds=OwnerApprovalService.DEFAULT_TTL_SECONDS,_expiry_cap=expiry,_db=db)
                await db.commit()
            except BaseException:await db.rollback();raise
        return {'approval_challenge_id':issued.challenge_id,'approval_challenge':issued.canonical,
                'issued_at_unix':req.issued_at_unix,'approval_expires_at_unix':issued.expires_at_unix,
                'resolved_action_id':self.reauth.ACTION,'resolved_review':review,'account_control_domain':context['account_control_domain']}

    async def _action(self,request,req,cancelled):
        await self.authenticate(request,req);proof=req.approval_proof
        if proof is None or proof.algorithm!=OwnerApprovalService.ALGORITHM:raise ReauthError('RESTRICTION_ACTION_PROOF_REQUIRED',403)
        original=await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(self.reauth.ADMISSIONS+proof.challenge_id,))
        if original is not None:
            saved=json.loads(original['value']);args=self.arguments(req.args)
            expected=digest({'context':saved['context'],'fact_id':args.get('reauth_fact_id'),'challenge_id':proof.challenge_id,
                'text_digest':digest(approval_text(req,args,saved['native_review'],saved['context']['account_control_domain'])),
                'parameters_digest':saved['approval_parameters_digest']})
            if (saved['device_id']!=req.device_id or saved['native_request']!=args or saved['request_digest']!=expected
                    or saved['admission_digest']!=digest({k:v for k,v in saved.items() if k!='admission_digest'})):
                raise ReauthError('RESTRICTION_ORIGINAL_ADMISSION_CONFLICT')
            caller=self.caller(request,req)
            async with self.store.connection() as db:
                await db.execute('BEGIN')
                try:await self.authorize(db,caller)
                finally:await db.rollback()
            return await self.read_child(saved,caller)
        args=self.arguments(req.args);recovery=args['variant']!='RESTRICT'
        args,caller,review,context,sources=await self.review(request,req,with_fact=recovery,cancelled=cancelled)
        parameters=self.parameters(args,review);text=approval_text(req,args,review,context['account_control_domain'])
        options={'challenge_id':proof.challenge_id,'signature_b64':proof.signature_b64,'text':text,
                 'parameters':parameters,'current_request_deadline':caller['request_deadline']}
        if recovery:admitted,winner=await self.reauth.admit(caller,context,args['reauth_fact_id'],**options)
        else:admitted,winner=await self.reauth.admit_restriction(caller,context,**options)
        if not winner:return await self.read_child(admitted,caller)
        guard=self._guard(caller,asyncio.get_running_loop(),cancelled)
        native={**args,'_restriction_admission':admitted,'_expected_resource_version':review['resource_version'],
                '_expected_review_digest':review['review_digest'],'_expected_restriction_context_digest':review['context_digest'],
                '_expected_account_control_domain':context['account_control_domain'],'_restriction_related_admissions':sources,
                '_native_operation':{'operation_id':admitted['operation_id'],'device_id':req.device_id,
                    'request_digest':digest(args),'authority_ref':admitted['authority_ref']+'::review:'+review['review_digest'],
                    'expires_at_unix':admitted['expires_at_unix']}}
        if args['variant']=='RECONCILE_DATA':
            native['_restriction_original_admission']=next(r for r in sources if r['operation_id']==args['parent_operation_id'])
        if isinstance(self.onboarding.control,LocalAccountControl):native['_account_dispatch_guard']=guard
        self._native_calls[admitted['operation_id']]=(admitted,caller,guard,asyncio.get_running_loop(),deepcopy(sources))
        try:
            await asyncio.to_thread(guard)
            if not cancelled.is_set():await asyncio.to_thread(self.onboarding.control.run,'account_restrict',native)
        except (HTTPException,OSError,TimeoutError,ConnectionError):pass
        finally:self._native_calls.pop(admitted['operation_id'],None)
        return await self.read_child(admitted,caller)

    def _read_caller(self,request):
        device=getattr(request.state,'van_device_id',None)
        if type(device) is not str or not device:raise ReauthError('RESTRICTION_CURRENT_OWNER_REQUIRED',403)
        return {'owner_id':'owner','device_id':device,
                'access_token_hash':hashlib.sha256(request.headers.get('X-Van-Device-Token','').encode()).hexdigest(),
                'proved':bool(getattr(request.state,'van_device_proved',False)),
                'verified_binding_identity':getattr(request.state,'van_device_proof_binding_identity',None),
                'request_deadline':self.clock()+MAX_AGE_S}

    async def read_record(self,request,alias,restriction_id=None):
        caller=self._read_caller(request)
        payload={'alias':alias,**({'restriction_id':restriction_id} if restriction_id is not None else {})}
        result=await self._read_native('account_restriction_read',payload,caller,mutating=False)
        try:
            if type(result) is not dict or set(result)!={'schema','restriction','execution_authority'}:
                raise ValueError()
            row=RestrictionState.model_validate(result['restriction'])
            if (result['schema']!='vati.account-restriction-read/1' or result['execution_authority'] is not False
                    or row.alias!=alias or row.device_id!=caller['device_id']
                    or restriction_id is not None and row.restriction_id!=restriction_id):raise ValueError()
            selected=request.headers.get('X-Van-Account-Control-Domain')
            if selected is not None and row.account_control_domain!=selected:raise ReauthError('RESTRICTION_DOMAIN_CHANGED')
        except (ValidationError,KeyError,TypeError,ValueError):raise ReauthError('RESTRICTION_NATIVE_STATE_UNVERIFIED',503) from None
        return result

    async def read_operation(self,request,operation_id):
        caller=self._read_caller(request)
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            try:
                await self.authorize(db,caller,False)
                row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                    (self.reauth.ADMISSIONS+operation_id,))).fetchone()
                if row is None:raise ReauthError('RESTRICTION_ORIGINAL_ADMISSION_UNAVAILABLE',404)
                saved=json.loads(row['value'])
                if (saved['device_id']!=caller['device_id'] or saved['operation_id']!=operation_id
                        or saved['admission_digest']!=digest({k:v for k,v in saved.items() if k!='admission_digest'})):
                    raise ReauthError('RESTRICTION_ORIGINAL_SCOPE_REFUSED',403)
                selected=request.headers.get('X-Van-Account-Control-Domain')
                if selected is not None and selected!=saved['context']['account_control_domain']:
                    raise ReauthError('RESTRICTION_DOMAIN_CHANGED')
            finally:await db.rollback()
        return await self.read_child(saved,caller)

    async def read_child(self,admitted,caller=None):
        value=None;context=admitted['context']
        try:
            candidate=await asyncio.to_thread(self.onboarding.control.operation,admitted['operation_id'],
                admitted['device_id'],context['account_control_domain'])
            required={'operation_id','action','effect_state','native_phase','reconciliation_required','result','native_event_ref','account_control_domain'}
            if (type(candidate) is not dict or set(candidate)!=required or candidate['operation_id']!=admitted['operation_id']
                    or candidate['action']!='account_restrict' or candidate['account_control_domain']!=context['account_control_domain']
                    or candidate['native_phase'] not in {'IN_FLIGHT','UNKNOWN','APPLIED','REFUSED'}
                    or candidate['effect_state']!=('UNKNOWN' if candidate['native_phase']=='IN_FLIGHT' else candidate['native_phase'])
                    or candidate['reconciliation_required'] is not (candidate['effect_state']=='UNKNOWN')
                    or type(candidate['native_event_ref']) is not str or __import__('re').fullmatch(HASH,candidate['native_event_ref']) is None):
                raise ValueError()
            if candidate['effect_state']=='UNKNOWN' and candidate['result'] is not None:raise ValueError()
            if candidate['effect_state']=='REFUSED':
                refused=candidate['result']
                if (type(refused) is not dict or set(refused)!={'status_code','detail'}
                        or type(refused['status_code']) is not int or not 400<=refused['status_code']<500
                        or refused['detail']!='Original request was refused before any account effect'):raise ValueError()
            if candidate['effect_state']=='APPLIED':
                result=RestrictionResult.model_validate(candidate['result']);row=result.restriction
                if result.variant!=context['variant']:raise ValueError()
                if result.variant!='RECONCILE_DATA':
                    wanted_phase={'RESTRICT':'RESTRICTED','BEGIN_REAUTH':'REAUTH_PENDING','COMPLETE_REAUTH':'LINKED_READ_ONLY'}[result.variant]
                    if (row is None or row.alias!=context['alias'] or row.device_id!=admitted['device_id']
                            or row.account_control_domain!=context['account_control_domain'] or row.incarnation!=context['incarnation']
                            or row.revision!=context['expected_revision']+1 or row.phase!=wanted_phase
                            or row.restriction_id!=(admitted['operation_id'] if context['expected_revision']==0 else context['restriction_id'])):
                        raise ValueError()
                if result.variant=='RECONCILE_DATA':
                    resolution=result.data_resolution;view=admitted['native_review']['view'];refs=view['related_operations']
                    anchor=next((r['operation_id'] for r in refs if r['parent_operation_id'] is None),None)
                    if (resolution is None or result.native_identity is not None
                            or resolution.resolution_child_operation_id!=admitted['operation_id']
                            or resolution.alias!=context['alias'] or resolution.selected_parent_operation_id!=context['parent_operation_id']
                            or resolution.admission_digest!=context['parent_admission_digest'] or resolution.resource_version!=context['resource_version']
                            or resolution.anchor_operation_id!=anchor or not set(resolution.resolved_operations)<={r['operation_id'] for r in refs}
                            or (None if row is None else row.model_dump(by_alias=True))!=view['before']
                            or resolution.revision!=(row.revision if row else 0)
                            or resolution.record_digest!=(row.record_digest if row else None)
                            or resolution.restriction_id!=(row.restriction_id if row else None)
                            or resolution.incarnation!=(row.incarnation if row else None)):
                        raise ValueError()
                elif result.data_resolution is not None:raise ValueError()
                if result.variant=='COMPLETE_REAUTH':
                    proof=result.native_identity
                    if (proof is None or proof.account_alias!=context['alias']
                            or proof.identity_scope_ref!=admitted['native_review']['view']['native_identity_scope_ref']
                            or not admitted['created_at_unix']*1000<=proof.observed_at_ms<admitted['expires_at_unix']*1000
                            or not 0<=proof.source_received_at_ms<=proof.observed_at_ms
                            or proof.observed_at_ms-proof.source_received_at_ms>30000
                            or proof.observation_ref!=digest({k:v for k,v in candidate['result']['native_identity'].items() if k!='observation_ref'})):
                        raise ValueError()
                elif result.native_identity is not None:raise ValueError()
            value=candidate
        except (HTTPException,OSError,TimeoutError,ConnectionError,ValidationError,ValueError,TypeError,KeyError):pass
        resolution=None
        if caller is not None and (value is None or value['effect_state']=='UNKNOWN'):
            try:
                resolved=await self._read_native('account_restriction_resolution',
                    {'alias':context['alias'],'operation_id':admitted['operation_id']},caller,sources=[admitted],mutating=False)
                if (type(resolved) is not dict or set(resolved)!={'schema','resolution','execution_authority'}
                        or resolved['schema']!='vati.account-restriction-resolution-read/1' or resolved['execution_authority'] is not False):raise ValueError()
                if resolved['resolution'] is not None:
                    parsed=RestrictionResolution.model_validate(resolved['resolution'])
                    if (parsed.alias!=context['alias'] or (admitted['operation_id'] not in parsed.resolved_operations
                            and admitted['operation_id']!=parsed.resolution_child_operation_id)):raise ValueError()
                    resolution=parsed.model_dump()
            except (HTTPException,OSError,TimeoutError,ConnectionError,ValidationError,ValueError,TypeError,KeyError):pass
        return {'schema':'van.account-restriction-operation/1','operation_id':admitted['operation_id'],
                'account_control_domain':context['account_control_domain'],'gateway_admission':'ADMITTED_NOT_NATIVE_COMPLETION',
                'effect_state':value['effect_state'] if value is not None else 'UNKNOWN',
                'native_phase':value['native_phase'] if value is not None else None,
                'native_event_ref':value['native_event_ref'] if value is not None else None,
                'observed_native_state':value is not None,'result':value['result'] if value is not None else None,
                'reconciliation_required':value is None or value['effect_state']=='UNKNOWN',
                'automatic_resend_permitted':False,'execution_authority':False,'data_resolution':resolution}


class RestrictionRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handle(request):
            try:
                if request.query_params:raise ReauthError('RESTRICTION_INPUT_INVALID',422)
                raw=await request.body()
                if len(raw)>8192:raise ReauthError('RESTRICTION_INPUT_CAPACITY',413)
                if request.method!='GET':
                    try:json.loads(raw,object_pairs_hook=_distinct,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
                    except (ValueError,RecursionError):raise ReauthError('RESTRICTION_INPUT_INVALID',422) from None
                response=await original(request);response.headers.update(HEADERS);return response
            except ReauthError as error:
                headers={**HEADERS,**({'Retry-After':str(error.retry_after)} if error.retry_after else {})}
                code=error.code.replace('LIFECYCLE_','RESTRICTION_',1).replace('CLEANUP_','RESTRICTION_',1)
                return JSONResponse(status_code=error.status,content={'detail':{'code':code,'locked_until':error.locked_until,'retry_after':error.retry_after}},headers=headers)
            except RequestValidationError:
                return JSONResponse(status_code=422,content={'detail':{'code':'RESTRICTION_INPUT_INVALID'}},headers=HEADERS)
            except HTTPException as error:
                error.headers={**(error.headers or {}),**HEADERS};raise
        return handle


def build_restriction_router(service):
    router=APIRouter(prefix='/v1/trading/accounts/restrictions',route_class=RestrictionRoute,tags=['account-restriction'])
    @router.post('/review')
    async def review(request:Request,body:RestrictionRequest):
        await service.authenticate(request,body)
        _,_,value,_,_=await service.review(request,body)
        return {'resolved_review':value,'execution_authority':False}
    @router.post('/reauth/challenge')
    async def reauth_challenge(request:Request,body:RestrictionRequest):return await service.issue_reauth(request,body)
    @router.post('/reauth/verify')
    async def reauth_verify(request:Request,body:RestrictionRequest):return await service.verify_reauth(request,body)
    @router.post('/challenge')
    async def challenge(request:Request,body:RestrictionRequest):return await service.challenge(request,body)
    @router.post('/action')
    async def action(request:Request,body:RestrictionRequest):
        value=await service.action(request,body)
        return JSONResponse(status_code=200 if value['effect_state']=='APPLIED' else 409,content=value,headers=HEADERS)
    @router.get('/records/{alias}')
    async def current(request:Request,alias:str):
        if __import__('re').fullmatch(ALIAS,alias) is None:raise ReauthError('RESTRICTION_INPUT_INVALID',422)
        return await service.read_record(request,alias)
    @router.get('/records/{alias}/{restriction_id}')
    async def historical(request:Request,alias:str,restriction_id:str):
        if __import__('re').fullmatch(ALIAS,alias) is None or __import__('re').fullmatch(ID,restriction_id) is None:
            raise ReauthError('RESTRICTION_INPUT_INVALID',422)
        return await service.read_record(request,alias,restriction_id)
    @router.get('/operations/{operation_id}')
    async def operation(request:Request,operation_id:str):
        if __import__('re').fullmatch(ID,operation_id) is None:raise ReauthError('RESTRICTION_INPUT_INVALID',422)
        return await service.read_operation(request,operation_id)
    return router
