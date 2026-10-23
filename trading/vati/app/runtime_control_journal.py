"""Durable original recovery requests and atomic local-control outcomes.

This journal performs no broker IO and does not clear any risk state itself.
An actor must hold its current runtime lease, validate the state reference, and
append its domain effect plus finish() within the same ledger.atomic block.
"""
from dataclasses import dataclass
import time
from copy import deepcopy

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind,make_event
from vati.app.runtime_control_protocol import RecoveryIntent,RecoveryProof,RuntimeControlError

PRODUCER='vati-runtime-recovery-control'
SCHEMA='vati.runtime-control-operation/1'
EXPIRED_SCHEMA='vati.runtime-control-expired-refusal/1'
FINAL=frozenset({'APPLIED','REFUSED'})
REASONS=frozenset({'APPLIED','APPROVAL_EXPIRED','OWNER_KEY_UNREGISTERED','SESSION_CHANGED',
    'STATE_CHANGED','PRECONDITION_UNMET','ACTOR_LEASE_LOST'})


class RuntimeControlConflict(RuntimeControlError):
    pass


class RuntimeControlStoreError(RuntimeControlError):
    pass


@dataclass(frozen=True)
class RuntimeControlState:
    intent: RecoveryIntent
    proof: RecoveryProof
    public_key_pem: str
    authority_ref: str
    phase: str
    event_ref: str
    accepted_at_unix: int
    result: dict | None=None
    expired_without_dispatch: bool=False

    def public(self):
        return {'operation_id':self.proof.operation_id,'phase':self.phase,
            'intent':self.intent.body(),'authority_ref':self.authority_ref,
            'accepted_at_unix':self.accepted_at_unix,'expires_at_unix':self.proof.expires_at_unix,
            'native_event_ref':self.event_ref,'result':deepcopy(self.result)}


def validate_result(result,phase,*,expired_without_dispatch=False):
    expected={'reason_code','effect_refs','entry_authority_granted','remaining_kill','state_ref'}
    if not isinstance(result,dict) or set(result)!=expected or result['reason_code'] not in REASONS:
        raise RuntimeControlStoreError('native recovery result shape is invalid')
    if (phase=='APPLIED')!=(result['reason_code']=='APPLIED') or result['entry_authority_granted'] is not False:
        raise RuntimeControlStoreError('native recovery result phase is invalid')
    from vati.risk.contracts import KillSwitchTrigger
    if expired_without_dispatch:
        if (phase!='REFUSED' or result['reason_code']!='APPROVAL_EXPIRED'
            or result['effect_refs']!=[] or result['remaining_kill'] is not None or result['state_ref'] is not None):
            raise RuntimeControlStoreError('expired original refusal cannot assert an effect or current risk state')
        return
    if (not isinstance(result['remaining_kill'],list)
        or any(x not in {k.value for k in KillSwitchTrigger} for x in result['remaining_kill'])):
        raise RuntimeControlStoreError('native remaining kill state is invalid')
    import re
    if not isinstance(result['state_ref'],str) or not re.fullmatch(r'[0-9a-f]{64}',result['state_ref']):
        raise RuntimeControlStoreError('native recovery readback state is invalid')
    if (not isinstance(result['effect_refs'],list)
        or any(not isinstance(x,str) or not re.fullmatch(r'[0-9a-f]{64}',x) for x in result['effect_refs'])
        or (phase=='REFUSED' and result['effect_refs'])
        or (phase=='APPLIED' and not result['effect_refs'])):
        raise RuntimeControlStoreError('native recovery effect references are invalid')


