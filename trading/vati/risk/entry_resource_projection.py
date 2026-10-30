"""Exact projected resource burdens, before admission of a reservation.

Margin quotes exclude fees. These values cannot close the complete obligation
or authorize a native submission. The financial writer must preserve that
unknown, admit current shared policy and reconcile existing obligations.
"""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import json

from vati.core import EventKind
from vati.core.canonical import canonical_json
from vati.core.ledger import committed_source_snapshot,require_committed_source_read
from vati.core.units import Money
from vati.funding.native import native_int
from vati.risk.arithmetic import fraction,exact_loss_amount
from vati.risk.authority import MARGIN_FLOOR_LEVEL_PCT
from vati.risk.current_entry_source import current_entry_source
from vati.risk.account_context import inspect_context
from vati.risk.heat import exact_open_stop_risk,exact_currency_leg_intervals
from vati.risk.contracts import Direction
from vati.risk.mandate_source import validate_mandate_source
from vati.risk.margin import exact_cash_margin_bounds
from vati.risk.native_margin_book import NativeMarginBook
from vati.risk.pending import pending_risk_losses,validate_valuation_contract
from vati.risk.serde import snapshot_from_dict


class EntryResourceError(ValueError):pass


@dataclass(frozen=True,init=False)
class EntryResourceProjection:
    _body_json:bytes
    def body(self):return json.loads(self._body_json)


