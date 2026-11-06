"""Production learning consumers cannot inherit another account's shared-ledger history."""
from decimal import Decimal as D

from conftest import mandate_dict
from vati.accounts import Account, AccountRegistry
from vati.app.service import ServiceConfig, SessionService
from vati.core import Ledger, EventKind, make_event
from vati.risk.serde import contract_to_dict


def seeded_execution(ledger, alias, *, count=80, environment='DEMO'):
    for index in range(count):
        trade=f'{alias}-{environment}-{index}'
        if alias is not None:
            ledger.append(make_event(EventKind.ORDER_COMMAND,'vati-execution-router',
                {'account_alias':alias,'trade_intent_id':trade,'idempotency_key':trade},
                event_time_ms=index+1,received_time_ms=index+1,correlation_id=trade))
        ledger.append(make_event(EventKind.TCA_RECORD,'vati-cycle',
            {'trade_intent_id':trade,'learning_environment':environment,'broker':'paper','symbol':'EURUSD',
             'session':'LONDON','event_window':'QUIET','cost_ratio':'2.5','slippage':'1','rejected':False},
            event_time_ms=index+1,received_time_ms=index+1,correlation_id=trade))


def service(tmp_path, eurusd):
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='paper_lab',broker='PAPER',mode='DEMO_TRADER',currency='USD'))
    cfg=ServiceConfig(account_alias='paper_lab',symbol='EURUSD',base='EUR',quote='USD',timeframe='H1',
        contract=contract_to_dict(eurusd),mandate=mandate_dict(venue='paper',mode='DEMO_TRADER',
            account_alias='paper_lab',allowed_strategies=['FX-TREND-PULLBACK-01']),
        capsules=['FX-TREND-PULLBACK-01'],registry_path=str(tmp_path/'accounts.json'),
        ledger=str(tmp_path/'shared.sqlite'),heartbeat_path=str(tmp_path/'heartbeat.json'))
    return SessionService(cfg,lambda:[],clock=lambda:1000).build()


def test_real_service_does_not_apply_another_accounts_execution_learning(tmp_path,eurusd):
    ledger=Ledger(tmp_path/'shared.sqlite')
    seeded_execution(ledger,'another_account')
    ledger.close()
    runtime=service(tmp_path,eurusd)
    assert runtime.learning_replay.tca_observations==0
    assert runtime.learning.broker_liquidity('EURUSD')==D('1')


def test_real_service_retains_this_accounts_execution_learning(tmp_path,eurusd):
    ledger=Ledger(tmp_path/'shared.sqlite')
    seeded_execution(ledger,'paper_lab')
    ledger.close()
    runtime=service(tmp_path,eurusd)
    assert runtime.learning_replay.tca_observations==80
    assert runtime.learning.broker_liquidity('EURUSD')<D('1')


def test_unbound_learning_history_refuses_new_risk_without_guessing_an_account(tmp_path,eurusd):
    from vati.risk import KillSwitch
    ledger=Ledger(tmp_path/'shared.sqlite')
    seeded_execution(ledger,None,count=2)
    ledger.close()
    runtime=service(tmp_path,eurusd)
    assert runtime.learning_replay.tca_observations==0
    assert len(runtime.learning_replay.unresolved_scope_refs)==2
    assert 'unbound' in runtime.learning.recovery_issue
    cycle=runtime.runner.cycle
    assert cycle.kill.halted
    cycle.kill=KillSwitch()  # a cleared switch cannot erase unresolved replay provenance
    assert 'learning history' in cycle.snapshot(now_ms=1000,quote_age_ms=0).loss_streak_lock
    runtime._heartbeat('TEST')
    import json
    assert 'learning history' in json.loads((tmp_path/'heartbeat.json').read_text())['learning_history_issue']


