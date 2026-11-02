"""BE-006 §7.9.5 owner assertions over original cash facts, never financial authority.

Only structured classification codes are retained, under the existing append-only
financial audit lifecycle. Withdrawal ends an assertion; it cannot erase history.
"""
from decimal import Decimal, localcontext
import re
import time

from vati.core.canonical import canonical_hash
from vati.core.decimal_context import native_decimal_context
from vati.core.events import EventKind, make_event
from vati.core.ledger import LedgerError
from vati.funding.journal import FundingBook

SCHEMA = 'funding-owner-classification/1'
PRODUCER = 'vati-owner-funding-classification'
LABELS = frozenset({'DEPOSIT','WITHDRAWAL','INTERNAL_TRANSFER','CREDIT','BONUS','FEE','OTHER_INCOME','OTHER_EXPENSE','UNRESOLVED'})
HEX = re.compile(r'^[0-9a-f]{64}$')
OP = re.compile(r'^[a-zA-Z0-9_-]{16,80}$')
FIELDS = {'operation_id','scope_hash','native_id','statement_ref','row_digest','expected_revision','action','label'}
FLAGS = {'provider_facts_changed':False,'settlement_qualified':False,'risk_capital_qualified':False,'execution_authority':False}


class ClassificationError(ValueError):
    def __init__(self,code,status=409):
        self.code,self.status=code,status
        super().__init__(code)


def validate(body):
    if not isinstance(body,dict) or set(body)!=FIELDS:
        raise ClassificationError('FUNDING_LABEL_INPUT_INVALID',422)
    if not isinstance(body['operation_id'],str) or not OP.fullmatch(body['operation_id']):
        raise ClassificationError('FUNDING_LABEL_INPUT_INVALID',422)
    for key in ('scope_hash','statement_ref','row_digest'):
        if not isinstance(body[key],str) or not HEX.fullmatch(body[key]):
            raise ClassificationError('FUNDING_LABEL_INPUT_INVALID',422)
    if type(body['native_id']) is not int or not 1<=body['native_id']<=2**64-1 or type(body['expected_revision']) is not int or not 0<=body['expected_revision']<2**31:
        raise ClassificationError('FUNDING_LABEL_INPUT_INVALID',422)
    if not ((body['action']=='SET' and isinstance(body['label'],str) and body['label'] in LABELS)
            or (body['action']=='WITHDRAW' and body['label'] is None)):
        raise ClassificationError('FUNDING_LABEL_INPUT_INVALID',422)
    return canonical_hash(body)


