"""Actual service news builders must expose unavailable sources and recover history."""
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from vati.app.service import SessionService
from vati.app.account_service import AccountCoordinatorService
from vati.core.ledger import Ledger
from vati.core.events import EventKind
from vati.events.news_ingress import Headline,NewsIngress,SourceTrust,rows_from_file

NOW=1_800_000_000_000


@pytest.fixture
def ledger(tmp_path):
    value=Ledger(tmp_path/'runtime.sqlite')
    try:yield value
    finally:value.close()


def configured(path):
    return {'path':str(path),'sources':[{'source_id':'publisher','trust':'T1_PRIMARY'}]}


def row(title='Policy decision'):
    return {'source':'publisher','title':title,'published_ms':NOW,'observed_ms':NOW,
            'symbols':'EURUSD','severity':'1'}


def service(kind,ledger,config):
    cfg=SimpleNamespace(news=config,symbol='EURUSD',account_alias='acct')
    if kind=='session':
        value=SessionService(cfg,lambda _now:[],clock=lambda:NOW)
        value.runner=SimpleNamespace(cycle=SimpleNamespace(ledger=ledger,
            engine=SimpleNamespace(m=SimpleNamespace(news_event_risk={}))))
    else:value=AccountCoordinatorService(cfg,clock=lambda:NOW)
    value._ledger=ledger
    return value


def build(value,kind):
    value.news=value._build_news() if kind=='session' else value._build_news(None)
    return value.news


@pytest.mark.parametrize('kind',['session','account'])
def test_service_builder_restores_durable_history_when_the_file_is_missing(tmp_path,ledger,kind):
    h=Headline(source_id='publisher',trust=SourceTrust.T1_PRIMARY,published_ms=NOW,
        observed_ms=NOW,title='Original policy decision',symbols=('EURUSD',),severity=Decimal('1'))
    NewsIngress(ledger=ledger).ingest(h,now_ms=NOW)
    value=service(kind,ledger,configured(tmp_path/'missing.jsonl'));news=build(value,kind)
    assert news.headlines()==[h]
    health=news.report(now_ms=NOW)['source_health']
    assert health['state']=='MISSING' and health['coverage']=='UNKNOWN'
    assert health['provider_qualified'] is False


@pytest.mark.parametrize('kind',['session','account'])
def test_bad_news_file_does_not_abort_the_service_news_builder(tmp_path,ledger,kind):
    path=tmp_path/'news.json';path.write_text('{')
    value=service(kind,ledger,configured(path))
    try:news=build(value,kind)
    except Exception as exc:pytest.fail('optional unreadable news aborted builder: '+type(exc).__name__)
    assert news.report(now_ms=NOW)['source_health']['state']=='UNREADABLE'
    assert news.headlines()==[]


@pytest.mark.parametrize('kind',['session','account'])
def test_missing_refresh_is_unknown_coverage_not_an_empty_success(tmp_path,ledger,kind):
    value=service(kind,ledger,configured(tmp_path/'missing.json'));build(value,kind)
    result=value.refresh_news(NOW)
    assert result.get('source_health',{}).get('state')=='MISSING'
    assert result['source_health']['coverage']=='UNKNOWN'


def test_malformed_jsonl_line_keeps_both_valid_neighbors_and_a_parse_diagnostic(tmp_path,ledger):
    path=tmp_path/'news.jsonl';path.write_text(json.dumps(row('First'))+'\n{bad\n'+json.dumps(row('Second'))+'\n')
    news=NewsIngress(ledger=ledger)
    try:counts=news.ingest_rows(rows_from_file(path),now_ms=NOW)
    except Exception as exc:pytest.fail('one malformed line discarded its valid neighbors: '+type(exc).__name__)
    assert counts=={'accepted':2,'duplicates':0,'skipped':1}
    assert {h.title for h in news.headlines()}=={'First','Second'}
    assert 'line 2' in news.skipped[0]['error'].lower()


