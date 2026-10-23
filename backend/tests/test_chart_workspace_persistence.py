"""Native, renderer-independent chart state; current owner edits never place orders."""
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from conftest_automation import make_store
from van_gateway.storage.db import Store
from van_gateway.trading.chart_models import CreateWorkspace,ReplaceWorkspace,RestoreWorkspace,DeleteWorkspace,WorkspaceState
from van_gateway.trading.chart_workspaces import ChartWorkspaceService,ChartWorkspaceError,sha


def state(name='Owner workspace',**changes):
    return WorkspaceState.model_validate({'name':name,'selected_panel_id':'main','panels':[{'panel_id':'main',
        'instrument':{'venue':'fixture-venue','environment':'DEMO','api_family':'spot','product_id':'native-product-01','symbol':'SAME'},
        'timeframe':'H1','viewport':{'start_ms':1000,'end_ms':2000,'min_price':'-1.0000000000000000001','max_price':'2.0000000000000000001'},
        'indicators':[{'indicator_id':'ema-one','spec':{'kind':'EMA','period':14},'source_timeframe':'H1'}],
        'drawings':[{'drawing_id':'line-one','kind':'TREND','anchors':[{'time_ms':1000,'price':'0.000000000000000001'},{'time_ms':2000,'price':'1.000000000000000001'}],'note':'owner private note fixture'}]}],**changes})

async def service(tmp_path):return ChartWorkspaceService(await make_store(tmp_path))
async def create(s,request='create-one',name='Owner workspace',owner='owner'):
    return await s.create(owner,CreateWorkspace(request_id=request,state=state(name)))

@pytest.mark.asyncio
async def test_exact_anchors_parameters_native_identity_and_restart_round_trip(tmp_path):
    s=await service(tmp_path);result=await create(s)
    restarted=ChartWorkspaceService(Store(s.store.path));actual=await restarted.get('owner',result.workspace_id)
    assert actual.state==state() and actual.state_sha256==result.state_sha256
    assert actual.state.panels[0].drawings[0].anchors[0].price=='0.000000000000000001'
    assert actual.authority_effect=='NONE' and actual.instrument_scope_status=='OWNER_SELECTION_NOT_NATIVE_VERIFIED'
    assert not await s.store.fetchall('SELECT * FROM mission_activities')

@pytest.mark.asyncio
async def test_replayed_create_has_one_original_identity_even_after_later_edit(tmp_path):
    s=await service(tmp_path);original=await create(s)
    changed=await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='edit-one',expected_revision=1,state=state('New title')))
    assert changed.revision==2 and await create(s)==original
    assert await s.operation('owner','create-one')==original
    assert (await s.get('owner',original.workspace_id)).state.name=='New title'
    assert (await s.get('owner',original.workspace_id,1)).state.name=='Owner workspace'
    assert (await s.listing('owner')).total_count==1

@pytest.mark.asyncio
async def test_same_request_cannot_change_payload_operation_or_target(tmp_path):
    s=await service(tmp_path);original=await create(s)
    with pytest.raises(ChartWorkspaceError,match='CHART_OPERATION_SCOPE_CONFLICT'):await create(s,name='Different request')
    with pytest.raises(ChartWorkspaceError,match='CHART_OPERATION_SCOPE_CONFLICT'):
        await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='create-one',expected_revision=1,state=state()))
    other=await create(s,request='create-other')
    await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='edit-one',expected_revision=1,state=state('Edit')))
    with pytest.raises(ChartWorkspaceError,match='CHART_OPERATION_SCOPE_CONFLICT'):
        await s.replace('owner',other.workspace_id,ReplaceWorkspace(request_id='edit-one',expected_revision=1,state=state('Edit')))

@pytest.mark.asyncio
async def test_same_request_concurrently_creates_one_workspace_across_service_instances(tmp_path):
    s=await service(tmp_path);other=ChartWorkspaceService(Store(s.store.path))
    results=await asyncio.gather(create(s),create(other),create(s),create(other))
    assert len({r.workspace_id for r in results})==1
    assert len(await s.store.fetchall('SELECT * FROM chart_workspace_revisions'))==1
    assert len(await s.store.fetchall('SELECT * FROM chart_workspace_operations'))==1

