"""Original native cash -> balanced projections in the existing VATI ledger.

This is neither a second financial journal nor a payment/settlement authority.
Original requests and native movement identities cannot be rebound or replayed
as another cash effect. Uncertain publication reconciles its original request.
"""
import re
import sqlite3
import time

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import EventKind, make_event
from vati.core.ledger import LedgerError
from vati.core.units import UnitError
from vati.funding.journal import FundingBook
from vati.funding.native import native_int
from vati.funding.postings import FinancialMovement

try:
    from psycopg import Error as PostgresError
except ImportError:
    STORAGE_ERRORS = (OSError, sqlite3.Error, LedgerError)
else:
    STORAGE_ERRORS = (OSError, sqlite3.Error, LedgerError, PostgresError)

PRODUCER = 'vati-native-cash-posting'
REQUEST = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', re.ASCII)
DIGEST = re.compile(r'[0-9a-f]{64}', re.ASCII)
NATIVE_ID = re.compile(r'[1-9][0-9]{0,18}', re.ASCII)


class MovementPublicationUnknown(OSError):
    def __init__(self, reason, *, request_id=None):
        super().__init__(reason)
        self.request_id=request_id


def _digest(value):
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise UnitError('FINANCIAL_SOURCE_REFERENCE_INVALID')
    return value


def _source_request(scope_hash, native_id, statement_ref):
    return {'scope_hash':_digest(scope_hash),'native_id':str(native_int(native_id, minimum=1)),
        'statement_ref':_digest(statement_ref)}


