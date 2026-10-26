"""Original partial-depth captures through the existing market archive owner.

Historical storage preserves observed bytes and policy, never current liquidity,
native continuity, normalized price semantics, provider admission or authority.
"""
from dataclasses import dataclass
from decimal import Decimal
import json
import re

from vati.core.canonical import canonical_hash,canonical_json
from vati.core.file_lock import exclusive_state_lock
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.depth import DepthObservation
from vati.execution.ctrader.feed import native_integer
from vati.market_data.native_archive import NativeMarketArchive,NativeArchiveError,REQUEST_ID,_scope
from vati.market_data.native_quotes import _validate_capacity

UINT64_TEXT=re.compile(r'(?:0|[1-9][0-9]{0,19})',re.ASCII)
MAX_TIME=253402300799000


@dataclass(frozen=True)
class NativeDepthCapture:
    max_age_ms: int
    limit: int
    depth_json: str
    read_capacity_json: str

    @classmethod
    def capture(cls,observation,read_capacity,*,max_age_ms,limit):
        if not isinstance(observation,DepthObservation):raise ValueError('original typed native depth required')
        return cls(max_age_ms,limit,canonical_json(observation.body()),canonical_json(read_capacity))

    def body(self):
        body={'schema':'vati.native-depth-capture/1','max_age_ms':self.max_age_ms,'limit':self.limit,
              'depth':json.loads(self.depth_json),'read_capacity':json.loads(self.read_capacity_json),
              'provider_qualified':False,'authority_effect':'NONE'}
        return body|{'capture_sha256':canonical_hash(body)}


def _uint_text(value,*,minimum=0):
    if not isinstance(value,str) or UINT64_TEXT.fullmatch(value) is None:
        raise ValueError('native depth canonical unsigned integer text required')
    return native_integer(int(value),minimum=minimum,maximum=2**64-1)


def _validate_capture(contract_body,capture):
    contract=NativeSymbolContract.from_body(contract_body);scope=contract.native_scope
    keys={'schema','max_age_ms','limit','depth','read_capacity','provider_qualified','authority_effect','capture_sha256'}
    if (not isinstance(capture,dict) or set(capture)!=keys or capture['schema']!='vati.native-depth-capture/1'
            or capture['provider_qualified'] is not False or capture['authority_effect']!='NONE'
            or capture['capture_sha256']!=canonical_hash({k:v for k,v in capture.items() if k!='capture_sha256'})):
        raise ValueError('native depth capture hash or format invalid')
    max_age=native_integer(capture['max_age_ms'],minimum=1)
    limit=native_integer(capture['limit'],minimum=1,maximum=4096)
    _validate_capacity(capture['read_capacity'])
    depth=capture['depth']
    fixed={'schema':'vati.ctrader-depth/1','state':'OBSERVED_PARTIAL_NATIVE_DEPTH','recovery_reason':None,
           'control_state':'SUBSCRIBE_ACKNOWLEDGED_QUEUED','subscription_state':'ACKNOWLEDGED_QUEUED_NOT_DELIVERY',
           'observed_changes':True,'native_timestamp_ms':None,'native_sequence':None,'complete_book':False,
           'empty_book_proven':False,'sequence_state':'NOT_PROVIDED_BY_NATIVE_DEPTH',
           'snapshot_boundary':'NOT_PROVIDED_BY_NATIVE_DEPTH',
           'availability_basis':'LOCAL_PROCESSING_CLOCK_NOT_NATIVE_TIME_OR_NETWORK_RECEIPT',
           'price_basis':'NATIVE_UINT64_DEPTH_PRICE_SCALE_NOT_QUALIFIED','price_scale':None,
           'normalized_prices_available':False,'size_basis':'NATIVE_QUOTE_CENTS_NOT_LOTS_OR_NOTIONAL',
           'provider_qualified':False,'tradability_qualified':False,'authority_effect':'NONE'}
    dynamic={'scope','contract_revision','bids','asks','observed_quote_count','observed_bid_count','observed_ask_count',
             'display_limit_per_side','display_truncated','native_change_events_processed','processed_at_ms',
             'last_change_processed_at_ms','evaluated_at_ms','processing_age_ms','side_state','crossed_observed_levels',
             'observation_sha256'}
    if (not isinstance(depth,dict) or set(depth)!=set(fixed)|dynamic
            or any(canonical_json(depth[k])!=canonical_json(v) for k,v in fixed.items())
            or depth['observation_sha256']!=canonical_hash({k:v for k,v in depth.items() if k!='observation_sha256'})):
        raise ValueError('native depth state, provenance or hash invalid')
    _scope(depth['scope'])
    if depth['scope']!=scope or depth['contract_revision']!=contract.revision:
        raise ValueError('native depth contract/scope differs')
    total=native_integer(depth['observed_quote_count'],maximum=4096)
    bid_count=native_integer(depth['observed_bid_count'],maximum=total)
    ask_count=native_integer(depth['observed_ask_count'],maximum=total)
    if total!=bid_count+ask_count or native_integer(depth['display_limit_per_side'],minimum=1,maximum=4096)!=limit:
        raise ValueError('native depth count or display policy differs')
    if depth['display_truncated'] is not (bid_count>limit or ask_count>limit):
        raise ValueError('native depth truncation state differs')
    seen=set();tops={}
    for side,count in [('bid',bid_count),('ask',ask_count)]:
        rows=depth[side+'s']
        if not isinstance(rows,list) or len(rows)!=min(count,limit):raise ValueError('native depth side count differs')
        order=[]
        for row in rows:
            if (not isinstance(row,dict) or set(row)!={'native_quote_id','side','native_price','native_size_cents','native_size'}
                    or row['side']!=side.upper()):raise ValueError('native depth quote format invalid')
            identity=_uint_text(row['native_quote_id']);price=_uint_text(row['native_price'],minimum=1)
            size=_uint_text(row['native_size_cents'])
            if identity in seen:raise ValueError('native depth quote identity duplicated')
            seen.add(identity)
            if row['native_size']!=str(Decimal((0,tuple(map(int,str(size))),-2))):
                raise ValueError('native depth cent amount differs')
            order.append(((-price if side=='bid' else price),identity))
        if order!=sorted(order):raise ValueError('native depth quote order differs')
        tops[side]=_uint_text(rows[0]['native_price'],minimum=1) if rows else None
    crossed=bool(bid_count and ask_count and tops['bid']>tops['ask'])
    state='TWO_SIDED' if bid_count and ask_count else 'BID_ONLY' if bid_count else 'ASK_ONLY' if ask_count else 'NO_OBSERVED_QUOTES'
    if depth['crossed_observed_levels'] is not crossed or depth['side_state']!=state:
        raise ValueError('native depth side state differs')
    native_integer(depth['native_change_events_processed'],minimum=1)
    changed=native_integer(depth['last_change_processed_at_ms'],minimum=contract.received_at_ms,maximum=MAX_TIME)
    processed=native_integer(depth['processed_at_ms'],minimum=changed,maximum=MAX_TIME)
    evaluated=native_integer(depth['evaluated_at_ms'],minimum=processed,maximum=MAX_TIME)
    age=native_integer(depth['processing_age_ms'],maximum=max_age)
    if age!=evaluated-changed:raise ValueError('native depth causal processing age differs')
    return contract,scope,'DEPTH'