def test_a_known_foreign_cohort_does_not_create_an_unresolved_history_fence(tmp_path,eurusd):
    ledger=Ledger(tmp_path/'shared.sqlite')
    seeded_execution(ledger,'another_account',count=2)
    ledger.close()
    runtime=service(tmp_path,eurusd)
    assert not runtime.learning.recovery_issue
    assert not runtime.runner.cycle.kill.halted
    assert len(runtime.learning_replay.excluded_scope_refs)==2


def test_live_hook_uses_the_same_account_bound_resolver_as_cold_recovery(tmp_path,eurusd):
    ledger=Ledger(tmp_path/'shared.sqlite')
    seeded_execution(ledger,'another_account',count=1)
    ledger.close()
    runtime=service(tmp_path,eurusd)
    adjustment=runtime.learning.on_tca(runtime._ledger,trade_intent_id='another_account-DEMO-0',
        symbol='EURUSD',session='LONDON',event_window='QUIET',cost_ratio=D('2.5'),slippage=D('1'))
    assert adjustment is None and not runtime.learning.brokers.profiles
    assert runtime.learning.refusals
    assert not runtime.learning.recovery_issue


def test_same_account_demo_observations_are_not_pooled_into_a_live_cohort():
    from vati.learning.hooks import LearningHooks
    from vati.learning.episodes import Environment
    from vati.learning.replay import restore_learning_runtime
    ledger=Ledger()
    seeded_execution(ledger,'paper_lab')
    learning=LearningHooks(environment=Environment.LIVE,account_alias='paper_lab')
    report=restore_learning_runtime(ledger,learning,{})
    assert report.tca_observations==0 and len(report.excluded_scope_refs)==80
    assert not learning.recovery_issue
    assert not learning.brokers.profiles


import pytest

@pytest.mark.parametrize('account,expected', [('paper_lab','DEGRADED'),('another_account','DEMO'),(None,'DEMO')])
def test_automatic_capsule_replay_cannot_cross_native_account_scope(eurusd,account,expected):
    from test_backtest_runner_cli import fx_cfg,fx_engine
    from vati.learning.hooks import LearningHooks
    from vati.learning.episodes import Environment
    from vati.learning.replay import restore_learning_runtime
    from vati.risk.contracts import StrategyState
    ledger=Ledger()
    seeded_execution(ledger,account,count=1)
    candidate=fx_engine(fx_cfg(eurusd))
    sid='FX-TREND-PULLBACK-01'
    parent=candidate.registry.get(sid)
    changed=candidate.registry.demote(sid,StrategyState.DEGRADED,reason='observed native process defects')
    ledger.append(make_event(EventKind.CAPSULE_STATE,'vati-cycle',
        {'strategy_id':sid,'from':parent.state.value,'to':'DEGRADED','capsule_hash':changed.capsule_hash,
         'supersedes':parent.capsule_hash,'capsule':changed.data,'by':'vati-learning','authority':'AUTOMATIC_DEMOTION_ONLY'},
        event_time_ms=10,received_time_ms=10,correlation_id=f'{account}-DEMO-0'))
    engine=fx_engine(fx_cfg(eurusd))
    learning=LearningHooks(environment=Environment.DEMO,account_alias='paper_lab')
    result=restore_learning_runtime(ledger,learning,{'EURUSD':engine})
    assert engine.registry.get(sid).state.value==expected
    assert result.demotions_restored==int(expected=='DEGRADED')
    assert bool(learning.recovery_issue)==(account is None)


def test_a_payload_account_label_cannot_manufacture_native_learning_ownership(tmp_path,eurusd):
    ledger=Ledger(tmp_path/'shared.sqlite')
    event=make_event(EventKind.TCA_RECORD,'vati-cycle',
        {'account_alias':'paper_lab','learning_environment':'DEMO','broker':'paper','symbol':'EURUSD',
         'session':'LONDON','event_window':'QUIET','cost_ratio':'2.5','slippage':'1','rejected':False},
        event_time_ms=1,received_time_ms=1,correlation_id='unbound')
    ledger.append(event);ledger.close()
    runtime=service(tmp_path,eurusd)
    assert runtime.learning_replay.unresolved_scope_refs==(event.hash,)
    assert runtime.runner.cycle.kill.halted


