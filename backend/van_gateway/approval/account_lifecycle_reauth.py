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

EPHEMERAL='account_lifecycle_ephemeral:'
ADMISSIONS='account_lifecycle_admission:'
USED='account_lifecycle_used_reauth:'
PURPOSE='ACCOUNT_LOCAL_LIFECYCLE_REAUTH_DATA'
ACTION='trading.account.account_remove'
SOURCE='account:account_remove:lifecycle:reauth'
CONTEXT_KEYS={'alias','lifecycle_id','incarnation','account_control_domain','original_device_id',
              'review_digest','resource_version','variant','semantic_digest'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


from van_gateway.approval.account_reauth import ReauthError


class LifecyclePurposeChallenges(OwnerApprovalService):
    # Storage discriminator only: SAME enrolled key, algorithm and canonical
    # verifier. Both new-purpose raw challenge roles share the scoped 7d owner.
    PREFIX=EPHEMERAL+'challenge:'


class AccountLifecycleReauthentication:
    # Per-family storage/purpose DATA, all using the SAME enrolled verifier.
    EPHEMERAL=EPHEMERAL
    ADMISSIONS=ADMISSIONS
    USED=USED
    PURPOSE=PURPOSE
    ACTION=ACTION
    SOURCE=SOURCE
    ACTION_SOURCE='account:account_remove'
    FACT_SCHEMA='van.account-lifecycle-reauth/1'
    ADMISSION_SCHEMA='van.account-lifecycle-admission/1'
    SUBJECT_KEY='lifecycle_id'
    APPROVALS=LifecyclePurposeChallenges

    def __init__(self,store,authorize,*,clock=None):
        self.store,self.authorize=store,authorize
        self.approvals=self.APPROVALS(store)
        self.clock=clock or (lambda:int(time.time()))

    @staticmethod
    def context(context,caller):
        import re
        if (not isinstance(context,dict) or set(context)!=CONTEXT_KEYS
                or caller.get('owner_id')!='owner' or context.get('original_device_id')!=caller.get('device_id')
                or not isinstance(caller.get('device_id'),str) or not caller['device_id']
                or context.get('variant') not in {'DELETE_GRACE','CANCEL_DELETE','IMMEDIATE_DISCONNECT'}):raise ReauthError('LIFECYCLE_CONTEXT_UNVERIFIED')
        for k in ('incarnation','account_control_domain','review_digest','resource_version','semantic_digest'):
            if not isinstance(context[k],str) or re.fullmatch(r'[0-9a-f]{64}',context[k]) is None:raise ReauthError('LIFECYCLE_CONTEXT_UNVERIFIED')
        if (not isinstance(context['alias'],str) or re.fullmatch(r'[a-z0-9_]{3,32}',context['alias']) is None
                or not isinstance(context['lifecycle_id'],str) or not context['lifecycle_id']):raise ReauthError('LIFECYCLE_CONTEXT_UNVERIFIED')
        return dict(context)

    @classmethod
    def _subject(cls,caller,context):
        return digest({'owner_id':caller['owner_id'],'device_id':caller['device_id'],
                       'native_domain':context['account_control_domain'],'purpose':cls.PURPOSE})

    async def _counter(self,db,subject):
        row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(self.EPHEMERAL+'throttle:'+subject,))).fetchone()
        if row is None:return {'failures':[],'locked_until':0}
        try:
            value=json.loads(row['value'])
            if (not isinstance(value,dict) or set(value)!={'failures','locked_until'} or not isinstance(value['failures'],list)
                    or len(value['failures'])>AuthThrottle.policy('approval_challenge').max_failures
                    or any(type(v) is not int or v<0 for v in value['failures'])
                    or type(value['locked_until']) is not int or value['locked_until']<0):raise ValueError()
        except (ValueError,TypeError,KeyError):raise ReauthError('LIFECYCLE_REAUTH_LOCK_STATE_UNKNOWN',503) from None
        return value

    async def _check_lock(self,db,subject):
        counter=await self._counter(db,subject);now=self.clock()
        if counter['locked_until']>now:
            raise ReauthError('LIFECYCLE_REAUTH_LOCKED',429,retry_after=counter['locked_until']-now,locked_until=counter['locked_until'])
        return counter

    async def _write_counter(self,db,subject,value):
        await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms',
            (self.EPHEMERAL+'throttle:'+subject,json.dumps(value,sort_keys=True,separators=(',',':')),self.clock()*1000))

    async def _failed(self,db,subject):
        policy=AuthThrottle.policy('approval_challenge');counter=await self._counter(db,subject);now=self.clock()
        failures=[v for v in counter['failures'] if now-policy.window_seconds<v<=now]
        failures.append(now);failures=failures[-policy.max_failures:]
        locked=now+policy.lockout_seconds if len(failures)>=policy.max_failures else 0
        await self._write_counter(db,subject,{'failures':failures,'locked_until':locked})
        return locked

    @classmethod
    def parameters(cls,context,actor_key_ref):return {'purpose':cls.PURPOSE,'context':context,'actor_key_ref':actor_key_ref,'execution_authority':False}

    async def validate_admission_sources(self,db,caller,context,parameters):
        return None

    async def current_actor(self,db,caller):
        # The real composition authorizer reads the actual enrolled approval
        # key/current transport-proof binding under this SAME Store writer.
        ref=await self.authorize(db,caller)
        import re
        if not isinstance(ref,str) or re.fullmatch(r'[0-9a-f]{64}',ref) is None:
            raise ReauthError('LIFECYCLE_CURRENT_ACTOR_UNVERIFIED',503)
        return ref

    @staticmethod
    def text(context):return 'Confirm identity for this local account lifecycle request; this does not approve deletion or cancellation. '+digest(context)

    async def issue(self,caller,context):
        context=self.context(context,caller);subject=self._subject(caller,context)
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor_key_ref=await self.current_actor(db,caller)
                await self._check_lock(db,subject)
                issued=await self.approvals.issue(device_id=caller['device_id'],source_command_id=self.SOURCE,turn_id=None,
                    action_id=self.ACTION,text=self.text(context),project_id=None,parameters=self.parameters(context,actor_key_ref),
                    ttl_seconds=OwnerApprovalService.DEFAULT_TTL_SECONDS,_db=db)
                await db.commit()
            except BaseException:await db.rollback();raise
        return {'purpose':self.PURPOSE,'challenge_id':issued.challenge_id,'canonical':issued.canonical,
                'expires_at_unix':issued.expires_at_unix,'context_digest':digest(context),'execution_authority':False}

    async def verify(self,caller,context,challenge_id,signature_b64):
        context=self.context(context,caller);subject=self._subject(caller,context)
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor_key_ref=await self.current_actor(db,caller)
                await self._check_lock(db,subject)
                try:
                    verified=await self.approvals.verify_and_consume(challenge_id=challenge_id,source_command_id=self.SOURCE,
                        signature_b64=signature_b64,device_id=caller['device_id'],turn_id=None,action_id=self.ACTION,
                        text=self.text(context),project_id=None,parameters=self.parameters(context,actor_key_ref),_db=db)
                except OwnerApprovalError as error:
                    if str(error)=='approval_signature_invalid':
                        # Only a genuine bad proof for its valid scoped challenge counts.
                        locked=await self._failed(db,subject);await db.commit()
                        now=self.clock()
                        raise ReauthError('LIFECYCLE_REAUTH_LOCKED' if locked>now else 'LIFECYCLE_REAUTH_PROOF_INVALID',
                            429 if locked>now else 403,retry_after=max(0,locked-now),locked_until=locked or None) from None
                    raise ReauthError('LIFECYCLE_REAUTH_'+str(error).upper(),403) from None
                now=self.clock()
                if now>=verified['expires_at_unix']:raise ReauthError('LIFECYCLE_REAUTH_EXPIRED')
                fact_id=verified['operation_id']
                fact={'schema':self.FACT_SCHEMA,'purpose':self.PURPOSE,'owner_id':'owner',
                    'device_id':caller['device_id'],'actor_key_ref':actor_key_ref,'context':context,'created_at_unix':now,
                    'expires_at_unix':verified['expires_at_unix'],'original_proof_ref':verified['authority_ref'],
                    'execution_authority':False}
                fact['fact_digest']=digest(fact)
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (self.EPHEMERAL+'fact:'+fact_id,json.dumps(fact,sort_keys=True,separators=(',',':')),now*1000))
                await self._write_counter(db,subject,{'failures':[],'locked_until':0})
                await db.commit()
            except BaseException:await db.rollback();raise
        return {'reauth_fact_id':fact_id,'fact_digest':fact['fact_digest'],'expires_at_unix':fact['expires_at_unix'],
                'purpose':self.PURPOSE,'execution_authority':False}

    async def require_fact(self,db,caller,context,fact_id,actor_key_ref):
        subject=self._subject(caller,context);await self._check_lock(db,subject)
        row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(self.EPHEMERAL+'fact:'+fact_id,))).fetchone()
        if row is None:raise ReauthError('LIFECYCLE_REAUTH_MISSING_OR_SPENT')
        try:
            fact=json.loads(row['value']);proof=fact.pop('fact_digest')
            if (set(fact)!={'schema','purpose','owner_id','device_id','actor_key_ref','context','created_at_unix','expires_at_unix','original_proof_ref','execution_authority'}
                    or fact['schema']!=self.FACT_SCHEMA or fact['purpose']!=self.PURPOSE
                    or fact['owner_id']!=caller['owner_id'] or fact['device_id']!=caller['device_id']
                    or fact['execution_authority'] is not False or proof!=digest(fact)
                    or type(fact['created_at_unix']) is not int or type(fact['expires_at_unix']) is not int
                    or not fact['created_at_unix']<fact['expires_at_unix']<=fact['created_at_unix']+OwnerApprovalService.DEFAULT_TTL_SECONDS):raise ValueError()
        except (KeyError,TypeError,ValueError,AttributeError):raise ReauthError('LIFECYCLE_REAUTH_FACT_UNKNOWN',503) from None
        if fact['context']!=context:raise ReauthError('LIFECYCLE_REAUTH_CONTEXT_CHANGED')
        if fact['actor_key_ref']!=actor_key_ref:raise ReauthError('LIFECYCLE_REAUTH_ACTOR_CHANGED')
        if self.clock()>=fact['expires_at_unix']:raise ReauthError('LIFECYCLE_REAUTH_EXPIRED')
        return {**fact,'fact_digest':proof}

    async def prune(self,db):
        # Only this new discriminated raw family; no original/used/admission refs.
        return await prune_ephemeral(db,self.clock()*1000,profile=type(self))

    def finalize_admission(self,record,*,parameters=None):return record

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
                await self.validate_admission_sources(db,caller,context,parameters)
                row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(self.ADMISSIONS+challenge_id,))).fetchone()
                if row is not None:
                    try:
                        old=json.loads(row['value'])
                        if (not isinstance(old,dict) or old['request_digest']!=request_digest or old['device_id']!=caller['device_id']
                                or old['owner_id']!='owner' or old['context']!=context
                                or old['admission_digest']!=digest({k:v for k,v in old.items() if k!='admission_digest'})):raise ValueError()
                    except (KeyError,ValueError,TypeError):raise ReauthError('LIFECYCLE_ORIGINAL_ADMISSION_CONFLICT') from None
                    await db.rollback()
                    return old,False
                fact=await self.require_fact(db,caller,context,fact_id,actor_key_ref)
                try:
                    proof=await self.approvals.verify_and_consume(challenge_id=challenge_id,source_command_id=self.ACTION_SOURCE,
                        signature_b64=signature_b64,device_id=caller['device_id'],turn_id=None,action_id=self.ACTION,
                        text=text,project_id=None,parameters=parameters,_db=db)
                except OwnerApprovalError as error:
                    if str(error)=='approval_signature_invalid':
                        locked=await self._failed(db,self._subject(caller,context));await db.commit();now=self.clock()
                        raise ReauthError('LIFECYCLE_REAUTH_LOCKED' if locked>now else 'LIFECYCLE_ACTION_PROOF_INVALID',
                            429 if locked>now else 403,retry_after=max(0,locked-now),locked_until=locked or None) from None
                    raise ReauthError('LIFECYCLE_ACTION_'+str(error).upper(),403) from None
                if type(current_request_deadline) is not int:raise ReauthError('LIFECYCLE_CURRENT_REQUEST_UNVERIFIED',403)
                expiry=min(fact['expires_at_unix'],proof['expires_at_unix'],current_request_deadline)
                # The verifier/reads may wait; no carried early clock or expired lock.
                await self._check_lock(db,self._subject(caller,context))
                now=self.clock()
                if now>=expiry:raise ReauthError('LIFECYCLE_PERMISSION_EXPIRED')
                record={'schema':self.ADMISSION_SCHEMA,'owner_id':'owner','device_id':caller['device_id'],
                    'operation_id':challenge_id,'reauth_purpose':self.PURPOSE,'actor_key_ref':actor_key_ref,'context':context,'request_digest':request_digest,
                    'reauth_fact_digest':fact['fact_digest'],'reauth_proof_ref':fact['original_proof_ref'],'created_at_unix':now,'expires_at_unix':expiry,
                    'authority_ref':proof['authority_ref'],'approval_text_digest':digest(text),'approval_parameters_digest':digest(parameters),
                    'reauth_fact_id':fact_id,'state':'ADMITTED_NOT_NATIVE_COMPLETION'}
                record=self.finalize_admission(record,parameters=parameters)
                record['admission_digest']=digest(record)
                removed=await db.execute('DELETE FROM runtime_meta WHERE key=?',(self.EPHEMERAL+'fact:'+fact_id,))
                if removed.rowcount!=1:raise ReauthError('LIFECYCLE_REAUTH_MISSING_OR_SPENT')
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (self.USED+fact_id,json.dumps({'fact_digest':fact['fact_digest'],'child_operation_id':challenge_id,
                        self.SUBJECT_KEY:context[self.SUBJECT_KEY],'incarnation':context['incarnation'],
                        'owner_id':caller['owner_id'],'device_id':caller['device_id'],
                        'account_control_domain':context['account_control_domain']},sort_keys=True,separators=(',',':')),now*1000))
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (self.ADMISSIONS+challenge_id,json.dumps(record,sort_keys=True,separators=(',',':')),now*1000))
                if self.clock()>=expiry:raise ReauthError('LIFECYCLE_PERMISSION_EXPIRED')
                await db.commit()
            except BaseException:await db.rollback();raise
        return record,True


