"""Original catalog vintages in an existing, dedicated source-only VATI ledger.

Never attach this archive to the protective/financial journal. Mixed event kinds
refuse. This reuses existing SQLite/PostgreSQL atomic writers and checked reads;
it does not create research permission, a grant format or a live source gate.
"""
from __future__ import annotations

import re
import sqlite3
import time

from vati.core.canonical import canonical_hash,canonical_json
from vati.core.events import EventKind,make_event
from vati.execution.ctrader.catalog import NativeSymbolCatalog,catalog_scope
from vati.execution.ctrader.feed import native_integer
from vati.core.ledger import LedgerError

try:
    from psycopg import Error as PostgresError
except ImportError:
    STORAGE_ERRORS=(OSError,sqlite3.Error,LedgerError)
else:
    STORAGE_ERRORS=(OSError,sqlite3.Error,LedgerError,PostgresError)

PRODUCER='vati-native-symbol-catalog'
REQUEST=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')


class CatalogArchiveError(ValueError):
    pass


class CatalogPublicationUnknown(OSError):
    pass


class NativeCatalogStore:
    def __init__(self,ledger,*,clock=None,max_events=10000,max_bytes=64*1024**2):
        if ledger is None:raise CatalogArchiveError('dedicated native catalog source ledger required')
        if type(max_events) is not int or not 1<=max_events<=100000:
            raise CatalogArchiveError('native catalog event capacity invalid')
        if type(max_bytes) is not int or not 1<=max_bytes<=256*1024**2:
            raise CatalogArchiveError('native catalog byte capacity invalid')
        self.ledger=ledger;self.clock=clock or (lambda:int(time.time()*1000))
        self.max_events=max_events;self.max_bytes=max_bytes

    def _history(self,scope):
        scope=catalog_scope(scope);selected=[];previous={};requests=set();total=0
        with self.ledger.read_snapshot():
            count=self.ledger.count(EventKind.NATIVE_SYMBOL_CATALOG)
            if self.ledger.count()!=count:raise CatalogArchiveError('catalog archive requires a dedicated source-only ledger')
            if count>self.max_events:raise CatalogArchiveError('native catalog recovery event capacity')
            seen=0
            for event in self.ledger.iter(EventKind.NATIVE_SYMBOL_CATALOG):
                seen+=1;payload=event.payload
                total+=len(canonical_json(event.body()).encode())
                if total>self.max_bytes:raise CatalogArchiveError('native catalog recovery byte capacity')
                if (event.producer!=PRODUCER or event.kind is not EventKind.NATIVE_SYMBOL_CATALOG
                        or type(event.schema_version) is not int or event.schema_version!=1
                        or event.decision_time_ms is not None
                        or type(event.event_time_ms) is not int or type(event.received_time_ms) is not int
                        or event.hash!=canonical_hash(event.body())
                        or not isinstance(payload,dict) or set(payload)!={'format','request_id','scope',
                            'revision','previous_record_hash','captured','recorded_at_ms'}
                        or payload['format']!='native-symbol-catalog-record/1'):
                    raise CatalogArchiveError('native catalog original envelope incompatible or corrupt')
                captured=NativeSymbolCatalog.from_body(payload['captured']);native_scope=captured.native_scope
                key=canonical_hash(native_scope);prior=previous.get(key)
                request=payload['request_id']
                if (not isinstance(request,str) or REQUEST.fullmatch(request) is None
                        or (key,request) in requests or canonical_hash(payload['scope'])!=key
                        or event.correlation_id!=key or type(payload['revision']) is not int
                        or payload['revision']!=(1 if prior is None else prior.payload['revision']+1)
                        or payload['previous_record_hash']!=(None if prior is None else prior.hash)
                        or event.event_time_ms!=captured.received_at_ms
                        or event.received_time_ms!=payload['recorded_at_ms']):
                    raise CatalogArchiveError('native catalog original scope,request or revision differs')
                available=native_integer(payload['recorded_at_ms'],minimum=captured.received_at_ms,maximum=253402300799000)
                if prior is not None and available<prior.received_time_ms:
                    raise CatalogArchiveError('native catalog availability moved backwards')
                requests.add((key,request));previous[key]=event
                if native_scope==scope:selected.append(event)
            if seen!=count:raise CatalogArchiveError('native catalog original readback missing')
            if not self.ledger.verify_chain()[0]:raise CatalogArchiveError('native catalog source ledger integrity unavailable')
        return selected,total,count

    @staticmethod
    def _receipt(event):
        payload=event.payload
        return {'record_ref':event.hash,'revision':payload['revision'],'request_id':payload['request_id'],
            'scope':payload['scope'],'catalog_revision':payload['captured']['metadata_revision'],
            'received_at_ms':event.event_time_ms,'available_at_ms':event.received_time_ms,
            'provider_qualified':False,'qualified_for_research':False,'authority_effect':'NONE'}

    def lookup(self,scope,request_id):
        if not isinstance(request_id,str) or REQUEST.fullmatch(request_id) is None:
            raise CatalogArchiveError('native catalog original request identity invalid')
        rows,_,_=self._history(scope)
        return next((self._receipt(event) for event in rows if event.payload['request_id']==request_id),None)

    def record(self,request_id,captured):
        if not isinstance(captured,NativeSymbolCatalog):raise CatalogArchiveError('native catalog captured source required')
        # Revalidate the actual immutable capture before entering the writer.
        NativeSymbolCatalog.from_body(captured.body());scope=captured.native_scope
        if not isinstance(request_id,str) or REQUEST.fullmatch(request_id) is None:
            raise CatalogArchiveError('native catalog original request identity invalid')
        publication_requested=False;confirmation_needed=False
        try:
            with self.ledger.atomic():
                rows,total,count=self._history(scope)
                original=next((event for event in rows if event.payload['request_id']==request_id),None)
                if original is not None:
                    if original.payload['captured']!=captured.body():
                        raise CatalogArchiveError('native catalog request conflicts with original capture')
                    confirmation_needed=True
                else:
                    if count>=self.max_events:
                        raise CatalogArchiveError('native catalog publication event capacity')
                    now=native_integer(self.clock(),minimum=captured.received_at_ms,maximum=253402300799000)
                    if rows and now<rows[-1].received_time_ms:raise CatalogArchiveError('native catalog publication clock moved backwards')
                    payload={'format':'native-symbol-catalog-record/1','request_id':request_id,'scope':scope,
                        'revision':len(rows)+1,'previous_record_hash':rows[-1].hash if rows else None,
                        'captured':captured.body(),'recorded_at_ms':now}
                    original=make_event(EventKind.NATIVE_SYMBOL_CATALOG,PRODUCER,payload,
                        event_time_ms=captured.received_at_ms,received_time_ms=now,correlation_id=canonical_hash(scope))
                    size=total+len(canonical_json(original.body()).encode())
                    if size>self.max_bytes:raise CatalogArchiveError('native catalog publication byte capacity')
                    publication_requested=True
                    self.ledger.append(original)
            confirmation_needed=True
            confirmed=self.lookup(scope,request_id)
            if confirmed is None or confirmed['record_ref']!=original.hash:
                raise CatalogPublicationUnknown('native catalog original publication readback unavailable')
            return confirmed
        except STORAGE_ERRORS as error:
            if publication_requested or confirmation_needed:
                raise CatalogPublicationUnknown('native catalog publication unknown; reconcile original request') from error
            raise CatalogArchiveError('native catalog source storage unavailable before publication') from error

    def snapshot(self,scope,*,revision=None,as_of_ms=None,record_ref=None):
        if revision is not None and as_of_ms is not None:
            raise CatalogArchiveError('select one catalog ordinal or time boundary')
        if revision is not None:native_integer(revision,minimum=1)
        if as_of_ms is not None:native_integer(as_of_ms,maximum=native_integer(self.clock(),maximum=253402300799000))
        history,_,_=self._history(scope)
        rows=[event for event in history if (revision is None or event.payload['revision']==revision)
            and (as_of_ms is None or event.received_time_ms<=as_of_ms)]
        if not rows:return None
        original=rows[-1]
        if record_ref is not None and (not isinstance(record_ref,str) or record_ref!=original.hash):
            raise CatalogArchiveError('native catalog pinned source reference differs')
        captured=NativeSymbolCatalog.from_body(original.payload['captured'])
        return {'receipt':self._receipt(original),'captured':captured.body(),'members':captured.members(),
            'coverage':'REQUESTED_ARCHIVED_ROWS' if captured.metadata['include_archived_symbols'] else 'ARCHIVED_COVERAGE_NOT_REQUESTED',
            'lifecycle_effective_times_qualified':False,'provider_qualified':False,'qualified_for_research':False,'authority_effect':'NONE'}


