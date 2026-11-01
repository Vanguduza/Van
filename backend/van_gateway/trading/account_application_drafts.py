"""LAC-135 owner-authored account preview; never a broker application or authority."""
from __future__ import annotations
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import re
import time
from typing import Literal

import aiosqlite
from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from van_gateway.artifacts.models import ArtifactKind
from van_gateway.owner_privacy import _SECRET

PREFIX = 'account_application_draft:'
FAMILY = 'account_application_selection:'
SOURCE_TYPE = 'account_application_preview'
TTL_MS = 300_000  # Local review freshness only; OWNER_STATE is never aged into deletion.
MAX_BYTES = 2048
MAX_DRAFTS = 256
UUID4 = r'^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$'
HEADERS = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class DraftError(ValueError):
    def __init__(self,code,status=409,field=None):
        self.code,self.status,self.field=code,status,field
        super().__init__(code)


class DraftInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    operation_id:str=Field(pattern=UUID4)
    family_id:str=Field(pattern=UUID4)
    expected_revision:int=Field(ge=0,le=1_000_000)
    variant:Literal['OPEN_NEW_LIVE']
    broker_kind:Literal['DERIV','CTRADER','MT5','MT5_EA','ZSE_OWNER_TICKET']


class EraseInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    expected_digest:str=Field(pattern=r'^[0-9a-f]{64}$')


