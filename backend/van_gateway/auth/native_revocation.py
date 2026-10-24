"""Durable propagation of revoked paired-device public keys to native trading."""
import asyncio
import hashlib
import json
import logging
import re
import time
from cryptography.exceptions import UnsupportedAlgorithm

from van_gateway.trading.accounts import _trading_path
_trading_path()
from vati.authority_registry import owner_key_id, revocation_record

PREFIX='native_owner_revocation:'
SCHEMA='van.native-owner-revocation/1'
LOG=logging.getLogger(__name__)

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class NativeOwnerKeyRevocationReceipt(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version: Literal['vati.owner-device-key-revocation/1']=Field(alias='schema')
    operation_id: str=Field(pattern=r'^[0-9a-f]{64}$')
    device_id: str
    key_id: str=Field(pattern=r'^device-[0-9a-f]{24}$')
    phase: Literal['APPLIED']
    revoked: Literal[True]
    key_active: Literal[False]
    revocation_ref: str=Field(pattern=r'^[0-9a-f]{64}$')
    registry_ref: str=Field(pattern=r'^[0-9a-f]{64}$')


class NativeOwnerKeyRevocationState(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id: str=Field(pattern=r'^[0-9a-f]{64}$')
    device_id: str
    key_id: str | None
    phase: Literal['PENDING','APPLIED','UNKNOWN']
    native_result: NativeOwnerKeyRevocationReceipt | None

    @model_validator(mode='after')
    def truthful_phase(self):
        if (self.phase=='APPLIED') != (self.native_result is not None):
            raise ValueError('native revocation requires its actual acknowledgement')
        return self


class DeviceRevocationResponse(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revoked: Literal[True]
    device_id: str
    revoked_privileged_executions: int
    revoked_client_certificates: int
    native_authority_revocation: NativeOwnerKeyRevocationState


def pending_record(device_id,public_key_pem,requested_at_unix):
    if type(requested_at_unix) is not int or requested_at_unix<0:raise ValueError('invalid owner revocation time')
    pem=public_key_pem if isinstance(public_key_pem,str) else ''
    try:
        key_id=owner_key_id(pem)
        identity=revocation_record(device_id,key_id)['operation_id']
    except (ValueError,TypeError,UnsupportedAlgorithm):
        # Legacy devices with unusable public-key metadata are still revoked
        # locally. Never pretend their native history was inspected or cleared.
        key_id=None
        identity=hashlib.sha256((SCHEMA+'|'+device_id+'|'+pem).encode()).hexdigest()
    return {'schema':SCHEMA,'operation_id':identity,'device_id':device_id,'key_id':key_id,
        'public_key_pem':pem,'requested_at_unix':requested_at_unix,'phase':'PENDING','native_result':None}


def public(record):
    return {k:record[k] for k in ('operation_id','device_id','key_id','phase','native_result')}


class NativeOwnerRevocations:
    def __init__(self,*,store,promotions):
        self.store,self.promotions=store,promotions
        self._lock=asyncio.Lock()

    @staticmethod
    def _matches_native(record,result):
        if record['key_id'] is None:return False
        proof=revocation_record(record['device_id'],record['key_id'])
        reference=hashlib.sha256(json.dumps(proof,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return (isinstance(result,dict) and set(result)==set(proof)|{
            'phase','revoked','key_active','revocation_ref','registry_ref'}
            and all(result.get(k)==v for k,v in proof.items())
            and result.get('phase')=='APPLIED' and result.get('revoked') is True
            and result.get('key_active') is False and result.get('revocation_ref')==reference
            and isinstance(result.get('registry_ref'),str)
            and re.fullmatch('[0-9a-f]{64}',result['registry_ref']) is not None)

    async def original(self,operation_id):
        if not isinstance(operation_id,str) or not re.fullmatch('[0-9a-f]{64}',operation_id):
            raise ValueError('invalid native owner revocation identity')
        row=await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(PREFIX+operation_id,))
        if row is None:raise ValueError('original owner revocation is unavailable')
        record=json.loads(row['value'])
        expected=pending_record(record['device_id'],record['public_key_pem'],record['requested_at_unix'])
        if (set(record)!=set(expected) or any(record[k]!=expected[k] for k in expected if k not in {'phase','native_result'})
            or record['operation_id']!=operation_id or record['phase'] not in {'PENDING','APPLIED'}):
            raise ValueError('original owner revocation is unreadable')
        if record['phase']=='APPLIED':
            if not self._matches_native(record,record['native_result']):raise ValueError('native revocation receipt is unreadable')
            return public(record)
        if record['native_result'] is not None:raise ValueError('pending revocation cannot assert a native result')
        return public(record)

    async def reconcile_operation(self,operation_id):
        # Validate cached outcomes through the same read-only original reader.
        status=await self.original(operation_id)
        if status['phase']=='APPLIED':return status
        row=await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(PREFIX+operation_id,))
        if row is None:raise ValueError('original owner revocation is unavailable')
        record=json.loads(row['value'])
        device=await self.store.fetchone('SELECT public_key_pem,revoked_at_unix FROM devices WHERE device_id=?',
            (record['device_id'],))
        if (device is None or device['revoked_at_unix'] is None
            or (device['public_key_pem'] or '')!=record['public_key_pem'] or record['key_id'] is None):
            return public(record)
        target={k:record[k] for k in ('device_id','key_id','public_key_pem','operation_id')}
        if self.promotions.control is None:return public(record)
        try:
            result=await asyncio.to_thread(self.promotions.control.run,'owner_authority_revoke',target)
            if not self._matches_native(record,result):return public(record)
            record['phase']='APPLIED';record['native_result']=result
            await self.store.execute('UPDATE runtime_meta SET value=?,updated_at_unix_ms=? WHERE key=?',
                (json.dumps(record,sort_keys=True,separators=(',',':')),int(time.time()*1000),PREFIX+operation_id))
        except Exception:
            # The local device remains revoked. Native acknowledgement loss is
            # reconciled with the same exact operation. A known valid native
            # acknowledgement stays APPLIED even if its local marker write fails.
            LOG.warning('native owner-key revocation remains pending')
        return public(record)

    async def reconcile_once(self,*,limit=50):
        if type(limit) is not int or not 1<=limit<=200:raise ValueError('native revocation batch must be bounded')
        async with self._lock:
            cursor_key='native_owner_revocation_cursor_v1'
            cursor=await self.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(cursor_key,))
            after=cursor['value'] if cursor else ''
            query='''SELECT key FROM runtime_meta WHERE key GLOB ?
                AND CASE WHEN json_valid(value) THEN json_extract(value,'$.phase')='PENDING' ELSE 0 END
                AND key > ? ORDER BY key LIMIT ?'''
            rows=await self.store.fetchall(query,(PREFIX+'*',after,limit))
            if not rows and after:rows=await self.store.fetchall(query,(PREFIX+'*','',limit))
            report={'examined':len(rows),'applied':0,'pending':0}
            for row in rows:
                try:
                    result=await self.reconcile_operation(row['key'][len(PREFIX):])
                    report['applied' if result['phase']=='APPLIED' else 'pending']+=1
                except Exception:
                    report['pending']+=1
                await self.store.execute('INSERT OR REPLACE INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                    (cursor_key,row['key'],int(time.time()*1000)))
            return report

    async def run(self):
        while True:
            try:await self.reconcile_once()
            except Exception:LOG.warning('native owner-key revocation dispatcher unavailable')
            await asyncio.sleep(5)
