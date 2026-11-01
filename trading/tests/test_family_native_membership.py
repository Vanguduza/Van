"""Native membership derives from original commands/fills and owner captures."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal as D

import pytest

from vati.core import Ledger
from vati.execution.recovery_scope import NativePositionHistory
from vati.lifecycle.family_actions import FamilyActionError
from vati.lifecycle.family_membership import original_native_snapshot
from test_family_durable_projection import recorded_scale


def snapshot(ledger, life, adapter, root):
    history = NativePositionHistory(ledger, account_alias=adapter.account_alias, venue=adapter.venue)
    return original_native_snapshot(history, life.families.for_intent(root.trade_intent_id), adapter)


def test_original_hedged_legs_keep_their_own_quantities_and_stops(tmp_path):
    with closing(Ledger(tmp_path/'membership.sqlite')) as ledger:
        life,adapter,root,child,entry,added = recorded_scale(ledger,netted=False)
        before = ledger.count()
        actual = snapshot(ledger,life,adapter,root)
        legs = {leg.position_id: leg for leg in actual.legs}
        assert actual.known and not actual.ambiguous
        assert legs[entry.broker_position_id].remaining == D('.06')
        assert legs[added.broker_position_id].remaining == D('.05')
        assert actual.remaining_exact == D('.11')
        assert all(leg.protection_confirmed for leg in legs.values())
        assert all(leg.close_rules.quantity_quantum is None for leg in legs.values())
        assert all(not leg.close_rules.partial_allowed for leg in legs.values())
        assert ledger.count() == before
        with closing(Ledger(ledger.path)) as cold:
            assert snapshot(cold,life,adapter,root).digest == actual.digest


@pytest.mark.parametrize('damage',['missing','manual','quantity','stop'])
def test_current_unknown_or_foreign_positions_never_replace_an_original_leg(tmp_path,damage):
    with closing(Ledger(tmp_path/'membership.sqlite')) as ledger:
        life,adapter,root,child,entry,added = recorded_scale(ledger,netted=False)
        if damage == 'missing':
            del adapter._positions[added.broker_position_id]
        elif damage == 'manual':
            adapter._positions[added.broker_position_id]['intent'] = 'manual'
        elif damage == 'quantity':
            adapter._positions[added.broker_position_id]['qty'] += D('.01')
        else:
            adapter._positions[added.broker_position_id]['stop'] = None
        actual = snapshot(ledger,life,adapter,root)
        child_leg = next(leg for leg in actual.legs if leg.trade_intent_id == child.trade_intent_id)
        if damage == 'stop':
            assert actual.known and not child_leg.protection_confirmed
            assert child_leg.stop is None
        else:
            assert not actual.known and child_leg.remaining is None


def test_a_netted_position_cannot_be_substituted_for_distinct_original_legs(tmp_path):
    with closing(Ledger(tmp_path/'membership.sqlite')) as ledger:
        life,adapter,root,child,entry,added = recorded_scale(ledger,netted=True)
        with pytest.raises(FamilyActionError,match='distinct native family legs'):
            snapshot(ledger,life,adapter,root)


def test_original_child_close_survives_cold_restore_without_reducing_the_root_leg(tmp_path):
    from vati.lifecycle.family import FamilyRegistry, FamilyMember, MemberRole
    with closing(Ledger(tmp_path/'membership.sqlite')) as ledger:
        life,adapter,root,child,entry,added = recorded_scale(ledger,netted=False)
        closed = life.router.apply_preservation('paper', position_id=added.broker_position_id,
            trade_intent_id=child.trade_intent_id, action='FULL_CLOSE', now_ms=4000,
            reason='ORIGINAL_CHILD_CLOSE')
        family = life.families.for_intent(root.trade_intent_id)
        life.families.apply(family.family_id, FamilyMember('child-exit:'+closed.receipt_hash,
            MemberRole.PARTIAL_EXIT, closed.filled_qty, closed.average_fill, 4000,
            trade_intent_id=child.trade_intent_id), now_ms=4000)
        with closing(Ledger(ledger.path)) as cold:
            history = NativePositionHistory(cold, account_alias=adapter.account_alias, venue='paper')
            restored = FamilyRegistry().restore(history, family_id=family.family_id,
                trade_intent_id=root.trade_intent_id, symbol='EURUSD', direction=root.direction,
                position_id=entry.broker_position_id)
            actual = original_native_snapshot(history, restored, adapter)
            legs = {leg.trade_intent_id: leg for leg in actual.legs}
            assert actual.known and legs[root.trade_intent_id].remaining == D('.06')
            assert legs[child.trade_intent_id].remaining == 0
            assert actual.remaining_exact == D('.06')