class ProfileContext(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    state:Literal['SINGLE_OWNER_GATEWAY']
    account_profile_ref:None
    configuration_digest:str=Field(pattern=r'^[0-9a-f]{64}$')


class DraftContext(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    owner_id:Literal['owner']
    device_id:str=Field(min_length=1)
    profile_context:ProfileContext


class SourceRevision(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    kind:Literal['MODULE_FILE_AT_SERVICE_START']
    sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


class UnresolvedProvider(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    state:Literal['UNRESOLVED']
    descriptor_ref:None
    version:None
    effect_confirmation_eligible:Literal[False]


class DraftCanonical(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    schema_name:Literal['van.account-application-draft/1']=Field(alias='schema')
    request:DraftInput
    context:DraftContext
    source_revision:SourceRevision
    draft_id:str=Field(pattern=r'^ad_[0-9a-f]{64}$')
    selection_revision:int=Field(ge=1)
    created_at_ms:int=Field(ge=0)
    expires_at_ms:int=Field(ge=0)
    state:Literal['DRAFT_STORED_NOT_SUBMITTED']
    provider_selection:UnresolvedProvider
    execution_authority:Literal[False]


class DraftReceipt(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    schema_name:Literal['van.account-application-draft-receipt/1']=Field(alias='schema')
    operation_id:str=Field(pattern=UUID4)
    draft_id:str=Field(pattern=r'^ad_[0-9a-f]{64}$')
    family_id:str=Field(pattern=UUID4)
    selection_revision:int=Field(ge=1)
    body_digest:str=Field(pattern=r'^[0-9a-f]{64}$')
    artifact_id:str
    artifact_digest:str=Field(pattern=r'^[0-9a-f]{64}$')
    created_at_ms:int
    expires_at_ms:int
    state:Literal['DRAFT_STORED_NOT_SUBMITTED']
    provider_qualified:Literal[False]
    execution_authority:Literal[False]


class DraftView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    receipt:DraftReceipt
    body:DraftCanonical
    selection_current:bool|None
    current_selection_state:Literal['CURRENT','SUPERSEDED','UNKNOWN']
    freshness:Literal['NOT_YET_ISSUED','EXPIRED','WITHIN_ORIGINAL_WINDOW']
    effect_confirmation_eligible:Literal[False]


class ErasedView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    state:Literal['ERASED']
    operation_id:str
    canonical_bodies_remaining:Literal[0]
    projections_remaining:Literal[0]
    execution_authority:Literal[False]


class RefusedView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    state:Literal['REFUSED']
    operation_id:str
    request_digest:str=Field(pattern=r'^[0-9a-f]{64}$')
    caller_device_id:str
    reason:Literal['ACCOUNT_DRAFT_REQUEST_EXPIRED']
    received_at_ms:int
    expires_at_ms:int
    execution_authority:Literal[False]


class EraseResult(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    state:Literal['ERASED','NO_DRAFT_CONTENT']
    operation_id:str
    body_digest:str|None=None
    canonical_bodies_removed:int=Field(ge=0,le=1)
    projections_removed:int=Field(ge=0,le=1)
    execution_authority:Literal[False]


class SelectionView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    family_id:str
    revision:int=Field(ge=0)
    draft_id:str|None
    effect_confirmation_eligible:Literal[False]


def _key(prefix,owner,identity):
    return prefix+digest({'owner_id':owner,'id':identity})


def _decode(raw):
    try:
        value=json.loads(raw,object_pairs_hook=_distinct,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,TypeError,RecursionError):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503) from None


async def _row(db,key):
    row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(key,))).fetchone()
    return None if row is None else _decode(row['value'])


async def _save(db,key,value,now):
    await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms',
        (key,canonical(value),now))


class AccountApplicationDrafts:
    def __init__(self,store,artifacts,authorize,*,clock=None):
        self.store,self.artifacts,self.authorize=store,artifacts,authorize
        self.clock=clock or (lambda:int(time.time()*1000))
        self.source_revision={'kind':'MODULE_FILE_AT_SERVICE_START','sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.tasks=set()

    def policy(self):
        return {'schema':'van.account-application-draft-policy/1','ttl_ms':TTL_MS,
            'max_body_bytes':MAX_BYTES,'max_drafts':MAX_DRAFTS,'retention':'OWNER_STATE_EXPLICIT_ERASE',
            'provider_context':'UNRESOLVED','effect_confirmation_eligible':False}

    async def _validate(self,db,record,owner,operation_id):
        try:
            if set(record)!={'body','body_digest','artifact_id'}:raise ValueError()
            body=record['body'];DraftCanonical.model_validate(body)
            request=DraftInput.model_validate(body['request']).model_dump()
            if (set(body)!={'schema','request','context','source_revision','draft_id','selection_revision','created_at_ms','expires_at_ms','state','provider_selection','execution_authority'}
                or body['schema']!='van.account-application-draft/1' or body['state']!='DRAFT_STORED_NOT_SUBMITTED'
                or body['execution_authority'] is not False
                or body['provider_selection']!={'state':'UNRESOLVED','descriptor_ref':None,'version':None,'effect_confirmation_eligible':False}
                or request['operation_id']!=operation_id or body['request']!=request
                or body['draft_id']!='ad_'+digest({'owner_id':owner,'operation_id':operation_id})
                or body['selection_revision']!=request['expected_revision']+1
                or type(body['created_at_ms']) is not int or type(body['expires_at_ms']) is not int
                or body['created_at_ms']<0 or body['expires_at_ms']!=body['created_at_ms']+TTL_MS
                or body['context']['owner_id']!=owner
                or set(body['context'])!={'owner_id','device_id','profile_context'}
                or set(body['context']['profile_context'])!={'state','account_profile_ref','configuration_digest'}
                or body['context']['profile_context']['state']!='SINGLE_OWNER_GATEWAY'
                or body['context']['profile_context']['account_profile_ref'] is not None
                or not isinstance(body['context']['device_id'],str)
                or set(body['source_revision'])!={'kind','sha256'}
                or body['source_revision'].get('kind')!='MODULE_FILE_AT_SERVICE_START'
                or not re.fullmatch(r'[0-9a-f]{64}',body['source_revision']['sha256'])
                or not re.fullmatch(r'[0-9a-f]{64}',body['context']['profile_context']['configuration_digest'])
                or record['body_digest']!=digest(body)):
                raise ValueError()
            artifact=await (await db.execute('SELECT * FROM owner_artifacts WHERE artifact_id=?',(record['artifact_id'],))).fetchone()
            if (not artifact or artifact['owner_id']!=owner or artifact['canonical_source_type']!=SOURCE_TYPE
                or artifact['canonical_source_id']!=body['draft_id'] or artifact['canonical_source_digest']!=record['body_digest']
                or artifact['expires_at_ms']!=body['expires_at_ms'] or artifact['created_at_ms']!=body['created_at_ms']
                or artifact['sensitivity']!='OWNER_PRIVATE' or artifact['kind']!='PLAN'
                or artifact['title']!='Live account intent preview'
                or artifact['summary']!='Owner draft only; no provider submission or execution authority.'
                or any(artifact[k] is not None for k in ('project_id','command_id','mission_id','execution_id','mime_type','content_ref','preview_ref'))
                or artifact['evidence_refs_json']!='[]'):
                raise ValueError()
        except (ValueError,TypeError,KeyError,ValidationError):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503) from None
        return record

    @staticmethod
    def _refused(record,operation_id):
        try:RefusedView.model_validate({**record,'execution_authority':False})
        except (ValueError,TypeError):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503) from None
        if (set(record)!={'state','operation_id','request_digest','caller_device_id','reason','received_at_ms','expires_at_ms'}
            or record['operation_id']!=operation_id or record['reason']!='ACCOUNT_DRAFT_REQUEST_EXPIRED'
            or type(record['received_at_ms']) is not int or type(record['expires_at_ms']) is not int
            or record['expires_at_ms']!=record['received_at_ms']+TTL_MS):
            raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)

    async def selection(self,family_id,caller):
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE');await self.authorize(db,caller,False)
            current=await self._current(db,caller['owner_id'],family_id)
            return {'family_id':family_id,**current,'effect_confirmation_eligible':False}

    @staticmethod
    def _selection_witness(record,owner,operation_id):
        try:
            witness=record['selection_witness']
            fields={'family_scope','draft_id','publication_revision','erase_revision','witness_hash'}
            if (not isinstance(witness,dict) or set(witness)!=fields
                or not re.fullmatch(re.escape(FAMILY)+r'[0-9a-f]{64}',witness['family_scope'])
                or witness['draft_id']!='ad_'+digest({'owner_id':owner,'operation_id':operation_id})
                or type(witness['publication_revision']) is not int or witness['publication_revision']<1
                or witness['erase_revision'] is not None and (type(witness['erase_revision']) is not int
                    or witness['erase_revision']!=witness['publication_revision']+1)):
                raise ValueError()
            bound={k:v for k,v in witness.items() if k!='witness_hash'}
            expected=digest({'owner_id':owner,'operation_id':operation_id,'body_digest':record['body_digest'],'selection':bound})
            if witness['witness_hash']!=expected:raise ValueError()
        except (ValueError,TypeError,KeyError):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503) from None
        return witness

    async def _erased(self,db,record,owner,operation_id):
        try:
            receipt=record['receipt']
            if (set(record) not in ({'state','body_digest','receipt'},{'state','body_digest','receipt','selection_witness'}) or record['state']!='ERASED'
                or set(receipt)!={'state','operation_id','body_digest','canonical_bodies_removed','projections_removed','execution_authority'}
                or receipt['state']!='ERASED' or receipt['operation_id']!=operation_id
                or receipt['body_digest']!=record['body_digest'] or not re.fullmatch(r'[0-9a-f]{64}',record['body_digest'])
                or type(receipt['canonical_bodies_removed']) is not int or type(receipt['projections_removed']) is not int
                or receipt['canonical_bodies_removed']!=1 or receipt['projections_removed']!=1
                or receipt['execution_authority'] is not False):raise ValueError()
            if 'selection_witness' in record:self._selection_witness(record,owner,operation_id)
            artifact=await (await db.execute('SELECT artifact_id FROM owner_artifacts WHERE owner_id=? AND canonical_source_type=? AND canonical_source_id=?',
                (owner,SOURCE_TYPE,'ad_'+digest({'owner_id':owner,'operation_id':operation_id})))).fetchone()
            if artifact is not None:raise ValueError()
        except (ValueError,KeyError,TypeError):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503) from None
        return receipt

    @staticmethod
    def _receipt(record):
        body=record['body']
        return {'schema':'van.account-application-draft-receipt/1','operation_id':body['request']['operation_id'],
            'draft_id':body['draft_id'],'family_id':body['request']['family_id'],'selection_revision':body['selection_revision'],
            'body_digest':record['body_digest'],'artifact_id':record['artifact_id'],
            'artifact_digest':record['body_digest'],'created_at_ms':body['created_at_ms'],'expires_at_ms':body['expires_at_ms'],
            'state':'DRAFT_STORED_NOT_SUBMITTED','provider_qualified':False,'execution_authority':False}

    async def _current(self,db,owner,family_id):
        """Validate the recorded head against original lifecycle evidence; never repair it.

        Erasure removes the body, but retains only opaque publication/erase
        identities and revisions in its original anti-replay tombstone. A null
        pointer is not evidence of a never-created or lawfully erased family.
        """
        family_scope=_key(FAMILY,owner,family_id)
        head=await _row(db,family_scope)
        rows=await (await db.execute("SELECT key,value FROM runtime_meta WHERE key GLOB ? AND json_valid(value) AND ("
            "(json_extract(value,'$.body.context.owner_id')=? AND json_extract(value,'$.body.request.family_id')=?) OR "
            "json_extract(value,'$.selection_witness.family_scope')=?)",
            (PREFIX+'*',owner,family_id,family_scope))).fetchall()
        # Old unassociated erase receipts remain readable history, but cannot
        # prove which family is virgin/current. Do not invent their lost lineage.
        legacy=await (await db.execute("SELECT key,value FROM runtime_meta WHERE key GLOB ? AND json_valid(value) "
            "AND json_extract(value,'$.state')='ERASED' AND json_type(value,'$.selection_witness') IS NULL",
            (PREFIX+'*',))).fetchall()
        for entry in legacy:
            old=_decode(entry['value']);receipt=old.get('receipt')
            if isinstance(receipt,dict) and isinstance(receipt.get('operation_id'),str):
                if entry['key']==_key(PREFIX,owner,receipt['operation_id']):
                    raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
        events={}
        def add(revision,kind,draft_id):
            if type(revision) is not int or revision<1 or revision in events:
                raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
            events[revision]=(kind,draft_id)
        for entry in rows:
            record=_decode(entry['value'])
            if record.get('state')=='ERASED':
                receipt=record.get('receipt')
                if not isinstance(receipt,dict) or not isinstance(receipt.get('operation_id'),str):
                    raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
                operation_id=receipt['operation_id']
                if entry['key']!=_key(PREFIX,owner,operation_id):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
                await self._erased(db,record,owner,operation_id)
                witness=self._selection_witness(record,owner,operation_id)
                add(witness['publication_revision'],'PUBLISH',witness['draft_id'])
                if witness['erase_revision'] is not None:add(witness['erase_revision'],'ERASE',witness['draft_id'])
            else:
                try:request=DraftInput.model_validate(record['body']['request'])
                except (KeyError,TypeError,ValueError):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503) from None
                if entry['key']!=_key(PREFIX,owner,request.operation_id):raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
                await self._validate(db,record,owner,request.operation_id)
                add(record['body']['selection_revision'],'PUBLISH',record['body']['draft_id'])
        revision=0;selected=None
        for number,(kind,draft_id) in sorted(events.items()):
            if number!=revision+1:raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
            if kind=='PUBLISH':selected=draft_id
            else:
                if selected!=draft_id:raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
                selected=None
            revision=number
        if head is None:
            if events:raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
            return {'revision':0,'draft_id':None}
        if (set(head)!={'revision','draft_id'} or type(head['revision']) is not int
            or not events or head['revision']!=revision or head['draft_id']!=selected):
            raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
        return head

    async def create(self,request,caller,received_at_ms):
        body=request.model_dump()
        if _SECRET.search(canonical(body)):raise DraftError('ACCOUNT_DRAFT_PRIVATE_INPUT',422)
        owner=caller['owner_id'];key=_key(PREFIX,owner,request.operation_id)
        try:
            async with self.store.connection() as db:
                await db.execute('BEGIN IMMEDIATE')
                context=await self.authorize(db,caller,True)
                old=await _row(db,key)
                if old is not None:
                    if old.get('state')=='REFUSED':
                        self._refused(old,request.operation_id)
                        if old['request_digest']!=digest(body):raise DraftError('ACCOUNT_DRAFT_ORIGINAL_REQUEST_CONFLICT')
                        if old['caller_device_id']!=context['device_id']:raise DraftError('ACCOUNT_DRAFT_CALLER_CHANGED',403)
                        raise DraftError(old['reason'])
                    if old.get('state')=='ERASED':
                        await self._erased(db,old,owner,request.operation_id)
                        raise DraftError('ACCOUNT_DRAFT_ERASED',410)
                    old=await self._validate(db,old,owner,request.operation_id)
                    if old['body']['context']['device_id']!=context['device_id']:raise DraftError('ACCOUNT_DRAFT_CALLER_CHANGED',403)
                    if old['body']['request']!=body:raise DraftError('ACCOUNT_DRAFT_ORIGINAL_REQUEST_CONFLICT')
                    return self._receipt(old)
                orphan=await (await db.execute('SELECT artifact_id FROM owner_artifacts WHERE owner_id=? AND canonical_source_type=? AND canonical_source_id=?',
                    (owner,SOURCE_TYPE,'ad_'+digest({'owner_id':owner,'operation_id':request.operation_id})))).fetchone()
                if orphan is not None:raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
                current=await self._current(db,owner,request.family_id)
                if current['revision']!=request.expected_revision:raise DraftError('ACCOUNT_DRAFT_SELECTION_CHANGED')
                now=self.clock()
                if type(received_at_ms) is not int or received_at_ms<0 or now<received_at_ms:raise DraftError('ACCOUNT_DRAFT_CLOCK_UNAVAILABLE',503)
                if now>=received_at_ms+TTL_MS:
                    await _save(db,key,{'state':'REFUSED','operation_id':request.operation_id,'request_digest':digest(body),
                        'caller_device_id':context['device_id'],'reason':'ACCOUNT_DRAFT_REQUEST_EXPIRED',
                        'received_at_ms':received_at_ms,'expires_at_ms':received_at_ms+TTL_MS},now)
                    await db.commit()
                    raise DraftError('ACCOUNT_DRAFT_REQUEST_EXPIRED')
                count=await (await db.execute("SELECT COUNT(*) AS n FROM runtime_meta WHERE key GLOB ? AND json_valid(value) AND json_type(value,'$.body')='object'",(PREFIX+'*',))).fetchone()
                if count['n']>=MAX_DRAFTS:raise DraftError('ACCOUNT_DRAFT_CAPACITY',503)
                # First publication, not a grant. No provider/currentness is inferred.
                original={'schema':'van.account-application-draft/1','request':body,'context':context,
                    'source_revision':self.source_revision,'draft_id':'ad_'+digest({'owner_id':owner,'operation_id':request.operation_id}),
                    'selection_revision':current['revision']+1,'created_at_ms':received_at_ms,'expires_at_ms':received_at_ms+TTL_MS,
                    'state':'DRAFT_STORED_NOT_SUBMITTED','provider_selection':{'state':'UNRESOLVED','descriptor_ref':None,'version':None,'effect_confirmation_eligible':False},
                    'execution_authority':False}
                DraftCanonical.model_validate(original)
                if _SECRET.search(canonical(original)):raise DraftError('ACCOUNT_DRAFT_PRIVATE_INPUT',422)
                hashed=digest(original)
                artifact=await self.artifacts.ensure_projection(kind=ArtifactKind.PLAN,title='Live account intent preview',
                    summary='Owner draft only; no provider submission or execution authority.',owner_id=owner,
                    canonical_source_type=SOURCE_TYPE,canonical_source_id=original['draft_id'],canonical_source_digest=hashed,
                    now_ms=received_at_ms,expires_at_ms=original['expires_at_ms'],_db=db)
                record={'body':original,'body_digest':hashed,'artifact_id':artifact.artifact_id}
                await _save(db,key,record,now)
                await _save(db,_key(FAMILY,owner,request.family_id),{'revision':original['selection_revision'],'draft_id':original['draft_id']},now)
                # Deadline and caller remain current at the actual commit boundary.
                await self.authorize(db,caller,True)
                if self.clock()>=original['expires_at_ms']:raise DraftError('ACCOUNT_DRAFT_REQUEST_EXPIRED')
                await db.commit()
        except (sqlite3.Error,aiosqlite.Error,OSError):
            return await self._recover(request,caller)
        # Reread from a separate connection; transport/commit ACK alone is not the receipt.
        return await self._recover(request,caller)

    async def _recover(self,request,caller):
        try:
            result=await self.inspect(request.operation_id,caller)
            if result.get('state')=='REFUSED':raise DraftError(result['reason'])
            if result.get('state')=='ERASED':raise DraftError('ACCOUNT_DRAFT_ERASED',410)
            if result['body']['request']!=request.model_dump():raise DraftError('ACCOUNT_DRAFT_ORIGINAL_REQUEST_CONFLICT')
            return result['receipt']
        except DraftError as error:
            if error.status in (403,410) or error.code=='ACCOUNT_DRAFT_REQUEST_EXPIRED':raise
            raise DraftError('ACCOUNT_DRAFT_OUTCOME_UNKNOWN',503) from None
        except (sqlite3.Error,aiosqlite.Error,OSError):raise DraftError('ACCOUNT_DRAFT_OUTCOME_UNKNOWN',503) from None

    async def inspect(self,operation_id,caller):
        owner=caller['owner_id']
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            await self.authorize(db,caller,False)
            record=await _row(db,_key(PREFIX,owner,operation_id))
            if record is None:raise DraftError('ACCOUNT_DRAFT_NOT_FOUND',404)
            if record.get('state')=='REFUSED':
                self._refused(record,operation_id)
                return {**record,'execution_authority':False}
            if record.get('state')=='ERASED':
                await self._erased(db,record,owner,operation_id)
                return {'state':'ERASED','operation_id':operation_id,'canonical_bodies_remaining':0,'projections_remaining':0,'execution_authority':False}
            record=await self._validate(db,record,owner,operation_id)
            try:current=await self._current(db,owner,record['body']['request']['family_id'])
            except DraftError as error:
                if error.code!='ACCOUNT_DRAFT_HISTORY_UNKNOWN':raise
                current=None
            selected=None if current is None else current['draft_id']==record['body']['draft_id'] and current['revision']==record['body']['selection_revision']
            return {'receipt':self._receipt(record),'body':record['body'],
                'selection_current':selected,'current_selection_state':'UNKNOWN' if selected is None else 'CURRENT' if selected else 'SUPERSEDED',
                'freshness':'NOT_YET_ISSUED' if self.clock()<record['body']['created_at_ms'] else 'EXPIRED' if self.clock()>=record['body']['expires_at_ms'] else 'WITHIN_ORIGINAL_WINDOW',
                'effect_confirmation_eligible':False}

    async def erase(self,operation_id,expected_digest,caller):
        owner=caller['owner_id']
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE');await self.authorize(db,caller,True)
            key=_key(PREFIX,owner,operation_id);record=await _row(db,key)
            if record is None:raise DraftError('ACCOUNT_DRAFT_NOT_FOUND',404)
            if record.get('state')=='REFUSED':
                self._refused(record,operation_id)
                if record['request_digest']!=expected_digest:raise DraftError('ACCOUNT_DRAFT_SELECTION_CHANGED')
                return {'state':'NO_DRAFT_CONTENT','operation_id':operation_id,'canonical_bodies_removed':0,'projections_removed':0,'execution_authority':False}
            if record.get('state')=='ERASED':
                await self._erased(db,record,owner,operation_id)
                if record.get('body_digest')!=expected_digest:raise DraftError('ACCOUNT_DRAFT_SELECTION_CHANGED')
                return record['receipt']
            record=await self._validate(db,record,owner,operation_id)
            if record['body_digest']!=expected_digest:raise DraftError('ACCOUNT_DRAFT_SELECTION_CHANGED')
            body=record['body']
            try:current=await self._current(db,owner,body['request']['family_id'])
            except DraftError as error:
                if error.code!='ACCOUNT_DRAFT_HISTORY_UNKNOWN':raise
                current=None
            cursor=await db.execute('DELETE FROM owner_artifacts WHERE artifact_id=? AND canonical_source_type=?',(record['artifact_id'],SOURCE_TYPE))
            if cursor.rowcount!=1:raise DraftError('ACCOUNT_DRAFT_HISTORY_UNKNOWN',503)
            erase_revision=None
            if current is not None and current['draft_id']==body['draft_id']:
                erase_revision=current['revision']+1
                await _save(db,_key(FAMILY,owner,body['request']['family_id']),{'revision':current['revision']+1,'draft_id':None},self.clock())
            result={'state':'ERASED','operation_id':operation_id,'body_digest':expected_digest,
                'canonical_bodies_removed':1,'projections_removed':1,'execution_authority':False}
            # No request/selection/context body survives; opaque key+hash prevents replay resurrection.
            witness={'family_scope':_key(FAMILY,owner,body['request']['family_id']),
                'draft_id':body['draft_id'],'publication_revision':body['selection_revision'],'erase_revision':erase_revision}
            witness['witness_hash']=digest({'owner_id':owner,'operation_id':operation_id,'body_digest':expected_digest,'selection':dict(witness)})
            await _save(db,key,{'state':'ERASED','body_digest':expected_digest,'receipt':result,'selection_witness':witness},self.clock());await db.commit()
            return result

    async def finish(self,coroutine):
        if len(self.tasks)>=4:
            coroutine.close()
            raise DraftError('ACCOUNT_DRAFT_BUSY',503)
        task=asyncio.create_task(coroutine);self.tasks.add(task)
        def done(original):
            self.tasks.discard(original)
            if not original.cancelled():original.exception()
        task.add_done_callback(done)
        return await asyncio.shield(task)

    async def drain(self):
        if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)


