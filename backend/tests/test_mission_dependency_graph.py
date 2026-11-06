import pytest
from conftest_automation import make_store
from van_gateway.mission.models import MissionOrigin
from van_gateway.models import OriginChannel
from van_gateway.mission.service import MissionService,MissionError
from van_gateway.mission.api import AddActivityBody

@pytest.mark.asyncio
async def test_orphan_dependency_refused_without_creating_work(tmp_path):
    store=await make_store(tmp_path);svc=MissionService(store)
    m=await svc.create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,origin_channel=OriginChannel.VOICE,title='Graph',goal='Observe dependencies')
    with pytest.raises(MissionError,match='ACTIVITY_DEPENDENCY_UNKNOWN'):
        await svc.add_activity(mission_id=m.mission_id,activity_type='research',capability_id='research',executor='HERMES',dependency_activity_ids=['missing'])
    assert await svc.activities(m.mission_id)==[]

def test_activity_wire_retains_dependency_identity():
    b=AddActivityBody(activity_type='research',capability_id='research',executor='HERMES',dependency_activity_ids=['existing-stage'])
    assert b.model_dump().get('dependency_activity_ids')==['existing-stage']


from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from van_gateway.config import get_settings
from van_gateway.mission.api import MissionApi
from van_gateway.mission.graph import project_graph
from van_gateway.mission.models import Activity, ActivityState, MissionState, MissionEventType
from van_gateway.models import PrincipalType


def node(name, *deps, **fields):
    return Activity(activity_id=name,mission_id='mission',activity_type='stage',
        capability_id='research',executor='HERMES',started_at_ms=1,
        dependency_activity_ids=list(deps),**fields)


def test_graph_ids_and_dependency_path_are_stable_across_layout_and_input_order():
    rows=[node('start'),node('middle','start'),node('finish','middle'),node('other','start')]
    a=project_graph('mission','RUNNING',rows)
    b=project_graph('mission','RUNNING',list(reversed(rows)))
    assert a==b and a.critical_path.node_ids==['start','middle','finish']
    assert a.critical_path.edge_count==2 and a.critical_path.estimated_duration_ms is None
    assert a.critical_path.basis=='DEPENDENCY_COUNT' and a.authority_granted is False
    assert all(n.state==ActivityState.PENDING for n in a.nodes)
    assert len({e.edge_id for e in a.edges})==3


def test_actual_cycles_exclude_downstream_nodes_and_suppress_critical_path():
    g=project_graph('mission','RUNNING',[node('a','b'),node('b','a'),node('downstream','b')])
    assert g.critical_path is None
    assert [i.node_ids for i in g.issues if i.code=='CYCLE']==[['a','b']]


def test_orphan_edges_and_conflicting_executor_claims_remain_visible():
    g=project_graph('mission','RUNNING',[node('a','missing',executor_ref='run-1'),node('b',executor_ref='run-1')])
    assert {i.code for i in g.issues}=={'MISSING_DEPENDENCY','CONFLICTING_EXECUTOR_BINDING'}
    assert g.critical_path is None and g.edges[0].source=='missing'


@pytest.mark.parametrize('outcome',['PARTIAL_SUCCESS','UNVERIFIABLE','SUBMITTED'])
def test_executor_outcome_does_not_invent_verified_mission_success(outcome):
    g=project_graph('mission','RUNNING',[node('a',state=ActivityState.COMPLETED)],
        observations={'a':{'state':outcome,'evidence_ref':'provider://original'}},
        evidence={'a':['stage://receipt','stage://receipt']})
    assert g.mission_state==MissionState.RUNNING
    assert g.nodes[0].executor_state==outcome and g.nodes[0].executor_observation_available
    assert g.nodes[0].evidence_refs==['provider://original','stage://receipt']


