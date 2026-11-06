"""Account-bound native order/deal snapshots for original-operation recovery.

An order status and its recorded executions do not establish cash settlement,
complete fees, position flatness, an unused reservation or permission to trade.
"""
from dataclasses import asdict,dataclass
import json

from vati.core.canonical import canonical_hash,canonical_json
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.protoschema import SCHEMA
from vati.funding.native import native_int
from vati.risk.account_context import inspect_context
from vati.risk.contracts import NativeAccountRiskContext


def _enum(name,value):
    if type(value) is int:
        native_int(value,minimum=0,maximum=2**31-1)
        return SCHEMA.enum_reverse[name].get(value)
    if type(value) is str and value in SCHEMA.enums[name]:
        return value
    raise ValueError('native enum representation invalid')


def _facts(response,account_id,order_id):
    if type(response) is not dict or native_int(response['ctidTraderAccountId'],minimum=1)!=account_id:
        raise ValueError('native order response account mismatch')
    payload=response.get('payloadType')
    if payload is not None and not (
        type(payload) is str and payload=='PROTO_OA_ORDER_DETAILS_RES'
        or type(payload) is int and payload==SCHEMA.payload_type['ProtoOAOrderDetailsRes']):
        raise ValueError('native order response protocol mismatch')
    order=response['order'];trade=order['tradeData']
    if type(order) is not dict or type(trade) is not dict or native_int(order['orderId'],minimum=1)!=order_id:
        raise ValueError('native order identity mismatch')
    symbol=native_int(trade['symbolId'],minimum=1)
    volume=native_int(trade['volume'],minimum=0)
    side=_enum('ProtoOATradeSide',trade['tradeSide'])
    kind=_enum('ProtoOAOrderType',order['orderType'])
    status=_enum('ProtoOAOrderStatus',order['orderStatus'])
    executed=native_int(order['executedVolume'],minimum=0) if 'executedVolume' in order else None
    updated=native_int(order['utcLastUpdateTimestamp'],minimum=0) if 'utcLastUpdateTimestamp' in order else None
    closing=order.get('closingOrder')
    if closing is not None and type(closing) is not bool:
        raise ValueError('native closing-order flag invalid')
    deals=response.get('deal',[])
    if type(deals) is not list or len(deals)>4096:
        raise ValueError('native order deal capacity unavailable')
    unique={};gross=0;positions=set()
    for deal in deals:
        if type(deal) is not dict:
            raise ValueError('native order deal format invalid')
        identity=native_int(deal['dealId'],minimum=1)
        if (native_int(deal['orderId'],minimum=1)!=order_id
            or native_int(deal['symbolId'],minimum=1)!=symbol
            or _enum('ProtoOATradeSide',deal['tradeSide'])!=side):
            raise ValueError('native order/deal scope mismatch')
        position=native_int(deal['positionId'],minimum=1)
        native_int(deal['executionTimestamp'],minimum=0)
        requested=native_int(deal['volume'],minimum=0)
        filled=native_int(deal['filledVolume'],minimum=0,maximum=requested)
        deal_status=_enum('ProtoOADealStatus',deal['dealStatus'])
        if filled and deal_status not in ('FILLED','PARTIALLY_FILLED'):
            raise ValueError('native order deal fill status inconsistent')
        digest=canonical_hash(deal)
        if identity in unique:
            if unique[identity]['digest']!=digest:
                raise ValueError('conflicting native deal identity')
            continue
        unique[identity]={'native_id':identity,'digest':digest,'filled_volume_cents':filled}
        gross+=filled;positions.add(position)
    # Raw tradeData.volume is retained without assuming that a provider's
    # snapshot field is an original or remaining parent allowance.
    relation='UNAVAILABLE' if executed is None else 'MATCH' if executed==gross else 'CONFLICT'
    state='NATIVE_ENUM_UNSUPPORTED' if None in (side,kind,status) else (
        'NATIVE_EXECUTION_TOTALS_UNRECONCILED' if relation=='CONFLICT' else 'NATIVE_ORDER_OBSERVED')
    return {'native_symbol_id':symbol,'native_trade_side':side,'native_order_type':kind,
        'native_order_status':status,'raw_trade_data_volume':volume,'reported_executed_volume':executed,
        'native_last_update_ms':updated,'closing_order':closing,
        'recorded_gross_deal_volume':gross,'recorded_deals':sorted(unique.values(),key=lambda d:d['native_id']),
        'native_position_ids':sorted(positions),'execution_total_relation':relation,
        'observation_state':state}