@pytest.mark.asyncio
async def test_cross_device_stale_edits_cannot_silently_win(tmp_path):
    s=await service(tmp_path);original=await create(s)
    results=await asyncio.gather(*(s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id=f'edit-{n}',expected_revision=1,state=state(f'Title {n}'))) for n in range(4)),return_exceptions=True)
    assert sum(not isinstance(r,Exception) for r in results)==1
    refused=[r for r in results if isinstance(r,ChartWorkspaceError)]
    assert len(refused)==3 and all(r.code=='CHART_REVISION_CONFLICT' and r.details['current_revision']==2 for r in refused)
    assert (await s.get('owner',original.workspace_id)).revision==2

@pytest.mark.asyncio
async def test_restore_is_new_revision_and_preserves_both_immutable_originals(tmp_path):
    s=await service(tmp_path);original=await create(s)
    await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='edit',expected_revision=1,state=state('Second')))
    restored=await s.restore('owner',original.workspace_id,RestoreWorkspace(request_id='undo',expected_revision=2,target_revision=1))
    current=await s.get('owner',original.workspace_id)
    assert restored.revision==3 and current.restored_from_revision==1 and current.state==state()
    assert (await s.get('owner',original.workspace_id,2)).state.name=='Second'
    assert await s.restore('owner',original.workspace_id,RestoreWorkspace(request_id='undo',expected_revision=2,target_revision=1))==restored
    with pytest.raises(ChartWorkspaceError,match='CHART_REVISION_CONFLICT'):
        await s.restore('owner',original.workspace_id,RestoreWorkspace(request_id='stale-undo',expected_revision=2,target_revision=2))

@pytest.mark.asyncio
async def test_owner_isolation_covers_current_revisions_operations_and_request_ids(tmp_path):
    s=await service(tmp_path);original=await create(s,owner='owner-alpha')
    assert (await s.listing('owner-beta')).total_count==0
    for operation in [s.get('owner-beta',original.workspace_id),s.get('owner-beta',original.workspace_id,1),s.operation('owner-beta','create-one'),s.revisions('owner-beta',original.workspace_id)]:
        with pytest.raises(ChartWorkspaceError) as exc:await operation
        assert exc.value.status==404
    beta=await create(s,owner='owner-beta');assert beta.workspace_id!=original.workspace_id

@pytest.mark.asyncio
async def test_delete_erases_all_private_revision_bodies_but_keeps_original_minimal_outcome(tmp_path):
    s=await service(tmp_path);original=await create(s)
    await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='edit',expected_revision=1,state=state('Private later title')))
    body=DeleteWorkspace(request_id='delete',expected_revision=2)
    result=await s.delete('owner',original.workspace_id,body)
    assert result.status=='DELETED' and result.state_sha256 is None and result.revision==3
    assert not await s.store.fetchall('SELECT * FROM chart_workspaces')
    assert not await s.store.fetchall('SELECT * FROM chart_workspace_revisions')
    assert await s.delete('owner',original.workspace_id,body)==result
    assert await s.operation('owner','create-one')==original
    retained=[dict(r) for r in await s.store.fetchall('SELECT * FROM chart_workspace_operations')]
    assert 'owner private note fixture' not in json.dumps(retained) and 'Private later title' not in json.dumps(retained)
    with pytest.raises(ChartWorkspaceError,match='CHART_WORKSPACE_UNKNOWN'):await s.get('owner',original.workspace_id,1)

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['create','replace','delete','restore'])
async def test_failed_original_receipt_insert_rolls_back_every_state_mutation(tmp_path,kind):
    s=await service(tmp_path);original=await create(s)
    if kind=='restore':await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='prior-edit',expected_revision=1,state=state('Before restore')))
    before=[dict(r) for r in await s.store.fetchall('SELECT * FROM chart_workspaces')]
    revisions=[dict(r) for r in await s.store.fetchall('SELECT * FROM chart_workspace_revisions')]
    await s.store.execute("CREATE TRIGGER fixture_refuse_chart_receipt BEFORE INSERT ON chart_workspace_operations BEGIN SELECT RAISE(ABORT,'receipt unavailable'); END")
    with pytest.raises(Exception,match='receipt unavailable'):
        if kind=='create':await create(s,request='new')
        elif kind=='replace':await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='new',expected_revision=1,state=state('New')))
        elif kind=='delete':await s.delete('owner',original.workspace_id,DeleteWorkspace(request_id='new',expected_revision=1))
        else:await s.restore('owner',original.workspace_id,RestoreWorkspace(request_id='new',expected_revision=2,target_revision=1))
    assert [dict(r) for r in await s.store.fetchall('SELECT * FROM chart_workspaces')]==before
    assert [dict(r) for r in await s.store.fetchall('SELECT * FROM chart_workspace_revisions')]==revisions

