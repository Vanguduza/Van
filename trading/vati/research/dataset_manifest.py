"""Bounded DatasetManifest candidates, never data-use or factual admission.

The existing schema owner carries the canonical wire contract. This parser
enforces its local semantics; every opaque reference still needs independent
resolution by its actual owner before a consumer may use any dataset bytes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import re

from vati.contracts import load_schema

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REFERENCES = 4096
_STAMP = re.compile(r'(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
    r'(?:\.(?P<fraction>\d{1,256}))?(?P<offset>Z|[+-](?:0\d|1\d|2[0-3]):[0-5]\d)', re.ASCII)


class DatasetContractError(ValueError):
    """Typed candidate refusal; never an approval or permission verdict."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def _identity(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip()
            or any(ord(char) < 32 for char in value)):
        raise DatasetContractError('DATASET_IDENTITY_INVALID')
    return value


def _sha(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise DatasetContractError('DATASET_DIGEST_INVALID')


def _integer(value):
    if type(value) is not int or not 1 <= value <= 2**63-1:
        raise DatasetContractError('DATASET_COUNT_OR_SIZE_INVALID')


def _timestamp(value):
    match = _STAMP.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise DatasetContractError('DATASET_AWARE_TIMESTAMP_REQUIRED')
    if match['offset'] == '-00:00':
        raise DatasetContractError('DATASET_KNOWN_TIME_OFFSET_REQUIRED')
    try:
        # Compare arbitrary admitted subsecond precision exactly. Converting to
        # datetime microseconds or epoch floats would hide nanosecond leakage.
        stamp = datetime.fromisoformat(match['base'] + match['offset'].replace('Z', '+00:00'))
        digits = match['fraction'] or ''
        return stamp.astimezone(timezone.utc), Fraction(int(digits or '0'), 10**len(digits))
    except (ValueError, OverflowError) as error:
        raise DatasetContractError('DATASET_TIMESTAMP_INVALID') from error


def _unique(values):
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_REFERENCES:
        raise DatasetContractError('DATASET_REFERENCE_COUNT_INVALID')
    for value in values:
        _identity(value)
    if len(set(values)) != len(values):
        raise DatasetContractError('DATASET_DUPLICATE_REFERENCE')


def _validate(record):
    schema = load_schema('dataset_manifest')
    if not isinstance(record, dict) or set(record) != set(schema['required']):
        raise DatasetContractError('DATASET_EXACT_FIELDS_REQUIRED')
    if record['schema_version'] != 'van-ml/1.0':
        raise DatasetContractError('DATASET_SCHEMA_INCOMPATIBLE')
    if record['authority_effect'] != 'NONE':
        raise DatasetContractError('DATASET_HAS_NO_EFFECT_AUTHORITY')
    _identity(record['record_id'])
    scope = record['scope']
    if not isinstance(scope, dict) or set(scope) != set(schema['properties']['scope']['required']):
        raise DatasetContractError('DATASET_EXACT_SCOPE_REQUIRED')
    for value in scope.values():
        _identity(value)
    if scope['environment'] not in {'FIXTURE', 'RESEARCH', 'SHADOW', 'LIVE_ADVISORY'}:
        raise DatasetContractError('DATASET_ENVIRONMENT_INVALID')
    available, cutoff, created = (_timestamp(record[field]) for field in
        ('max_input_available_at', 'data_cutoff', 'created_at'))
    if not available <= cutoff <= created:
        raise DatasetContractError('DATASET_TEMPORAL_ORDER_INVALID')
    if record['availability_quality'] not in {'OBSERVED', 'PROVIDER_PUBLISHED', 'RECONSTRUCTED', 'MIXED'}:
        raise DatasetContractError('DATASET_AVAILABILITY_QUALITY_INVALID')
    if record['revision_policy'] not in {'AS_OBSERVED', 'CORRECTED_RESEARCH_ONLY'}:
        raise DatasetContractError('DATASET_REVISION_POLICY_INVALID')
    if record['revision_policy'] == 'CORRECTED_RESEARCH_ONLY' and scope['environment'] not in {'FIXTURE', 'RESEARCH'}:
        raise DatasetContractError('DATASET_CORRECTED_RESEARCH_NOT_ADVISORY_OR_SHADOW')
    for field in ('universe_digest', 'calendar_digest', 'source_manifest_digest', 'row_identity_digest', 'feature_definition_digest'):
        _sha(record[field])
    _integer(record['row_count'])
    _unique(record['target_spec_ids']); _unique(record['entitlement_refs']); _identity(record['consent_scope_ref'])
    partitions = record['partitions']
    if not isinstance(partitions, list) or not 1 <= len(partitions) <= MAX_REFERENCES:
        raise DatasetContractError('DATASET_PARTITION_COUNT_INVALID')
    identities = set(); total_bytes = 0
    for partition in partitions:
        if not isinstance(partition, dict) or set(partition) != {'artifact_id', 'sha256', 'media_type', 'size_bytes'}:
            raise DatasetContractError('DATASET_EXACT_PARTITION_FIELDS_REQUIRED')
        _identity(partition['artifact_id']); _identity(partition['media_type']); _sha(partition['sha256']); _integer(partition['size_bytes'])
        if partition['artifact_id'] in identities:
            raise DatasetContractError('DATASET_DUPLICATE_PARTITION_IDENTITY')
        identities.add(partition['artifact_id']); total_bytes += partition['size_bytes']
        if total_bytes > 2**63-1:
            raise DatasetContractError('DATASET_TOTAL_SIZE_OVERFLOW')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise DatasetContractError('DATASET_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _nonfinite(_):
    raise DatasetContractError('DATASET_NONFINITE_JSON_REFUSED')


@dataclass(frozen=True)
class DatasetManifestCandidate:
    """Immutable parsed record. Construction does not resolve or approve anything."""
    encoded: bytes

    def __post_init__(self):
        if type(self.encoded) is not bytes or not 1 <= len(self.encoded) <= MAX_MANIFEST_BYTES:
            raise DatasetContractError('DATASET_MANIFEST_BYTE_LIMIT')
        try:
            record = json.loads(self.encoded, object_pairs_hook=_pairs, parse_constant=_nonfinite)
            _validate(record)
            object.__setattr__(self, 'encoded', _json(record))
            if len(self.encoded) > MAX_MANIFEST_BYTES:
                raise DatasetContractError('DATASET_MANIFEST_BYTE_LIMIT')
        except DatasetContractError:
            raise
        except (UnicodeError, RecursionError, TypeError, ValueError) as error:
            raise DatasetContractError('DATASET_JSON_INVALID') from error

    @property
    def digest(self):
        return hashlib.sha256(self.encoded).hexdigest()

    def body(self):
        # No caller receives a mutable reference to the sealed candidate.
        return json.loads(self.encoded)

    def unresolved(self):
        record = self.body()
        return {'status': 'UNRESOLVED_DATASET_CANDIDATE', 'record_id': record['record_id'],
            'manifest_sha256': self.digest, 'authority_effect': 'NONE', 'qualified_for_research': False,
            'scope': record['scope'], 'required_resolutions': {
                'artifact_ids': [p['artifact_id'] for p in record['partitions']],
                'target_spec_ids': record['target_spec_ids'], 'entitlement_refs': record['entitlement_refs'],
                'consent_scope_ref': record['consent_scope_ref'],
                **{field: record[field] for field in ('universe_digest', 'calendar_digest',
                    'source_manifest_digest', 'row_identity_digest', 'feature_definition_digest')}},
            'reason_codes': ['ACTUAL_REFERENCES_AND_BYTES_NOT_RESOLVED',
                'CURRENT_SCOPE_CONSENT_AND_SOURCE_USE_NOT_VERIFIED',
                'SOURCE_CLOCKS_ROWS_CALENDAR_UNIVERSE_NOT_VERIFIED']}
