"""Actual owner HTTP boundary, event replay and bound-device proof for monitor controls."""
import json
import pytest
from conftest_market_monitors import isolate_native_backgrounds
from test_local_typed_actions import client, _settings, _pair_for_test
from van_gateway.trading.monitor_source import LedgerMonitorSource
from test_market_monitor_persistence import instrument, Source
from test_market_monitor_measurements import snapshot

PREFIX = '/v1/trading/monitors'
pytestmark = pytest.mark.asyncio


async def test_paired_owner_can_recover_list_mutations_and_privacy_inventory_without_dispatch(client):
    ac, app, hermes = client
    assert (await ac.get(PREFIX+'/capabilities')).status_code == 401
    await _pair_for_test(ac, app, 'dev-monitor-owner', 'fixture-monitor-secret')
    cap = await ac.get(PREFIX+'/capabilities')
    assert cap.status_code == 200 and cap.json()['authority_effect'] == 'NONE'
    assert cap.json()['technical_source_binding'] == 'UNAVAILABLE_BAR_LAKE_HAS_NO_FULL_NATIVE_IDENTITY'
    state = {'name':'Owner list','entries':[{'instrument':instrument(),'favourite':True}],
             'sort_by':'SPREAD','descending':True}
    created = await ac.post(PREFIX+'/watchlists', json={'request_id':'create','state':state})
    assert created.status_code == 200, created.text
    identity = created.json()['object_id']
    get = await ac.get(PREFIX+'/watchlists/'+identity)
    assert get.status_code == 200 and get.json()['state']['entries'][0]['instrument'] == instrument()
    assert get.headers['cache-control'] == 'no-store'
    stale = await ac.request('DELETE',PREFIX+'/watchlists/'+identity,
        json={'request_id':'stale','expected_revision':2})
    assert stale.status_code == 409 and stale.json()['detail'] == {
        'code':'MONITOR_REVISION_CONFLICT','current_revision':1}
    deleted = await ac.request('DELETE',PREFIX+'/watchlists/'+identity,
        json={'request_id':'delete','expected_revision':1})
    assert deleted.status_code == 200 and deleted.json()['status'] == 'DELETED'
    assert (await ac.get(PREFIX+'/operations/create')).json() == created.json()
    assert (await ac.post(PREFIX+'/watchlists',json={'request_id':'create','state':state})).json() == created.json()
    assert (await ac.get(PREFIX+'/watchlists/'+identity)).status_code == 404
    inventory = await ac.get('/v1/context/memory')
    assert inventory.status_code == 200 and 'market_monitors' in inventory.json()['kept_deliberately']
    assert hermes['create_run'] == 0
    assert not await app.state.store.fetchall('SELECT * FROM mission_activities')


async def test_monitor_event_has_one_identity_on_both_paired_devices_and_survives_replay(client):
    ac, app, hermes = client
    await _pair_for_test(ac,app,'dev-monitor-one','fixture-monitor-one')
    first_token = ac.headers['X-Van-Device-Token']
    monitors = app.state.market_monitors
    source = Source()
    source.snapshot = snapshot([11])
    monitors.source = source
    monitors.clock = lambda: 1000000
    created = await ac.post(PREFIX+'/alerts',json={'request_id':'event-alert','state':{
        'name':'Owner private condition','instrument':instrument(),
        'condition':{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'10'}}})
    assert created.status_code == 200,created.text
    await app.state.scheduler.jobs["trading.market_monitors"].run()
    await _pair_for_test(ac,app,'dev-monitor-two','fixture-monitor-two')
    second_token = ac.headers['X-Van-Device-Token']
    observed = []
    for device, token in [('dev-monitor-one',first_token),('dev-monitor-two',second_token)]:
        result = await ac.get('/v1/events',params={'device_id':device,'after_seq':0},
                              headers={'X-Van-Device-Token':token})
        assert result.status_code == 200,result.text
        rows = [r for r in result.json()['events'] if r['event_type']=='trading.alert.triggered']
        assert len(rows) == 1
        observed.append(rows[0])
    assert observed[0]['event_id'] == observed[1]['event_id']
    assert observed[0]['seq'] == observed[1]['seq']
    await app.state.scheduler.jobs["trading.market_monitors"].run()
    assert len(await app.state.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")) == 1
    assert hermes['create_run'] == 0


async def test_unqualified_technical_alert_and_scan_are_explicitly_unavailable_and_never_dispatch(client):
    ac, app, hermes = client
    await _pair_for_test(ac,app,'dev-monitor-hold','fixture-monitor-hold')
    state = {'name':'Waiting for source binding','instrument':instrument(),
             'condition':{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'0'}}
    created = await ac.post(PREFIX+'/alerts',json={'request_id':'held','state':state})
    assert created.status_code == 200, created.text
    await app.state.scheduler.jobs["trading.market_monitors"].run()
    actual = await ac.get(PREFIX+'/alerts/'+created.json()['object_id'])
    assert actual.json()['lifecycle'] == 'ACTIVE'
    assert actual.json()['evaluation']['state'] == 'UNAVAILABLE'
    scan = await ac.post(PREFIX+'/screen',json={'instruments':[instrument()],
        'conditions':[{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'0'}]})
    assert scan.status_code == 200 and scan.json()['rows'][0]['state'] == 'UNAVAILABLE'
    assert scan.json()['rows'][0]['price_age_ms'] is None
    bad = await ac.post(PREFIX+'/alerts',json={'request_id':'bad','state':state|{'place_order':True}})
    assert bad.status_code == 422 and bad.headers['cache-control'] == 'no-store'
    assert not await app.state.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")
    assert hermes['create_run'] == 0