class NativeCatalogCollector:
    """Existing independent reader -> original source ledger; no native orders."""
    def __init__(self,store,reader_factory):
        if not isinstance(store,NativeCatalogStore) or not callable(reader_factory):
            raise CatalogArchiveError('native catalog owner and independent reader required')
        self.store,self.reader_factory=store,reader_factory

    def _original(self,scope,request_id,captured=None):
        original=self.store.lookup(scope,request_id)
        if original is None:return None
        frozen=self.store.snapshot(scope,revision=original['revision'],record_ref=original['record_ref'])
        if frozen is None or frozen['captured']['metadata']['include_archived_symbols'] is not True:
            raise CatalogArchiveError('native catalog original request profile differs')
        if captured is not None and frozen['captured']!=captured.body():
            raise CatalogArchiveError('native catalog original capture differs')
        return original

    def collect(self,request_id,expected_scope):
        scope=catalog_scope(expected_scope)
        original=self._original(scope,request_id)
        if original is not None:return original
        reader=self.reader_factory()
        try:captured=reader.read_catalog(scope)
        finally:reader.close()
        if (not isinstance(captured,NativeSymbolCatalog) or captured.native_scope!=scope
                or captured.metadata['include_archived_symbols'] is not True):
            raise CatalogArchiveError('native catalog collection scope or request differs')
        try:return self.store.record(request_id,captured)
        except CatalogPublicationUnknown as uncertain:
            try:original=self._original(scope,request_id,captured)
            except STORAGE_ERRORS:raise uncertain
            if original is not None:return original
            raise