@pytest.mark.parametrize('bad',[{}, {'headlines':None}, {'headlines':{}}])
def test_invalid_file_envelope_cannot_become_an_empty_success(tmp_path,bad):
    path=tmp_path/'news.json';path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):rows_from_file(path)


@pytest.mark.parametrize('kind',['session','account'])
def test_corrected_file_recovers_from_partial_without_erasing_original_history(tmp_path,ledger,kind):
    path=tmp_path/'news.jsonl';path.write_text(json.dumps(row('First'))+'\n{bad\n')
    value=service(kind,ledger,configured(path));news=build(value,kind)
    assert news.report(now_ms=NOW)['source_health']['state']=='PARTIAL'
    path.write_text(json.dumps(row('First'))+'\n'+json.dumps(row('Second'))+'\n')
    result=value.refresh_news(NOW+1)
    assert result['source_health']['state']=='READY_DECLARED'
    assert {h.title for h in news.headlines()}=={'First','Second'}
    assert result['source_health']['skipped_in_batch']==0


@pytest.mark.parametrize('kind',['session','account'])
def test_absent_optional_news_configuration_keeps_the_existing_disabled_behavior(ledger,kind):
    assert build(service(kind,ledger,{}),kind) is None


def health_records(ledger):
    return [e for e in ledger.iter(EventKind.MARKET_DATA_HEALTH)
            if e.producer=='vati-news-file-health']


@pytest.mark.parametrize('kind',['session','account'])
def test_repeated_snapshot_check_retains_original_health_receipt_without_publisher_freshness(tmp_path,ledger,kind):
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]))
    value=service(kind,ledger,configured(path));build(value,kind)
    original=health_records(ledger)[0]
    result=value.refresh_news(NOW+1000);health=result['source_health']
    assert health_records(ledger)==[original]
    assert health['receipt_hash']==original.hash and health['transition_observed_ms']==NOW
    assert health['checked_ms']==NOW+1000 and health['coverage']=='DECLARED_SNAPSHOT_ONLY'
    assert health['provider_qualified'] is False and health['live_eligible'] is False


def test_file_health_returning_to_an_old_state_keeps_each_actual_transition(tmp_path,ledger):
    path=tmp_path/'news.json';value=service('account',ledger,configured(path));build(value,'account')
    path.write_text(json.dumps([row()]));first=value.refresh_news(NOW+1)['source_health']
    path.unlink();assert value.refresh_news(NOW+2)['source_health']['state']=='MISSING'
    path.write_text(json.dumps([row()]));second=value.refresh_news(NOW+3)['source_health']
    records=health_records(ledger)
    assert [e.payload['material']['state'] for e in records]==['MISSING','READY_DECLARED','MISSING','READY_DECLARED']
    assert first['receipt_hash']!=second['receipt_hash']
    assert ledger.count(EventKind.NEWS_HEADLINE)==1 and ledger.verify_chain()[0]


@pytest.mark.parametrize('kind',['session','account'])
def test_health_persistence_failure_is_unknown_and_reconciles_without_duplicate_news(tmp_path,ledger,monkeypatch,kind):
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]))
    value=service(kind,ledger,configured(path));append=ledger.append
    def unavailable(event):
        if event.producer=='vati-news-file-health':raise OSError('fixture health writer unavailable')
        return append(event)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',unavailable);news=build(value,kind)
    assert news.report(now_ms=NOW)['source_health']['state']=='PERSISTENCE_UNAVAILABLE'
    assert health_records(ledger)==[] and ledger.count(EventKind.NEWS_HEADLINE)==1
    result=value.refresh_news(NOW+1)
    assert result['source_health']['state']=='READY_DECLARED' and len(health_records(ledger))==1
    assert ledger.count(EventKind.NEWS_HEADLINE)==1


