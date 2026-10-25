"""Revisioned, scoped raw observations. Nothing here qualifies a live source.

An atomic immutable record rename is the durable commit point. The head is a
derived index: a lost index update can be recovered from the original record,
while a head ahead of or conflicting with the captured chain refuses reads.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time
from decimal import Decimal, localcontext

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.file_lock import exclusive_state_lock
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.feed import MAX_TIMESTAMP, PERIOD, TrendbarObservation, native_integer
from vati.execution.ctrader.transport import DEMO_HOST, LIVE_HOST
from vati.market_data.feeds.lake import BarLake

MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10000  # Capacity refusal; no implicit retention or deletion policy.
RECORD_FILE = re.compile(r'([0-9]{20})-([0-9a-f]{64})\.json')
REQUEST_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')


class NativeArchiveError(ValueError):
    pass


def _scope(scope):
    if not isinstance(scope, dict) or set(scope) != {
            'provider', 'environment', 'transport_host', 'native_account_id', 'native_symbol_id'}:
        raise ValueError('native market scope format invalid')
    expected = {DEMO_HOST: 'DEMO', LIVE_HOST: 'LIVE'}.get(scope['transport_host'])
    if scope['provider'] != 'CTRADER' or expected is None or scope['environment'] != expected:
        raise ValueError('native market environment unavailable')
    native_integer(scope['native_account_id'], minimum=1)
    native_integer(scope['native_symbol_id'], minimum=1)


def _capture(contract_body, observation):
    contract = NativeSymbolContract.from_body(contract_body)
    scope = contract.native_scope
    if not isinstance(observation, dict):
        raise ValueError('native bar observation unavailable')
    expected = {'schema', 'native_account_id', 'native_symbol_id', 'symbol', 'timeframe',
                'from_ms', 'to_ms', 'received_at_ms', 'transport_host', 'contract_revision',
                'has_more', 'excluded_open_bars', 'volume_basis', 'field_default_profile',
                'defaulted_delta_fields', 'interval_basis', 'spread_state', 'spread',
                'authority_effect', 'provider_qualified', 'bars', 'observation_sha256'}
    if set(observation) != expected:
        raise ValueError('native bar observation format invalid')
    body = {k: v for k, v in observation.items() if k != 'observation_sha256'}
    fixed = {'schema': 'vati.ctrader-trendbars/1', 'volume_basis': 'NATIVE_TICK_COUNT',
             'field_default_profile': 'COORDINATES_EXPLICIT_OPTIONAL_DELTAS_PROTO2_ZERO',
             'interval_basis': 'FIXED_DURATION_FROM_NATIVE_OPEN_MINUTE_CALENDAR_UNQUALIFIED',
             'spread_state': 'UNAVAILABLE_NATIVE_TRENDBAR_HAS_NO_SPREAD',
             'spread': None, 'authority_effect': 'NONE'}
    if (any(body[k] != value for k, value in fixed.items()) or body['provider_qualified'] is not False
            or canonical_hash(body) != observation['observation_sha256']):
        raise ValueError('native bar observation hash or authority invalid')
    for key in ('native_account_id', 'native_symbol_id'):
        if native_integer(body[key], minimum=1) != scope[key]:
            raise ValueError('native bar observation product/account mismatch')
    if body['transport_host'] != scope['transport_host'] or body['contract_revision'] != contract.revision:
        raise ValueError('native bar observation contract mismatch')
    name = contract.metadata['light']['symbolName']
    if (not isinstance(body['symbol'], str) or body['symbol'] != body['symbol'].upper()
            or body['symbol'].replace('/', '') != name.upper().replace('/', '')):
        raise ValueError('native bar observation alias mismatch')
    timeframe = body['timeframe']
    if not isinstance(timeframe, str) or timeframe not in PERIOD:
        raise ValueError('native bar observation timeframe invalid')
    step = PERIOD[timeframe][1]
    lo = native_integer(body['from_ms'], maximum=MAX_TIMESTAMP)
    hi = native_integer(body['to_ms'], minimum=lo, maximum=MAX_TIMESTAMP)
    received = native_integer(body['received_at_ms'], minimum=contract.received_at_ms, maximum=253402300799000)
    if body['has_more'] is not None and type(body['has_more']) is not bool:
        raise ValueError('native bar pagination state invalid')
    excluded = native_integer(body['excluded_open_bars'], maximum=2001)
    rows = body['bars']
    if not isinstance(rows, list) or len(rows) + excluded > 2001:
        raise ValueError('native bar observation resource bound')
    seen, previous = set(), None
    with localcontext() as context:
        context.prec = 80
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                    'start_ms', 'end_ms', 'open', 'high', 'low', 'close', 'volume', 'ticks'}:
                raise ValueError('native bar format invalid')
            start = native_integer(row['start_ms'], minimum=lo, maximum=hi)
            end = native_integer(row['end_ms'], minimum=start, maximum=min(hi, received))
            if start % 60000 or end-start != step or (previous is not None and start <= previous):
                raise ValueError('native bar interval, order or availability invalid')
            previous = start
            seen.add(start)
            values = []
            for key in ('open', 'high', 'low', 'close', 'volume'):
                value = row[key]
                if not isinstance(value, str) or not 1 <= len(value) <= 128:
                    raise ValueError('native bar number representation invalid')
                parsed = Decimal(value)
                if not parsed.is_finite():
                    raise ValueError('native bar number nonfinite')
                values.append(parsed)
            opening, high, low, close, volume = values
            low_units = low*100000
            native_integer(int(low_units), minimum=-(2**63))
            if low_units != int(low_units) or high < max(opening, close) or low > min(opening, close):
                raise ValueError('native bar price coordinates invalid')
            for price in (opening, close, high):
                delta = (price-low)*100000
                if delta != int(delta):
                    raise ValueError('native bar price precision invalid')
                native_integer(int(delta), maximum=2**64-1)
            ticks = native_integer(row['ticks'])
            if volume != ticks:
                raise ValueError('native bar tick volume invalid')
    defaults = body['defaulted_delta_fields']
    if not isinstance(defaults, list) or len(defaults) > len(rows):
        raise ValueError('native bar default provenance invalid')
    previous = -1
    keys = ('deltaOpen', 'deltaClose', 'deltaHigh')
    for item in defaults:
        if not isinstance(item, dict) or set(item) != {'start_ms', 'fields'}:
            raise ValueError('native bar default provenance invalid')
        start = native_integer(item['start_ms'], minimum=0)
        fields = item['fields']
        if (start not in seen or start <= previous or not isinstance(fields, list) or not fields
                or fields != [key for key in keys if key in fields]):
            raise ValueError('native bar default provenance invalid')
        previous = start
        row = next(row for row in rows if row['start_ms'] == start)
        for field, value in zip(keys, ('open', 'close', 'high')):
            if field in fields and Decimal(row[value]) != Decimal(row['low']):
                raise ValueError('native bar default contradicts captured price')
    return contract, scope, timeframe


class NativeMarketArchive:
    observation_type = TrendbarObservation
    _validate_capture = staticmethod(_capture)

    @staticmethod
    def _validate_timeframe(timeframe):
        if not isinstance(timeframe, str) or timeframe not in PERIOD:
            raise ValueError('native market archive timeframe invalid')

    @staticmethod
    def _observation_available_at(observation):
        return observation['received_at_ms']

    def __init__(self, root, *, clock=None):
        if not Path(root).is_absolute():
            raise NativeArchiveError('native market archive requires an explicit absolute storage root')
        self.root = Path(root).resolve()
        self.clock = clock or (lambda: int(time.time()*1000))

    def _partition(self, scope, timeframe, *, create=False):
        _scope(scope)
        self._validate_timeframe(timeframe)
        key = canonical_hash({'scope': scope, 'timeframe': timeframe})
        part = self.root/key
        if self.root.resolve() != self.root or part.is_symlink() or not part.resolve().is_relative_to(self.root):
            raise ValueError('native market archive partition escapes root')
        if create:
            part.mkdir(parents=True, exist_ok=True)
        return part

    @staticmethod
    def _read(path):
        if path.is_symlink() or path.stat().st_size > MAX_RECORD_BYTES:
            raise ValueError('native market archive path or resource bound')
        blob = path.read_bytes()
        if len(blob) > MAX_RECORD_BYTES:
            raise ValueError('native market archive resource bound')
        body = json.loads(blob)
        if canonical_json(body).encode() != blob:
            raise ValueError('native market archive noncanonical record')
        return body, hashlib.sha256(blob).hexdigest()

    def _load(self, part, scope, timeframe):
        rows, previous, requests = [], None, set()
        paths = sorted(part.glob('*.json')) if part.exists() else []
        files = [p for p in paths if p.name != 'head.json']
        if len(files) > MAX_RECORDS:
            raise ValueError('native market archive capacity exceeded')
        for path in files:
            match = RECORD_FILE.fullmatch(path.name)
            if match is None:
                raise ValueError('native market archive unexpected record path')
            body, digest = self._read(path)
            revision = len(rows)+1
            if isinstance(body, dict):
                _scope(body.get('scope'))
            if (int(match[1]) != revision or match[2] != digest or not isinstance(body, dict)
                    or set(body) != {'schema', 'scope', 'timeframe', 'revision', 'previous_hash',
                                     'request_id', 'contract', 'observation', 'recorded_at_ms'}
                    or body['schema'] != 'vati.native-market-record/1'
                    or type(body['revision']) is not int or body['revision'] != revision
                    or body['scope'] != scope or body['timeframe'] != timeframe
                    or body['previous_hash'] != previous or not isinstance(body['request_id'], str)
                    or not REQUEST_ID.fullmatch(body['request_id']) or body['request_id'] in requests):
                raise ValueError('native market archive sequence, hash or scope invalid')
            _, captured_scope, captured_timeframe = self._validate_capture(body['contract'], body['observation'])
            if captured_scope != scope or captured_timeframe != timeframe:
                raise ValueError('native market archive captured scope mismatch')
            recorded = native_integer(body['recorded_at_ms'], minimum=self._observation_available_at(body['observation']), maximum=253402300799000)
            if rows and recorded < rows[-1][0]['recorded_at_ms']:
                raise ValueError('native market archive availability moved backwards')
            requests.add(body['request_id'])
            rows.append((body, digest))
            previous = digest
        head = part/'head.json'
        state = 'MISSING' if rows else 'EMPTY'
        if head.exists() or head.is_symlink():
            index, _ = self._read(head)
            if isinstance(index, dict):
                _scope(index.get('scope'))
            if (not isinstance(index, dict) or set(index) != {'schema', 'scope', 'timeframe', 'revision', 'record_hash'}
                    or index['schema'] != 'vati.native-market-head/1' or index['scope'] != scope
                    or index['timeframe'] != timeframe or type(index['revision']) is not int
                    or not 1 <= index['revision'] <= len(rows)
                    or rows[index['revision']-1][1] != index['record_hash']):
                raise ValueError('native market archive index conflicts with captured history')
            state = 'CONSISTENT' if index['revision'] == len(rows) else 'STALE'
        return rows, state

    @staticmethod
    def _receipt(body, digest, index_state):
        return {'record_ref': digest, 'revision': body['revision'], 'request_id': body['request_id'],
                'scope': body['scope'], 'timeframe': body['timeframe'],
                'contract_revision': body['contract']['metadata_revision'],
                'received_at_ms': body['observation']['received_at_ms'],
                'available_at_ms': body['recorded_at_ms'], 'index_state': index_state,
                'state': 'OBSERVED_UNQUALIFIED' if body['observation']['bars'] else 'EMPTY_UNQUALIFIED',
                'provider_qualified': False, 'authority_effect': 'NONE'}

    def _write_head(self, part, scope, timeframe, rows):
        body, digest = rows[-1]
        head = {'schema': 'vati.native-market-head/1', 'scope': scope, 'timeframe': timeframe,
                'revision': body['revision'], 'record_hash': digest}
        BarLake._atomic_write(part/'head.json', canonical_json(head).encode())

    def record(self, request_id, contract, observation):
        try:
            if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
                raise ValueError('native market request identity invalid')
            if not isinstance(contract, NativeSymbolContract) or not isinstance(observation, self.observation_type):
                raise ValueError('native market captured objects required')
            original_contract, original_observation = contract.body(), observation.body()
            _, scope, timeframe = self._validate_capture(original_contract, original_observation)
            part = self._partition(scope, timeframe, create=True)
            with exclusive_state_lock(part/'head.json'):
                rows, index_state = self._load(part, scope, timeframe)
                for old, digest in rows:
                    if old['request_id'] != request_id:
                        continue
                    if old['contract'] != original_contract or old['observation'] != original_observation:
                        raise ValueError('native market request identity conflicts with its original capture')
                    if index_state != 'CONSISTENT':
                        self._write_head(part, scope, timeframe, rows)
                    return self.lookup(scope, timeframe, request_id)
                if len(rows) >= MAX_RECORDS:
                    raise ValueError('native market archive capacity exhausted; explicit retention decision required')
                received = native_integer(self.clock(), minimum=self._observation_available_at(original_observation), maximum=253402300799000)
                if rows and received < rows[-1][0]['recorded_at_ms']:
                    raise ValueError('native market archive clock moved backwards')
                body = {'schema': 'vati.native-market-record/1', 'scope': scope, 'timeframe': timeframe,
                        'revision': len(rows)+1, 'previous_hash': rows[-1][1] if rows else None,
                        'request_id': request_id, 'contract': original_contract,
                        'observation': original_observation, 'recorded_at_ms': received}
                blob = canonical_json(body).encode()
                if len(blob) > MAX_RECORD_BYTES:
                    raise ValueError('native market archive record resource bound')
                digest = hashlib.sha256(blob).hexdigest()
                path = part/f'{body["revision"]:020d}-{digest}.json'
                BarLake._atomic_write(path, blob)
                rows.append((body, digest))
                self._write_head(part, scope, timeframe, rows)
                # Independently parse/hash the durable original before reporting it.
                return self.lookup(scope, timeframe, request_id)
        except (KeyError, TypeError, ValueError, ArithmeticError, OSError) as exc:
            raise NativeArchiveError('native market capture unavailable: '+str(exc)) from exc

    def lookup(self, scope, timeframe, request_id):
        try:
            if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
                raise ValueError('native market request identity invalid')
            part = self._partition(scope, timeframe)
            if not part.exists():
                return None
            with exclusive_state_lock(part/'head.json'):
                rows, state = self._load(part, scope, timeframe)
            for body, digest in rows:
                if body['request_id'] == request_id:
                    return self._receipt(body, digest, state)
            return None
        except (KeyError, TypeError, ValueError, ArithmeticError, OSError) as exc:
            raise NativeArchiveError('native market archive read unavailable: '+str(exc)) from exc

    def reconcile(self, scope, timeframe, request_id):
        """Repair only the derived index; independently reread the durable original."""
        try:
            if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
                raise ValueError('native market request identity invalid')
            part = self._partition(scope, timeframe)
            if not part.exists():
                return None
            with exclusive_state_lock(part/'head.json'):
                rows, state = self._load(part, scope, timeframe)
                if not any(body['request_id'] == request_id for body, _ in rows):
                    return None
                if state != 'CONSISTENT':
                    self._write_head(part, scope, timeframe, rows)
                original = self.lookup(scope, timeframe, request_id)
                if original is None or original['index_state'] != 'CONSISTENT':
                    raise ValueError('native market archive index repair not confirmed')
                return original
        except (KeyError, TypeError, ValueError, ArithmeticError, OSError) as exc:
            raise NativeArchiveError('native market archive recovery unavailable: '+str(exc)) from exc

    def snapshot(self, scope, timeframe, *, revision=None, as_of_ms=None):
        try:
            if revision is not None and as_of_ms is not None:
                raise ValueError('select one native market history boundary')
            if revision is not None:
                native_integer(revision, minimum=1)
            if as_of_ms is not None:
                native_integer(as_of_ms, maximum=native_integer(self.clock(), maximum=253402300799000))
            part = self._partition(scope, timeframe)
            if not part.exists():
                return None
            with exclusive_state_lock(part/'head.json'):
                rows, state = self._load(part, scope, timeframe)
            selected = [(body, digest) for body, digest in rows
                        if (revision is None or body['revision'] == revision)
                        and (as_of_ms is None or body['recorded_at_ms'] <= as_of_ms)]
            if not selected:
                return None  # No captured observation; never an invented zero series.
            body, digest = selected[-1]
            return {'receipt': self._receipt(body, digest, state), 'contract': body['contract'],
                    'observation': body['observation']}
        except (KeyError, TypeError, ValueError, ArithmeticError, OSError) as exc:
            raise NativeArchiveError('native market snapshot unavailable: '+str(exc)) from exc
