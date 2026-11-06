"""One signed, durable cancellation attempt on an original native entry order.

No network exactly-once assumption: a committed request is never sent again.
Unknown replies recover by reading that same order. Cancellation and its raw
executions remain separate from flatness, protection and financial release.
"""
from contextlib import ExitStack, nullcontext
import hashlib
import json
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vati.authority import OwnerAuthorityVerifier, PREFIX, MAX_ACT_LIFETIME_SECONDS, _unb64u, canonical_statement
from vati.core import EventKind, make_event
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.file_lock import exclusive_state_lock
from vati.core.ledger import committed_source_snapshot, require_committed_source_read
from vati.execution.ctrader.orders import NativeOrderObservation
from vati.execution.ctrader.transport import CancellationNotSent
from vati.execution.native_order_book import NativeOrderBook, _identity
from vati.funding.native import native_int
from vati.risk.control_archive import archive_verified_control

ACT = 'native-order-cancel'
EVENT = 'ORIGINAL_NATIVE_CANCEL_CONTROL'
PRODUCER = 'vati-native-order-cancel-owner'
SCHEMA = 'vati.original-native-cancel-control/1'


class NativeCancelError(ValueError):
    pass


class NativeCancelUnknown(OSError):
    def __init__(self, request_id):
        self.request_id = request_id
        super().__init__('NATIVE_CANCEL_STORAGE_OUTCOME_UNKNOWN_READ_ORIGINAL_REQUEST_NEVER_RESEND')


def cancel_subject(intent):
    return ACT+':'+intent['intent_hash']


def _intent(body):
    fields = {'schema', 'request_id', 'command_hash', 'margin_source_ref', 'native_order_id',
              'deadline_ms', 'account_alias', 'physical_account_key', 'monetary_scope_hash',
              'original_command_ref', 'original_input_ref', 'original_lease_epoch', 'lease_epoch', 'intent_hash'}
    if type(body) is not dict or set(body) != fields or body['schema'] != 'vati.native-cancel-intent/1':
        raise NativeCancelError('NATIVE_CANCEL_INTENT_SHAPE_INVALID')
    _identity(body['request_id'], body['command_hash'], body['margin_source_ref'], body['native_order_id'])
    native_int(body['deadline_ms'], minimum=1)
    for name in ('lease_epoch','original_lease_epoch'):
        if body[name] is not None:
            native_int(body[name], minimum=1)
    for key in ('account_alias', 'physical_account_key', 'monetary_scope_hash', 'original_command_ref', 'original_input_ref'):
        if type(body[key]) is not str or not body[key]:
            raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_SCOPE_UNAVAILABLE')
    if body['intent_hash'] != canonical_hash({k:v for k,v in body.items() if k != 'intent_hash'}):
        raise NativeCancelError('NATIVE_CANCEL_INTENT_SEAL_INVALID')
    return json.loads(canonical_json(body))


def _original_signature(archive, intent, at_ms):
    """Original signature at original application time; never a fresh grant."""
    if type(archive) is not dict or archive.get('schema') != 'vati.original-direct-risk-control/1':
        raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_SIGNATURE_UNAVAILABLE')
    prefix, encoded, signature = archive['token'].split('.')
    body = json.loads(_unb64u(encoded)); verified = archive['verified_authority']
    expected = {'act':ACT, 'subject':cancel_subject(intent), 'issued_at_unix':body['iat'],
                'expires_at_unix':body['exp'], 'nonce':body['nonce'], 'key_id':body['kid']}
    if (prefix != PREFIX or verified != expected or body['act'] != ACT or body['subject'] != expected['subject']
            or type(body['iat']) is not int or type(body['exp']) is not int
            or type(body['nonce']) is not str or not body['nonce']
            or type(body['kid']) is not str or not body['kid']
            or not 0 < body['exp']-body['iat'] <= MAX_ACT_LIFETIME_SECONDS
            or not body['iat']*1000 <= at_ms < min(body['exp']*1000, intent['deadline_ms'])):
        raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_SIGNATURE_SCOPE_OR_TIME_INVALID')
    key = serialization.load_pem_public_key(archive['public_key_pem'].encode())
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise NativeCancelError('NATIVE_CANCEL_OWNER_KEY_KIND_INVALID')
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != archive['public_key_sha256']:
        raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_KEY_FINGERPRINT_INVALID')
    key.verify(_unb64u(signature), canonical_statement(act=ACT, subject=expected['subject'],
        issued_at_unix=body['iat'], expires_at_unix=body['exp'], nonce=body['nonce']).encode(),
        ec.ECDSA(hashes.SHA256()))
    return archive['public_key_sha256'], body['nonce']


