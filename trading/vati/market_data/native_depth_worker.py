"""Configured one-shot native depth producer; task DATA never grants authority.

One bounded reader per service, separate from the protective socket. Original
request stages live with the existing depth archive; capture and task outcomes
remain separate. A possible read without captured bytes is never recaptured.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import json
import math
import re
import threading

from vati.accounts.registry import AccountRegistry, BrokerKind
from vati.accounts.resource_version import resource_snapshot
from vati.accounts.physical_scope import ctrader_host
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.file_lock import exclusive_state_lock
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.feed import native_integer
from vati.market_data.native_archive import NativeArchiveError, REQUEST_ID
from vati.market_data.native_depth import NativeDepthArchive, NativeDepthCapture

MAX_TIME = 253402300799000
DIGEST = re.compile(r'[0-9a-f]{64}')


def source_profile_ref(registry_path, alias):
    """Opaque selector, NOT owner, provider or execution authority."""
    return canonical_hash({'registry': str(Path(registry_path).resolve()), 'alias': alias})


@dataclass(frozen=True)
class NativeDepthSourcePolicy:
    """Pure data validation composes existing native reader/collector ranges."""
    config_json: str

    @classmethod
    def parse(cls, body):
        fields = {'schema', 'archive_root', 'source_profile_ref', 'resource_version',
                  'config_generation', 'queue_capacity', 'max_history_bytes', 'max_request_bytes',
                  'max_requests', 'operation_timeout_s', 'max_read_frames', 'max_read_bytes', 'requests'}
        if type(body) is not dict or set(body) != fields or body['schema'] != 'vati.depth-source-policy/1':
            raise ValueError('NATIVE_DEPTH_CONFIG_INVALID')
        if (type(body['archive_root']) is not str or not Path(body['archive_root']).is_absolute()
                or Path(body['archive_root']).is_symlink()
                or str(Path(body['archive_root']).resolve()) != body['archive_root']):
            raise ValueError('NATIVE_DEPTH_ROOT_INVALID')
        for name in ('source_profile_ref', 'resource_version', 'config_generation'):
            if type(body[name]) is not str or DIGEST.fullmatch(body[name]) is None:
                raise ValueError('NATIVE_DEPTH_BINDING_INVALID')
        native_integer(body['queue_capacity'], minimum=1, maximum=16)
        native_integer(body['max_requests'], minimum=1, maximum=10000)
        native_integer(body['max_history_bytes'], minimum=1, maximum=256*1024**2)
        native_integer(body['max_request_bytes'], minimum=1, maximum=1024**2)
        native_integer(body['max_read_frames'], minimum=1, maximum=65536)
        native_integer(body['max_read_bytes'], minimum=1, maximum=256*1024**2)
        seconds = body['operation_timeout_s']
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 300:
            raise ValueError('NATIVE_DEPTH_TIME_BUDGET_INVALID')
        requests = body['requests']
        if type(requests) is not list or not 1 <= len(requests) <= body['queue_capacity']:
            raise ValueError('NATIVE_DEPTH_QUEUE_CAPACITY')
        seen = set()
        for request in requests:
            if type(request) is not dict or set(request) != {
                    'request_id', 'contract', 'contract_ref', 'max_age_ms', 'limit',
                    'not_before_ms', 'expires_at_ms'}:
                raise ValueError('NATIVE_DEPTH_REQUEST_INVALID')
            identity = request['request_id']
            if type(identity) is not str or REQUEST_ID.fullmatch(identity) is None or identity in seen:
                raise ValueError('NATIVE_DEPTH_REQUEST_ID_INVALID')
            seen.add(identity)
            contract = NativeSymbolContract.from_body(request['contract'])
            if request['contract_ref'] != canonical_hash(contract.body()):
                raise ValueError('NATIVE_DEPTH_CONTRACT_REFERENCE_INVALID')
            native_integer(request['max_age_ms'], minimum=1)
            native_integer(request['limit'], minimum=1, maximum=4096)
            native_integer(request['not_before_ms'], maximum=MAX_TIME)
            native_integer(request['expires_at_ms'], minimum=request['not_before_ms']+1, maximum=MAX_TIME)
        return cls(canonical_json(body))

    def body(self):
        return json.loads(self.config_json)


class NativeDepthWorker:
    def __init__(self, service, policy, *, reader_factory=None):
        self.service = service
        self.policy = policy
        self.config = policy.body()
        self.clock = service.clock
        self.archive = NativeDepthArchive(self.config['archive_root'], clock=self.clock,
                                         max_history_bytes=self.config['max_history_bytes'])
        self._factory = reader_factory or (lambda: service.adapter.market_reader(
            collection_timeout_s=self.config['operation_timeout_s'],
            max_read_frames=self.config['max_read_frames'], max_read_bytes=self.config['max_read_bytes']))
        self._stop = threading.Event()
        self._thread = None
        self._mutex = threading.Lock()
        self._outcomes = {}
        self._active = False

    def start(self):
        with self._mutex:
            if self._thread is not None or self._stop.is_set():
                return
            self._thread = threading.Thread(target=self._run, name='vati-native-depth-reader', daemon=True)
            self._thread.start()

    def snapshot(self):
        with self._mutex:
            return {'state': 'STOP_PENDING' if self._stop.is_set() and self._active else
                    'RUNNING' if self._active else 'STOPPED' if self._stop.is_set() else 'IDLE',
                    'requests': json.loads(canonical_json(self._outcomes)),
                    'authority_effect': 'NONE', 'provider_qualified': False}

    def wait_idle(self, timeout):
        thread = self._thread
        if thread is threading.current_thread():
            return False
        if thread is not None:
            thread.join(timeout)
        return thread is None or not thread.is_alive()

    def close(self):
        self._stop.set()
        # An uninterruptible injected host connector cannot be killed as a Python
        # thread. Retain the worker/capacity and report STOP_PENDING truthfully.
        return self.wait_idle(self.config['operation_timeout_s']+1)

    def _check(self, request, *, historical=False):
        if self._stop.is_set() or getattr(self.service, 'stop_requested', False):
            raise NativeArchiveError('NATIVE_DEPTH_STOPPED')
        if canonical_json(getattr(self.service.cfg, 'depth_capture', None)) != self.policy.config_json:
            raise NativeArchiveError('NATIVE_DEPTH_CONFIG_CHANGED')
        cfg = self.service.cfg
        registry = AccountRegistry(cfg.registry_path)
        account = registry.get(cfg.account_alias)
        contract = NativeSymbolContract.from_body(request['contract'])
        scope = contract.native_scope
        if (account.broker != BrokerKind.CTRADER or not account.enabled
                or str(scope['native_account_id']) != account.login
                or scope['transport_host'] != ctrader_host(account)
                or source_profile_ref(cfg.registry_path, cfg.account_alias) != self.config['source_profile_ref']):
            raise NativeArchiveError('NATIVE_DEPTH_CURRENT_SCOPE_CHANGED')
        adapter = self.service.adapter
        if (getattr(adapter, 'ctid_trader_account_id', None) != scope['native_account_id']
                or getattr(getattr(adapter, 'transport', None), 'host', None) != scope['transport_host']):
            raise NativeArchiveError('NATIVE_DEPTH_ADAPTER_SCOPE_CHANGED')
        if not historical:
            # A native file generation is an existing opaque source version. No
            # secret hash/values are journaled. Env-only keys have no such proof.
            target = account.credential_ref.secrets_file
            if not target or Path(target).is_symlink() or not Path(target).is_file():
                raise NativeArchiveError('NATIVE_DEPTH_CREDENTIAL_GENERATION_UNBOUND')
            if resource_snapshot(registry, account.alias)['resource_version'] != self.config['resource_version']:
                raise NativeArchiveError('NATIVE_DEPTH_SOURCE_VERSION_CHANGED')
            symbol = adapter.symbol(contract.metadata['light']['symbolName'])
            if symbol.native_contract is None or symbol.native_contract.revision != contract.revision:
                raise NativeArchiveError('NATIVE_DEPTH_CURRENT_CONTRACT_CHANGED')
        # Sample after all native registry/metadata reads and lock waits.
        now = native_integer(self.clock(), maximum=MAX_TIME)
        if not historical and not request['not_before_ms'] <= now < request['expires_at_ms']:
            raise NativeArchiveError('NATIVE_DEPTH_REQUEST_EXPIRED_OR_NOT_READY')
        return registry, account

    @contextmanager
    def _publication_scope(self, request):
        registry = AccountRegistry(self.service.cfg.registry_path)
        alias = self.service.cfg.account_alias
        with registry.operation_lock(alias), registry._mutation_lock():
            current = AccountRegistry(registry.path).get(alias)
            target = current.credential_ref.secrets_file
            if not target:
                raise NativeArchiveError('NATIVE_DEPTH_CREDENTIAL_GENERATION_UNBOUND')
            with exclusive_state_lock(Path(target)):
                self._check(request)
                yield

    def _intent(self, request):
        return {'request': request, 'policy': {k:v for k,v in self.config.items() if k != 'requests'}}

    def capture(self, request):
        """Same original cross-process lock covers task and collection arbitration."""
        request = json.loads(canonical_json(request))
        if request not in self.config['requests']:
            raise NativeArchiveError('NATIVE_DEPTH_REQUEST_NOT_CONFIGURED')
        contract = NativeSymbolContract.from_body(request['contract'])
        scope, identity = contract.native_scope, request['request_id']
        intent = self._intent(request)
        part = self.archive._partition(scope, 'DEPTH', create=True)
        options = {'max_bytes': self.config['max_request_bytes']}
        # This source-read slot is NOT a financial/registry/archive-head writer.
        # It serializes actual native reader lifetime across processes/symbols
        # for the same physical account in this configured archive owner.
        reader_scope = {k:v for k,v in scope.items() if k != 'native_symbol_id'}
        slot = self.archive.root / ('depth-reader-' + canonical_hash(reader_scope))
        with exclusive_state_lock(part/('request-'+canonical_hash(identity))), exclusive_state_lock(slot):
            task = self.archive.request_state(scope, identity, **options)
            original = self.archive.lookup(scope, 'DEPTH', identity)
            if task is not None and task['intent'] != intent:
                raise NativeArchiveError('NATIVE_DEPTH_ORIGINAL_REQUEST_CONFLICT')
            if original is not None:
                self._check(request, historical=True)
                if task is None or task['history'][-1]['state'] == 'REFUSED':
                    raise NativeArchiveError('NATIVE_DEPTH_HISTORICAL_CAPTURE_UNBOUND')
                if (original['contract_revision'] != contract.revision
                        or original['captured_max_age_ms'] != request['max_age_ms']
                        or original['captured_limit'] != request['limit']):
                    raise NativeArchiveError('NATIVE_DEPTH_ORIGINAL_CAPTURE_CONFLICT')
                if original['index_state'] != 'CONSISTENT':
                    original = self.archive.reconcile(scope, 'DEPTH', identity)
                self.archive.advance_request(scope, identity, intent, 'CAPTURED', **options)
                return {'state': 'CAPTURED', 'receipt': original}
            if task is None:
                task = self.archive.prepare_request(scope, identity, intent,
                    max_requests=self.config['max_requests'], **options)
            state = task['history'][-1]['state']
            if state != 'PREPARED':
                return {'state': 'UNCERTAIN' if state != 'REFUSED' else 'REFUSED',
                        'reason': 'ORIGINAL_CAPTURE_MISSING_NO_RECAPTURE', 'receipt': None}
            try:
                self._check(request)
            except Exception:
                self.archive.advance_request(scope, identity, intent, 'REFUSED', **options)
                return {'state': 'REFUSED', 'reason': 'CURRENT_SOURCE_SCOPE_OR_EXPIRY_REFUSED', 'receipt': None}
            self.archive.advance_request(scope, identity, intent, 'READ_MAY_HAVE_OCCURRED', **options)
            reader = None
            try:
                # The stage commit itself can block. Recheck before constructing
                # the independent reader; a missing ACK never proves no read.
                self._check(request)
                reader = self._factory()
                returned, observed = reader.read_depth(contract, max_age_ms=request['max_age_ms'], limit=request['limit'])
                capacity = reader.read_capacity_snapshot()
                reader.close()
                reader = None
                if (not isinstance(returned, NativeSymbolContract) or returned.revision != contract.revision
                        or returned.native_scope != scope):
                    raise NativeArchiveError('NATIVE_DEPTH_RETURNED_SCOPE_CHANGED')
                captured = NativeDepthCapture.capture(observed, capacity,
                    max_age_ms=request['max_age_ms'], limit=request['limit'])
                with self._publication_scope(request):
                    receipt = self.archive.record(identity, returned, captured,
                        before_replace=lambda: self._check(request))
                self.archive.advance_request(scope, identity, intent, 'CAPTURED', **options)
                return {'state': 'CAPTURED', 'receipt': receipt}
            except Exception:
                # A possible record commit is independent evidence, recovered
                # on original read. Never reset the request or refetch the book.
                self.archive.advance_request(scope, identity, intent, 'UNCERTAIN', **options)
                return {'state': 'UNCERTAIN', 'reason': 'ORIGINAL_READ_OR_PUBLICATION_UNCERTAIN', 'receipt': None}
            finally:
                if reader is not None:
                    reader.close()

    def _run(self):
        with self._mutex:
            self._active = True
        try:
            for request in sorted(self.config['requests'], key=lambda r:(r['not_before_ms'], r['request_id'])):
                while self.clock() < request['not_before_ms'] and not self._stop.is_set():
                    self._stop.wait(0.05)
                if self._stop.is_set():
                    break
                try:
                    outcome = self.capture(request)
                except Exception:
                    outcome = {'state': 'HOLD', 'reason': 'ORIGINAL_SOURCE_STATE_UNAVAILABLE', 'receipt': None}
                with self._mutex:
                    self._outcomes[request['request_id']] = outcome
        finally:
            with self._mutex:
                self._active = False


def poll_depth_capture(service):
    """No constructor/import/GET effect; only explicit runtime lifecycle calls."""
    configured = getattr(service.cfg, 'depth_capture', None)
    worker = getattr(service, '_depth_capture_worker', None)
    if worker is not None:
        if configured is None or getattr(service, 'stop_requested', False):
            worker._stop.set()  # Nonblocking; capacity stays until actual close.
        same = canonical_json(configured) == worker.policy.config_json
        if same or not worker.wait_idle(0) or configured is None:
            service.depth_capture_state = worker.snapshot()
            return service.depth_capture_state
        # Only an explicitly changed configuration may submit a new original.
        # Reused IDs still arbitrate against their immutable task and capture.
    if configured is None:
        return {'state': 'OFF', 'authority_effect': 'NONE'}
    try:
        policy = NativeDepthSourcePolicy.parse(configured)
        worker = NativeDepthWorker(service, policy)
    except (TypeError, ValueError, OSError):
        service.depth_capture_state = {'state': 'REFUSED', 'reason': 'NATIVE_DEPTH_CONFIG_INVALID', 'authority_effect': 'NONE'}
        return service.depth_capture_state
    service._depth_capture_worker = worker
    worker.start()
    service.depth_capture_state = worker.snapshot()
    return service.depth_capture_state


def stop_depth_capture(service):
    worker = getattr(service, '_depth_capture_worker', None)
    if worker is not None:
        joined = worker.close()
        service.depth_capture_state = worker.snapshot()
        return joined
    return True
