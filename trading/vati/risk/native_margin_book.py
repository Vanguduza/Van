"""Original native margin observations, durably bound to their risk input.

Historical readback survives quote expiry. It cannot turn a current-price
estimate into an admitted reservation, settlement or execution grant.
"""
from dataclasses import asdict
import time

from vati.core import EventKind, make_event
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.ledger import committed_source_snapshot, require_committed_source_read
from vati.execution.ctrader.feed import native_integer
from vati.execution.ctrader.margin_quote import ExpectedMarginObservation
from vati.risk.native_history import original_native_risk_input

EVENT='ORIGINAL_NATIVE_MARGIN'
PRODUCER='vati-native-margin-book'
SCHEMA='vati.original-native-margin-record/1'


class NativeMarginError(ValueError):
    pass


class NativeMarginUnknown(OSError):
    def __init__(self,source_ref):
        self.source_ref=source_ref
        super().__init__('NATIVE_MARGIN_STORAGE_OUTCOME_UNKNOWN_READ_ORIGINAL_SOURCE')


class NativeMarginBook:
    def __init__(self,ledger,*,clock=None,max_records=4096,max_bytes=16*1024**2,max_ledger_events=100000):
        for value,limit in [(max_records,100000),(max_bytes,256*1024**2),(max_ledger_events,1000000)]:
            if type(value) is not int or not 1<=value<=limit:raise NativeMarginError('NATIVE_MARGIN_CAPACITY_INVALID')
        self.ledger=ledger;self.clock=clock or (lambda:int(time.time()*1000))
        self.max_records,self.max_bytes,self.max_ledger_events=max_records,max_bytes,max_ledger_events

    def _now(self):
        try:return native_integer(self.clock(),maximum=253402300799000)
        except Exception:raise NativeMarginError('NATIVE_MARGIN_STORAGE_CLOCK_UNAVAILABLE') from None

    def _rows(self):
        rows={};size=0;last=-1
        if self.ledger.count()>self.max_ledger_events:raise NativeMarginError('NATIVE_MARGIN_EVENT_CAPACITY')
        if not self.ledger.verify_chain()[0]:raise NativeMarginError('NATIVE_MARGIN_CHAIN_UNAVAILABLE')
        seen=set()
        for event in self.ledger.iter():
            earlier=seen
            if event.kind is not EventKind.SESSION:
                seen.add(event.hash);continue
            p=event.payload
            if not isinstance(p,dict) or p.get('event')!=EVENT:
                seen.add(event.hash);continue
            size+=len(canonical_json(event.body()).encode())
            if len(rows)>=self.max_records or size>self.max_bytes:raise NativeMarginError('NATIVE_MARGIN_HISTORY_CAPACITY')
            if (set(p)!={'event','schema','original_input_ref','observation'} or p['schema']!=SCHEMA
                    or event.producer!=PRODUCER or event.schema_version!=1 or event.decision_time_ms is not None
                    or event.hash!=canonical_hash(event.body()) or p['original_input_ref'] not in earlier):
                raise NativeMarginError('NATIVE_MARGIN_RECORD_INVALID')
            q=ExpectedMarginObservation.from_body(p['observation']).body();key=q['source_ref']
            native_integer(event.received_time_ms,minimum=last,maximum=q['valid_until_ms']-1)
            if (type(event.event_time_ms) is not int or event.event_time_ms!=event.received_time_ms
                    or event.received_time_ms<q['received_at_ms'] or key!=event.correlation_id or key in rows):
                raise NativeMarginError('NATIVE_MARGIN_ORIGINAL_IDENTITY_OR_CLOCK_INVALID')
            rows[key]=event;last=event.received_time_ms
            seen.add(event.hash)
        return rows,size,last

    def _original(self,event):
        p=event.payload;q=p['observation']
        original=original_native_risk_input(self.ledger,p['original_input_ref'],available_at_ms=q['requested_at_ms'])
        if (canonical_json(asdict(original.context))!=canonical_json(q['native_account_context'])
                or max(original.event_time_ms,original.received_time_ms)>q['requested_at_ms']):
            raise NativeMarginError('NATIVE_MARGIN_ORIGINAL_INPUT_BINDING_INVALID')
        return original

    @staticmethod
    def _receipt(event):
        q=event.payload['observation']
        return {'record_ref':event.hash,'source_ref':q['source_ref'],
            'original_input_ref':event.payload['original_input_ref'],
            'available_at_ms':event.received_time_ms,'state':'ORIGINAL_NATIVE_ESTIMATE_STORED',
            'reservation_qualified':False,'execution_authority':False}

    def lookup(self,source_ref):
        with committed_source_snapshot(self.ledger):
            event=self._rows()[0].get(source_ref)
            if event is None:return None
            self._original(event)
            return {'receipt':self._receipt(event),'observation':event.payload['observation']}

    def record(self,original_input_ref,observation):
        require_committed_source_read(self.ledger)
        if getattr(self.ledger,'_read_snapshot_depth',0):raise NativeMarginError('NATIVE_MARGIN_REQUIRES_OWN_WRITER')
        if type(observation) is not ExpectedMarginObservation:raise NativeMarginError('NATIVE_MARGIN_TYPED_OBSERVATION_REQUIRED')
        q=ExpectedMarginObservation.from_body(observation.body()).body();key=q['source_ref']
        original=original_native_risk_input(self.ledger,original_input_ref,available_at_ms=q['requested_at_ms'])
        if canonical_json(asdict(original.context))!=canonical_json(q['native_account_context']):
            raise NativeMarginError('NATIVE_MARGIN_ORIGINAL_INPUT_BINDING_INVALID')
        known=self.lookup(key)
        if known is not None:
            if known['receipt']['original_input_ref']!=original_input_ref:raise NativeMarginError('NATIVE_MARGIN_ORIGINAL_INPUT_CONFLICT')
            return known['receipt']
        before_head=self.ledger.head();started=False
        try:
            with self.ledger.atomic():
                rows,size,last=self._rows();event=rows.get(key)
                if event is not None:
                    if event.payload['original_input_ref']!=original_input_ref:raise NativeMarginError('NATIVE_MARGIN_ORIGINAL_INPUT_CONFLICT')
                else:
                    if self.ledger.head()!=before_head:raise NativeMarginError('NATIVE_MARGIN_SOURCE_CHANGED_RETRY_ORIGINAL')
                    now=self._now()
                    if not max(last,q['received_at_ms'])<=now<q['valid_until_ms']:
                        raise NativeMarginError('NATIVE_MARGIN_EXPIRED_OR_CLOCK_REGRESSED')
                    if len(rows)>=self.max_records or self.ledger.count()>=self.max_ledger_events:
                        raise NativeMarginError('NATIVE_MARGIN_EVENT_CAPACITY')
                    event=make_event(EventKind.SESSION,PRODUCER,{'event':EVENT,'schema':SCHEMA,
                        'original_input_ref':original_input_ref,'observation':q},
                        event_time_ms=now,received_time_ms=now,correlation_id=key)
                    if size+len(canonical_json(event.body()).encode())>self.max_bytes:
                        raise NativeMarginError('NATIVE_MARGIN_BYTE_CAPACITY')
                    started=True;self.ledger.append(event)
            started=True
            confirmed=self.lookup(key)
            if confirmed is None or confirmed['receipt']['record_ref']!=event.hash:
                raise NativeMarginUnknown(key)
            return confirmed['receipt']
        except NativeMarginUnknown:raise
        except Exception:
            if started:raise NativeMarginUnknown(key) from None
            raise

    def capture(self,adapter,original_input_ref,symbol,lots,*,deadline_ms):
        """Actual adapter caller; record only after the native read completes."""
        original=original_native_risk_input(self.ledger,original_input_ref,available_at_ms=self._now())
        observation=adapter.expected_margin(symbol,lots,context=original.context,deadline_ms=deadline_ms)
        return self.record(original_input_ref,observation)
