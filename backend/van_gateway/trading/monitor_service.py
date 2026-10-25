"""Durable owner monitor controls and server evaluation in the existing Store/EventBus."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from decimal import Decimal
from typing import Any
from pydantic import ValidationError

from van_gateway.storage.db import Store
from van_gateway.events.bus import EventBus
from .monitor_models import (AlertState, AlertView, AlertPage, WatchlistState, WatchlistView,
    WatchlistPage, MonitorWrite, MonitorCapabilities, EvaluationStatus, ScreenRow, ScreenResult,
    ScreenRequest, ScreenRuleState, ScreenRuleView, ScreenRulePage, ScreenRuleBinding)
from .monitor_source import MarketSnapshot, NewsObservation, PERIOD_MS
from .monitor_calculations import measurement, matched, text


class MonitorError(ValueError):
    def __init__(self, code: str, status: int = 409, **details):
        super().__init__(code)
        self.code, self.status, self.details = code, status, details


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class MarketMonitorService:
    def __init__(self, store: Store, source, *, events: EventBus | None = None,
                 attention=None, clock=None):
        self.store, self.source = store, source
        self.events = events or EventBus(store)
        self.attention = attention
        self.clock = clock or (lambda: int(time.time()*1000))

    @staticmethod
    def capabilities():
        return MonitorCapabilities()

    def now(self):
        value = self.clock()
        if type(value) is not int or not 0 <= value <= 253402300799000:
            raise MonitorError('MONITOR_CLOCK_UNAVAILABLE', 503)
        return value

    @staticmethod
    def _view(row):
        if hashlib.sha256(row['state_json'].encode()).hexdigest() != row['state_sha256']:
            raise MonitorError('MONITOR_STATE_INTEGRITY_FAILED', 503)
        common = dict(object_id=row['object_id'], revision=row['revision'],
                      state_sha256=row['state_sha256'], updated_at_ms=row['updated_at_ms'])
        try:
            if row['kind'] == 'WATCHLIST':
                return WatchlistView(**common, state=WatchlistState.model_validate_json(row['state_json']))
            if row['kind'] == 'SCREEN_RULE':
                return ScreenRuleView(**common, state=ScreenRuleState.model_validate_json(row['state_json']))
            return AlertView(**common, state=AlertState.model_validate_json(row['state_json']),
                             lifecycle=row['lifecycle'], arm_generation=row['arm_generation'],
                             armed_at_ms=row['armed_at_ms'],
                             evaluation=EvaluationStatus.model_validate_json(row['evaluation_json'])
                             if row['evaluation_json'] else None)
        except (ValidationError, ValueError, TypeError) as exc:
            raise MonitorError('MONITOR_STATE_INTEGRITY_FAILED', 503) from exc

    async def _head(self, db, owner, kind, identity):
        row = await (await db.execute(
            'SELECT * FROM market_monitor_objects WHERE owner_id=? AND kind=? AND object_id=?',
            (owner, kind, identity))).fetchone()
        if row is None:
            raise MonitorError('MONITOR_OBJECT_UNKNOWN', 404)
        return row

    async def get(self, owner, kind, identity):
        async with self.store.connection() as db:
            return self._view(await self._head(db, owner, kind, identity))

    async def listing(self, owner, kind, *, limit=100, after_id=None):
        if type(limit) is not int or not 1 <= limit <= 128:
            raise MonitorError('MONITOR_INVALID_PAGE', 422)
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            if after_id is not None:
                await self._head(db, owner, kind, after_id)
            rows = await (await db.execute(
                'SELECT * FROM market_monitor_objects WHERE owner_id=? AND kind=? AND object_id>? '
                'ORDER BY object_id LIMIT ?', (owner, kind, after_id or '', limit+1))).fetchall()
            count = await (await db.execute(
                'SELECT count(*) n FROM market_monitor_objects WHERE owner_id=? AND kind=?',
                (owner, kind))).fetchone()
            visible = rows[:limit]
            cls = {'WATCHLIST':WatchlistPage, 'ALERT':AlertPage, 'SCREEN_RULE':ScreenRulePage}[kind]
            return cls(items=[self._view(r) for r in visible], total_count=count['n'],
                       next_after_id=visible[-1]['object_id'] if len(rows)>limit else None)

    async def operation(self, owner, request_id):
        row = await self.store.fetchone(
            'SELECT result_json FROM market_monitor_operations WHERE owner_id=? AND request_id=?',
            (owner, request_id))
        if row is None:
            raise MonitorError('MONITOR_OPERATION_UNKNOWN', 404)
        return MonitorWrite.model_validate_json(row['result_json'])

    async def write(self, owner, kind, operation, body, identity=None):
        if kind not in {'WATCHLIST', 'ALERT', 'SCREEN_RULE'} or operation not in {'CREATE', 'REPLACE', 'DELETE', 'PAUSE', 'RESTART'}:
            raise MonitorError('MONITOR_INVALID_OPERATION', 422)
        if kind != 'ALERT' and operation in {'PAUSE', 'RESTART'}:
            raise MonitorError('MONITOR_INVALID_OPERATION', 422)
        if (operation == 'CREATE') != (identity is None):
            raise MonitorError('MONITOR_INVALID_OPERATION', 422)
        request_hash = digest({'kind': kind, 'operation': operation, 'object_id': identity,
                               'body': body.model_dump(mode='json')})
        if operation in {'CREATE', 'REPLACE'}:
            cls = {'WATCHLIST':WatchlistState, 'ALERT':AlertState, 'SCREEN_RULE':ScreenRuleState}[kind]
            state_json = cls.model_validate(body.state.model_dump(mode='json')).model_dump_json()
        else:
            state_json = None
        if state_json is not None and len(state_json.encode()) > self.capabilities().max_state_bytes:
            raise MonitorError('MONITOR_STATE_TOO_LARGE', 413)
        attempted_commit = False
        try:
            async with self.store.connection() as db:
                await db.execute('BEGIN IMMEDIATE')
                old = await (await db.execute(
                    'SELECT * FROM market_monitor_operations WHERE owner_id=? AND request_id=?',
                    (owner, body.request_id))).fetchone()
                if old is not None:
                    if old['request_sha256'] != request_hash:
                        raise MonitorError('MONITOR_OPERATION_SCOPE_CONFLICT')
                    return MonitorWrite.model_validate_json(old['result_json'])
                now = self.now()
                if operation == 'CREATE':
                    count = await (await db.execute(
                        'SELECT count(*) n FROM market_monitor_objects WHERE owner_id=? AND kind=?',
                        (owner, kind))).fetchone()
                    limits = self.capabilities()
                    cap = {'WATCHLIST':limits.max_watchlists, 'ALERT':limits.max_alerts,
                           'SCREEN_RULE':limits.max_screen_rules}[kind]
                    if count['n'] >= cap:
                        raise MonitorError('MONITOR_OBJECT_CAPACITY_REACHED', 429)
                    identity = {'WATCHLIST':'mwl_', 'ALERT':'mal_', 'SCREEN_RULE':'msr_'}[kind]+uuid.uuid4().hex
                    revision, generation, armed, lifecycle = 1, 1, now, 'ACTIVE'
                else:
                    row = await self._head(db, owner, kind, identity)
                    self._view(row)
                    if row['revision'] != body.expected_revision:
                        raise MonitorError('MONITOR_REVISION_CONFLICT', current_revision=row['revision'])
                    prior = self._view(row)
                    high_water = max(row['updated_at_ms'], row['armed_at_ms'],
                        prior.evaluation.clock_high_water_ms or 0 if kind == 'ALERT' and prior.evaluation else 0)
                    if now < high_water:
                        raise MonitorError('MONITOR_CLOCK_UNAVAILABLE', 503)
                    revision, generation = row['revision']+1, row['arm_generation']
                    armed, lifecycle = row['armed_at_ms'], row['lifecycle']
                    if state_json is None:
                        state_json = row['state_json']
                    if operation == 'PAUSE':
                        lifecycle = 'PAUSED'
                    elif operation == 'RESTART':
                        lifecycle, generation, armed = 'ACTIVE', generation+1, now
                    elif operation == 'REPLACE' and kind == 'ALERT':
                        generation, armed = generation+1, now
                state_hash = hashlib.sha256(state_json.encode()).hexdigest()
                if operation == 'DELETE':
                    await db.execute('DELETE FROM market_monitor_objects WHERE owner_id=? AND object_id=?',
                                     (owner, identity))
                    state_hash = None
                elif operation == 'CREATE':
                    await db.execute(
                        'INSERT INTO market_monitor_objects(owner_id,object_id,kind,revision,state_json,state_sha256,'
                        'lifecycle,arm_generation,armed_at_ms,updated_at_ms) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (owner, identity, kind, revision, state_json, state_hash, lifecycle, generation, armed, now))
                else:
                    await db.execute(
                        'UPDATE market_monitor_objects SET revision=?,state_json=?,state_sha256=?,lifecycle=?,'
                        'arm_generation=?,armed_at_ms=?,updated_at_ms=?,evaluation_json=NULL '
                        'WHERE owner_id=? AND object_id=?',
                        (revision, state_json, state_hash, lifecycle, generation, armed, now, owner, identity))
                status = {'PAUSE': 'PAUSED', 'RESTART': 'RESTARTED', 'DELETE': 'DELETED'}.get(operation, 'SAVED')
                result = MonitorWrite(request_id=body.request_id, object_id=identity, kind=kind,
                                      revision=revision, state_sha256=state_hash, status=status)
                await db.execute(
                    'INSERT INTO market_monitor_operations(owner_id,request_id,request_sha256,result_json,created_at_ms) '
                    'VALUES(?,?,?,?,?)', (owner, body.request_id, request_hash, result.model_dump_json(), now))
                attempted_commit = True
                await db.commit()
                return result
        except MonitorError:
            raise
        except Exception as exc:
            if not attempted_commit:
                raise
            try:
                observed = await self.store.fetchone(
                    'SELECT request_sha256,result_json FROM market_monitor_operations WHERE owner_id=? AND request_id=?',
                    (owner, body.request_id))
            except Exception:
                raise MonitorError('MONITOR_WRITE_OUTCOME_UNKNOWN', 503, request_id=body.request_id) from exc
            if observed is None:
                raise MonitorError('MONITOR_WRITE_NOT_APPLIED', 503, request_id=body.request_id) from exc
            if observed['request_sha256'] != request_hash:
                raise MonitorError('MONITOR_OPERATION_SCOPE_CONFLICT') from exc
            return MonitorWrite.model_validate_json(observed['result_json'])

    @staticmethod
    def _qualified(snapshot, instrument, timeframe, max_age, now):
        if snapshot is None:
            return None, 'NATIVE_INSTRUMENT_BINDING_UNAVAILABLE'
        try:
            data = snapshot.model_dump(mode='json') if isinstance(snapshot, MarketSnapshot) else snapshot
            snapshot = MarketSnapshot.model_validate(data)
        except (ValidationError, ValueError, TypeError):
            return None, 'SOURCE_OBSERVATION_INVALID'
        if snapshot.instrument != instrument or snapshot.timeframe != timeframe:
            return None, 'SOURCE_SCOPE_MISMATCH'
        if snapshot.available_at_ms > now or snapshot.bars[-1].end_ms > now:
            return None, 'SOURCE_FROM_FUTURE'
        if now-snapshot.bars[-1].end_ms > max_age:
            return None, 'SOURCE_STALE'
        return snapshot, 'QUALIFIED_CLOSED_OBSERVATION'

    def _technical(self, view, snapshot, now):
        snapshot, reason = self._qualified(snapshot, view.state.instrument, view.state.timeframe,
                                           view.state.max_age_ms, now)
        status = dict(state='UNAVAILABLE', reason=reason, evaluated_at_ms=now)
        if snapshot is None:
            return EvaluationStatus(**status), False
        condition = view.state.condition
        value = measurement(snapshot, condition)
        if value is None:
            return EvaluationStatus(state='UNAVAILABLE', reason='INDICATOR_HISTORY_UNAVAILABLE',
                                    evaluated_at_ms=now), False
        identity = digest(snapshot.model_dump(mode='json'))
        current = EvaluationStatus(state='BASELINE', reason='FIRST_QUALIFIED_OBSERVATION', evaluated_at_ms=now,
            sample_id=identity, source_id=snapshot.source_id, source_revision=snapshot.source_revision,
            measurement_basis={'PRICE':'CLOSED_BAR_CLOSE','INDICATOR':'INDICATOR_ON_CLOSED_BARS','DRAWING':'PINNED_DRAWING_ON_CLOSED_BARS'}[condition.kind],
            event_time_ms=snapshot.bars[-1].end_ms, available_at_ms=snapshot.available_at_ms, value=text(value))
        previous = view.evaluation
        prior_value = None
        if previous is not None and previous.event_time_ms is not None and previous.value is not None:
            if current.event_time_ms < previous.event_time_ms:
                return previous.model_copy(update={'reason': 'OUT_OF_ORDER_OBSERVATION', 'evaluated_at_ms': now}), False
            if current.event_time_ms == previous.event_time_ms:
                if current.sample_id == previous.sample_id:
                    return previous.model_copy(update={'reason': 'OBSERVATION_ALREADY_EVALUATED', 'evaluated_at_ms': now}), False
                current.reason = 'CORRECTED_OBSERVATION_BASELINE'
                return current, False
            if (previous.source_id == current.source_id and previous.source_revision == current.source_revision
                and previous.event_time_ms+PERIOD_MS[snapshot.timeframe] == current.event_time_ms
                and previous.available_at_ms is not None and previous.available_at_ms <= current.available_at_ms):
                prior_value = Decimal(previous.value)
        threshold = Decimal(0) if condition.kind == 'DRAWING' else Decimal(condition.threshold)
        trigger = matched(condition.comparator, value, threshold, prior_value)
        if condition.comparator.startswith('CROSS_') and prior_value is None:
            return current, False
        current.state, current.reason = ('TRIGGERED', 'CONDITION_SATISFIED') if trigger else ('NO_MATCH', 'CONDITION_NOT_SATISFIED')
        return current, trigger

    def _news(self, view, available, rows, now):
        if not available:
            return EvaluationStatus(state='UNAVAILABLE', reason='NEWS_LEDGER_UNAVAILABLE', evaluated_at_ms=now), False
        condition = view.state.condition
        try:
            checked = [NewsObservation.model_validate(r.model_dump(mode='json') if isinstance(r, NewsObservation) else r) for r in rows]
        except (ValidationError, ValueError, TypeError):
            return EvaluationStatus(state='UNAVAILABLE', reason='NEWS_OBSERVATION_INVALID', evaluated_at_ms=now), False
        for row in sorted(checked, key=lambda r: (r.published_ms, r.sample_id)):
            allowed = {'T1_PRIMARY'} if condition.minimum_trust == 'T1_PRIMARY' else {'T1_PRIMARY', 'T2_SECONDARY'}
            if (row.trust not in allowed or row.published_ms < view.armed_at_ms
                or not row.published_ms <= row.available_at_ms <= now or now-row.published_ms > view.state.max_age_ms):
                continue
            if view.state.instrument is not None and view.state.instrument.symbol.upper() not in {s.upper() for s in row.symbols}:
                continue
            content = (row.title+' '+row.excerpt).casefold()
            hits = [k in content for k in condition.keywords]
            if (all(hits) if condition.match == 'ALL' else any(hits)):
                return EvaluationStatus(state='TRIGGERED', reason='RECORDED_HEADLINE_KEYWORD_MATCH', evaluated_at_ms=now,
                    sample_id=row.sample_id, source_id=row.source_id, measurement_basis='RECORDED_NEWS', event_time_ms=row.published_ms,
                    available_at_ms=row.available_at_ms), True
        return EvaluationStatus(state='NO_MATCH', reason='NO_FRESH_TRUSTED_MATCHING_HEADLINE', evaluated_at_ms=now), False

    async def _apply(self, owner, view, evaluation, trigger):
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            row = await (await db.execute(
                'SELECT * FROM market_monitor_objects WHERE owner_id=? AND object_id=?', (owner, view.object_id))).fetchone()
            if (row is None or row['lifecycle'] != 'ACTIVE' or row['revision'] != view.revision
                or row['arm_generation'] != view.arm_generation or row['state_sha256'] != view.state_sha256):
                return False
            current = self._view(row)
            if current.evaluation != view.evaluation:
                return False
            now = self.now()
            high_water = max(row['armed_at_ms'], row['updated_at_ms'],
                current.evaluation.clock_high_water_ms or 0 if current.evaluation else 0)
            if now < high_water:
                evaluation = EvaluationStatus(state='UNAVAILABLE', reason='MONITOR_CLOCK_MOVED_BACKWARDS',
                    evaluated_at_ms=now, clock_high_water_ms=high_water)
                trigger = False
            if trigger and (now < evaluation.evaluated_at_ms or evaluation.event_time_ms is None
                            or evaluation.available_at_ms is None or not evaluation.event_time_ms <= evaluation.available_at_ms <= now
                            or now-evaluation.event_time_ms > view.state.max_age_ms):
                evaluation = EvaluationStatus(state='UNAVAILABLE', reason='OBSERVATION_EXPIRED_BEFORE_PUBLICATION',
                                              evaluated_at_ms=now)
                trigger = False
            evaluation = evaluation.model_copy(update={'evaluated_at_ms': now, 'clock_high_water_ms': max(now, high_water)})
            if trigger:
                event_id = 'market-alert:'+digest({'owner': owner, 'alert_id': view.object_id, 'arm': view.arm_generation})
                evaluation = evaluation.model_copy(update={'event_id': event_id})
                payload = {'alert_id': view.object_id, 'arm_generation': view.arm_generation,
                           'condition_kind': view.state.condition.kind,
                           'instrument': view.state.instrument.model_dump(mode='json') if view.state.instrument else None,
                           'sample_id': evaluation.sample_id, 'source_id': evaluation.source_id,
                           'measurement_basis': evaluation.measurement_basis,
                           'source_event_time_ms': evaluation.event_time_ms,
                           'source_available_at_ms': evaluation.available_at_ms,
                           'triggered_at_ms': now, 'measured_value': evaluation.value, 'authority_effect': 'NONE'}
                seq = await self.events.publish_in_transaction(db, 'trading.alert.triggered', payload,
                    event_id=event_id, correlation_id=view.object_id, occurred_at_ms=now)
                await db.execute('INSERT INTO market_monitor_publications(event_seq) VALUES(?) '
                                 'ON CONFLICT(event_seq) DO NOTHING', (seq,))
            await db.execute('UPDATE market_monitor_objects SET evaluation_json=?,lifecycle=? WHERE owner_id=? AND object_id=?',
                             (evaluation.model_dump_json(), 'TRIGGERED' if trigger else 'ACTIVE', owner, view.object_id))
            await db.commit()
            return trigger

    async def run(self, owner='owner'):
        now = self.now()
        rows = await self.store.fetchall(
            "SELECT * FROM market_monitor_objects WHERE owner_id=? AND kind='ALERT' AND lifecycle='ACTIVE' "
            "ORDER BY object_id LIMIT 128", (owner,))
        market_cache, news = {}, None
        triggered = 0
        for row in rows:
            view = self._view(row)
            if view.state.condition.kind == 'NEWS':
                if news is None:
                    try:
                        news = self.source.news()
                    except Exception:
                        news = (False, [])
                evaluation, fire = self._news(view, *news, self.now())
            else:
                key = digest({'instrument': view.state.instrument.model_dump(mode='json'), 'timeframe': view.state.timeframe})
                if key not in market_cache:
                    try:
                        market_cache[key] = self.source.market(view.state.instrument, view.state.timeframe)
                    except Exception:
                        market_cache[key] = None
                evaluation, fire = self._technical(view, market_cache[key], self.now())
            triggered += int(await self._apply(owner, view, evaluation, fire))
        published = await self.publish_pending()
        return {'evaluated': len(rows), 'triggered': triggered, 'attention_projected': published}

    async def publish_pending(self):
        if self.attention is None:
            return 0
        from van_gateway.models import AttentionSeverity
        rows = await self.store.fetchall(
            'SELECT e.seq,e.event_id,e.payload_json FROM market_monitor_publications p '
            'JOIN events e ON e.seq=p.event_seq WHERE p.projected=0 ORDER BY e.seq LIMIT 128')
        done = 0
        for row in rows:
            await self.attention.upsert(title='Market alert triggered', severity=AttentionSeverity.INFO,
                source='trading.monitor', dedupe_key=row['event_id'],
                payload=json.loads(row['payload_json']), source_revision=1)
            await self.store.execute('UPDATE market_monitor_publications SET projected=1 WHERE event_seq=?', (row['seq'],))
            done += 1
        return done

    async def run_screen_rule(self, owner, identity, body):
        view = await self.get(owner, 'SCREEN_RULE', identity)
        if view.revision != body.expected_revision:
            raise MonitorError('MONITOR_REVISION_CONFLICT', current_revision=view.revision)
        request = ScreenRequest.model_validate(view.state.model_dump(mode='json', exclude={'name'}))
        result = await self.screen(owner, request)
        return result.model_copy(update={'saved_rule':ScreenRuleBinding(object_id=view.object_id,
            revision=view.revision, state_sha256=view.state_sha256)})

    async def screen(self, owner, body):
        now = self.now()
        window = now-now % 60000
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            old = await (await db.execute(
                'SELECT * FROM market_monitor_scan_budget WHERE owner_id=?', (owner,))).fetchone()
            if old is not None and now < old['window_ms']:
                raise MonitorError('MONITOR_SCAN_CLOCK_ROLLBACK', 429, retry_after_ms=old['window_ms']-now)
            used = old['used'] if old is not None and old['window_ms'] == window else 0
            if used+len(body.instruments) > self.capabilities().scan_instruments_per_minute:
                raise MonitorError('MONITOR_SCAN_QUOTA_REACHED', 429, retry_after_ms=60000-now % 60000)
            await db.execute('INSERT INTO market_monitor_scan_budget(owner_id,window_ms,used) VALUES(?,?,?) '
                             'ON CONFLICT(owner_id) DO UPDATE SET window_ms=excluded.window_ms,used=excluded.used',
                             (owner, window, used+len(body.instruments)))
            await db.commit()
        results = []
        for instrument in body.instruments:
            try:
                snapshot = self.source.market(instrument, body.timeframe)
            except Exception:
                snapshot = None
            row_now = self.now()
            snapshot, reason = self._qualified(snapshot, instrument, body.timeframe, body.max_age_ms, row_now)
            if snapshot is None:
                results.append(ScreenRow(instrument=instrument, state='UNAVAILABLE', reason=reason, price_age_ms=None, evaluated_at_ms=row_now))
                continue
            values = [measurement(snapshot, c) for c in body.conditions]
            if any(v is None for v in values):
                results.append(ScreenRow(instrument=instrument, state='UNAVAILABLE',
                                         reason='INDICATOR_HISTORY_UNAVAILABLE', price_age_ms=row_now-snapshot.bars[-1].end_ms, evaluated_at_ms=row_now))
                continue
            hits = [matched(c.comparator, v, Decimal(c.threshold)) for c, v in zip(body.conditions, values)]
            results.append(ScreenRow(instrument=instrument, state='MATCH' if all(hits) else 'NO_MATCH',
                reason='QUALIFIED_CLOSED_OBSERVATION', price_age_ms=row_now-snapshot.bars[-1].end_ms, evaluated_at_ms=row_now,
                values=[text(v) for v in values], sample_id=digest(snapshot.model_dump(mode='json'))))
        return ScreenResult(evaluated_at_ms=self.now(), rows=results)
