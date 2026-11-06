"""Real archive -> typed Parquet -> independent original-source readback.

Executed explicitly by the pinned Parquet source CI job; missing dependencies fail.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_native_bar_windows import original, capture
from vati.core.canonical import canonical_hash
from vati.research.bar_partitions import NativeBarPartitionService, PartitionPublicationUnknown
from vati.market_data.native_windows import NativeBarWindowReader
from vati_forecast_worker.source_partitions import (
    SourcePartitionError, projected_rows, encode_native_bar_partition,
    verify_native_bar_partition, arrow_schema,
)


from test_forecast_source_partitions import source, rehash

@pytest.fixture
def arrow():
    import pyarrow
    return pyarrow


def test_actual_parquet_readback_is_typed_exact_and_deterministic(source, arrow):
    window = source[3]
    data = encode_native_bar_partition(window)
    assert data.startswith(b'PAR1') and data.endswith(b'PAR1')
    assert data == encode_native_bar_partition(window)
    result = verify_native_bar_partition(data, window)
    assert result['sha256'] == hashlib.sha256(data).hexdigest() and result['row_count'] == 3
    assert result['qualified_for_research'] is False and result['authority_effect'] == 'NONE'
    assert result['coverage_state'] == 'UNQUALIFIED_SCHEDULE_COVERAGE'
    from pyarrow import parquet as pq
    table = pq.read_table(arrow.BufferReader(data))
    assert table.schema.remove_metadata() == arrow_schema()
    assert table.to_pylist() == projected_rows(window)


@pytest.mark.parametrize('damage', ['rows', 'schema', 'compression', 'metadata', 'bytes'])
def test_actual_parquet_tampering_refuses_even_when_file_hash_is_recomputed(source, arrow, damage):
    from pyarrow import parquet as pq
    window = source[3]; data = encode_native_bar_partition(window)
    table = pq.read_table(arrow.BufferReader(data))
    if damage == 'rows':
        rows = table.to_pylist(); rows[0]['close'] = '999'
        table = arrow.Table.from_pylist(rows, schema=table.schema)
    if damage == 'schema': table = table.drop(['scope_sha256'])
    if damage == 'metadata': table = table.replace_schema_metadata({})
    if damage == 'bytes': data = b'not parquet'
    else:
        out = arrow.BufferOutputStream()
        pq.write_table(table, out, compression='snappy' if damage == 'compression' else 'NONE', use_dictionary=False)
        data = out.getvalue().to_pybytes()
    with pytest.raises(SourcePartitionError): verify_native_bar_partition(data, window)


def test_source_owner_publication_replay_and_cold_reopen_preserve_original(source, tmp_path, arrow):
    book, contract, sample, window = source
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
    result = service.publish(window, expected_scope=contract.native_scope)
    paths = sorted(p.name for p in service.root.iterdir())
    assert result['original_source_resolved'] and result['dataset_manifest_admitted'] is False
    assert result['research_use_state'] == 'UNKNOWN_REFUSED'
    assert service.publish(window, expected_scope=contract.native_scope) == result
    assert sorted(p.name for p in service.root.iterdir()) == paths
    cold = NativeBarPartitionService(NativeBarWindowReader(book), service.root)
    assert cold.get(window['window_sha256'], expected_scope=contract.native_scope) == result
    # Independent interpreter, original bytes and the same actual dependency.
    code = '''
import json,sys
from vati.market_data.native_archive import NativeMarketArchive
from vati.market_data.native_windows import NativeBarWindowReader
from vati.research.bar_partitions import NativeBarPartitionService
reader=NativeBarWindowReader(NativeMarketArchive(sys.argv[1],clock=lambda:400000))
value=NativeBarPartitionService(reader,sys.argv[2]).get(sys.argv[3],expected_scope=json.loads(sys.argv[4]))
print(json.dumps(value))
'''
    child = subprocess.run([sys.executable, '-c', code, str(book.root), str(service.root), window['window_sha256'],
        json.dumps(contract.native_scope)], env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout) == result


def test_future_equal_clock_corrections_do_not_rewrite_published_partition(source, tmp_path, arrow):
    book, contract, sample, window = source
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
    before = service.publish(window, expected_scope=contract.native_scope)
    path = service.root/(window['window_sha256']+'.parquet'); original_bytes = path.read_bytes()
    second = book.record('later-correction', contract, replace(sample, bars=(replace(sample.bars[0], close=sample.bars[0].low),)))
    later = capture(book, contract, second)
    changed = service.publish(later, expected_scope=contract.native_scope)
    assert before['publication_ref'] != changed['publication_ref']
    assert path.read_bytes() == original_bytes
    assert service.get(window['window_sha256'], expected_scope=contract.native_scope) == before


def test_claimed_window_cannot_replace_actual_archive_resolution(source, tmp_path, arrow):
    book, contract, sample, window = source
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
    fake = deepcopy(window); fake['rows'][0]['bar']['close'] = fake['rows'][0]['bar']['low']; rehash(fake)
    with pytest.raises(ValueError, match='ORIGINAL_READBACK_CONFLICT'):
        service.publish(fake, expected_scope=contract.native_scope)
    assert not list(service.root.glob('*.parquet'))


def test_lost_manifest_ack_reconciles_original_without_new_partition(source, tmp_path, arrow, monkeypatch):
    from vati.market_data.feeds.lake import BarLake
    book, contract, sample, window = source
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
    write = BarLake._atomic_write
    def lost(path, data):
        write(path, data)
        if path.suffix == '.json': raise OSError('injected lost manifest ACK')
    with monkeypatch.context() as patch:
        patch.setattr(BarLake, '_atomic_write', lost)
        with pytest.raises(PartitionPublicationUnknown): service.publish(window, expected_scope=contract.native_scope)
    result = service.get(window['window_sha256'], expected_scope=contract.native_scope)
    assert result and result == service.publish(window, expected_scope=contract.native_scope)
    assert len(list(service.root.glob('*.parquet'))) == 1


def test_missing_manifest_recovers_only_exact_original_orphan(source, tmp_path, arrow):
    book, contract, sample, window = source
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
    result = service.publish(window, expected_scope=contract.native_scope)
    service._file(window['window_sha256']+'.json').unlink()
    assert service.get(window['window_sha256'], expected_scope=contract.native_scope) is None
    assert service.publish(window, expected_scope=contract.native_scope) == result
    service._file(window['window_sha256']+'.json').unlink()
    service._file(window['window_sha256']+'.parquet').write_bytes(b'conflicting orphan')
    with pytest.raises(SourcePartitionError, match='ORPHAN_CONFLICT'):
        service.publish(window, expected_scope=contract.native_scope)


@pytest.mark.parametrize('damage', ['source', 'partition', 'manifest', 'symlink'])
def test_readback_never_turns_corruption_or_links_into_success(source, tmp_path, arrow, damage):
    book, contract, sample, window = source
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
    service.publish(window, expected_scope=contract.native_scope)
    if damage == 'source':
        path = next(p for p in book._partition(contract.native_scope, 'M1').glob('*.json') if p.name != 'head.json')
        path.write_bytes(path.read_bytes()+b' ')
    elif damage == 'partition': service._file(window['window_sha256']+'.parquet').write_bytes(b'corrupt')
    elif damage == 'manifest': service._file(window['window_sha256']+'.json').write_bytes(b'{}')
    else:
        path = service._file(window['window_sha256']+'.parquet'); target = tmp_path/'elsewhere'
        path.rename(target); path.symlink_to(target)
    with pytest.raises(ValueError): service.get(window['window_sha256'], expected_scope=contract.native_scope)


def test_concurrent_real_writers_publish_one_original(source, tmp_path, arrow):
    from concurrent.futures import ThreadPoolExecutor
    book, contract, sample, window = source
    def publish():
        service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
        return service.publish(window, expected_scope=contract.native_scope)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:publish(), range(2)))
    assert results[0] == results[1] and len(list((tmp_path/'derived').glob('*.parquet'))) == 1


def test_actual_research_cli_resolves_source_and_reports_unknown_rights(source, tmp_path, arrow):
    book, contract, sample, window = source
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps({'operation':'native_bar_source_partition',
        'window':window, 'expected_scope':contract.native_scope}))
    child = subprocess.run([sys.executable, '-m', 'vati', 'research', '--spec', str(spec),
        '--native-archive', str(book.root), '--source-partitions', str(tmp_path/'derived')],
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result['partition']['original_source_resolved'] is True
    assert result['partition']['research_use_state'] == 'UNKNOWN_REFUSED'
    assert result['partition']['qualified_for_research'] is False


def test_wrong_native_account_cannot_read_matching_ticker_partition(source, tmp_path, arrow):
    book, contract, sample, window = source
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived')
    service.publish(window, expected_scope=contract.native_scope)
    with pytest.raises(ValueError, match='SCOPE_CONFLICT'):
        service.get(window['window_sha256'], expected_scope=dict(contract.native_scope, native_account_id=999))


@pytest.mark.parametrize('limit', ['bytes', 'count'])
def test_storage_capacity_refuses_before_new_publication_and_preserves_original(source, tmp_path, arrow, limit):
    from vati.research.bar_partitions import PartitionBudget
    book, contract, sample, window = source
    budget = PartitionBudget(stored_bytes=1) if limit == 'bytes' else PartitionBudget(publications=1)
    service = NativeBarPartitionService(NativeBarWindowReader(book), tmp_path/'derived', budget=budget)
    if limit == 'count':
        original = service.publish(window, expected_scope=contract.native_scope)
        receipt = book.record('another-source-window', contract, replace(sample, bars=(sample.bars[0],)))
        other = capture(book, contract, receipt)
    else: other = window
    before = {p.name:p.read_bytes() for p in service.root.iterdir()}
    with pytest.raises(SourcePartitionError, match='STORAGE_CAPACITY'):
        service.publish(other, expected_scope=contract.native_scope)
    after = {p.name:p.read_bytes() for p in service.root.iterdir() if not p.name.endswith('.lock')}
    assert after == {k:v for k,v in before.items() if not k.endswith('.lock')}
    if limit == 'count': assert service.get(window['window_sha256'], expected_scope=contract.native_scope) == original
