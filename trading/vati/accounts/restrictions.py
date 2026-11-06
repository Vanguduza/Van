"""Strict restriction DATA, distinct from mode/mandate and unlink history.

Public metadata contains no credential values or provider authority. Legacy
records have no restriction row; their previous lifecycle state stays unknown.
"""
import copy
import re
from vati.accounts.registry import AccountRegistryError
from vati.core.canonical import canonical_hash

SCHEMA='vati.account-restriction/1'
PHASES={'RESTRICTED','REAUTH_PENDING','LINKED_READ_ONLY'}
REASONS={'OWNER_REQUEST','CREDENTIALS_EXPIRED','BROKER_DISABLED','KILL_SWITCH','VERIFICATION_FAILED'}
REASON_TEXT={'OWNER_REQUEST':'Owner requested a restriction.',
    'CREDENTIALS_EXPIRED':'Owner reports credential re-verification is required.',
    'BROKER_DISABLED':'Owner reports the broker account is disabled.',
    'KILL_SWITCH':'Owner activated the entry restriction.',
    'VERIFICATION_FAILED':'Owner reports account verification failed.'}
TRANSITION_TEXT={'REAUTH_PENDING':'Owner requested fresh reauthentication; entries remain blocked.',
    'LINKED_READ_ONLY':'Fresh native identity was verified for read-only recovery; no mode or mandate granted.'}
HEX=re.compile(r'^[0-9a-f]{64}$')
ID=re.compile(r'^[A-Za-z0-9_-]{20,128}$')
ALIAS=re.compile(r'^[a-z0-9_]{3,32}$')
SECRET_TEXT=re.compile(r'(?i)(password|token|api[_-]?key)\s*[:=]')
FIELDS={'schema','alias','restriction_id','incarnation','device_id','account_control_domain',
    'revision','phase','reason_code','reason','created_at_unix','updated_at_unix','origin','events','prior_phase_observation'}
ORIGIN={'operation_id','request_digest','resource_version','review_digest','admission_digest'}
EVENT={'operation_id','from_phase','to_phase','at_unix','device_id','why','request_digest',
    'resource_version','admission_digest','previous_digest'}

def _require(value,message):
    if not value:raise AccountRegistryError(message)

def _text(value,maximum):return isinstance(value,str) and 0<len(value)<=maximum and not SECRET_TEXT.search(value)
def _hash(value):return isinstance(value,str) and bool(HEX.fullmatch(value))
def _id(value):return isinstance(value,str) and bool(ID.fullmatch(value))
def _time(value):return type(value) is int and 0<value<2**63

def validate_record(row):
    _require(isinstance(row,dict) and set(row)==FIELDS,'restriction DATA fields are invalid; HOLD')
    _require(row['schema']==SCHEMA and isinstance(row['alias'],str) and ALIAS.fullmatch(row['alias']),'restriction identity is invalid; HOLD')
    _require(_id(row['restriction_id']) and _hash(row['incarnation']) and _text(row['device_id'],128)
        and _hash(row['account_control_domain']),'restriction scope is invalid; HOLD')
    _require(type(row['revision']) is int and 0<row['revision']<2**63 and isinstance(row['phase'],str) and row['phase'] in PHASES,'restriction phase/revision is invalid; HOLD')
    _require(isinstance(row['reason_code'],str) and row['reason_code'] in REASONS
        and row['reason']==REASON_TEXT[row['reason_code']],'restriction reason must be a fixed owner-selected code; HOLD')
    _require(_time(row['created_at_unix']) and _time(row['updated_at_unix']) and row['updated_at_unix']>=row['created_at_unix'],'restriction chronology is invalid; HOLD')
    origin=row['origin'];events=row['events']
    _require(isinstance(origin,dict) and set(origin)==ORIGIN and origin['operation_id']==row['restriction_id']
        and all(_hash(origin[k]) for k in ORIGIN-{'operation_id'}),'restriction original bindings are invalid; HOLD')
    _require(isinstance(events,list) and len(events)==row['revision'] and bool(events),'restriction transition history is unavailable; HOLD')
    seen=set();previous=None;prior_time=0
    for index,event in enumerate(events):
        _require(isinstance(event,dict) and set(event)==EVENT,'restriction transition fields are invalid; HOLD')
        _require(isinstance(event['to_phase'],str) and event['to_phase'] in PHASES
            and (event['from_phase'] is None or isinstance(event['from_phase'],str)),'restriction transition phase is invalid; HOLD')
        _require(_id(event['operation_id']) and event['operation_id'] not in seen and event['device_id']==row['device_id']
            and event['why']==(row['reason'] if event['to_phase']=='RESTRICTED' else TRANSITION_TEXT[event['to_phase']])
            and _time(event['at_unix']) and event['at_unix']>=prior_time
            and all(_hash(event[k]) for k in ('request_digest','resource_version','admission_digest')),'restriction transition binding is invalid; HOLD')
        if index==0:
            # Absent legacy lifecycle evidence stays null, never inferred as
            # ACTIVE_ELIGIBLE from a mode label or a configured credential.
            _require(event['operation_id']==row['restriction_id'] and (event['from_phase'] is None or isinstance(event['from_phase'],str)
                and event['from_phase'] in {'LINKED_READ_ONLY','KYC_PENDING','ACTIVE_ELIGIBLE'})
                and event['to_phase']=='RESTRICTED' and event['previous_digest'] is None
                and event['at_unix']==row['created_at_unix']
                and all(event[k]==origin[k] for k in ('request_digest','resource_version','admission_digest')),
                'restriction initial transition is invalid; HOLD')
            observation=row['prior_phase_observation']
            if event['from_phase'] is None:
                _require(isinstance(observation,dict) and set(observation)=={'observed','reason','source_ref'}
                    and observation['observed'] is False and observation['reason']=='PRIOR_CANONICAL_PHASE_NOT_OBSERVED'
                    and _hash(observation['source_ref']),'restriction null prior phase lacks provenance; HOLD')
            else:
                _require(isinstance(observation,dict) and set(observation)=={'observed','phase','proof_ref'}
                    and observation['observed'] is True and observation['phase']==event['from_phase']
                    and _hash(observation['proof_ref']),'restriction prior phase lacks genuine observation; HOLD')
        else:
            _require(event['from_phase']==previous and (previous,event['to_phase']) in {
                ('RESTRICTED','REAUTH_PENDING'),('REAUTH_PENDING','LINKED_READ_ONLY'),('REAUTH_PENDING','RESTRICTED'),
                ('LINKED_READ_ONLY','RESTRICTED')}
                and _hash(event['previous_digest']),'restriction transition is not permitted; HOLD')
            predecessor=copy.deepcopy(row)
            predecessor.update(revision=index,phase=previous,updated_at_unix=events[index-1]['at_unix'],events=copy.deepcopy(events[:index]))
            _require(event['previous_digest']==canonical_hash(predecessor),'restriction predecessor digest differs; HOLD')
        seen.add(event['operation_id']);previous=event['to_phase'];prior_time=event['at_unix']
    _require(previous==row['phase'] and prior_time==row['updated_at_unix'],'restriction current state differs from transition history; HOLD')
    return copy.deepcopy(row)

