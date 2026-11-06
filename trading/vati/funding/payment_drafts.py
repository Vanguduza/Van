"""Immutable owner-scoped drafts in the existing VATI SQL ledger.

Nothing here approves, reserves, submits, reconciles or settles money. The
composition owner must supply its existing instrument-retention policy guard.
"""
import time

from vati.core.canonical import canonical_hash,canonical_json
from vati.core.events import EventKind,make_event
from vati.core.ledger import require_committed_source_read,committed_source_snapshot
from vati.funding.payment_contracts import PaymentIntent,_identity,_integer

PRODUCER='vati-payment-draft'
SCHEMA='vati.payment-draft-record/1'


class PaymentDraftError(ValueError):
    pass


class PaymentDraftUnknown(OSError):
    def __init__(self,request_id):
        self.request_id=request_id
        super().__init__('PAYMENT_DRAFT_OUTCOME_UNKNOWN_READ_ORIGINAL_REQUEST')


class PaymentDraftBook:
    def __init__(self,ledger,*,privacy_guard,clock=None,max_records=4096,max_bytes=16*1024**2,max_ledger_events=100000):
        if ledger is None or not callable(privacy_guard):raise PaymentDraftError('PAYMENT_DRAFT_EXISTING_LEDGER_AND_PRIVACY_GUARD_REQUIRED')
        for value,limit in [(max_records,100000),(max_bytes,256*1024**2),(max_ledger_events,1000000)]:
            if type(value) is not int or not 1<=value<=limit:raise PaymentDraftError('PAYMENT_DRAFT_CAPACITY_INVALID')
        self.ledger,self.privacy_guard=ledger,privacy_guard
        self.clock=clock or (lambda:int(time.time()*1000))
        self.max_records,self.max_bytes,self.max_ledger_events=max_records,max_bytes,max_ledger_events

    def _idle(self,*,publication=False):
        require_committed_source_read(self.ledger)
        if publication and getattr(self.ledger,'_read_snapshot_depth',0):
            raise PaymentDraftError('PAYMENT_DRAFT_REQUIRES_OWN_WRITER_TRANSACTION')

    @staticmethod
    def _key(owner,request):return canonical_hash({'owner_ref':owner,'request_id':request})

    def _guard(self,intent):
        try:self.privacy_guard(intent)
        except Exception:raise PaymentDraftError('PAYMENT_DRAFT_RETENTION_BOUNDARY_REFUSED') from None

    def _now(self,*,minimum=0):
        try:now=_integer(self.clock())
        except Exception:raise PaymentDraftError('PAYMENT_DRAFT_STORAGE_CLOCK_UNAVAILABLE') from None
        if now<minimum:raise PaymentDraftError('PAYMENT_DRAFT_STORAGE_CLOCK_REGRESSED')
        return now

    def _history(self):
        rows={};size=0;last=-1
        try:
            with self.ledger.read_snapshot():
                if (self.ledger.count()>self.max_ledger_events or self.ledger.count(EventKind.PAYMENT_DRAFT)>self.max_records):
                    raise PaymentDraftError('PAYMENT_DRAFT_EVENT_CAPACITY')
                if not self.ledger.verify_chain()[0]:raise PaymentDraftError('PAYMENT_DRAFT_JOURNAL_INTEGRITY_UNAVAILABLE')
                for event in self.ledger.iter(EventKind.PAYMENT_DRAFT):
                    size+=len(canonical_json(event.body()).encode())
                    if size>self.max_bytes or len(rows)>=self.max_records:raise PaymentDraftError('PAYMENT_DRAFT_HISTORY_CAPACITY')
                    payload=event.payload
                    if (event.producer!=PRODUCER or type(event.schema_version) is not int or event.schema_version!=1
                            or event.decision_time_ms is not None or type(payload) is not dict
                            or set(payload)!={'schema','intent','intent_hash'} or payload['schema']!=SCHEMA):
                        raise PaymentDraftError('PAYMENT_DRAFT_RECORD_INVALID')
                    intent=PaymentIntent.from_body(payload['intent']);self._guard(intent)
                    key=self._key(intent.quote.beneficiary.owner_ref,intent.request_id)
                    if (key in rows or key!=event.correlation_id or intent.intent_hash!=payload['intent_hash']
                            or type(event.received_time_ms) is not int or event.received_time_ms<last
                            or event.event_time_ms!=event.received_time_ms or type(event.event_time_ms) is not int):
                        raise PaymentDraftError('PAYMENT_DRAFT_IDENTITY_OR_CLOCK_INVALID')
                    # Original storage had to occur inside the claimed quote window.
                    intent.validate_binding(expected_intent_hash=intent.intent_hash,owner_ref=intent.quote.beneficiary.owner_ref,
                        account_scope_ref=intent.quote.beneficiary.account_scope_ref,
                        beneficiary_digest=intent.quote.beneficiary.beneficiary_digest,now_ms=event.received_time_ms)
                    rows[key]=(event,intent);last=event.received_time_ms
        except PaymentDraftError:raise
        except (KeyError,TypeError,ValueError,ArithmeticError):
            raise PaymentDraftError('PAYMENT_DRAFT_RECORD_INVALID') from None
        return rows,size,last

    def _committed_history(self):
        # The shared owner rechecks transaction state after acquiring its reader
        # lock, so another thread's staged writer cannot become source evidence.
        with committed_source_snapshot(self.ledger):return self._history()

    @staticmethod
    def _receipt(event,intent):
        return {'schema':'vati.payment-draft-receipt/1','record_ref':event.hash,'request_id':intent.request_id,
            'owner_ref':intent.quote.beneficiary.owner_ref,'account_scope_ref':intent.quote.beneficiary.account_scope_ref,
            'intent_hash':intent.intent_hash,'quote_hash':intent.quote.quote_hash,'available_at_ms':event.received_time_ms,
            'state':'DRAFT_STORED_NOT_APPROVED','provider_qualified':False,'execution_authority':False}

    def lookup(self,owner_ref,request_id):
        _identity(owner_ref);_identity(request_id)
        rows,_,_=self._committed_history();original=rows.get(self._key(owner_ref,request_id))
        return None if original is None else self._receipt(*original)

    def inspect(self,owner_ref,request_id):
        _identity(owner_ref);_identity(request_id)
        rows,_,_=self._committed_history();original=rows.get(self._key(owner_ref,request_id))
        if original is None:return None
        event,intent=original;now=self._now()
        return {'receipt':self._receipt(event,intent),'intent':intent.body(),
            'claimed_quote_time_state':'NOT_YET_ISSUED' if now<intent.quote.issued_at_ms else
                'EXPIRED' if now>=intent.quote.expires_at_ms else 'WITHIN_CLAIMED_WINDOW',
            'current_payment_eligibility':'NOT_ADMITTED','execution_authority':False}

    def publish(self,owner_ref,intent):
        _identity(owner_ref)
        if type(intent) is not PaymentIntent or intent.quote.beneficiary.owner_ref!=owner_ref:
            raise PaymentDraftError('PAYMENT_DRAFT_OWNER_OR_INPUT_DIFFERS')
        self._guard(intent);started=False;confirmation_needed=False
        key=self._key(owner_ref,intent.request_id)
        try:
            self._idle(publication=True);rows,_,_=self._committed_history();original=rows.get(key)
            if original is not None:
                if original[1].intent_hash!=intent.intent_hash:raise PaymentDraftError('PAYMENT_DRAFT_ORIGINAL_REQUEST_CONFLICT')
                return self._receipt(*original)
            with self.ledger.atomic():
                rows,size,last=self._history();original=rows.get(key)
                if original is not None:
                    if original[1].intent_hash!=intent.intent_hash:raise PaymentDraftError('PAYMENT_DRAFT_ORIGINAL_REQUEST_CONFLICT')
                    event=original[0];confirmation_needed=True
                else:
                    # Recheck inside the actual SQL writer; waiting for it cannot
                    # extend an expired quote or change its original identity.
                    now=self._now(minimum=max(0,last))
                    intent.validate_binding(expected_intent_hash=intent.intent_hash,owner_ref=owner_ref,
                        account_scope_ref=intent.quote.beneficiary.account_scope_ref,
                        beneficiary_digest=intent.quote.beneficiary.beneficiary_digest,now_ms=now)
                    if len(rows)>=self.max_records or self.ledger.count()>=self.max_ledger_events:
                        raise PaymentDraftError('PAYMENT_DRAFT_EVENT_CAPACITY')
                    event=make_event(EventKind.PAYMENT_DRAFT,PRODUCER,
                        {'schema':SCHEMA,'intent':intent.body(),'intent_hash':intent.intent_hash},
                        event_time_ms=now,received_time_ms=now,correlation_id=key)
                    if size+len(canonical_json(event.body()).encode())>self.max_bytes:
                        raise PaymentDraftError('PAYMENT_DRAFT_BYTE_CAPACITY')
                    self._guard(intent);started=True;self.ledger.append(event)
            confirmation_needed=True;confirmed=self.lookup(owner_ref,intent.request_id)
            if confirmed is None or confirmed['record_ref']!=event.hash:raise PaymentDraftUnknown(intent.request_id)
            return confirmed
        except PaymentDraftUnknown:raise
        except Exception:
            if started or confirmation_needed:raise PaymentDraftUnknown(intent.request_id) from None
            raise