def test_actual_health_commit_reply_loss_reads_back_the_original_transition(tmp_path,ledger,monkeypatch):
    from contextlib import contextmanager
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]));value=service('account',ledger,configured(path));atomic=ledger.atomic
    @contextmanager
    def lose_health_reply():
        outer=not ledger._conn.in_transaction;before=len(health_records(ledger))
        with atomic():yield ledger
        if outer and len(health_records(ledger))>before:raise OSError('fixture lost committed health reply')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'atomic',lose_health_reply);news=build(value,'account')
    assert news.source_health['state']=='PERSISTENCE_UNAVAILABLE'
    original=health_records(ledger)[0]
    assert value.refresh_news(NOW+1)['source_health']['receipt_hash']==original.hash
    assert health_records(ledger)==[original] and ledger.verify_chain()[0]


@pytest.mark.parametrize('kind',['session','account'])
def test_recovery_refusal_preserves_corrupt_originals_without_writing_new_health(tmp_path,ledger,kind):
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]))
    news=NewsIngress(ledger=ledger);news.ingest(news.headline_from_row(row()),now_ms=NOW)
    ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE kind='NEWS_HEADLINE'")
    head=ledger.head();count=ledger.count();value=service(kind,ledger,configured(path));news=build(value,kind)
    assert news.source_health['state']=='RECOVERY_UNAVAILABLE' and news.source_health['coverage']=='UNKNOWN'
    assert ledger.head()==head and ledger.count()==count


@pytest.mark.parametrize('limits',[{'max_file_bytes':10},{'max_rows':1}])
def test_file_capacity_refusal_does_not_fake_empty_coverage_or_ingest_partial_data(tmp_path,ledger,limits):
    path=tmp_path/'news.json';path.write_text(json.dumps([row('First'),row('Second')]))
    value=service('account',ledger,configured(path)|limits);news=build(value,'account')
    assert news.source_health['state']=='CAPACITY_EXCEEDED' and news.source_health['coverage']=='UNKNOWN'
    assert ledger.count(EventKind.NEWS_HEADLINE)==0


@pytest.mark.parametrize('kind',['session','account'])
def test_invalid_builder_clock_cannot_be_written_as_a_valid_health_clock(tmp_path,ledger,kind):
    value=service(kind,ledger,configured(tmp_path/'news.json')|{'max_rows':0});value.clock=lambda:True
    news=build(value,kind)
    assert news.source_health['state']=='CLOCK_UNAVAILABLE' and news.source_health['checked_ms'] is None
    assert health_records(ledger)==[]


@pytest.mark.parametrize('kind',['session','account'])
def test_partial_batch_publication_stays_unknown_until_originals_are_reconciled(tmp_path,ledger,monkeypatch,kind):
    path=tmp_path/'news.json';path.write_text(json.dumps([row('First'),row('Second')]))
    value=service(kind,ledger,configured(path));append=ledger.append
    def fail_second(event):
        if event.kind is EventKind.NEWS_HEADLINE and event.payload['title']=='Second':
            raise OSError('fixture second publication unavailable')
        return append(event)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',fail_second);news=build(value,kind)
    assert news.source_health['state']=='PUBLICATION_UNKNOWN' and ledger.count(EventKind.NEWS_HEADLINE)==1
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',fail_second);result=value.refresh_news(NOW)
    assert result['accepted'] is None and result['duplicates'] is None and result['reconcile_required']
    result=value.refresh_news(NOW+1)
    assert result['source_health']['state']=='READY_DECLARED'
    assert ledger.count(EventKind.NEWS_HEADLINE)==ledger.count(EventKind.NEWS_OBSERVATION)==2


def test_independent_health_readback_failure_does_not_turn_a_committed_row_into_success(tmp_path,ledger,monkeypatch):
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]));value=service('account',ledger,configured(path));read=ledger.iter
    def unavailable_after_commit(kind=None,correlation_id=None):
        if kind is EventKind.MARKET_DATA_HEALTH and not ledger._conn.in_transaction:return iter(())
        return read(kind,correlation_id=correlation_id)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'iter',unavailable_after_commit);news=build(value,'account')
    assert news.source_health['state']=='PERSISTENCE_UNAVAILABLE'
    original=health_records(ledger)[0]
    assert value.refresh_news(NOW+1)['source_health']['receipt_hash']==original.hash
    assert health_records(ledger)==[original]


