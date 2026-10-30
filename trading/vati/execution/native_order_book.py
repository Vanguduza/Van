"""Original native order observations bound to an already dispatched command.

This journal owns readback, not cancellation, financial reservations or release.
Repeated reads retain distinct original availability; a replay returns the first
durable result without another provider request, even after its deadline.
"""
import re
import time

from vati.core import EventKind, make_event
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.ledger import committed_source_snapshot, require_committed_source_read
from vati.execution.ctrader.orders import NativeOrderObservation
from vati.funding.native import native_int
from vati.risk.contracts import NativeAccountRiskContext
from vati.risk.native_margin_book import NativeMarginBook

EVENT = 'ORIGINAL_NATIVE_ORDER_OBSERVATION'
PRODUCER = 'vati-native-order-book'
SCHEMA = 'vati.original-native-order-record/1'
_KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', re.ASCII)
_REF = re.compile(r'[0-9a-f]{64}', re.ASCII)


class NativeOrderError(ValueError):
    pass


class NativeOrderUnknown(OSError):
    def __init__(self, request_id):
        self.request_id = request_id
        super().__init__('NATIVE_ORDER_STORAGE_OUTCOME_UNKNOWN_READ_ORIGINAL_REQUEST')


def _identity(request_id, command_hash, margin_source_ref, native_order_id):
    if type(request_id) is not str or _KEY.fullmatch(request_id) is None:
        raise NativeOrderError('NATIVE_ORDER_REQUEST_ID_INVALID')
    for ref in (command_hash, margin_source_ref):
        if type(ref) is not str or _REF.fullmatch(ref) is None:
            raise NativeOrderError('NATIVE_ORDER_ORIGINAL_REFERENCE_INVALID')
    native_int(native_order_id, minimum=1)
    return {'request_id': request_id, 'command_hash': command_hash,
            'margin_source_ref': margin_source_ref, 'native_order_id': native_order_id}