@pytest.mark.asyncio
async def test_list_and_revision_pages_report_native_totals_without_duplicates(tmp_path):
    s=await service(tmp_path)
    originals=[await create(s,request=f'create-{n}') for n in range(5)]
    ids=[];cursor=None
    for _ in range(10):
        page=await s.listing('owner',limit=2,after_id=cursor);ids.extend(r.workspace_id for r in page.workspaces);assert page.total_count==5
        cursor=page.next_after_id
        if cursor is None:break
    assert len(ids)==len(set(ids))==5
    original=originals[0]
    for n in range(1,5):await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id=f'edit-{n}',expected_revision=n,state=state(f'Revision {n+1}')))
    numbers=[];cursor=None
    for _ in range(10):
        page=await s.revisions('owner',original.workspace_id,limit=2,before_revision=cursor);numbers.extend(r.revision for r in page.revisions);assert page.total_count==5
        cursor=page.next_before_revision
        if cursor is None:break
    assert numbers==[5,4,3,2,1]
    with pytest.raises(ChartWorkspaceError,match='CHART_REVISION_UNKNOWN'):await s.revisions('owner',original.workspace_id,before_revision=900)

@pytest.mark.asyncio
@pytest.mark.parametrize('corruption',['bytes','valid_hash_invalid_model'])
async def test_corrupt_persisted_state_is_explicitly_unavailable(tmp_path,corruption):
    s=await service(tmp_path);original=await create(s);bad='{}'
    if corruption=='bytes':bad=state('Tampered but structurally valid').model_dump_json()
    if corruption=='bytes':await s.store.execute('UPDATE chart_workspace_revisions SET state_json=?',(bad,))
    else:await s.store.execute('UPDATE chart_workspace_revisions SET state_json=?,state_sha256=?',(bad,sha(bad)))
    with pytest.raises(ChartWorkspaceError,match='CHART_STATE_INTEGRITY_FAILED') as exc:await s.get('owner',original.workspace_id)
    assert exc.value.status==503

@pytest.mark.asyncio
async def test_capacity_refuses_without_removing_existing_history(tmp_path,monkeypatch):
    s=await service(tmp_path);cap=s.capability().model_copy(update={'max_workspaces':1,'max_revisions':1});monkeypatch.setattr(s,'capability',lambda:cap)
    original=await create(s)
    with pytest.raises(ChartWorkspaceError,match='CHART_WORKSPACE_CAPACITY_REACHED'):await create(s,request='extra')
    with pytest.raises(ChartWorkspaceError,match='CHART_REVISION_CAPACITY_REACHED'):
        await s.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='extra-edit',expected_revision=1,state=state('Extra')))
    assert (await s.get('owner',original.workspace_id)).revision==1
    assert (await s.revisions('owner',original.workspace_id)).total_count==1

@pytest.mark.parametrize('change',[
    {'schema_version':True},{'schema_version':2},{'name':' '},{'name':'bad\x00name'},
    {'selected_panel_id':'absent'},{'layout':'SPLIT_HORIZONTAL'},{'owner_id':'attacker'},{'authority_effect':'TRADE'},
])
def test_state_schema_rejects_ambiguous_or_privileged_fields(change):
    with pytest.raises(ValidationError):state(**change)

