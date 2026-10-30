"""Actual production factory, cached adapter, real registry writer and order path."""
from dataclasses import replace
from decimal import Decimal

import pytest

from vati.accounts import Account,AccountRegistry
from vati.app.service import build_adapter
from test_account_lifecycle import _command


def factory(tmp_path):
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='paper_lab',broker='PAPER',mode='DEMO_TRADER',currency='USD'))
    adapter=build_adapter(account,registry)
    command=replace(_command('registry-bound'),account_alias='paper_lab',venue='paper',command_hash='').sealed()
    return adapter,registry,command


@pytest.mark.parametrize('change',[{'enabled':False},{'mode':'OBSERVE'},{'mode':'ADVISOR'},
    {'mode':'SHADOW_TRADER'},{'demo':False},{'currency':'EUR'}])
def test_cached_adapter_cannot_ignore_a_changed_owner_entry_boundary(tmp_path,change):
    adapter,registry,command=factory(tmp_path)
    writer=AccountRegistry(registry.path);writer.replace(replace(writer.get('paper_lab'),**change))
    receipt=adapter.submit(command,now_ms=1000)
    assert receipt.status=='REJECTED' and receipt.filled_qty==0
    assert adapter.positions()==[]


def test_unlinked_cached_adapter_cannot_open_a_new_position(tmp_path):
    adapter,registry,command=factory(tmp_path)
    AccountRegistry(registry.path).remove('paper_lab')
    assert adapter.submit(command,now_ms=1000).status=='REJECTED'
    assert adapter.positions()==[]


def test_a_rejected_cached_entry_does_not_disable_protection_or_mutate_equity(tmp_path):
    adapter,registry,command=factory(tmp_path)
    filled=adapter.submit(command,now_ms=1000);before=adapter.sync_account()
    writer=AccountRegistry(registry.path);writer.replace(replace(writer.get('paper_lab'),enabled=False))
    assert adapter.submit(replace(command,trade_intent_id='blocked-second'),now_ms=2000).status=='REJECTED'
    assert adapter.sync_account()==before
    assert len(adapter.positions())==1
    adapter.close(filled.broker_position_id,None,now_ms=3000,reason='owner-protective-close')
    assert adapter.positions()==[]


def test_valid_registry_entry_and_local_label_updates_remain_available(tmp_path):
    from vati.execution.paper import PaperAdapter
    adapter,registry,command=factory(tmp_path)
    writer=AccountRegistry(registry.path);writer.replace(replace(writer.get('paper_lab'),label='Owner label'))
    assert type(adapter) is PaperAdapter
    assert adapter.submit(command,now_ms=1000).status=='FILLED'


@pytest.mark.parametrize('field,value',[('account_alias','wrong_alias'),('venue','deriv')])
def test_factory_binding_checks_the_native_command_scope(tmp_path,field,value):
    adapter,_,command=factory(tmp_path)
    assert adapter.submit(replace(command,**{field:value}),now_ms=1000).status=='REJECTED'
    assert adapter.positions()==[]


def test_a_replaced_mandate_reference_fences_the_cached_runtime(tmp_path):
    adapter,registry,command=factory(tmp_path)
    writer=AccountRegistry(registry.path);writer.replace(replace(writer.get('paper_lab'),mandate_ref='new-owner-authority'))
    assert adapter.submit(command,now_ms=1000).status=='REJECTED'
    assert adapter.positions()==[]


def test_unreadable_registry_never_uses_the_last_successful_entry_setting(tmp_path):
    adapter,registry,command=factory(tmp_path)
    registry.path.write_text('{broken')
    assert adapter.submit(command,now_ms=1000).status=='REJECTED'
    assert adapter.positions()==[]


def test_provider_failure_after_delegation_is_not_reclassified_as_a_presend_refusal(tmp_path,monkeypatch):
    from vati.accounts import AccountRegistryError
    from vati.execution.paper import PaperAdapter
    calls=[]
    def uncertain(self,command,*,now_ms):
        calls.append(command);raise AccountRegistryError('induced after delegated effect')
    monkeypatch.setattr(PaperAdapter,'submit',uncertain)
    adapter,_,command=factory(tmp_path)
    with pytest.raises(AccountRegistryError,match='after delegated effect'):
        adapter.submit(command,now_ms=1000)
    assert calls==[command]


def test_real_registry_mutation_waits_until_the_delegated_effect_finishes(tmp_path,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from vati.execution.paper import PaperAdapter
    entered=threading.Event();release=threading.Event();started=threading.Event();finished=threading.Event()
    original=PaperAdapter.submit
    def paused(self,command,*,now_ms):
        entered.set();assert release.wait(5)
        return original(self,command,now_ms=now_ms)
    monkeypatch.setattr(PaperAdapter,'submit',paused)
    adapter,registry,command=factory(tmp_path)
    def disable():
        current=AccountRegistry(registry.path);started.set()
        try:current.replace(replace(current.get('paper_lab'),enabled=False))
        finally:finished.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        effect=pool.submit(adapter.submit,command,now_ms=1000)
        assert entered.wait(5)
        mutation=pool.submit(disable);assert started.wait(5)
        try:assert not finished.wait(0.15),'registry mutation overtook delegated entry'
        finally:release.set()
        assert effect.result(5).status=='FILLED';mutation.result(5)
    assert adapter.submit(command,now_ms=1001).status=='REJECTED'