class NativeOrderBook:
    def __init__(self, ledger, *, clock=None, max_records=4096,
                 max_bytes=32*1024**2, max_events=100000):
        for value, cap in ((max_records, 100000), (max_bytes, 256*1024**2), (max_events, 1000000)):
            if type(value) is not int or not 1 <= value <= cap:
                raise NativeOrderError('NATIVE_ORDER_CAPACITY_INVALID')
        self.ledger, self.clock = ledger, clock or (lambda: int(time.time()*1000))
        self.max_records, self.max_bytes, self.max_events = max_records, max_bytes, max_events

    def _now(self):
        return native_int(self.clock(), minimum=0)

    def _rows(self):
        if self.ledger.count() > self.max_events or not self.ledger.verify_chain()[0]:
            raise NativeOrderError('NATIVE_ORDER_HISTORY_CAPACITY_OR_INTEGRITY')
        rows = {}; size = 0; last = -1
        for event in self.ledger.iter(EventKind.SESSION):
            p = event.payload
            if type(p) is not dict or p.get('event') != EVENT:
                continue
            size += len(canonical_json(event.body()).encode())
            if len(rows) >= self.max_records or size > self.max_bytes:
                raise NativeOrderError('NATIVE_ORDER_HISTORY_CAPACITY')
            if (set(p) != {'event', 'schema', 'request', 'observation'} or p['schema'] != SCHEMA
                    or event.producer != PRODUCER or event.schema_version != 1
                    or event.decision_time_ms is not None or event.hash != canonical_hash(event.body())):
                raise NativeOrderError('NATIVE_ORDER_RECORD_INVALID')
            request = p['request']
            if type(request) is not dict or request != _identity(**request):
                raise NativeOrderError('NATIVE_ORDER_REQUEST_INVALID')
            q = NativeOrderObservation.from_body(p['observation']).body()
            key = request['request_id']
            if (key != event.correlation_id or key in rows
                    or request['native_order_id'] != q['native_order_id']
                    or type(event.event_time_ms) is not int
                    or event.event_time_ms != event.received_time_ms):
                raise NativeOrderError('NATIVE_ORDER_IDENTITY_OR_CLOCK_INVALID')
            native_int(event.received_time_ms, minimum=max(last, q['received_at_ms']),
                       maximum=q['deadline_ms']-1)
            rows[key] = event; last = event.received_time_ms
        return rows, size, last

    def _binding(self, request, *, available_at_ms, observation=None):
        book = NativeMarginBook(self.ledger)
        original = book.lookup_entry(request['command_hash'], request['margin_source_ref'])
        if original is None:
            raise NativeOrderError('NATIVE_ORDER_ORIGINAL_ENTRY_UNAVAILABLE')
        volume = book.lookup_entry_volume(request['command_hash'], request['margin_source_ref'],
                                         available_at_ms=available_at_ms)
        if request['native_order_id'] not in volume['native_order_ids']:
            raise NativeOrderError('NATIVE_ORDER_NOT_OWNED_BY_ORIGINAL_COMMAND')
        quote = original['observation']
        if observation is not None:
            q = observation
            context = q['native_account_context']
            facts = q['facts']
            side = {'LONG': 'BUY', 'SHORT': 'SELL'}[original['command']['direction']]
            if (context != quote['native_account_context']
                    or facts['native_symbol_id'] != quote['native_symbol_id']
                    or facts['native_trade_side'] != side):
                raise NativeOrderError('NATIVE_ORDER_ORIGINAL_SCOPE_DIFFERS')
        return original, volume

    @staticmethod
    def _receipt(event):
        p = event.payload; q = p['observation']
        return {'record_ref': event.hash, 'request_id': p['request']['request_id'],
                'source_ref': q['source_ref'], 'available_at_ms': event.received_time_ms,
                'state': 'ORIGINAL_NATIVE_ORDER_STORED', 'execution_authority': False,
                'reservation_qualified': False, 'settlement_qualified': False}

    def lookup(self, request_id):
        if type(request_id) is not str or _KEY.fullmatch(request_id) is None:
            raise NativeOrderError('NATIVE_ORDER_REQUEST_ID_INVALID')
        with committed_source_snapshot(self.ledger):
            event = self._rows()[0].get(request_id)
            if event is None:
                return None
            p = event.payload
            self._binding(p['request'], available_at_ms=p['observation']['requested_at_ms'],
                          observation=p['observation'])
            return {'receipt': self._receipt(event), 'request': p['request'], 'observation': p['observation']}

    def record(self, request_id, command_hash, margin_source_ref, observation):
        require_committed_source_read(self.ledger)
        if getattr(self.ledger, '_read_snapshot_depth', 0):
            raise NativeOrderError('NATIVE_ORDER_REQUIRES_OWN_WRITER')
        if type(observation) is not NativeOrderObservation:
            raise NativeOrderError('NATIVE_ORDER_TYPED_OBSERVATION_REQUIRED')
        q = NativeOrderObservation.from_body(observation.body()).body()
        request = _identity(request_id, command_hash, margin_source_ref, q['native_order_id'])
        known = self.lookup(request_id)
        if known is not None:
            if known['request'] != request or known['observation'] != q:
                raise NativeOrderError('NATIVE_ORDER_ORIGINAL_REQUEST_CONFLICT')
            return known['receipt']
        with committed_source_snapshot(self.ledger):
            self._binding(request, available_at_ms=q['requested_at_ms'], observation=q)
            before_head = self.ledger.head()
        started = False
        try:
            with self.ledger.atomic():
                rows, size, last = self._rows()
                event = rows.get(request_id)
                if event is not None:
                    if event.payload['request'] != request or event.payload['observation'] != q:
                        raise NativeOrderError('NATIVE_ORDER_ORIGINAL_REQUEST_CONFLICT')
                else:
                    if self.ledger.head() != before_head:
                        raise NativeOrderError('NATIVE_ORDER_SOURCE_CHANGED_RECONCILE_ORIGINAL')
                    now = self._now()
                    if not max(last, q['received_at_ms']) <= now < q['deadline_ms']:
                        raise NativeOrderError('NATIVE_ORDER_EXPIRED_OR_CLOCK_REGRESSED')
                    if len(rows) >= self.max_records or self.ledger.count() >= self.max_events:
                        raise NativeOrderError('NATIVE_ORDER_EVENT_CAPACITY')
                    event = make_event(EventKind.SESSION, PRODUCER,
                        {'event': EVENT, 'schema': SCHEMA, 'request': request, 'observation': q},
                        event_time_ms=now, received_time_ms=now, correlation_id=request_id)
                    if size+len(canonical_json(event.body()).encode()) > self.max_bytes:
                        raise NativeOrderError('NATIVE_ORDER_BYTE_CAPACITY')
                    started = True; self.ledger.append(event)
            started = True
            confirmed = self.lookup(request_id)
            if confirmed is None or confirmed['receipt']['record_ref'] != event.hash:
                raise NativeOrderUnknown(request_id)
            return confirmed['receipt']
        except NativeOrderUnknown:
            raise
        except Exception:
            if started:
                raise NativeOrderUnknown(request_id) from None
            raise

    def capture(self, adapter, request_id, command_hash, margin_source_ref, native_order_id, *, deadline_ms):
        require_committed_source_read(self.ledger)
        if getattr(self.ledger, '_read_snapshot_depth', 0):
            raise NativeOrderError('NATIVE_ORDER_REQUIRES_OWN_WRITER')
        request = _identity(request_id, command_hash, margin_source_ref, native_order_id)
        known = self.lookup(request_id)
        if known is not None:
            if known['request'] != request:
                raise NativeOrderError('NATIVE_ORDER_ORIGINAL_REQUEST_CONFLICT')
            return known['receipt']
        now = self._now(); native_int(deadline_ms, minimum=now+1)
        original, _ = self._binding(request, available_at_ms=now)
        context = NativeAccountRiskContext(**original['observation']['native_account_context'])
        if (getattr(adapter, 'account_alias', None) != context.account_alias
                or getattr(adapter, 'venue', None) != 'ctrader'):
            raise NativeOrderError('NATIVE_ORDER_ADAPTER_SCOPE_DIFFERS')
        observation = adapter.order_details(native_order_id, context=context, deadline_ms=deadline_ms)
        return self.record(request_id, command_hash, margin_source_ref, observation)

    def for_command(self, command_hash, *, available_at_ms):
        """Retain all original facts; later missing rows cannot erase a fill."""
        native_int(available_at_ms, minimum=0)
        with committed_source_snapshot(self.ledger):
            events = [e for e in self._rows()[0].values()
                      if e.payload['request']['command_hash'] == command_hash
                      and e.received_time_ms <= available_at_ms]
            deals = {}; reported_by_order = {}; issues = set(); refs = []; possible_entry_orders = set()
            for event in events:
                p = event.payload; q = p['observation']; facts = q['facts']
                _, volume = self._binding(p['request'], available_at_ms=q['requested_at_ms'], observation=q)
                refs.append(event.hash)
                if facts['native_order_status'] in {'ORDER_STATUS_ACCEPTED','ORDER_STATUS_FILLED'}:
                    # A live unfilled order can still execute. A reported fill
                    # also remains possible exposure when its deals are absent.
                    possible_entry_orders.add(q['native_order_id'])
                if facts['observation_state'] != 'NATIVE_ORDER_OBSERVED' or facts['closing_order'] is not False:
                    issues.add('NATIVE_ORDER_FACTS_UNRECONCILED')
                reported = facts['reported_executed_volume']
                if reported is not None:
                    reported_by_order[q['native_order_id']] = max(
                        reported_by_order.get(q['native_order_id'], 0), reported)
                for deal in facts['recorded_deals']:
                    key = (q['native_order_id'], deal['native_id'])
                    if key in deals and deals[key] != deal:
                        issues.add('NATIVE_ORDER_DEAL_CORRECTION_UNRECONCILED')
                        if deal['filled_volume_cents'] > deals[key]['filled_volume_cents']:
                            deals[key] = deal
                    else:
                        deals[key] = deal
                if sum(reported_by_order.values()) > volume['original_command_volume_cents']:
                    issues.add('NATIVE_ORDER_EXECUTION_EXCEEDS_ORIGINAL_COMMAND')
            gross = sum(d['filled_volume_cents'] for d in deals.values())
            if events and gross > volume['original_command_volume_cents']:
                issues.add('NATIVE_ORDER_EXECUTION_EXCEEDS_ORIGINAL_COMMAND')
            return {'original_record_refs': refs, 'recorded_gross_deal_volume': gross,
                    'native_orders_requiring_original_exposure':sorted(possible_entry_orders),
                    'maximum_reported_executed_volume': sum(reported_by_order.values()), 'issues': sorted(issues),
                    'remaining_entry_allowance': None, 'position_flat': None,
                    'execution_authority': False, 'settlement_qualified': False}
