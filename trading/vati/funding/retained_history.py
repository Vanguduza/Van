"""Original physical-account cash prefix; never incarnation P&L or authority.

The native lifecycle owner supplies a verified original plan and deletion
event. Source ordering is ledger ordering, never a wall-clock comparison.
"""
import base64
import json

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.core.ledger import LedgerError, committed_source_snapshot
from vati.funding.journal import FundingBook
from vati.funding.mt5_journal import Mt5FundingBook
from vati.funding.native import NativeAccountMark

VIEW = 'FINANCIAL_HISTORY'
SCHEMA = 'vati.retained-cash-history/1'


class RetainedHistoryError(ValueError):
    pass


def _cursor(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        raise RetainedHistoryError('RETAINED_HISTORY_CURSOR_INVALID')
    try:
        def distinct(pairs):
            out = {}
            for key, item in pairs:
                if key in out: raise ValueError()
                out[key] = item
            return out
        raw = base64.b64decode(value, altchars=b'-_', validate=True)
        result = json.loads(raw, object_pairs_hook=distinct)
        if not isinstance(result, dict): raise ValueError()
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise RetainedHistoryError('RETAINED_HISTORY_CURSOR_INVALID') from None


def _encode(value):
    return base64.urlsafe_b64encode(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).decode()


def _snapshot_source(ledger, event, profile, prior):
    """Validate actual native facts, not merely an alias/configuration match."""
    p = event.payload
    observation = p.get('funding_observation')
    if not isinstance(observation, dict): return None
    mark = p.get('native_account_mark') or observation.get('native_mark')
    if not isinstance(mark, dict): return None
    if profile['broker'] == 'CTRADER':
        if mark.get('schema') != 'native-account-mark/1': return None
        typed = NativeAccountMark.from_body(mark)
        if (typed.account_alias != profile['alias'] or str(typed.native_account_id) != profile['login']
            or typed.currency != profile['currency']
            or typed.environment != ('DEMO' if profile['demo'] else 'LIVE')): return None
        book = FundingBook(ledger)
        ref = observation.get('statement', {}).get('statement_ref')
        query_ref = None
    elif profile['broker'] == 'MT5':
        if (mark.get('schema') != 'mt5-account-mark/1' or mark.get('account_alias') != profile['alias']
            or str(mark.get('login')) != profile['login'] or mark.get('server') != profile['server']
            or mark.get('currency') != profile['currency'] or mark.get('demo') is not profile['demo']): return None
        book = Mt5FundingBook(ledger)
        query_ref = observation.get('query_ref')
        query = next((q for q in book._queries(mark['scope_hash']) if q.hash == query_ref), None)
        if query is None or query.hash not in prior or query.payload['mark'] != mark:
            raise LedgerError('retained_original_query_unavailable')
        ref = query.payload['cash_statement_ref']
        if observation.get('statement', {}).get('statement_ref') != ref:
            raise LedgerError('retained_original_query_statement_differs')
    else:
        return None
    scope = mark['scope_hash']
    if observation.get('scope_hash') != scope or ref not in prior:
        raise LedgerError('retained_original_statement_unavailable')
    facts = book.observations(scope, as_of=ref)
    return {'scope_hash': scope, 'snapshot_ref': event.hash, 'query_ref': query_ref,
            'statement_ref': ref, 'facts': facts, 'source_observed_at_ms': mark.get('observed_at_ms')}


def read_history(ledger, *, lifecycle, plan_ref, profile, cutoff_ref, limit=100, cursor=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise RetainedHistoryError('RETAINED_HISTORY_LIMIT_INVALID')
    with committed_source_snapshot(ledger):
        if not ledger.verify_chain()[0]: raise LedgerError('retained_source_chain_invalid')
        prior = set()
        selected = None
        cutoff_found = False
        for event in ledger.iter():
            if event.hash == cutoff_ref:
                cutoff_found = True
                break
            if (event.kind is EventKind.ACCOUNT_SNAPSHOT and event.producer in {'vati-service', 'vati-account-service'}
                and event.payload.get('account_alias') == lifecycle['alias']):
                if event.hash != canonical_hash(event.body()): raise LedgerError('retained_snapshot_seal_invalid')
                try:
                    candidate = _snapshot_source(ledger, event, profile, prior)
                except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
                    raise LedgerError('retained_original_source_invalid') from None
                if candidate is not None: selected = candidate
            prior.add(event.hash)
        if not cutoff_found: raise LedgerError('retained_original_cutoff_unavailable')
        binding = {'schema': SCHEMA, 'view': VIEW, 'alias': lifecycle['alias'],
            'lifecycle_id': lifecycle['operation_id'], 'incarnation': lifecycle['incarnation'],
            'account_control_domain': lifecycle['account_control_domain'], 'original_plan_ref': plan_ref,
            'cutoff_ref': cutoff_ref}
        result = binding | {'attribution': 'ORIGINAL_PHYSICAL_ACCOUNT_PRE_DELETION',
            'generation_provenance': 'UNKNOWN', 'return_qualification': 'NOT_ISSUED',
            'settlement_qualification': 'NOT_ISSUED', 'risk_capital_qualified': False,
            'execution_authority': False, 'freshness': 'HISTORICAL',
            'remaining_obligations': ['EXCLUSIVE_GENERATION_ATTRIBUTION', 'LATER_ORIGINAL_EFFECT_SETTLEMENT',
                'MONTHLY_YEARLY_STATEMENTS_AND_EXPORTS'],
            'movements': [], 'movement_count': 0, 'truncated': False, 'next_cursor': None}
        if selected is None:
            if cursor is not None: raise RetainedHistoryError('RETAINED_HISTORY_ANCHOR_UNAVAILABLE')
            return result | {'state': 'UNOBSERVED', 'reason': 'ORIGINAL_PRE_DELETION_NATIVE_SOURCE_UNOBSERVED'}
        facts = selected.pop('facts')
        binding |= selected | {'limit': limit}
        offset = 0
        if cursor is not None:
            decoded = _cursor(cursor)
            if (set(decoded) != set(binding) | {'offset'} or type(decoded.get('offset')) is not int
                or decoded['offset'] < 0 or any(decoded.get(k) != v for k, v in binding.items())):
                raise RetainedHistoryError('RETAINED_HISTORY_CURSOR_SCOPE_CHANGED')
            offset = decoded['offset']
        rows = sorted(facts['movements'], key=lambda row: row['movement']['native_id'])
        if offset > len(rows): raise RetainedHistoryError('RETAINED_HISTORY_CURSOR_OFFSET_INVALID')
        page = rows[offset:offset + limit]
        truncated = offset + len(page) < len(rows)
        return result | selected | {'state': facts['state'], 'reason': 'ORIGINAL_OBSERVED_PREFIX_NOT_LIFETIME_COVERAGE',
            'movements': page, 'movement_count': len(rows), 'truncated': truncated,
            'coverage_windows': facts['coverage_windows'], 'conflicts': facts['conflicts'],
            'next_cursor': _encode(binding | {'offset': offset + len(page)}) if truncated else None}


class MovementFrontier:
    """Bounded candidates for one keyset page, in original journal order.

    Callers advance source rows in finite work budgets and retain this object
    only in the trusted handler-owned job. This proves selected rows only;
    global source consistency needs a separate complete validation pass.
    """
    def __init__(self, after_native_id, limit):
        if type(after_native_id) is not int or after_native_id < 0:
            raise ValueError('invalid retained history bookmark')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid retained history page limit')
        self.after_native_id = after_native_id
        self.capacity = limit + 1
        self._rows = {}
        self._contradictions = set()

    def observe(self, row, statement_ref, observed_at_ms, received_at_ms):
        native_id = row['native_id']
        if type(native_id) is not int or native_id <= 0:
            raise ValueError('invalid native movement identity')
        if native_id <= self.after_native_id:
            return
        prior = self._rows.get(native_id)
        if prior is not None:
            if prior['movement'] != row:
                self._contradictions.add(native_id)
            return
        if len(self._rows) == self.capacity:
            largest = max(self._rows)
            if native_id >= largest:
                return
            del self._rows[largest]
            self._contradictions.discard(largest)
        self._rows[native_id] = {'movement': row, 'original_statement_ref': statement_ref,
            'observed_at_ms': observed_at_ms, 'received_at_ms': received_at_ms}

    def page(self):
        if self._contradictions:
            raise LedgerError('funding_original_history_conflict')
        ids = sorted(self._rows)
        return [self._rows[key] for key in ids[:self.capacity - 1]], len(ids) == self.capacity


class VerifiedLedgerScan:
    """Incremental original-chain scan to a caller-proved immutable anchor.

    Existing event JSON parsing and owner typed validation are atomic. The trusted
    event predicate selects whole events only; row access uses the existing
    decoded movement list without copying or filtering. Each inspected row
    consumes budget. Do not
    expose results until the complete anchor has been proved. Cursor data never
    constructs this state.
    """
    def __init__(self, through_seq, through_chain):
        from vati.core.ledger import GENESIS
        if type(through_seq) is not int or through_seq <= 0:
            raise ValueError('invalid retained history anchor ordinal')
        if not isinstance(through_chain, str) or len(through_chain) != 64:
            raise ValueError('invalid retained history anchor chain')
        self.through_seq = through_seq
        self.through_chain = through_chain
        self.seq = 0
        self.chain = GENESIS
        self.pending = None
        self.row_offset = 0
        self.finished = False
        self.failed = False

    def advance(self, ledger, include_event, accept_row, *, event_budget, row_budget):
        if self.failed:
            raise LedgerError('retained_scan_restart_required')
        try:
            return self._advance(ledger, include_event, accept_row, event_budget=event_budget, row_budget=row_budget)
        except BaseException:
            self.failed = True
            raise

    def _advance(self, ledger, include_event, accept_row, *, event_budget, row_budget):
        import hashlib
        if type(event_budget) is not int or event_budget <= 0 or type(row_budget) is not int or row_budget <= 0:
            raise ValueError('invalid retained history work budget')
        events = rows = 0
        while not self.finished:
            if self.pending is None:
                if events == event_budget:
                    break
                page = ledger.read_page(self.seq, 1, through_seq=self.through_seq)
                if not page:
                    raise LedgerError('retained_original_anchor_unavailable')
                seq, event, previous, chain = page[0]
                if (seq <= self.seq or previous != self.chain or event.hash != canonical_hash(event.body())
                    or chain != hashlib.sha256((previous + event.hash).encode()).hexdigest()):
                    raise LedgerError('retained_source_chain_invalid')
                selected = event.payload['statement']['movements'] if include_event(event) else ()
                if not isinstance(selected, (list, tuple)):
                    raise TypeError('retained history rows must be an existing decoded sequence')
                self.pending = (seq, event, chain, selected)
                self.row_offset = 0
                events += 1
            seq, event, chain, selected = self.pending
            while self.row_offset < len(selected) and rows < row_budget:
                accept_row(event, selected[self.row_offset])
                self.row_offset += 1
                rows += 1
            if self.row_offset < len(selected):
                break
            self.seq, self.chain = seq, chain
            self.pending = None
            if seq == self.through_seq:
                if chain != self.through_chain:
                    raise LedgerError('retained_original_anchor_changed')
                self.finished = True
        return {'events': events, 'rows': rows, 'finished': self.finished}


class RetainedHistoryJobs:
    """Handler-lifetime trusted work only; client tokens convey no authority."""
    def __init__(self, *, clock=None, ttl_seconds=300):
        import threading
        import time
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError('invalid retained job lifetime')
        self._clock = clock or time.monotonic
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._jobs = {}
        self._closed = False

    def _expire(self, now):
        for key in [key for key, value in self._jobs.items() if value['expires'] <= now and value['inflight'] == 0]:
            del self._jobs[key]

    def start(self, device, binding, job, guard):
        import copy
        import threading
        import uuid
        with self._condition:
            if self._closed:
                raise RetainedHistoryError('RETAINED_HISTORY_RESTART_REQUIRED')
            now = self._clock()
            self._expire(now)
            if len(self._jobs) >= 8 or sum(item['device'] == device for item in self._jobs.values()) >= 2:
                raise RetainedHistoryError('RETAINED_HISTORY_JOB_CAPACITY')
            key = uuid.uuid4().hex
            item = {'device': device, 'binding': copy.deepcopy(binding),
                'job': copy.deepcopy(job), 'expires': now + self._ttl, 'lock': threading.Lock(), 'inflight':1, 'invalid':False}
            self._jobs[key] = item
        try:
            guard()
            guard()
            with self._condition:
                if self._closed or item['expires'] <= self._clock():
                    raise RetainedHistoryError('RETAINED_HISTORY_RESTART_REQUIRED')
                return key
        except BaseException:
            with self._condition:item['invalid']=True
            raise
        finally:
            with self._condition:
                item['inflight'] -= 1
                if item['inflight']==0 and (self._closed or item['invalid']):
                    if self._jobs.get(key) is item:del self._jobs[key]
                self._condition.notify_all()

    def advance(self, key, device, binding, guard, step):
        import copy
        with self._lock:
            if self._closed:
                raise RetainedHistoryError('RETAINED_HISTORY_RESTART_REQUIRED')
            self._expire(self._clock())
            item = self._jobs.get(key)
            if item is None or item['invalid']:
                raise RetainedHistoryError('RETAINED_HISTORY_RESTART_REQUIRED')
            if item['device'] != device or item['binding'] != binding:
                raise RetainedHistoryError('RETAINED_HISTORY_OWNER_CHANGED')
            item['inflight'] += 1
        try:
            with item['lock']:
                with self._lock:
                    if (self._closed or item['invalid'] or self._jobs.get(key) is not item
                        or item['expires'] <= self._clock()):
                        raise RetainedHistoryError('RETAINED_HISTORY_RESTART_REQUIRED')
                try:
                    guard()
                    result = copy.deepcopy(step(item['job']))
                    guard()
                    with self._lock:
                        if (self._closed or item['invalid'] or self._jobs.get(key) is not item
                            or item['expires'] <= self._clock()):
                            raise RetainedHistoryError('RETAINED_HISTORY_RESTART_REQUIRED')
                        item['expires'] = self._clock() + self._ttl
                    return result
                except BaseException:
                    with self._lock:item['invalid']=True
                    raise
        finally:
            with self._condition:
                item['inflight'] -= 1
                if item['inflight']==0 and (self._closed or item['invalid']):
                    if self._jobs.get(key) is item:del self._jobs[key]
                self._condition.notify_all()

    def release(self,key,device,binding):
        with self._lock:
            item=self._jobs.get(key)
            if item is None or item['invalid']:
                raise RetainedHistoryError('RETAINED_HISTORY_RESTART_REQUIRED')
            if item['device']!=device or item['binding']!=binding:
                raise RetainedHistoryError('RETAINED_HISTORY_OWNER_CHANGED')
            item['invalid']=True
            if item['inflight']==0:del self._jobs[key]

    def close(self):
        with self._condition:
            self._closed=True
            self._condition.notify_all()
            for key in [key for key,item in self._jobs.items() if item['inflight']==0]:del self._jobs[key]
            while self._jobs:self._condition.wait()


class GlobalMovementValidation:
    """Prove all original IDs using bounded candidates and repeated scans.

    Completeness requires reaching every ID and its later observations. No
    global OBSERVED conclusion is available while any scan remains unfinished.
    The original funding owner and scope are bound at construction; each
    matching OBSERVED event is checked by the existing journal owner. Existing typed validation remains
    an atomic event operation; each subsequent row inspection is budgeted.
    """
    def __init__(self, through_seq, through_chain, *, broker, scope_hash, batch_limit=100):
        if broker not in {'CTRADER', 'MT5'} or not isinstance(scope_hash, str) or len(scope_hash) != 64:
            raise ValueError('invalid original funding scope')
        self.broker = broker
        self.scope_hash = scope_hash
        self.through_seq = through_seq
        self.through_chain = through_chain
        self.batch_limit = batch_limit
        self.after_native_id = 0
        self.frontier = MovementFrontier(0, batch_limit)
        self.scan = VerifiedLedgerScan(through_seq, through_chain)
        self.finished = False
        self.failed = False
        self.saw_conflict = False

    def advance(self, ledger, *, event_budget, row_budget):
        if self.failed:
            raise LedgerError('retained_scan_restart_required')
        if self.finished:
            return {'events': 0, 'rows': 0, 'finished': True}
        book = FundingBook(ledger) if self.broker == 'CTRADER' else Mt5FundingBook(ledger)
        def selected(event):
            if event.correlation_id != book.correlation_prefix + self.scope_hash:
                return False
            book.validate_event(event, self.scope_hash)
            if event.payload['state'] == 'CONFLICT': self.saw_conflict = True
            return event.payload['state'] == 'OBSERVED'
        def observe(event, row):
            self.frontier.observe(row, event.hash, event.payload['statement']['observed_at_ms'], event.received_time_ms)
        try:
            result = self.scan.advance(ledger, selected, observe,
                event_budget=event_budget, row_budget=row_budget)
            if self.scan.finished:
                page, more = self.frontier.page()
                if more:
                    if not page:
                        raise LedgerError('retained_validation_frontier_invalid')
                    self.after_native_id = page[-1]['movement']['native_id']
                    self.frontier = MovementFrontier(self.after_native_id, self.batch_limit)
                    self.scan = VerifiedLedgerScan(self.through_seq, self.through_chain)
                else:
                    self.finished = True
            result['finished'] = self.finished
            return result
        except BaseException:
            self.failed = True
            raise


class OriginalBoundaryScan:
    """Discover the original deletion ordinal through its exact journal hash.

    The lifecycle owner must already have proved the original operation and
    sealed plan. Hash, kind, operation correlation and first IN_FLIGHT phase
    are bound here; no cursor or later alias state supplies those values.
    """
    def __init__(self, operation_id, cutoff_ref):
        from vati.core.ledger import GENESIS
        if not isinstance(operation_id, str) or not operation_id or not isinstance(cutoff_ref, str) or len(cutoff_ref) != 64:
            raise ValueError('invalid original deletion boundary')
        self.operation_id, self.cutoff_ref = operation_id, cutoff_ref
        self.seq, self.chain = 0, GENESIS
        self.finished = False
        self.failed = False

    def advance(self, ledger, *, event_budget):
        import hashlib
        if self.failed:
            raise LedgerError('retained_scan_restart_required')
        if type(event_budget) is not int or event_budget <= 0:
            raise ValueError('invalid retained history work budget')
        count = 0
        try:
            while not self.finished and count < event_budget:
                page = ledger.read_page(self.seq, 1)
                if not page:
                    raise LedgerError('retained_original_boundary_unavailable')
                seq, event, previous, chain = page[0]
                if (seq <= self.seq or previous != self.chain or event.hash != canonical_hash(event.body())
                    or chain != hashlib.sha256((previous + event.hash).encode()).hexdigest()):
                    raise LedgerError('retained_source_chain_invalid')
                self.seq, self.chain = seq, chain
                count += 1
                if event.hash == self.cutoff_ref:
                    if (event.kind is not EventKind.ACCOUNT_OPERATION or event.correlation_id != self.operation_id
                        or event.payload.get('phase') != 'IN_FLIGHT' or event.payload.get('previous_ref') != ''):
                        raise LedgerError('retained_original_boundary_invalid')
                    self.finished = True
            return {'events': count, 'finished': self.finished}
        except BaseException:
            self.failed = True
            raise


class OriginalReferenceScan:
    """Find one exact event while proving its position under an existing anchor."""
    def __init__(self, through_seq, through_chain, reference):
        from vati.core.ledger import GENESIS
        if (type(through_seq) is not int or through_seq <= 0 or not isinstance(through_chain, str)
            or len(through_chain) != 64 or not isinstance(reference, str) or len(reference) != 64):
            raise ValueError('invalid original reference binding')
        self.through_seq, self.through_chain, self.reference = through_seq, through_chain, reference
        self.seq, self.chain = 0, GENESIS
        self._found = None
        self.finished = self.failed = False

    def advance(self, ledger, *, event_budget):
        import hashlib
        if self.failed:
            raise LedgerError('retained_scan_restart_required')
        if type(event_budget) is not int or event_budget <= 0:
            raise ValueError('invalid retained history work budget')
        count = 0
        try:
            while not self.finished and count < event_budget:
                page = ledger.read_page(self.seq, 1, through_seq=self.through_seq)
                if not page:
                    raise LedgerError('retained_original_anchor_unavailable')
                seq, event, previous, chain = page[0]
                if (seq <= self.seq or previous != self.chain or event.hash != canonical_hash(event.body())
                    or chain != hashlib.sha256((previous + event.hash).encode()).hexdigest()):
                    raise LedgerError('retained_source_chain_invalid')
                if event.hash == self.reference:
                    if self._found is None:
                        self._found = (seq, event, chain)
                self.seq, self.chain = seq, chain
                count += 1
                if seq == self.through_seq:
                    if chain != self.through_chain:
                        raise LedgerError('retained_original_anchor_changed')
                    self.finished = True
            return {'events': count, 'finished': self.finished}
        except BaseException:
            self.failed = True
            raise

    def result(self):
        if self.failed or not self.finished:
            raise LedgerError('retained_original_reference_unproven')
        return self._found


class OriginalSnapshotDiscovery:
    """Bounded original snapshot selection; every candidate's refs are proved.

    A candidate pauses the chain walk while exact references are re-scanned
    under the same deletion anchor. No event, statement or query list is
    accumulated, and each step charges every inspected event to its budget.
    """
    def __init__(self, through_seq, through_chain, lifecycle_alias, profile):
        import copy
        from vati.core.ledger import GENESIS
        self.through_seq, self.through_chain = through_seq, through_chain
        self.alias, self.profile = lifecycle_alias, copy.deepcopy(profile)
        self.seq, self.chain = 0, GENESIS
        self.candidate = None
        self.selected = None
        self.ref_scan = None
        self.query_validation = None
        self.found = {}
        self.phase = 'WALK'
        self.finished = self.failed = False
        self.lineage_gap = False

    def _candidate(self, event):
        if (event.kind is not EventKind.ACCOUNT_SNAPSHOT or event.producer not in {'vati-service','vati-account-service'}
            or event.payload.get('account_alias') != self.alias):
            return None
        p = event.payload; observation = p.get('funding_observation')
        if not isinstance(observation, dict): return {'lineage_gap':True} if 'funding_observation' in p else None
        statement = observation.get('statement')
        if not isinstance(statement,dict): return {'lineage_gap':True}
        mark = p.get('native_account_mark') or observation.get('native_mark')
        if not isinstance(mark,dict): return {'lineage_gap':True}
        profile = self.profile
        foreign = False
        if profile['broker'] == 'CTRADER':
            if mark.get('schema') != 'native-account-mark/1': return {'lineage_gap':True}
            try: typed = NativeAccountMark.from_body(mark)
            except (ValueError, TypeError, ArithmeticError): return {'lineage_gap':True}
            if (typed.account_alias != profile['alias'] or str(typed.native_account_id) != profile['login']
                or typed.currency != profile['currency']
                or typed.environment != ('DEMO' if profile['demo'] else 'LIVE')): return None
            query_ref = None
            statement_ref = statement.get('statement_ref')
        elif profile['broker'] == 'MT5':
            if mark.get('schema') != 'mt5-account-mark/1': return {'lineage_gap':True}
            identity=(mark.get('account_alias'),mark.get('login'),mark.get('server'),mark.get('currency'),mark.get('demo'))
            if (not isinstance(identity[0],str) or not identity[0].strip() or type(identity[1]) is not int or identity[1] <= 0
                or any(not isinstance(x,str) or not x.strip() for x in identity[2:4]) or type(identity[4]) is not bool
                or mark.get('scope_hash') != canonical_hash({'provider':'MT5','login':identity[1],
                    'server':identity[2],'currency':identity[3],'demo':identity[4]})):
                return {'lineage_gap':True}
            foreign = (mark.get('account_alias') != profile['alias'] or str(mark.get('login')) != profile['login']
                or mark.get('server') != profile['server'] or mark.get('currency') != profile['currency']
                or mark.get('demo') is not profile['demo'])
            query_ref = observation.get('query_ref')
            statement_ref = statement.get('statement_ref')
        else:
            return None
        scope = mark['scope_hash']
        if (observation.get('scope_hash') != scope or not isinstance(statement_ref,str) or len(statement_ref)!=64
            or profile['broker']=='MT5' and (not isinstance(query_ref,str) or len(query_ref)!=64)):
            return {'lineage_gap':True}
        return {'scope_hash': scope, 'snapshot_ref': event.hash, 'query_ref': query_ref,
            'statement_ref': statement_ref, 'source_observed_at_ms': mark.get('observed_at_ms'), 'mark': mark, 'foreign': foreign}

    def _accept_candidate(self):
        statement_seq, _, statement_chain=self.found['STATEMENT']
        if self.candidate['foreign']:
            self.candidate=self.ref_scan=self.query_validation=None;self.found={};self.phase='WALK';return
        self.selected={k:v for k,v in self.candidate.items() if k not in {'mark','foreign'}}
        self.selected.update(statement_seq=statement_seq,statement_chain=statement_chain)
        self.candidate=self.ref_scan=self.query_validation=None;self.found={};self.phase='WALK'

    def advance(self, ledger, *, event_budget):
        import hashlib
        if self.failed: raise LedgerError('retained_scan_restart_required')
        if type(event_budget) is not int or event_budget <= 0: raise ValueError('invalid retained history work budget')
        count = 0
        try:
            while not self.finished and count < event_budget:
                if self.phase == 'FINAL_QUERY_HISTORY':
                    try:
                        step=self.query_validation.advance(ledger,event_budget=event_budget-count)
                    except LedgerError as error:
                        count+=self.query_validation.last_advance_events
                        if (str(error)=='mt5_native_query_statement_unavailable'
                            and self.query_validation.failure_seq>self.selected['snapshot_seq']):
                            self.lineage_gap=True;self.finished=True;break
                        raise
                    count+=step['events']
                    if self.query_validation.finished:self.finished=True
                    break
                if self.phase == 'QUERY_HISTORY':
                    try:
                        step=self.query_validation.advance(ledger,event_budget=event_budget-count)
                    except LedgerError as error:
                        count+=self.query_validation.last_advance_events
                        if (str(error)=='mt5_native_query_statement_unavailable'
                            and (self.selected is None or self.query_validation.failure_seq>self.selected['snapshot_seq'])):
                            self.lineage_gap=True;self.candidate=self.ref_scan=self.query_validation=None
                            self.found={};self.phase='WALK';continue
                        raise
                    count+=step['events']
                    if not self.query_validation.finished:break
                    self._accept_candidate()
                    continue
                if self.phase in {'STATEMENT','QUERY'}:
                    step = self.ref_scan.advance(ledger, event_budget=event_budget-count)
                    count += step['events']
                    if not self.ref_scan.finished: break
                    found = self.ref_scan.result()
                    if found is None or found[0] >= self.candidate['snapshot_seq']:
                        self.lineage_gap=True;self.candidate=self.ref_scan=None;self.found={};self.phase='WALK'
                        continue
                    self.found[self.phase] = found
                    if self.phase == 'STATEMENT' and self.candidate['query_ref'] is not None:
                        self.phase = 'QUERY'
                        self.ref_scan = OriginalReferenceScan(self.through_seq,self.through_chain,self.candidate['query_ref'])
                        continue
                    statement_seq, statement, statement_chain = self.found['STATEMENT']
                    book = FundingBook(ledger) if self.profile['broker']=='CTRADER' else Mt5FundingBook(ledger)
                    if statement.correlation_id != book.correlation_prefix+self.candidate['scope_hash']:
                        raise LedgerError('retained_original_statement_unavailable')
                    book.validate_event(statement,self.candidate['scope_hash'])
                    if self.candidate['query_ref'] is not None:
                        query_seq, query, _ = self.found['QUERY']
                        if query.payload.get('mark') != self.candidate['mark'] and self.candidate['foreign']:
                            self.lineage_gap=True;self.candidate=self.ref_scan=None;self.found={};self.phase='WALK'
                            continue
                        if (statement_seq >= query_seq or query.correlation_id != 'mt5-query:'+self.candidate['scope_hash']
                            or query.payload.get('mark') != self.candidate['mark']):
                            raise LedgerError('retained_original_query_unavailable')
                        book.validate_query(query,self.candidate['scope_hash'],statement)
                        self.query_validation=OriginalQueryHistoryValidation(self.candidate['snapshot_seq'],self.candidate['snapshot_chain'],self.candidate['scope_hash'])
                        self.phase='QUERY_HISTORY'
                        continue
                    self._accept_candidate()
                    continue
                page = ledger.read_page(self.seq,1,through_seq=self.through_seq)
                if not page: raise LedgerError('retained_original_anchor_unavailable')
                seq,event,previous,chain = page[0]
                if (seq <= self.seq or previous != self.chain or event.hash != canonical_hash(event.body())
                    or chain != hashlib.sha256((previous+event.hash).encode()).hexdigest()):
                    raise LedgerError('retained_source_chain_invalid')
                self.seq,self.chain=seq,chain;count+=1
                candidate = None if self.lineage_gap else self._candidate(event)
                if candidate is not None and candidate.get('lineage_gap'):
                    self.lineage_gap=True;candidate=None
                if candidate is not None:
                    candidate['snapshot_seq']=seq;candidate['snapshot_chain']=chain;self.candidate=candidate;self.phase='STATEMENT'
                    self.ref_scan=OriginalReferenceScan(self.through_seq,self.through_chain,candidate['statement_ref'])
                if seq == self.through_seq:
                    if chain != self.through_chain: raise LedgerError('retained_original_anchor_changed')
                    if self.phase != 'WALK': raise LedgerError('retained_original_boundary_invalid')
                    if self.profile['broker']=='MT5' and self.selected is not None:
                        self.query_validation=OriginalQueryHistoryValidation(self.through_seq,self.through_chain,self.selected['scope_hash'])
                        self.phase='FINAL_QUERY_HISTORY'
                    else:self.finished = True
            return {'events':count,'finished':self.finished}
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError) as error:
            self.failed=True;raise LedgerError('retained_original_source_invalid') from error
        except BaseException:
            self.failed=True;raise

    def result(self):
        if self.failed or not self.finished: raise LedgerError('retained_original_snapshot_unproven')
        return self.selected


class OriginalMovementPage:
    """One bounded keyset page under the original statement-chain anchor."""
    def __init__(self, through_seq, through_chain, *, broker, scope_hash, after_native_id, limit):
        if broker not in {'CTRADER','MT5'} or not isinstance(scope_hash,str) or len(scope_hash)!=64:
            raise ValueError('invalid original funding scope')
        self.broker,self.scope_hash=broker,scope_hash
        self.scan=VerifiedLedgerScan(through_seq,through_chain)
        self.frontier=MovementFrontier(after_native_id,limit)
        self.finished=self.failed=False
        self._page=None

    def advance(self,ledger,*,event_budget,row_budget):
        if self.failed: raise LedgerError('retained_scan_restart_required')
        if self.finished: return {'events':0,'rows':0,'finished':True}
        book=FundingBook(ledger) if self.broker=='CTRADER' else Mt5FundingBook(ledger)
        def selected(event):
            if event.correlation_id != book.correlation_prefix+self.scope_hash:
                return False
            book.validate_event(event,self.scope_hash)
            return event.payload['state']=='OBSERVED'
        def observe(event,row):
            self.frontier.observe(row,event.hash,event.payload['statement']['observed_at_ms'],event.received_time_ms)
        try:
            result=self.scan.advance(ledger,selected,observe,event_budget=event_budget,row_budget=row_budget)
            if self.scan.finished:
                self._page=self.frontier.page();self.finished=True
            return result | {'finished':self.finished}
        except BaseException:
            self.failed=True;raise

    def result(self):
        if self.failed or not self.finished:raise LedgerError('retained_original_page_unproven')
        return self._page


class OriginalMetadataPage:
    """One coverage or conflict-evidence page, ordered by event ordinal/item.

    Large conflict maps are traversed as already-decoded dictionary iterators;
    each examined entry consumes row budget. The bookmark controls output only,
    never chain progress or global consistency qualification.
    """
    def __init__(self,through_seq,through_chain,*,broker,scope_hash,collection,after,limit):
        from vati.core.ledger import GENESIS
        if (broker not in {'CTRADER','MT5'} or not isinstance(scope_hash,str) or len(scope_hash)!=64
            or collection not in {'COVERAGE','CONFLICT'} or type(limit) is not int or not 1<=limit<=100
            or not isinstance(after,tuple) or len(after)!=2 or any(type(v) is not int or v<0 for v in after)):
            raise ValueError('invalid original metadata page binding')
        self.through_seq,self.through_chain=through_seq,through_chain
        self.broker,self.scope_hash,self.collection,self.after,self.limit=broker,scope_hash,collection,after,limit
        self.seq,self.chain=0,GENESIS
        self.pending=None;self.rows=[];self.finished=self.failed=False

    def advance(self,ledger,*,event_budget,row_budget):
        import hashlib
        if self.failed:raise LedgerError('retained_scan_restart_required')
        if type(event_budget) is not int or event_budget<=0 or type(row_budget) is not int or row_budget<=0:
            raise ValueError('invalid retained history work budget')
        if self.finished:return {'events':0,'rows':0,'finished':True}
        events=rows=0;book=FundingBook(ledger) if self.broker=='CTRADER' else Mt5FundingBook(ledger)
        try:
            while not self.finished:
                if self.pending is None:
                    if events==event_budget:break
                    page=ledger.read_page(self.seq,1,through_seq=self.through_seq)
                    if not page:raise LedgerError('retained_original_anchor_unavailable')
                    seq,event,previous,chain=page[0]
                    if (seq<=self.seq or previous!=self.chain or event.hash!=canonical_hash(event.body())
                        or chain!=hashlib.sha256((previous+event.hash).encode()).hexdigest()):
                        raise LedgerError('retained_source_chain_invalid')
                    self.seq,self.chain=seq,chain;events+=1
                    matching=event.correlation_id==book.correlation_prefix+self.scope_hash
                    if matching:
                        book.validate_event(event,self.scope_hash)
                        if len(self.rows)<self.limit+1 and self.collection=='COVERAGE' and event.payload['state']=='OBSERVED':
                            self.pending={'event':event,'seq':seq,'index':0,'iterator':iter((None,))}
                        elif len(self.rows)<self.limit+1 and self.collection=='CONFLICT' and event.payload['state']=='CONFLICT':
                            refs=event.payload.get('conflicting_original_refs')
                            if not isinstance(refs,dict):raise LedgerError('retained_original_conflict_invalid')
                            from itertools import chain as iterator_chain
                            self.pending={'event':event,'seq':seq,'index':0,'iterator':iterator_chain(
                                (('EVENT',None),), (('REFERENCE',item) for item in refs.items()),
                                (('MOVEMENT',row) for row in event.payload['statement']['movements']))}
                    if self.pending is None and seq==self.through_seq:
                        if chain!=self.through_chain:raise LedgerError('retained_original_anchor_changed')
                        self.finished=True
                    continue
                if rows==row_budget:break
                item=next(self.pending['iterator'],None)
                if item is None and self.collection=='CONFLICT':
                    self.pending=None
                elif self.collection=='COVERAGE':
                    event=self.pending['event'];key=(self.pending['seq'],0);rows+=1
                    if key>self.after:
                        body=event.payload['statement'];self.rows.append((key,{'from_ms':body['from_ms'],'to_ms':body['to_ms'],'statement_ref':event.hash}))
                    self.pending=None
                else:
                    event=self.pending['event'];key=(self.pending['seq'],self.pending['index']);self.pending['index']+=1;rows+=1
                    kind,value=item
                    if kind=='EVENT':
                        body=event.payload['statement']
                        evidence={'kind':'CONFLICT_EVENT','statement_ref':event.hash,'observed_at_ms':body['observed_at_ms'],
                            'received_at_ms':event.received_time_ms,'from_ms':body['from_ms'],'to_ms':body['to_ms']}
                    elif kind=='REFERENCE':
                        native_id,original_ref=value
                        if not isinstance(native_id,str) or not isinstance(original_ref,str):raise LedgerError('retained_original_conflict_invalid')
                        evidence={'kind':'CONFLICT_REFERENCE','statement_ref':event.hash,'native_id':native_id,'original_ref':original_ref}
                    elif kind=='MOVEMENT':
                        evidence={'kind':'CONFLICT_MOVEMENT','statement_ref':event.hash,'movement':value,
                            'lineage':'QUARANTINED_NOT_OBSERVED','execution_authority':False}
                    else:raise LedgerError('retained_original_conflict_invalid')
                    if key>self.after:self.rows.append((key,evidence))
                    if len(self.rows)==self.limit+1:self.pending=None
                if self.pending is None and self.seq==self.through_seq:
                    if self.chain!=self.through_chain:raise LedgerError('retained_original_anchor_changed')
                    self.finished=True
            return {'events':events,'rows':rows,'finished':self.finished}
        except BaseException:
            self.failed=True;raise

    def result(self):
        if self.failed or not self.finished:raise LedgerError('retained_original_page_unproven')
        page=self.rows[:self.limit]
        return [row for _,row in page],len(self.rows)>self.limit,(page[-1][0] if page else self.after)


class RetainedHistoryReadJob:
    """Trusted, resumable original-owner data work; never a new authority."""
    def __init__(self,*,operation_id,cutoff_ref,alias,profile,collection,after,limit):
        import copy
        if collection not in {'MOVEMENTS','COVERAGE','CONFLICT'}:
            raise ValueError('invalid retained history collection')
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('invalid retained history page limit')
        if collection=='MOVEMENTS':
            if type(after) is not int or after<0:raise ValueError('invalid movement bookmark')
        elif not isinstance(after,tuple) or len(after)!=2 or any(type(v) is not int or v<0 for v in after):
            raise ValueError('invalid metadata bookmark')
        self.operation_id,self.alias,self.profile=operation_id,alias,copy.deepcopy(profile)
        self.collection,self.after,self.limit=collection,after,limit
        self.boundary=OriginalBoundaryScan(operation_id,cutoff_ref)
        self.snapshot=self.validation=self.page=None
        self.phase='BOUNDARY';self.finished=self.failed=False
        self._result=None

    def advance(self,ledger,*,event_budget,row_budget):
        if self.failed:raise LedgerError('retained_scan_restart_required')
        if self.finished:return {'events':0,'rows':0,'finished':True}
        try:
            if self.phase=='BOUNDARY':
                step=self.boundary.advance(ledger,event_budget=event_budget)
                if self.boundary.finished:
                    self.snapshot=OriginalSnapshotDiscovery(self.boundary.seq,self.boundary.chain,self.alias,self.profile)
                    self.phase='SNAPSHOT'
                return {'events':step['events'],'rows':0,'finished':False}
            if self.phase=='SNAPSHOT':
                step=self.snapshot.advance(ledger,event_budget=event_budget)
                if self.snapshot.finished:
                    source=self.snapshot.result()
                    if source is None:
                        self._result={'state':'UNOBSERVED','reason':('ORIGINAL_LINEAGE_REQUIRES_RECONCILIATION' if self.snapshot.lineage_gap else 'ORIGINAL_PRE_DELETION_NATIVE_SOURCE_UNOBSERVED')}
                        self.finished=True
                    else:
                        self.validation=GlobalMovementValidation(source['statement_seq'],source['statement_chain'],
                            broker=self.profile['broker'],scope_hash=source['scope_hash'],batch_limit=self.limit)
                        self.phase='VALIDATE'
                return {'events':step['events'],'rows':0,'finished':self.finished}
            if self.phase=='VALIDATE':
                step=self.validation.advance(ledger,event_budget=event_budget,row_budget=row_budget)
                if self.validation.finished:
                    source=self.snapshot.result()
                    args={'broker':self.profile['broker'],'scope_hash':source['scope_hash'],'limit':self.limit}
                    if self.collection=='MOVEMENTS':
                        self.page=OriginalMovementPage(source['statement_seq'],source['statement_chain'],after_native_id=self.after,**args)
                    else:
                        self.page=OriginalMetadataPage(source['statement_seq'],source['statement_chain'],collection=self.collection,after=self.after,**args)
                    self.phase='PAGE'
                return step | {'finished':False}
            step=self.page.advance(ledger,event_budget=event_budget,row_budget=row_budget)
            if self.page.finished:
                source=self.snapshot.result()
                if self.collection=='MOVEMENTS':
                    rows,more=self.page.result();bookmark=(rows[-1]['movement']['native_id'] if rows else self.after)
                else:
                    rows,more,bookmark=self.page.result()
                prefix_state='CONFLICT' if self.validation.saw_conflict else 'OBSERVED'
                self._result={'state':'RECONCILIATION_REQUIRED' if self.snapshot.lineage_gap else prefix_state,
                    'original_prefix_state':prefix_state,
                    'reason':'ORIGINAL_LATER_LINEAGE_UNAVAILABLE' if self.snapshot.lineage_gap else 'ORIGINAL_OBSERVED_PREFIX_NOT_LIFETIME_COVERAGE','source':source,
                    'collection':self.collection,'rows':rows,'more':more,'bookmark':bookmark,
                    'movement_count':None}
                self.finished=True
            return step | {'finished':self.finished}
        except BaseException:
            self.failed=True;raise

    def result(self):
        if self.failed or not self.finished:raise LedgerError('retained_original_page_unproven')
        return self._result


class OriginalQueryHistoryValidation:
    """Validate each original-prefix MT5 query against its original statement."""
    def __init__(self,through_seq,through_chain,scope_hash):
        from vati.core.ledger import GENESIS
        self.through_seq,self.through_chain,self.scope_hash=through_seq,through_chain,scope_hash
        self.seq,self.chain=0,GENESIS
        self.pending=self.ref_scan=None
        self.failure_seq=0
        self.last_advance_events=0
        self.finished=self.failed=False

    def advance(self,ledger,*,event_budget):
        import hashlib
        if self.failed:raise LedgerError('retained_scan_restart_required')
        if type(event_budget) is not int or event_budget<=0:raise ValueError('invalid retained history work budget')
        count=0;self.last_advance_events=0
        try:
            while not self.finished and count<event_budget:
                if self.pending is not None:
                    step=self.ref_scan.advance(ledger,event_budget=event_budget-count);count+=step['events']
                    if not self.ref_scan.finished:break
                    found=self.ref_scan.result()
                    if found is None:
                        self.failure_seq=self.pending[0];raise LedgerError('mt5_native_query_statement_unavailable')
                    if found[0]>=self.pending[0]:
                        self.failure_seq=self.pending[0];raise LedgerError('mt5_native_query_statement_unavailable')
                    _,query=self.pending;_,statement,_=found
                    book=Mt5FundingBook(ledger)
                    if statement.correlation_id!=book.correlation_prefix+self.scope_hash:
                        raise LedgerError('mt5_native_query_journal_invalid')
                    book.validate_query(query,self.scope_hash,statement)
                    self.pending=self.ref_scan=None
                    if self.seq==self.through_seq:self.finished=True
                    continue
                page=ledger.read_page(self.seq,1,through_seq=self.through_seq)
                if not page:raise LedgerError('retained_original_anchor_unavailable')
                seq,event,previous,chain=page[0]
                if (seq<=self.seq or previous!=self.chain or event.hash!=canonical_hash(event.body())
                    or chain!=hashlib.sha256((previous+event.hash).encode()).hexdigest()):
                    raise LedgerError('retained_source_chain_invalid')
                self.seq,self.chain=seq,chain;count+=1
                if seq==self.through_seq and chain!=self.through_chain:raise LedgerError('retained_original_anchor_changed')
                if event.correlation_id=='funding-mt5:'+self.scope_hash:
                    Mt5FundingBook(ledger).validate_event(event,self.scope_hash)
                if event.kind is EventKind.FUNDING_MT5_QUERY and event.correlation_id=='mt5-query:'+self.scope_hash:
                    ref=event.payload.get('cash_statement_ref')
                    if not isinstance(ref,str) or len(ref)!=64:
                        self.failure_seq=seq;raise LedgerError('mt5_native_query_statement_unavailable')
                    self.pending=(seq,event);self.ref_scan=OriginalReferenceScan(self.through_seq,self.through_chain,ref)
                elif seq==self.through_seq:self.finished=True
            return {'events':count,'finished':self.finished}
        except BaseException:
            self.failed=True;raise
        finally:
            self.last_advance_events=count
