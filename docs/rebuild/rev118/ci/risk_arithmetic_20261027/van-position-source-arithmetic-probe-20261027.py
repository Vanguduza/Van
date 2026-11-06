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
