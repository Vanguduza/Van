"""Real archive -> typed Parquet -> independent original-source readback.

Parquet execution uses the separate pinned worker dependency suite. The public
source suite executes these lightweight boundary cases without importing Arrow.
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


@pytest.fixture
def source(tmp_path):
    book, contract, sample, receipt = original(tmp_path)
    window = capture(book, contract, receipt)
    return book, contract, sample, window


def rehash(window):
    window['window_sha256'] = canonical_hash({k:v for k,v in window.items() if k != 'window_sha256'})
    return window


def test_projection_preserves_exact_prices_clocks_scope_and_unknowns(source):
    book, contract, sample, window = source
    rows = projected_rows(window)
    assert len(rows) == 3 and len({r['row_id'] for r in rows}) == 3
    assert rows[0]['open'] == str(sample.bars[0].open)
    assert rows[0]['available_at_ms'] == 400000
    assert rows[0]['spread'] is None and rows[0]['volume_basis'] == 'NATIVE_TICK_COUNT'
    assert all(r['scope_sha256'] == canonical_hash(contract.native_scope) for r in rows)


@pytest.mark.parametrize('field,value', [('qualified_for_research', True), ('provider_qualified', True),
    ('authority_effect', 'ORDER'), ('availability_basis', 'OBSERVED_PROVIDER_QUALIFIED')])
def test_self_qualification_is_refused_even_with_recomputed_hash(source, field, value):
    window = deepcopy(source[3]); window[field] = value
    with pytest.raises(SourcePartitionError): projected_rows(rehash(window))


@pytest.mark.parametrize('damage', ['future', 'overlap', 'price', 'volume', 'revision', 'contract', 'empty', 'hash'])
def test_bad_rows_do_not_materialize_as_missing_or_zero(source, damage):
    window = deepcopy(source[3]); row = window['rows'][0]
    if damage == 'future': row['available_at_ms'] = 400001
    if damage == 'overlap': window['rows'].append(deepcopy(row))
    if damage == 'price': row['bar']['open'] = 'NaN'
    if damage == 'volume': row['bar']['volume'] = '0.5'
    if damage == 'revision': row['source_revision'] = 999
    if damage == 'contract': row['contract_revision'] = 'a' * 64
    if damage == 'empty': window['rows'] = []
    if damage == 'hash': window['window_sha256'] = 'a' * 64
    else: rehash(window)
    with pytest.raises(SourcePartitionError): projected_rows(window)


def test_research_workflow_requires_actual_configured_source_owner(source):
    from vati.research.workflow import TradingResearchWorkflow
    with pytest.raises(SourcePartitionError, match='SOURCE_OWNER_UNAVAILABLE'):
        TradingResearchWorkflow().run_spec({'operation':'native_bar_source_partition',
            'window':source[3], 'expected_scope':source[1].native_scope})


@pytest.mark.parametrize('operation', ['coverage', 'native_bar_source_partition'])
def test_research_cli_does_not_create_missing_archive_or_apply_source_flags_to_other_operations(tmp_path, operation):
    from argparse import Namespace
    from vati.__main__ import cmd_research
    spec = tmp_path/'spec.json'; spec.write_text(json.dumps({'operation':operation}))
    with pytest.raises(SourcePartitionError, match='EXPLICIT_EXISTING_SOURCE'):
        cmd_research(Namespace(spec=str(spec), ledger=None, native_archive=str(tmp_path/'absent'),
                               source_partitions=str(tmp_path/'derived')))
    assert not (tmp_path/'absent').exists() and not (tmp_path/'derived').exists()


@pytest.mark.parametrize('operation', ['coverage', 'invalid_operation'])
def test_research_cli_closes_real_sqlite_connection_on_success_and_failure(tmp_path, monkeypatch, operation):
    import sqlite3
    from argparse import Namespace
    from vati.__main__ import cmd_research
    from vati.core.ledger import Ledger
    from vati.core import ledger_pg
    ledger = Ledger(tmp_path/'actual.sqlite'); monkeypatch.setattr(ledger_pg, 'open_ledger', lambda _:ledger)
    spec = tmp_path/'spec.json'; spec.write_text(json.dumps({'operation':operation}))
    if operation == 'coverage': assert cmd_research(Namespace(spec=str(spec), ledger='configured')) == 0
    else:
        with pytest.raises(ValueError, match='unknown trading research'):
            cmd_research(Namespace(spec=str(spec), ledger='configured'))
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        ledger.count()


