"""Actual SQLite controls, replay, isolation and migration for owner market monitors."""
import json
import sqlite3
from types import SimpleNamespace
import pytest
from van_gateway.storage.db import Store
from van_gateway.trading.monitor_models import (WatchlistState, CreateWatchlist, ReplaceWatchlist,
    AlertState, CreateAlert, MonitorControl, MonitorCapabilities)
from van_gateway.trading.monitor_service import MarketMonitorService, MonitorError


class Source:
    snapshot = None
    headlines = ()
    available = True

    def market(self, instrument, timeframe):
        return self.snapshot

    def news(self):
        return self.available, list(self.headlines)


def instrument(**changes):
    return {**dict(venue='fixture-venue', environment='DEMO', api_family='spot',
                product_id='native-product', symbol='SAME', account_id='account-one',
                contract_revision='contract-one'), **changes}


def watch(name='Owner list', **changes):
    return WatchlistState.model_validate({'name': name, 'entries': [{'instrument': instrument()}], **changes})


def alert(**changes):
    return AlertState.model_validate({'name': 'Private owner rule', 'instrument': instrument(),
        'condition': {'kind': 'PRICE', 'comparator': 'AT_OR_ABOVE', 'threshold': '10.0000000000000000001'},
        **changes})


async def service(tmp_path, **kwargs):
    store = Store(str(tmp_path/'monitors.sqlite3'))
    await store.migrate()
    return MarketMonitorService(store, kwargs.pop('source', Source()), clock=kwargs.pop('clock', lambda: 1000000), **kwargs)


async def create(s, request='create', owner='owner', state=None):
    return await s.write(owner, 'WATCHLIST', 'CREATE', CreateWatchlist(request_id=request, state=state or watch()))


async def create_alert(s, request='alert-create', state=None):
    return await s.write('owner', 'ALERT', 'CREATE', CreateAlert(request_id=request, state=state or alert()))


@pytest.mark.asyncio
async def test_exact_native_identity_preferences_and_favourites_survive_restart(tmp_path):
    s = await service(tmp_path)
    state = watch(sort_by='SPREAD', descending=True, favourites_only=True)
    state.entries[0].favourite = True
    saved = await create(s, state=state)
    restarted = MarketMonitorService(Store(s.store.path), Source())
    actual = await restarted.get('owner', 'WATCHLIST', saved.object_id)
    assert actual.state == state and actual.state_sha256 == saved.state_sha256
    assert actual.authority_effect == 'NONE'
    assert actual.instrument_binding == 'OWNER_SELECTION_NOT_NATIVE_VERIFIED'


@pytest.mark.asyncio
async def test_original_receipt_survives_edit_delete_and_lost_response_retry_without_resurrection(tmp_path):
    s = await service(tmp_path)
    original = await create(s)
    edited = await s.write('owner', 'WATCHLIST', 'REPLACE',
        ReplaceWatchlist(request_id='edit', expected_revision=1, state=watch('Changed')), original.object_id)
    assert edited.revision == 2
    deleted = await s.write('owner', 'WATCHLIST', 'DELETE',
        MonitorControl(request_id='delete', expected_revision=2), original.object_id)
    assert deleted.status == 'DELETED' and await create(s) == original
    assert await s.operation('owner', 'create') == original
    assert not await s.store.fetchall('SELECT * FROM market_monitor_objects')
    assert 'Private owner' not in json.dumps([dict(r) for r in await s.store.fetchall('SELECT * FROM market_monitor_operations')])
    with pytest.raises(MonitorError, match='MONITOR_OBJECT_UNKNOWN'):
        await s.get('owner', 'WATCHLIST', original.object_id)


@pytest.mark.asyncio
async def test_request_identity_is_bound_to_payload_kind_target_and_operation(tmp_path):
    s = await service(tmp_path)
    saved = await create(s)
    for owner_kind, operation, body, identity in [
        ('WATCHLIST', 'CREATE', CreateWatchlist(request_id='create', state=watch('Changed')), None),
        ('ALERT', 'CREATE', CreateAlert(request_id='create', state=alert()), None),
        ('WATCHLIST', 'DELETE', MonitorControl(request_id='create', expected_revision=1), saved.object_id),
    ]:
        with pytest.raises(MonitorError, match='MONITOR_OPERATION_SCOPE_CONFLICT'):
            await s.write('owner', owner_kind, operation, body, identity)
    assert (await s.get('owner', 'WATCHLIST', saved.object_id)).revision == 1


@pytest.mark.asyncio
async def test_stale_cas_and_foreign_owner_cannot_change_or_read_rule_or_receipt(tmp_path):
    s = await service(tmp_path)
    saved = await create(s)
    with pytest.raises(MonitorError, match='MONITOR_REVISION_CONFLICT'):
        await s.write('owner', 'WATCHLIST', 'DELETE',
            MonitorControl(request_id='stale', expected_revision=2), saved.object_id)
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_operations')) == 1
    for operation in [s.get('other-owner', 'WATCHLIST', saved.object_id),
                      s.operation('other-owner', 'create')]:
        with pytest.raises(MonitorError) as error:
            await operation
        assert error.value.status == 404
    assert (await s.listing('other-owner', 'WATCHLIST')).items == []