class FinancialMovementBook:
    def __init__(self, ledger, *, clock=None, max_movements=10000,
                 max_source_statements=10000, max_bytes=64*1024**2):
        if ledger is None:
            raise UnitError('FINANCIAL_EXISTING_LEDGER_REQUIRED')
        if (type(max_movements) is not int or not 1 <= max_movements <= 100000
                or type(max_source_statements) is not int or not 1 <= max_source_statements <= 100000
                or type(max_bytes) is not int or not 1 <= max_bytes <= 256*1024**2):
            raise UnitError('FINANCIAL_PROJECTION_CAPACITY_INVALID')
        self.ledger=ledger; self.clock=clock or (lambda:int(time.time()*1000))
        self.max_movements=max_movements; self.max_source_statements=max_source_statements
        self.max_bytes=max_bytes

    def _transaction(self, *, publication=False):
        connection=getattr(self.ledger,'_conn',None)
        if connection is None:
            raise UnitError('FINANCIAL_TRANSACTION_STATE_UNAVAILABLE')
        if hasattr(connection,'in_transaction'):
            active=connection.in_transaction
        elif hasattr(connection,'info'):
            active=connection.info.transaction_status != 0
        else:
            raise UnitError('FINANCIAL_TRANSACTION_STATE_UNAVAILABLE')
        if active and (publication or not getattr(self.ledger,'_read_snapshot_depth',0)):
            raise UnitError('FINANCIAL_PROJECTION_REQUIRES_OWN_WRITER_TRANSACTION')

    def _history(self):
        try:
            return self._read_history()
        except UnitError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError) as error:
            raise UnitError('FINANCIAL_ORIGINAL_PROJECTION_INVALID') from error

    def _read_history(self):
        rows=[]; size=0; requests=set(); movements=set(); prior=-1
        with self.ledger.read_snapshot():
            count=self.ledger.count(EventKind.FINANCIAL_MOVEMENT)
            source_count=self.ledger.count(EventKind.FUNDING_STATEMENT)
            if count > self.max_movements or source_count > self.max_source_statements:
                raise UnitError('FINANCIAL_PROJECTION_EVENT_CAPACITY')
            if not self.ledger.verify_chain()[0]:
                raise UnitError('FINANCIAL_ORIGINAL_JOURNAL_INTEGRITY_UNAVAILABLE')
            sources={}
            for source in self.ledger.iter(EventKind.FUNDING_STATEMENT):
                size+=len(canonical_json(source.body()).encode())
                if size > self.max_bytes or source.hash in sources:
                    raise UnitError('FINANCIAL_SOURCE_BYTE_CAPACITY_OR_DUPLICATE_REFERENCE')
                sources[source.hash]=source
            if len(sources) != source_count:
                raise UnitError('FINANCIAL_ORIGINAL_SOURCE_READBACK_COUNT_INVALID')
            for event in self.ledger.iter(EventKind.FINANCIAL_MOVEMENT):
                size+=len(canonical_json(event.body()).encode()); p=event.payload
                if size > self.max_bytes or len(rows) >= self.max_movements:
                    raise UnitError('FINANCIAL_PROJECTION_BYTE_OR_EVENT_CAPACITY')
                if (event.kind is not EventKind.FINANCIAL_MOVEMENT or event.producer != PRODUCER
                        or type(event.schema_version) is not int
                        or event.schema_version != 1 or event.decision_time_ms is not None
                        or event.hash != canonical_hash(event.body()) or not isinstance(p,dict)
                        or set(p) != {'format','request_id','request_sha256','source','movement'}
                        or p['format'] != 'native-financial-movement-record/1'):
                    raise UnitError('FINANCIAL_ORIGINAL_ENVELOPE_INVALID')
                request=p['request_id']; source=p['source']
                if (not isinstance(request,str) or REQUEST.fullmatch(request) is None or request in requests
                        or not isinstance(source,dict) or set(source) != {'scope_hash','native_id','statement_ref'}
                        or not isinstance(source['native_id'],str) or NATIVE_ID.fullmatch(source['native_id']) is None):
                    raise UnitError('FINANCIAL_ORIGINAL_REQUEST_INVALID')
                expected=_source_request(source['scope_hash'],int(source['native_id']),source['statement_ref'])
                if source != expected or p['request_sha256'] != canonical_hash(expected):
                    raise UnitError('FINANCIAL_ORIGINAL_SOURCE_IDENTITY_INVALID')
                original=sources.get(source['statement_ref'])
                if original is None:
                    raise UnitError('FINANCIAL_ORIGINAL_NATIVE_STATEMENT_UNAVAILABLE')
                actual=FinancialMovement(original,int(source['native_id']),recorded_at_ms=event.received_time_ms).body()
                if (type(event.received_time_ms) is not int or type(event.event_time_ms) is not int
                        or canonical_json(actual) != canonical_json(p['movement'])
                        or actual['scope_hash'] != source['scope_hash']
                        or event.correlation_id != actual['movement_id']
                        or event.event_time_ms != actual['occurred_at_ms']
                        or event.received_time_ms < prior or actual['movement_id'] in movements):
                    raise UnitError('FINANCIAL_ORIGINAL_POSTINGS_CLOCK_OR_IDENTITY_INVALID')
                requests.add(request); movements.add(actual['movement_id']); prior=event.received_time_ms
                rows.append(event)
            if len(rows) != count:
                raise UnitError('FINANCIAL_ORIGINAL_READBACK_COUNT_INVALID')
        return rows,size,sources

    @staticmethod
    def _receipt(event):
        movement=event.payload['movement']
        return {'record_ref':event.hash,'request_id':event.payload['request_id'],
            'movement_id':movement['movement_id'],'scope_hash':movement['scope_hash'],
            'native_id':movement['native_id'],'available_at_ms':event.received_time_ms,
            'posting_state':movement['state'],'status':'SOURCE_POSTED_NOT_SETTLEMENT_OR_RISK_ADMISSION',
            'current_source_use_verified':False,'settlement_qualification':'NOT_ISSUED',
            'risk_capital_qualified':False,'execution_authority':False}

    def lookup(self, request_id):
        if not isinstance(request_id,str) or REQUEST.fullmatch(request_id) is None:
            raise UnitError('FINANCIAL_REQUEST_ID_INVALID')
        self._transaction(); rows,_,_=self._history()
        event=next((e for e in rows if e.payload['request_id']==request_id),None)
        return None if event is None else self._receipt(event)

    def _current_source(self, requested, sources):
        facts=FundingBook(self.ledger).observations(requested['scope_hash'])
        if facts['state'] != 'OBSERVED':
            raise UnitError('FINANCIAL_NATIVE_SOURCE_UNAVAILABLE_OR_CONFLICTED')
        row=next((r for r in facts['movements'] if str(r['movement']['native_id'])==requested['native_id']),None)
        if row is None or row['original_statement_ref'] != requested['statement_ref']:
            raise UnitError('FINANCIAL_ORIGINAL_NATIVE_MOVEMENT_REFERENCE_CONFLICT')
        event=sources.get(requested['statement_ref'])
        if event is None:
            raise UnitError('FINANCIAL_ORIGINAL_NATIVE_STATEMENT_UNAVAILABLE')
        return event

    def publish(self, request_id, *, scope_hash, native_id, statement_ref):
        if not isinstance(request_id,str) or REQUEST.fullmatch(request_id) is None:
            raise UnitError('FINANCIAL_REQUEST_ID_INVALID')
        requested=_source_request(scope_hash,native_id,statement_ref); fingerprint=canonical_hash(requested)
        started=False; confirmation_needed=False
        try:
            self._transaction(publication=True); rows,_,_=self._history()
            original=next((e for e in rows if e.payload['request_id']==request_id),None)
            if original is not None:
                if original.payload['request_sha256'] != fingerprint:
                    raise UnitError('FINANCIAL_ORIGINAL_REQUEST_CONFLICT')
                return self._receipt(original)
            with self.ledger.atomic():
                rows,size,sources=self._history()
                original=next((e for e in rows if e.payload['request_id']==request_id),None)
                if original is not None:
                    if original.payload['request_sha256'] != fingerprint:
                        raise UnitError('FINANCIAL_ORIGINAL_REQUEST_CONFLICT')
                    confirmation_needed=True
                else:
                    source=self._current_source(requested,sources)
                    now=native_int(self.clock(),minimum=source.received_time_ms)
                    if rows and now < rows[-1].received_time_ms:
                        raise UnitError('FINANCIAL_PUBLICATION_CLOCK_MOVED_BACKWARDS')
                    movement=FinancialMovement(source,native_id,recorded_at_ms=now).body()
                    if len(rows) >= self.max_movements:
                        raise UnitError('FINANCIAL_PUBLICATION_EVENT_CAPACITY')
                    if any(e.payload['movement']['movement_id']==movement['movement_id'] for e in rows):
                        raise UnitError('FINANCIAL_NATIVE_MOVEMENT_ALREADY_POSTED_USE_ORIGINAL_REQUEST')
                    payload={'format':'native-financial-movement-record/1','request_id':request_id,
                        'request_sha256':fingerprint,'source':requested,'movement':movement}
                    original=make_event(EventKind.FINANCIAL_MOVEMENT,PRODUCER,payload,
                        event_time_ms=movement['occurred_at_ms'],received_time_ms=now,
                        correlation_id=movement['movement_id'])
                    if size+len(canonical_json(original.body()).encode()) > self.max_bytes:
                        raise UnitError('FINANCIAL_PUBLICATION_BYTE_CAPACITY')
                    started=True; self.ledger.append(original)
            confirmation_needed=True; confirmed=self.lookup(request_id)
            if confirmed is None or confirmed['record_ref'] != original.hash:
                raise MovementPublicationUnknown('FINANCIAL_ORIGINAL_PUBLICATION_READBACK_UNAVAILABLE',request_id=request_id)
            return confirmed
        except MovementPublicationUnknown:
            raise
        except STORAGE_ERRORS as error:
            if started or confirmation_needed:
                raise MovementPublicationUnknown('FINANCIAL_PUBLICATION_UNKNOWN_RECONCILE_ORIGINAL_REQUEST',request_id=request_id) from error
            raise UnitError('FINANCIAL_STORAGE_UNAVAILABLE_BEFORE_PUBLICATION') from error

    def inspect(self, request_id):
        receipt=self.lookup(request_id)
        if receipt is None:
            return None
        rows,_,sources=self._history(); original=next(e for e in rows if e.hash==receipt['record_ref'])
        try:
            self._current_source(original.payload['source'],sources)
        except UnitError:
            return {'publication':receipt,'movement':original.payload['movement'],
                'source_state':'UNAVAILABLE_OR_CONFLICTED','current_original_source_verified':False,
                'risk_capital_qualified':False,'execution_authority':False}
        return {'publication':receipt,'movement':original.payload['movement'],
            'source_state':'ORIGINAL_OBSERVATION_VERIFIED','current_original_source_verified':True,
            'risk_capital_qualified':False,'execution_authority':False}

    def materialize(self, scope_hash, *, max_batch=100):
        """Resume bounded derived work from original facts, including older windows.

        The native collection cursor cannot stand in for this recovery cursor:
        a source commit may survive a crash before its projection was posted.
        Every publication still takes its own writer lock and original readback.
        """
        _digest(scope_hash)
        if type(max_batch) is not int or not 1 <= max_batch <= 1000:
            raise UnitError('FINANCIAL_PROJECTION_BATCH_CAPACITY_INVALID')
        self._transaction(publication=True)
        rows,_,_=self._history()
        facts=FundingBook(self.ledger).observations(scope_hash)
        if facts['state']=='CONFLICT':
            return self.projection(scope_hash)
        posted={e.payload['movement']['native_id'] for e in rows
            if e.payload['movement']['scope_hash']==scope_hash}
        pending=[r for r in facts['movements'] if str(r['movement']['native_id']) not in posted]
        for row in pending[:max_batch]:
            native_id=row['movement']['native_id']
            identity=canonical_hash({'source_kind':'CTRADER_NATIVE_CASH',
                'scope_hash':scope_hash,'native_id':str(native_id)})
            self.publish('native-cash:'+identity,scope_hash=scope_hash,native_id=native_id,
                statement_ref=row['original_statement_ref'])
        return self.projection(scope_hash)

    def projection(self, scope_hash, *, limit=100):
        """Read-only owner projection; historical postings never certify cash use."""
        _digest(scope_hash)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise UnitError('FINANCIAL_PROJECTION_READ_CAPACITY_INVALID')
        self._transaction()
        with self.ledger.read_snapshot():
            rows,_,_=self._history()
            facts=FundingBook(self.ledger).observations(scope_hash)
            originals={str(r['movement']['native_id']):r['original_statement_ref']
                for r in facts['movements']}
            selected=[e for e in rows if e.payload['movement']['scope_hash']==scope_hash]
            current=facts['state']=='OBSERVED' and all(
                originals.get(e.payload['source']['native_id'])==e.payload['source']['statement_ref']
                for e in selected)
            posted={e.payload['source']['native_id'] for e in selected}
            pending=len(set(originals)-posted)
            state=('CONFLICT' if facts['state']=='CONFLICT' or (selected and not current)
                else 'NO_DATA' if facts['state']=='NO_DATA'
                else 'PENDING' if pending else 'SOURCE_POSTED_NOT_SETTLEMENT_OR_RISK_ADMISSION')
            return {'schema':'vati.financial-movement-projection/1','state':state,
                'scope_hash':scope_hash,'source_state':facts['state'],
                'original_movement_count':len(originals),'posted_count':len(selected),
                'pending_count':pending,'movements_truncated':len(selected)>limit,
                'movements':[{'publication':self._receipt(e),'movement':e.payload['movement']}
                    for e in selected[-limit:]],
                'current_original_source_verified':current,
                'settlement_qualification':'NOT_ISSUED','risk_capital_qualified':False,
                'execution_authority':False}
