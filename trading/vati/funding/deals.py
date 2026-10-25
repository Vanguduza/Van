"""Complete, native-scoped deal observations for balance reconciliation.

Native closing balances/versions are facts, not inferred net trade settlement.
The published timestamp API has no ID cursor. Saturated millisecond windows are
therefore refused instead of dropping same-time deals at a page boundary.
"""
from dataclasses import dataclass
from decimal import Decimal
from vati.core.canonical import canonical_hash
from vati.execution.base import VenueUnavailable
from vati.funding.native import native_int,native_money

@dataclass(frozen=True)
class NativeCloseBalance:
    entry_price: Decimal
    gross_profit: Decimal
    swap: Decimal
    commission: Decimal
    balance_after: Decimal
    money_digits: int
    pnl_conversion_fee: Decimal | None
    balance_version: int | None
    closed_volume_cents: int | None

    def body(self):
        return {k:str(v) if isinstance(v,Decimal) else v for k,v in vars(self).items()}

@dataclass(frozen=True)
class NativeDeal:
    native_id: int
    order_id: int
    position_id: int
    symbol_id: int
    occurred_at_ms: int
    status: str
    requested_volume_cents: int
    filled_volume_cents: int
    execution_price: Decimal | None
    commission: Decimal | None
    money_digits: int | None
    close: NativeCloseBalance | None

    def body(self):
        return {k:(str(v) if isinstance(v,Decimal) else v.body() if isinstance(v,NativeCloseBalance) else v) for k,v in vars(self).items()}

@dataclass(frozen=True)
class NativeDealStatement:
    provider: str
    environment: str
    account_alias: str
    native_account_id: int
    deposit_asset_id: int
    currency: str
    from_ms: int
    to_ms: int
    observed_at_ms: int
    deals: tuple[NativeDeal,...]
    request_count: int

    @property
    def scope_hash(self):
        return canonical_hash({k:getattr(self,k) for k in ('provider','environment','native_account_id','deposit_asset_id','currency')})

    def body(self):
        return {'schema':'native-deal-statement/1',**{k:getattr(self,k) for k in ('provider','environment','account_alias','native_account_id','deposit_asset_id','currency','from_ms','to_ms','observed_at_ms','request_count')},
            'deals':[row.body() for row in self.deals]}

    @classmethod
    def from_body(cls,body):
        fields={'schema','provider','environment','account_alias','native_account_id','deposit_asset_id','currency','from_ms','to_ms','observed_at_ms','request_count','deals'}
        if not isinstance(body,dict) or set(body)!=fields or body['schema']!='native-deal-statement/1' or not isinstance(body['deals'],list):
            raise ValueError('native_deal_statement_format_invalid')
        def amount(value):
            if not isinstance(value,str) or not 1<=len(value)<=128:raise ValueError('native_deal_amount_format_invalid')
            value=Decimal(value)
            if not value.is_finite():raise ValueError('native_deal_amount_format_invalid')
            return value
        rows=[]
        deal_fields=set(NativeDeal.__dataclass_fields__);close_fields=set(NativeCloseBalance.__dataclass_fields__)
        for row in body['deals']:
            if not isinstance(row,dict) or set(row)!=deal_fields:raise ValueError('native_deal_statement_format_invalid')
            close=row['close']
            if close is not None:
                if not isinstance(close,dict) or set(close)!=close_fields:raise ValueError('native_deal_statement_format_invalid')
                close=NativeCloseBalance(**{k:(amount(v) if k in {'entry_price','gross_profit','swap','commission','balance_after'} or k=='pnl_conversion_fee' and v is not None else v) for k,v in close.items()})
            rows.append(NativeDeal(**{k:(close if k=='close' else amount(v) if k in {'execution_price','commission'} and v is not None else v) for k,v in row.items()}))
        return cls(**{k:(tuple(rows) if k=='deals' else v) for k,v in body.items() if k!='schema'})

def _price(value):
    if type(value) not in (int,float):raise ValueError('native_price_invalid')
    result=Decimal(str(value))
    if not result.is_finite() or result<=0:raise ValueError('native_price_invalid')
    return result

