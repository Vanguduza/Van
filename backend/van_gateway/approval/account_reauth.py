"""Purpose-specific retirement reauthentication DATA, never action permission.

Uses the existing enrolled biometric approval key/service. A separate substantive
A4 permission plus this unspent fact are consumed with child admission by ONE
existing Store writer. The native journal remains a distinct commit owner.
"""
import hashlib
import json
import secrets
import time

from van_gateway.approval.service import OwnerApprovalService,OwnerApprovalError
from van_gateway.auth.throttle import AuthThrottle
from van_gateway.ops.retention import RETENTION_DAYS,RetentionClass

EPHEMERAL='account_cleanup_ephemeral:'
ADMISSIONS='account_cleanup_admission:'
USED='account_cleanup_used_reauth:'
PURPOSE='ACCOUNT_PENDING_CLEANUP_REAUTH_DATA'
ACTION='trading.account.account_remove'
SOURCE='account:account_remove:reauth'
CONTEXT_KEYS={'alias','parent_operation_id','plan_ref','account_control_domain','original_device_id',
              'review_digest','resource_version','remaining_steps','retire_parent_safety_obligation'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class ReauthError(ValueError):
    def __init__(self,code,status=409,*,retry_after=0,locked_until=None):
        self.code,self.status,self.retry_after,self.locked_until=code,status,retry_after,locked_until
        super().__init__(code)


class CleanupPurposeChallenges(OwnerApprovalService):
    # Storage discriminator only: SAME enrolled key, algorithm and canonical
    # verifier. Both new-purpose raw challenge roles share the scoped 7d owner.
    PREFIX=EPHEMERAL+'challenge:'


class AccountReauthentication:
    def __init__(self,store,authorize,*,clock=None):
        self.store,self.authorize=store,authorize
        self.approvals=CleanupPurposeChallenges(store)
        self.clock=clock or (lambda:int(time.time()))

    @staticmethod
    def context(context,caller):
        import re
        if (not isinstance(caller,dict) or not isinstance(caller.get('device_id'),str) or not 1<=len(caller['device_id'])<=256
                or not isinstance(context,dict) or set(context)!=CONTEXT_KEYS):raise ReauthError('CLEANUP_CONTEXT_UNVERIFIED')
        for k in ('plan_ref','account_control_domain','review_digest','resource_version'):
            if not isinstance(context[k],str) or re.fullmatch(r'[0-9a-f]{64}',context[k]) is None:raise ReauthError('CLEANUP_CONTEXT_UNVERIFIED')
        if (not isinstance(context['parent_operation_id'],str) or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',context['parent_operation_id']) is None
                or not isinstance(context['alias'],str) or re.fullmatch(r'[a-z0-9_]{3,32}',context['alias']) is None
                or context['original_device_id']!=caller['device_id'] or caller['owner_id']!='owner'
                or type(context['retire_parent_safety_obligation']) is not bool
                or not isinstance(context['remaining_steps'],list)
                or any(v not in ('REGISTRY_REMOVE','CREDENTIAL_OVERWRITE','CREDENTIAL_UNLINK') for v in context['remaining_steps'])
                or len(set(context['remaining_steps']))!=len(context['remaining_steps'])):raise ReauthError('CLEANUP_CONTEXT_UNVERIFIED')
        return dict(context)

    @staticmethod
    def _subject(caller,context):
        return digest({'owner_id':caller['owner_id'],'device_id':caller['device_id'],
                       'native_domain':context['account_control_domain'],'purpose':PURPOSE})

    async def _counter(self,db,subject):
        row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'throttle:'+subject,))).fetchone()
        if row is None:return {'failures':[],'locked_until':0}
        try:
            value=json.loads(row['value'])
            if (not isinstance(value,dict) or set(value)!={'failures','locked_until'} or not isinstance(value['failures'],list)
                    or len(value['failures'])>AuthThrottle.policy('approval_challenge').max_failures
                    or any(type(v) is not int or v<0 for v in value['failures'])
                    or type(value['locked_until']) is not int or value['locked_until']<0):raise ValueError()
        except (ValueError,TypeError,KeyError):raise ReauthError('CLEANUP_REAUTH_LOCK_STATE_UNKNOWN',503) from None
        return value

    async def _check_lock(self,db,subject):
        counter=await self._counter(db,subject);now=self.clock()
        if counter['locked_until']>now:
            raise ReauthError('CLEANUP_REAUTH_LOCKED',429,retry_after=counter['locked_until']-now,locked_until=counter['locked_until'])
        return counter

    async def _write_counter(self,db,subject,value):
        await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms',
            (EPHEMERAL+'throttle:'+subject,json.dumps(value,sort_keys=True,separators=(',',':')),self.clock()*1000))

    async def _failed(self,db,subject):
        policy=AuthThrottle.policy('approval_challenge');counter=await self._counter(db,subject);now=self.clock()
        failures=[v for v in counter['failures'] if now-policy.window_seconds<v<=now]
        failures.append(now);failures=failures[-policy.max_failures:]
        locked=now+policy.lockout_seconds if len(failures)>=policy.max_failures else 0
        await self._write_counter(db,subject,{'failures':failures,'locked_until':locked})
        return locked

    @staticmethod
    def parameters(context,actor_key_ref):return {'purpose':PURPOSE,'context':context,'actor_key_ref':actor_key_ref,'execution_authority':False}

    async def current_actor(self,db,caller):
        # The real composition authorizer reads the actual enrolled approval
        # key/current transport-proof binding under this SAME Store writer.
        ref=await self.authorize(db,caller)
        import re
        if not isinstance(ref,str) or re.fullmatch(r'[0-9a-f]{64}',ref) is None:
            raise ReauthError('CLEANUP_CURRENT_ACTOR_UNVERIFIED',503)
        return ref

    @staticmethod
    def text(context):return 'Confirm identity for this pending local cleanup; this does not approve cleanup. '+digest(context)

    async def issue(self,caller,context):
        context=self.context(context,caller);subject=self._subject(caller,context)
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor_key_ref=await self.current_actor(db,caller)
                await self._check_lock(db,subject)
                issued=await self.approvals.issue(device_id=caller['device_id'],source_command_id=SOURCE,turn_id=None,
                    action_id=ACTION,text=self.text(context),project_id=None,parameters=self.parameters(context,actor_key_ref),
                    ttl_seconds=OwnerApprovalService.DEFAULT_TTL_SECONDS,_db=db)
                await db.commit()
            except BaseException:await db.rollback();raise
        return {'purpose':PURPOSE,'challenge_id':issued.challenge_id,'canonical':issued.canonical,
                'expires_at_unix':issued.expires_at_unix,'context_digest':digest(context),'execution_authority':False}

    async def verify(self,caller,context,challenge_id,signature_b64):
        context=self.context(context,caller);subject=self._subject(caller,context)
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor_key_ref=await self.current_actor(db,caller)
                await self._check_lock(db,subject)
                try:
                    verified=await self.approvals.verify_and_consume(challenge_id=challenge_id,source_command_id=SOURCE,
                        signature_b64=signature_b64,device_id=caller['device_id'],turn_id=None,action_id=ACTION,
                        text=self.text(context),project_id=None,parameters=self.parameters(context,actor_key_ref),_db=db)
                except OwnerApprovalError as error:
                    if str(error)=='approval_signature_invalid':
                        # Only a genuine bad proof for its valid scoped challenge counts.
                        locked=await self._failed(db,subject);await db.commit()
                        now=self.clock()
                        raise ReauthError('CLEANUP_REAUTH_LOCKED' if locked>now else 'CLEANUP_REAUTH_PROOF_INVALID',
                            429 if locked>now else 403,retry_after=max(0,locked-now),locked_until=locked or None) from None
                    raise ReauthError('CLEANUP_REAUTH_'+str(error).upper(),403) from None
                now=self.clock()
                if now>=verified['expires_at_unix']:raise ReauthError('CLEANUP_REAUTH_EXPIRED')
                fact_id=verified['operation_id']
                fact={'schema':'van.account-cleanup-reauth/1','purpose':PURPOSE,'owner_id':'owner',
                    'device_id':caller['device_id'],'actor_key_ref':actor_key_ref,'context':context,'created_at_unix':now,
                    'expires_at_unix':verified['expires_at_unix'],'original_proof_ref':verified['authority_ref'],
                    'execution_authority':False}
                fact['fact_digest']=digest(fact)
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (EPHEMERAL+'fact:'+fact_id,json.dumps(fact,sort_keys=True,separators=(',',':')),now*1000))
                await self._write_counter(db,subject,{'failures':[],'locked_until':0})
                await db.commit()
            except BaseException:await db.rollback();raise
        return {'reauth_fact_id':fact_id,'fact_digest':fact['fact_digest'],'expires_at_unix':fact['expires_at_unix'],
                'purpose':PURPOSE,'execution_authority':False}

    async def require_fact(self,db,caller,context,fact_id,actor_key_ref):
        subject=self._subject(caller,context);await self._check_lock(db,subject)
        row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+fact_id,))).fetchone()
        if row is None:raise ReauthError('CLEANUP_REAUTH_MISSING_OR_SPENT')
        try:
            fact=json.loads(row['value']);proof=fact.pop('fact_digest')
            if (set(fact)!={'schema','purpose','owner_id','device_id','actor_key_ref','context','created_at_unix','expires_at_unix','original_proof_ref','execution_authority'}
                    or fact['schema']!='van.account-cleanup-reauth/1' or fact['purpose']!=PURPOSE
                    or fact['owner_id']!=caller['owner_id'] or fact['device_id']!=caller['device_id'] or fact['context']!=context
                    or fact['execution_authority'] is not False or proof!=digest(fact)
                    or type(fact['created_at_unix']) is not int or type(fact['expires_at_unix']) is not int
                    or not fact['created_at_unix']<fact['expires_at_unix']<=fact['created_at_unix']+OwnerApprovalService.DEFAULT_TTL_SECONDS):raise ValueError()
        except (KeyError,TypeError,ValueError,AttributeError):raise ReauthError('CLEANUP_REAUTH_FACT_UNKNOWN',503) from None
        if fact['actor_key_ref']!=actor_key_ref:raise ReauthError('CLEANUP_REAUTH_ACTOR_CHANGED')
        if self.clock()>=fact['expires_at_unix']:raise ReauthError('CLEANUP_REAUTH_EXPIRED')
        return {**fact,'fact_digest':proof}

    async def prune(self,db):
        # Only this new discriminated raw family; no original/used/admission refs.
        return await prune_ephemeral(db,self.clock()*1000)

    async def admit(self,caller,context,fact_id,*,challenge_id,signature_b64,text,parameters,current_request_deadline):
        """One SQL winner consumes BOTH approvals and records the native child intent.

        An exact replay reads this original admission; it never dispatches again.
        Native claiming/physical outcome is a separate owner, not this commit.
        """
        context=self.context(context,caller)
        request_digest=digest({'context':context,'fact_id':fact_id,'challenge_id':challenge_id,'text_digest':digest(text),'parameters_digest':digest(parameters)})
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor_key_ref=await self.current_actor(db,caller)
                row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+challenge_id,))).fetchone()
                if row is not None:
                    try:
                        old=json.loads(row['value'])
                        if (not isinstance(old,dict) or old['request_digest']!=request_digest or old['device_id']!=caller['device_id']
                                or old['owner_id']!='owner' or old['context']!=context
                                or old['admission_digest']!=digest({k:v for k,v in old.items() if k!='admission_digest'})):raise ValueError()
                    except (KeyError,ValueError,TypeError):raise ReauthError('CLEANUP_ORIGINAL_ADMISSION_CONFLICT') from None
                    await db.rollback()
                    return old,False
                fact=await self.require_fact(db,caller,context,fact_id,actor_key_ref)
                try:
                    proof=await self.approvals.verify_and_consume(challenge_id=challenge_id,source_command_id='account:account_remove',
                        signature_b64=signature_b64,device_id=caller['device_id'],turn_id=None,action_id=ACTION,
                        text=text,project_id=None,parameters=parameters,_db=db)
                except OwnerApprovalError as error:
                    if str(error)=='approval_signature_invalid':
                        locked=await self._failed(db,self._subject(caller,context));await db.commit();now=self.clock()
                        raise ReauthError('CLEANUP_REAUTH_LOCKED' if locked>now else 'CLEANUP_ACTION_PROOF_INVALID',
                            429 if locked>now else 403,retry_after=max(0,locked-now),locked_until=locked or None) from None
                    raise ReauthError('CLEANUP_ACTION_'+str(error).upper(),403) from None
                if type(current_request_deadline) is not int:raise ReauthError('CLEANUP_CURRENT_REQUEST_UNVERIFIED',403)
                expiry=min(fact['expires_at_unix'],proof['expires_at_unix'],current_request_deadline)
                # The verifier/reads may wait; no carried early clock or expired lock.
                await self._check_lock(db,self._subject(caller,context))
                now=self.clock()
                if now>=expiry:raise ReauthError('CLEANUP_PERMISSION_EXPIRED')
                record={'schema':'van.account-cleanup-admission/1','owner_id':'owner','device_id':caller['device_id'],
                    'operation_id':challenge_id,'actor_key_ref':actor_key_ref,'context':context,'request_digest':request_digest,
                    'reauth_fact_digest':fact['fact_digest'],'created_at_unix':now,'expires_at_unix':expiry,
                    'authority_ref':proof['authority_ref'],'approval_text_digest':digest(text),'approval_parameters_digest':digest(parameters),
                    'reauth_fact_id':fact_id,'state':'ADMITTED_NOT_NATIVE_COMPLETION'}
                record['admission_digest']=digest(record)
                removed=await db.execute('DELETE FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+fact_id,))
                if removed.rowcount!=1:raise ReauthError('CLEANUP_REAUTH_MISSING_OR_SPENT')
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (USED+fact_id,json.dumps({'fact_digest':fact['fact_digest'],'child_operation_id':challenge_id,
                        'parent_operation_id':context['parent_operation_id'],'plan_ref':context['plan_ref'],
                        'owner_id':caller['owner_id'],'device_id':caller['device_id'],
                        'account_control_domain':context['account_control_domain']},sort_keys=True,separators=(',',':')),now*1000))
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (ADMISSIONS+challenge_id,json.dumps(record,sort_keys=True,separators=(',',':')),now*1000))
                if self.clock()>=expiry:raise ReauthError('CLEANUP_PERMISSION_EXPIRED')
                await db.commit()
            except BaseException:await db.rollback();raise
        return record,True