class NativeDepthArchive(NativeMarketArchive):
    observation_type=NativeDepthCapture
    contract_types=(NativeSymbolContract,)
    _validate_capture=staticmethod(_validate_capture)

    @staticmethod
    def _validate_timeframe(timeframe):
        if timeframe!='DEPTH':raise ValueError('native depth archive requires DEPTH partition')

    @staticmethod
    def _observation_available_at(observation):return observation['depth']['evaluated_at_ms']

    @staticmethod
    def _receipt(body,digest,index_state):
        capture=body['observation'];depth=capture['depth']
        return {'record_ref':digest,'revision':body['revision'],'request_id':body['request_id'],
                'scope':body['scope'],'timeframe':'DEPTH','contract_revision':body['contract']['metadata_revision'],
                'captured_max_age_ms':capture['max_age_ms'],'captured_limit':capture['limit'],
                'host_processed_at_ms':depth['processed_at_ms'],'last_change_processed_at_ms':depth['last_change_processed_at_ms'],
                'evaluated_at_ms':depth['evaluated_at_ms'],'available_at_ms':body['recorded_at_ms'],
                'index_state':index_state,'state':'HISTORICAL_PARTIAL_DEPTH_CAPTURE_UNQUALIFIED',
                'current_freshness':'NOT_EVALUATED_HISTORICAL_RECORD','complete_book':False,
                'normalized_prices_available':False,'provider_qualified':False,'authority_effect':'NONE'}


class NativeDepthCollector:
    def __init__(self,archive,reader_factory):
        if not isinstance(archive,NativeDepthArchive) or not callable(reader_factory):
            raise ValueError('native depth archive and reader factory required')
        self.archive,self.reader_factory=archive,reader_factory

    def collect(self,request_id,expected_contract,*,max_age_ms=5000,limit=100):
        if (not isinstance(request_id,str) or REQUEST_ID.fullmatch(request_id) is None
                or not isinstance(expected_contract,NativeSymbolContract)):
            raise NativeArchiveError('native depth collection identity or contract invalid')
        native_integer(max_age_ms,minimum=1);native_integer(limit,minimum=1,maximum=4096)
        scope=expected_contract.native_scope;part=self.archive._partition(scope,'DEPTH',create=True)
        with exclusive_state_lock(part/('request-'+canonical_hash(request_id))):
            original=self.archive.lookup(scope,'DEPTH',request_id)
            if original is not None:
                if (original['contract_revision']!=expected_contract.revision
                        or original['captured_max_age_ms']!=max_age_ms or original['captured_limit']!=limit):
                    raise NativeArchiveError('native depth collection identity conflicts with original contract/policy')
                return self.archive.reconcile(scope,'DEPTH',request_id) if original['index_state']!='CONSISTENT' else original
            reader=self.reader_factory()
            try:contract,observed=reader.read_depth(expected_contract,max_age_ms=max_age_ms,limit=limit)
            finally:reader.close()
            capacity=reader.read_capacity_snapshot()
            if (not isinstance(contract,NativeSymbolContract) or not isinstance(observed,DepthObservation)
                    or contract.native_scope!=scope or contract.revision!=expected_contract.revision):
                raise NativeArchiveError('native depth result differs from original contract')
            capture=NativeDepthCapture.capture(observed,capacity,max_age_ms=max_age_ms,limit=limit)
            return self.archive.record(request_id,contract,capture)