def _deal(raw,lo,hi):
    from vati.execution.ctrader.protoschema import SCHEMA
    if not isinstance(raw,dict):raise ValueError('native_deal_invalid')
    fields=[native_int(raw[k],minimum=1) for k in ('dealId','orderId','positionId','symbolId')]
    at=native_int(raw['executionTimestamp'],minimum=lo,maximum=hi)
    native_int(raw['createTimestamp'],minimum=0,maximum=at)
    requested=native_int(raw['volume'],minimum=0);filled=native_int(raw['filledVolume'],minimum=0,maximum=requested)
    status=raw['dealStatus']
    if type(status) is int:
        native_int(status,minimum=0,maximum=2**31-1)
        status=SCHEMA.enum_reverse['ProtoOADealStatus'].get(status,'NATIVE_UNKNOWN:'+str(status))
    elif not isinstance(status,str) or status not in SCHEMA.enums['ProtoOADealStatus']:raise ValueError('native_deal_status_invalid')
    digits=native_int(raw['moneyDigits'],minimum=0,maximum=18) if 'moneyDigits' in raw else None
    commission=None
    if 'commission' in raw:
        if digits is None:raise ValueError('native_deal_precision_unknown')
        commission=native_money(raw['commission'],digits)
    price=_price(raw['executionPrice']) if 'executionPrice' in raw else None
    if filled and (price is None or status not in {'FILLED','PARTIALLY_FILLED'}):raise ValueError('native_fill_invalid')
    close=None
    if 'closePositionDetail' in raw:
        detail=raw['closePositionDetail']
        if not filled or not isinstance(detail,dict):raise ValueError('native_close_invalid')
        exponent=native_int(detail['moneyDigits'],minimum=0,maximum=18)
        close=NativeCloseBalance(_price(detail['entryPrice']),*[native_money(detail[key],exponent) for key in ('grossProfit','swap','commission','balance')],exponent,
            native_money(detail['pnlConversionFee'],exponent) if 'pnlConversionFee' in detail else None,
            native_int(detail['balanceVersion'],minimum=0) if 'balanceVersion' in detail else None,
            native_int(detail['closedVolume'],minimum=0,maximum=filled) if 'closedVolume' in detail else None)
    return NativeDeal(*fields,at,status,requested,filled,price,commission,digits,close)

def collect_native_deals(adapter,*,from_ms,to_ms):
    from vati.execution.ctrader.transport import DEMO_HOST,LIVE_HOST,CtraderApiError
    try:
        started=native_int(adapter.clock(),minimum=0)
        native_int(from_ms,minimum=0);native_int(to_ms,minimum=0,maximum=2147483646000)
        native_int(adapter.ctid_trader_account_id,minimum=1)
        environment={DEMO_HOST:'DEMO',LIVE_HOST:'LIVE'}.get(getattr(adapter.transport,'host',None))
        if environment is None or from_ms>to_ms or to_ms>started or to_ms-from_ms>604800000:raise ValueError()
    except (TypeError,ValueError):raise VenueUnavailable('cTrader deals require an exact closed past window of at most one week') from None
    adapter._authenticate()
    try:
        original=adapter._native_trader_identity();currency=adapter._currency
        if 'registrationTimestamp' in original and from_ms<native_int(original['registrationTimestamp'],minimum=0):raise ValueError()
        pending=[(from_ms,to_ms)];seen={};leaves={};requests=0
        while pending:
            lo,hi=pending.pop();requests+=1
            if requests>128:raise ValueError('native_deal_page_budget_exceeded')
            name,response=adapter.transport.call('ProtoOADealListReq',{'ctidTraderAccountId':adapter.ctid_trader_account_id,
                'fromTimestamp':lo,'toTimestamp':hi,'maxRows':1000})
            if (name!='ProtoOADealListRes' or type(response['ctidTraderAccountId']) is not int
                or response['ctidTraderAccountId']!=adapter.ctid_trader_account_id or type(response['hasMore']) is not bool):raise ValueError()
            raw_rows=response.get('deal',[])
            if not isinstance(raw_rows,list) or len(raw_rows)>1000:raise ValueError()
            rows=[_deal(row,lo,hi) for row in raw_rows]
            for row in rows:
                if row.native_id in seen and seen[row.native_id]!=row:raise ValueError('native_deal_history_changed_during_read')
                seen[row.native_id]=row
            if len(seen)>64000:raise ValueError('native_deal_fact_budget_exceeded')
            if response['hasMore']:
                if lo==hi:raise ValueError('native_same_millisecond_page_saturated')
                mid=(lo+hi)//2;pending.extend([(mid+1,hi),(lo,mid)])
            else:
                leaves.update((row.native_id,row) for row in rows)
        if set(seen)!=set(leaves):raise ValueError('native_deal_history_incomplete_after_page_split')
        latest=adapter._native_trader_identity()
        if latest['depositAssetId']!=original['depositAssetId'] or adapter._currency!=currency:raise ValueError()
        at=native_int(adapter.clock(),minimum=started)
        # Native IDs sort only the immutable document, not economic chronology.
        return NativeDealStatement('CTRADER',environment,adapter.account_alias,adapter.ctid_trader_account_id,
            original['depositAssetId'],currency,from_ms,to_ms,at,tuple(leaves[k] for k in sorted(leaves)),requests)
    except (CtraderApiError,KeyError,TypeError,ValueError,ArithmeticError):
        raise VenueUnavailable('cTrader complete native deal history, identity or precision unavailable') from None
