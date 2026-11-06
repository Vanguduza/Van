"""Original position projection methods; no native provider or order effect."""
from decimal import Decimal, localcontext, ROUND_DOWN
from fractions import Fraction
from types import SimpleNamespace

import pytest

from vati.app.account_service import AccountCoordinatorService
from vati.app.cycle import DecisionCycle
from vati.risk.contracts import Direction, LossModel


@pytest.mark.parametrize('producer', ['account', 'cycle'])
@pytest.mark.parametrize('hostile', [False, True])
def test_original_position_projection_keeps_original_stop_distance(eurusd, producer, hostile):
    position = SimpleNamespace(symbol='EURUSD', position_id='source-fixture-only',
        direction=Direction.LONG, quantity=Decimal('1'), entry_price=Decimal('1.10010'),
        stop_price=Decimal('1.09790'), loss_model=LossModel.STOP_DISTANCE)
    fixture = SimpleNamespace(adapter=SimpleNamespace(positions=lambda: [position]),
        protection=SimpleNamespace(rules={}), contracts={'EURUSD': eurusd},
        cfg=SimpleNamespace(contract=eurusd), _entries={})
    project = (AccountCoordinatorService._open_positions if producer == 'account'
               else DecisionCycle._open_positions)
    original_distance = abs(Fraction(position.entry_price) - Fraction(position.stop_price))
    with localcontext() as caller:
        if hostile:
            caller.prec = 1
            caller.rounding = ROUND_DOWN
        projected = project(fixture)
        assert len(projected) == 1
        assert Fraction(projected[0].stop_distance) == original_distance


@pytest.mark.parametrize('producer', ['account', 'cycle'])
def test_existing_stop_loss_uses_original_tick_ratio(eurusd, producer):
    from dataclasses import replace
    from vati.risk.heat import position_risk
    contract = replace(eurusd, tick_size=Decimal('3'), tick_value=Decimal('1'))
    position = SimpleNamespace(symbol='EURUSD', position_id='source-fixture-only',
        direction=Direction.LONG, quantity=Decimal('40'), entry_price=Decimal('6'),
        stop_price=Decimal('3'), loss_model=LossModel.STOP_DISTANCE)
    fixture = SimpleNamespace(adapter=SimpleNamespace(positions=lambda: [position]),
        protection=SimpleNamespace(rules={}), contracts={'EURUSD': contract},
        cfg=SimpleNamespace(contract=contract), _entries={})
    project = (AccountCoordinatorService._open_positions if producer == 'account'
               else DecisionCycle._open_positions)
    assert position_risk(project(fixture)[0]) == Decimal('40')


@pytest.mark.parametrize('producer', ['account', 'cycle'])
def test_original_deriv_portfolio_retains_builtin_stake_loss(eurusd, producer):
    from dataclasses import replace
    from vati.execution.deriv import DerivAdapter
    from vati.risk.heat import position_risk
    # Actual production portfolio parser over an explicitly isolated reply;
    # this fixture performs no network, owner admission or financial effect.
    transport_fixture = SimpleNamespace(_call=lambda _: {'portfolio': {'contracts': [
        {'contract_id': 'source-fixture-only', 'symbol': 'EURUSD', 'buy_price': '5'}]}})
    position = DerivAdapter.positions(transport_fixture)[0]
    assert position.loss_model is LossModel.FULL_STAKE and position.quantity == Decimal('5')
    contract = replace(eurusd, venue='deriv', loss_model=LossModel.FULL_STAKE)
    fixture = SimpleNamespace(adapter=SimpleNamespace(positions=lambda: [position]),
        protection=SimpleNamespace(rules={}), contracts={'EURUSD': contract},
        cfg=SimpleNamespace(contract=contract), _entries={})
    project = (AccountCoordinatorService._open_positions if producer == 'account'
               else DecisionCycle._open_positions)
    projected = project(fixture)[0]
    assert projected.loss_model is LossModel.FULL_STAKE
    assert position_risk(projected) == Decimal('5')