class ClassificationBook:
    def __init__(self,ledger,*,clock=None):
        self.ledger=ledger
        self.clock=clock or (lambda:int(time.time()*1000))

    def _history(self):
        if not self.ledger.verify_incremental()[0]:
            raise ClassificationError('FUNDING_LABEL_HISTORY_UNKNOWN',503)
        rows=[];heads={};operations=set()
        for event in self.ledger.iter(EventKind.FUNDING_OWNER_CLASSIFICATION):
            p=event.payload
            try:
                if (not isinstance(p,dict) or set(p)!={'schema','request','request_digest','owner_id','device_id','original','revision','previous_ref','created_at_ms','deadline_ms','provenance',*FLAGS}
                        or event.producer!=PRODUCER or p['schema']!=SCHEMA or event.hash!=canonical_hash(event.body())
                        or p['owner_id']!='owner' or not isinstance(p['device_id'],str) or not 1<=len(p['device_id'])<=256
                        or p['provenance']!='OWNER_ASSERTION' or any(p[k] is not False for k in FLAGS)):
                    raise ValueError()
                request=p['request'];digest=validate(request)
                key=(request['scope_hash'],request['native_id'])
                old=heads.get(key)
                if (digest!=p['request_digest'] or request['operation_id'] in operations
                        or p['revision']!=request['expected_revision']+1 or type(p['revision']) is not int
                        or request['expected_revision']!=(old.payload['revision'] if old else 0)
                        or p['previous_ref']!=(old.hash if old else None)
                        or type(p['created_at_ms']) is not int or type(p['deadline_ms']) is not int
                        or p['deadline_ms']!=p['created_at_ms']+300_000
                        or event.event_time_ms!=p['created_at_ms'] or event.received_time_ms!=p['created_at_ms']
                        or event.correlation_id!='funding-label:'+request['scope_hash']):
                    raise ValueError()
                original=p['original']
                if (not isinstance(original,dict) or set(original)!={'scope','movement','statement_ref','row_digest'}
                        or original['statement_ref']!=request['statement_ref'] or original['row_digest']!=request['row_digest']
                        or not isinstance(original['movement'],dict) or original['movement'].get('native_id')!=request['native_id']
                        or canonical_hash(original['movement'])!=request['row_digest']
                        or not isinstance(original['scope'],dict) or canonical_hash(original['scope'])!=request['scope_hash']):
                    raise ValueError()
                # An audit record must still resolve to its actual original source.
                self._original(request,current=False,expected=original)
                operations.add(request['operation_id']);heads[key]=event;rows.append(event)
            except (KeyError,TypeError,ValueError,ArithmeticError,LedgerError) as exc:
                raise ClassificationError('FUNDING_LABEL_HISTORY_UNKNOWN',503) from exc
        return rows,heads

    def _original(self,request,*,current,expected=None):
        try:return self._resolve_original(request,current=current,expected=expected)
        except ClassificationError:raise
        except (KeyError,TypeError,ValueError,ArithmeticError,LedgerError) as exc:
            raise ClassificationError('FUNDING_LABEL_SOURCE_UNKNOWN',503) from exc

    def _resolve_original(self,request,*,current,expected=None):
        """Resolve source through its existing typed original owner, never a caller body."""
        event=next((e for e in self.ledger.iter() if e.hash==request['statement_ref']),None)
        if event is None:raise ClassificationError('FUNDING_LABEL_SOURCE_UNKNOWN',503)
        if event.kind is EventKind.FUNDING_STATEMENT:
            book=FundingBook(self.ledger)
            fields=('provider','environment','native_account_id','deposit_asset_id','currency')
        elif event.kind is EventKind.FUNDING_MT5_STATEMENT:
            from vati.funding.mt5_journal import Mt5FundingBook
            book=Mt5FundingBook(self.ledger)
            # Use the existing producer's canonical identity, not guessed MT5 aliases.
            fields=None
        else:raise ClassificationError('FUNDING_LABEL_SOURCE_UNKNOWN',503)
        for source in self.ledger.iter(book.kind,correlation_id=book.correlation_prefix+request['scope_hash']):
            if not isinstance(source.payload,dict) or not isinstance(source.payload.get('statement'),dict):
                raise ClassificationError('FUNDING_LABEL_SOURCE_UNKNOWN',503)
        originals=book._events(request['scope_hash'])
        if not any(e.hash==event.hash and e.payload['state']=='OBSERVED' for e in originals):
            raise ClassificationError('FUNDING_LABEL_SOURCE_UNKNOWN',503)
        facts=book.observations(request['scope_hash'])
        row=next((r for r in facts['movements'] if r['movement']['native_id']==request['native_id']),None)
        if (row is None or row['original_statement_ref']!=event.hash
                or canonical_hash(row['movement'])!=request['row_digest']):
            raise ClassificationError('FUNDING_LABEL_SOURCE_UNKNOWN',503)
        statement=book.statement_type.from_body(event.payload['statement'])
        if fields is None:
            # Mt5FundingFrame.scope_hash owns this exact shape.
            scope={'provider':'MT5',**{k:getattr(statement,k) for k in ('login','server','currency','demo')}}
        else:scope={k:event.payload['statement'][k] for k in fields}
        original={'scope':scope,'movement':row['movement'],'statement_ref':event.hash,'row_digest':request['row_digest']}
        if canonical_hash(scope)!=request['scope_hash'] or expected is not None and original!=expected:
            raise ClassificationError('FUNDING_LABEL_SOURCE_UNKNOWN',503)
        if current and facts['state']=='CONFLICT':
            raise ClassificationError('FUNDING_LABEL_SOURCE_CONFLICT',409)
        return original

    @staticmethod
    def receipt(event):
        p=event.payload
        return {'operation_id':p['request']['operation_id'],'receipt_ref':event.hash,'request_digest':p['request_digest'],
                'revision':p['revision'],'previous_ref':p['previous_ref'],'state':'ASSERTED' if p['request']['action']=='SET' else 'WITHDRAWN',
                'created_at_ms':p['created_at_ms'],'original_deadline_ms':p['deadline_ms'],'provenance':'OWNER_ASSERTION',**FLAGS}

    def lookup(self,operation_id):
        with self.ledger.read_snapshot():
            rows,heads=self._history()
            event=next((e for e in rows if e.payload['request']['operation_id']==operation_id),None)
            if event is None:raise ClassificationError('FUNDING_LABEL_NOT_FOUND',404)
            p=event.payload;r=p['request'];head=heads[(r['scope_hash'],r['native_id'])]
            try:self._original(r,current=True);current='CURRENT' if head.hash==event.hash else 'SUPERSEDED'
            except ClassificationError:current='UNKNOWN'
            return {'receipt':self.receipt(event),'request':r,'original':p['original'],'actor_device_id':p['device_id'],
                    'current_assertion_state':current,'current_revision':head.payload['revision'],**FLAGS}

    def publish(self,body,*,device_id,received_at_ms,cancelled=lambda:False):
        digest=validate(body)
        if not isinstance(device_id,str) or not 1<=len(device_id)<=256:
            raise ClassificationError('FUNDING_LABEL_OWNER_REFUSED',403)
        if type(received_at_ms) is not int or received_at_ms<0:
            raise ClassificationError('FUNDING_LABEL_INPUT_INVALID',422)
        with self.ledger.atomic():
            rows,heads=self._history()
            existing=next((e for e in rows if e.payload['request']['operation_id']==body['operation_id']),None)
            if existing:
                if existing.payload['request_digest']!=digest or existing.payload['device_id']!=device_id:
                    raise ClassificationError('FUNDING_LABEL_ORIGINAL_CONFLICT',409)
                return self.receipt(existing)
            old=heads.get((body['scope_hash'],body['native_id']))
            if body['expected_revision']!=(old.payload['revision'] if old else 0):
                raise ClassificationError('FUNDING_LABEL_REVISION_CONFLICT',409)
            if body['action']=='WITHDRAW' and (old is None or old.payload['request']['action']=='WITHDRAW'):
                raise ClassificationError('FUNDING_LABEL_NO_CURRENT_ASSERTION',409)
            original=self._original(body,current=True)
            if old and old.payload['original']!=original:
                raise ClassificationError('FUNDING_LABEL_SOURCE_CONFLICT',409)
            if cancelled():raise ClassificationError('FUNDING_LABEL_CANCELLED',409)
            now=self.clock()
            if type(now) is not int or now<received_at_ms or now>=received_at_ms+300_000:
                raise ClassificationError('FUNDING_LABEL_REQUEST_EXPIRED',409)
            event=make_event(EventKind.FUNDING_OWNER_CLASSIFICATION,PRODUCER,
                {'schema':SCHEMA,'request':dict(body),'request_digest':digest,'owner_id':'owner','device_id':device_id,
                 'original':original,'revision':body['expected_revision']+1,'previous_ref':old.hash if old else None,
                 'created_at_ms':received_at_ms,'deadline_ms':received_at_ms+300_000,'provenance':'OWNER_ASSERTION',**FLAGS},
                event_time_ms=received_at_ms,received_time_ms=received_at_ms,correlation_id='funding-label:'+body['scope_hash'])
            self.ledger.append(event)
        return self.receipt(event)

    def overlay(self,scope_hash,*,as_of=None):
        """Descriptive owner basis only. Never feeds native reconciliation/risk."""
        with self.ledger.read_snapshot():
            rows,_=self._history();heads={}
            for event in rows:
                if event.payload['request']['scope_hash']==scope_hash:
                    heads[event.payload['request']['native_id']]=event
                if as_of is not None and event.hash==as_of:break
            if as_of is not None and not any(e.hash==as_of for e in rows):
                raise ClassificationError('FUNDING_LABEL_HISTORY_UNKNOWN',503)
            output=[];totals={};components={}
            for event in heads.values():
                p=event.payload;r=p['request']
                self._original(r,current=as_of is None)
                output.append({'native_id':r['native_id'],'label':r['label'],'receipt':self.receipt(event)})
                if r['action']=='SET':
                    key=(p['original']['scope']['currency'],r['label'])
                    movement=p['original']['movement']
                    with localcontext(native_decimal_context()):
                        if p['original']['scope']['provider']=='MT5':
                            # Preserve the actual MT5 owner's separate double-text
                            # facts; no invented settled delta or unitization.
                            for component in ('profit','commission','swap','fee'):
                                ck=(*key,component)
                                components[ck]=components.get(ck,Decimal(0))+Decimal(movement[component])
                        else:totals[key]=totals.get(key,Decimal(0))+Decimal(movement['delta'])
            return {'state':'AVAILABLE','assertions':output,'descriptive_totals':[{'currency':k[0],'label':k[1],'delta':str(v)} for k,v in sorted(totals.items())],
                    'native_component_totals':[{'currency':k[0],'label':k[1],'component':k[2],'amount':str(v)} for k,v in sorted(components.items())],
                    'basis':'OWNER_ASSERTION_NOT_PROVIDER_RECLASSIFICATION',**FLAGS}
