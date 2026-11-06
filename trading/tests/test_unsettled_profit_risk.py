"""Estimated gains cannot release settled loss limits, live or after restart."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_account_lifecycle import _command, _lifecycle
from test_account_risk_recovery_scope import losses, NOW, STRATEGY
from test_parent_cash_and_unknown_close import unknown_entry
from test_recoverable_lockouts import _cycle
from vati.core import Ledger, EventKind, make_event
from vati.execution.paper import PaperAdapter
from vati.risk.lockouts import LockoutPolicy, LossStreakGovernor


@pytest.mark.parametrize('runtime', ['cycle','account','scalar-account'])
@pytest.mark.parametrize('exit_price', [D('1.1'), D('1.11')])
def test_unsettled_or_flat_close_cannot_erase_prior_losses_live_or_cold(eurusd, runtime, exit_price):
    ledger = Ledger(); alias = 'fx_primary' if runtime=='cycle' else 'acct'
    losses(ledger, alias, n=3)
    if runtime=='cycle':
        actor = _cycle(eurusd, ledger); entries = actor._entries
    else:
        actor = _lifecycle(ledger, PaperAdapter(account_alias=alias)); entries = actor.entries
        actor.streaks = LossStreakGovernor.rebuild(LockoutPolicy(4), ledger.iter(), account_alias=alias)
        if runtime=='scalar-account': actor.streaks = None
    actor.consecutive_losses = 3
    entry = unknown_entry(); entry['fees'] = D('0'); entries['unsettled-close'] = entry
    actor._on_close('unsettled-close', exit_price, 'NATIVE_CLOSE_PRICE_WITHOUT_FINAL_CASH', NOW+10)
    review = list(ledger.iter(EventKind.TRADE_REVIEW))[-1]
    assert review.payload['maturity']['fees_final'] is False
    assert review.payload['maturity']['cash_reconciled'] is False
    assert actor.consecutive_losses == 3
    if actor.streaks is not None:
        assert actor.streaks.verdict(STRATEGY, NOW+11).losses == 3
    cold = LossStreakGovernor.rebuild(LockoutPolicy(4), ledger.iter(), account_alias=alias)
    assert cold.verdict(STRATEGY, NOW+11).losses == 3


def settled_parent():
    ledger = Ledger(); losses(ledger, 'acct', n=3)
    adapter = PaperAdapter(account_alias='acct')
    request = replace(_command('settled-parent'), entry_type='MARKET', command_hash='').sealed()
    opened = adapter.submit(request, now_ms=NOW+1)
    adapter.last_price['EURUSD'] = D('1.11')
    closed = adapter.close(opened.broker_position_id, None, now_ms=NOW+2, reason='SETTLED_GAIN')
    actor = _lifecycle(ledger, adapter)
    actor.streaks = LossStreakGovernor.rebuild(LockoutPolicy(4), ledger.iter(), account_alias='acct')
    actor.entries[request.trade_intent_id] = {'entry':opened.average_fill, 'stop':request.protective_stop,
        'direction':request.direction, 'quantity':request.quantity, 'symbol':'EURUSD',
        'strategy_id':STRATEGY, 'fees':D('0'), 'cost_pct':D('0')}
    actor._on_close(request.trade_intent_id, closed.average_fill, 'SETTLED_GAIN', NOW+3)
    review = list(ledger.iter(EventKind.TRADE_REVIEW))[-1]
    return ledger, actor, review


def test_actual_paper_settled_parent_gain_can_release_its_losses_and_cold_replay():
    ledger, actor, review = settled_parent()
    assert review.payload['maturity']['fees_final'] is True
    assert review.payload['maturity']['cash_reconciled'] is True
    assert actor.streaks.verdict(STRATEGY, NOW+4).losses == 0
    assert LossStreakGovernor.rebuild(LockoutPolicy(4), ledger.iter(), account_alias='acct').verdict(STRATEGY, NOW+4).losses == 0


@pytest.mark.parametrize('damage', ['parent','fees','cash','truthy-fees','source','environment','currency','basis','absent'])
def test_cold_native_review_with_unproven_finality_cannot_release_losses(damage):
    import copy
    ledger, _, review = settled_parent(); altered = Ledger()
    payload = copy.deepcopy(review.payload)
    if damage in {'parent','fees','cash','truthy-fees'}:
        field = {'parent':'parent_final','fees':'fees_final','cash':'cash_reconciled','truthy-fees':'fees_final'}[damage]
        payload['maturity'][field] = 'true' if damage=='truthy-fees' else False
    elif damage=='source': payload['maturity']['source']='UNADMITTED_PROVIDER_CLAIM'
    elif damage=='environment': payload['maturity']['source_environment']='LIVE'
    elif damage=='currency': payload['maturity']['account_currency']=''
    elif damage=='basis': payload['pnl_basis']='REPORTED_NET_OR_LEGACY_UNSPECIFIED_CONVENTION'
    else: payload.pop('maturity')
    for event in ledger.iter():
        if event.hash==review.hash:
            event=make_event(event.kind,event.producer,payload,event_time_ms=event.event_time_ms,
                received_time_ms=event.received_time_ms,correlation_id=event.correlation_id)
        altered.append(event)
    assert altered.verify_chain()[0]
    cold=LossStreakGovernor.rebuild(LockoutPolicy(4),altered.iter(),account_alias='acct')
    assert cold.verdict(STRATEGY,NOW+4).losses==3


@pytest.mark.parametrize('unproven', [False, 1, 'true', None])
def test_nonboolean_profit_authority_is_never_a_settled_gain(unproven):
    governor=LossStreakGovernor(LockoutPolicy(4))
    for n in range(3):governor.on_close(STRATEGY,D('-10'),n)
    governor.on_close(STRATEGY,D('100'),4,profit_final=unproven)
    assert governor.verdict(STRATEGY,5).losses==3
