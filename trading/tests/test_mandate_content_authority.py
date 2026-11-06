"""A genuine owner signature cannot authorize an unsigned policy edit."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import intent,mandate_dict,snapshot
from vati.core import Ledger
from vati.execution import ExecutionRouter,PaperAdapter,ProtectionManager
from vati.risk import Decision,KillSwitch,MandateError,RiskAuthority,StrategyState,TradingMandate


@pytest.mark.parametrize('change',[
    {'account_alias':'other-physical-account'},
    {'venue':'paper'},
    {'mode':'AUTONOMOUS_LIVE'},
    {'instruments':['EURUSD','GBPUSD','USDJPY','XAUUSD','EURCHF']},
    {'allowed_strategies':['FX-LONDON-BREAKOUT-04','UNSIGNED-STRATEGY']},
    {'max_risk_per_trade':'0.0100'},
    {'max_daily_loss':'0.0300'},
    {'max_total_positions':8},
    {'weekend_hold_allowed':True},
    {'expires_at_unix':1800000000+40*86400},
    {'expires_at_unix':1800000000+10*86400},
    {'drawdown_tiers':[{'threshold':'0.04','multiplier':'0.75'},{'threshold':'0.08','multiplier':'0'}]},
    {'strategy_risk_budgets':{'FX-LONDON-BREAKOUT-04':'0.0030'}},
])
def test_same_identity_and_version_cannot_admit_different_effective_policy(change):
    original=mandate_dict();admitted=TradingMandate.from_mapping(original)
    assert admitted.mandate_id==original['mandate_id']
    with pytest.raises(MandateError,match='mandate is not owner-signed'):
        TradingMandate.from_mapping({**original,**change})


def test_unsigned_risk_increase_cannot_reach_actual_sender(eurusd):
    raw=mandate_dict(venue='paper',mode='DEMO_TRADER',max_risk_per_trade='0.0020')
    signed=TradingMandate.from_mapping(raw)
    try:altered=TradingMandate.from_mapping({**raw,'max_risk_per_trade':'0.0100'})
    except MandateError:return
    contract=replace(eurusd,venue='paper');trade=intent(venue='paper',strategy_state=StrategyState.DEMO,requested_risk_pct=D('.0080'))
    result=RiskAuthority(altered).evaluate_safe(trade,snapshot(contract))
    assert result.decision in {Decision.APPROVED,Decision.REDUCED}
    assert result.approved_risk_pct>signed.max_risk_per_trade
    paper=PaperAdapter(account_alias=altered.account_alias)
    router=ExecutionRouter(ledger=Ledger(),adapters={'paper':paper},kill_switch=KillSwitch(),protection=ProtectionManager())
    actual=router.execute(trade,result,altered,now_ms=1800000000000)
    assert actual.status=='FILLED' and paper.positions()
    pytest.fail('a real owner token authorized an unsigned higher-risk fill')


def test_owner_can_sign_an_explicit_changed_policy_and_the_sender_uses_its_bound_limit(eurusd):
    raw=mandate_dict(venue='paper',mode='DEMO_TRADER',max_risk_per_trade='0.0030')
    admitted=TradingMandate.from_mapping(raw);contract=replace(eurusd,venue='paper')
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO)
    result=RiskAuthority(admitted).evaluate_safe(trade,snapshot(contract))
    assert result.decision in {Decision.APPROVED,Decision.REDUCED} and result.approved_risk_pct<=D('.0030')
    paper=PaperAdapter(account_alias=admitted.account_alias)
    actual=ExecutionRouter(ledger=Ledger(),adapters={'paper':paper},kill_switch=KillSwitch(),protection=ProtectionManager()).execute(trade,result,admitted,now_ms=1800000000000)
    assert actual.status=='FILLED' and paper.positions()


def test_explicit_defaults_and_equivalent_money_units_have_the_same_subject():
    from dataclasses import asdict
    from vati.risk.mandate import DEFAULT_DRAWDOWN_TIERS,mandate_subject
    original=mandate_dict()
    explicit={**original,'drawdown_tiers':[asdict(t) for t in DEFAULT_DRAWDOWN_TIERS],
        'strategy_risk_budgets':{},'strategy_temperaments':{},'trading_temperament':None,
        'max_risk_per_trade':'0.005','instruments':list(reversed(original['instruments']))}
    assert mandate_subject(original)==mandate_subject(explicit)
    assert TradingMandate.from_mapping(explicit).authority_matches_policy()


def test_identity_only_historical_signature_is_not_silently_upgraded():
    from conftest import owner_authority
    raw=mandate_dict()
    raw['owner_signature_ref']=owner_authority().token(act='mandate-admit',
        subject=f"{raw['mandate_id']}:{raw['version']}",issued_at_unix=raw['signed_at_unix'],
        lifetime_seconds=raw['expires_at_unix']-raw['signed_at_unix'])
    with pytest.raises(MandateError,match='owner-signed'):TradingMandate.from_mapping(raw)


def test_grant_lifetime_cannot_be_shorter_than_the_standing_policy():
    from conftest import owner_authority
    from vati.risk.mandate import mandate_subject
    raw=mandate_dict()
    raw['owner_signature_ref']=owner_authority().token(act='mandate-admit',subject=mandate_subject(raw),
        issued_at_unix=raw['signed_at_unix'],lifetime_seconds=60)
    with pytest.raises(MandateError,match='grant lifetime'):TradingMandate.from_mapping(raw)


def test_a_mutated_nested_policy_is_refused_by_the_real_kernel(eurusd):
    raw=mandate_dict(venue='paper',mode='DEMO_TRADER',strategy_risk_budgets={'FX-LONDON-BREAKOUT-04':'0.0010'})
    admitted=TradingMandate.from_mapping(raw)
    assert admitted.authority_matches_policy()
    admitted.strategy_risk_budgets['FX-LONDON-BREAKOUT-04']=D('.0050')
    result=RiskAuthority(admitted).evaluate_safe(intent(venue='paper',strategy_state=StrategyState.DEMO),snapshot(replace(eurusd,venue='paper')))
    assert result.decision is Decision.REJECTED and result.reason_code=='MANDATE_AUTHORITY_MISMATCH'


def test_a_resealed_approval_cannot_bypass_the_router_policy_admission(eurusd):
    from vati.execution import RouterError
    from vati.risk.serde import mandate_binding_hash
    raw=mandate_dict(venue='paper',mode='DEMO_TRADER');admitted=TradingMandate.from_mapping(raw)
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO)
    decision=RiskAuthority(admitted).evaluate_safe(trade,snapshot(replace(eurusd,venue='paper')))
    altered=replace(admitted,max_risk_per_trade=D('.0100'))
    rebound=RiskAuthority._seal(replace(decision,mandate_hash=mandate_binding_hash(altered)))
    paper=PaperAdapter(account_alias=altered.account_alias);ledger=Ledger()
    router=ExecutionRouter(ledger=ledger,adapters={'paper':paper},kill_switch=KillSwitch(),protection=ProtectionManager())
    with pytest.raises(RouterError,match='policy-bound owner grant'):router.execute(trade,rebound,altered,now_ms=1800000000000)
    assert not paper.positions()


def test_subject_never_rounds_distinct_high_precision_limits_to_the_same_policy():
    from vati.risk.mandate import mandate_subject
    original=mandate_dict()
    one={**original,'max_risk_per_trade':'0.005000000000000000000000000000001'}
    two={**original,'max_risk_per_trade':'0.005000000000000000000000000000002'}
    assert mandate_subject(one)!=mandate_subject(two)


def test_changed_effective_default_requires_new_owner_admission(monkeypatch):
    from vati.risk import mandate as module
    raw=mandate_dict()
    monkeypatch.setattr(module,'DEFAULT_DRAWDOWN_TIERS',(
        module.DrawdownTier(D('.03'),D('.75')),module.DrawdownTier(D('.08'),D('0'))))
    with pytest.raises(MandateError,match='owner-signed'):TradingMandate.from_mapping(raw)
