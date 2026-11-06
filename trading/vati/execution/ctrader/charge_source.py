"""Recorded native commission provenance, outside legacy receipt seal bodies.

The raw signed component and its own scale are preserved. The scalar receipt
retains its existing magnitude convention; neither value is complete fees,
cash reconciliation, a qualified rebate convention or settlement finality.
"""
from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction

from vati.core.canonical import canonical_hash,canonical_json
from vati.funding.native import native_int
from vati.risk.arithmetic import fraction

SCHEMA='vati.ctrader-recorded-charge/1'


def execution_ref(receipt):
    body=asdict(receipt) if not isinstance(receipt,dict) else receipt
    from vati.execution.base import ExecutionReceipt
    names=set(ExecutionReceipt.__dataclass_fields__)-{'receipt_hash','received_time_unix_ms'}
    return canonical_hash({k:v for k,v in body.items() if k in names})


def _commission(raw,digits):
    if type(raw) is not int or not -(2**63)<=raw<2**63 or type(digits) is not int or not 0<=digits<=18:
        return None
    return Decimal((0,tuple(map(int,str(abs(raw)))),-digits))


def _fraction(value):
    if type(value) is str:
        if not 1<=len(value)<=512:raise ValueError('native recorded charge amount capacity')
        value=Decimal(value)
    return fraction(value)


def validate_charge_source(body,receipt,*,account_alias,closing):
    p=asdict(receipt) if not isinstance(receipt,dict) else receipt
    names={'schema','account_alias','native_account_id','closing','execution_ref','captured_at_ms',
        'native_deal_id','native_order_id','native_position_id','native_symbol_id','filled_volume_cents',
        'lot_size_cents','execution_price','raw_commission','money_digits','recorded_fee',
        'fees_final','cash_reconciled','source_ref'}
    if (type(body) is not dict or set(body)!=names or body['schema']!=SCHEMA
            or len(canonical_json(body).encode())>16384
            or body['source_ref']!=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
            or body['execution_ref']!=execution_ref(p) or body['account_alias']!=account_alias
            or type(body['closing']) is not bool or body['closing'] is not closing
            or body['fees_final'] is not False or body['cash_reconciled'] is not False
            or p['venue']!='ctrader' or p['status'] not in {'FILLED','PARTIAL'}):
        raise ValueError('native recorded charge source binding unavailable')
    for key in ('native_account_id','native_deal_id','native_order_id','native_position_id',
                'native_symbol_id','filled_volume_cents','lot_size_cents'):
        native_int(body[key],minimum=1)
    captured=native_int(body['captured_at_ms'],minimum=0)
    received=p['received_time_unix_ms']
    if received is not None and (type(received) is not int or received<captured):
        raise ValueError('native recorded charge source availability differs')
    if (str(body['native_order_id'])!=p['broker_order_id'] or str(body['native_position_id'])!=p['broker_position_id']
            or Fraction(body['filled_volume_cents'],body['lot_size_cents'])!=_fraction(p['filled_qty'])
            or _fraction(body['execution_price'])!=_fraction(p['average_fill'])):
        raise ValueError('native recorded charge execution differs')
    raw=body['raw_commission'];digits=body['money_digits']
    if raw is not None and (type(raw) is not int or not -(2**63)<=raw<2**63):
        raise ValueError('native recorded charge integer invalid')
    if digits is not None:native_int(digits,minimum=0,maximum=18)
    fee=_commission(raw,digits)
    if ((None if fee is None else str(fee))!=body['recorded_fee']
            or (p['fees'] is None)!=(fee is None)
            or fee is not None and _fraction(p['fees'])!=fraction(fee)):
        raise ValueError('native recorded charge scalar differs')
    return body


def capture_charge_source(receipt,deal,symbol,*,account_alias,native_account_id,closing):
    raw=deal.get('commission');digits=deal.get('moneyDigits')
    if type(raw) is not int or not -(2**63)<=raw<2**63:raw=None
    if type(digits) is not int or not 0<=digits<=18:digits=None
    fee=_commission(raw,digits)
    body={'schema':SCHEMA,'account_alias':account_alias,'native_account_id':native_account_id,
        'closing':closing,'execution_ref':execution_ref(receipt),'captured_at_ms':receipt.received_time_unix_ms,
        'native_deal_id':deal['dealId'],'native_order_id':deal['orderId'],'native_position_id':deal['positionId'],
        'native_symbol_id':deal['symbolId'],'filled_volume_cents':deal['filledVolume'],
        'lot_size_cents':symbol.lot_size_cents,'execution_price':str(receipt.average_fill),
        'raw_commission':raw,'money_digits':digits,'recorded_fee':None if fee is None else str(fee),
        'fees_final':False,'cash_reconciled':False}
    body['source_ref']=canonical_hash(body)
    return validate_charge_source(body,receipt,account_alias=account_alias,closing=closing)


def receipt_charge_evidence(adapter,receipt):
    """Capture only an actual CTrader adapter observation; never a scalar echo."""
    from vati.execution.ctrader.adapter import CtraderAdapter
    if not isinstance(adapter,CtraderAdapter):return {}
    try:
        source=adapter.recorded_native_charge(receipt)
        return {} if source is None else {'recorded_native_charge':source}
    except (KeyError,TypeError,ValueError,ArithmeticError):
        return {}  # A provenance problem must not discard a real native fill.