@pytest.mark.asyncio
async def test_pause_and_explicit_restart_are_revision_checked_and_rearm_once(tmp_path):
    s = await service(tmp_path)
    saved = await create_alert(s)
    paused = await s.write('owner', 'ALERT', 'PAUSE',
        MonitorControl(request_id='pause', expected_revision=1), saved.object_id)
    view = await s.get('owner', 'ALERT', saved.object_id)
    assert view.lifecycle == 'PAUSED' and view.arm_generation == 1
    assert (await s.run())['evaluated'] == 0
    body = MonitorControl(request_id='restart', expected_revision=paused.revision)
    restarted = await s.write('owner', 'ALERT', 'RESTART', body, saved.object_id)
    assert restarted.status == 'RESTARTED'
    assert await s.write('owner', 'ALERT', 'RESTART', body, saved.object_id) == restarted
    view = await s.get('owner', 'ALERT', saved.object_id)
    assert view.lifecycle == 'ACTIVE' and view.arm_generation == 2 and view.evaluation is None


@pytest.mark.asyncio
async def test_pagination_is_stable_owner_scoped_and_checks_cursor_scope(tmp_path):
    s = await service(tmp_path)
    ids = sorted([(await create(s, request='row-'+str(n))).object_id for n in range(3)])
    page = await s.listing('owner', 'WATCHLIST', limit=2)
    assert [i.object_id for i in page.items] == ids[:2] and page.total_count == 3
    assert page.next_after_id == ids[1]
    tail = await s.listing('owner', 'WATCHLIST', limit=2, after_id=page.next_after_id)
    assert [i.object_id for i in tail.items] == ids[2:] and tail.next_after_id is None
    with pytest.raises(MonitorError, match='MONITOR_OBJECT_UNKNOWN'):
        await s.listing('other-owner', 'WATCHLIST', after_id=ids[0])


@pytest.mark.asyncio
async def test_corrupt_saved_state_is_explicit_unavailable_not_a_healthy_empty_list(tmp_path):
    s = await service(tmp_path)
    saved = await create(s)
    await s.store.execute('UPDATE market_monitor_objects SET state_json=? WHERE object_id=?',
                          ('{"name":"tampered"}', saved.object_id))
    with pytest.raises(MonitorError, match='MONITOR_STATE_INTEGRITY_FAILED') as error:
        await s.get('owner', 'WATCHLIST', saved.object_id)
    assert error.value.status == 503


@pytest.mark.asyncio
async def test_capacity_and_invalid_clock_do_not_create_partial_objects_or_receipts(tmp_path, monkeypatch):
    s = await service(tmp_path)
    monkeypatch.setattr(s, 'capabilities', lambda: MonitorCapabilities(max_watchlists=1))
    await create(s)
    with pytest.raises(MonitorError, match='MONITOR_OBJECT_CAPACITY_REACHED'):
        await create(s, request='over-capacity')
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_objects')) == 1
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_operations')) == 1
    s.clock = lambda: True
    with pytest.raises(MonitorError, match='MONITOR_CLOCK_UNAVAILABLE'):
        await create_alert(s)
    assert not await s.store.fetchall("SELECT * FROM market_monitor_objects WHERE kind='ALERT'")


@pytest.mark.asyncio
async def test_schema57_upgrade_keeps_existing_chart_and_adds_monitor_tables(tmp_path, monkeypatch):
    import van_gateway.storage.db as module
    from van_gateway.trading.chart_models import CreateWorkspace, WorkspaceState
    from van_gateway.trading.chart_workspaces import ChartWorkspaceService
    store = Store(str(tmp_path/'old57.sqlite3'))
    with monkeypatch.context() as patch:
        patch.setattr(module, 'MIGRATIONS', {k: v for k, v in module.MIGRATIONS.items() if k <= 57})
        await store.migrate()
    old = await store.fetchone('SELECT MAX(version) n FROM schema_migrations')
    assert old['n'] == 57
    state = WorkspaceState.model_validate({'name': 'Saved old chart', 'selected_panel_id': 'main',
        'panels': [{'panel_id': 'main', 'instrument': instrument(), 'timeframe': 'H1'}]})
    charts = ChartWorkspaceService(store)
    saved = await charts.create('owner', CreateWorkspace(request_id='old-chart', state=state))
    await store.migrate()
    assert (await charts.get('owner', saved.workspace_id)).state == state
    assert (await store.fetchone('SELECT MAX(version) n FROM schema_migrations'))['n'] == 58
    monitors = MarketMonitorService(store, Source(), clock=lambda: 1000000)
    assert (await create(monitors)).status == 'SAVED'


@pytest.mark.asyncio
async def test_real_backup_and_restore_preserve_lists_alert_arms_and_original_results(tmp_path):
    from van_gateway.ops.backup import create_backup, restore, verify
    s = await service(tmp_path)
    saved, rule = await create(s), await create_alert(s)
    await s.write('owner', 'ALERT', 'PAUSE', MonitorControl(request_id='pause', expected_revision=1), rule.object_id)
    folder = tmp_path/'backup'
    manifest = create_backup(database_path=s.store.path, destination=folder)
    assert manifest.row_counts['market_monitor_objects'] == 2 and verify(folder)['ok']
    path = tmp_path/'recovered.sqlite3'
    restore(folder, database_path=path)
    restored = MarketMonitorService(Store(str(path)), Source())
    assert await restored.operation('owner', 'create') == saved
    assert (await restored.get('owner', 'WATCHLIST', saved.object_id)).state == watch()
    actual = await restored.get('owner', 'ALERT', rule.object_id)
    assert actual.lifecycle == 'PAUSED' and actual.arm_generation == 1
