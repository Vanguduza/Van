"""Native public-key tombstones survive retry, competing writers and stale caches."""
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vati.authority_registry import (owner_key_id,revocation_record,enroll_owner_key,
    revoke_owner_key,read_registry,active_keys)
from vati.authority import OwnerAuthorityVerifier,OwnerAuthorityError,sign_token,load_owner_keys


def owner():
    key=ec.generate_private_key(ec.SECP256R1())
    pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return key,pem,owner_key_id(pem)


def revoke(path,pem,kid,device='owner-s24'):
    record=revocation_record(device,kid)
    return revoke_owner_key(path,device_id=device,key_id=kid,public_key_pem=pem,operation_id=record['operation_id'])


def test_native_revocation_is_idempotent_and_preserves_unrelated_owner_keys(tmp_path):
    _,pem,kid=owner();_,other,other_id=owner();path=tmp_path/'keys.json'
    path.write_text(json.dumps({'keys':{kid:pem,other_id:other}}))
    first=revoke(path,pem,kid)
    assert first['key_active'] is False and first['revoked'] is True
    assert load_owner_keys(path)=={other_id:other}
    assert revoke(path,pem,kid)==first
    assert revoke(path,pem,kid,'another-device')['key_active'] is False
    assert len(read_registry(path)['revocations'])==2
    for device in ('owner-s24','another-device'):
        with pytest.raises(PermissionError,match='revoked'):enroll_owner_key(path,kid,pem)
    assert load_owner_keys(path)=={other_id:other}


def test_enrollment_and_revocation_cannot_resurrect_a_key_between_independent_writers(tmp_path):
    _,pem,kid=owner();path=tmp_path/'keys.json';enroll_owner_key(path,kid,pem)
    barrier=Barrier(2)
    def enroll():
        barrier.wait(timeout=5)
        try:enroll_owner_key(path,kid,pem)
        except PermissionError:return 'REFUSED'
        return 'ENROLLED_BEFORE_REVOCATION'
    def remove():
        barrier.wait(timeout=5)
        return revoke(path,pem,kid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one=pool.submit(enroll);two=pool.submit(remove)
        assert two.result(timeout=10)['phase']=='APPLIED'
        assert one.result(timeout=10) in {'REFUSED','ENROLLED_BEFORE_REVOCATION'}
    assert load_owner_keys(path)=={}
    with pytest.raises(PermissionError):enroll_owner_key(path,kid,pem)


def test_native_verifier_reloads_current_keys_without_resetting_one_time_consumption(tmp_path):
    key,pem,kid=owner();path=tmp_path/'keys.json';enroll_owner_key(path,kid,pem)
    verifier=OwnerAuthorityVerifier(load_owner_keys(path),registry_path=path)
    token=sign_token(key,act='owner-halt',subject='s24-native',key_id=kid)
    verifier.verify(token,act='owner-halt',subject='s24-native')
    with pytest.raises(OwnerAuthorityError,match='already used'):verifier.verify(token,act='owner-halt',subject='s24-native')
    revoke(path,pem,kid)
    with pytest.raises(OwnerAuthorityError,match='not registered'):
        verifier.verify(token,act='owner-halt',subject='s24-native',single_use=False)
    assert len(verifier.consumed)==1


@pytest.mark.parametrize('defect',['identity','target','operation','unknown_field'])
def test_unreadable_revocation_history_never_silently_becomes_a_fresh_registry(tmp_path,defect):
    _,pem,kid=owner();path=tmp_path/'keys.json';enroll_owner_key(path,kid,pem);revoke(path,pem,kid)
    raw=json.loads(path.read_text());rid=next(iter(raw['revocations']));row=raw['revocations'][rid]
    if defect=='identity':row['device_id']='a-different-owner'
    elif defect=='target':row['key_id']='device-'+'f'*24
    elif defect=='operation':row['operation_id']='f'*64
    else:row['ignored']='unexpected'
    path.write_text(json.dumps(raw));before=path.read_bytes()
    with pytest.raises(ValueError):load_owner_keys(path)
    with pytest.raises(ValueError):enroll_owner_key(path,kid,pem)
    assert path.read_bytes()==before


def test_group_writable_key_registry_is_not_authority(tmp_path):
    _,pem,kid=owner();path=tmp_path/'keys.json';enroll_owner_key(path,kid,pem)
    path.chmod(0o666)
    with pytest.raises(ValueError,match='writable'):load_owner_keys(path)


def test_key_file_aliases_share_one_serialized_revocation_target(tmp_path):
    _,pem,kid=owner();path=tmp_path/'native.json';alias=tmp_path/'configured-alias.json'
    enroll_owner_key(path,kid,pem);alias.symlink_to(path)
    revoke(alias,pem,kid)
    assert alias.is_symlink()
    assert load_owner_keys(path)==load_owner_keys(alias)=={}
    with pytest.raises(PermissionError):enroll_owner_key(path,kid,pem)


def test_an_enrollment_read_cannot_overwrite_a_concurrent_native_tombstone(tmp_path,monkeypatch):
    import threading
    import vati.authority_registry as registry
    _,pem,kid=owner();path=tmp_path/'keys.json';enroll_owner_key(path,kid,pem)
    first_read=threading.Event();revoked=threading.Event();read=registry.read_registry
    def observed(p):
        value=read(p)
        if threading.current_thread().name.startswith('native-enroll') and not first_read.is_set():
            first_read.set();revoked.wait(0.3)
        return value
    monkeypatch.setattr(registry,'read_registry',observed)
    def enroll():
        try:enroll_owner_key(path,kid,pem)
        except PermissionError:pass
    def remove():
        try:return revoke(path,pem,kid)
        finally:revoked.set()
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='native-enroll') as one:
        first=one.submit(enroll);assert first_read.wait(2)
        with ThreadPoolExecutor(max_workers=1,thread_name_prefix='native-revoke') as two:
            second=two.submit(remove)
            assert second.result(timeout=5)['phase']=='APPLIED'
        first.result(timeout=5)
    assert load_owner_keys(path)=={}
    assert len(read_registry(path)['revocations'])==1


