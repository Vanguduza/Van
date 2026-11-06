"""Real registry writer and both production runtime/entry consumers, SOURCE."""
from dataclasses import asdict
from decimal import Decimal as D
from types import SimpleNamespace as NS
import time
import pytest
from vati.accounts import Account,AccountRegistry
from vati.accounts.lifecycle import require_attached
from vati.accounts.registry import AccountRegistryError
from vati.core.canonical import canonical_hash
from vati.app.service import ServiceConfig,SessionService
from vati.app.account_service import AccountCoordinatorService
from vati.accounts.access import bind_entry_authority


def detached(tmp_path):
    r=AccountRegistry(tmp_path/'accounts.json')
    acc=r.add(Account('paper_owner','PAPER','DEMO_TRADER','USD'))
    now=int(time.time())
    row={'schema':'vati.account-lifecycle/1','alias':acc.alias,'operation_id':'original_deletion_00000001','device_id':'source-device',
        'account_control_domain':'1'*64,'incarnation':'2'*64,'revision':2,'phase':'PENDING_ARCHIVE',
        'created_at_unix':now,'archive_at_unix':now+600,'grace_seconds':600,'restore':asdict(acc),
        'strategies':['fx_trend_pullback-v1'],'session_sources':[],'history_ref':'3'*64,'credential_disposition':'NONE',
        'unlink_ref':'4'*64,'oauth_discard_ref':'5'*64,'original_request':{'alias':acc.alias,'variant':'DELETE_GRACE','grace_seconds':600,'oauth_discard_digest':'5'*64},'detached':True,'link_intent':'RELINK_REQUIRED','remote_account_closed':False}
    r.lifecycle_update(acc.alias,lambda current:current._lifecycles.update({acc.alias:row}))
    return r,acc,row

def config(r):return ServiceConfig(account_alias='paper_owner',symbol='EURUSD',base='EUR',quote='USD',timeframe='M5',
    contract={},mandate={},capsules=['fx_trend_pullback-v1'],registry_path=str(r.path),
    instruments=[{'symbol':'GBPUSD','base':'GBP','quote':'USD'}])

@pytest.mark.parametrize('runtime',[SessionService,AccountCoordinatorService])
def test_actual_runtime_builds_refuse_detached_even_with_enabled_old_config(tmp_path,runtime):
    r,acc,_=detached(tmp_path)
    assert r.get(acc.alias).enabled and r.get(acc.alias).mode=='DEMO_TRADER'
    service=SessionService(config(r),bar_source=NS()) if runtime is SessionService else runtime(config(r))
    with pytest.raises(AccountRegistryError,match='detached'):service.build()

@pytest.mark.parametrize('reuse',[False,True])
def test_actual_final_cached_adapter_cannot_send_after_detachment_or_alias_reuse(tmp_path,reuse):
    r,acc,_=detached(tmp_path);sent=[]
    if reuse:
        r.remove(acc.alias);r.add(acc)
    adapter=bind_entry_authority(NS(submit=lambda *a,**kw:sent.append(True)),r,acc)
    cmd=NS(account_alias=acc.alias,venue=acc.router_venue,trade_intent_id='source-original-entry',
        decision_hash='1'*64,entry_price=D('1'))
    receipt=adapter.submit(cmd,now_ms=int(time.time()*1000))
    assert receipt.status=='REJECTED' and not sent
    assert AccountRegistry(r.path)._lifecycles[acc.alias]['detached'] is True

def test_generic_registry_writer_cannot_drop_native_detachment_metadata(tmp_path):
    r,acc,row=detached(tmp_path)
    from dataclasses import replace
    r.replace(replace(acc,label='New local label'))
    cold=AccountRegistry(r.path)
    assert cold._lifecycles[acc.alias]==row
    with pytest.raises(AccountRegistryError):require_attached(cold,acc.alias)

@pytest.mark.parametrize('corruption',['phase','detached','archive_at_unix','schema'])
def test_corrupt_lifecycle_state_holds_in_actual_registry_reader(tmp_path,corruption):
    r,acc,row=detached(tmp_path)
    import json
    data=json.loads(r.path.read_text());data['account_lifecycles'][acc.alias][corruption]='invalid'
    r.path.write_text(json.dumps(data))
    with pytest.raises(AccountRegistryError):AccountRegistry(r.path)


def test_historical_ordinary_v1_remains_readable_and_lifecycle_envelope_is_sticky_v2(tmp_path):
    import json
    ordinary=AccountRegistry(tmp_path/'ordinary.json');ordinary.add(Account('ordinary_owner','PAPER','OBSERVE','USD'))
    assert json.loads(ordinary.path.read_text())['schema_version']==1
    assert AccountRegistry(ordinary.path).get('ordinary_owner')
    r,acc,row=detached(tmp_path)
    assert json.loads(r.path.read_text())['schema_version']==2
    r.remove(acc.alias);r.add(acc)
    assert json.loads(r.path.read_text())['schema_version']==2
    assert AccountRegistry(r.path)._lifecycles[acc.alias]==row

@pytest.mark.parametrize('mutation',['erase','rebind','downgrade'])
def test_native_lifecycle_writer_refuses_detachment_erasure_rebinding_or_version_downgrade(tmp_path,mutation):
    import json
    r,acc,row=detached(tmp_path);before=r.path.read_bytes()
    if mutation=='downgrade':
        data=json.loads(before);data['schema_version']=1;r.path.write_text(json.dumps(data))
        with pytest.raises(AccountRegistryError):AccountRegistry(r.path)
    else:
        def alter(current):
            if mutation=='erase':current._lifecycles.clear()
            else:current._lifecycles[acc.alias]['operation_id']='replacement_original_000001'
        with pytest.raises(AccountRegistryError):r.lifecycle_update(acc.alias,alter)
        assert r.path.read_bytes()==before
