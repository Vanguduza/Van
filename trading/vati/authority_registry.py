"""Atomic public owner-key enrollment/revocation; no private keys or new grants."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from vati.core.file_lock import exclusive_state_lock

REVOCATION_SCHEMA='vati.owner-device-key-revocation/1'


def owner_registry_path(path=None):
    return Path(path if path is not None else (
        os.environ.get('VAN_OWNER_AUTHORITY_KEYS','')
        or Path(__file__).resolve().parents[2]/'registries'/'owner_authority_keys.json')).resolve()


def _public_der(pem):
    if not isinstance(pem,str):raise ValueError('owner authority public key must be text')
    return serialization.load_pem_public_key(pem.encode()).public_bytes(
        serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)


def _key_fingerprint(pem):
    try:
        key=serialization.load_pem_public_key(pem.encode())
        der=key.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        return 'device-'+hashlib.sha256(der).hexdigest()[:24]
    except (ValueError,TypeError,AttributeError,UnsupportedAlgorithm):
        # Unusable legacy key material cannot verify a signature. Preserve an
        # unrelated legacy entry rather than inventing its public-key identity.
        return None


def owner_key_id(pem):
    if not isinstance(pem,str):raise ValueError('owner authority public key must be text')
    key=serialization.load_pem_public_key(pem.encode())
    if not isinstance(key,ec.EllipticCurvePublicKey) or not isinstance(key.curve,ec.SECP256R1):
        raise ValueError('owner authority key must be EC P-256')
    der=key.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    return 'device-'+hashlib.sha256(der).hexdigest()[:24]


def revocation_record(device_id,key_id):
    if (not isinstance(device_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',device_id)
        or not isinstance(key_id,str) or not re.fullmatch(r'device-[0-9a-f]{24}',key_id)):
        raise ValueError('owner device/key revocation identity is invalid')
    operation_id=hashlib.sha256((REVOCATION_SCHEMA+'|'+device_id+'|'+key_id).encode()).hexdigest()
    return {'schema':REVOCATION_SCHEMA,'operation_id':operation_id,'device_id':device_id,'key_id':key_id}


def read_registry(path):
    path=Path(path)
    if not path.is_file():return {'keys':{},'revocations':{}}
    if os.name!='nt' and path.stat().st_mode & 0o022:
        raise ValueError('owner authority registry must not be writable by another group or user')
    raw=json.loads(path.read_text())
    if not isinstance(raw,dict):raise ValueError('owner authority registry must be an object')
    keys=raw.get('keys',raw);revocations=raw.get('revocations',{}) if 'keys' in raw else {}
    if (not isinstance(keys,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in keys.items())
        or not isinstance(revocations,dict)):
        raise ValueError('owner authority registry is unreadable')
    for identity,row in revocations.items():
        if not isinstance(row,dict) or row!=revocation_record(row.get('device_id'),row.get('key_id')) or identity!=row['operation_id']:
            raise ValueError('owner authority revocation history is invalid')
    return {'keys':{k:v for k,v in keys.items() if v.strip()},'revocations':revocations}


def active_keys(record):
    revoked={r['key_id'] for r in record['revocations'].values()}
    return {k:v for k,v in record['keys'].items()
        if k not in revoked and (not revoked or _key_fingerprint(v) not in revoked)}


def _write(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump({'version':2,**payload},stream,sort_keys=True,indent=2);stream.write('\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        if os.name!='nt':
            directory=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def enroll_owner_key(path,key_id,pem):
    path=Path(path).resolve()
    if owner_key_id(pem)!=key_id:raise ValueError('owner authority fingerprint differs')
    with exclusive_state_lock(path):
        record=read_registry(path)
        if any(row['key_id']==key_id for row in record['revocations'].values()):
            raise PermissionError('owner authority key is revoked; a stale enrollment cannot restore it')
        existing=active_keys(record)
        if any(k!=key_id and _public_der(v)!=_public_der(pem) for k,v in existing.items()):
            raise PermissionError('a different owner authority key is already enrolled; explicit owner-device rebind is required')
        if key_id in existing and _public_der(existing[key_id])!=_public_der(pem):
            raise PermissionError('owner authority key id collides with different key material')
        record['keys']={**existing,key_id:pem.strip()+'\n'}
        _write(path,record)


def revoke_owner_key(path,*,device_id,key_id,public_key_pem,operation_id):
    path=Path(path).resolve()
    if owner_key_id(public_key_pem)!=key_id:raise ValueError('owner authority fingerprint differs')
    revoked=revocation_record(device_id,key_id)
    if operation_id!=revoked['operation_id']:raise ValueError('owner revocation operation differs from its exact target')
    with exclusive_state_lock(path):
        record=read_registry(path)
        pem=record['keys'].get(key_id)
        if pem and _public_der(pem)!=_public_der(public_key_pem):raise PermissionError('owner authority fingerprint collision')
        record['keys']={k:v for k,v in record['keys'].items()
            if k!=key_id and _key_fingerprint(v)!=key_id}
        record['revocations'][operation_id]=revoked
        _write(path,record)
        current=read_registry(path)
        if key_id in active_keys(current) or current['revocations'].get(operation_id)!=revoked:
            raise OSError('native owner revocation readback differs')
        return {**revoked,'phase':'APPLIED','revoked':True,'key_active':False,
            'revocation_ref':hashlib.sha256(json.dumps(revoked,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'registry_ref':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
