"""Original visible, hidden and archived symbol listings; no execution contract."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from vati.core.canonical import canonical_hash,canonical_json
from vati.execution.ctrader.contracts import _finite_json
from vati.execution.ctrader.feed import native_integer
from vati.execution.ctrader.protoschema import SCHEMA
from vati.execution.ctrader.transport import DEMO_HOST,LIVE_HOST

MAX_CATALOG_BYTES=8*1024**2
MAX_CATALOG_ROWS=100000


def catalog_scope(scope):
    if not isinstance(scope,dict) or set(scope)!={'provider','environment','transport_host','native_account_id'}:
        raise ValueError('native catalog scope format invalid')
    if any(not isinstance(scope[name],str) for name in ('provider','environment','transport_host')):
        raise ValueError('native catalog scope text invalid')
    if (scope['provider']!='CTRADER' or scope['environment'] not in {'DEMO','LIVE'}
            or {DEMO_HOST:'DEMO',LIVE_HOST:'LIVE'}.get(scope['transport_host'])!=scope['environment']):
        raise ValueError('native catalog environment invalid')
    native_integer(scope['native_account_id'],minimum=1)
    return dict(scope)


def _text(value,*,allow_empty=False):
    if not isinstance(value,str) or (not allow_empty and not value.strip()) or len(value)>4096 or any(ord(c)<32 for c in value):
        raise ValueError('native catalog text invalid')


def _validate_response(response,account,received,include_archived):
    if not isinstance(response,dict) or set(response)-{f.name for f in SCHEMA.messages['ProtoOASymbolsListRes']}:
        raise ValueError('native catalog response format incompatible')
    if native_integer(response['ctidTraderAccountId'],minimum=1)!=account:
        raise ValueError('native catalog response account differs')
    payload=response.get('payloadType')
    expected_name=next(f.default for f in SCHEMA.messages['ProtoOASymbolsListRes'] if f.name=='payloadType')
    if 'payloadType' in response and not ((type(payload) is int and payload==SCHEMA.payload_type['ProtoOASymbolsListRes'])
            or (type(payload) is str and payload==expected_name)):
        raise ValueError('native catalog response payload type differs')
    light=response.get('symbol',[]);archived=response.get('archivedSymbol',[])
    if (not isinstance(light,list) or not isinstance(archived,list)
            or len(light)+len(archived)>MAX_CATALOG_ROWS):raise ValueError('native catalog row capacity')
    if archived and not include_archived:raise ValueError('unsolicited archived catalog scope')
    seen=set()
    for rows,type_name in [(light,'ProtoOALightSymbol'),(archived,'ProtoOAArchivedSymbol')]:
        allowed={f.name for f in SCHEMA.messages[type_name]}
        for row in rows:
            if not isinstance(row,dict) or set(row)-allowed:raise ValueError('native catalog row format incompatible')
            identity=native_integer(row['symbolId'],minimum=1)
            if identity in seen:raise ValueError('native catalog duplicate or conflicting native identity')
            seen.add(identity)
            if rows is light:
                if 'enabled' in row and type(row['enabled']) is not bool:raise ValueError('native catalog visibility invalid')
                if 'symbolName' in row:_text(row['symbolName'],allow_empty=True)
                for key in ('baseAssetId','quoteAssetId','symbolCategoryId'):
                    if key in row:native_integer(row[key],minimum=1)
                if 'sortingNumber' in row and (type(row['sortingNumber']) not in (float,int)
                        or not math.isfinite(row['sortingNumber'])):raise ValueError('native catalog sorting number invalid')
            else:
                _text(row['name'])
                native_integer(row['utcLastUpdateTimestamp'],maximum=received)
            if 'description' in row and (not isinstance(row['description'],str) or len(row['description'])>4096):
                raise ValueError('native catalog description bound invalid')


@dataclass(frozen=True)
class NativeSymbolCatalog:
    metadata_json: str
    received_at_ms: int

    def __post_init__(self):
        native_integer(self.received_at_ms,maximum=253402300799000)
        if not isinstance(self.metadata_json,str) or len(self.metadata_json.encode())>MAX_CATALOG_BYTES:
            raise ValueError('native catalog byte capacity')
        metadata=json.loads(self.metadata_json);_finite_json(metadata)
        if (not isinstance(metadata,dict) or set(metadata)!={'schema','scope','include_archived_symbols',
                'protocol_schema_sha256','response'} or metadata['schema']!='vati.ctrader-catalog/1'
                or canonical_json(metadata)!=self.metadata_json):raise ValueError('native catalog metadata format invalid')
        scope=catalog_scope(metadata['scope'])
        if type(metadata['include_archived_symbols']) is not bool:raise ValueError('native catalog request profile unavailable')
        if metadata['protocol_schema_sha256']!=canonical_hash(SCHEMA.files_sha256):
            raise ValueError('native catalog protocol schema incompatible')
        _validate_response(metadata['response'],scope['native_account_id'],self.received_at_ms,metadata['include_archived_symbols'])

    @classmethod
    def capture(cls,*,scope,response,received_at_ms,include_archived_symbols):
        metadata={'schema':'vati.ctrader-catalog/1','scope':catalog_scope(scope),'response':response,
            'include_archived_symbols':include_archived_symbols,'protocol_schema_sha256':canonical_hash(SCHEMA.files_sha256)}
        _finite_json(metadata)
        return cls(canonical_json(metadata),received_at_ms)

    @property
    def metadata(self):return json.loads(self.metadata_json)

    @property
    def native_scope(self):return self.metadata['scope']

    @property
    def revision(self):return canonical_hash(self.metadata)

    def body(self):
        return {'schema':'vati.ctrader-catalog-capture/1','metadata':self.metadata,
            'metadata_revision':self.revision,'received_at_ms':self.received_at_ms,
            'provider_qualified':False,'qualified_for_research':False,'authority_effect':'NONE'}

    @classmethod
    def from_body(cls,body):
        if (not isinstance(body,dict) or set(body)!={'schema','metadata','metadata_revision','received_at_ms',
                'provider_qualified','qualified_for_research','authority_effect'}
                or body['schema']!='vati.ctrader-catalog-capture/1' or body['provider_qualified'] is not False
                or body['qualified_for_research'] is not False or body['authority_effect']!='NONE'):
            raise ValueError('native catalog capture format or authority invalid')
        captured=cls(canonical_json(body['metadata']),body['received_at_ms'])
        if body['metadata_revision']!=captured.revision:raise ValueError('native catalog revision differs')
        return captured

    def members(self):
        """Native IDs, not aliases; updated-at is never invented as delisting time."""
        metadata=self.metadata;rows=[]
        for kind,key in [('LIGHT','symbol'),('ARCHIVED','archivedSymbol')]:
            for original in metadata['response'].get(key,[]):
                visible=original.get('enabled',False) if kind=='LIGHT' else False
                rows.append({'native_symbol_id':original['symbolId'],
                    'instrument_identity':canonical_hash({'scope':metadata['scope'],'native_symbol_id':original['symbolId']}),
                    'original':original,'source_kind':kind,'visible':visible,
                    'name_state':'PRESENT' if original.get('symbolName' if kind=='LIGHT' else 'name') else 'UNAVAILABLE_NATIVE_NAME',
                    'visibility_basis':'ARCHIVED_SOURCE_RECORD' if kind=='ARCHIVED' else
                        'EXPLICIT_NATIVE_ENABLED' if 'enabled' in original else 'PROTO2_OMITTED_BOOL_DEFAULT_FALSE',
                    'observed_at_ms':self.received_at_ms,'lifecycle_effective_at_ms':None,
                    'lifecycle_time_state':'UNAVAILABLE_NATIVE_LAST_UPDATE_IS_NOT_DELISTING_TIME',
                    'provider_qualified':False,'qualified_for_research':False,'authority_effect':'NONE'})
        return sorted(rows,key=lambda row:row['native_symbol_id'])
