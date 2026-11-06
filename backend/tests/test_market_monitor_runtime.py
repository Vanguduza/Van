"""Real Store/EventBus/Attention integration and fault recovery; fixture sources are not live proof."""
from contextlib import asynccontextmanager
import json
import pytest
from van_gateway.events.bus import EventBus
from van_gateway.storage.db import Store
from van_gateway.attention.engine import AttentionEngine
from van_gateway.trading.monitor_service import MarketMonitorService, MonitorError
from van_gateway.trading.monitor_models import MonitorControl, ScreenRequest
from test_market_monitor_persistence import service, create_alert, instrument, alert, Source
from test_market_monitor_measurements import snapshot, news

pytestmark = pytest.mark.asyncio


async def test_one_canonical_trigger_survives_service_restart_and_explicit_rearm_is_distinct(tmp_path):
    source = Source()
    source.snapshot = snapshot([11])
    s = await service(tmp_path, source=source)
    saved = await create_alert(s)
    assert (await s.run())['triggered'] == 1
    first = await s.get('owner', 'ALERT', saved.object_id)
    assert first.lifecycle == 'TRIGGERED' and first.evaluation.event_id
    restarted = MarketMonitorService(Store(s.store.path), source, clock=lambda: 1000000)
    assert (await restarted.run())['triggered'] == 0
    rows = await s.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")
    assert len(rows) == 1 and rows[0]['event_id'] == first.evaluation.event_id
    payload = json.loads(rows[0]['payload_json'])
    assert payload['authority_effect'] == 'NONE' and payload['source_available_at_ms'] == 960100
    assert payload['triggered_at_ms'] == rows[0]['occurred_at_ms'] == 1000000
    assert 'Private owner rule' not in rows[0]['payload_json']
    await restarted.write('owner', 'ALERT', 'RESTART',
        MonitorControl(request_id='explicit-rearm', expected_revision=1), saved.object_id)
    assert (await restarted.run())['triggered'] == 1
    second = await restarted.get('owner', 'ALERT', saved.object_id)
    assert second.arm_generation == 2 and second.evaluation.event_id != first.evaluation.event_id
    assert len(await s.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")) == 2
    assert not await s.store.fetchall('SELECT * FROM mission_activities')


async def test_event_alert_state_and_projection_witness_have_one_sqlite_rollback_boundary(tmp_path):
    source = Source()
    source.snapshot = snapshot([11])
    s = await service(tmp_path, source=source)
    saved = await create_alert(s)
    class FailAfterInsert(EventBus):
        async def publish_in_transaction(self, *a, **kw):
            await super().publish_in_transaction(*a, **kw)
            raise OSError('injected loss before commit')
    s.events = FailAfterInsert(s.store)
    with pytest.raises(OSError, match='injected loss'):
        await s.run()
    assert (await s.get('owner', 'ALERT', saved.object_id)).lifecycle == 'ACTIVE'
    assert not await s.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")
    assert not await s.store.fetchall('SELECT * FROM market_monitor_publications')
    s.events = EventBus(s.store)
    assert (await s.run())['triggered'] == 1
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_publications')) == 1


async def test_delayed_evaluation_is_rechecked_after_write_lock_before_publication(tmp_path):
    clock = [1000000]
    source = Source()
    source.snapshot = snapshot([11])
    s = await service(tmp_path, source=source, clock=lambda: clock[0])
    saved = await create_alert(s)
    original = s._apply
    async def delayed(*a):
        clock[0] = 1200000
        return await original(*a)
    s._apply = delayed
    assert (await s.run())['triggered'] == 0
    view = await s.get('owner', 'ALERT', saved.object_id)
    assert view.lifecycle == 'ACTIVE' and view.evaluation.reason == 'OBSERVATION_EXPIRED_BEFORE_PUBLICATION'
    assert not await s.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")


async def test_competing_evaluators_cannot_overwrite_a_newer_baseline_or_emit_from_a_stale_view(tmp_path):
    source = Source()
    clock = [1000000]
    s = await service(tmp_path, source=source, clock=lambda: clock[0])
    saved = await create_alert(s, state=alert(condition={'kind':'PRICE','comparator':'CROSS_ABOVE','threshold':'10'}))
    first = await s.get('owner', 'ALERT', saved.object_id)
    competing = await s.get('owner', 'ALERT', saved.object_id)
    baseline, fire = s._technical(first, snapshot([9]), clock[0])
    assert not fire
    assert not await s._apply('owner', first, baseline, fire)
    clock[0] = 1040000
    late, fire = s._technical(competing, snapshot([11], end_ms=1020000), clock[0])
    assert not fire and not await s._apply('owner', competing, late, fire)
    observed = await s.get('owner', 'ALERT', saved.object_id)
    assert observed.evaluation.value == '9' and observed.evaluation.event_time_ms == 960000
    source.snapshot = snapshot([11], end_ms=1020000)
    assert (await s.run())['triggered'] == 1


async def test_committed_original_write_is_recovered_after_its_commit_acknowledgement_is_lost(tmp_path):
    class AckLoss(Store):
        armed = False
        @asynccontextmanager
        async def connection(self):
            async with super().connection() as db:
                original = db.commit
                async def commit():
                    await original()
                    if self.armed:
                        self.armed = False
                        raise OSError('commit applied, acknowledgement lost')
                db.commit = commit
                yield db
    store = AckLoss(str(tmp_path/'lost-ack.sqlite3'))
    await store.migrate()
    s = MarketMonitorService(store, Source(), clock=lambda: 1000000)
    store.armed = True
    original = await create_alert(s)
    assert original == await create_alert(s)
    assert len(await store.fetchall('SELECT * FROM market_monitor_objects')) == 1
    assert len(await store.fetchall('SELECT * FROM market_monitor_operations')) == 1


async def test_attention_projection_recovers_after_lost_ack_and_rule_deletion_without_reopening_acknowledged_item(tmp_path):
    source = Source()
    source.snapshot = snapshot([11])
    s = await service(tmp_path, source=source)
    engine = AttentionEngine(s.store)
    class LostAttentionAck:
        async def upsert(self, **kw):
            await engine.upsert(**kw)
            raise OSError('attention applied, acknowledgement lost')
    s.attention = LostAttentionAck()
    saved = await create_alert(s)
    with pytest.raises(OSError, match='attention applied'):
        await s.run()
    rows = await s.store.fetchall("SELECT * FROM attention WHERE source='trading.monitor'")
    assert len(rows) == 1
    await engine.acknowledge(rows[0]['id'])
    await s.write('owner', 'ALERT', 'DELETE',
        MonitorControl(request_id='delete-after-trigger', expected_revision=1), saved.object_id)
    restarted = MarketMonitorService(Store(s.store.path), source, attention=engine, clock=lambda: 1000000)
    assert (await restarted.run())['attention_projected'] == 1
    rows = await s.store.fetchall("SELECT * FROM attention WHERE source='trading.monitor'")
    assert len(rows) == 1 and rows[0]['state'] == 'ACKNOWLEDGED'
    assert (await s.store.fetchone('SELECT projected FROM market_monitor_publications'))['projected'] == 1


async def test_scan_quota_is_atomic_and_survives_service_restart_and_clock_rollback(tmp_path):
    source = Source()
    source.snapshot = snapshot([11])
    s = await service(tmp_path, source=source)
    body = ScreenRequest.model_validate({'instruments':[instrument()],
        'conditions':[{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'10'}]})
    from van_gateway.trading.monitor_models import MonitorCapabilities
    s.capabilities = lambda: MonitorCapabilities(scan_instruments_per_minute=1)
    result = await s.screen('owner', body)
    assert result.rows[0].state == 'MATCH' and result.rows[0].price_age_ms == 40000
    other = MarketMonitorService(Store(s.store.path), source, clock=lambda: 1000000)
    other.capabilities = s.capabilities
    with pytest.raises(MonitorError, match='MONITOR_SCAN_QUOTA_REACHED'):
        await other.screen('owner', body)
    other.clock = lambda: 900000
    with pytest.raises(MonitorError, match='MONITOR_SCAN_CLOCK_ROLLBACK'):
        await other.screen('owner', body)
    other.clock = lambda: 1020000
    assert (await other.screen('owner', body)).rows[0].state == 'MATCH'


async def test_news_uses_existing_native_ledger_records_with_source_and_availability(tmp_path):
    from van_gateway.trading.monitor_source import LedgerMonitorSource
    from van_gateway.trading.service import TradingService
    from vati.core.events import make_event, EventKind
    from vati.core.ledger import Ledger
    path = tmp_path/'vati.sqlite3'
    ledger = Ledger(str(path))
    event = make_event(EventKind.NEWS_HEADLINE, 'fixture-news-ingress',
        {'source_id':'fixture-primary','trust':'T1_PRIMARY','title':'Gold export rules announced',
         'symbols':['SAME'],'body_excerpt':'Observed publisher statement'},
        event_time_ms=1000000, received_time_ms=1000100, correlation_id='fixture-headline')
    ledger.append(event)
    ledger.close()
    source = LedgerMonitorSource(TradingService(str(path)))
    s = await service(tmp_path, source=source, clock=lambda: 1000200)
    state = alert(condition={'kind':'NEWS','keywords':['gold export'],'minimum_trust':'T1_PRIMARY'})
    saved = await create_alert(s, state=state)
    # The alert was armed after the first headline: old stories cannot become new triggers.
    assert (await s.run())['triggered'] == 0
    ledger = Ledger(str(path))
    fresh = make_event(EventKind.NEWS_HEADLINE, 'fixture-news-ingress',
        {'source_id':'fixture-primary','trust':'T1_PRIMARY','title':'Gold export new rules published',
         'symbols':['SAME']}, event_time_ms=1000300, received_time_ms=1000400, correlation_id='new-headline')
    ledger.append(fresh)
    ledger.close()
    s.clock = lambda: 1000500
    assert (await s.run())['triggered'] == 1
    observed = await s.get('owner','ALERT',saved.object_id)
    assert observed.evaluation.sample_id == fresh.hash and observed.evaluation.available_at_ms == 1000400


async def test_clock_rollback_cannot_publish_before_rule_arm_or_clear_its_durable_high_water(tmp_path):
    clock = [1000000]
    source = Source()
    source.snapshot = snapshot([9], end_ms=900000)
    s = await service(tmp_path, source=source, clock=lambda: clock[0])
    saved = await create_alert(s)
    assert (await s.run())['triggered'] == 0
    first = await s.get('owner', 'ALERT', saved.object_id)
    assert first.evaluation.clock_high_water_ms == 1000000
    source.snapshot = snapshot([11], end_ms=960000)
    for now in [990000, 995000]:
        clock[0] = now
        assert (await s.run())['triggered'] == 0
        observed = await s.get('owner', 'ALERT', saved.object_id)
        assert observed.evaluation.reason == 'MONITOR_CLOCK_MOVED_BACKWARDS'
        assert observed.evaluation.clock_high_water_ms == 1000000
    assert not await s.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")
    clock[0] = 1010000
    assert (await s.run())['triggered'] == 1


async def test_configuration_edit_cannot_reset_the_clock_fence_to_a_rolled_back_instant(tmp_path):
    clock = [1000000]
    s = await service(tmp_path, clock=lambda: clock[0])
    saved = await create_alert(s)
    clock[0] = 900000
    with pytest.raises(MonitorError, match='MONITOR_CLOCK_UNAVAILABLE'):
        await s.write('owner', 'ALERT', 'RESTART',
            MonitorControl(request_id='backwards-restart', expected_revision=1), saved.object_id)
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_operations')) == 1
    view = await s.get('owner', 'ALERT', saved.object_id)
    assert view.arm_generation == 1 and view.armed_at_ms == 1000000