def _distinct(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result


class PrivateDraftRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handle(request):
            try:
                if request.query_params:raise DraftError('ACCOUNT_DRAFT_INPUT_INVALID',422)
                if request.method in {'POST','DELETE'}:
                    raw=await request.body()
                    if len(raw)>MAX_BYTES:raise DraftError('ACCOUNT_DRAFT_BODY_CAPACITY',413)
                    json.loads(raw,object_pairs_hook=_distinct,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
                response=await original(request);response.headers.update(HEADERS);return response
            except (ValueError,RecursionError) as error:
                code=error.code if isinstance(error,DraftError) else 'ACCOUNT_DRAFT_INPUT_INVALID'
                status=error.status if isinstance(error,DraftError) else 422
                return JSONResponse(status_code=status,content={'detail':{'code':code,'field':error.field or 'input'} if isinstance(error,DraftError) else {'code':code,'field':'input'}},headers=HEADERS)
            except (sqlite3.Error,aiosqlite.Error,OSError):
                return JSONResponse(status_code=503,content={'detail':{'code':'ACCOUNT_DRAFT_HISTORY_UNKNOWN'}},headers=HEADERS)
            except RequestValidationError as error:
                location=error.errors()[0].get('loc',()) if error.errors() else ()
                field=location[-1] if location and location[-1] in {'operation_id','family_id','expected_revision','variant','broker_kind','expected_digest'} else 'input'
                return JSONResponse(status_code=422,content={'detail':{'code':'ACCOUNT_DRAFT_INPUT_INVALID','field':field}},headers=HEADERS)
        return handle


def build_account_application_draft_router(service):
    router=APIRouter(prefix='/v1/trading/accounts/application-drafts',route_class=PrivateDraftRoute,tags=['account-drafts'])
    def caller(request):
        device=getattr(request.state,'van_device_id',None)
        if not device:raise DraftError('ACCOUNT_DRAFT_OWNER_REQUIRED',403)
        return {'owner_id':'owner','device_id':device,'access_token_hash':hashlib.sha256(request.headers.get('X-Van-Device-Token','').encode()).hexdigest(),
            'proved':getattr(request.state,'van_device_proved',False)}
    @router.get('/selections/{family_id}',response_model=SelectionView)
    async def selection(request:Request,family_id:str):return await service.selection(family_id,caller(request))
    @router.post('',response_model=DraftReceipt)
    async def create(request:Request,body:DraftInput):
        received=service.clock();return await service.finish(service.create(body,caller(request),received))
    @router.get('/{operation_id}',response_model=DraftView|ErasedView|RefusedView)
    async def inspect(request:Request,operation_id:str):return await service.inspect(operation_id,caller(request))
    @router.delete('/{operation_id}',response_model=EraseResult,response_model_exclude_none=True)
    async def erase(request:Request,operation_id:str,body:EraseInput):return await service.finish(service.erase(operation_id,body.expected_digest,caller(request)))
    return router
