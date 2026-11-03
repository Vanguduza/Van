"""Prospective native unlink evidence; SOURCE temp filesystem, no provider effect."""
import json
from contextlib import closing
import sqlite3

import pytest
from backend.tests.test_account_unlink_review import client,_env,isolate,paper,challenge
from vati.core import Ledger,EventKind
from commander.account_effects import AccountEffectJournal,AccountEffectUnknown
from commander.account_cleanup import UnlinkRecoveryBook


@pytest.mark.asyncio
async def test_prospective_plan_and_registry_step_commit_without_business_count_change(client,tmp_path):
    ac,app=client;await paper(ac)
    body,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    operation=body['approval_proof']['challenge_id']
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:before=ledger.count(EventKind.ACCOUNT_OPERATION)
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert result.status_code==200,result.text
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        book=UnlinkRecoveryBook(ledger,secrets_root=tmp_path/'secrets');history=book._history(operation)
        assert ledger.count(EventKind.ACCOUNT_OPERATION)==before+2
        assert len(AccountEffectJournal(ledger).business_events())==before-1+2
        assert history['plan'] is not None and history['epoch']==1
        assert history['steps']['REGISTRY_REMOVE'].payload['data']['state']=='DONE'
        assert history['plan'].payload['data']['steps']==['REGISTRY_REMOVE']
        assert book.summary(operation,'test-device')['execution_authority'] is False
        assert not any('unlink-recovery' in e.correlation_id for e in ledger.iter())
    with closing(Ledger(tmp_path/'vati.sqlite')) as restarted:
        assert UnlinkRecoveryBook(restarted,secrets_root=tmp_path/'secrets')._history(operation)['plan'].hash==history['plan'].hash


def test_same_database_technical_schema_no_business_rows_and_borrowed_writer_refused(tmp_path):
    path=tmp_path/'native.sqlite'
    with closing(Ledger(path)) as ledger:
        before=ledger.count();book=UnlinkRecoveryBook(ledger,secrets_root=tmp_path/'secrets')
        assert ledger.count()==before
        assert book.summary('legacy_original_operation_0001','old-device')['state']=='LEGACY_UNBOUND_HOLD'
        with ledger.atomic():
            with pytest.raises(Exception,match='committed_source_read_requires_idle'):
                with book.atomic('new_cleanup_operation_0001'):pass
        assert ledger.count()==before


def test_partial_foreign_technical_schema_refuses_without_repairing_it(tmp_path):
    path=tmp_path/'native.sqlite'
    with closing(Ledger(path)) as ledger:
        ledger._conn.execute('CREATE TABLE account_unlink_schema(version INTEGER,contract TEXT)')
        ledger._conn.execute('INSERT INTO account_unlink_schema VALUES(1,?)',('foreign/1',));ledger._conn.commit()
        with pytest.raises(AccountEffectUnknown):UnlinkRecoveryBook(ledger,secrets_root=tmp_path/'secrets')
        assert ledger._conn.execute('SELECT contract FROM account_unlink_schema').fetchone()[0]=='foreign/1'
        assert ledger.count()==0


@pytest.mark.asyncio
async def test_private_may_begin_is_independently_committed_before_actual_registry_syscall(client,tmp_path,monkeypatch):
    import os
    import vati.accounts.registry as registry_module
    import commander.account_effects as effects
    ac,app=client;await paper(ac)
    body,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    operation=body['approval_proof']['challenge_id'];replace=registry_module.os.replace;seen=[]
    def observed(source,dest):
        marker=effects._effect_started.get()
        if marker is not None and marker[1].command=='account_remove' and str(dest)==str(tmp_path/'accounts.json'):
            # A wholly independent connection sees committed technical facts BEFORE replace.
            with sqlite3.connect(tmp_path/'vati.sqlite') as db:
                rows=db.execute('SELECT body_json FROM account_unlink_facts WHERE operation_id=? ORDER BY seq',(operation,)).fetchall()
            facts=[json.loads(r[0])['payload'] for r in rows]
            assert [p['kind'] for p in facts]==['PLAN','EPOCH','STEP']
            assert facts[-1]['data']['state']=='MAY_BEGIN'
            assert 'paper_owner' in json.loads((tmp_path/'accounts.json').read_text())['accounts'][0]['alias']
            seen.append(True)
        return replace(source,dest)
    monkeypatch.setattr(registry_module.os,'replace',observed)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert seen and response.status_code==200,response.text