def validate_records(current,history):
    _require(isinstance(current,dict) and isinstance(history,dict),'restriction registry maps are invalid; HOLD')
    seen=set();operations=set()
    for historical,rows in [(False,current),(True,history)]:
        for key,raw in rows.items():
            row=validate_record(raw)
            _require(key==(row['restriction_id'] if historical else row['alias']),'restriction registry key differs; HOLD')
            _require(row['restriction_id'] not in seen,'restriction incarnation is duplicated; HOLD')
            seen.add(row['restriction_id'])
            for event in row['events']:
                _require(event['operation_id'] not in operations,'restriction operation is duplicated; HOLD');operations.add(event['operation_id'])
    return copy.deepcopy(current),copy.deepcopy(history)

def public_record(row):
    value=validate_record(row)
    return {k:value[k] for k in ('schema','alias','restriction_id','incarnation','device_id','account_control_domain',
        'revision','phase','reason_code','reason','created_at_unix','updated_at_unix')}|{
        'record_digest':canonical_hash(value),'entry_permitted':False,
        'mode_or_mandate_granted':False,'protection_or_manual_exit_cancelled':False,
        'transition_reason':value['events'][-1]['why'],'prior_phase_observation':value['prior_phase_observation']}

def require_entry_unrestricted(registry,alias):
    if alias in registry._restrictions:
        raise AccountRegistryError('Account restriction requires separate read-only recovery and existing mode/mandate admission; new entries refused')

def initial_record(*,alias,operation_id,device_id,domain,resource_version,request_digest,
                   review_digest,admission_digest,reason_code,now):
    """DATA construction only; the native owner separately verifies admission."""
    _require(reason_code in REASONS,'restriction reason code is invalid')
    reason=REASON_TEXT[reason_code]
    return validate_record({'schema':SCHEMA,'alias':alias,'restriction_id':operation_id,
        'incarnation':resource_version,'device_id':device_id,'account_control_domain':domain,
        'revision':1,'phase':'RESTRICTED','reason_code':reason_code,'reason':reason,
        'created_at_unix':now,'updated_at_unix':now,
        'prior_phase_observation':{'observed':False,'reason':'PRIOR_CANONICAL_PHASE_NOT_OBSERVED','source_ref':resource_version},
        'origin':{'operation_id':operation_id,'request_digest':request_digest,'resource_version':resource_version,
            'review_digest':review_digest,'admission_digest':admission_digest},
        'events':[{'operation_id':operation_id,'from_phase':None,'to_phase':'RESTRICTED','at_unix':now,
            'device_id':device_id,'why':reason,'request_digest':request_digest,'resource_version':resource_version,
            'admission_digest':admission_digest,'previous_digest':None}]})

def transition_record(row,*,operation_id,device_id,phase,request_digest,resource_version,admission_digest,now):
    prior=validate_record(row);value=copy.deepcopy(prior)
    value['events'].append({'operation_id':operation_id,'from_phase':prior['phase'],'to_phase':phase,
        'at_unix':now,'device_id':device_id,'why':prior['reason'] if phase=='RESTRICTED' else TRANSITION_TEXT.get(phase),
        'request_digest':request_digest,'resource_version':resource_version,'admission_digest':admission_digest,
        'previous_digest':canonical_hash(prior)})
    value.update(revision=prior['revision']+1,phase=phase,updated_at_unix=now)
    return validate_record(value)