@pytest.mark.parametrize('mode',['empty','unconfigured','invalid-utf8'])
def test_noncovering_inputs_keep_their_distinct_source_states(tmp_path,ledger,mode):
    path=tmp_path/'news.json';config=configured(path)
    if mode=='empty':path.write_text('[]');expected='EMPTY_DECLARED'
    elif mode=='unconfigured':config.pop('path');expected='UNCONFIGURED'
    else:path.write_bytes(b'\xff');expected='UNREADABLE'
    value=service('account',ledger,config);news=build(value,'account')
    assert news.source_health['state']==expected
    assert news.source_health['provider_qualified'] is False and news.source_health['live_eligible'] is False
    assert ledger.count(EventKind.NEWS_HEADLINE)==0


@pytest.mark.parametrize('kind',['session','account'])
def test_assessment_failure_is_explicit_and_preserves_the_previous_reduction(tmp_path,ledger,monkeypatch,kind):
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]));value=service(kind,ledger,configured(path));news=build(value,kind)
    prior={'EURUSD':Decimal('0.4')}
    if kind=='session':value.runner.cycle.engine.m.news_event_risk=prior
    else:value.evaluators={'EURUSD':SimpleNamespace(engine=SimpleNamespace(m=SimpleNamespace(news_event_risk=prior)))}
    def unavailable(*_args,**_kwargs):raise OSError('fixture assessment unavailable')
    monkeypatch.setattr(news,'candidate_risk',unavailable)
    result=value.refresh_news(NOW) if kind=='session' else value._apply_news_event_risk(NOW)
    state=result.get('risk_state') if kind=='session' else result.get('EURUSD',{}).get('state')
    assert state=='UNAVAILABLE' and prior=={'EURUSD':Decimal('0.4')}


def test_changed_file_capacity_policy_gets_a_new_health_receipt_without_rewriting_history(tmp_path,ledger):
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]));value=service('account',ledger,configured(path)|{'max_rows':100})
    news=build(value,'account');original=health_records(ledger)[0];first=news.source_health['source_ref']
    value.cfg.news['max_rows']=101
    result=value.refresh_news(NOW+1)
    assert result['source_health']['source_ref']!=first
    assert len(health_records(ledger))==2 and health_records(ledger)[0]==original
    assert ledger.count(EventKind.NEWS_HEADLINE)==1


def test_file_health_does_not_count_a_future_observation_as_an_available_headline(tmp_path,ledger):
    path=tmp_path/'news.json';path.write_text(json.dumps([row()|{'observed_ms':NOW+1000}]))
    value=service('account',ledger,configured(path));news=build(value,'account')
    assert news.headlines(as_of_ms=NOW)==[]
    assert news.source_health['last_known_headlines']==0


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_native_health_writers_preserve_one_unchanged_snapshot_receipt(tmp_path,backend):
    from concurrent.futures import ThreadPoolExecutor
    from test_news_durable_publication import native_factory
    factory=native_factory(tmp_path,backend);seed=factory();seed.close()
    path=tmp_path/'news.json';path.write_text(json.dumps([row()]))
    def check(_):
        value=factory()
        try:
            instance=service('account',value,configured(path));news=build(instance,'account')
            return news.source_health['receipt_hash']
        finally:value.close()
    with ThreadPoolExecutor(max_workers=2) as pool:hashes=list(pool.map(check,range(4)))
    value=factory()
    try:
        assert len(set(hashes))==1 and len(health_records(value))==1
        assert value.count(EventKind.NEWS_HEADLINE)==value.count(EventKind.NEWS_OBSERVATION)==1
        assert value.verify_chain()[0]
    finally:value.close()


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_native_health_commit_reply_loss_reconciles_the_original(tmp_path,backend,monkeypatch):
    from contextlib import contextmanager
    from test_news_durable_publication import native_factory
    factory=native_factory(tmp_path,backend);value=factory();path=tmp_path/'news.json';path.write_text(json.dumps([row()]));atomic=value.atomic
    @contextmanager
    def lose_reply():
        outer=value._atomic_depth==0 if backend=='postgres' else not value._conn.in_transaction
        before=len(health_records(value))
        with atomic():yield value
        if outer and len(health_records(value))>before:raise OSError('fixture actual native health reply lost')
    try:
        instance=service('account',value,configured(path))
        with monkeypatch.context() as patch:
            patch.setattr(value,'atomic',lose_reply);news=build(instance,'account')
        assert news.source_health['state']=='PERSISTENCE_UNAVAILABLE'
        original=health_records(value)[0]
    finally:value.close()
    value=factory()
    try:
        cold=build(service('account',value,configured(path)),'account')
        assert cold.source_health['receipt_hash']==original.hash and health_records(value)==[original]
        assert value.verify_chain()[0]
    finally:value.close()


