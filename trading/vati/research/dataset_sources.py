"""Resolve actual native partition bytes and row clocks for a dataset candidate.

This inspector reuses the original source/partition owners. It grants no data
use, never reports READY, and cannot substitute source facts for the missing
universe/calendar/feature/target/consent/entitlement owners.
"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from fractions import Fraction
import hashlib

from vati.core.canonical import canonical_hash
from vati.research.bar_partitions import NativeBarPartitionService
from vati.research.dataset_manifest import DatasetManifestCandidate, DatasetContractError, _timestamp
from vati_forecast_worker.source_partitions import projected_rows


def _milliseconds(value):
    whole, remainder = divmod(value, 1000)
    return datetime(1970,1,1,tzinfo=timezone.utc) + timedelta(seconds=whole), Fraction(remainder,1000)


@dataclass(frozen=True)
class DatasetInspectionBudget:
    partitions: int = 256
    rows: int = 100000
    source_bytes: int = 64 * 1024**2

    def __post_init__(self):
        for name, maximum in (('partitions',4096), ('rows',1000000), ('source_bytes',512*1024**2)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise DatasetContractError('DATASET_INSPECTION_BUDGET_INVALID')


class NativeDatasetSourceInspector:
    def __init__(self, partitions, *, budget=None):
        if not isinstance(partitions, NativeBarPartitionService):
            raise DatasetContractError('DATASET_ORIGINAL_PARTITION_OWNER_REQUIRED')
        self.partitions = partitions
        self.budget = DatasetInspectionBudget() if budget is None else budget
        if not isinstance(self.budget, DatasetInspectionBudget):
            raise DatasetContractError('DATASET_INSPECTION_BUDGET_REQUIRED')

    def inspect(self, candidate, *, expected_scope):
        if not isinstance(candidate, DatasetManifestCandidate):
            raise DatasetContractError('DATASET_PARSED_CANDIDATE_REQUIRED')
        record = candidate.body(); cutoff = _timestamp(record['data_cutoff'])
        if (len(record['partitions']) > self.budget.partitions or record['row_count'] > self.budget.rows
                or sum(p['size_bytes'] for p in record['partitions']) > self.budget.source_bytes):
            raise DatasetContractError('DATASET_INSPECTION_CAPACITY_REFUSED')
        rows = []; ids = set(); windows = []; descriptors = []
        maximum = None; previous_end = None; total_bytes = 0
        # Retain the exact manifest partition order; never sort away a row/order
        # conflict or silently align arrays by position.
        for reference in record['partitions']:
            original = self.partitions.read(reference['artifact_id'], expected_scope=expected_scope)
            if original is None:
                raise DatasetContractError('DATASET_PARTITION_REFERENCE_UNAVAILABLE')
            descriptor = original.receipt(); window = original.window()
            total_bytes += len(original.parquet) + len(original.window_json)
            if total_bytes > self.budget.source_bytes:
                raise DatasetContractError('DATASET_INSPECTION_ACTUAL_BYTE_LIMIT')
            if (reference['sha256'] != hashlib.sha256(original.parquet).hexdigest()
                    or reference['size_bytes'] != len(original.parquet)
                    or reference['media_type'] != descriptor['media_type']):
                raise DatasetContractError('DATASET_ACTUAL_ARTIFACT_BYTES_CONFLICT')
            if _milliseconds(window['as_of_ms']) > cutoff:
                raise DatasetContractError('DATASET_SOURCE_VIEW_AFTER_CUTOFF')
            selected = projected_rows(window)
            for row in selected:
                if row['row_id'] in ids or (previous_end is not None and row['start_ms'] < previous_end):
                    raise DatasetContractError('DATASET_DUPLICATE_OR_UNORDERED_SOURCE_ROW')
                ids.add(row['row_id']); previous_end = row['end_ms']; rows.append(row['row_id'])
                if len(rows) > self.budget.rows:
                    raise DatasetContractError('DATASET_INSPECTION_ACTUAL_ROW_LIMIT')
            available = _milliseconds(window['max_input_available_ms'])
            maximum = available if maximum is None else max(maximum, available)
            windows.append({key:window[key] for key in ('window_sha256','coverage_state','timeframe',
                'through_revision','boundary_ref','as_of_ms','from_ms','to_ms','max_input_available_ms')})
            descriptors.append(descriptor)
        if record['row_count'] != len(rows) or record['row_identity_digest'] != canonical_hash(rows):
            raise DatasetContractError('DATASET_ACTUAL_ROWS_OR_IDENTITY_CONFLICT')
        if _timestamp(record['max_input_available_at']) != maximum:
            raise DatasetContractError('DATASET_ACTUAL_AVAILABILITY_CONFLICT')
        if record['availability_quality'] != 'OBSERVED':
            raise DatasetContractError('DATASET_NATIVE_CAPTURE_IS_OBSERVED_LOCAL_NOT_RECONSTRUCTED_OR_PROVIDER_CLOCK')
        if record['revision_policy'] != 'AS_OBSERVED':
            raise DatasetContractError('DATASET_CORRECTED_RESEARCH_REQUIRES_SEPARATE_OWNER')
        # A native window is an actual immutable source manifest. A compound
        # source manifest needs its own durable owner object; a computed list
        # hash alone cannot stand in for that still-unresolved object.
        single_source = len(windows) == 1
        if single_source and record['source_manifest_digest'] != windows[0]['window_sha256']:
            raise DatasetContractError('DATASET_ACTUAL_SOURCE_MANIFEST_CONFLICT')
        result = candidate.unresolved()
        result['required_resolutions'].pop('artifact_ids')
        result['required_resolutions'].pop('row_identity_digest')
        if single_source:
            result['required_resolutions'].pop('source_manifest_digest')
        result['resolved_source_facts'] = {'partitions': descriptors, 'row_count': len(rows),
            'row_identity_digest': canonical_hash(rows), 'native_scope': dict(expected_scope),
            'source_manifest_resolved': single_source,
            'availability_basis': 'LOCAL_CAPTURE_CLOCK_NOT_NATIVE_CLOCK_QUALIFICATION',
            'coverage_states': [window['coverage_state'] for window in windows],
            'source_windows': windows,
            'provider_qualified': False, 'qualified_for_research': False, 'authority_effect': 'NONE'}
        result['reason_codes'] = ['CURRENT_SCOPE_CONSENT_AND_SOURCE_USE_NOT_VERIFIED',
            'CANONICAL_DATASET_SCOPE_AND_DATA_ORIGIN_NOT_VERIFIED',
            'DATASET_CREATION_TIME_AND_CURRENT_POLICY_NOT_VERIFIED',
            'CALENDAR_UNIVERSE_FEATURE_AND_TARGET_REFERENCES_NOT_RESOLVED',
            'NATIVE_SOURCE_AND_SCHEDULE_COVERAGE_NOT_QUALIFIED']
        if not single_source:
            result['reason_codes'].append('COMPOUND_SOURCE_MANIFEST_NOT_RESOLVED')
        return result
