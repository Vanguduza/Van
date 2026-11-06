"""Immutable candidate publication using the existing VATI ledger owner.

No data-use grant, financial journal or alternate approval format is created.
Published metadata and currently usable source bytes remain separate states.
"""
from datetime import datetime, timedelta, timezone
import json
import time

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import EventKind, make_event
from vati.execution.ctrader.feed import native_integer
from vati.market_data.native_archive import REQUEST_ID, _scope
from vati.market_data.catalog_store import STORAGE_ERRORS
from vati.research.dataset_manifest import DatasetManifestCandidate, DatasetContractError
from vati.research.dataset_sources import NativeDatasetSourceInspector

PRODUCER = 'vati-dataset-candidate-publication'


class DatasetPublicationUnknown(OSError):
    """Reconcile the original request before attempting another publication."""


def _candidate(body):
    return DatasetManifestCandidate(canonical_json(body).encode())


def _stamp(milliseconds):
    return (datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=milliseconds)).isoformat(
        timespec='milliseconds').replace('+00:00','Z')


class DatasetCandidateArchive:
    def __init__(self, ledger, inspector=None, *, clock=None, max_events=1000, max_bytes=64*1024**2):
        if ledger is None or (inspector is not None and not isinstance(inspector,NativeDatasetSourceInspector)):
            raise DatasetContractError('DATASET_SOURCE_LEDGER_AND_INSPECTOR_REQUIRED')
        if (type(max_events) is not int or not 1<=max_events<=10000
                or type(max_bytes) is not int or not 1<=max_bytes<=256*1024**2):
            raise DatasetContractError('DATASET_PUBLICATION_CAPACITY_INVALID')
        self.ledger=ledger;self.inspector=inspector;self.clock=clock or (lambda:int(time.time()*1000))
        self.max_events=max_events;self.max_bytes=max_bytes

    def _outside_transaction(self):
        connection=getattr(self.ledger,'_conn',None)
        if (connection is None or getattr(self.ledger,'_atomic_depth',0)
                or getattr(self.ledger,'_read_snapshot_depth',0)):
            raise DatasetContractError('DATASET_PUBLICATION_REQUIRES_OWN_TRANSACTION')
        if hasattr(connection,'in_transaction'):active=connection.in_transaction
        elif hasattr(connection,'info'):active=connection.info.transaction_status!=0
        else:raise DatasetContractError('DATASET_TRANSACTION_STATE_UNAVAILABLE')
        if active:raise DatasetContractError('DATASET_PUBLICATION_REQUIRES_OWN_TRANSACTION')

    def _history(self):
        try:return self._read_history()
        except DatasetContractError:raise
        except (KeyError,TypeError,ValueError,OverflowError) as error:
            raise DatasetContractError('DATASET_ORIGINAL_RECORD_INVALID') from error

    def _read_history(self):
        rows=[];size=0;requests=set();records=set();prior=-1
        with self.ledger.read_snapshot():
            count=self.ledger.count(EventKind.DATASET_MANIFEST_CANDIDATE)
            if self.ledger.count()!=count:raise DatasetContractError('DATASET_DEDICATED_SOURCE_LEDGER_REQUIRED')
            if count>self.max_events:raise DatasetContractError('DATASET_SOURCE_EVENT_CAPACITY')
            for event in self.ledger.iter(EventKind.DATASET_MANIFEST_CANDIDATE):
                size+=len(canonical_json(event.body()).encode());p=event.payload
                if size>self.max_bytes or len(rows)>=self.max_events:
                    raise DatasetContractError('DATASET_SOURCE_BYTE_OR_EVENT_CAPACITY')
                if (event.kind is not EventKind.DATASET_MANIFEST_CANDIDATE or event.producer!=PRODUCER
                        or type(event.schema_version) is not int or event.schema_version!=1
                        or event.decision_time_ms is not None
                        or type(event.event_time_ms) is not int or type(event.received_time_ms) is not int
                        or event.hash!=canonical_hash(event.body())
                        or not isinstance(p,dict) or set(p)!={'format','request_id','request_sha256','requested_manifest',
                            'native_scope','manifest','source_witness_digest','recorded_at_ms'}
                        or p['format']!='dataset-manifest-candidate-record/1'):
                    raise DatasetContractError('DATASET_ORIGINAL_ENVELOPE_INVALID')
                request=p['request_id'];_scope(p['native_scope'])
                if not isinstance(request,str) or REQUEST_ID.fullmatch(request) is None or request in requests:
                    raise DatasetContractError('DATASET_ORIGINAL_REQUEST_INVALID')
                requested=_candidate(p['requested_manifest']);published=_candidate(p['manifest'])
                now=native_integer(p['recorded_at_ms'],maximum=253402300799000)
                expected=requested.body()|{'created_at':_stamp(now)};record_id=published.body()['record_id']
                fingerprint=canonical_hash({'manifest':requested.body(),'native_scope':p['native_scope']})
                witness=p['source_witness_digest']
                if (p['request_sha256']!=fingerprint or published.body()!=expected or record_id in records
                        or event.correlation_id!=record_id or event.event_time_ms!=now or event.received_time_ms!=now
                        or now<prior or not isinstance(witness,str) or len(witness)!=64
                        or any(char not in '0123456789abcdef' for char in witness)):
                    raise DatasetContractError('DATASET_ORIGINAL_IDENTITY_CLOCK_OR_WITNESS_INVALID')
                requests.add(request);records.add(record_id);prior=now;rows.append(event)
            if len(rows)!=count or not self.ledger.verify_chain()[0]:
                raise DatasetContractError('DATASET_ORIGINAL_LEDGER_READBACK_UNAVAILABLE')
        return rows,size

    @staticmethod
    def _receipt(event):
        p=event.payload;manifest=_candidate(p['manifest'])
        return {'record_ref':event.hash,'request_id':p['request_id'],'record_id':manifest.body()['record_id'],
            'manifest_sha256':manifest.digest,'available_at_ms':event.received_time_ms,
            'status':'CANDIDATE_PUBLISHED_NOT_ADMITTED','current_source_use_verified':False,
            'qualified_for_research':False,'authority_effect':'NONE'}

    def lookup(self,request_id):
        if not isinstance(request_id,str) or REQUEST_ID.fullmatch(request_id) is None:
            raise DatasetContractError('DATASET_REQUEST_ID_INVALID')
        self._outside_transaction()
        rows,_=self._history();event=next((e for e in rows if e.payload['request_id']==request_id),None)
        return None if event is None else self._receipt(event)

    def publish(self,request_id,candidate,*,expected_scope):
        if (not isinstance(request_id,str) or REQUEST_ID.fullmatch(request_id) is None
                or not isinstance(candidate,DatasetManifestCandidate)):
            raise DatasetContractError('DATASET_REQUEST_AND_CANDIDATE_REQUIRED')
        _scope(expected_scope);scope=json.loads(canonical_json(expected_scope));requested=candidate.body()
        fingerprint=canonical_hash({'manifest':requested,'native_scope':scope})
        try:
            self._outside_transaction();rows,_=self._history()
        except STORAGE_ERRORS as error:
            raise DatasetContractError('DATASET_STORAGE_UNAVAILABLE_BEFORE_PUBLICATION') from error
        original=next((e for e in rows if e.payload['request_id']==request_id),None)
        if original is not None:
            if original.payload['request_sha256']!=fingerprint:raise DatasetContractError('DATASET_ORIGINAL_REQUEST_CONFLICT')
            return self._receipt(original)
        if self.inspector is None:raise DatasetContractError('DATASET_SOURCE_INSPECTOR_UNAVAILABLE')
        # File/Parquet/source work does not hold the SQL writer lock.
        inspection=self.inspector.inspect(candidate,expected_scope=scope)
        witness=canonical_hash(inspection['resolved_source_facts']);requested_publication=False;confirmation_needed=False
        try:
            self._outside_transaction()
            with self.ledger.atomic():
                rows,size=self._history();original=next((e for e in rows if e.payload['request_id']==request_id),None)
                if original is not None:
                    if original.payload['request_sha256']!=fingerprint:raise DatasetContractError('DATASET_ORIGINAL_REQUEST_CONFLICT')
                    confirmation_needed=True
                else:
                    if len(rows)>=self.max_events or any(e.payload['manifest']['record_id']==requested['record_id'] for e in rows):
                        raise DatasetContractError('DATASET_RECORD_ID_OR_EVENT_CAPACITY_CONFLICT')
                    now=native_integer(self.clock(),maximum=253402300799000)
                    if rows and now<rows[-1].received_time_ms:raise DatasetContractError('DATASET_CREATION_CLOCK_MOVED_BACKWARDS')
                    published=_candidate(requested|{'created_at':_stamp(now)})
                    payload={'format':'dataset-manifest-candidate-record/1','request_id':request_id,
                        'request_sha256':fingerprint,'requested_manifest':requested,'native_scope':scope,
                        'manifest':published.body(),'source_witness_digest':witness,'recorded_at_ms':now}
                    original=make_event(EventKind.DATASET_MANIFEST_CANDIDATE,PRODUCER,payload,
                        event_time_ms=now,received_time_ms=now,correlation_id=published.body()['record_id'])
                    if size+len(canonical_json(original.body()).encode())>self.max_bytes:
                        raise DatasetContractError('DATASET_PUBLICATION_BYTE_CAPACITY')
                    requested_publication=True;self.ledger.append(original)
            confirmation_needed=True;confirmed=self.lookup(request_id)
            if confirmed is None or confirmed['record_ref']!=original.hash:
                raise DatasetPublicationUnknown('DATASET_ORIGINAL_PUBLICATION_READBACK_UNAVAILABLE')
            return confirmed
        except DatasetPublicationUnknown:
            raise
        except STORAGE_ERRORS as error:
            if requested_publication or confirmation_needed:
                raise DatasetPublicationUnknown('DATASET_PUBLICATION_UNKNOWN_RECONCILE_ORIGINAL_REQUEST') from error
            raise DatasetContractError('DATASET_STORAGE_UNAVAILABLE_BEFORE_PUBLICATION') from error

    def inspect(self,request_id):
        if not isinstance(request_id,str) or REQUEST_ID.fullmatch(request_id) is None:
            raise DatasetContractError('DATASET_REQUEST_ID_INVALID')
        self._outside_transaction()
        rows,_=self._history();event=next((e for e in rows if e.payload['request_id']==request_id),None)
        if event is None:return None
        if self.inspector is None:raise DatasetContractError('DATASET_SOURCE_INSPECTOR_UNAVAILABLE')
        candidate=_candidate(event.payload['manifest'])
        current=self.inspector.inspect(candidate,expected_scope=event.payload['native_scope'])
        if canonical_hash(current['resolved_source_facts'])!=event.payload['source_witness_digest']:
            raise DatasetContractError('DATASET_ORIGINAL_SOURCE_WITNESS_CONFLICT')
        return {'publication':self._receipt(event),'manifest':candidate.body(),'current_inspection':current}