def test_long_workflow_uses_no_recursive_dfs_or_quadratic_path_copies():
    rows=[node(str(i),*([str(i-1)] if i else [])) for i in range(1500)]
    g=project_graph('mission','RUNNING',rows)
    assert g.critical_path.node_ids==[str(i) for i in range(1500)]
    assert g.critical_path.edge_count==1499


def test_oversized_graph_is_refused_instead_of_silently_omitting_work():
    with pytest.raises(ValueError,match='MISSION_GRAPH_NODE_LIMIT'):
        project_graph('mission','RUNNING',[node(str(i)) for i in range(2001)])


async def service(tmp_path):
    svc=MissionService(await make_store(tmp_path))
    m=await svc.create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,title='Graph',goal='Inspect actual work')
    return svc,m


async def stage(svc,m,**fields):
    return await svc.add_activity(mission_id=m.mission_id,activity_type='stage',capability_id='research',executor='HERMES',**fields)


@pytest.mark.asyncio
async def test_foreign_dependency_refused_and_does_not_attach_another_missions_work(tmp_path):
    svc,m=await service(tmp_path);a=await stage(svc,m)
    other=await svc.create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,title='Other',goal='Separate scope')
    with pytest.raises(MissionError,match='ACTIVITY_DEPENDENCY_SCOPE_MISMATCH'):
        await stage(svc,other,dependency_activity_ids=[a.activity_id])
    assert await svc.activities(other.mission_id)==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('deps',[[''],['missing','missing'],[False],[' ']])
async def test_invalid_dependency_input_creates_no_activity(tmp_path,deps):
    svc,m=await service(tmp_path)
    with pytest.raises(MissionError,match='ACTIVITY_DEPENDENCY_INVALID'):
        await stage(svc,m,dependency_activity_ids=deps)
    assert await svc.activities(m.mission_id)==[]


@pytest.mark.asyncio
async def test_terminal_transition_during_admission_cannot_append_new_work(tmp_path,monkeypatch):
    svc,m=await service(tmp_path)
    async def cancellation_wins(mission,capability):
        await svc.transition(mission.mission_id,target=MissionState.CANCELLED)
    monkeypatch.setattr(svc,'_assert_capability_permitted',cancellation_wins)
    with pytest.raises(MissionError,match='MISSION_TERMINAL'):
        await stage(svc,m)
    assert await svc.activities(m.mission_id)==[]


@pytest.mark.asyncio
async def test_activity_http_producer_preserves_dependency_and_verification_contracts(tmp_path):
    from van_gateway.config import Settings
    svc,m=await service(tmp_path);a=await stage(svc,m)
    api=MissionApi(svc.store,Settings(internal_control_token='mission-test-control'),missions=svc,registry=None,router=None)
    app=FastAPI();app.include_router(api.router)
    body={'activity_type':'stage','capability_id':'research','executor':'HERMES',
        'dependency_activity_ids':[a.activity_id],'retry_policy':'RECONCILE_FIRST',
        'verification_contract':{'readback':'provider://actual'}}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
        assert (await c.post(f'/v1/missions/{m.mission_id}/activities',json=body)).status_code==403
        r=await c.post(f'/v1/missions/{m.mission_id}/activities',json=body,headers={'X-Van-Internal-Token':'mission-test-control'})
        assert r.status_code==200,r.text
        row=r.json();assert row['dependency_activity_ids']==[a.activity_id]
        assert row['retry_policy']==body['retry_policy'] and row['verification_contract']==body['verification_contract']
        assert (await c.post(f'/v1/missions/{m.mission_id}/activities',json={**body,'layout_grants_authority':True},headers={'X-Van-Internal-Token':'mission-test-control'})).status_code==422
    stored=(await svc.activities(m.mission_id))[-1]
    assert stored.dependency_activity_ids==[a.activity_id]