def test_two_separate_python_processes_cannot_resurrect_a_revoked_key(tmp_path):
    import os
    import subprocess
    import sys
    _,pem,kid=owner();path=tmp_path/'process-keys.json';pemfile=tmp_path/'owner-public.pem'
    pemfile.write_text(pem);enroll_owner_key(path,kid,pem)
    code='''
import sys,time
from pathlib import Path
from vati.authority_registry import enroll_owner_key,revoke_owner_key,revocation_record
path,pemfile,kid,role,barrier=sys.argv[1:]
pem=Path(pemfile).read_text();barrier=Path(barrier)
(barrier/(role+'.ready')).touch()
other='revoke' if role=='enroll' else 'enroll'
end=time.monotonic()+8
while not (barrier/(other+'.ready')).exists():
 if time.monotonic()>end:raise TimeoutError('independent process barrier')
 time.sleep(.01)
if role=='enroll':
 try:enroll_owner_key(path,kid,pem)
 except PermissionError:pass
else:
 record=revocation_record('owner-s24',kid)
 revoke_owner_key(path,device_id='owner-s24',key_id=kid,public_key_pem=pem,operation_id=record['operation_id'])
'''
    processes=[]
    try:
        for role in ('enroll','revoke'):
            processes.append(subprocess.Popen([sys.executable,'-c',code,str(path),str(pemfile),kid,role,str(tmp_path)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ)))
        for process in processes:
            out,error=process.communicate(timeout=15)
            assert process.returncode==0,(out,error)
    finally:
        for process in processes:
            if process.poll() is None:process.kill();process.wait(timeout=5)
    assert load_owner_keys(path)=={}
    assert len(read_registry(path)['revocations'])==1


def test_revoke_the_public_key_under_every_registered_alias_without_touching_another_key(tmp_path):
    key,pem,kid=owner();_,other,other_id=owner();path=tmp_path/'aliases.json'
    path.write_text(json.dumps({'keys':{kid:pem,'owner-policy-alias':pem,other_id:other}}))
    verifier=OwnerAuthorityVerifier(load_owner_keys(path),registry_path=path)
    token=sign_token(key,act='owner-halt',subject='alias-native-test',key_id='owner-policy-alias')
    assert verifier.verify(token,act='owner-halt',subject='alias-native-test',single_use=False)
    revoke(path,pem,kid)
    assert load_owner_keys(path)=={other_id:other}
    with pytest.raises(OwnerAuthorityError):
        verifier.verify(token,act='owner-halt',subject='alias-native-test',single_use=False)
    # A later file restore must not bypass a durable tombstone by changing a key label.
    raw=json.loads(path.read_text());raw['keys']['different-restored-label']=pem
    path.write_text(json.dumps(raw))
    assert load_owner_keys(path)=={other_id:other}


def test_enrolling_the_same_public_key_preserves_existing_policy_aliases(tmp_path):
    key,pem,kid=owner();path=tmp_path/'aliases.json'
    path.write_text(json.dumps({'keys':{'owner-policy-alias':pem}}))
    enroll_owner_key(path,kid,pem)
    assert load_owner_keys(path)=={'owner-policy-alias':pem,kid:pem.strip()+'\n'}
    verifier=OwnerAuthorityVerifier(load_owner_keys(path),registry_path=path)
    token=sign_token(key,act='owner-halt',subject='alias-native-test',key_id='owner-policy-alias')
    assert verifier.verify(token,act='owner-halt',subject='alias-native-test')


def test_the_same_key_with_different_pem_line_endings_is_not_a_replacement(tmp_path):
    _,pem,kid=owner();path=tmp_path/'line-endings.json'
    path.write_text(json.dumps({'keys':{kid:pem.replace('\n','\r\n')}}))
    enroll_owner_key(path,kid,pem)
    assert owner_key_id(load_owner_keys(path)[kid])==kid
