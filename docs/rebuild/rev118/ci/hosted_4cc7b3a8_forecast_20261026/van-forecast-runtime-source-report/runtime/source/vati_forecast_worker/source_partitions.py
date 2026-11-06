"""Bounded derived source partitions, without data-use or dataset admission.

The native archive owner must independently resolve the supplied window. These
functions preserve its facts in Parquet; a client-created window/hash cannot
establish provenance, a calendar, completeness, consent or a licence.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

MAX_BYTES = 64 * 1024**2
MAX_ROWS = 100000
FORMAT = 'van.native-bar-source-partition/1'
TEXT = ('row_id', 'scope_sha256', 'source_record_ref', 'contract_revision',
        'open', 'high', 'low', 'close', 'volume', 'volume_basis', 'spread_state')
INTEGER = ('source_revision', 'received_at_ms', 'available_at_ms', 'start_ms', 'end_ms', 'ticks')


class SourcePartitionError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**63-1:
        raise SourcePartitionError('PARTITION_INTEGER_INVALID')
    return value


def _hash(value):
    if not isinstance(value, str) or re.fullmatch('[a-f0-9]{64}', value) is None:
        raise SourcePartitionError('PARTITION_REFERENCE_INVALID')
    return value


def projected_rows(window):
    """Validate the source envelope, retaining unknown native facts as unknown."""
    try:
        if (not isinstance(window, dict) or window.get('schema') != 'vati.native-bar-window/1'
                or window.get('authority_effect') != 'NONE' or window.get('provider_qualified') is not False
                or window.get('qualified_for_research') is not False
                or window.get('availability_basis') != 'LOCAL_CAPTURE_CLOCK_NOT_NATIVE_CLOCK_QUALIFICATION'
                or not isinstance(window.get('rows'), list) or not 1 <= len(window['rows']) <= MAX_ROWS
                or len(canonical(window)) > MAX_BYTES):
            raise SourcePartitionError('PARTITION_SOURCE_FORMAT_OR_CAPACITY')
        body = {k: v for k, v in window.items() if k != 'window_sha256'}
        if digest(body) != _hash(window['window_sha256']):
            raise SourcePartitionError('PARTITION_WINDOW_HASH_CONFLICT')
        scope = window['scope']
        if (not isinstance(scope, dict) or set(scope) != {'provider', 'environment', 'transport_host',
                'native_account_id', 'native_symbol_id'} or scope['provider'] != 'CTRADER'
                or {'demo.ctraderapi.com': 'DEMO', 'live.ctraderapi.com': 'LIVE'}.get(scope['transport_host']) != scope['environment']):
            raise SourcePartitionError('PARTITION_NATIVE_SCOPE_CONFLICT')
        for field in ('native_account_id', 'native_symbol_id'):
            _integer(scope[field], 1)
        cutoff = _integer(window['as_of_ms'])
        lo, hi = _integer(window['from_ms']), _integer(window['to_ms'])
        if lo >= hi or hi > cutoff or _integer(window['max_input_available_ms']) > cutoff:
            raise SourcePartitionError('PARTITION_WINDOW_CLOCK_CONFLICT')
        step = {'M1':60000, 'M5':300000, 'M15':900000, 'M30':1800000,
                'H1':3600000, 'H4':14400000, 'D1':86400000}[window['timeframe']]
        sources = {}
        for source in window['source_records']:
            receipt = source['receipt']; ref = _hash(receipt['record_ref'])
            if (ref in sources or source['spread'] is not None or source['volume_basis'] != 'NATIVE_TICK_COUNT'
                    or source['spread_state'] != 'UNAVAILABLE_NATIVE_TRENDBAR_HAS_NO_SPREAD'
                    or receipt['scope'] != scope or receipt['timeframe'] != window['timeframe']):
                raise SourcePartitionError('PARTITION_SOURCE_FACT_CONFLICT')
            sources[ref] = source
        if not sources or max(_integer(s['receipt']['available_at_ms']) for s in sources.values()) != window['max_input_available_ms']:
            raise SourcePartitionError('PARTITION_AVAILABILITY_CONFLICT')
        rows = []; previous_end = None
        for item in window['rows']:
            bar = item['bar']; start = _integer(bar['start_ms']); end = _integer(bar['end_ms'])
            if (end-start != step or not lo <= start < end <= hi
                    or (previous_end is not None and start < previous_end)):
                raise SourcePartitionError('PARTITION_INTERVAL_CONFLICT')
            previous_end = end
            source = sources[_hash(item['source_record_ref'])]; receipt = source['receipt']
            if (_integer(item['source_revision'], 1) != receipt['revision']
                    or _integer(item['available_at_ms']) != receipt['available_at_ms']
                    or _integer(item['received_at_ms']) != receipt['received_at_ms']
                    or not end <= _integer(item['received_at_ms']) <= item['available_at_ms'] <= cutoff
                    or _hash(item['contract_revision']) != source['contract']['metadata_revision']):
                raise SourcePartitionError('PARTITION_ROW_SOURCE_OR_CLOCK_CONFLICT')
            values = {}
            for name in ('open', 'high', 'low', 'close', 'volume'):
                value = bar[name]
                if not isinstance(value, str) or not 1 <= len(value) <= 128:
                    raise SourcePartitionError('PARTITION_EXACT_DECIMAL_REQUIRED')
                values[name] = Decimal(value)
                if not values[name].is_finite():
                    raise SourcePartitionError('PARTITION_NONFINITE_PRICE')
            if (values['low'] > min(values['open'], values['close'])
                    or values['high'] < max(values['open'], values['close'])
                    or values['volume'] != _integer(bar['ticks']) or values['volume'] < 0):
                raise SourcePartitionError('PARTITION_MARKET_FACT_CONFLICT')
            identity = {'scope': scope, 'timeframe': window['timeframe'], 'start_ms': start, 'end_ms': end}
            rows.append({'row_id': digest(identity), 'scope_sha256': digest(scope),
                **{name: item[name] for name in ('source_record_ref', 'source_revision', 'contract_revision',
                    'received_at_ms', 'available_at_ms')}, **bar,
                'volume_basis': source['volume_basis'], 'spread': None, 'spread_state': source['spread_state']})
        return rows
    except (KeyError, TypeError, InvalidOperation, OverflowError, RecursionError) as error:
        raise SourcePartitionError('PARTITION_SOURCE_INVALID') from error


def arrow_schema():
    # Imported only by slow research materialization/consumption, never T0.
    import pyarrow as pa
    return pa.schema([*(pa.field(name, pa.string(), nullable=False) for name in TEXT),
        *(pa.field(name, pa.int64(), nullable=False) for name in INTEGER),
        pa.field('spread', pa.string(), nullable=True)])


def _metadata(window, rows):
    return {b'van.source_partition': canonical({'format': FORMAT, 'window_sha256': window['window_sha256'],
        'row_identity_digest': digest([row['row_id'] for row in rows]),
        'row_count': len(rows), 'qualified_for_research': False, 'authority_effect': 'NONE'})}


def encode_native_bar_partition(window):
    rows = projected_rows(window)
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.Table.from_pylist(rows, schema=arrow_schema()).replace_schema_metadata(_metadata(window, rows))
    output = pa.BufferOutputStream()
    pq.write_table(table, output, compression='NONE', use_dictionary=False, row_group_size=1024,
                   version='2.6', write_statistics=True)
    data = output.getvalue().to_pybytes()
    if len(data) > MAX_BYTES:
        raise SourcePartitionError('PARTITION_ARTIFACT_BYTE_LIMIT')
    verify_native_bar_partition(data, window)
    return data


def verify_native_bar_partition(data, window):
    """Inspect bounded metadata before decode, then compare all typed source rows.

    This is byte/content verification only. The caller must resolve the original
    archive independently; no ready DatasetManifest is created by this reader.
    """
    rows = projected_rows(window)
    if type(data) is not bytes or not 12 <= len(data) <= MAX_BYTES:
        raise SourcePartitionError('PARTITION_ARTIFACT_BYTE_LIMIT')
    import pyarrow as pa
    import pyarrow.parquet as pq
    try:
        reader = pq.ParquetFile(pa.BufferReader(data), thrift_string_size_limit=1024*1024,
                                thrift_container_size_limit=100000, arrow_extensions_enabled=False)
        metadata = reader.metadata
        if (metadata.num_rows != len(rows) or not 1 <= metadata.num_row_groups <= MAX_ROWS
                or not reader.schema_arrow.remove_metadata().equals(arrow_schema())
                or reader.schema_arrow.metadata != _metadata(window, rows)):
            raise SourcePartitionError('PARTITION_SCHEMA_OR_IDENTITY_CONFLICT')
        total = 0
        for group_index in range(metadata.num_row_groups):
            group = metadata.row_group(group_index)
            if not 1 <= group.num_rows <= 1024:
                raise SourcePartitionError('PARTITION_ROW_GROUP_LIMIT')
            for column_index in range(group.num_columns):
                column = group.column(column_index)
                total += column.total_uncompressed_size
                if column.compression != 'UNCOMPRESSED' or not 0 <= total <= MAX_BYTES:
                    raise SourcePartitionError('PARTITION_COMPRESSION_OR_DECODE_LIMIT')
        table = reader.read(use_threads=False)
        if table.to_pylist() != rows:
            raise SourcePartitionError('PARTITION_SOURCE_ROWS_CONFLICT')
    except (pa.ArrowException, OSError) as error:
        raise SourcePartitionError('PARTITION_PARQUET_INVALID') from error
    return {'format': FORMAT, 'window_sha256': window['window_sha256'],
        'row_identity_digest': digest([row['row_id'] for row in rows]), 'row_count': len(rows),
        'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data),
        'media_type': 'application/vnd.apache.parquet', 'qualified_for_research': False,
        'coverage_state': window['coverage_state'], 'authority_effect': 'NONE'}