@dataclass(frozen=True,init=False)
class NativeOrderObservation:
    _body_json:bytes

    def body(self):return json.loads(self._body_json)

    @classmethod
    def from_body(cls,body):
        fields={'schema','account_alias','physical_account_key','monetary_scope_hash','native_account_context',
            'native_order_id','requested_at_ms','received_at_ms','deadline_ms','connection_id','request','response',
            'native_trader_before','native_trader_after','facts','remaining_entry_allowance','position_flat',
            'cash_settled','fees_final','provider_qualified','reservation_qualified','execution_authority','source_ref'}
        if type(body) is not dict or set(body)!=fields or body['schema']!='vati.ctrader-order-observation/1':
            raise ValueError('native order observation shape invalid')
        if body['source_ref']!=canonical_hash({k:v for k,v in body.items() if k!='source_ref'}):
            raise ValueError('native order observation seal invalid')
        context=NativeAccountRiskContext(**body['native_account_context']);source=inspect_context(context);mark=source['mark']
        start=native_int(body['requested_at_ms'],minimum=0)
        end=native_int(body['received_at_ms'],minimum=start)
        native_int(body['deadline_ms'],minimum=end+1);native_int(body['connection_id'],minimum=1)
        order_id=native_int(body['native_order_id'],minimum=1);account_id=native_int(mark['native_account_id'],minimum=1)
        if (context.provider!='CTRADER' or body['account_alias']!=context.account_alias
            or body['physical_account_key']!=context.physical_account_key
            or body['monetary_scope_hash']!=context.monetary_scope_hash or source['observed_at_ms']>start
            or body['request']!={'ctidTraderAccountId':account_id,'orderId':order_id}):
            raise ValueError('native order observation scope invalid')
        for trader in (body['native_trader_before'],body['native_trader_after']):
            if (native_int(trader['ctidTraderAccountId'],minimum=1)!=account_id
                or native_int(trader['depositAssetId'],minimum=1)!=mark['deposit_asset_id']):
                raise ValueError('native order trader identity differs')
        if body['facts']!=_facts(body['response'],account_id,order_id):
            raise ValueError('native order facts differ from original response')
        if (body['remaining_entry_allowance'] is not None or body['position_flat'] is not None
            or any(body[k] is not False for k in ('cash_settled','fees_final','provider_qualified',
                'reservation_qualified','execution_authority'))):
            raise ValueError('native order snapshot cannot issue finality or authority')
        value=object.__new__(cls);object.__setattr__(value,'_body_json',canonical_json(body).encode());return value


def read_order_details(adapter,order_id,*,context,deadline_ms):
    try:
        started=native_int(adapter.clock(),minimum=0);native_int(deadline_ms,minimum=started+1)
        order_id=native_int(order_id,minimum=1)
        source=inspect_context(context);mark=source['mark']
        from vati.execution.ctrader.transport import DEMO_HOST,LIVE_HOST
        environment={DEMO_HOST:'DEMO',LIVE_HOST:'LIVE'}.get(getattr(adapter.transport,'host',None))
        if (context.provider!='CTRADER' or context.account_alias!=adapter.account_alias
            or mark['native_account_id']!=adapter.ctid_trader_account_id or environment!=mark['environment']
            or source['observed_at_ms']>started):raise ValueError('native order context unavailable')
        adapter._ensure_auth();connection=native_int(getattr(adapter.transport,'connection_id',None),minimum=1)
        native_int(adapter.clock(),minimum=started,maximum=deadline_ms-1)
        before=adapter._native_trader_identity()
        if before['depositAssetId']!=mark['deposit_asset_id'] or adapter._currency!=source['currency']:
            raise ValueError('native order monetary scope changed')
        native_int(adapter.clock(),minimum=started,maximum=deadline_ms-1)
        request={'ctidTraderAccountId':adapter.ctid_trader_account_id,'orderId':order_id}
        name,response=adapter.transport.call('ProtoOAOrderDetailsReq',request)
        if name!='ProtoOAOrderDetailsRes':raise ValueError('native order response type differs')
        facts=_facts(response,adapter.ctid_trader_account_id,order_id)
        native_int(adapter.clock(),minimum=started,maximum=deadline_ms-1)
        after=adapter._native_trader_identity();received=native_int(adapter.clock(),minimum=started,maximum=deadline_ms-1)
        if (getattr(adapter.transport,'connection_id',None)!=connection
            or after['depositAssetId']!=mark['deposit_asset_id'] or adapter._currency!=source['currency']):
            raise ValueError('native order connection or monetary scope changed')
        body={'schema':'vati.ctrader-order-observation/1','account_alias':context.account_alias,
            'physical_account_key':context.physical_account_key,'monetary_scope_hash':context.monetary_scope_hash,
            'native_account_context':asdict(context),'native_order_id':order_id,'requested_at_ms':started,
            'received_at_ms':received,'deadline_ms':deadline_ms,'connection_id':connection,
            'request':request,'response':response,'native_trader_before':before,'native_trader_after':after,'facts':facts,
            'remaining_entry_allowance':None,'position_flat':None,'cash_settled':False,'fees_final':False,
            'provider_qualified':False,'reservation_qualified':False,'execution_authority':False}
        body['source_ref']=canonical_hash(body);return NativeOrderObservation.from_body(body)
    except Exception:
        raise VenueUnavailable('cTrader original native order details unavailable; reconcile the original operation') from None
