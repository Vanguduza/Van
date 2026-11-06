"""Immutable historical quote captures, never current tradability or authority.

The native bar archive's commit/recovery mechanism is shared without rewriting
existing records. SPOT partitions retain their original quote policy and read
resource diagnostic. This is snapshot capture, not a complete tick stream.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import json

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.file_lock import exclusive_state_lock
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.feed import native_integer
from vati.execution.ctrader.spots import SpotObservation
from vati.market_data.native_archive import NativeMarketArchive, NativeArchiveError, REQUEST_ID, _scope


@dataclass(frozen=True)
class NativeQuoteCapture:
    max_age_ms: int
    quote_json: str
    read_capacity_json: str

    @classmethod
    def capture(cls, observation, read_capacity, *, max_age_ms):
        if not isinstance(observation, SpotObservation):
            raise ValueError('original typed native quote required')
        return cls(max_age_ms, canonical_json(observation.body()), canonical_json(read_capacity))

    def body(self):
        body={'schema':'vati.native-quote-capture/1','max_age_ms':self.max_age_ms,
              'quote':json.loads(self.quote_json),'read_capacity':json.loads(self.read_capacity_json),
              'provider_qualified':False,'authority_effect':'NONE'}
        return body|{'capture_sha256':canonical_hash(body)}


def _validate_capacity(body):
    keys={'schema','state','max_read_frames','max_read_bytes','admitted_frame_headers',
          'reserved_encoded_bytes','refused_frame_length','accounting_basis','provider_qualified','authority_effect'}
    if (not isinstance(body,dict) or set(body)!=keys or body['schema']!='vati.ctrader-read-capacity/1'
            or body['state']!='WITHIN_LIMIT' or body['refused_frame_length'] is not None
            or body['provider_qualified'] is not False or body['authority_effect']!='NONE'
            or body['accounting_basis']!='ADMITTED_PROTOBUF_LENGTH_EXCLUDING_PREFIX_NOT_DECODED_DELIVERY_OR_PROCESS_MEMORY'):
        raise ValueError('native quote read-capacity capture invalid')
    frames=native_integer(body['max_read_frames'],minimum=1,maximum=65536)
    size=native_integer(body['max_read_bytes'],minimum=1,maximum=256*1024*1024)
    admitted=native_integer(body['admitted_frame_headers'],minimum=1,maximum=frames)
    reserved=native_integer(body['reserved_encoded_bytes'],minimum=1,maximum=size)
    if admitted>reserved:raise ValueError('native quote read-capacity totals inconsistent')


def _validate_capture(contract_body, capture):
    contract=NativeSymbolContract.from_body(contract_body);scope=contract.native_scope
    keys={'schema','max_age_ms','quote','read_capacity','provider_qualified','authority_effect','capture_sha256'}
    if (not isinstance(capture,dict) or set(capture)!=keys
            or capture['schema']!='vati.native-quote-capture/1'
            or capture['provider_qualified'] is not False or capture['authority_effect']!='NONE'
            or capture['capture_sha256']!=canonical_hash({k:v for k,v in capture.items() if k!='capture_sha256'})):
        raise ValueError('native quote capture hash or format invalid')
    max_age=native_integer(capture['max_age_ms'],minimum=1)
    _validate_capacity(capture['read_capacity'])
    quote=capture['quote']
    if not isinstance(quote,dict):raise ValueError('native quote unavailable')
    _scope(quote.get('scope'))
    if quote['scope']!=scope or quote.get('contract_revision')!=contract.revision:
        raise ValueError('native quote contract/scope differs')
    prices=[]
    with localcontext() as context:
        context.prec=80
        for side in ('bid','ask'):
            value=quote.get(side)
            if not isinstance(value,str) or not 1<=len(value)<=128:raise ValueError('native quote price unavailable')
            value=Decimal(value)
            if not value.is_finite():raise ValueError('native quote price unavailable')
            units=value*100000
            if units!=int(units):raise ValueError('native quote price precision invalid')
            native_integer(int(units),minimum=1,maximum=2**64-1);prices.append(value)
    if prices[1]<prices[0]:raise ValueError('native quote crossed')
    processed=native_integer(quote.get('processed_at_ms'),minimum=contract.received_at_ms,maximum=253402300799000)
    evaluated=native_integer(quote.get('evaluated_at_ms'),minimum=processed,maximum=253402300799000)
    bid_time=native_integer(quote.get('bid_native_time_ms'),maximum=processed)
    ask_time=native_integer(quote.get('ask_native_time_ms'),maximum=processed)
    age=native_integer(quote.get('age_ms'),maximum=max_age)
    if age!=evaluated-min(bid_time,ask_time):raise ValueError('native quote causal age differs')
    ignored=native_integer(quote.get('ignored_older_updates'))
    state='OBSERVED_UNQUALIFIED_LATE_UPDATE_IGNORED' if ignored else 'OBSERVED_UNQUALIFIED'
    original=SpotObservation(canonical_json(scope),contract.revision,state,*prices,bid_time,ask_time,
        processed,evaluated,age,ignored,True,'SUBSCRIBE_ACKNOWLEDGED_QUEUED').body()
    if (quote.get('provider_qualified') is not False or quote.get('authority_effect')!='NONE'
            or quote!=original):
        raise ValueError('native quote state, provenance or hash invalid')
    return contract,scope,'SPOT'


class NativeQuoteArchive(NativeMarketArchive):
    observation_type=NativeQuoteCapture
    contract_types=(NativeSymbolContract,)
    _validate_capture=staticmethod(_validate_capture)

    @staticmethod
    def _validate_timeframe(timeframe):
        if timeframe!='SPOT':raise ValueError('native quote archive requires SPOT partition')

    @staticmethod
    def _observation_available_at(observation):
        return observation['quote']['evaluated_at_ms']

    @staticmethod
    def _receipt(body,digest,index_state):
        capture=body['observation'];quote=capture['quote']
        return {'record_ref':digest,'revision':body['revision'],'request_id':body['request_id'],
                'scope':body['scope'],'timeframe':'SPOT','contract_revision':body['contract']['metadata_revision'],
                'captured_max_age_ms':capture['max_age_ms'],'native_bid_time_ms':quote['bid_native_time_ms'],
                'native_ask_time_ms':quote['ask_native_time_ms'],'host_processed_at_ms':quote['processed_at_ms'],
                'evaluated_at_ms':quote['evaluated_at_ms'],'available_at_ms':body['recorded_at_ms'],
                'index_state':index_state,'state':'HISTORICAL_QUOTE_CAPTURE_UNQUALIFIED',
                'current_freshness':'NOT_EVALUATED_HISTORICAL_RECORD','provider_qualified':False,'authority_effect':'NONE'}


class NativeQuoteCollector:
    def __init__(self, archive, reader_factory):
        if not isinstance(archive,NativeQuoteArchive):raise ValueError('native quote archive required')
        self.archive,self.reader_factory=archive,reader_factory

    def collect(self,request_id,expected_contract,*,max_age_ms=5000):
        if (not isinstance(request_id,str) or not REQUEST_ID.fullmatch(request_id)
                or not isinstance(expected_contract,NativeSymbolContract)):
            raise NativeArchiveError('native quote collection identity or contract invalid')
        native_integer(max_age_ms,minimum=1)
        scope=expected_contract.native_scope;part=self.archive._partition(scope,'SPOT',create=True)
        with exclusive_state_lock(part/('request-'+canonical_hash(request_id))):
            original=self.archive.lookup(scope,'SPOT',request_id)
            if original is not None:
                if (original['contract_revision']!=expected_contract.revision
                        or original['captured_max_age_ms']!=max_age_ms):
                    raise NativeArchiveError('native quote collection identity conflicts with original contract/policy')
                return self.archive.reconcile(scope,'SPOT',request_id) if original['index_state']!='CONSISTENT' else original
            reader=self.reader_factory()
            try:
                contract,observed=reader.read_quote(expected_contract,max_age_ms=max_age_ms)
            finally:
                reader.close()
            # Read the final diagnostic only after the original worker is joined.
            # WITHIN_LIMIT is not a freshness, provider or continuity certificate.
            capacity=reader.read_capacity_snapshot()
            if (not isinstance(contract,NativeSymbolContract) or not isinstance(observed,SpotObservation)
                    or contract.native_scope!=scope or contract.revision!=expected_contract.revision):
                raise NativeArchiveError('native quote result differs from original contract')
            capture=NativeQuoteCapture.capture(observed,capacity,max_age_ms=max_age_ms)
            return self.archive.record(request_id,contract,capture)
