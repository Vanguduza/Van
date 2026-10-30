"""The parent review must reflect all realised cash and preserve unknown-state fences."""
from dataclasses import replace
import pytest
from decimal import Decimal as D

from test_account_lifecycle import _command,_lifecycle
from test_account_risk_recovery_scope import losses,NOW,STRATEGY
from test_recoverable_lockouts import _cycle
from vati.core import Ledger,EventKind
from vati.execution.paper import PaperAdapter
from vati.execution.review import closed_trade_pnl,native_economic_maturity
from vati.risk.contracts import Direction
from vati.risk.lockouts import LockoutPolicy,LossStreakGovernor


def partial_parent():
    adapter=PaperAdapter(account_alias='acct')
    command=replace(_command('partial-parent'),entry_type='MARKET',quantity=D('2'),command_hash='').sealed()
    receipt=adapter.submit(command,now_ms=1)
    position=receipt.broker_position_id
    adapter.last_price['EURUSD']=D('1.1010')
    adapter.close(position,D('1'),now_ms=2,reason='PARTIAL')
    adapter.last_price['EURUSD']=D('1.0990')
    adapter.close(position,None,now_ms=3,reason='CLOSE')
    entry={'trade_intent_id':command.trade_intent_id,'fees':D('0'),'carry':D('0')}
    return adapter,entry


def test_all_partial_close_cash_reaches_the_parent_outcome_once(eurusd):
    adapter,entry=partial_parent()
    measured=closed_trade_pnl(entry,D('1.0990'),eurusd,adapter.closed)
    assert measured.amount==adapter.realised_pnl
    assert measured.amount==adapter.equity-D('10000')
    assert native_economic_maturity(adapter,entry['trade_intent_id'],measured)['parent_final'] is True


def test_fees_and_carry_apply_once_to_the_whole_parent_not_each_reduction(eurusd):
    adapter,entry=partial_parent();entry.update(fees=D('2'),carry=D('-1'))
    measured=closed_trade_pnl(entry,D('1.0990'),eurusd,adapter.closed)
    assert measured.amount==adapter.realised_pnl-D('3')


def unknown_entry():
    return {'entry':D('1.1'),'stop':D('1.09'),'direction':Direction.LONG,'quantity':D('1'),
        'strategy_id':STRATEGY,'symbol':'EURUSD','fees':D('NaN'),'cost_pct':D('0')}


def test_an_unknown_cycle_close_cannot_reset_three_real_losses(eurusd):
    ledger=Ledger();losses(ledger,'fx_primary',n=3);cycle=_cycle(eurusd,ledger)
    cycle._entries['unsettled']=unknown_entry()
    cycle._on_close('unsettled',D('1.09'),'VENUE_STOP',NOW+10)
    assert cycle.streaks.verdict(STRATEGY,NOW+11).losses==3
    assert 'unresolved' in cycle.streaks.recovery_issue
    assert cycle.kill.halted
    assert 'unresolved' in cycle.snapshot(now_ms=NOW+11,quote_age_ms=0).loss_streak_lock
    cold=_cycle(eurusd,ledger)
    assert cold.streaks.verdict(STRATEGY,NOW+12).losses==3
    assert cold.kill.halted and cold.streaks.recovery_issue


def test_unknown_account_close_latches_reconciliation_without_resetting_losses(eurusd):
    ledger=Ledger();adapter=PaperAdapter(account_alias='acct');life=_lifecycle(ledger,adapter)
    life.streaks=LossStreakGovernor(LockoutPolicy(4))
    for index in range(3):life.streaks.on_close(STRATEGY,D('-10'),index)
    life.entries['unsettled']=unknown_entry()
    life._on_close('unsettled',D('1.09'),'VENUE_STOP',NOW+10)
    assert life.streaks.verdict(STRATEGY,NOW+11).losses==3
    assert 'unresolved' in life.streaks.recovery_issue
    assert life.router.kill.halted


def test_duplicate_native_cash_delta_is_not_an_extra_profit(eurusd):
    adapter, entry = partial_parent()
    measured = closed_trade_pnl(entry, D('1.0990'), eurusd, adapter.closed+[dict(adapter.closed[0])])
    assert measured.amount == adapter.realised_pnl


@pytest.mark.parametrize('change', ['conflict', 'mixed_snapshot', 'missing_identity', 'mixed_basis'])
def test_ambiguous_parent_cash_is_unresolved_instead_of_guessed(eurusd, change):
    adapter, entry = partial_parent()
    rows = [dict(row) for row in adapter.closed]
    if change == 'conflict':
        rows.append({**rows[0], 'pnl': D('999')})
    elif change == 'mixed_snapshot':
        rows.append({'intent': entry['trade_intent_id'], 'pnl': D('999')})
    elif change == 'missing_identity':
        rows[0].pop('close_id')
    else:
        rows[0]['pnl_basis'] = 'NET_CONFIRMED'
    assert closed_trade_pnl(entry, D('1.0990'), eurusd, rows).amount is None


def test_legacy_parent_snapshots_are_not_summed_as_execution_deltas(eurusd):
    rows = [{'intent': 'legacy', 'pnl': D('5')}, {'intent': 'legacy', 'pnl': D('8')}]
    measured = closed_trade_pnl({'trade_intent_id': 'legacy'}, D('1'), eurusd, rows)
    assert measured.amount == D('8') and 'LEGACY_UNSPECIFIED' in measured.basis


@pytest.mark.parametrize('quantity', [D('0'), D('-1'), D('NaN'), D('Infinity')])
def test_invalid_paper_reduction_cannot_change_cash_or_position(quantity):
    adapter = PaperAdapter(); opened = adapter.submit(replace(_command('invalid'), entry_type='MARKET'), now_ms=1)
    before = adapter.sync_account()
    with pytest.raises(ValueError, match='positive'):
        adapter.close(opened.broker_position_id, quantity, now_ms=2, reason='PARTIAL')
    assert adapter.sync_account() == before and len(adapter.positions()) == 1 and not adapter.closed