@pytest.mark.parametrize('change',[
    {'anchors':[{'time_ms':True,'price':'1'},{'time_ms':2000,'price':'2'}]},
    {'anchors':[{'time_ms':1000,'price':1.01},{'time_ms':2000,'price':'2'}]},
    {'anchors':[{'time_ms':1000,'price':'NaN'},{'time_ms':2000,'price':'2'}]},
    {'anchors':[{'time_ms':1000,'price':'1'},{'time_ms':1000,'price':'2'}]},
    {'anchors':[{'time_ms':1000,'price':'1'}]}, {'pixels':[1,2]}, {'kind':'SCRIPT'},
])
def test_drawing_model_never_rounds_prices_or_substitutes_pixels(change):
    body=state().model_dump();body['panels'][0]['drawings'][0].update(change)
    with pytest.raises(ValidationError):WorkspaceState.model_validate(body)

@pytest.mark.parametrize('change',[
    {'provenance_tier':'VATI_SOURCE'},{'schema_version':True},{'spec':{'kind':'EMA','period':True}},
    {'spec':{'kind':'EMA','period':0}},{'spec':{'kind':'MACD','fast':30,'slow':12}},
    {'spec':{'kind':'BOLLINGER','deviations':'0'}},{'spec':{'kind':'SCRIPT','javascript':'trade()'}},
])
def test_indicator_settings_cannot_claim_certification_or_execute_code(change):
    body=state().model_dump();body['panels'][0]['indicators'][0].update(change)
    with pytest.raises(ValidationError):WorkspaceState.model_validate(body)

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['not_applied','applied_then_ack_lost','applied_then_later_owner_edit','readback_unavailable','conflicting_request_after_rollback'])
async def test_commit_recovery_reports_only_the_original_native_operation(tmp_path,monkeypatch,mode):
    s=await service(tmp_path);connection=s.store.connection;original_fetch=s.store.fetchone;armed=True
    competing=ChartWorkspaceService(Store(s.store.path));body=CreateWorkspace(request_id='uncertain',state=state())
    @asynccontextmanager
    async def interleaved():
        nonlocal armed
        async with connection() as db:
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def commit(self):
                    nonlocal armed
                    if not armed:return await db.commit()
                    armed=False
                    if mode in {'applied_then_ack_lost','applied_then_later_owner_edit','readback_unavailable'}:
                        await db.commit()
                        if mode=='applied_then_later_owner_edit':
                            original=await competing.operation('owner','uncertain')
                            await competing.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='later',expected_revision=1,state=state('Later owner edit')))
                    elif mode=='conflicting_request_after_rollback':
                        await db.rollback()
                        await competing.create('owner',CreateWorkspace(request_id='uncertain',state=state('Conflicting request')))
                    raise OSError('commit acknowledgement lost')
            yield Connection()
    monkeypatch.setattr(s.store,'connection',interleaved)
    if mode=='readback_unavailable':
        async def unavailable(*args,**kwargs):raise OSError('native read unavailable')
        monkeypatch.setattr(s.store,'fetchone',unavailable)
    if mode in {'not_applied','readback_unavailable','conflicting_request_after_rollback'}:
        with pytest.raises(ChartWorkspaceError) as exc:await s.create('owner',body)
        expected='CHART_WRITE_NOT_APPLIED' if mode=='not_applied' else 'CHART_WRITE_OUTCOME_UNKNOWN'
        assert exc.value.code==expected and exc.value.status==503 and exc.value.details['request_id']=='uncertain'
    else:
        result=await s.create('owner',body)
        assert result==await competing.operation('owner','uncertain') and result.revision==1
        assert (await competing.get('owner',result.workspace_id,1)).state==state()
        if mode=='applied_then_later_owner_edit':assert (await competing.get('owner',result.workspace_id)).revision==2
    monkeypatch.setattr(s.store,'fetchone',original_fetch)
    if mode=='not_applied':
        assert not await s.store.fetchall('SELECT * FROM chart_workspaces')
        assert (await s.create('owner',body)).revision==1
    if mode=='readback_unavailable':assert (await competing.operation('owner','uncertain')).status=='SAVED'

