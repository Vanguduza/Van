"""Original cTrader commission units, not a complete future fee obligation.

Only the existing margin owner may resolve the durable contract vintage. These
terms preserve absent fields and native asset identities. A conditional native
commission calculation is neither a worst-case reservation nor settlement.
"""
from dataclasses import dataclass
from fractions import Fraction
import json

from vati.core.canonical import canonical_json,canonical_hash
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.feed import native_integer

TYPES={1:('USD_PER_MILLION_USD','USD_TURNOVER',10**8),
       2:('USD_PER_LOT','NATIVE_LOTS',10**8),
       3:('PERCENTAGE_OF_VALUE','QUOTE_TURNOVER_PERCENT',10**5),
       4:('QUOTE_CCY_PER_LOT','NATIVE_LOTS',10**8)}
EXTRA=('pnlConversionFeeRate','swapLong','swapShort','swapCalculationType',
       'swapPeriod','swapTime','skipSWAPPeriods','chargeSwapAtWeekends',
       'rolloverCommission','skipRolloverDays','rolloverCommission3Days','gslCharge','distanceSetIn')


class NativeFeeTermsError(ValueError):pass


def _fraction(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def _optional_integer(detail,key,*,minimum=-(2**63),maximum=2**63-1):
    if key not in detail:return None
    return native_integer(detail[key],minimum=minimum,maximum=maximum)


@dataclass(frozen=True,init=False)
class NativeCommissionTerms:
    _body_json:bytes

    def __init__(self,contract):
        try:
            if type(contract)is not NativeSymbolContract:
                raise ValueError('original typed native contract required')
            meta=contract.metadata;detail=meta['detail'];light=meta['light']
            kind=_optional_integer(detail,'commissionType',minimum=1,maximum=2**31-1)
            raw=_optional_integer(detail,'preciseTradingCommissionRate')
            minimum=_optional_integer(detail,'preciseMinCommission')
            minimum_kind=_optional_integer(detail,'minCommissionType',minimum=1,maximum=2**31-1)
            asset=detail.get('minCommissionAsset')
            if asset is not None and (type(asset)is not str or not 1<=len(asset)<=64
                    or asset!=asset.strip() or any(ord(c)<33 or ord(c)>126 for c in asset)):
                raise ValueError('native minimum commission asset invalid')
            quote=_optional_integer(light,'quoteAssetId',minimum=1)
            missing=[key for key in ('commissionType','preciseTradingCommissionRate',
                'preciseMinCommission','minCommissionType') if key not in detail]
            if minimum_kind==1 and asset is None:missing.append('minCommissionAsset')
            if minimum_kind==2 and quote is None:missing.append('quoteAssetId')
            known=kind in TYPES and minimum_kind in (1,2)
            state='NATIVE_TERMS_OBSERVED' if known and not missing else 'NATIVE_TERMS_INCOMPLETE'
            if (kind is not None and kind not in TYPES) or (minimum_kind is not None and minimum_kind not in (1,2)):
                state='NATIVE_TERMS_UNSUPPORTED'
            rate=None
            if kind in TYPES and raw is not None:
                name,unit,scale=TYPES[kind]
                rate={'type':name,'native_type':kind,'raw_precise_rate':raw,
                      'amount':_fraction(Fraction(raw,scale)),'unit':unit}
            minimum_terms=None
            if minimum is not None:
                minimum_terms={'raw_precise_minimum':minimum,'amount':_fraction(Fraction(minimum,10**8)),
                    'native_type':minimum_kind,'currency_label':asset if minimum_kind==1 else None,
                    'native_quote_asset_id':quote if minimum_kind==2 else None}
            body={'schema':'vati.native-commission-terms/1','native_scope':contract.native_scope,
                'native_contract_revision':contract.revision,'captured_at_ms':contract.received_at_ms,
                'lot_size_in_native_cents':detail['lotSize'],'native_quote_asset_id':quote,
                'state':state,'missing_fields':missing,'rate':rate,'minimum':minimum_terms,
                'other_native_cost_fields':{key:detail[key] for key in EXTRA if key in detail},
                'other_cost_field_presence':{key:key in detail for key in EXTRA},
                'raw_fields':{key:detail[key] for key in ('commission','commissionType',
                    'preciseTradingCommissionRate','minCommission','preciseMinCommission',
                    'minCommissionType','minCommissionAsset') if key in detail},
                'scale_basis':'PINNED_NATIVE_PROTO_PRECISE_FIELDS_NO_DEPRECATED_FALLBACK',
                'native_sign_convention_qualified':False,'charge_count_bound':None,
                'complete_future_obligation':False,'reservation_qualified':False,
                'execution_authority':False,'settlement_qualified':False}
            object.__setattr__(self,'_body_json',canonical_json(body).encode())
        except (KeyError,TypeError,ValueError,ArithmeticError):
            raise NativeFeeTermsError('NATIVE_COMMISSION_TERMS_INVALID') from None

    def body(self):return json.loads(self._body_json)

    def one_charge(self,*,native_volume,usd_turnover=None,quote_turnover=None):
        """Conditional exact commission before minimum/conversion/financing.

        Turnover arguments are explicit rational *scenario inputs*, not native
        observed FX, executed price or permission to consume account assets.
        """
        body=self.body();rate=body['rate']
        if rate is None:raise NativeFeeTermsError('NATIVE_COMMISSION_RATE_UNAVAILABLE')
        native_integer(native_volume,minimum=1)
        raw=rate['raw_precise_rate']
        if raw<0:raise NativeFeeTermsError('NATIVE_COMMISSION_SIGN_CONVENTION_UNQUALIFIED')
        kind=rate['native_type'];amount=Fraction(raw,TYPES[kind][2])
        scenario=None
        if kind in (2,4):
            cost=amount*Fraction(native_volume,body['lot_size_in_native_cents'])
        else:
            turnover=usd_turnover if kind==1 else quote_turnover
            if type(turnover)is not Fraction or turnover<=0 or turnover.numerator.bit_length()>4096 or turnover.denominator.bit_length()>4096:
                raise NativeFeeTermsError('EXPLICIT_EXACT_COMMISSION_SCENARIO_TURNOVER_REQUIRED')
            scenario={'turnover':_fraction(turnover),'denomination':'USD' if kind==1 else 'EXPLICIT_QUOTE_TURNOVER_SCENARIO',
                'native_price_or_fx_qualified':False}
            cost=amount*turnover/(1000000 if kind==1 else 100)
        minimum=body['minimum'];adjusted=None;minimum_state='NATIVE_MINIMUM_UNAVAILABLE'
        if minimum is not None:
            raw_minimum=minimum['raw_precise_minimum']
            if raw_minimum<0:
                minimum_state='NATIVE_MINIMUM_SIGN_CONVENTION_UNQUALIFIED'
            elif raw_minimum==0:
                adjusted=cost;minimum_state='EXPLICIT_NATIVE_ZERO_MINIMUM'
            elif ((kind in (1,2) and minimum['native_type']==1 and minimum['currency_label']=='USD')
                  or (kind in (3,4) and minimum['native_type']==2
                      and minimum['native_quote_asset_id'] is not None)):
                adjusted=max(cost,Fraction(raw_minimum,10**8));minimum_state='APPLIED_SAME_NATIVE_DENOMINATION'
            else:minimum_state='NATIVE_MINIMUM_ASSET_MAPPING_OR_CONVERSION_UNAVAILABLE'
        return {'schema':'vati.conditional-native-commission/1','native_contract_revision':body['native_contract_revision'],
            'terms_hash':canonical_hash(body),'native_volume':native_volume,'amount':_fraction(cost),
            'scenario_inputs':scenario,'native_value_basis_qualified':False,
            'denomination':'USD' if kind in (1,2) else 'NATIVE_QUOTE_ASSET',
            'native_quote_asset_id':body['native_quote_asset_id'] if kind in (3,4) else None,
            'basis':'ONE_SCENARIO_CHARGE_BEFORE_MINIMUM_CONVERSION_FINANCING_OTHER_COSTS',
            'minimum_state':minimum_state,'minimum_adjusted_amount':None if adjusted is None else _fraction(adjusted),
            'worst_case_fee':None,'complete_future_obligation':False,
            'reservation_qualified':False,'execution_authority':False}


def original_entry_commission_terms(book,command_hash,source_ref):
    from vati.core.ledger import committed_source_snapshot
    with committed_source_snapshot(book.ledger):
        original=book.lookup_entry(command_hash,source_ref)
        if original is None:return None
        quote=original['observation'];receipt=original['receipt']
        if quote['schema']!='vati.ctrader-expected-margin/1':
            return {'schema':'vati.original-entry-fee-terms/1','state':'PROVIDER_FEE_TERMS_UNAVAILABLE',
                'entry_record_ref':receipt['record_ref'],'source_ref':source_ref,
                'command_hash':command_hash,'complete_future_obligation':False,
                'reservation_qualified':False,'execution_authority':False}
        terms=NativeCommissionTerms(NativeSymbolContract.from_body(quote['native_contract'])).body()
        return {'schema':'vati.original-entry-fee-terms/1','state':terms['state'],
            'entry_record_ref':receipt['record_ref'],'source_ref':source_ref,'command_hash':command_hash,
            'original_input_ref':receipt['original_input_ref'],'available_at_ms':receipt['available_at_ms'],
            'quote_valid_until_ms':quote['valid_until_ms'],'terms':terms,
            'complete_future_obligation':False,'reservation_qualified':False,'execution_authority':False}
