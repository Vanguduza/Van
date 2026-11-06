"""Read-only native identity, including inactive catalog entries.

This is deliberately a separate type from NativeSymbolContract. It contains no
order-volume or execution permission and cannot enter the active symbol registry.
Native archived update time remains metadata, never an effective delisting date.
"""
from dataclasses import dataclass
import json

from vati.core.canonical import canonical_hash, canonical_json
from vati.execution.ctrader.catalog import NativeSymbolCatalog, MAX_CATALOG_BYTES
from vati.execution.ctrader.feed import native_integer


@dataclass(frozen=True)
class NativeReadIdentity:
    metadata_json: str
    received_at_ms: int

    def __post_init__(self):
        native_integer(self.received_at_ms, maximum=253402300799000)
        if not isinstance(self.metadata_json, str) or len(self.metadata_json.encode()) > MAX_CATALOG_BYTES+4096:
            raise ValueError('native read identity byte bound')
        metadata = json.loads(self.metadata_json)
        if (not isinstance(metadata, dict) or set(metadata) != {'schema', 'catalog_metadata', 'native_symbol_id'}
                or metadata['schema'] != 'vati.ctrader-read-identity/1'
                or canonical_json(metadata) != self.metadata_json):
            raise ValueError('native read identity format invalid')
        identity = native_integer(metadata['native_symbol_id'], minimum=1)
        catalog = NativeSymbolCatalog(canonical_json(metadata['catalog_metadata']), self.received_at_ms)
        if catalog.metadata['include_archived_symbols'] is not True:
            raise ValueError('native read identity requires archived catalog request profile')
        selected = [member for member in catalog.members() if member['native_symbol_id'] == identity]
        if len(selected) != 1:
            raise ValueError('native read identity absent from original catalog')
        object.__setattr__(self, '_catalog', catalog)
        object.__setattr__(self, '_member_json', canonical_json(selected[0]))

    @classmethod
    def capture(cls, catalog, native_symbol_id):
        if not isinstance(catalog, NativeSymbolCatalog):
            raise ValueError('native original catalog capture required')
        return cls(canonical_json({'schema':'vati.ctrader-read-identity/1',
            'catalog_metadata':catalog.metadata, 'native_symbol_id':native_symbol_id}), catalog.received_at_ms)

    @property
    def metadata(self):
        return json.loads(self.metadata_json)

    @property
    def member(self):
        return json.loads(self._member_json)

    @property
    def revision(self):
        return canonical_hash(self.metadata)

    @property
    def native_scope(self):
        return self._catalog.native_scope | {'native_symbol_id': self.metadata['native_symbol_id']}

    @property
    def display_name(self):
        member = self.member
        return member['original'].get('symbolName' if member['source_kind']=='LIGHT' else 'name')

    @property
    def series_label(self):
        name = self.display_name
        label = name.replace('/', '').upper() if name else ''
        if label and len(label) <= 256:
            return label
        return 'CTRADER_NATIVE_' + str(self.native_scope['native_symbol_id'])

    def body(self):
        member = self.member; name = self.display_name
        return {'schema':'vati.ctrader-read-identity-capture/1', 'metadata':self.metadata,
            'metadata_revision':self.revision, 'received_at_ms':self.received_at_ms,
            'source_kind':member['source_kind'], 'series_label':self.series_label,
            'series_label_basis':'NATIVE_DECLARED_NAME' if name and 1<=len(name.replace('/', '').upper())<=256
                else 'NATIVE_ID_LABEL_NAME_UNAVAILABLE_OR_TOO_LONG',
            'lifecycle_effective_at_ms':None, 'qualified_for_execution':False,
            'qualified_for_research':False, 'provider_qualified':False, 'authority_effect':'NONE'}

    @classmethod
    def from_body(cls, body):
        if not isinstance(body, dict) or body.get('schema') != 'vati.ctrader-read-identity-capture/1':
            raise ValueError('native read identity capture format invalid')
        if any(body.get(key) is not False for key in ('qualified_for_execution','qualified_for_research','provider_qualified')):
            raise ValueError('native read identity has no qualification authority')
        try:
            identity = cls(canonical_json(body['metadata']), body['received_at_ms'])
            if identity.body() != body:
                raise ValueError('native read identity hash, facts or authority invalid')
            return identity
        except (KeyError, TypeError) as error:
            raise ValueError('native read identity capture invalid') from error