async def prune_ephemeral(db,now_ms):
    """Only aged, well-formed, expired NEW-purpose raw families; unknown holds.

    Native references/used/admission identities are outside this discriminator.
    A corrupt timestamp cannot erase an active lock or fresh unspent fact.
    """
    cutoff=now_ms-int(RETENTION_DAYS[RetentionClass.EPHEMERAL])*86400*1000
    rows=await (await db.execute('SELECT key,value,updated_at_unix_ms FROM runtime_meta WHERE key GLOB ? AND updated_at_unix_ms<?',
        (EPHEMERAL+'*',cutoff))).fetchall()
    deleted=0
    for row in rows:
        try:
            value=json.loads(row['value']);kind=row['key'][len(EPHEMERAL):].split(':',1)[0]
            if not isinstance(value,dict):continue
            if kind in {'fact','challenge'}:
                if (type(value.get('expires_at_unix')) is not int or type(value.get('created_at_unix')) is not int
                        or not 0<value['created_at_unix']<value['expires_at_unix']
                        or value['created_at_unix']*1000>=cutoff or value['expires_at_unix']*1000>now_ms):continue
                if kind=='fact':
                    if (set(value)!={'schema','purpose','owner_id','device_id','actor_key_ref','context','created_at_unix','expires_at_unix','original_proof_ref','execution_authority','fact_digest'}
                            or value['schema']!='van.account-cleanup-reauth/1' or value['purpose']!=PURPOSE
                            or value['execution_authority'] is not False or value['fact_digest']!=digest({k:v for k,v in value.items() if k!='fact_digest'})):continue
                    AccountReauthentication.context(value['context'],{'owner_id':value['owner_id'],'device_id':value['device_id']})
                else:
                    if (set(value)!={'challenge_id','device_id','source_command_id','turn_id','action_id','intent_digest','intent_digest_schema','parameters_bound','parameters','canonical','expires_at_unix','created_at_unix'}
                            or value['challenge_id']!=row['key'][len(EPHEMERAL+'challenge:'):]
                            or value['source_command_id'] not in {SOURCE,'account:account_remove'} or value['action_id']!=ACTION
                            or value['turn_id'] is not None or value['intent_digest_schema']!=OwnerApprovalService.INTENT_SCHEMA
                            or value['parameters_bound'] is not True or not isinstance(value['parameters'],dict)):continue
                    if value['canonical']!=OwnerApprovalService._canonical_challenge(challenge_id=value['challenge_id'],device_id=value['device_id'],
                            source_command_id=value['source_command_id'],turn_id=None,action_id=value['action_id'],
                            intent_digest=value['intent_digest'],expires_at_unix=value['expires_at_unix']):continue
            elif kind=='throttle':
                failures=value.get('failures');locked=value.get('locked_until')
                if (set(value)!={'failures','locked_until'} or not isinstance(failures,list)
                        or any(type(v) is not int or v<0 for v in failures) or type(locked) is not int or locked<0
                        or locked*1000>now_ms or any(v*1000>=cutoff for v in failures)):continue
            else:continue
        except (ValueError,TypeError,KeyError,ReauthError,OwnerApprovalError):continue
        result=await db.execute('DELETE FROM runtime_meta WHERE key=? AND value=? AND updated_at_unix_ms=?',
            (row['key'],row['value'],row['updated_at_unix_ms']))
        deleted+=result.rowcount
    return deleted
