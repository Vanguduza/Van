"""Actual registry/entry consumers, PAPER metadata only; no Owner proof claim."""
import copy,json
from dataclasses import asdict,replace
from decimal import Decimal
from types import SimpleNamespace as NS
import pytest
from vati.accounts import Account,AccountRegistry
from vati.accounts.registry import AccountRegistryError
from vati.accounts.resource_version import resource_snapshot
from vati.accounts.restrictions import initial_record,transition_record,validate_record,public_record
from vati.accounts.access import bind_entry_authority
from vati.core.canonical import canonical_hash

ALIAS='paper_owner'

def paper(tmp_path):
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(ALIAS,'PAPER','DEMO_TRADER','USD',mandate_ref='prior-admitted-PAPER-fixture'))
    return registry

def row(registry,alias=ALIAS):
    return initial_record(alias=alias,operation_id='restriction_original_000001',device_id='source-device',
        domain='1'*64,resource_version=resource_snapshot(registry,alias)['resource_version'],
        request_digest='2'*64,review_digest='3'*64,admission_digest='4'*64,reason_code='OWNER_REQUEST',now=100)

def restrict(registry,alias=ALIAS):
    value=row(registry,alias)
    def change(current):
        current._restrictions[alias]=value
        current.accounts[alias]=replace(current.get(alias),enabled=False)
    registry.restriction_update(alias,change)
    return value

def test_legacy_account_and_resource_hash_do_not_gain_a_default_dataclass_field(tmp_path):
    registry=paper(tmp_path);account=registry.get(ALIAS)
    old={'schema':'vati.account-resource/1','alias':ALIAS,'revision':1,
        'account':asdict(account),'credential_file_generation':None}
    assert resource_snapshot(registry,ALIAS)['resource_version']==canonical_hash(old)
    assert 'restriction' not in asdict(account)
    assert json.loads(registry.path.read_text())['schema_version']==1

def test_restriction_only_schema4_needs_no_invented_unlink_rows_and_survives_other_writers(tmp_path):
    registry=paper(tmp_path);value=restrict(registry)
    data=json.loads(registry.path.read_text())
    assert data['schema_version']==4 and data['lifecycle_schema_floor']==1
    assert 'account_lifecycles' not in data and 'account_lifecycle_history' not in data
    cold=AccountRegistry(registry.path);assert cold._restrictions[ALIAS]==value
    cold.replace(replace(cold.get(ALIAS),label='New local label'))
    assert AccountRegistry(registry.path)._restrictions[ALIAS]==value
    assert cold.get(ALIAS).mode=='DEMO_TRADER' and cold.get(ALIAS).mandate_ref=='prior-admitted-PAPER-fixture'
    assert public_record(value)['entry_permitted'] is False

@pytest.mark.parametrize('history',[False,True])
def test_schema4_preserves_previous_lifecycle_floor_and_cold_reload_rejects_erasure(tmp_path,history):
    from trading.tests.test_account_strategy_detachment import detached
    registry,account,original=detached(tmp_path)
    if history:
        def rotate(current):
            current._lifecycle_history[original['operation_id']]=copy.deepcopy(original)
            newer=copy.deepcopy(original);newer.update(operation_id='later_lifecycle_00000001',incarnation='9'*64)
            current._lifecycles[account.alias]=newer
        registry.lifecycle_update(account.alias,rotate)
    registry.add(Account('other_owner','PAPER','OBSERVE','USD'))
    before=json.loads(registry.path.read_text());restrict(registry,'other_owner')
    data=json.loads(registry.path.read_text());assert data['lifecycle_schema_floor']==(3 if history else 2)
    for key in ['account_lifecycles']+(['account_lifecycle_history'] if history else []):assert data[key]==before[key]
    key='account_lifecycle_history' if history else 'account_lifecycles'
    del data[key];registry.path.write_text(json.dumps(data))
    with pytest.raises(AccountRegistryError,match='cannot be read safely') as error:AccountRegistry(registry.path)
    assert isinstance(error.value.__cause__,AccountRegistryError) and 'prior lifecycle' in str(error.value.__cause__)

