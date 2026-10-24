"""One setup on distinct accounts/venues must not collide in native history."""
import pytest
from decimal import Decimal
from test_backtest_runner_cli import fx_cfg,fx_engine
from test_intelligence import pullback_fixture
from test_strategies_arbiter import state_for
from vati.strategies import StrategyContext


@pytest.mark.parametrize('scope',['account','venue'])
def test_real_opportunity_identity_is_scoped_while_original_idempotency_remains_stable(eurusd,scope):
    cfg=fx_cfg(eurusd);engine=fx_engine(cfg);state=state_for(pullback_fixture())
    context=StrategyContext(Decimal('.0003'))
    def assess(account,venue,seed):
        result=engine.assess(state,context,regime_label=state.regime.trend.value,
            account_alias=account,venue=venue,idempotency_seed=seed)
        assert result.intent is not None
        return result.intent
    original=assess('fx_primary','paper','original-native-seed')
    restarted=assess('fx_primary','paper','original-native-seed')
    changed=assess('another_owner_account' if scope=='account' else 'fx_primary',
        'mt5' if scope=='venue' else 'paper','other-native-seed')
    assert original.trade_intent_id==restarted.trade_intent_id and original.idempotency_key==restarted.idempotency_key
    assert original.decision_hash==changed.decision_hash
    assert original.trade_intent_id!=changed.trade_intent_id


def test_new_scoped_uuid_still_honours_the_original_native_idempotency_claim(eurusd):
    import uuid
    from dataclasses import replace
    from conftest import snapshot
    from vati.core import EventKind,Ledger
    from vati.core.canonical import canonical_hash
    from vati.execution import ExecutionRouter,PaperAdapter,ProtectionManager,RouterError
    from vati.risk import Decision,KillSwitch,RiskAuthority,TradingMandate
    cfg=fx_cfg(eurusd);engine=fx_engine(cfg);state=state_for(pullback_fixture())
    chosen=engine.assess(state,StrategyContext(Decimal('.0003')),regime_label=state.regime.trend.value,
        account_alias=cfg.account_alias,venue='paper',idempotency_seed='original-native-seed').intent
    assert chosen is not None
    legacy=replace(chosen,trade_intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'vati:'+chosen.decision_hash)),
        idempotency_key=canonical_hash({'seed':'original-native-seed','decision':chosen.decision_hash})[:32])
    assert legacy.trade_intent_id!=chosen.trade_intent_id
    mandate=TradingMandate.from_mapping(cfg.mandate_dict);native=replace(snapshot(cfg.contract),now_unix=state.as_of_ms//1000)
    paper=PaperAdapter();ledger=Ledger()
    def router():return ExecutionRouter(ledger=ledger,adapters={'paper':paper},kill_switch=KillSwitch(),protection=ProtectionManager())
    old=RiskAuthority(mandate).evaluate_safe(legacy,native)
    assert old.decision in {Decision.APPROVED,Decision.REDUCED}
    assert router().execute(legacy,old,mandate,now_ms=state.as_of_ms).status=='FILLED'
    new=RiskAuthority(mandate).evaluate_safe(chosen,native)
    assert new.decision in {Decision.APPROVED,Decision.REDUCED}
    with pytest.raises(RouterError,match='duplicate idempotency'):
        router().execute(chosen,new,mandate,now_ms=state.as_of_ms)
    assert ledger.count(EventKind.ORDER_COMMAND)==1 and len(paper.positions())==1