def test_full_paper_session_builder_survives_bad_news_and_keeps_the_same_cycle_binding(tmp_path,eurusd):
    from conftest import mandate_dict
    from test_backtest_runner_cli import synthetic_bars
    from vati.accounts import Account,AccountRegistry
    from vati.app.service import ServiceConfig,lake_bar_source
    from vati.market_data.feeds import BarLake
    from vati.risk.serde import contract_to_dict
    AccountRegistry(tmp_path/'accounts.json').add(Account(alias='paper_lab',broker='PAPER',mode='DEMO_TRADER',currency='USD'))
    lake=BarLake(tmp_path/'lake');bars=synthetic_bars();lake.write(bars,symbol='EURUSD',timeframe='H1',source='fixture',provenance='SYNTHETIC')
    path=tmp_path/'news.json';path.write_text('{');at=bars[100].end_ms
    cfg=ServiceConfig(account_alias='paper_lab',symbol='EURUSD',base='EUR',quote='USD',timeframe='H1',
        contract=contract_to_dict(eurusd),mandate=mandate_dict(venue='paper',mode='DEMO_TRADER',account_alias='paper_lab',allowed_strategies=['FX-TREND-PULLBACK-01']),
        capsules=['FX-TREND-PULLBACK-01'],registry_path=str(tmp_path/'accounts.json'),ledger=str(tmp_path/'session.sqlite'),
        lake_root=str(tmp_path/'lake'),heartbeat_path=str(tmp_path/'heartbeat.json'),news=configured(path))
    value=SessionService(cfg,lake_bar_source(lake,'EURUSD','H1'),clock=lambda:at)
    try:
        value.build()
        assert value.news.source_health['state']=='UNREADABLE' and value.runner.cycle.news is value.news
        value._heartbeat('BUILT')
        heartbeat=json.loads(Path(cfg.heartbeat_path).read_text())
        assert heartbeat.get('news',{}).get('source_health',{}).get('state')=='UNREADABLE'
        assert heartbeat['account_alias']=='paper_lab'
        path.write_text(json.dumps([row()|{'published_ms':at,'observed_ms':at}]))
        assert value.refresh_news(at)['source_health']['state']=='READY_DECLARED'
        assert value.runner.cycle.news is value.news and value.news.source_health['provider_qualified'] is False
        value._heartbeat('BUILT')
        assert json.loads(Path(cfg.heartbeat_path).read_text())['news']['source_health']['state']=='READY_DECLARED'
    finally:
        value.close()
        if value._ledger is not None:value._ledger.close()


@pytest.mark.parametrize('enabled',[False,True])
def test_account_owner_heartbeat_reports_news_state_before_the_first_bar(tmp_path,ledger,enabled):
    value=service('account',ledger,configured(tmp_path/'missing.json') if enabled else {})
    value.cfg.heartbeat_path=str(tmp_path/'heartbeat.json');build(value,'account')
    value._heartbeat('BUILT');heartbeat=json.loads(Path(value.cfg.heartbeat_path).read_text())
    assert heartbeat.get('news',{}).get('source_health',{}).get('state')==('MISSING' if enabled else 'DISABLED')
    assert heartbeat['account_alias']=='acct' and heartbeat['owner_policy_current'] is False
