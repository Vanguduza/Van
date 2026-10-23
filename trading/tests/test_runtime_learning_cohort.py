"""Physical simulation and research execution cannot acquire live evidence weight."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_backtest_runner_cli import fx_cfg,fx_engine,synthetic_bars
from test_single_session_lease import config
from conftest import historical_mandate_dict
from vati.accounts import AccountRegistry
from vati.app.service import SessionService
from vati.backtest import BacktestEngine
from vati.core import Ledger,EventKind
from vati.intelligence.events import EventMatrix
from vati.learning.episodes import Environment
from vati.learning.hooks import LearningHooks
from vati.market_data import FX_CALENDAR


def backtest(cfg,path,hooks=None):
    return BacktestEngine(cfg=cfg,engine=fx_engine(cfg),cost_fn=lambda st:D('0.0003'),
        calendar=FX_CALENDAR,events=EventMatrix(),ledger_path=str(path),learning=hooks)


@pytest.mark.parametrize('environment',[Environment.LIVE,Environment.LIMITED_LIVE,Environment.DEMO])
def test_backtest_refuses_a_non_backtest_hook_before_creating_financial_history(tmp_path,eurusd,environment):
    path=tmp_path/'research.sqlite';hooks=LearningHooks(environment=environment)
    with pytest.raises(ValueError,match='BACKTEST|backtest|cohort'):
        backtest(fx_cfg(eurusd),path,hooks)
    assert not path.exists() and not hooks.brokers.profiles and not hooks.episodes


def test_a_relabelled_hook_is_refused_again_before_a_backtest_run(tmp_path,eurusd):
    path=tmp_path/'research.sqlite';hooks=LearningHooks(environment=Environment.BACKTEST)
    engine=backtest(fx_cfg(eurusd),path,hooks);hooks.environment=Environment.LIVE
    with pytest.raises(ValueError,match='BACKTEST|backtest|cohort'):engine.run(synthetic_bars())
    assert not path.exists() and not hooks.brokers.profiles and not hooks.episodes


def test_a_backtest_without_hooks_still_records_its_native_research_cohort(tmp_path,eurusd):
    path=tmp_path/'research.sqlite';result=backtest(fx_cfg(eurusd),path).run(synthetic_bars())
    ledger=Ledger(path)
    try:
        assert result.trades>0
        risks=list(ledger.iter(EventKind.RISK_DECISION));assert risks
        assert all(r.payload.get('execution_cohort',{}).get('environment')=='BACKTEST' for r in risks)
    finally:ledger.close()


def test_actual_paper_service_cannot_label_its_execution_facts_as_live(tmp_path,eurusd):
    cfg=config(tmp_path,eurusd);reg=AccountRegistry(cfg.registry_path);account=reg.get(cfg.account_alias)
    reg.replace(replace(account,mode='AUTONOMOUS_LIVE',demo=False,mandate_ref='fixture-signed-policy'))
    cfg.mandate=historical_mandate_dict(venue='paper',mode='AUTONOMOUS_LIVE',account_alias=account.alias,
        allowed_strategies=['FX-TREND-PULLBACK-01'])
    service=SessionService(cfg,lambda now:[],clock=lambda:1000).build()
    try:assert service.learning.environment is Environment.DEMO
    finally:service.close();service._ledger.close()


def test_scoped_backtest_health_and_execution_facts_keep_their_research_weights_after_restart(tmp_path,eurusd):
    from vati.learning.replay import restore_learning_runtime
    cfg=fx_cfg(eurusd);path=tmp_path/'study.sqlite'
    hooks=LearningHooks(environment=Environment.BACKTEST,account_alias=cfg.account_alias)
    result=backtest(cfg,path,hooks).run(synthetic_bars());assert result.trades>0
    assert not hooks.refusals and not hooks.recovery_issue
    assert sum((hooks.health.verdict(s).weighted_samples for s in hooks.health._obs),D(0))==D('0.3')*result.trades
    assert hooks.brokers.profiles and all(p._w()==0 for p in hooks.brokers.profiles.values())
    assert hooks.adjustments==[]
    ledger=Ledger(path)
    try:
        cold=LearningHooks(environment=Environment.BACKTEST,account_alias=cfg.account_alias)
        report=restore_learning_runtime(ledger,cold,{})
        assert report.health_observations==result.trades and not cold.recovery_issue
        assert sum((cold.health.verdict(s).weighted_samples for s in cold.health._obs),D(0))==D('0.3')*result.trades
        live=LearningHooks(environment=Environment.LIVE,account_alias=cfg.account_alias)
        excluded=restore_learning_runtime(ledger,live,{})
        assert excluded.tca_observations==excluded.health_observations==0
        assert excluded.excluded_scope_refs and not live.recovery_issue and not live.brokers.profiles
    finally:ledger.close()


@pytest.mark.parametrize('damage',['schema','shape','kind','simulated-live','native-backtest','native-policy','environment'])
def test_a_malformed_native_cohort_stays_unresolved_instead_of_acquiring_live_weight(damage):
    from vati.core import make_event
    from vati.learning.scope import LearningScope
    ledger=Ledger();cohort={'schema':'vati.execution-cohort/1','kind':'NATIVE_ADAPTER','environment':'LIVE'}
    if damage=='schema':cohort['schema']='different'
    elif damage=='shape':cohort['extra']='unadmitted'
    elif damage=='kind':cohort['kind']='unknown'
    elif damage=='simulated-live':cohort['kind']='SIMULATED_PAPER'
    elif damage=='native-backtest':cohort['environment']='BACKTEST'
    elif damage=='native-policy':cohort['environment']='DEMO'
    else:cohort['environment']=[]
    ledger.append(make_event(EventKind.RISK_DECISION,'vati-cycle',{'inputs':{
        'intent':{'account_alias':'source_account','trade_intent_id':'original'},
        'mandate':{'account_alias':'source_account','mode':'AUTONOMOUS_LIVE'}},
        'execution_cohort':cohort},event_time_ms=1,received_time_ms=1,correlation_id='original'))
    fact=make_event(EventKind.TCA_RECORD,'vati-cycle',{'learning_environment':'LIVE'},
        event_time_ms=2,received_time_ms=2,correlation_id='original');ledger.append(fact)
    scope=LearningScope(ledger,'source_account',Environment.LIVE)
    assert not scope.admit(fact) and scope.unresolved_refs=={fact.hash}
    ledger.close()


def test_paper_live_policy_risk_record_has_the_actual_demo_cohort_for_cold_consumers(tmp_path,eurusd):
    from vati.learning.scope import LearningScope
    cfg=config(tmp_path,eurusd);reg=AccountRegistry(cfg.registry_path);account=reg.get(cfg.account_alias)
    reg.replace(replace(account,mode='AUTONOMOUS_LIVE',demo=False,mandate_ref='fixture-signed-policy'))
    cfg.mandate=historical_mandate_dict(venue='paper',mode='AUTONOMOUS_LIVE',account_alias=account.alias,
        allowed_strategies=['FX-TREND-PULLBACK-01'])
    bars=synthetic_bars();service=SessionService(cfg,lambda now:[],clock=lambda:bars[-1].end_ms).build()
    try:
        for index,bar in enumerate(bars):
            service.runner.cycle.step(bars[:index+1],now_ms=bar.end_ms,last_quote_ms=bar.end_ms)
            if service._ledger.count(EventKind.RISK_DECISION):break
        risk=next(service._ledger.iter(EventKind.RISK_DECISION))
        assert risk.payload['inputs']['mandate']['mode']=='AUTONOMOUS_LIVE'
        assert risk.payload['execution_cohort']['environment']=='DEMO'
        assert LearningScope(service._ledger,cfg.account_alias,Environment.DEMO).admit(risk)
        live=LearningScope(service._ledger,cfg.account_alias,Environment.LIVE)
        assert not live.admit(risk) and live.excluded_refs=={risk.hash} and not live.issue
    finally:service.close();service._ledger.close()


def test_actual_book_builder_keeps_a_paper_live_policy_in_the_demo_cohort(tmp_path,eurusd):
    import os,uuid
    from vati.app.account_service import AccountCoordinatorService
    from vati.risk.serde import contract_to_dict
    if not os.environ.get('VATI_TEST_PG_DSN'):pytest.skip('requires real isolated PostgreSQL fixture')
    cfg=config(tmp_path,eurusd,ledger=os.environ['VATI_TEST_PG_DSN']);cfg.lake_root=str(tmp_path/'lake')
    reg=AccountRegistry(cfg.registry_path);account=reg.get(cfg.account_alias);alias='cohort_book_'+uuid.uuid4().hex[:12]
    reg.add(replace(account,alias=alias,mode='AUTONOMOUS_LIVE',demo=False,mandate_ref='fixture-signed-policy'))
    cfg.account_alias=alias;cfg.mandate=historical_mandate_dict(venue='paper',mode='AUTONOMOUS_LIVE',account_alias=alias,
        allowed_strategies=['FX-TREND-PULLBACK-01'])
    other=replace(eurusd,symbol='GBPUSD',base_currency='GBP')
    cfg.instruments=[{'symbol':'GBPUSD','base':'GBP','quote':'USD','contract':contract_to_dict(other)}]
    service=AccountCoordinatorService(cfg,clock=lambda:1000).build()
    try:assert service.learning.environment is Environment.DEMO
    finally:
        service._lease_store.close()
        service._ledger.close()