@pytest.mark.parametrize('account,expected', [('paper_lab',3),('another_account',0),(None,0)])
def test_real_service_quality_and_lessons_share_the_native_account_boundary(tmp_path,eurusd,account,expected):
    from vati.cognition.attribution import DecisionQualityInputs,DecisionQualityLedger
    from vati.learning.episodes import LessonStore,Environment,lesson_from_verdict
    sid='FX-TREND-PULLBACK-01'
    ledger=Ledger(tmp_path/'shared.sqlite')
    seeded_execution(ledger,account,count=3)
    quality=DecisionQualityLedger(ledger=ledger)
    lessons=LessonStore(ledger=ledger)
    for index in range(3):
        verdict=quality.record(DecisionQualityInputs(trade_intent_id=f'{account}-DEMO-{index}',strategy_id=sid),
            symbol='EURUSD',r_multiple=D('1'),now_ms=index+10)
        lessons.record(lesson_from_verdict(verdict,symbol='EURUSD',regime='TREND',session='LONDON',
            environment=Environment.DEMO,now_ms=index+10))
    ledger.close()
    runtime=service(tmp_path,eurusd)
    cycle=runtime.runner.cycle
    assert len(cycle.decision_quality.verdicts_for(sid))==expected
    assert len(cycle.lessons.lessons_for(sid,limit=5))==expected
    if expected:
        assert cycle.decision_quality.health_multiplier(sid)<1
    else:
        assert cycle.decision_quality.health_multiplier(sid)==1


def test_postgres_native_learning_scope_uses_the_same_account_boundary():
    import os,uuid
    dsn=os.environ.get('VATI_TEST_PG_DSN')
    if not dsn or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
        pytest.skip('explicit isolated PostgreSQL learning fixture not available')
    from vati.core.ledger_pg import PostgresLedger
    from vati.learning.hooks import LearningHooks
    from vati.learning.episodes import Environment
    from vati.learning.replay import restore_learning_runtime
    ledger=PostgresLedger(dsn,ledger_name='learn_'+uuid.uuid4().hex[:12])
    try:
        seeded_execution(ledger,'paper_lab',count=2)
        seeded_execution(ledger,'another_account',count=2)
        learning=LearningHooks(environment=Environment.DEMO,account_alias='paper_lab')
        report=restore_learning_runtime(ledger,learning,{})
        assert report.tca_observations==2
        assert len(report.excluded_scope_refs)==2 and not report.unresolved_scope_refs
        assert ledger.verify_chain()==(True,8)
        from vati.cognition.attribution import DecisionQualityInputs,DecisionQualityLedger
        from vati.learning.episodes import LessonStore,lesson_from_verdict
        quality=DecisionQualityLedger(ledger=ledger)
        lessons=LessonStore(ledger=ledger)
        for alias in ('paper_lab','another_account'):
            for index in range(2):
                verdict=quality.record(DecisionQualityInputs(trade_intent_id=f'{alias}-DEMO-{index}',strategy_id='strategy'),
                    symbol='EURUSD',r_multiple=D('1'),now_ms=index+10)
                lessons.record(lesson_from_verdict(verdict,symbol='EURUSD',regime='TREND',session='LONDON',
                    environment=Environment.DEMO,now_ms=index+10))
        scope=learning.resolver(ledger).scope
        restored_quality=DecisionQualityLedger(ledger=ledger,scope=scope)
        restored_lessons=LessonStore(ledger=ledger,scope=scope)
        assert restored_quality.restore_from_ledger(ledger)==2
        assert restored_lessons.restore_from_ledger(ledger)==2
        assert not learning.recovery_issue
        assert ledger.verify_chain()==(True,16)
    finally:
        ledger.close()