class RuntimeControlJournal:
    def __init__(self,ledger,*,clock=None):
        self.ledger=ledger;self.clock=clock or (lambda:int(time.time()))

    def _states(self):
        if not self.ledger.verify_chain()[0]:raise RuntimeControlStoreError('native recovery history integrity failed')
        states={}
        for event in self.ledger.iter(EventKind.SESSION):
            if event.producer!=PRODUCER:continue
            try:
                p=event.payload
                if (event.hash!=canonical_hash(event.body()) or p['schema'] not in {SCHEMA,EXPIRED_SCHEMA}
                    or set(p)!={'schema','intent','proof','public_key_pem','authority_ref','phase','previous_ref','accepted_at_unix','result'}):
                    raise ValueError('native recovery record shape')
                intent=RecoveryIntent.from_mapping(p['intent']);proof=RecoveryProof.from_mapping(p['proof'])
                previous=states.get(proof.operation_id)
                if event.correlation_id!=proof.operation_id or type(p['accepted_at_unix']) is not int:
                    raise ValueError('native original recovery identity')
                expired=p['schema']==EXPIRED_SCHEMA
                if expired:
                    # A signed, expired original may only receive a terminal
                    # no-dispatch refusal. It never enters the actor queue.
                    if (previous is not None or p['phase']!='REFUSED' or p['previous_ref']
                        or p['accepted_at_unix']<proof.expires_at_unix
                        or p['accepted_at_unix']!=event.received_time_ms//1000):
                        raise ValueError('expired original refusal lineage')
                    reference=proof.verify_signature(intent,{proof.key_id:p['public_key_pem']})
                    validate_result(p['result'],'REFUSED',expired_without_dispatch=True)
                else:
                    reference=proof.verify(intent,{proof.key_id:p['public_key_pem']},now_unix=p['accepted_at_unix'])
                if reference!=p['authority_ref']:raise ValueError('native recovery proof reference')
                if expired:
                    pass
                elif previous is None:
                    if (p['phase']!='REQUESTED' or p['previous_ref'] or p['result'] is not None
                        or p['accepted_at_unix']!=event.received_time_ms//1000):
                        raise ValueError('native recovery first phase')
                else:
                    if (previous.phase!='REQUESTED' or p['phase'] not in FINAL
                        or p['previous_ref']!=previous.event_ref
                        or (intent,proof,p['public_key_pem'],reference,p['accepted_at_unix'])!=(previous.intent,previous.proof,
                            previous.public_key_pem,previous.authority_ref,previous.accepted_at_unix)):
                        raise ValueError('native recovery outcome lineage')
                    validate_result(p['result'],p['phase'])
                    if p['phase']=='APPLIED':self._validate_effects(previous,p['result'],before_ref=event.hash)
                states[proof.operation_id]=RuntimeControlState(intent,proof,p['public_key_pem'],reference,p['phase'],
                    event.hash,p['accepted_at_unix'],p['result'],expired)
            except (KeyError,TypeError,ValueError,AttributeError) as exc:
                raise RuntimeControlStoreError('native recovery record is invalid') from exc
        return states

    def _append(self,state,phase,*,previous_ref='',result=None):
        now=state.accepted_at_unix if phase=='REQUESTED' else self.clock()
        if state.expired_without_dispatch and phase!='REFUSED':
            raise RuntimeControlStoreError('an expired original refusal cannot authorize another phase')
        payload={'schema':EXPIRED_SCHEMA if state.expired_without_dispatch else SCHEMA,'intent':state.intent.body(),'proof':state.proof.public_record(),
            'public_key_pem':state.public_key_pem,'authority_ref':state.authority_ref,'phase':phase,
            'previous_ref':previous_ref,'accepted_at_unix':state.accepted_at_unix,'result':result}
        event=make_event(EventKind.SESSION,PRODUCER,payload,event_time_ms=now*1000,received_time_ms=now*1000,
            correlation_id=state.proof.operation_id)
        self.ledger.append(event)
        return RuntimeControlState(state.intent,state.proof,state.public_key_pem,state.authority_ref,phase,
            event.hash,state.accepted_at_unix,result,state.expired_without_dispatch)

    def enqueue(self,intent,proof,keys):
        if not isinstance(intent,RecoveryIntent) or not isinstance(proof,RecoveryProof):
            raise RuntimeControlError('native recovery intent or proof type is invalid')
        if RecoveryIntent.from_mapping(intent.body())!=intent:
            raise RuntimeControlError('native recovery arguments are not canonical')
        RecoveryProof.from_mapping(proof.public_record())
        with self.ledger.atomic():
            old=self._states().get(proof.operation_id)
            if old is not None:
                if old.intent!=intent or old.proof!=proof:
                    raise RuntimeControlConflict('original recovery request differs from its signed actor or target')
                return old
            now=self.clock()
            try:
                ref=proof.verify(intent,keys,now_unix=now)
            except RuntimeControlError:
                if type(now) is not int or now<proof.expires_at_unix:
                    raise
                ref=proof.verify_signature(intent,keys)
                # Absence is established under the same ledger writer lock as
                # this terminal event. No REQUESTED state or actor effect exists.
                state=RuntimeControlState(intent,proof,keys[proof.key_id],ref,'REFUSED','',now,
                    expired_without_dispatch=True)
                result={'reason_code':'APPROVAL_EXPIRED','effect_refs':[],'entry_authority_granted':False,
                    'remaining_kill':None,'state_ref':None}
                validate_result(result,'REFUSED',expired_without_dispatch=True)
                return self._append(state,'REFUSED',result=result)
            state=RuntimeControlState(intent,proof,keys[proof.key_id],ref,'REQUESTED','',now)
            return self._append(state,'REQUESTED')

    def status(self,operation_id,device_id):
        if not isinstance(operation_id,str):return None
        with self.ledger.atomic():
            state=self._states().get(operation_id)
            # A different device does not gain an operation-existence oracle.
            return state if state is not None and state.intent.device_id==device_id else None

    def pending(self,session_id):
        with self.ledger.atomic():
            return tuple(s for s in self._states().values() if s.phase=='REQUESTED' and s.intent.session_id==session_id)

    def pending_account(self,account_alias):
        with self.ledger.atomic():
            return tuple(s for s in self._states().values() if s.phase=='REQUESTED' and s.intent.account_alias==account_alias)

    def finish(self,state,phase,result):
        if phase not in FINAL:raise RuntimeControlStoreError('native recovery completion phase is invalid')
        validate_result(result,phase)
        with self.ledger.atomic():
            current=self._states().get(state.proof.operation_id)
            if current is None or (current.intent,current.proof)!=(state.intent,state.proof):
                raise RuntimeControlConflict('native original recovery request is unavailable')
            if current.phase in FINAL:
                if current.phase==phase and current.result==result:return current
                raise RuntimeControlConflict('native original recovery already has a different outcome')
            if current.event_ref!=state.event_ref:raise RuntimeControlConflict('native original recovery phase changed')
            if phase=='APPLIED':self._validate_effects(current,result)
            return self._append(current,phase,previous_ref=current.event_ref,result=result)

    def _validate_effects(self,state,result,*,before_ref=None):
        from vati.risk.lockouts import RESET_EVENT,DRAWDOWN_RESUME_EVENT
        rows=list(self.ledger.iter())
        indices={e.hash:i for i,e in enumerate(rows)}
        lower=indices.get(state.event_ref,-1)
        upper=indices.get(before_ref,len(rows))
        if lower<0 or any(not lower<indices.get(ref,-1)<upper for ref in result['effect_refs']):
            raise RuntimeControlStoreError('native recovery effect is outside its original operation')
        effects={e.hash:e for e in rows if e.hash in result['effect_refs']}
        if set(effects)!=set(result['effect_refs']):raise RuntimeControlStoreError('native recovery effect evidence is missing')
        for event in effects.values():
            p=event.payload;args=dict(state.intent.arguments)
            if (event.hash!=canonical_hash(event.body()) or event.producer!='vati-cycle'
                or event.correlation_id!=state.intent.session_id
                or p.get('account_alias')!=state.intent.account_alias
                or p.get('owner_signature_ref')!=state.authority_ref):
                raise RuntimeControlStoreError('native recovery effect belongs to another actor or target')
            action=state.intent.action
            if action=='clear_kill_switch':
                valid=(event.kind is EventKind.KILL_SWITCH and p.get('cleared') is True and p.get('trigger')==args['trigger'])
            elif action=='reset_loss_streak':
                valid=(event.kind is EventKind.SESSION and p.get('event')==RESET_EVENT and p.get('scope')==args['scope'])
            else:
                valid=(event.kind is EventKind.SESSION and p.get('event')==DRAWDOWN_RESUME_EVENT)
            if not valid:raise RuntimeControlStoreError('native recovery effect does not match the approved action')