@pytest.mark.asyncio
async def test_cancellation_before_commit_cannot_leave_chart_state_without_original_receipt(tmp_path,monkeypatch):
    s=await service(tmp_path);connection=s.store.connection;reached=asyncio.Event();armed=True
    @asynccontextmanager
    async def cancellable():
        async with connection() as db:
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def commit(self):
                    if armed:
                        reached.set();await asyncio.Event().wait()
                    await db.commit()
            yield Connection()
    monkeypatch.setattr(s.store,'connection',cancellable)
    task=asyncio.create_task(create(s))
    await asyncio.wait_for(reached.wait(),5);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert not await s.store.fetchall('SELECT * FROM chart_workspaces')
    assert not await s.store.fetchall('SELECT * FROM chart_workspace_revisions')
    assert not await s.store.fetchall('SELECT * FROM chart_workspace_operations')
    armed=False
    assert (await create(s)).revision==1

@pytest.mark.asyncio
async def test_state_size_budget_fails_without_any_private_snapshot_or_false_receipt(tmp_path):
    s=await service(tmp_path);body=state().model_dump()
    drawing=body['panels'][0]['drawings'][0]
    body['panels'][0]['drawings']=[{**drawing,'drawing_id':f'drawing-{n}','note':'x'*4000} for n in range(80)]
    with pytest.raises(ChartWorkspaceError,match='CHART_STATE_TOO_LARGE') as exc:
        await s.create('owner',CreateWorkspace(request_id='large',state=WorkspaceState.model_validate(body)))
    assert exc.value.status==413 and not await s.store.fetchall('SELECT * FROM chart_workspace_operations')

@pytest.mark.parametrize('spec',[
    {'kind':'SMA','period':20},{'kind':'EMA','period':20},{'kind':'RSI','period':14},{'kind':'ATR','period':14},
    {'kind':'MACD','fast':12,'slow':26,'signal':9},{'kind':'BOLLINGER','period':20,'deviations':'2.5'},
    {'kind':'VWAP','anchor_ms':1700000000000},
])
def test_every_supported_indicator_setting_round_trips_with_parameters(spec):
    body=state().model_dump();body['panels'][0]['indicators'][0]['spec']=spec
    parsed=WorkspaceState.model_validate(body)
    assert parsed.panels[0].indicators[0].spec.model_dump()==spec

@pytest.mark.asyncio
async def test_same_symbol_keeps_disjoint_native_products_and_no_alias_remapping(tmp_path):
    s=await service(tmp_path);body=state().model_dump();first=body['panels'][0]
    first['instrument']['product_id']='Exact native product / A'
    other=json.loads(json.dumps(first));other['panel_id']='other';other['instrument'].update(venue='other-venue',product_id='Exact native product / B',account_id='Account / B')
    body.update(layout='SPLIT_HORIZONTAL',panels=[first,other])
    saved=await s.create('owner',CreateWorkspace(request_id='multi-product',state=WorkspaceState.model_validate(body)))
    actual=await s.get('owner',saved.workspace_id)
    assert actual.state.model_dump()==WorkspaceState.model_validate(body).model_dump()
    assert actual.state.panels[0].instrument.symbol==actual.state.panels[1].instrument.symbol
    assert actual.state.panels[0].instrument.product_id!=actual.state.panels[1].instrument.product_id

@pytest.mark.asyncio
async def test_additive_migration_resumes_partial_table_creation_and_preserves_existing_owner_data(tmp_path):
    s=await service(tmp_path)
    await s.store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES('fixture_previous_owner','unchanged',123)")
    await s.store.execute('DROP TABLE chart_workspace_revisions');await s.store.execute('DROP TABLE chart_workspace_operations')
    await s.store.execute('DELETE FROM schema_migrations WHERE version=56')
    restarted=Store(s.store.path);await restarted.migrate();await restarted.migrate()
    assert (await restarted.fetchone("SELECT value FROM runtime_meta WHERE key='fixture_previous_owner'"))['value']=='unchanged'
    assert (await restarted.fetchone('SELECT max(version) v FROM schema_migrations'))['v']==56
    assert (await create(ChartWorkspaceService(restarted))).revision==1
