"""Saved screen rules: real persistence, exact run snapshots and transactional migration recovery."""
import json
import sqlite3
import pytest
from van_gateway.storage.db import Store
from van_gateway.trading.monitor_models import (ScreenRuleState, CreateScreenRule,
    ReplaceScreenRule, RunScreenRule, MonitorControl, MonitorCapabilities)
from van_gateway.trading.monitor_service import MarketMonitorService, MonitorError
from test_market_monitor_persistence import (Source, instrument, service, create, create_alert)
from test_market_monitor_measurements import snapshot

pytestmark = pytest.mark.asyncio


def state(name='Owner screen', threshold='10'):
    return ScreenRuleState.model_validate({'name':name,'instruments':[instrument()],
        'timeframe':'M1','conditions':[{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':threshold}]})


async def create_rule(s, request='screen-create', owner='owner', config=None):
    return await s.write(owner,'SCREEN_RULE','CREATE',
        CreateScreenRule(request_id=request,state=config or state()))


async def test_saved_rule_exact_settings_and_original_receipt_survive_restart_edit_and_deletion(tmp_path):
    s = await service(tmp_path)
    original = await create_rule(s)
    restarted = MarketMonitorService(Store(s.store.path), Source(), clock=lambda:1000000)
    actual = await restarted.get('owner','SCREEN_RULE',original.object_id)
    assert actual.state == state() and actual.authority_effect == 'NONE'
    assert actual.kind == 'SCREEN_RULE'
    edit = await restarted.write('owner','SCREEN_RULE','REPLACE',
        ReplaceScreenRule(request_id='edit',expected_revision=1,state=state('Changed','12')), original.object_id)
    assert edit.revision == 2
    assert await create_rule(restarted) == original
    assert (await restarted.listing('owner','SCREEN_RULE')).total_count == 1
    deleted = await restarted.write('owner','SCREEN_RULE','DELETE',
        MonitorControl(request_id='delete',expected_revision=2), original.object_id)
    assert deleted.status == 'DELETED' and await create_rule(restarted) == original
    assert await restarted.operation('owner','screen-create') == original
    assert (await restarted.listing('owner','SCREEN_RULE')).items == []
    body = json.dumps([dict(r) for r in await s.store.fetchall('SELECT * FROM market_monitor_operations')])
    assert 'Changed' not in body and 'Owner screen' not in body


async def test_rule_owner_target_payload_and_revision_are_checked_before_data_read_or_quota(tmp_path):
    s = await service(tmp_path)
    saved = await create_rule(s)
    with pytest.raises(MonitorError,match='MONITOR_OPERATION_SCOPE_CONFLICT'):
        await create_rule(s,config=state(threshold='11'))
    with pytest.raises(MonitorError,match='MONITOR_REVISION_CONFLICT'):
        await s.run_screen_rule('owner',saved.object_id,RunScreenRule(expected_revision=2))
    with pytest.raises(MonitorError,match='MONITOR_OBJECT_UNKNOWN'):
        await s.run_screen_rule('foreign-owner',saved.object_id,RunScreenRule(expected_revision=1))
    assert not await s.store.fetchall('SELECT * FROM market_monitor_scan_budget')
    with pytest.raises(MonitorError,match='MONITOR_INVALID_OPERATION'):
        await s.write('owner','SCREEN_RULE','PAUSE',
            MonitorControl(request_id='invalid-pause',expected_revision=1),saved.object_id)
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_operations')) == 1


async def test_run_is_bound_to_saved_revision_and_charges_the_existing_durable_scan_quota(tmp_path):
    source = Source()
    source.snapshot = snapshot([11])
    s = await service(tmp_path,source=source)
    s.capabilities = lambda:MonitorCapabilities(scan_instruments_per_minute=1)
    saved = await create_rule(s)
    result = await s.run_screen_rule('owner',saved.object_id,RunScreenRule(expected_revision=1))
    assert result.rows[0].state == 'MATCH' and result.rows[0].values == ['11']
    assert result.saved_rule.object_id == saved.object_id and result.saved_rule.revision == 1
    assert result.saved_rule.state_sha256 == saved.state_sha256 and result.authority_effect == 'NONE'
    other = MarketMonitorService(Store(s.store.path),source,clock=lambda:1000000)
    other.capabilities = s.capabilities
    with pytest.raises(MonitorError,match='MONITOR_SCAN_QUOTA_REACHED'):
        await other.run_screen_rule('owner',saved.object_id,RunScreenRule(expected_revision=1))
    assert not await s.store.fetchall('SELECT * FROM mission_activities')
    assert not await s.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")


async def test_concurrent_rule_edit_does_not_relabel_a_captured_scan_as_the_newer_rule(tmp_path):
    source = Source()
    source.snapshot = snapshot([11])
    s = await service(tmp_path,source=source)
    original = await create_rule(s)
    native_screen = s.screen
    async def interleaved(owner, body):
        await s.write(owner,'SCREEN_RULE','REPLACE',
            ReplaceScreenRule(request_id='concurrent-edit',expected_revision=1,state=state('New','999')),
            original.object_id)
        return await native_screen(owner,body)
    s.screen = interleaved
    result = await s.run_screen_rule('owner',original.object_id,RunScreenRule(expected_revision=1))
    assert result.rows[0].state == 'MATCH'
    assert result.saved_rule.revision == 1 and result.saved_rule.state_sha256 == original.state_sha256
    current = await s.get('owner','SCREEN_RULE',original.object_id)
    assert current.revision == 2 and current.state.conditions[0].threshold == '999'


async def test_screen_rule_capacity_does_not_consume_watchlist_capacity_or_prevent_deletion(tmp_path):
    s = await service(tmp_path)
    s.capabilities = lambda:MonitorCapabilities(max_screen_rules=1,max_watchlists=1)
    saved = await create_rule(s)
    with pytest.raises(MonitorError,match='MONITOR_OBJECT_CAPACITY_REACHED'):
        await create_rule(s,request='over-capacity')
    assert (await create(s)).kind == 'WATCHLIST'
    await s.write('owner','SCREEN_RULE','DELETE',
        MonitorControl(request_id='delete',expected_revision=1),saved.object_id)
    assert (await create_rule(s,request='new-original')).kind == 'SCREEN_RULE'


async def build_version58(tmp_path,monkeypatch):
    import van_gateway.storage.db as module
    store = Store(str(tmp_path/'old58.sqlite3'))
    with monkeypatch.context() as patch:
        patch.setattr(module,'MIGRATIONS',{v:script for v,script in module.MIGRATIONS.items() if v <= 58})
        await store.migrate()
    s = MarketMonitorService(store,Source(),clock=lambda:1000000)
    old_list, old_alert = await create(s), await create_alert(s)
    before = [dict(r) for r in await store.fetchall('SELECT * FROM market_monitor_objects ORDER BY object_id')]
    return s,old_list,old_alert,before


async def test_actual58_to59_migration_preserves_state_originals_and_replays_a_lost_version_marker(tmp_path,monkeypatch):
    s,old_list,old_alert,before = await build_version58(tmp_path,monkeypatch)
    await s.store.migrate()
    assert [dict(r) for r in await s.store.fetchall('SELECT * FROM market_monitor_objects ORDER BY object_id')] == before
    assert await s.operation('owner','create') == old_list
    assert await s.operation('owner','alert-create') == old_alert
    saved = await create_rule(s)
    all_rows = [dict(r) for r in await s.store.fetchall('SELECT * FROM market_monitor_objects ORDER BY object_id')]
    # Model interruption after the migration transaction committed, before its marker persisted.
    await s.store.execute('DELETE FROM schema_migrations WHERE version=59')
    await s.store.migrate()
    assert [dict(r) for r in await s.store.fetchall('SELECT * FROM market_monitor_objects ORDER BY object_id')] == all_rows
    assert (await s.get('owner','SCREEN_RULE',saved.object_id)).state == state()
    assert not await s.store.fetchall('PRAGMA foreign_key_check')
    indexes = await s.store.fetchall("PRAGMA index_list('market_monitor_objects')")
    assert sum(r['name']=='market_monitor_active' for r in indexes) == 1
    assert not await s.store.fetchall("SELECT name FROM sqlite_master WHERE name='market_monitor_objects_v58'")


async def test_failed_table_rebuild_rolls_back_without_losing_existing_rules_and_next_boot_recovers(tmp_path,monkeypatch):
    import van_gateway.storage.db as module
    s,old_list,old_alert,before = await build_version58(tmp_path,monkeypatch)
    script = module.MIGRATIONS[59]
    boundary = 'DROP TABLE market_monitor_objects_v58;'
    assert script.count(boundary) == 1
    broken = script.replace(boundary,'SELECT * FROM injected_missing_table;\n'+boundary)
    with monkeypatch.context() as patch:
        patch.setattr(module,'MIGRATIONS',{**module.MIGRATIONS,59:broken})
        with pytest.raises(sqlite3.OperationalError,match='injected_missing_table'):
            await s.store.migrate()
    assert [dict(r) for r in await s.store.fetchall('SELECT * FROM market_monitor_objects ORDER BY object_id')] == before
    assert (await s.store.fetchone('SELECT MAX(version) n FROM schema_migrations'))['n'] == 58
    assert not await s.store.fetchall("SELECT name FROM sqlite_master WHERE name='market_monitor_objects_v58'")
    await s.store.migrate()
    assert await s.operation('owner','create') == old_list
    assert await s.operation('owner','alert-create') == old_alert
    assert (await create_rule(s)).status == 'SAVED'
