"""Device-signed, operation-bound recovery intent; no bearer trading grant.

The canonical statement matches the existing gateway A4 approval challenge.
Public signatures can prove only this original operation and exact target state.
The native journal, not possession of a signature, determines replay outcomes.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vati.risk.contracts import KillSwitchTrigger
from vati.risk.lockouts import ACCOUNT_SCOPE

ACTIONS=frozenset({'clear_kill_switch','reset_loss_streak','resume_drawdown'})
SCHEMA='vati.runtime-recovery/1'
ALGORITHM='ECDSA_P256_SHA256'
MAX_APPROVAL_SECONDS=120
MAX_REQUEST_AGE_SECONDS=300


class RuntimeControlError(ValueError):
    pass


@dataclass(frozen=True)
class RecoveryIntent:
    device_id: str
    account_alias: str
    session_id: str
    action: str
    state_ref: str
    issued_at_unix: int
    arguments: tuple[tuple[str,str],...]=()

    @classmethod
    def from_mapping(cls,value):
        if not isinstance(value,dict) or set(value)!={'schema','device_id','account_alias','session_id','action','state_ref','issued_at_unix','args'}:
            raise RuntimeControlError('runtime recovery intent shape is invalid')
        if value['schema']!=SCHEMA or not isinstance(value['args'],dict):
            raise RuntimeControlError('runtime recovery intent schema is invalid')
        for name in ('device_id','account_alias','session_id','action','state_ref'):
            if not isinstance(value[name],str):raise RuntimeControlError('runtime recovery identity must be text')
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value['device_id']):raise RuntimeControlError('owner device identity is invalid')
        if not re.fullmatch(r'[a-z0-9_]{3,32}',value['account_alias']):raise RuntimeControlError('native account alias is invalid')
        if not value['session_id'] or len(value['session_id'])>384 or any(c in value['session_id'] for c in '|\r\n'):
            raise RuntimeControlError('native session identity is invalid')
        if not re.fullmatch(r'[0-9a-f]{64}',value['state_ref']):raise RuntimeControlError('native recovery state reference is invalid')
        if value['action'] not in ACTIONS:raise RuntimeControlError('runtime recovery action is unsupported')
        if type(value['issued_at_unix']) is not int or value['issued_at_unix']<0:raise RuntimeControlError('runtime recovery issue time is invalid')
        args=value['args'];action=value['action']
        expected={'trigger'} if action=='clear_kill_switch' else ({'scope'} if action=='reset_loss_streak' else set())
        if set(args)!=expected or any(not isinstance(v,str) for v in args.values()):
            raise RuntimeControlError('runtime recovery arguments do not match the action')
        if action=='clear_kill_switch' and args['trigger'] not in {x.value for x in KillSwitchTrigger}:
            raise RuntimeControlError('runtime kill trigger is invalid')
        if action=='reset_loss_streak' and args['scope']!=ACCOUNT_SCOPE and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',args['scope']):
            raise RuntimeControlError('runtime loss scope is invalid')
        return cls(**{k:value[k] for k in ('device_id','account_alias','session_id','action','state_ref','issued_at_unix')},arguments=tuple(sorted(args.items())))

    def body(self):
        return {'schema':SCHEMA,'device_id':self.device_id,'account_alias':self.account_alias,'session_id':self.session_id,
            'action':self.action,'state_ref':self.state_ref,'issued_at_unix':self.issued_at_unix,'args':dict(self.arguments)}

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(self.body(),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

    @property
    def action_id(self):return 'trading.runtime.'+self.action

    @property
    def approval_text(self):return 'trading-runtime-control|'+self.digest

    @property
    def intent_digest(self):
        return hashlib.sha256('|'.join(['van-a4-intent-v1',self.device_id,self.action_id,'',self.approval_text]).encode()).hexdigest()


def approval_statement(intent,operation_id,expires_at_unix):
    if not isinstance(operation_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',operation_id):
        raise RuntimeControlError('runtime original operation identity is invalid')
    if type(expires_at_unix) is not int:raise RuntimeControlError('runtime approval expiry is invalid')
    return '|'.join(['van-a4-approval-v2',operation_id,intent.device_id,'runtime:'+intent.action,
        '',intent.action_id,intent.intent_digest,str(expires_at_unix)])


@dataclass(frozen=True)
class RecoveryProof:
    operation_id: str
    expires_at_unix: int
    key_id: str
    signature_b64: str
    algorithm: str=ALGORITHM

    @classmethod
    def from_mapping(cls,value):
        if not isinstance(value,dict) or set(value)!={'operation_id','expires_at_unix','key_id','signature_b64','algorithm'}:
            raise RuntimeControlError('runtime approval proof shape is invalid')
        proof=cls(**value)
        if (not isinstance(proof.operation_id,str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',proof.operation_id)):
            raise RuntimeControlError('runtime original operation identity is invalid')
        if type(proof.expires_at_unix) is not int or proof.expires_at_unix<0:
            raise RuntimeControlError('runtime approval expiry is invalid')
        if (not isinstance(proof.key_id,str) or not proof.key_id or len(proof.key_id)>128
            or not isinstance(proof.signature_b64,str) or not 1<=len(proof.signature_b64)<=1024
            or proof.algorithm!=ALGORITHM):raise RuntimeControlError('runtime approval proof fields are invalid')
        return proof

    def public_record(self):
        return {'operation_id':self.operation_id,'expires_at_unix':self.expires_at_unix,'key_id':self.key_id,
                'signature_b64':self.signature_b64,'algorithm':self.algorithm}

    def verify(self,intent: RecoveryIntent,keys: Mapping[str,str],*,now_unix:int):
        # Revalidate dataclass construction too; callers cannot bypass the shape
        # gate by instantiating a mutable or differently typed field directly.
        if RecoveryIntent.from_mapping(intent.body()) != intent:
            raise RuntimeControlError('runtime recovery arguments are not canonical')
        RecoveryProof.from_mapping(self.public_record())
        statement=approval_statement(intent,self.operation_id,self.expires_at_unix)
        if type(now_unix) is not int or now_unix<0:raise RuntimeControlError('native approval clock is invalid')
        if not intent.issued_at_unix-60<=now_unix<intent.issued_at_unix+MAX_REQUEST_AGE_SECONDS:
            raise RuntimeControlError('runtime request time is stale or not yet valid')
        if not now_unix<self.expires_at_unix<=now_unix+MAX_APPROVAL_SECONDS:
            raise RuntimeControlError('runtime owner approval expired or exceeds its native lifetime')
        pem=keys.get(self.key_id)
        if not isinstance(pem,str) or not pem:raise RuntimeControlError('runtime owner key is not currently registered')
        try:
            key=serialization.load_pem_public_key(pem.encode())
            if not isinstance(key,ec.EllipticCurvePublicKey) or not isinstance(key.curve,ec.SECP256R1):
                raise ValueError('owner key must be P256')
            signature=base64.b64decode(self.signature_b64,validate=True)
            key.verify(signature,statement.encode(),ec.ECDSA(hashes.SHA256()))
        except (ValueError,TypeError,InvalidSignature) as exc:
            raise RuntimeControlError('runtime owner signature is invalid') from exc
        return 'owner-runtime-control:'+hashlib.sha256(statement.encode()+b'\n'+signature).hexdigest()
