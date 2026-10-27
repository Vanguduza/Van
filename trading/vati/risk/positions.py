"""Project existing provider facts without rounding away their loss inputs."""
from decimal import Decimal

from vati.risk.arithmetic import decimal, fraction
from vati.risk.contracts import LossModel, OpenPosition, StopRiskTerms

ZERO = Decimal('0')
ONE = Decimal('1')


def project_open_position(*, symbol, direction, quantity, entry, stop, contract, loss_model):
    """Pure projection, not a native observation, reservation or permission."""
    if symbol.upper() != contract.symbol.upper() or loss_model is not contract.loss_model:
        # A different symbol/model cannot borrow this contract's cash value.
        return OpenPosition(symbol, direction, quantity, ZERO, ZERO, '', '',
                            has_broker_side_stop=False)
    if loss_model is LossModel.FULL_STAKE:
        return OpenPosition(symbol, direction, ZERO, ZERO, ZERO,
                            contract.base_currency, contract.quote_currency,
                            has_broker_side_stop=False, loss_model=loss_model, stake=quantity)
    distance = decimal(abs(fraction(entry) - fraction(stop))) if stop is not None else ZERO
    if loss_model is LossModel.ILLIQUID_EQUITY:
        return OpenPosition(symbol, direction, quantity, distance, ONE,
                            contract.base_currency, contract.quote_currency,
                            has_broker_side_stop=False, loss_model=loss_model,
                            liquidity_haircut_per_unit=decimal(fraction(entry) * fraction(contract.liquidity_haircut)))
    terms = (StopRiskTerms(entry, stop, contract.tick_size, contract.tick_value)
             if stop is not None else None)
    return OpenPosition(symbol, direction, quantity, distance,
                        contract.value_per_price_unit_per_lot,
                        contract.base_currency, contract.quote_currency,
                        has_broker_side_stop=stop is not None, loss_model=loss_model,
                        stop_terms=terms)
