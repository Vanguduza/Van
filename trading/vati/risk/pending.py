"""Exact possible-fill risk; pending protection is deliberately unconfirmed."""
import re
from fractions import Fraction

from vati.risk.arithmetic import fraction,exact_loss_amount
from vati.risk.contracts import PendingRiskCommitment,SymbolContract,Direction,LossModel

_REF=re.compile('[a-f0-9]{64}',re.ASCII)


def pending_risk_losses(snapshot):
    values=[];seen=set()
    if type(snapshot.pending_risk_commitments) is not tuple:
        raise ValueError('pending risk requires immutable original commitments')
    for p in snapshot.pending_risk_commitments:
        if (type(p) is not PendingRiskCommitment or type(p.contract) is not SymbolContract
                or type(p.direction) is not Direction or p.protection_confirmed is not False
                or p.execution_authority is not False or type(p.new_position_slots) is not int
                or p.new_position_slots not in (0,1) or p.state not in {'UNCONFIRMED','PENDING','PARTIAL','OPEN','UNCERTAIN'}
                or not isinstance(p.origin_alias,str) or not p.origin_alias
                or not isinstance(p.command_ref,str) or _REF.fullmatch(p.command_ref) is None
                or not isinstance(p.original_input_ref,str) or _REF.fullmatch(p.original_input_ref) is None
                or p.command_ref in seen):raise ValueError('pending risk original identity, state or authority invalid')
        c=snapshot.native_account_context
        if (c is None or p.physical_account_key!=c.physical_account_key or p.monetary_scope_hash!=c.monetary_scope_hash
                or p.contract.account_currency!=snapshot.symbol_contract.account_currency):
            raise ValueError('pending risk native monetary scope mismatch')
        if fraction(p.quantity)<=0 or fraction(p.entry)<=0:
            raise ValueError('pending risk exact quantity/price unavailable')
        if type(p.contract.loss_model) is not LossModel:
            raise ValueError('pending risk original loss model unavailable')
        if p.contract.loss_model is LossModel.STOP_DISTANCE and (
                fraction(p.contract.tick_size)<=0 or fraction(p.contract.tick_value)<=0):
            raise ValueError('pending risk original tick terms unavailable')
        if p.contract.loss_model is LossModel.ILLIQUID_EQUITY and fraction(p.contract.liquidity_haircut)<0:
            raise ValueError('pending risk cannot offset loss with a negative haircut')
        if p.contract.loss_model is not LossModel.FULL_STAKE and (p.stop is None or fraction(p.stop)<=0):
            raise ValueError('pending risk protective level unavailable')
        value=exact_loss_amount(p.quantity,p.contract,entry=p.entry,stop=p.stop)
        if value<0:raise ValueError('pending risk cannot supply negative capacity')
        seen.add(p.command_ref);values.append((p,value))
    return tuple(values)
