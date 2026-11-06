"""Read the pinned native expected-margin protocol, without an order effect.

This is a current-price broker estimate. It is not a limit-price valuation,
collateral reservation, settlement proof or permission to trade.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal
from fractions import Fraction
import json

from vati.core.canonical import canonical_hash,canonical_json
from vati.core.units import Money
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.feed import native_integer
from vati.risk.account_context import inspect_context
from vati.risk.contracts import NativeAccountRiskContext

_STABLE_TRADER_FIELDS = ('ctidTraderAccountId','depositAssetId','moneyDigits',
    'leverageInCents','accountType','totalMarginCalculationType',
    'isLimitedRisk','limitedRiskMarginCalculationStrategy')
_LIMITATIONS = ['NATIVE_REQUEST_EXCLUDES_ACCORDING_TO_GSL_MARGIN']


def _exact_volume(lots, detail):
    if (type(lots) is not Decimal or not lots.is_finite() or lots<=0
            or len(lots.as_tuple().digits)>512 or abs(lots.as_tuple().exponent)>128):
        raise ValueError('original exact native quantity required')
    exact=Fraction(lots)*detail['lotSize']
    if exact.denominator!=1:raise ValueError('quantity is not representable natively')
    volume=native_integer(exact.numerator,minimum=detail['minVolume'],maximum=detail['maxVolume'])
    if volume%detail['stepVolume']:raise ValueError('quantity is not on the native volume step')
    return volume


def _validate_body(body):
    fields={'schema','account_alias','physical_account_key','monetary_scope_hash',
        'native_account_id','deposit_asset_id','currency','symbol','native_symbol_id',
        'native_contract_revision','native_contract','native_account_context','original_quantity',
        'native_volume','requested_at_ms','received_at_ms','valid_until_ms','request','response',
        'native_trader_before','native_trader_after','buy_margin','sell_margin',
        'valuation_basis','calculation_limitations','budget_denomination',
        'provider_qualified','reservation_qualified','execution_authority','source_ref'}
    if type(body) is not dict or set(body)!=fields:raise ValueError('native margin capture shape')
    if body['source_ref']!=canonical_hash({k:v for k,v in body.items() if k!='source_ref'}):
        raise ValueError('native margin capture seal')
    context=NativeAccountRiskContext(**body['native_account_context']);source=inspect_context(context)
    contract=NativeSymbolContract.from_body(body['native_contract']);scope=contract.native_scope
    detail=contract.metadata['detail'];mark=source['mark']
    start=native_integer(body['requested_at_ms'],maximum=253402300799000)
    end=native_integer(body['received_at_ms'],minimum=start,maximum=253402300799000)
    native_integer(body['valid_until_ms'],minimum=end+1,maximum=253402300799000)
    if type(body['original_quantity']) is not str or not 1<=len(body['original_quantity'])<=1024:
        raise ValueError('original quantity text capacity')
    volume=_exact_volume(Decimal(body['original_quantity']),detail)
    if (context.provider!='CTRADER' or body['account_alias']!=context.account_alias
            or body['physical_account_key']!=context.physical_account_key
            or body['monetary_scope_hash']!=context.monetary_scope_hash
            or scope['native_account_id']!=mark['native_account_id']
            or body['native_account_id']!=scope['native_account_id']
            or body['deposit_asset_id']!=mark['deposit_asset_id']
            or body['currency']!=source['currency'] or scope['environment']!=mark['environment']
            or body['symbol']!=contract.metadata['light']['symbolName']
            or body['native_symbol_id']!=scope['native_symbol_id']
            or body['native_contract_revision']!=contract.revision
            or body['native_volume']!=volume or source['observed_at_ms']>start
            or contract.received_at_ms>start):raise ValueError('original margin capture scope')
    native_integer(body['native_account_id'],minimum=1)
    native_integer(body['deposit_asset_id'],minimum=1)
    native_integer(body['native_symbol_id'],minimum=1)
    native_integer(body['native_volume'],minimum=1)
    request={'ctidTraderAccountId':body['native_account_id'],'symbolId':body['native_symbol_id'],'volume':[volume]}
    if canonical_json(body['request'])!=canonical_json(request):raise ValueError('native request mismatch')
    r=body['response'];digits=native_integer(r['moneyDigits'],maximum=18)
    from vati.execution.ctrader import SCHEMA
    payload=r.get('payloadType')
    valid_payload=(type(payload) is str and payload=='PROTO_OA_EXPECTED_MARGIN_RES'
        or type(payload) is int and payload==SCHEMA.payload_type['ProtoOAExpectedMarginRes'])
    if (set(r)-{'ctidTraderAccountId','moneyDigits','margin','payloadType'}
            or 'payloadType' in r and not valid_payload):
        raise ValueError('native response protocol mismatch')
    if (native_integer(r['ctidTraderAccountId'],minimum=1)!=body['native_account_id']
            or not isinstance(r.get('margin'),list) or len(r['margin'])!=1
            or native_integer(r['margin'][0]['volume'],minimum=1)!=volume):
        raise ValueError('native response mismatch')
    before,after=body['native_trader_before'],body['native_trader_after']
    for trader in (before,after):
        if (native_integer(trader['ctidTraderAccountId'],minimum=1)!=body['native_account_id']
                or native_integer(trader['depositAssetId'],minimum=1)!=body['deposit_asset_id']):
            raise ValueError('native trader scope mismatch')
        native_integer(trader['moneyDigits'],maximum=18)
        native_integer(trader['balance'],minimum=-(2**63))
        if 'leverageInCents' in trader:native_integer(trader['leverageInCents'],minimum=1)
    if any(canonical_json(before.get(k))!=canonical_json(after.get(k)) for k in _STABLE_TRADER_FIELDS):
        raise ValueError('native account margin semantics changed')
    for side,key in [('buy','buyMargin'),('sell','sellMargin')]:
        if set(r['margin'][0])!={'volume','buyMargin','sellMargin'}:raise ValueError('native margin row shape')
        amount=native_integer(r['margin'][0][key])
        expected=Money(amount,digits,body['currency'],body['monetary_scope_hash']).body()
        if body[side+'_margin']!=expected:raise ValueError('native margin money mismatch')
    if (body['schema']!='vati.ctrader-expected-margin/1'
            or body['valuation_basis']!='NATIVE_CURRENT_PRICE_ESTIMATE_NO_ORDER_PRICE_INPUT'
            or body['calculation_limitations']!=_LIMITATIONS
            or body['budget_denomination']!='ACCOUNT_MONETARY_SCOPE_NOT_PAYMENT_ASSET_OR_CONVERSION_PROOF'
            or any(body[k] is not False for k in ('provider_qualified','reservation_qualified','execution_authority'))):
        raise ValueError('native estimate cannot issue qualification or authority')


@dataclass(frozen=True,init=False)
class ExpectedMarginObservation:
    _body_json: bytes

    def body(self):return json.loads(self._body_json)

    @classmethod
    def from_body(cls,body):
        _validate_body(body)
        value=object.__new__(cls)
        object.__setattr__(value,'_body_json',canonical_json(body).encode())
        return value


def read_expected_margin(adapter,symbol,lots,*,context,deadline_ms):
    """Bind original quantity, native account/asset, symbol and connection."""
    try:
        started=native_integer(adapter.clock(),maximum=253402300799000)
        native_integer(deadline_ms,minimum=started+1,maximum=253402300799000)
        if (type(lots) is not Decimal or not lots.is_finite() or lots<=0
                or len(lots.as_tuple().digits)>512 or abs(lots.as_tuple().exponent)>128
                or not isinstance(symbol,str) or not 1<=len(symbol)<=256):
            raise ValueError('original exact native quantity required')
        source=inspect_context(context)
        if (context.provider!='CTRADER' or context.account_alias!=adapter.account_alias
                or source['observed_at_ms']>started):raise ValueError('native account source invalid')
        adapter._ensure_auth()
        connection=getattr(adapter.transport,'connection_id',None)
        native_integer(connection,minimum=1)
        spec=adapter.symbol(symbol)
        contract=spec.native_contract
        if type(contract) is not NativeSymbolContract or contract.received_at_ms>started:
            raise ValueError('original native contract unavailable')
        scope=contract.native_scope;mark=source['mark']
        if (scope['native_account_id']!=adapter.ctid_trader_account_id
                or mark['native_account_id']!=scope['native_account_id']
                or scope['transport_host']!=getattr(adapter.transport,'host',None)
                or scope['environment']!=mark['environment']
                or scope['native_symbol_id']!=spec.symbol_id or spec.contract_revision!=contract.revision):
            raise ValueError('original native account/symbol scope changed')
        detail=contract.metadata['detail']
        if (spec.name!=contract.metadata['light']['symbolName'] or spec.digits!=detail['digits']
                or any(getattr(spec,field)!=detail[key] for field,key in (
                ('lot_size_cents','lotSize'),('min_volume','minVolume'),
                ('step_volume','stepVolume'),('max_volume','maxVolume')))):
            raise ValueError('native volume metadata changed')
        volume=_exact_volume(lots,detail)
        before=adapter._native_trader_identity()
        currency=adapter._currency
        if before['depositAssetId']!=mark['deposit_asset_id'] or currency!=source['currency']:
            raise ValueError('native deposit asset changed')
        request={'ctidTraderAccountId':adapter.ctid_trader_account_id,'symbolId':spec.symbol_id,'volume':[volume]}
        name,response=adapter.transport.call('ProtoOAExpectedMarginReq',request)
        if (name!='ProtoOAExpectedMarginRes' or not isinstance(response,dict)
                or native_integer(response['ctidTraderAccountId'],minimum=1)!=adapter.ctid_trader_account_id
                or not isinstance(response.get('margin'),list) or len(response['margin'])!=1):
            raise ValueError('native expected margin response mismatch')
        digits=native_integer(response['moneyDigits'],maximum=18)
        row=response['margin'][0]
        if native_integer(row['volume'],minimum=1)!=volume:raise ValueError('native quoted volume mismatch')
        buy=native_integer(row['buyMargin']);sell=native_integer(row['sellMargin'])
        after=adapter._native_trader_identity()
        received=native_integer(adapter.clock(),minimum=started,maximum=deadline_ms-1)
        if (not adapter._auth_is_current() or connection!=getattr(adapter.transport,'connection_id',None)
                or adapter._currency!=currency or after['depositAssetId']!=before['depositAssetId']
                or after.get('leverageInCents')!=before.get('leverageInCents')):
            raise ValueError('native connection, asset or leverage changed during quote')
        body={'schema':'vati.ctrader-expected-margin/1','account_alias':context.account_alias,
            'physical_account_key':context.physical_account_key,'monetary_scope_hash':context.monetary_scope_hash,
            'native_account_id':adapter.ctid_trader_account_id,'deposit_asset_id':before['depositAssetId'],
            'currency':currency,'symbol':spec.name,'native_symbol_id':spec.symbol_id,
            'native_contract_revision':contract.revision,'native_contract':contract.body(),
            'native_account_context':asdict(context),'original_quantity':str(lots),'native_volume':volume,
            'requested_at_ms':started,'received_at_ms':received,'valid_until_ms':deadline_ms,
            'request':request,'response':response,'native_trader_before':before,'native_trader_after':after,
            'buy_margin':Money(buy,digits,currency,context.monetary_scope_hash).body(),
            'sell_margin':Money(sell,digits,currency,context.monetary_scope_hash).body(),
            'valuation_basis':'NATIVE_CURRENT_PRICE_ESTIMATE_NO_ORDER_PRICE_INPUT',
            'calculation_limitations':_LIMITATIONS,
            'budget_denomination':'ACCOUNT_MONETARY_SCOPE_NOT_PAYMENT_ASSET_OR_CONVERSION_PROOF',
            'provider_qualified':False,'reservation_qualified':False,'execution_authority':False}
        body['source_ref']=canonical_hash(body)
        return ExpectedMarginObservation.from_body(body)
    except (KeyError,TypeError,ValueError,ArithmeticError,AttributeError):
        raise VenueUnavailable('cTrader original expected-margin scope, precision, quantity or deadline unavailable') from None