async def prune_ephemeral(db,now_ms,*,profile=None):
    """Only aged, well-formed, expired NEW-purpose raw families; unknown holds.

    Native references/used/admission identities are outside this discriminator.
    A corrupt timestamp cannot erase an active lock or fresh unspent fact.
    """
    if profile is None:
        # Existing retention owner dispatches both explicit new raw families;
        # original admissions/used refs/native history remain outside prefixes.
        return (await prune_ephemeral(db,now_ms,profile=AccountLifecycleReauthentication)
                +await prune_ephemeral(db,now_ms,profile=AccountRestrictionReauthentication))
    cutoff=now_ms-int(RETENTION_DAYS[RetentionClass.EPHEMERAL])*86400*1000
    rows=await (await db.execute('SELECT key,value,updated_at_unix_ms FROM runtime_meta WHERE key GLOB ? AND updated_at_unix_ms<?',
        (profile.EPHEMERAL+'*',cutoff))).fetchall()
    deleted=0
    for row in rows:
        try:
            value=json.loads(row['value']);kind=row['key'][len(profile.EPHEMERAL):].split(':',1)[0]
            if not isinstance(value,dict):continue
            if kind in {'fact','challenge'}:
                if (type(value.get('expires_at_unix')) is not int or type(value.get('created_at_unix')) is not int
                        or not 0<value['created_at_unix']<value['expires_at_unix']
                        or value['created_at_unix']*1000>=cutoff or value['expires_at_unix']*1000>now_ms):continue
                if kind=='fact':
                    if (set(value)!={'schema','purpose','owner_id','device_id','actor_key_ref','context','created_at_unix','expires_at_unix','original_proof_ref','execution_authority','fact_digest'}
                            or value['schema']!=profile.FACT_SCHEMA or value['purpose']!=profile.PURPOSE
                            or value['execution_authority'] is not False or value['fact_digest']!=digest({k:v for k,v in value.items() if k!='fact_digest'})):continue
                    profile.context(value['context'],{'owner_id':value['owner_id'],'device_id':value['device_id']})
                else:
                    if (set(value)!={'challenge_id','device_id','source_command_id','turn_id','action_id','intent_digest','intent_digest_schema','parameters_bound','parameters','canonical','expires_at_unix','created_at_unix'}
                            or value['challenge_id']!=row['key'][len(profile.EPHEMERAL+'challenge:'):]
                            or value['source_command_id'] not in {profile.SOURCE,profile.ACTION_SOURCE} or value['action_id']!=profile.ACTION
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


class RestrictionPurposeChallenges(OwnerApprovalService):
    # Storage discriminator only; same enrolled device verifier and algorithm.
    PREFIX='account_restriction_ephemeral:challenge:'


class AccountRestrictionReauthentication(AccountLifecycleReauthentication):
    EPHEMERAL='account_restriction_ephemeral:'
    ADMISSIONS='account_restriction_admission:'
    USED='account_restriction_used_reauth:'
    PURPOSE='ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA'
    ACTION='trading.account.account_restrict'
    SOURCE='account:account_restrict:reauth'
    ACTION_SOURCE='account:account_restrict'
    FACT_SCHEMA='van.account-restriction-reauth/1'
    ADMISSION_SCHEMA='van.account-restriction-admission/1'
    SUBJECT_KEY='restriction_id'
    APPROVALS=RestrictionPurposeChallenges
    VARIANTS={'RESTRICT','BEGIN_REAUTH','COMPLETE_REAUTH','RECONCILE_DATA'}
    REASONS={'OWNER_REQUEST','CREDENTIALS_EXPIRED','BROKER_DISABLED','KILL_SWITCH','VERIFICATION_FAILED'}

    @classmethod
    def context(cls,context,caller):
        import re
        fields={'alias','restriction_id','incarnation','account_control_domain','original_device_id',
                'review_digest','resource_version','variant','semantic_digest','expected_revision',
                'expected_digest','reason_code','parent_operation_id','parent_admission_digest'}
        if (not isinstance(context,dict) or set(context)!=fields
                or caller.get('owner_id')!='owner' or context.get('original_device_id')!=caller.get('device_id')
                or not isinstance(caller.get('device_id'),str) or not caller['device_id']
                or type(context.get('variant')) is not str or context['variant'] not in cls.VARIANTS
                or type(context.get('reason_code')) is not str or context['reason_code'] not in cls.REASONS):
            raise ReauthError('RESTRICTION_CONTEXT_UNVERIFIED')
        for name in ('incarnation','account_control_domain','review_digest','resource_version','semantic_digest'):
            if type(context[name]) is not str or re.fullmatch(r'[0-9a-f]{64}',context[name]) is None:
                raise ReauthError('RESTRICTION_CONTEXT_UNVERIFIED')
        if (type(context['alias']) is not str or re.fullmatch(r'[a-z0-9_]{3,32}',context['alias']) is None
                or type(context['restriction_id']) is not str or not 20<=len(context['restriction_id'])<=128
                or type(context['expected_revision']) is not int or context['expected_revision']<0):
            raise ReauthError('RESTRICTION_CONTEXT_UNVERIFIED')
        initial=context['variant']=='RESTRICT' and context['expected_revision']==0
        empty_resolution=context['variant']=='RECONCILE_DATA' and context['expected_revision']==0
        if initial:
            if (context['restriction_id']!='proposed:'+context['resource_version']
                    or context['expected_digest'] is not None):raise ReauthError('RESTRICTION_CONTEXT_UNVERIFIED')
        elif (re.fullmatch(r'[A-Za-z0-9_-]{20,128}',context['restriction_id']) is None
                or empty_resolution and context['expected_digest'] is not None
                or not empty_resolution and (context['expected_revision']<1 or type(context['expected_digest']) is not str
                    or re.fullmatch(r'[0-9a-f]{64}',context['expected_digest']) is None)):
            raise ReauthError('RESTRICTION_CONTEXT_UNVERIFIED')
        parent=context['parent_operation_id']
        if context['variant']=='RECONCILE_DATA':
            if (type(parent) is not str or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',parent) is None
                    or type(context['parent_admission_digest']) is not str
                    or re.fullmatch(r'[0-9a-f]{64}',context['parent_admission_digest']) is None):
                raise ReauthError('RESTRICTION_CONTEXT_UNVERIFIED')
        elif parent is not None or context['parent_admission_digest'] is not None:
            raise ReauthError('RESTRICTION_CONTEXT_UNVERIFIED')
        return dict(context)

    @staticmethod
    def text(context):
        return 'Confirm identity for account restriction recovery; this does not approve a state change or grant trading. '+digest(context)

    async def validate_admission_sources(self,db,caller,context,parameters):
        refs=parameters.get('restriction_review',{}).get('view',{}).get('related_operations')
        if context['variant']!='RECONCILE_DATA':
            if refs!=[]:raise ReauthError('RESTRICTION_UNEXPECTED_CAUSAL_PROOF')
            return
        if type(refs) is not list or not 1<=len(refs)<=64:raise ReauthError('RESTRICTION_CAUSAL_PROOF_CAPACITY')
        if [r.get('operation_id') for r in refs]!=sorted({r.get('operation_id') for r in refs}):
            raise ReauthError('RESTRICTION_CAUSAL_SOURCE_CHANGED')
        for ref in refs:
            raw=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(self.ADMISSIONS+ref['operation_id'],))).fetchone()
            if raw is None:raise ReauthError('RESTRICTION_CAUSAL_SOURCE_CHANGED')
            record=json.loads(raw['value']);c=record['context']
            if (record['admission_digest']!=ref['admission_digest'] or record['admission_digest']!=digest({k:v for k,v in record.items() if k!='admission_digest'})
                    or record['device_id']!=caller['device_id'] or c['incarnation']!=context['incarnation']
                    or c['account_control_domain']!=context['account_control_domain'] or c['alias']!=context['alias']
                    or record['native_review_digest']!=ref['native_review_digest']
                    or record['authority_ref']+'::review:'+record['native_review_digest']!=ref['authority_ref']
                    or digest(record['native_request'])!=ref['request_digest']
                    or c['parent_operation_id']!=ref['parent_operation_id'] or c['parent_admission_digest']!=ref['parent_admission_digest']):
                raise ReauthError('RESTRICTION_CAUSAL_SOURCE_CHANGED')

    def finalize_admission(self,record,*,parameters=None):
        try:
            if type(parameters) is not dict or set(parameters)!={'restriction_review','native_request','reauth_fact_digest'}:
                raise ValueError()
            review=parameters['restriction_review'];request=parameters['native_request'];context=record['context']
            expected={'alias':context['alias'],'variant':context['variant']}
            if context['variant']=='RESTRICT':expected['reason_code']=context['reason_code']
            if context['variant']!='RESTRICT' or context['expected_revision']>0:
                expected.update(restriction_id=context['restriction_id'],expected_revision=context['expected_revision'])
                if context['expected_digest'] is not None:expected['expected_digest']=context['expected_digest']
            if context['variant']=='RECONCILE_DATA':expected['parent_operation_id']=context['parent_operation_id']
            if context['variant']!='RESTRICT':
                expected.update(reauth_fact_id=record['reauth_fact_id'],reauth_fact_digest=record['reauth_fact_digest'])
            if request!=expected:raise ValueError()
            if (type(request) is not dict or any(type(k) is not str or k.startswith('_') for k in request)
                    or review['request_digest']!=digest(request)
                    or review['semantic_digest']!=context['semantic_digest']
                    or context['semantic_digest']!=digest({k:v for k,v in request.items() if k not in {'reauth_fact_id','reauth_fact_digest'}})
                    or review['context_digest']!=context['review_digest']
                    or review['context_digest']!=digest({k:v for k,v in review.items() if k not in {'review_digest','request_digest','context_digest'}})
                    or review['resource_version']!=context['resource_version']
                    or review['review_digest']!=digest({k:v for k,v in review.items() if k!='review_digest'})
                    or parameters['reauth_fact_digest']!=record['reauth_fact_digest']):raise ValueError()
        except (TypeError,KeyError,ValueError):raise ReauthError('RESTRICTION_APPROVAL_CONTEXT_MISMATCH',403) from None
        return {**record,'action':'account_restrict','purpose':'ACCOUNT_RESTRICTION_CONTROL',
                'native_review_digest':review['review_digest'],'native_review':json.loads(json.dumps(review)),
                'native_request':dict(request)}

    async def admit_restriction(self,caller,context,*,challenge_id,signature_b64,text,parameters,current_request_deadline):
        """Narrowing restriction needs actual substantive A4, not a recovery fact.

        Recovery uses inherited distinct-purpose fact plus a separate A4; neither
        path can grant a sending mode, mandate, or entry activation.
        """
        context=self.context(context,caller)
        if context['variant']!='RESTRICT':raise ReauthError('RESTRICTION_RECOVERY_REAUTH_REQUIRED',403)
        request_digest=digest({'context':context,'fact_id':None,'challenge_id':challenge_id,
                              'text_digest':digest(text),'parameters_digest':digest(parameters)})
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                actor=await self.current_actor(db,caller);await self._check_lock(db,self._subject(caller,context))
                await self.validate_admission_sources(db,caller,context,parameters)
                row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(self.ADMISSIONS+challenge_id,))).fetchone()
                if row is not None:
                    try:
                        old=json.loads(row['value'])
                        if (old['request_digest']!=request_digest or old['device_id']!=caller['device_id']
                                or old['owner_id']!='owner' or old['context']!=context
                                or old['admission_digest']!=digest({k:v for k,v in old.items() if k!='admission_digest'})):
                            raise ValueError()
                    except (KeyError,ValueError,TypeError):raise ReauthError('RESTRICTION_ORIGINAL_ADMISSION_CONFLICT') from None
                    await db.rollback();return old,False
                try:
                    proof=await self.approvals.verify_and_consume(challenge_id=challenge_id,source_command_id=self.ACTION_SOURCE,
                        signature_b64=signature_b64,device_id=caller['device_id'],turn_id=None,action_id=self.ACTION,
                        text=text,project_id=None,parameters=parameters,_db=db)
                except OwnerApprovalError as error:
                    if str(error)=='approval_signature_invalid':
                        locked=await self._failed(db,self._subject(caller,context));await db.commit();now=self.clock()
                        raise ReauthError('RESTRICTION_APPROVAL_LOCKED' if locked>now else 'RESTRICTION_APPROVAL_INVALID',
                            429 if locked>now else 403,retry_after=max(0,locked-now),locked_until=locked or None) from None
                    raise ReauthError('RESTRICTION_APPROVAL_UNVERIFIED',403) from None
                if type(current_request_deadline) is not int:raise ReauthError('RESTRICTION_CURRENT_REQUEST_UNVERIFIED',403)
                expiry=min(proof['expires_at_unix'],current_request_deadline)
                await self._check_lock(db,self._subject(caller,context));now=self.clock()
                if now>=expiry:raise ReauthError('RESTRICTION_PERMISSION_EXPIRED',403)
                record=self.finalize_admission({'schema':self.ADMISSION_SCHEMA,'owner_id':'owner','device_id':caller['device_id'],
                    'operation_id':challenge_id,'reauth_purpose':None,'actor_key_ref':actor,'context':context,
                    'request_digest':request_digest,'reauth_fact_digest':None,'reauth_proof_ref':None,
                    'created_at_unix':now,'expires_at_unix':expiry,'authority_ref':proof['authority_ref'],
                    'approval_text_digest':digest(text),'approval_parameters_digest':digest(parameters),
                    'reauth_fact_id':None,'state':'ADMITTED_NOT_NATIVE_COMPLETION'},parameters=parameters)
                record['admission_digest']=digest(record)
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (self.ADMISSIONS+challenge_id,json.dumps(record,sort_keys=True,separators=(',',':')),now*1000))
                if self.clock()>=expiry:raise ReauthError('RESTRICTION_PERMISSION_EXPIRED',403)
                await db.commit()
            except BaseException:await db.rollback();raise
        return record,True
