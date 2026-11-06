"""Native persisted generations, exact account scope and real kernel lock behavior."""
from dataclasses import replace
import json
import multiprocessing
import subprocess
import sys

import pytest

from vati.accounts import Account,AccountRegistry,AccountRegistryError
from vati.accounts.resource_version import resource_snapshot
from vati.core.file_lock import exclusive_state_lock


def paper(alias='paper_lab',label='Original'):
    return Account(alias=alias,broker='PAPER',mode='DEMO_TRADER',currency='USD',label=label)


def version(path,alias='paper_lab'):
    return resource_snapshot(AccountRegistry(path),alias)['resource_version']


def test_native_version_is_stable_across_cold_readers(tmp_path):
    path=tmp_path/'accounts.json';r=AccountRegistry(path);r.add(paper())
    before=path.read_bytes();v=version(path)
    assert version(path)==v and path.read_bytes()==before


def test_disjoint_account_mutation_does_not_invalidate_this_accounts_approval(tmp_path):
    path=tmp_path/'accounts.json';r=AccountRegistry(path);r.add(paper())
    original=version(path);r.add(paper('other_account'))
    assert version(path)==original


def test_reverted_metadata_still_invalidates_an_older_native_generation(tmp_path):
    path=tmp_path/'accounts.json';r=AccountRegistry(path);r.add(paper());stale=AccountRegistry(path)
    original=version(path);r.replace(paper(label='Temporary'));r.replace(paper())
    assert version(path)!=original
    with pytest.raises(AccountRegistryError,match='changed since read'):
        stale.replace(paper(label='Old approved update'))
    assert AccountRegistry(path).get('paper_lab').label=='Original'


def test_absent_alias_generation_survives_registration_and_removal(tmp_path):
    path=tmp_path/'accounts.json';before=version(path)
    r=AccountRegistry(path);r.add(paper());r.remove('paper_lab')
    assert resource_snapshot(AccountRegistry(path),'paper_lab')['state']=='ABSENT'
    assert version(path)!=before
    r.add(paper());registered=version(path);r.remove('paper_lab');r.add(paper())
    assert version(path)!=registered


def test_a_native_touch_invalidates_stale_whole_registry_saves(tmp_path):
    path=tmp_path/'accounts.json';r=AccountRegistry(path);r.add(paper());stale=AccountRegistry(path)
    before=version(path);r.touch('paper_lab')
    assert version(path)!=before
    with pytest.raises(AccountRegistryError,match='changed since read'):
        stale.save()


def test_failed_native_swap_keeps_the_previous_generation_and_cache(tmp_path,monkeypatch):
    path=tmp_path/'accounts.json';r=AccountRegistry(path);r.add(paper())
    original=version(path);before=path.read_bytes()
    def fail(*args):raise OSError('induced swap failure')
    with monkeypatch.context() as m:
        m.setattr('vati.accounts.registry.os.replace',fail)
        with pytest.raises(OSError,match='swap failure'):r.replace(paper(label='Lost'))
    assert path.read_bytes()==before and version(path)==original
    assert r.get('paper_lab').label=='Original'
    r.replace(paper(label='Saved'))
    assert version(path)!=original


@pytest.mark.parametrize('epoch',[True,0,-1,'2',2**63])
def test_invalid_native_generations_are_not_overwritten_from_a_stale_cache(tmp_path,epoch):
    path=tmp_path/'accounts.json';r=AccountRegistry(path);r.add(paper())
    data=json.loads(path.read_text());data['resource_revisions']['paper_lab']=epoch
    path.write_text(json.dumps(data));before=path.read_bytes()
    with pytest.raises(AccountRegistryError):r.replace(paper(label='Overwrite'))
    assert path.read_bytes()==before


def test_exhausted_native_generation_refuses_without_wrapping_or_writing(tmp_path):
    path=tmp_path/'accounts.json';r=AccountRegistry(path);r.add(paper())
    data=json.loads(path.read_text());data['resource_revisions']['paper_lab']=2**63-1
    path.write_text(json.dumps(data));before=path.read_bytes();r=AccountRegistry(path)
    with pytest.raises(AccountRegistryError,match='exhausted'):r.touch('paper_lab')
    assert path.read_bytes()==before


def test_nested_native_lock_completes_without_a_second_kernel_acquisition(tmp_path):
    script="from vati.core.file_lock import exclusive_state_lock as lock\nimport sys\nwith lock(sys.argv[1]):\n with lock(sys.argv[1]):\n  print('nested-completed')\n"
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path/'state')],capture_output=True,text=True,timeout=4)
    assert result.returncode==0 and result.stdout.strip()=='nested-completed'


def lock_worker(path,attempting,acquired):
    attempting.set()
    with exclusive_state_lock(path):acquired.set()


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(),reason='actual fork inheritance requires fork')
def test_a_forked_child_cannot_inherit_the_parents_reentrant_permission(tmp_path):
    ctx=multiprocessing.get_context('fork');attempting=ctx.Event();acquired=ctx.Event()
    child=ctx.Process(target=lock_worker,args=(str(tmp_path/'state'),attempting,acquired))
    try:
        with exclusive_state_lock(tmp_path/'state'):
            with exclusive_state_lock(tmp_path/'state'):
                child.start();assert attempting.wait(3)
            assert not acquired.wait(0.15),'child bypassed the parent kernel lock'
        assert acquired.wait(3)
        child.join(3);assert child.exitcode==0
    finally:
        if child.pid is not None and child.is_alive():child.kill();child.join(3)


def test_native_version_never_reads_or_hashes_credential_values(tmp_path,monkeypatch):
    from pathlib import Path
    from vati.accounts import CredentialRef
    secret=tmp_path/'private.env';secret.write_text('DERIV_API_TOKEN=fixture-private-material\n');secret.chmod(0o600)
    path=tmp_path/'accounts.json';registry=AccountRegistry(path)
    registry.add(Account(alias='deriv_demo',broker='DERIV',mode='DEMO_TRADER',currency='USD',
        login='VRTC900',credential_ref=CredentialRef(secrets_file=str(secret))))
    original=Path.read_text
    def forbidden_values(self,*args,**kwargs):
        if self==secret:raise AssertionError('native version read credential values')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',forbidden_values)
    snapshot=resource_snapshot(AccountRegistry(path),'deriv_demo')
    assert len(snapshot['resource_version'])==64
    assert 'fixture-private-material' not in json.dumps(snapshot)