@pytest.mark.asyncio
async def test_graph_endpoint_reads_persisted_stages_evidence_and_cycles_without_mutating(tmp_path):
    svc,m=await service(tmp_path);a=await stage(svc,m);b=await stage(svc,m,dependency_activity_ids=[a.activity_id])
    await svc.record_event(mission_id=m.mission_id,activity_id=b.activity_id,
        event_type=MissionEventType.ACTIVITY_CHECKPOINTED,actor=PrincipalType.SYSTEM,
        summary='Observed stage',evidence_ref='stage://original')
    await svc.record_event(mission_id=m.mission_id,activity_id=b.activity_id,
        event_type=MissionEventType.ACTIVITY_CHECKPOINTED,actor=PrincipalType.SYSTEM,
        summary='Internal',evidence_ref='internal://hidden',owner_visibility=False)
    # Historical corruption stays visible; layout/readback does not repair or run it.
    await svc.store.execute('UPDATE mission_activities SET dependency_activity_ids_json=? WHERE activity_id=?',
        (svc.store.dumps([b.activity_id]),a.activity_id))
    before=[dict(r) for r in await svc.store.fetchall('SELECT * FROM mission_activities')]
    app=FastAPI();app.include_router(MissionApi(svc.store,get_settings(),missions=svc,registry=None,router=None).router)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        r=await client.get(f'/v1/missions/{m.mission_id}/graph')
        assert r.status_code==200,r.text
        d=r.json();assert d['critical_path'] is None and d['issues'][0]['code']=='CYCLE'
        n=next(n for n in d['nodes'] if n['node_id']==b.activity_id)
        assert n['evidence_refs']==['stage://original'] and not n['executor_observation_available']
        assert (await client.get('/v1/missions/missing/graph')).status_code==404
    assert [dict(r) for r in await svc.store.fetchall('SELECT * FROM mission_activities')]==before
    assert (await svc.get(m.mission_id)).state==MissionState.CAPTURED


@pytest.mark.asyncio
async def test_graph_observes_one_snapshot_while_another_connection_updates_work(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from van_gateway.storage.db import Store
    svc,m=await service(tmp_path);a=await stage(svc,m)
    original=svc.store.connection;writer=Store(svc.store.path);wrote=False
    @asynccontextmanager
    async def concurrent_connection():
        async with original() as db:
            async def execute(sql,params=()):
                nonlocal wrote
                cursor=await db.execute(sql,params)
                if sql.startswith('SELECT state FROM missions') and not wrote:
                    wrote=True
                    async with writer.connection() as other:
                        await other.execute('BEGIN IMMEDIATE')
                        await other.execute("UPDATE missions SET state='RUNNING' WHERE mission_id=?",(m.mission_id,))
                        await other.execute("UPDATE mission_activities SET state='COMPLETED' WHERE activity_id=?",(a.activity_id,))
                        await other.commit()
                return cursor
            yield SimpleNamespace(execute=execute)
    monkeypatch.setattr(svc.store,'connection',concurrent_connection)
    graph=await svc.dependency_graph(m.mission_id)
    assert wrote and graph.mission_state==MissionState.CAPTURED
    assert graph.nodes[0].state==ActivityState.PENDING
    assert (await writer.fetchone('SELECT state FROM missions WHERE mission_id=?',(m.mission_id,)))['state']=='RUNNING'
    assert (await writer.fetchone('SELECT state FROM mission_activities WHERE activity_id=?',(a.activity_id,)))['state']=='COMPLETED'


@pytest.mark.asyncio
async def test_corrupt_historical_dependencies_are_unavailable_not_an_empty_plan(tmp_path):
    svc,m=await service(tmp_path);a=await stage(svc,m)
    await svc.store.execute('UPDATE mission_activities SET dependency_activity_ids_json=? WHERE activity_id=?',('{invalid',a.activity_id))
    app=FastAPI();app.include_router(MissionApi(svc.store,get_settings(),missions=svc,registry=None,router=None).router)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
        r=await c.get(f'/v1/missions/{m.mission_id}/graph')
        assert r.status_code==503 and r.json()['detail']['error']=='MISSION_GRAPH_SOURCE_INVALID'