@pytest.mark.asyncio
async def test_expiry_after_technical_commit_before_replace_retains_reserved_unknown(client,tmp_path,monkeypatch):
    from types import SimpleNamespace
    import commander.account_effects as effects
    ac,app=client;await paper(ac)
    body,issued=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    operation=body['approval_proof']['challenge_id'];before=(tmp_path/'accounts.json').read_bytes()
    step=UnlinkRecoveryBook.step;seen=[]
    def delayed(self,*a,**kw):
        result=step(self,*a,**kw)
        if a[4:]==('REGISTRY_REMOVE','MAY_BEGIN'):
            seen.append(True);monkeypatch.setattr(effects,'time',SimpleNamespace(time=lambda:issued['approval_expires_at_unix']))
        return result
    monkeypatch.setattr(UnlinkRecoveryBook,'step',delayed)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert seen and response.status_code==409 and response.json()['effect_state']=='UNKNOWN',response.text
    # Persistent incarnation detachment now precedes the recoverable plan.
    # A later refused account-removal replacement cannot erase that DATA effect.
    from vati.accounts import AccountRegistry
    cold=AccountRegistry(tmp_path/'accounts.json')
    assert (tmp_path/'accounts.json').read_bytes()!=before
    assert 'paper_owner' in cold.accounts and cold._lifecycles['paper_owner']['phase']=='DISCONNECTING'
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        parent=AccountEffectJournal(ledger).status(operation,'test-device')
        assert parent.phase=='UNKNOWN' and parent.result is None
        assert UnlinkRecoveryBook(ledger,secrets_root=tmp_path/'secrets')._history(operation)['steps']['REGISTRY_REMOVE'].payload['data']['state']=='MAY_BEGIN'


@pytest.mark.asyncio
async def test_invalid_integrity_key_after_reservation_preserves_unknown_without_plan(client,tmp_path):
    ac,app=client;await paper(ac)
    body,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    key=tmp_path/'secrets'/'private.unlink-plan-integrity.env'
    key.write_text('UNLINK_PLAN_INTEGRITY_KEY=malformed\n');key.chmod(0o600)
    before=(tmp_path/'accounts.json').read_bytes()
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert result.status_code==409,result.text
    from vati.accounts import AccountRegistry
    cold=AccountRegistry(tmp_path/'accounts.json')
    assert (tmp_path/'accounts.json').read_bytes()!=before
    assert 'paper_owner' in cold.accounts and cold._lifecycles['paper_owner']['phase']=='DISCONNECTING'
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        state=AccountEffectJournal(ledger).status(body['approval_proof']['challenge_id'],'test-device')
        assert state.phase=='UNKNOWN' and state.result is None
        assert not UnlinkRecoveryBook(ledger,initialize=False,secrets_root=tmp_path/'secrets')._facts(state.intent.operation_id)
    assert key.read_text()=='UNLINK_PLAN_INTEGRITY_KEY=malformed\n'


def test_orphaned_private_history_is_not_migrated_or_signed(tmp_path):
    with closing(Ledger(tmp_path/'native.sqlite')) as ledger:
        ledger._conn.execute('CREATE TABLE account_unlink_facts(original_evidence TEXT)')
        ledger._conn.execute("INSERT INTO account_unlink_facts VALUES('unsealed-original')");ledger._conn.commit()
        with pytest.raises(AccountEffectUnknown):UnlinkRecoveryBook(ledger,secrets_root=tmp_path/'secrets')
        assert ledger._conn.execute('SELECT * FROM account_unlink_facts').fetchall()==[('unsealed-original',)]
        assert not (tmp_path/'secrets').exists()


@pytest.mark.asyncio
async def test_capture_verifies_full_approved_original_before_minimizing_private_fields(client,tmp_path):
    from dataclasses import replace
    from commander.accounts import AccountControlSettings
    from commander.account_cleanup import prepare_plan
    from vati.accounts import AccountRegistry
    ac,app=client;await paper(ac)
    _,issued=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    registry=AccountRegistry(tmp_path/'accounts.json');account=registry.get('paper_owner')
    settings=AccountControlSettings(str(registry.path),str(tmp_path/'secrets'))
    review=issued['resolved_review']
    plan=prepare_plan(settings,registry,account,review,None)
    assert 'notes' not in plan['account_identity'] and 'mandate_ref' not in plan['account_identity']
    # A field omitted from the private minimal plan still belongs to the FULL
    # approved resource hash; a stale registry object cannot conceal its change.
    AccountRegistry(registry.path).replace(replace(account,notes='SOURCE nonsecret changed metadata'))
    with pytest.raises(AccountEffectUnknown):prepare_plan(settings,registry,account,review,None)
    assert not (tmp_path/'secrets'/'private.unlink-plan-integrity.env').exists()


def test_private_schema_loss_after_open_is_typed_hold_not_driver_error_or_repair(tmp_path):
    with closing(Ledger(tmp_path/'native.sqlite')) as ledger:
        book=UnlinkRecoveryBook(ledger)
        ledger._conn.execute('DROP TABLE account_unlink_heads');ledger._conn.commit()
        with pytest.raises(AccountEffectUnknown):book._history('original_missing_table_0001')
        assert ledger._conn.execute("SELECT name FROM sqlite_master WHERE name='account_unlink_heads'").fetchone() is None
        assert ledger.count()==0