@pytest.mark.parametrize('damage',['foreign','downgrade','missing-floor','boolean-floor'])
def test_strict_schema4_foreign_or_downgraded_envelopes_refuse(tmp_path,damage):
    registry=paper(tmp_path);restrict(registry);data=json.loads(registry.path.read_text())
    if damage=='foreign':data['foreign_restriction_owner']={}
    elif damage=='downgrade':data['schema_version']=1
    elif damage=='missing-floor':data.pop('lifecycle_schema_floor')
    else:data['lifecycle_schema_floor']=True
    registry.path.write_text(json.dumps(data))
    with pytest.raises(AccountRegistryError):AccountRegistry(registry.path)

@pytest.mark.parametrize('field',['request_digest','resource_version','admission_digest'])
def test_initial_event_cannot_disagree_with_original_bindings(tmp_path,field):
    value=row(paper(tmp_path));value['events'][0][field]='f'*64
    with pytest.raises(AccountRegistryError,match='initial transition'):validate_record(value)

def test_cold_reader_validates_exact_predecessor_digest(tmp_path):
    registry=paper(tmp_path);original=restrict(registry)
    advanced=transition_record(original,operation_id='restriction_reauth_000001',device_id='source-device',
        phase='REAUTH_PENDING',request_digest='5'*64,resource_version=resource_snapshot(registry,ALIAS)['resource_version'],
        admission_digest='6'*64,now=101)
    registry.restriction_update(ALIAS,lambda current:current._restrictions.update({ALIAS:advanced}))
    data=json.loads(registry.path.read_text());data['account_restrictions'][ALIAS]['events'][1]['previous_digest']='f'*64
    registry.path.write_text(json.dumps(data))
    with pytest.raises(AccountRegistryError,match='cannot be read safely') as error:AccountRegistry(registry.path)
    assert isinstance(error.value.__cause__,AccountRegistryError) and 'predecessor' in str(error.value.__cause__)

@pytest.mark.parametrize('target',['selected','other','schema','floor'])
def test_transform_cannot_change_writer_owned_resource_or_schema_scope(tmp_path,target):
    registry=paper(tmp_path);registry.add(Account('other_owner','PAPER','OBSERVE','USD'));before=registry.path.read_bytes();value=row(registry)
    def corrupt(current):
        current._restrictions[ALIAS]=value;current.accounts[ALIAS]=replace(current.get(ALIAS),enabled=False)
        if target in {'selected','other'}:current._resource_revisions[ALIAS if target=='selected' else 'other_owner']+=1
        elif target=='schema':current._schema_version=4
        else:current._lifecycle_schema_floor=3
    with pytest.raises(AccountRegistryError,match='epochs or schema'):registry.restriction_update(ALIAS,corrupt)
    assert registry.path.read_bytes()==before

@pytest.mark.parametrize('whole_save',[False,True])
def test_enabling_profile_cannot_clear_restriction(tmp_path,whole_save):
    registry=paper(tmp_path);restrict(registry);before=registry.path.read_bytes()
    with pytest.raises(AccountRegistryError,match='restriction'):
        if whole_save:
            registry.accounts[ALIAS]=replace(registry.get(ALIAS),enabled=True);registry.save()
        else:registry.replace(replace(registry.get(ALIAS),enabled=True))
    assert registry.path.read_bytes()==before and not AccountRegistry(registry.path).get(ALIAS).enabled

def test_cached_entry_refuses_but_native_protective_and_manual_exit_callbacks_remain(tmp_path):
    registry=paper(tmp_path);bound=registry.get(ALIAS);sent=[];closed=[]
    adapter=bind_entry_authority(NS(submit=lambda *a,**kw:sent.append(True),close=lambda:closed.append('protective/manual')),registry,bound)
    restrict(registry)
    command=NS(account_alias=ALIAS,venue='paper',trade_intent_id='source-entry',decision_hash='1'*64,entry_price=Decimal('1'))
    assert adapter.submit(command,now_ms=1000).status=='REJECTED' and not sent
    adapter.close();assert closed==['protective/manual']

def test_alias_recreation_archives_exact_original_restriction_without_retargeting(tmp_path):
    registry=paper(tmp_path);original=restrict(registry)
    registry.remove(ALIAS);registry.add(Account(ALIAS,'PAPER','OBSERVE','USD'))
    cold=AccountRegistry(registry.path)
    assert ALIAS not in cold._restrictions and cold._restriction_history[original['restriction_id']]==original
    assert cold.get(ALIAS).mode=='OBSERVE'
    assert json.loads(cold.path.read_text())['schema_version']==4
