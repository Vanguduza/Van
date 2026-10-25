"""Captured native contract metadata; integrity and identity grant no authority."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from vati.core.canonical import canonical_hash, canonical_json
from vati.execution.ctrader.feed import native_integer
from vati.execution.ctrader.transport import DEMO_HOST, LIVE_HOST


def _finite_json(value, depth=0):
    if depth > 32:
        raise ValueError('native contract metadata nesting bound')
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('native contract metadata keys invalid')
        for item in value.values():
            _finite_json(item, depth+1)
    elif isinstance(value, list):
        for item in value:
            _finite_json(item, depth+1)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('native contract metadata is nonfinite')
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError('native contract metadata type invalid')


@dataclass(frozen=True)
class NativeSymbolContract:
    """Canonical text prevents a caller mutating a nested captured dictionary.

    Its revision preserves the existing vati.ctrader-symbol/1 hash. Receipt time
    records availability separately and cannot rewrite that contract identity.
    """
    metadata_json: str
    received_at_ms: int

    def __post_init__(self):
        native_integer(self.received_at_ms, maximum=253402300799000)
        if not isinstance(self.metadata_json, str) or len(self.metadata_json.encode()) > 262144:
            raise ValueError('native contract metadata resource bound')
        metadata = json.loads(self.metadata_json)
        _finite_json(metadata)
        if (not isinstance(metadata, dict) or set(metadata) != {
                'schema', 'native_account_id', 'transport_host', 'light', 'detail'}
                or metadata['schema'] != 'vati.ctrader-symbol/1'
                or canonical_json(metadata) != self.metadata_json):
            raise ValueError('native contract metadata format invalid')
        native_integer(metadata['native_account_id'], minimum=1)
        host = metadata['transport_host']
        if host is not None and (not isinstance(host, str) or not host or len(host) > 253):
            raise ValueError('native contract host invalid')
        light, detail = metadata['light'], metadata['detail']
        if not isinstance(light, dict) or not isinstance(detail, dict):
            raise ValueError('native contract original metadata unavailable')
        if (not {'symbolId', 'symbolName', 'enabled'} <= light.keys()
                or not {'symbolId', 'digits', 'pipPosition', 'lotSize', 'minVolume', 'maxVolume', 'stepVolume'} <= detail.keys()):
            raise ValueError('native contract mandatory metadata unavailable')
        product = native_integer(light['symbolId'], minimum=1)
        if native_integer(detail['symbolId'], minimum=1) != product or light.get('enabled') is not True:
            raise ValueError('native contract product scope invalid')
        name = light['symbolName']
        if not isinstance(name, str) or not name.strip() or len(name) > 256 or any(ord(c) < 32 for c in name):
            raise ValueError('native contract product name invalid')
        native_integer(detail['digits'], maximum=18)
        native_integer(detail['pipPosition'], minimum=-(2**31), maximum=2**31-1)
        native_integer(detail['lotSize'], minimum=1)
        minimum = native_integer(detail['minVolume'], minimum=1)
        maximum = native_integer(detail['maxVolume'], minimum=minimum)
        native_integer(detail['stepVolume'], minimum=1, maximum=maximum)

    @classmethod
    def capture(cls, *, account_id, transport_host, light, detail, received_at_ms):
        metadata = {'schema': 'vati.ctrader-symbol/1', 'native_account_id': account_id,
                    'transport_host': transport_host, 'light': light, 'detail': detail}
        _finite_json(metadata)
        return cls(canonical_json(metadata), received_at_ms)

    @property
    def metadata(self):
        return json.loads(self.metadata_json)

    @property
    def revision(self):
        return canonical_hash(self.metadata)

    @property
    def native_scope(self):
        metadata = self.metadata
        environment = {DEMO_HOST: 'DEMO', LIVE_HOST: 'LIVE'}.get(metadata['transport_host'])
        if environment is None:
            raise ValueError('native contract environment unavailable')
        return {'provider': 'CTRADER', 'environment': environment,
                'transport_host': metadata['transport_host'],
                'native_account_id': metadata['native_account_id'],
                'native_symbol_id': metadata['light']['symbolId']}

    def body(self):
        return {'schema': 'vati.ctrader-contract-capture/1', 'metadata': self.metadata,
                'metadata_revision': self.revision, 'received_at_ms': self.received_at_ms,
                'provider_qualified': False, 'authority_effect': 'NONE'}

    @classmethod
    def from_body(cls, body):
        if not isinstance(body, dict) or set(body) != {
                'schema', 'metadata', 'metadata_revision', 'received_at_ms',
                'provider_qualified', 'authority_effect'}:
            raise ValueError('native contract capture format invalid')
        result = cls(canonical_json(body['metadata']), body['received_at_ms'])
        if result.body() != body or body['provider_qualified'] is not False:
            raise ValueError('native contract capture hash or authority invalid')
        return result
