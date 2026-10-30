"""Original native cash -> balanced projections in the existing VATI ledger.

This is neither a second financial journal nor a payment/settlement authority.
Original requests and native movement identities cannot be rebound or replayed
as another cash effect. Uncertain publication reconciles its original request.
"""
import re
import sqlite3
import time
from decimal import Decimal
from fractions import Fraction

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import EventKind, make_event
from vati.core.ledger import LedgerError
from vati.core.units import UnitError
from vati.funding.journal import FundingBook
from vati.funding.native import native_int
from vati.funding.postings import FinancialMovement
from vati.funding.deal_journal import DealBook
from vati.funding.close_postings import FinancialCloseMovement

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


def _close_request(scope_hash,native_id,statement_ref,balance_anchor_ref,anchor_native_id=None):
    return _source_request(scope_hash,native_id,statement_ref)|{
        'balance_anchor_ref':_digest(balance_anchor_ref),
        'anchor_native_id':None if anchor_native_id is None else str(native_int(anchor_native_id,minimum=1))}


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

    def _history(self,*,anchor_refs=()):
        try:
            return self._read_history(anchor_refs=anchor_refs)
        except UnitError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError) as error:
            raise UnitError('FINANCIAL_ORIGINAL_PROJECTION_INVALID') from error

    def _read_history(self,*,anchor_refs=()):
        rows=[]; size=0; requests=set(); movements=set(); prior=-1
        with self.ledger.read_snapshot():
            count=self.ledger.count(EventKind.FINANCIAL_MOVEMENT)
            source_count=sum(self.ledger.count(k) for k in (EventKind.FUNDING_STATEMENT,EventKind.FUNDING_DEAL_STATEMENT))
            if count > self.max_movements or source_count > self.max_source_statements:
                raise UnitError('FINANCIAL_PROJECTION_EVENT_CAPACITY')
            if not self.ledger.verify_chain()[0]:
                raise UnitError('FINANCIAL_ORIGINAL_JOURNAL_INTEGRITY_UNAVAILABLE')
            events=list(self.ledger.iter(EventKind.FINANCIAL_MOVEMENT))
            wanted=set(anchor_refs)
            for event in events:
                p=event.payload
                if isinstance(p,dict) and isinstance(p.get('source'),dict) and 'balance_anchor_ref' in p['source']:
                    wanted.add(_digest(p['source']['balance_anchor_ref']))
            sources={}
            original_sources=[*self.ledger.iter(EventKind.FUNDING_STATEMENT),
                *self.ledger.iter(EventKind.FUNDING_DEAL_STATEMENT)]
            available={e.hash for e in original_sources}
            if wanted-available:
                original_sources.extend(e for e in self.ledger.iter(EventKind.ACCOUNT_SNAPSHOT) if e.hash in wanted-available)
            if len(original_sources)>self.max_source_statements:
                raise UnitError('FINANCIAL_PROJECTION_EVENT_CAPACITY')
            for source in original_sources:
                size+=len(canonical_json(source.body()).encode())
                if size > self.max_bytes or source.hash in sources:
                    raise UnitError('FINANCIAL_SOURCE_BYTE_CAPACITY_OR_DUPLICATE_REFERENCE')
                sources[source.hash]=source
            if len(sources) != len(original_sources):
                raise UnitError('FINANCIAL_ORIGINAL_SOURCE_READBACK_COUNT_INVALID')
            for event in events:
                size+=len(canonical_json(event.body()).encode()); p=event.payload
                if size > self.max_bytes or len(rows) >= self.max_movements:
                    raise UnitError('FINANCIAL_PROJECTION_BYTE_OR_EVENT_CAPACITY')
                if (event.kind is not EventKind.FINANCIAL_MOVEMENT or event.producer != PRODUCER
                        or type(event.schema_version) is not int
                        or event.schema_version != 1 or event.decision_time_ms is not None
                        or event.hash != canonical_hash(event.body()) or not isinstance(p,dict)
                        or set(p) != {'format','request_id','request_sha256','source','movement'}
                        or p['format'] not in {'native-financial-movement-record/1','native-financial-close-record/1'}):
                    raise UnitError('FINANCIAL_ORIGINAL_ENVELOPE_INVALID')
                request=p['request_id']; source=p['source']
                if (not isinstance(request,str) or REQUEST.fullmatch(request) is None or request in requests
                        or not isinstance(source,dict)
                        or not isinstance(source['native_id'],str) or NATIVE_ID.fullmatch(source['native_id']) is None):
                    raise UnitError('FINANCIAL_ORIGINAL_REQUEST_INVALID')
                if p['format']=='native-financial-close-record/1':
                    if set(source)!={'scope_hash','native_id','statement_ref','balance_anchor_ref','anchor_native_id'}:
                        raise UnitError('FINANCIAL_ORIGINAL_REQUEST_INVALID')
                    anchor_id=source['anchor_native_id']
                    if anchor_id is not None and (not isinstance(anchor_id,str) or NATIVE_ID.fullmatch(anchor_id)is None):
                        raise UnitError('FINANCIAL_ORIGINAL_REQUEST_INVALID')
                    expected=_close_request(source['scope_hash'],int(source['native_id']),source['statement_ref'],
                        source['balance_anchor_ref'],None if anchor_id is None else int(anchor_id))
                else:
                    if set(source)!={'scope_hash','native_id','statement_ref'}:
                        raise UnitError('FINANCIAL_ORIGINAL_REQUEST_INVALID')
                    expected=_source_request(source['scope_hash'],int(source['native_id']),source['statement_ref'])
                if source != expected or p['request_sha256'] != canonical_hash(expected):
                    raise UnitError('FINANCIAL_ORIGINAL_SOURCE_IDENTITY_INVALID')
                original=sources.get(source['statement_ref'])
                if original is None:
                    raise UnitError('FINANCIAL_ORIGINAL_NATIVE_STATEMENT_UNAVAILABLE')
                actual=self._movement(source,sources,event.received_time_ms)
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
        is_close='balance_anchor_ref' in requested
        facts=(DealBook(self.ledger) if is_close else FundingBook(self.ledger)).observations(requested['scope_hash'])
        if facts['state'] != 'OBSERVED':
            raise UnitError('FINANCIAL_NATIVE_SOURCE_UNAVAILABLE_OR_CONFLICTED')
        row_field,label=('deals','deal') if is_close else ('movements','movement')
        row=next((r for r in facts[row_field] if str(r[label]['native_id'])==requested['native_id']),None)
        if row is None or row['original_statement_ref'] != requested['statement_ref']:
            raise UnitError('FINANCIAL_ORIGINAL_NATIVE_MOVEMENT_REFERENCE_CONFLICT')
        if is_close or any(r['deal']['close'] is not None
                for r in DealBook(self.ledger).observations(requested['scope_hash'])['deals']):
            self._balance_points(requested['scope_hash'])
        event=sources.get(requested['statement_ref'])
        if event is None:
            raise UnitError('FINANCIAL_ORIGINAL_NATIVE_STATEMENT_UNAVAILABLE')
        return event

    def _balance_points(self,scope_hash):
        """Original native versions; source repetition is not a second effect."""
        from vati.funding.reconciliation import _marks
        if self.ledger.count(EventKind.ACCOUNT_SNAPSHOT)>100000:
            raise UnitError('FINANCIAL_NATIVE_BALANCE_ANCHOR_CAPACITY')
        cash=FundingBook(self.ledger).observations(scope_hash)
        deals=DealBook(self.ledger).observations(scope_hash)
        if any(f['state']=='CONFLICT' for f in (cash,deals)):
            raise UnitError('FINANCIAL_NATIVE_SOURCE_UNAVAILABLE_OR_CONFLICTED')
        points={};effects={}
        def add(version,balance,ref,native_id,available,kind):
            if version is None:return
            native_int(version,minimum=0)
            amount=Fraction(Decimal(balance));known=points.get(version)
            if known is not None and known['balance']!=amount:
                raise UnitError('FINANCIAL_NATIVE_BALANCE_VERSION_CONFLICT')
            if kind!='MARK':
                identity=(kind,native_id)
                if version in effects and effects[version]!=identity:
                    raise UnitError('FINANCIAL_NATIVE_BALANCE_VERSION_CONFLICT')
                effects[version]=identity
            candidate={'balance':amount,'record_ref':ref,'native_id':native_id,'available_at_ms':available}
            order=lambda p:(p['available_at_ms'],p['record_ref'],p['native_id'] or 0)
            if known is None or order(candidate)<order(known):points[version]=candidate
        for event,mark in _marks(self.ledger,scope_hash):
            add(mark.balance_version,str(mark.balance),event.hash,None,event.received_time_ms,'MARK')
        for observed in cash['movements']:
            row=observed['movement']
            add(row['balance_version'],row['balance_after'],observed['original_statement_ref'],
                row['native_id'],observed['received_at_ms'],'CASH')
        for observed in deals['deals']:
            row=observed['deal'];detail=row['close']
            if detail is not None:
                add(detail['balance_version'],detail['balance_after'],observed['original_statement_ref'],
                    row['native_id'],observed['received_at_ms'],'CLOSE')
        return points

    @staticmethod
    def _movement(requested,sources,at):
        source=sources.get(requested['statement_ref'])
        if source is None:raise UnitError('FINANCIAL_ORIGINAL_NATIVE_STATEMENT_UNAVAILABLE')
        native_id=int(requested['native_id'])
        if 'balance_anchor_ref' in requested:
            anchor=sources.get(requested['balance_anchor_ref'])
            if anchor is None:raise UnitError('FINANCIAL_ORIGINAL_BALANCE_ANCHOR_UNAVAILABLE')
            anchor_id=requested['anchor_native_id']
            return FinancialCloseMovement(source,native_id,anchor,
                anchor_native_id=None if anchor_id is None else int(anchor_id),recorded_at_ms=at).body()
        return FinancialMovement(source,native_id,recorded_at_ms=at).body()

    def publish(self, request_id, *, scope_hash, native_id, statement_ref):
        return self._publish(request_id,_source_request(scope_hash,native_id,statement_ref))

    def publish_close(self,request_id,*,scope_hash,native_id,statement_ref,balance_anchor_ref,anchor_native_id=None):
        return self._publish(request_id,_close_request(scope_hash,native_id,statement_ref,balance_anchor_ref,anchor_native_id))

    def _publish(self,request_id,requested):
        if not isinstance(request_id,str) or REQUEST.fullmatch(request_id) is None:
            raise UnitError('FINANCIAL_REQUEST_ID_INVALID')
        fingerprint=canonical_hash(requested)
        anchors=(requested['balance_anchor_ref'],) if 'balance_anchor_ref' in requested else ()
        started=False; confirmation_needed=False
        try:
            self._transaction(publication=True)
            rows,_,_=self._history(anchor_refs=anchors) if anchors else self._history()
            original=next((e for e in rows if e.payload['request_id']==request_id),None)
            if original is not None:
                if original.payload['request_sha256'] != fingerprint:
                    raise UnitError('FINANCIAL_ORIGINAL_REQUEST_CONFLICT')
                return self._receipt(original)
            with self.ledger.atomic():
                rows,size,sources=self._history(anchor_refs=anchors) if anchors else self._history()
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
                    movement=self._movement(requested,sources,now)
                    if len(rows) >= self.max_movements:
                        raise UnitError('FINANCIAL_PUBLICATION_EVENT_CAPACITY')
                    if any(e.payload['movement']['movement_id']==movement['movement_id'] for e in rows):
                        raise UnitError('FINANCIAL_NATIVE_MOVEMENT_ALREADY_POSTED_USE_ORIGINAL_REQUEST')
                    payload={'format':'native-financial-close-record/1' if anchors else 'native-financial-movement-record/1','request_id':request_id,
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

    def _source_view(self,scope_hash):
        cash=FundingBook(self.ledger).observations(scope_hash)
        deals=DealBook(self.ledger).observations(scope_hash)
        originals={('CTRADER_NATIVE_CASH',str(r['movement']['native_id'])):r for r in cash['movements']}
        closes=[r for r in deals['deals'] if r['deal']['close'] is not None]
        originals.update({('CTRADER_NATIVE_CLOSE',str(r['deal']['native_id'])):r for r in closes})
        state=cash['state'];points={};reason=None
        if closes:
            state='CONFLICT' if 'CONFLICT' in (cash['state'],deals['state']) else 'OBSERVED'
            if state!='CONFLICT':
                try:points=self._balance_points(scope_hash)
                except UnitError as error:state='CONFLICT';reason=str(error)
        return {'state':state,'originals':originals,'points':points,'reason':reason}

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
        facts=self._source_view(scope_hash)
        if facts['state']=='CONFLICT':
            return self.projection(scope_hash)
        posted={(e.payload['movement']['source_kind'],e.payload['movement']['native_id']) for e in rows
            if e.payload['movement']['scope_hash']==scope_hash}
        pending=[(key,row) for key,row in facts['originals'].items() if key not in posted]
        def order(item):
            (kind,native_id),row=item
            version=row['deal']['close']['balance_version'] if kind=='CTRADER_NATIVE_CLOSE' else 0
            return (kind=='CTRADER_NATIVE_CLOSE',version is None,version or 0,int(native_id))
        pending.sort(key=order);published=0;unresolved=[]
        for (kind,identity_id),row in pending:
            if published>=max_batch:break
            native_id=int(identity_id)
            identity=canonical_hash({'source_kind':kind,'scope_hash':scope_hash,'native_id':identity_id})
            if kind=='CTRADER_NATIVE_CASH':
                self.publish('native-cash:'+identity,scope_hash=scope_hash,native_id=native_id,
                    statement_ref=row['original_statement_ref'])
            else:
                version=row['deal']['close']['balance_version']
                anchor=facts['points'].get(version-1) if type(version)is int and version>0 else None
                if anchor is None:
                    unresolved.append({'native_id':identity_id,'reason':'FINANCIAL_ORIGINAL_BALANCE_ANCHOR_UNAVAILABLE'
                        if type(version)is int and version>0 else 'FINANCIAL_NATIVE_CLOSE_ORDER_UNAVAILABLE'})
                    continue
                try:
                    self.publish_close('native-close:'+identity,scope_hash=scope_hash,native_id=native_id,
                        statement_ref=row['original_statement_ref'],balance_anchor_ref=anchor['record_ref'],
                        anchor_native_id=anchor['native_id'])
                except UnitError as error:
                    unresolved.append({'native_id':identity_id,'reason':str(error)})
                    continue
            published+=1
        result=self.projection(scope_hash)
        if unresolved:
            result['unresolved_close_count']=len(unresolved)
            result['unresolved_closes']=unresolved[:max_batch]
        return result

    def projection(self, scope_hash, *, limit=100):
        """Read-only owner projection; historical postings never certify cash use."""
        _digest(scope_hash)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise UnitError('FINANCIAL_PROJECTION_READ_CAPACITY_INVALID')
        self._transaction()
        with self.ledger.read_snapshot():
            rows,_,_=self._history()
            facts=self._source_view(scope_hash)
            originals={key:r['original_statement_ref'] for key,r in facts['originals'].items()}
            selected=[e for e in rows if e.payload['movement']['scope_hash']==scope_hash]
            current=facts['state']=='OBSERVED' and all(
                originals.get((e.payload['movement']['source_kind'],e.payload['source']['native_id']))==e.payload['source']['statement_ref']
                for e in selected)
            posted={(e.payload['movement']['source_kind'],e.payload['source']['native_id']) for e in selected}
            pending=len(set(originals)-posted)
            state=('CONFLICT' if facts['state']=='CONFLICT' or (selected and not current)
                else 'NO_DATA' if facts['state']=='NO_DATA'
                else 'PENDING' if pending else 'SOURCE_POSTED_NOT_SETTLEMENT_OR_RISK_ADMISSION')
            result={'schema':'vati.financial-movement-projection/1','state':state,
                'scope_hash':scope_hash,'source_state':facts['state'],
                'original_movement_count':len(originals),'posted_count':len(selected),
                'pending_count':pending,'movements_truncated':len(selected)>limit,
                'movements':[{'publication':self._receipt(e),'movement':e.payload['movement']}
                    for e in selected[-limit:]],
                'current_original_source_verified':current,
                'settlement_qualification':'NOT_ISSUED','risk_capital_qualified':False,
                'execution_authority':False}
            if facts['reason'] is not None:result['reason']=facts['reason']
            unresolved=[]
            for (kind,native_id),observed in facts['originals'].items():
                if facts['state']=='CONFLICT' or kind!='CTRADER_NATIVE_CLOSE' or (kind,native_id) in posted:continue
                version=observed['deal']['close']['balance_version']
                reason=('FINANCIAL_NATIVE_CLOSE_ORDER_UNAVAILABLE' if type(version)is not int or version<1
                    else 'FINANCIAL_ORIGINAL_BALANCE_ANCHOR_UNAVAILABLE' if version-1 not in facts['points'] else None)
                if reason is not None:unresolved.append({'native_id':native_id,'reason':reason})
            if unresolved:
                result['unresolved_close_count']=len(unresolved)
                result['unresolved_closes']=unresolved[:limit]
            return result
