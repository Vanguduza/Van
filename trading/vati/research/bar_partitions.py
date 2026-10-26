"""Derived Parquet publication over the existing native archive; never a grant.

This source materializer does not publish an admitted DatasetManifest. Unknown
calendars, incomplete coverage and absent research-use rights stay explicit.
"""
import json
from dataclasses import dataclass
from pathlib import Path
import re

from vati.core.file_lock import exclusive_state_lock
from vati.market_data.feeds.lake import BarLake
from vati.market_data.native_windows import NativeBarWindowReader
from vati_forecast_worker.source_partitions import (
    SourcePartitionError, MAX_BYTES, canonical, encode_native_bar_partition,
    verify_native_bar_partition,
)


class PartitionPublicationUnknown(SourcePartitionError):
    """Reconcile the original window reference; do not create a replacement."""


@dataclass(frozen=True)
class PartitionBudget:
    publications: int = 256
    stored_bytes: int = 512 * 1024**2

    def __post_init__(self):
        if (type(self.publications) is not int or not 1 <= self.publications <= 10000
                or type(self.stored_bytes) is not int or not 1 <= self.stored_bytes <= 1024**3):
            raise SourcePartitionError('PARTITION_STORAGE_BUDGET_INVALID')


class NativeBarPartitionService:
    def __init__(self, reader, root, *, budget=None):
        if not isinstance(reader, NativeBarWindowReader):
            raise SourcePartitionError('PARTITION_ORIGINAL_ARCHIVE_OWNER_REQUIRED')
        self.reader = reader
        self.budget = budget or PartitionBudget()
        if not isinstance(self.budget, PartitionBudget):
            raise SourcePartitionError('PARTITION_STORAGE_BUDGET_REQUIRED')
        self.root = Path(root).absolute()
        self._paths()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _paths(self):
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise SourcePartitionError('PARTITION_LINKED_OUTPUT_REFUSED')

    def _file(self, name):
        self._paths()
        path = self.root / name
        if path.is_symlink():
            raise SourcePartitionError('PARTITION_LINKED_OUTPUT_REFUSED')
        return path

    @staticmethod
    def _read(path):
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise SourcePartitionError('PARTITION_ARTIFACT_BYTE_LIMIT')
        return data

    @staticmethod
    def _ref(value):
        if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
            raise SourcePartitionError('PARTITION_WINDOW_REFERENCE_INVALID')
        return value

    def _capacity(self, additions):
        existing = {}; publications = set()
        for path in self.root.iterdir():
            if path.name == '.source-publications.lock':
                continue
            if (path.is_symlink() or not path.is_file()
                    or re.fullmatch('[0-9a-f]{64}\\.(json|parquet)', path.name) is None):
                raise SourcePartitionError('PARTITION_OUTPUT_NAMESPACE_CONFLICT')
            existing[path.name] = path.stat().st_size
            publications.add(path.stem)
        # A global writer lock covers every native scope using this output
        # owner. Cross-account storage cannot bypass the actual total budget.
        for name, size in additions.items():
            existing[name] = size
            publications.add(Path(name).stem)
        if len(publications) > self.budget.publications or sum(existing.values()) > self.budget.stored_bytes:
            raise SourcePartitionError('PARTITION_STORAGE_CAPACITY_REFUSED')

    def get(self, window_ref, *, expected_scope):
        window_ref = self._ref(window_ref)
        manifest_path = self._file(window_ref + '.json')
        if not manifest_path.exists():
            return None
        if manifest_path.stat().st_size > MAX_BYTES:
            raise SourcePartitionError('PARTITION_MANIFEST_BYTE_LIMIT')
        raw = self._read(manifest_path)
        try:
            manifest = json.loads(raw)
            if canonical(manifest) != raw or set(manifest) != {'schema', 'window', 'partition'}:
                raise SourcePartitionError('PARTITION_MANIFEST_INVALID')
            window = manifest['window']
            if (manifest['schema'] != 'vati.native-source-parquet-publication/1'
                    or window['window_sha256'] != window_ref):
                raise SourcePartitionError('PARTITION_MANIFEST_IDENTITY_CONFLICT')
            actual = self.reader.verify(window, expected_scope=expected_scope)
            descriptor = manifest['partition']
            path = self._file(window_ref + '.parquet')
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                raise SourcePartitionError('PARTITION_ORIGINAL_BYTES_UNAVAILABLE')
            data = self._read(path)
            if verify_native_bar_partition(data, actual) != descriptor:
                raise SourcePartitionError('PARTITION_READBACK_CONFLICT')
            return descriptor | {'publication_ref': window_ref, 'original_source_resolved': True,
                'dataset_manifest_admitted': False, 'research_use_state': 'UNKNOWN_REFUSED'}
        except (KeyError, TypeError, ValueError) as error:
            raise SourcePartitionError('PARTITION_PUBLICATION_INVALID:' + str(error)) from error

    def publish(self, window, *, expected_scope):
        # The hash/envelope is not provenance: resolve original archive facts.
        actual = self.reader.verify(window, expected_scope=expected_scope)
        window_ref = self._ref(actual['window_sha256'])
        requested = False
        try:
            with exclusive_state_lock(self._file('.source-publications')):
                original = self.get(window_ref, expected_scope=expected_scope)
                if original is not None:
                    return original
                data = encode_native_bar_partition(actual)
                descriptor = verify_native_bar_partition(data, actual)
                manifest = {'schema': 'vati.native-source-parquet-publication/1',
                            'window': actual, 'partition': descriptor}
                raw = canonical(manifest)
                if len(raw) > MAX_BYTES:
                    raise SourcePartitionError('PARTITION_MANIFEST_BYTE_LIMIT')
                self._capacity({window_ref + '.parquet': len(data), window_ref + '.json': len(raw)})
                # Resolve again before writing: a corrupt/revoked source view
                # cannot be replaced with a previously computed client hash.
                self.reader.verify(actual, expected_scope=expected_scope)
                path = self._file(window_ref + '.parquet')
                if path.exists():
                    # Recover the original deterministic bytes after a lost
                    # manifest ACK; a conflicting orphan is never overwritten.
                    if path.stat().st_size != len(data) or self._read(path) != data:
                        raise SourcePartitionError('PARTITION_ORPHAN_CONFLICT')
                else:
                    requested = True
                    BarLake._atomic_write(path, data)
                requested = True
                BarLake._atomic_write(self._file(window_ref + '.json'), raw)
            result = self.get(window_ref, expected_scope=expected_scope)
            if result is None:
                raise PartitionPublicationUnknown('PARTITION_ORIGINAL_READBACK_UNAVAILABLE:' + window_ref)
            return result
        except OSError as error:
            if requested:
                raise PartitionPublicationUnknown('PARTITION_PUBLICATION_UNKNOWN:' + window_ref) from error
            raise SourcePartitionError('PARTITION_STORAGE_UNAVAILABLE') from error

