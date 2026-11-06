"""Source-only governor parity and alias-bounded original reset semantics."""
from dataclasses import asdict
from decimal import Decimal as D
import random

import pytest

from vati.risk.physical_lockouts import PhysicalLossStreakGovernor
from vati.risk.lockouts import LossStreakGovernor, LockoutPolicy, ACCOUNT_SCOPE, WEEK_MS


@pytest.mark.parametrize('seed', range(24))
def test_one_alias_matches_the_existing_complete_clock_reset_and_profit_behavior(seed):
    rng = random.Random(seed)
    policy = LockoutPolicy(3, cooldown_ms=100, max_cooldowns_per_week=2)
    original = LossStreakGovernor(policy)
    physical = PhysicalLossStreakGovernor(policy, account_alias='account_a')
    now = 0
    for _ in range(90):
        now += rng.choice([0, 1, 50, 101, WEEK_MS+1])
        sid = rng.choice(['strategy_a', 'strategy_b', 'owner.manual'])
        if rng.randrange(7) == 0:
            scope = rng.choice([sid, ACCOUNT_SCOPE])
            assert physical.reset(scope) == original.reset(scope)
        else:
            pnl = rng.choice([D('-1'), D('0'), D('1')])
            final = rng.choice([True, False])
            assert physical.on_close(sid, pnl, now, profit_final=final) == original.on_close(sid, pnl, now, profit_final=final)
        assert {k:asdict(v) for k,v in physical._scopes.items()} == {k:asdict(v) for k,v in original._scopes.items()}
        for target in ('strategy_a','strategy_b','owner.manual'):
            assert physical.verdict(target, now) == original.verdict(target, now)


def test_alias_switch_cannot_split_the_account_loss_limit():
    g = PhysicalLossStreakGovernor(LockoutPolicy(4,cooldown_ms=100), account_alias='account_b')
    for i, alias in enumerate(['account_a','account_a','account_b','account_b']):
        g.on_close('strategy',D('-1'),i,origin_alias=alias)
    assert 'cooling down' in g.verdict('strategy',3).lock
    assert g.original_contributors(ACCOUNT_SCOPE) == ('account_a','account_b')
    assert g.verdict('strategy',104).risk_multiplier == D('0.5')


def test_alias_reset_preserves_other_alias_pending_losses_and_joint_clock():
    g = PhysicalLossStreakGovernor(LockoutPolicy(4,cooldown_ms=100),account_alias='account_a')
    for i,alias in enumerate(['account_a','account_b','account_a','account_b']):
        g.on_close('strategy',D('-1'),i,origin_alias=alias)
    g.on_close('strategy',D('-1'),4,origin_alias='account_b')
    g.reset(ACCOUNT_SCOPE)
    assert g._scopes[ACCOUNT_SCOPE].losses == 1
    assert g.original_contributors(ACCOUNT_SCOPE) == ('account_b',)
    assert g.verdict('strategy',4).lock
    assert g._scopes[ACCOUNT_SCOPE].probation


def test_each_contributing_alias_must_release_its_original_suspension():
    g = PhysicalLossStreakGovernor(LockoutPolicy(1,cooldown_ms=1,max_cooldowns_per_week=1),account_alias='account_a')
    g.on_close('strategy',D('-1'),0,origin_alias='account_a')
    g.on_close('strategy',D('-1'),2,origin_alias='account_b')
    assert g._scopes[ACCOUNT_SCOPE].suspended
    g.reset(ACCOUNT_SCOPE)
    assert g._scopes[ACCOUNT_SCOPE].suspended
    assert g.original_contributors(ACCOUNT_SCOPE) == ('account_b',)
    # Replay the second alias's independently verified original reset.
    g._reset_original_alias(ACCOUNT_SCOPE,'account_b')
    assert not g._scopes[ACCOUNT_SCOPE].suspended
    assert g._scopes[ACCOUNT_SCOPE].losses == 0
    assert not g._scopes[ACCOUNT_SCOPE].probation


def test_final_profit_keeps_the_existing_suspension_and_cooldown_rules():
    g = PhysicalLossStreakGovernor(LockoutPolicy(1,cooldown_ms=100,max_cooldowns_per_week=1),account_alias='account_a')
    g.on_close('strategy',D('-1'),0,origin_alias='account_a')
    g.on_close('strategy',D('1'),1,origin_alias='account_b',profit_final=True)
    assert g.verdict('strategy',1).lock and not g._scopes[ACCOUNT_SCOPE].probation
    g.on_close('strategy',D('-1'),2,origin_alias='account_b')
    g.on_close('strategy',D('1'),3,origin_alias='account_b',profit_final=True)
    assert g._scopes[ACCOUNT_SCOPE].suspended


def test_manual_and_strategy_controls_keep_the_existing_separate_scopes():
    g = PhysicalLossStreakGovernor(LockoutPolicy(1,cooldown_ms=100),account_alias='account_a')
    g.on_close('owner.manual',D('-1'),1,origin_alias='account_b')
    assert g.verdict('owner.manual',2).lock
    assert not g.verdict('automatic',2).lock
    g.reset('automatic')
    assert g.verdict('owner.manual',2).lock


def test_estimated_profit_does_not_release_any_original_losses():
    g = PhysicalLossStreakGovernor(LockoutPolicy(4),account_alias='account_a')
    g.on_close('strategy',D('-1'),1,origin_alias='account_b')
    g.on_close('strategy',D('1'),2,origin_alias='account_a')
    assert g._scopes[ACCOUNT_SCOPE].losses == 1


@pytest.mark.parametrize('value',[D('NaN'),D('Infinity'),1.0])
def test_non_exact_or_nonfinite_outcome_cannot_supply_physical_risk_history(value):
    g = PhysicalLossStreakGovernor(LockoutPolicy(4),account_alias='account_a')
    with pytest.raises(ValueError):
        g.on_close('strategy',value,1,origin_alias='account_b')