class NativeCancelOwner:
    def __init__(self, router, *, authority=None, max_records=4096, max_bytes=32*1024**2):
        if (type(max_records) is not int or not 1 <= max_records <= 100000
                or type(max_bytes) is not int or not 1 <= max_bytes <= 256*1024**2):
            raise NativeCancelError('NATIVE_CANCEL_CAPACITY_INVALID')
        self.router, self.ledger = router, router.ledger
        self.authority = authority if authority is not None else OwnerAuthorityVerifier()
        if type(self.authority) is not OwnerAuthorityVerifier:
            raise NativeCancelError('NATIVE_CANCEL_REAL_OWNER_VERIFIER_REQUIRED')
        self.clock = router.clock or (lambda: int(time.time()*1000))
        self.max_records, self.max_bytes = max_records, max_bytes

    def _now(self):
        return native_int(self.clock(), minimum=0)

    def prepare(self, request_id, command_hash, margin_source_ref, native_order_id, *, deadline_ms, lease_epoch=None, at_ms=None):
        now = self._now() if at_ms is None else native_int(at_ms, minimum=0)
        native_int(deadline_ms, minimum=now+1)
        target = _identity(request_id, command_hash, margin_source_ref, native_order_id)
        with committed_source_snapshot(self.ledger):
            original, volume = NativeOrderBook(self.ledger)._binding(target, available_at_ms=now)
        q = original['observation']; cmd = original['command']
        if cmd['entry_type'] not in {'LIMIT','PASSIVE_LIMIT','STOP','STOP_LIMIT'}:
            raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_PENDING_ENTRY_REQUIRED')
        if cmd['lease_epoch'] is not None and lease_epoch is None:
            raise NativeCancelError('NATIVE_CANCEL_CURRENT_RUNTIME_LEASE_REQUIRED')
        body = {'schema':'vati.native-cancel-intent/1', **target, 'deadline_ms':deadline_ms,
                'account_alias':cmd['account_alias'], 'physical_account_key':q['physical_account_key'],
                'monetary_scope_hash':q['monetary_scope_hash'], 'original_command_ref':volume['command_ref'],
                'original_input_ref':volume['original_input_ref'], 'original_lease_epoch':cmd['lease_epoch'],
                'lease_epoch':lease_epoch}
        body['intent_hash'] = canonical_hash(body)
        return _intent(body)

    def _history(self):
        if self.ledger.count() > 100000 or not self.ledger.verify_chain()[0]:
            raise NativeCancelError('NATIVE_CANCEL_HISTORY_UNAVAILABLE')
        found = {}; nonces = set(); size = 0; last = -1; records = 0
        for event in self.ledger.iter(EventKind.SESSION):
            p = event.payload
            if type(p) is not dict or p.get('event') != EVENT:
                continue
            size += len(canonical_json(event.body()).encode()); records += 1
            if records > self.max_records or size > self.max_bytes:
                raise NativeCancelError('NATIVE_CANCEL_HISTORY_CAPACITY')
            if (p.get('schema') != SCHEMA or event.producer != PRODUCER
                    or type(event.schema_version) is not int or event.schema_version != 1
                    or event.decision_time_ms is not None or event.hash != canonical_hash(event.body())
                    or type(event.event_time_ms) is not int or event.event_time_ms != event.received_time_ms):
                raise NativeCancelError('NATIVE_CANCEL_RECORD_INVALID')
            native_int(event.received_time_ms, minimum=max(0,last)); last = event.received_time_ms
            key = event.correlation_id
            if p.get('state') == 'REQUESTED':
                if (set(p) != {'event','schema','state','intent','original_owner_control',
                               'prequery_request_id','prequery_record_ref'} or key in found):
                    raise NativeCancelError('NATIVE_CANCEL_REQUEST_CONFLICT')
                intent = _intent(p['intent'])
                if intent['request_id'] != key:
                    raise NativeCancelError('NATIVE_CANCEL_REQUEST_ID_DIFFERS')
                nonce = _original_signature(p['original_owner_control'], intent, event.received_time_ms)
                if nonce in nonces:
                    raise NativeCancelError('NATIVE_CANCEL_OWNER_NONCE_REUSED')
                nonces.add(nonce); found[key] = {'request':event, 'latest':event, 'attempt':event, 'query':None}
            else:
                previous = found.get(key)
                if (previous is None or set(p) != {'event','schema','state','request_ref','previous_ref',
                                                'response','order_query_receipt','availability'}
                        or p['state'] not in {'NOT_SENT','WIRE_OBSERVED','UNKNOWN','ORDER_OBSERVED'}
                        or p['request_ref'] != previous['request'].hash
                        or p['previous_ref'] != previous['latest'].hash):
                    raise NativeCancelError('NATIVE_CANCEL_STATE_CHAIN_INVALID')
                availability = p['availability']
                if availability not in ({'state':'AVAILABLE','received_at_ms':event.received_time_ms},
                                        {'state':'UNAVAILABLE','received_at_ms':None}):
                    raise NativeCancelError('NATIVE_CANCEL_AVAILABILITY_INVALID')
                if p['state']=='ORDER_OBSERVED':
                    if type(p['order_query_receipt']) is not dict or p['response'] is not None:
                        raise NativeCancelError('NATIVE_CANCEL_NATIVE_QUERY_RECEIPT_INVALID')
                    previous['query']=event
                else:
                    if previous['attempt'].payload['state']!='REQUESTED' or p['order_query_receipt'] is not None:
                        raise NativeCancelError('NATIVE_CANCEL_DUPLICATE_TRANSPORT_RESULT')
                    previous['attempt']=event
                previous['latest'] = event
        return found, nonces, size, last, records

    def lookup(self, request_id):
        with committed_source_snapshot(self.ledger):
            selected = self._history()[0].get(request_id)
            if selected is None:
                return None
            request = selected['request']; latest = selected['latest']; intent = request.payload['intent']
            original = self.prepare(intent['request_id'], intent['command_hash'], intent['margin_source_ref'],
                intent['native_order_id'], deadline_ms=intent['deadline_ms'], lease_epoch=intent['lease_epoch'],
                at_ms=request.received_time_ms)
            if original != intent:
                raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_ENTRY_BINDING_DIFFERS')
            pre = NativeOrderBook(self.ledger).lookup(request.payload['prequery_request_id'])
            if pre is None or pre['receipt']['record_ref'] != request.payload['prequery_record_ref']:
                raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_PREQUERY_UNAVAILABLE')
            observation = pre['observation']
            if (pre['request']['command_hash'] != intent['command_hash']
                    or pre['request']['margin_source_ref'] != intent['margin_source_ref']
                    or pre['request']['native_order_id'] != intent['native_order_id']
                    or observation['deadline_ms'] != intent['deadline_ms']
                    or not pre['receipt']['available_at_ms'] <= request.received_time_ms < intent['deadline_ms']):
                raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_PREQUERY_DIFFERS')
            return {'request_id':request_id, 'intent':intent, 'original_request_ref':request.hash,
                    'state_ref':latest.hash, 'state':latest.payload['state'],
                    'attempt_state':selected['attempt'].payload['state'],
                    'attempt_state_ref':selected['attempt'].hash,
                    'original_response':selected['attempt'].payload.get('response'),
                    'latest_native_order_query':None if selected['query'] is None else selected['query'].payload['order_query_receipt'],
                    'response':latest.payload.get('response'), 'order_query_receipt':latest.payload.get('order_query_receipt'),
                    'availability':latest.payload.get('availability',{'state':'AVAILABLE','received_at_ms':request.received_time_ms}),
                    'remaining_entry_allowance':None, 'position_flat':None, 'cash_settled':False,
                    'fees_final':False, 'reservation_qualified':False, 'execution_authority':False}

    def _append(self, event):
        if self.ledger.count() >= 100000:
            raise NativeCancelError('NATIVE_CANCEL_EVENT_CAPACITY')
        history, _, size, _, count = self._history()
        reserved = sum(row['attempt'].payload['state']=='REQUESTED' for row in history.values())
        if event.payload['state']=='REQUESTED':
            reserved += 1
        elif (event.payload['state'] in {'NOT_SENT','WIRE_OBSERVED','UNKNOWN'}
                and history[event.correlation_id]['attempt'].payload['state']=='REQUESTED'):
            reserved -= 1
        if (count+1+reserved > self.max_records
                or size+len(canonical_json(event.body()).encode()) > self.max_bytes):
            raise NativeCancelError('NATIVE_CANCEL_RECORD_CAPACITY')
        self.ledger.append(event)

    def _retryable_rejection(self, selected, positions):
        """Only an explicit scoped rejection plus a later native working read.

        This permits a newly signed attempt. The original request is still
        never resent; silence, timeout and a still-working order alone do not
        establish that its earlier cancellation was rejected.
        """
        attempt = selected['attempt']; query = selected['query']
        if attempt.payload['state']=='NOT_SENT':
            return True
        if attempt.payload['state']!='WIRE_OBSERVED' or query is None:
            return False
        try:
            wire = attempt.payload['response']; native = wire['body']
            receipt = query.payload['order_query_receipt']
            captured = NativeOrderBook(self.ledger).lookup(receipt['request_id'])
            if captured is None or captured['receipt']!=receipt:
                return False
            q = captured['observation']; request = selected['request'].payload['intent']
            order = native['order']; trade = order['tradeData']; facts = q['facts']
            from vati.execution.ctrader.orders import _enum
            return (positions[receipt['record_ref']] > positions[attempt.hash]
                    and wire['message']=='ProtoOAExecutionEvent'
                    and native_int(native['ctidTraderAccountId'],minimum=1)==q['request']['ctidTraderAccountId']
                    and native_int(order['orderId'],minimum=1)==request['native_order_id']
                    and _enum('ProtoOAExecutionType',native['executionType'])=='ORDER_CANCEL_REJECTED'
                    and native_int(trade['symbolId'],minimum=1)==facts['native_symbol_id']
                    and _enum('ProtoOATradeSide',trade['tradeSide'])==facts['native_trade_side']
                    and facts['native_order_status']=='ORDER_STATUS_ACCEPTED'
                    and facts['closing_order'] is False and facts['observation_state']=='NATIVE_ORDER_OBSERVED')
        except (KeyError,TypeError,ValueError):
            return False

    def _finish(self, current, *, state, response=None, order_query_receipt=None):
        started = False
        try:
            require_committed_source_read(self.ledger)
            with self.ledger.atomic():
                history, _, _, last, _ = self._history()
                selected = history[current['request_id']]
                if selected['latest'].hash != current['state_ref']:
                    raise NativeCancelError('NATIVE_CANCEL_CONCURRENT_STATE_RECONCILE_ORIGINAL')
                try:
                    now = self._now()
                    native_int(now, minimum=max(last,selected['latest'].received_time_ms))
                    availability = {'state':'AVAILABLE','received_at_ms':now}
                except Exception:
                    now = self._history()[3]
                    availability = {'state':'UNAVAILABLE','received_at_ms':None}
                event = make_event(EventKind.SESSION, PRODUCER, {'event':EVENT, 'schema':SCHEMA,
                    'state':state, 'request_ref':current['original_request_ref'], 'previous_ref':current['state_ref'],
                    'response':response, 'order_query_receipt':order_query_receipt, 'availability':availability},
                    event_time_ms=now, received_time_ms=now, correlation_id=current['request_id'])
                started = True; self._append(event)
            result = self.lookup(current['request_id'])
            if result is None or result['state_ref'] != event.hash:
                raise NativeCancelUnknown(current['request_id'])
            return result
        except Exception:
            if started:
                raise NativeCancelUnknown(current['request_id']) from None
            raise

    def execute(self, intent, owner_token):
        require_committed_source_read(self.ledger)
        if getattr(self.ledger, '_read_snapshot_depth', 0):
            raise NativeCancelError('NATIVE_CANCEL_REQUIRES_OWN_COMMITTED_WRITER')
        intent = _intent(intent); key = intent['request_id']; known = self.lookup(key)
        if known is not None:
            if known['intent'] != intent:
                raise NativeCancelError('NATIVE_CANCEL_REQUEST_RETARGET_REFUSED')
            return known
        now = self._now()
        expected = self.prepare(key, intent['command_hash'], intent['margin_source_ref'], intent['native_order_id'],
                                deadline_ms=intent['deadline_ms'], lease_epoch=intent['lease_epoch'], at_ms=now)
        if expected != intent:
            raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_ENTRY_BINDING_DIFFERS')
        # Signature verification is separate from one-shot redemption. The SQL
        # writer below owns durable nonce consumption with the exact request;
        # a process-local set cannot implement crash-safe single use.
        verified = self.authority.verify(owner_token, act=ACT, subject=cancel_subject(intent),
                                         now_unix=now//1000, single_use=False)
        proof = archive_verified_control(owner_token, verified)
        nonce = _original_signature(proof, intent, now)
        binding = verified._verified_key_binding; epoch = intent['lease_epoch']
        router = self.router; adapter = router.adapters.get('ctrader')
        def fence():
            current = self._now()
            return (now <= current < min(intent['deadline_ms'], verified.expires_at_unix*1000)
                    and current >= verified.issued_at_unix*1000 and binding.is_current()
                    and (router.lease_fence(epoch) is True if router.lease_fence is not None else epoch is None))
        guard = router.lease_submission_guard(epoch) if router.lease_submission_guard is not None else nullcontext(epoch is None)
        with ExitStack() as locks:
            if binding.registry_path is not None:
                locks.enter_context(exclusive_state_lock(binding.registry_path))
            if locks.enter_context(guard) is not True or not fence():
                raise NativeCancelError('NATIVE_CANCEL_CURRENT_OWNER_OR_LEASE_REFUSED')
            book = NativeOrderBook(self.ledger, clock=self.clock)
            prekey = 'cancel-pre-'+intent['intent_hash']
            book.capture(adapter, prekey, intent['command_hash'], intent['margin_source_ref'],
                         intent['native_order_id'], deadline_ms=intent['deadline_ms'])
            pre = book.lookup(prekey); observation = NativeOrderObservation.from_body(pre['observation'])
            # The adapter validates native pending/nonclosing semantics before
            # any write. Preserve the original signed request before dispatch.
            with committed_source_snapshot(self.ledger):
                history = self._history()[0]
                positions = {event.hash:index for index,event in enumerate(self.ledger.iter())}
                retryable = {old['request'].hash for old in history.values()
                             if self._retryable_rejection(old,positions)}
                before_head = self.ledger.head()
            started = False
            try:
                with self.ledger.atomic():
                    history, nonces, _, last, _ = self._history()
                    if key in history or nonce in nonces:
                        raise NativeCancelError('NATIVE_CANCEL_REQUEST_OR_NONCE_ALREADY_COMMITTED')
                    _, _, _, _, records = self._history()
                    reserved = sum(row['attempt'].payload['state']=='REQUESTED' for row in history.values())
                    if records+reserved+2 > self.max_records:
                        raise NativeCancelError('NATIVE_CANCEL_REQUEST_AND_RESULT_CAPACITY')
                    for other in history.values():
                        previous = other['request'].payload['intent']
                        if ((previous['physical_account_key'],previous['native_order_id']) ==
                                (intent['physical_account_key'],intent['native_order_id'])
                                and other['request'].hash not in retryable):
                            raise NativeCancelError('NATIVE_CANCEL_ORIGINAL_ORDER_ATTEMPT_REQUIRES_RECONCILIATION')
                    if self.ledger.head() != before_head or not fence():
                        raise NativeCancelError('NATIVE_CANCEL_SOURCE_OR_CURRENT_FENCE_CHANGED')
                    applied = native_int(self._now(), minimum=max(last,pre['receipt']['available_at_ms']))
                    _original_signature(proof, intent, applied)
                    event = make_event(EventKind.SESSION, PRODUCER, {'event':EVENT, 'schema':SCHEMA,
                        'state':'REQUESTED', 'intent':intent, 'original_owner_control':proof,
                        'prequery_request_id':prekey, 'prequery_record_ref':pre['receipt']['record_ref']},
                        event_time_ms=applied, received_time_ms=applied, correlation_id=key)
                    started = True; self._append(event)
                current = self.lookup(key)
                if current is None or current['original_request_ref'] != event.hash or current['state'] != 'REQUESTED':
                    raise NativeCancelUnknown(key)
            except Exception:
                if started:
                    raise NativeCancelUnknown(key) from None
                raise
            try:
                if not fence():
                    raise CancellationNotSent('original cancellation fence expired after committed readback; not sent')
                name, response = adapter.cancel_order(observation, deadline_ms=intent['deadline_ms'], recheck=fence)
            except CancellationNotSent:
                return self._finish(current, state='NOT_SENT')
            except Exception as error:
                return self._finish(current, state='UNKNOWN', response={'error_type':type(error).__name__})
            return self._finish(current, state='WIRE_OBSERVED', response={'message':name,'body':response})

    def reconcile(self, request_id, query_id, *, deadline_ms):
        """Read the original order after an uncertain/expired attempt; never resend."""
        current = self.lookup(request_id)
        if current is None:
            return None
        intent = current['intent']; book = NativeOrderBook(self.ledger, clock=self.clock)
        # Replaying an older read returns its original receipt alongside the
        # current control lifecycle; it cannot move availability or roll back
        # a later native observation.
        with committed_source_snapshot(self.ledger):
            for event in self.ledger.iter(EventKind.SESSION,correlation_id=request_id):
                p = event.payload
                if (p.get('event')==EVENT and p.get('state')=='ORDER_OBSERVED'
                        and p['order_query_receipt']['request_id']==query_id):
                    original = book.lookup(query_id)
                    if original is None or original['receipt']!=p['order_query_receipt']:
                        raise NativeCancelError('NATIVE_CANCEL_RECONCILIATION_RECEIPT_DIFFERS')
                    return {**current,'reconciliation_query_receipt':original['receipt']}
        query = book.capture(self.router.adapters.get('ctrader'), query_id, intent['command_hash'],
            intent['margin_source_ref'], intent['native_order_id'], deadline_ms=deadline_ms)
        with committed_source_snapshot(self.ledger):
            positions = {event.hash:index for index,event in enumerate(self.ledger.iter())}
            if positions[query['record_ref']]<=positions[current['attempt_state_ref']]:
                raise NativeCancelError('NATIVE_CANCEL_RECONCILIATION_REQUIRES_LATER_ORIGINAL_NATIVE_QUERY')
        result = self._finish(current, state='ORDER_OBSERVED', order_query_receipt=query)
        return {**result,'reconciliation_query_receipt':query}
