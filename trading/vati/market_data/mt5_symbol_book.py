"""Small original symbol observations bound before a risk decision exists.

The existing MT5 query journal proves the account source. This book neither
admits current FX/risk terms nor stores a feed/catalog in the financial log.
"""
import re,time

from vati.core import EventKind,make_event
from vati.core.canonical import canonical_json,canonical_hash
from vati.core.ledger import committed_source_snapshot,require_committed_source_read
from vati.execution.mt5_symbol_contract import Mt5SymbolContractObservation
from vati.funding.native import native_int
from vati.risk.account_context import inspect_context
from vati.risk.contracts import NativeAccountRiskContext
from vati.risk.native_history import _original_mt5_query,NativeRiskSourceUnavailable

EVENT='ORIGINAL_MT5_SYMBOL_TERMS'
PRODUCER='vati-mt5-symbol-book'
SCHEMA='vati.original-mt5-symbol-record/1'


class NativeSymbolError(ValueError):pass


class NativeSymbolUnknown(OSError):
    def __init__(self,source_ref):
        self.source_ref=source_ref
        super().__init__('NATIVE_SYMBOL_STORAGE_OUTCOME_UNKNOWN_READ_ORIGINAL_SOURCE')


class NativeSymbolBook:
    observation_type=Mt5SymbolContractObservation
    event_name=EVENT
    producer=PRODUCER
    record_schema=SCHEMA
    receipt_schema='vati.original-mt5-symbol-receipt/1'
    stored_state='ORIGINAL_NATIVE_SYMBOL_STORED'

    def __init__(self,ledger,*,clock=None,max_records=4096,max_bytes=16*1024**2,max_ledger_events=100000):
        for value,limit in [(max_records,100000),(max_bytes,256*1024**2),(max_ledger_events,1000000)]:
            if type(value) is not int or not 1<=value<=limit:raise NativeSymbolError('NATIVE_SYMBOL_CAPACITY_INVALID')
        self.ledger=ledger;self.clock=clock or (lambda:int(time.time()*1000))
        self.max_records,self.max_bytes,self.max_ledger_events=max_records,max_bytes,max_ledger_events

    def _now(self):
        try:return native_int(self.clock(),minimum=0,maximum=253402300799000)
        except Exception:raise NativeSymbolError('NATIVE_SYMBOL_STORAGE_CLOCK_UNAVAILABLE') from None

    def _bind(self,body,queries):
        context=NativeAccountRiskContext(**body['native_account_context']);source=inspect_context(context)
        try:query=_original_mt5_query(self.ledger,context,queries)
        except NativeRiskSourceUnavailable:
            raise NativeSymbolError('NATIVE_SYMBOL_ORIGINAL_QUERY_UNAVAILABLE') from None
        omit_alias=lambda value:{k:v for k,v in value.items() if k!='account_alias'}
        if (max(query.event_time_ms,query.received_time_ms)>body['requested_at_ms']
                or query.payload['source_ref']!=context.observation_ref
                or omit_alias(query.payload['mark'])!=omit_alias(source['mark'])):
            raise NativeSymbolError('NATIVE_SYMBOL_ORIGINAL_QUERY_BINDING_INVALID')
        return query

    def _history(self):
        if self.ledger.count()>self.max_ledger_events:raise NativeSymbolError('NATIVE_SYMBOL_EVENT_CAPACITY')
        if not self.ledger.verify_chain()[0]:raise NativeSymbolError('NATIVE_SYMBOL_CHAIN_UNAVAILABLE')
        rows={};size=0;last=-1;queries={}
        for event in self.ledger.iter(EventKind.SESSION):
            p=event.payload
            if type(p) is not dict or p.get('event')!=self.event_name:continue
            size+=len(canonical_json(event.body()).encode())
            if size>self.max_bytes or len(rows)>=self.max_records:raise NativeSymbolError('NATIVE_SYMBOL_HISTORY_CAPACITY')
            if (event.producer!=self.producer or type(event.schema_version) is not int or event.schema_version!=1
                    or event.decision_time_ms is not None or event.hash!=canonical_hash(event.body())
                    or set(p)!={'event','schema','observation'} or p['schema']!=self.record_schema):
                raise NativeSymbolError('NATIVE_SYMBOL_RECORD_INVALID')
            q=self.observation_type.from_body(p['observation']).body();key=q['source_ref']
            self._bind(q,queries)
            if (key in rows or event.correlation_id!=key or type(event.event_time_ms) is not int
                    or type(event.received_time_ms) is not int or event.event_time_ms!=event.received_time_ms
                    or not max(last,q['received_at_ms'])<=event.received_time_ms<q['valid_until_ms']):
                raise NativeSymbolError('NATIVE_SYMBOL_ORIGINAL_IDENTITY_OR_CLOCK_INVALID')
            rows[key]=event;last=event.received_time_ms
        return rows,size,last

    def _receipt(self,event):
        q=event.payload['observation']
        return {'schema':self.receipt_schema,'record_ref':event.hash,
            'source_ref':q['source_ref'],'source_query_ref':q['native_account_context']['source_query_ref'],
            'available_at_ms':event.received_time_ms,'state':self.stored_state,
            'risk_terms_qualified':False,'execution_authority':False}

    def lookup(self,source_ref):
        if type(source_ref) is not str or re.fullmatch('[a-f0-9]{64}',source_ref) is None:
            raise NativeSymbolError('NATIVE_SYMBOL_REFERENCE_INVALID')
        with committed_source_snapshot(self.ledger):
            event=self._history()[0].get(source_ref)
            return None if event is None else {'receipt':self._receipt(event),'observation':event.payload['observation']}

    def record(self,observation):
        require_committed_source_read(self.ledger)
        if getattr(self.ledger,'_read_snapshot_depth',0):raise NativeSymbolError('NATIVE_SYMBOL_REQUIRES_OWN_WRITER')
        if type(observation) is not self.observation_type:
            raise NativeSymbolError('NATIVE_SYMBOL_TYPED_OBSERVATION_REQUIRED')
        q=self.observation_type.from_body(observation.body()).body();key=q['source_ref']
        with committed_source_snapshot(self.ledger):self._bind(q,{})
        known=self.lookup(key)
        if known is not None:return known['receipt']
        before=self.ledger.head();started=False
        try:
            with self.ledger.atomic():
                rows,size,last=self._history();event=rows.get(key)
                if event is None:
                    if self.ledger.head()!=before:raise NativeSymbolError('NATIVE_SYMBOL_SOURCE_CHANGED_RETRY_ORIGINAL')
                    self._bind(q,{})
                    now=self._now()
                    if not max(last,q['received_at_ms'])<=now<q['valid_until_ms']:
                        raise NativeSymbolError('NATIVE_SYMBOL_EXPIRED_OR_CLOCK_REGRESSED')
                    if len(rows)>=self.max_records or self.ledger.count()>=self.max_ledger_events:
                        raise NativeSymbolError('NATIVE_SYMBOL_EVENT_CAPACITY')
                    event=make_event(EventKind.SESSION,self.producer,{'event':self.event_name,'schema':self.record_schema,'observation':q},
                        event_time_ms=now,received_time_ms=now,correlation_id=key)
                    if size+len(canonical_json(event.body()).encode())>self.max_bytes:
                        raise NativeSymbolError('NATIVE_SYMBOL_BYTE_CAPACITY')
                    started=True;self.ledger.append(event)
            started=True;confirmed=self.lookup(key)
            if confirmed is None or confirmed['receipt']['record_ref']!=event.hash:raise NativeSymbolUnknown(key)
            return confirmed['receipt']
        except NativeSymbolUnknown:raise
        except Exception:
            if started:raise NativeSymbolUnknown(key) from None
            raise

    def capture(self,adapter,symbol,*,context,deadline_ms):
        require_committed_source_read(self.ledger)
        # Verify the original current account query before issuing a native read.
        from dataclasses import asdict
        proof={'native_account_context':asdict(context),'requested_at_ms':self._now()}
        with committed_source_snapshot(self.ledger):
            if not self.ledger.verify_chain()[0]:raise NativeSymbolError('NATIVE_SYMBOL_CHAIN_UNAVAILABLE')
            self._bind(proof,{})
        observation=self._read(adapter,symbol,context=context,deadline_ms=deadline_ms)
        return self.record(observation)

    def _read(self,adapter,symbol,*,context,deadline_ms):
        return adapter.symbol_contract(symbol,context=context,deadline_ms=deadline_ms)