def project_entry_resources(ledger,command,entry_margin_ref,current_risk_ref,mandate_source,*,at_ms):
    """Read original sources; round burdens up and capacity down exactly."""
    require_committed_source_read(ledger)
    try:
        with committed_source_snapshot(ledger):
            source=current_entry_source(ledger,command,entry_margin_ref,current_risk_ref,available_at_ms=at_ms).body()
            native_int(mandate_source['captured_at_ms'],minimum=0,maximum=at_ms)
            policy=validate_mandate_source(mandate_source,decision_time_ms=mandate_source['captured_at_ms'],
                expected_hash=source['decision']['mandate_hash']).body()
            if source['risk_state']!='SUFFICIENT':raise EntryResourceError('CURRENT_RISK_REFUSED')
            if (policy['account_alias']!=command.account_alias or policy['venue']!=command.venue
                    or command.symbol.upper() not in policy['instruments']
                    or command.strategy_id not in policy['allowed_strategies']):
                raise EntryResourceError('SIGNED_RESOURCE_POLICY_SCOPE_MISMATCH')
            facts=snapshot_from_dict(source['snapshot']);context=facts.native_account_context
            bound=next(e for e in ledger.iter(EventKind.SESSION) if e.hash==entry_margin_ref)
            quote=NativeMarginBook(ledger).lookup_entry(command.command_hash,bound.payload['source_ref'])['observation']
            if context.provider=='MT5':digits=quote['reported_currency_digits']
            else:digits=quote['native_trader_after']['moneyDigits']
            if type(digits)is not int or not 0<=digits<=18:raise EntryResourceError('NATIVE_CURRENCY_DIGITS_UNAVAILABLE')
            money=Money.from_body(source['estimate_money'])
            if money.asset_ref!=context.monetary_scope_hash or money.currency!=facts.symbol_contract.account_currency:
                raise EntryResourceError('RESOURCE_MONETARY_SCOPE_MISMATCH')
            original=next(e for e in ledger.iter(EventKind.RISK_DECISION) if e.hash==source['original_risk_ref'])
            before=snapshot_from_dict(original.payload['inputs']['snapshot'])
            validate_valuation_contract(before.symbol_contract,facts.symbol_contract)
            loss=max(exact_loss_amount(command.quantity,c,entry=command.entry_price,stop=command.protective_stop)
                for c in (before.symbol_contract,facts.symbol_contract))
            original_limit=fraction(before.equity)*fraction(Decimal(original.payload['decision']['approved_risk_pct']))
            current_limit=fraction(facts.equity)*fraction(Decimal(source['decision']['approved_risk_pct']))
            selected_risk=fraction(Decimal(policy['max_risk_per_trade']))
            if command.strategy_id in policy['strategy_risk_budgets']:
                selected_risk=min(selected_risk,fraction(Decimal(policy['strategy_risk_budgets'][command.strategy_id])))
            signed_limit=min(fraction(before.equity),fraction(facts.equity))*selected_risk
            if loss>min(original_limit,current_limit,signed_limit):raise EntryResourceError('COMMAND_EXCEEDS_ORIGINAL_OR_CURRENT_LOSS_BUDGET')
            free,level=exact_cash_margin_bounds(facts.equity,facts.used_margin,facts.free_margin,facts.margin_level_pct)
            if free is None or facts.used_margin is None:raise EntryResourceError('NATIVE_COLLATERAL_UNAVAILABLE')
            scale=10**digits
            down=lambda value:Fraction((value*scale).__floor__(),scale)
            up=lambda value:Fraction(-((-value*scale).__floor__()),scale)
            capital=down(fraction(facts.equity));original_used=fraction(facts.used_margin)
            if original_used<0:raise EntryResourceError('NATIVE_MARGIN_LIABILITY_INVALID')
            used=up(original_used);floor=fraction(MARGIN_FLOOR_LEVEL_PCT)/100
            if context.provider=='MT5':
                mark=inspect_context(context)['mark']
                capital=min(capital,down(fraction(Decimal(mark['reported_equity'])))-up(fraction(Decimal(mark['credit']))))
            free=min(free,capital-used)
            if original_used>0:
                if level is None:raise EntryResourceError('NATIVE_MARGIN_LEVEL_UNAVAILABLE')
                capital=min(capital,original_used*level/100)
            pending_losses=pending_risk_losses(facts)
            pending=sum((v for _,v in pending_losses),Fraction(0))
            heat=exact_open_stop_risk(facts.open_positions,facts.equity,additional_loss=pending)
            if heat is None:raise EntryResourceError('EXISTING_STOP_RISK_UNMEASURED')
            capacities={'free_cash':free,'margin_floor_equity':capital-used*floor,
                'stop_risk':fraction(facts.equity)*(fraction(Decimal(policy['max_open_stop_risk']))-heat)}
            def quantized(value,*,up=False,strict=False):
                if value<0:raise EntryResourceError('NATIVE_RESOURCE_CAPACITY_NEGATIVE')
                atoms=value*10**digits
                ceil=-(-atoms.numerator//atoms.denominator)
                minor=ceil-1 if strict else ceil if up else atoms.numerator//atoms.denominator
                if minor<0:raise EntryResourceError('NATIVE_RESOURCE_CAPACITY_UNAVAILABLE')
                return Money(minor,digits,money.currency,money.asset_ref).body()
            required_margin=Money.from_body(quantized(money.fraction,up=True)).fraction
            burdens={'free_cash':required_margin,'margin_floor_equity':required_margin*floor,'stop_risk':loss}
            intervals=exact_currency_leg_intervals(facts.open_positions,pending_losses=pending_losses)
            if intervals is None:raise EntryResourceError('EXISTING_CURRENCY_LEG_RISK_UNMEASURED')
            leg_limit=fraction(facts.equity)*fraction(Decimal(policy['max_currency_leg_exposure']))
            sign=1 if command.direction is Direction.LONG else -1
            entry_legs={}
            for ccy,value in ((facts.symbol_contract.base_currency,sign*loss),
                              (facts.symbol_contract.quote_currency,-sign*loss)):
                entry_legs[ccy]=entry_legs.get(ccy,Fraction(0))+value
            for ccy in sorted(set(intervals)|set(entry_legs)):
                low,high=intervals.get(ccy,(Fraction(0),Fraction(0)))
                value=entry_legs.get(ccy,Fraction(0))
                for side,required,capacity in (('up',max(Fraction(0),value),leg_limit-high),
                                               ('down',max(Fraction(0),-value),leg_limit+low)):
                    name='currency_leg_'+side+':'+ccy
                    burdens[name]=required;capacities[name]=capacity
            symbols={p.symbol.upper() for p in facts.open_positions}
            symbols.update(p.contract.symbol.upper() for p,_ in pending_losses)
            symbols.add(command.symbol.upper())
            slot_capacities={'account':policy['max_total_positions']-len(facts.open_positions)
                -sum(p.new_position_slots for p,_ in pending_losses)}
            for symbol in sorted(symbols):
                slot_capacities['instrument:'+symbol]=policy['max_positions_per_instrument']\
                    -sum(p.symbol.upper()==symbol for p in facts.open_positions)\
                    -sum(p.new_position_slots for p,_ in pending_losses if p.contract.symbol.upper()==symbol)
            if any(type(v)is not int or v<0 for v in slot_capacities.values()):
                raise EntryResourceError('EXISTING_POSITION_SLOT_CAPACITY_UNAVAILABLE')
            body={'schema':'vati.entry-resource-projection/1','command_hash':command.command_hash,
                'entry_margin_ref':entry_margin_ref,'current_risk_ref':current_risk_ref,
                'original_risk_ref':source['original_risk_ref'],'source_head':source['source_head'],
                'physical_account_key':source['physical_account_key'],'monetary_scope_hash':source['monetary_scope_hash'],
                'quote_valid_until_ms':source['quote_valid_until_ms'],'quote_time_state':source['quote_time_state'],
                'price_binding':source['price_binding'],
                'policy_hash':mandate_source['mandate_hash'],
                'burdens':{k:quantized(v,up=True) for k,v in burdens.items()},
                'capacities':{k:quantized(v,strict=k=='margin_floor_equity') for k,v in capacities.items()},
                'unobserved_currency_leg_capacity':quantized(leg_limit),
                'slot_burdens':{'account':1,'instrument:'+command.symbol.upper():1},
                'slot_capacities':slot_capacities,
                'unobserved_instrument_slot_capacity':policy['max_positions_per_instrument'],
                'fee_state':'UNMEASURED_NOT_ZERO','obligations_complete':False,
                'shared_policy_arbitration':'NOT_ADMITTED','reservation_qualified':False,'execution_authority':False}
            result=object.__new__(EntryResourceProjection);object.__setattr__(result,'_body_json',canonical_json(body).encode())
            return result
    except EntryResourceError:raise
    except Exception as error:raise EntryResourceError('ENTRY_RESOURCE_SOURCE_UNAVAILABLE:'+type(error).__name__) from None
