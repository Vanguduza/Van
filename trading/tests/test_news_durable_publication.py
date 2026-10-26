"""Real ledger publication must precede remembered news completion."""
from contextlib import contextmanager
from decimal import Decimal

import pytest

from vati.core.events import EventKind
from vati.core.events import make_event
from vati.core.ledger import Ledger
from vati.events.news_ingress import Headline, NewsIngress, NewsIngressError, SourceTrust

NOW=1_800_000_000_000


def story(**changes):
    return Headline(**(dict(source_id='publisher',trust=SourceTrust.T1_PRIMARY,
        published_ms=NOW,observed_ms=NOW,title='Emergency policy decision',
        symbols=('EURUSD',),severity=Decimal('1'))|changes))


@pytest.fixture
def ledger(tmp_path):
    value=Ledger(tmp_path/'news.sqlite')
    try:yield value
    finally:value.close()


def test_failed_headline_publication_does_not_become_memory_success(ledger,monkeypatch):
    news=NewsIngress(ledger=ledger);h=story()
    def unavailable(_event):raise OSError('fixture writer unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',unavailable)
        with pytest.raises(OSError):news.ingest(h,now_ms=NOW)
    assert news.headlines()==[] and news.relayed_by(h.headline_id)==()
    assert news.candidate_risk('EURUSD',now_ms=NOW)==(Decimal('1'),Decimal('0'),())
    assert ledger.count()==0


def test_cold_replay_reads_the_original_instead_of_appending_a_new_headline(ledger):
    h=story();NewsIngress(ledger=ledger).ingest(h,now_ms=NOW)
    original=next(ledger.iter(EventKind.NEWS_HEADLINE));head=ledger.head()
    assert NewsIngress(ledger=ledger).ingest(h,now_ms=NOW+1000) is None
    assert ledger.count(EventKind.NEWS_HEADLINE)==1 and ledger.head()==head
    assert next(ledger.iter(EventKind.NEWS_HEADLINE)).hash==original.hash


def test_lost_actual_sql_commit_reply_does_not_advance_memory_and_replay_preserves_original(ledger,monkeypatch):
    news=NewsIngress(ledger=ledger);h=story();atomic=ledger.atomic
    @contextmanager
    def commit_then_lose_reply():
        outer=not ledger._conn.in_transaction
        with atomic():yield ledger
        if outer:raise OSError('fixture ACK lost after actual SQL commit')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'atomic',commit_then_lose_reply)
        with pytest.raises(OSError,match='actual SQL commit'):news.ingest(h,now_ms=NOW)
    original=next(ledger.iter(EventKind.NEWS_HEADLINE));head=ledger.head()
    assert news.headlines()==[] and news.relayed_by(h.headline_id)==()
    assert news.ingest(h,now_ms=NOW+1000) is None
    assert ledger.count(EventKind.NEWS_HEADLINE)==1 and ledger.head()==head
    assert next(ledger.iter(EventKind.NEWS_HEADLINE)).hash==original.hash
    assert news.candidate_risk('EURUSD',now_ms=NOW,persist=False)[1]==Decimal('1')


def test_independent_original_readback_is_required_before_headline_success(ledger,monkeypatch):
    news=NewsIngress(ledger=ledger);h=story();read=ledger.iter
    def unavailable_after_commit(kind=None,correlation_id=None):
        if kind is EventKind.NEWS_HEADLINE and not ledger._conn.in_transaction:return iter(())
        return read(kind,correlation_id=correlation_id)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'iter',unavailable_after_commit)
        with pytest.raises(OSError,match='not confirmed'):news.ingest(h,now_ms=NOW)
    assert ledger.count(EventKind.NEWS_HEADLINE)==1 and news.headlines()==[]


def test_missing_known_original_cannot_be_recreated_or_reported_complete(ledger):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h)
    ledger._conn.execute('DELETE FROM events WHERE kind=?',(EventKind.NEWS_HEADLINE.value,))
    with pytest.raises(NewsIngressError,match='missing'):news.ingest(h)
    assert ledger.count(EventKind.NEWS_HEADLINE)==0


def test_corrupt_original_cannot_be_ignored_by_a_cold_publisher(ledger):
    h=story();NewsIngress(ledger=ledger).ingest(h)
    ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE kind=?",(EventKind.NEWS_HEADLINE.value,))
    head=ledger.head()
    with pytest.raises(NewsIngressError):NewsIngress(ledger=ledger).ingest(h)
    assert ledger.count(EventKind.NEWS_HEADLINE)==1 and ledger.head()==head


def test_failed_impact_publication_does_not_become_remembered_success(ledger,monkeypatch):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h);append=ledger.append
    def unavailable(event):
        if event.kind is EventKind.EVENT_IMPACT:raise OSError('fixture impact writer unavailable')
        return append(event)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',unavailable)
        with pytest.raises(OSError):news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    assert news.impacts_for('p')==[] and ledger.count(EventKind.EVENT_IMPACT)==0


def test_identical_impact_replay_keeps_one_original_receipt_and_memory_record(ledger):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h)
    a=news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    original=next(ledger.iter(EventKind.EVENT_IMPACT));head=ledger.head()
    b=news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    assert a==b and ledger.count(EventKind.EVENT_IMPACT)==1 and ledger.head()==head
    assert next(ledger.iter(EventKind.EVENT_IMPACT)).hash==original.hash
    assert news.impacts_for('p')==[a]


def test_a_distinct_relay_observation_is_durable_without_rewriting_the_original(ledger):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h,now_ms=NOW)
    original=next(ledger.iter(EventKind.NEWS_HEADLINE))
    relay=story(source_id='relay',observed_ms=NOW+1000);news.ingest(relay,now_ms=NOW+1000)
    records=list(ledger.iter())
    assert any(e.payload.get('full_claim',{}).get('source_id')=='relay' for e in records)
    assert ledger.count(EventKind.NEWS_HEADLINE)==1
    assert next(ledger.iter(EventKind.NEWS_HEADLINE))==original


def test_cold_relay_replay_keeps_its_original_availability_instead_of_retry_time(ledger):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h,now_ms=NOW)
    relay=story(source_id='relay',observed_ms=NOW+1000);news.ingest(relay,now_ms=NOW+1000)
    head=ledger.head();cold=NewsIngress(ledger=ledger)
    assert cold.ingest(relay,now_ms=NOW+2000) is None
    impacts=cold.assess_subject(subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW+1000,persist=False)
    assert len(impacts)==1 and 'relay' in impacts[0].evidence_refs
    assert ledger.head()==head


def test_failed_relay_publication_cannot_become_remembered_provenance(ledger,monkeypatch):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h);append=ledger.append
    def unavailable(event):
        if event.kind.value=='NEWS_OBSERVATION':raise OSError('fixture relay writer unavailable')
        return append(event)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',unavailable)
        with pytest.raises(OSError):news.ingest(story(source_id='relay'))
    assert news.relayed_by(h.headline_id)==('publisher',)


def test_missing_known_observation_receipt_cannot_be_recreated(ledger):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h)
    relay=story(source_id='relay');news.ingest(relay)
    ledger._conn.execute("DELETE FROM events WHERE kind='NEWS_OBSERVATION' AND json_extract(payload_json,'$.full_claim.source_id')='relay'")
    with pytest.raises(NewsIngressError,match='missing'):news.ingest(relay)


@pytest.mark.parametrize('missing',[EventKind.NEWS_HEADLINE,EventKind.NEWS_OBSERVATION])
def test_cold_retry_cannot_recreate_a_missing_required_original_receipt(ledger,missing):
    h=story();NewsIngress(ledger=ledger).ingest(h,now_ms=NOW)
    ledger._conn.execute('DELETE FROM events WHERE kind=?',(missing.value,))
    head=ledger.head();count=ledger.count()
    with pytest.raises(NewsIngressError,match='missing'):
        NewsIngress(ledger=ledger).ingest(h,now_ms=NOW+1000)
    assert ledger.head()==head and ledger.count()==count


def test_read_only_cold_recovery_restores_full_claims_and_relay_clocks(ledger,monkeypatch):
    news=NewsIngress(ledger=ledger);h=story(title='A'*700,body_excerpt='B'*2000,url='https://example.invalid/'+'c'*700)
    news.ingest(h,now_ms=NOW+100)
    relay=story(source_id='relay',title=h.title,body_excerpt=h.body_excerpt,url=h.url,observed_ms=NOW+1000)
    news.ingest(relay,now_ms=NOW+1500);head=ledger.head()
    def forbidden(_event):raise AssertionError('recovery must not publish')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',forbidden)
        cold=NewsIngress.from_ledger(ledger)
    assert cold.headlines()==[h] and cold.relayed_by(h.headline_id)==('publisher','relay')
    assert cold.relayed_by(h.headline_id,as_of_ms=NOW+100)==('publisher',)
    assert cold.relayed_by(h.headline_id,as_of_ms=NOW+1500)==('publisher','relay')
    assert cold.headlines(as_of_ms=NOW)==[] and ledger.head()==head
    assert cold.ingest(relay,now_ms=NOW+2000) is None and ledger.head()==head


def test_legacy_original_and_untimed_relay_labels_are_preserved_without_inventing_clocks(ledger):
    h=story();payload=h.body()|{'ingress_version':'news-ingress/5.1.0','relayed_by':['publisher','untimed']}
    original=make_event(EventKind.NEWS_HEADLINE,'vati-news-ingress',payload,event_time_ms=NOW,received_time_ms=NOW+100,correlation_id=h.headline_id)
    ledger.append(original);head=ledger.head();cold=NewsIngress.from_ledger(ledger)
    assert cold.headlines()==[h] and cold.relayed_by(h.headline_id)==('publisher','untimed')
    assert cold.relayed_by(h.headline_id,as_of_ms=NOW+100)==('publisher',)
    assert cold.report(now_ms=NOW+100)['legacy_unqualified_relays']=={h.headline_id:['untimed']}
    assert ledger.head()==head and next(ledger.iter())==original


@pytest.mark.parametrize('fault',['corruption','missing-observation','capacity','chain'])
def test_invalid_or_incomplete_recovery_refuses_partial_success_without_rewriting(ledger,fault):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h)
    if fault=='corruption':ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE kind='NEWS_HEADLINE'")
    elif fault=='missing-observation':ledger._conn.execute("DELETE FROM events WHERE kind='NEWS_OBSERVATION'")
    elif fault=='chain':ledger._conn.execute("UPDATE events SET prev_hash='broken' WHERE kind='NEWS_OBSERVATION'")
    head=ledger.head();count=ledger.count()
    with pytest.raises(NewsIngressError):NewsIngress.from_ledger(ledger,max_events=1 if fault=='capacity' else 100)
    assert ledger.head()==head and ledger.count()==count


def test_two_actual_sql_writers_keep_one_original_and_one_observation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    path=tmp_path/'shared.sqlite';seed=Ledger(path);seed.close();barrier=threading.Barrier(2)
    def publish(offset):
        value=Ledger(path)
        try:
            news=NewsIngress(ledger=value);barrier.wait(timeout=10)
            return news.ingest(story(),now_ms=NOW+offset)
        finally:value.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(publish,offset) for offset in (100,200)]
        results=[f.result(timeout=30) for f in futures]
    value=Ledger(path)
    try:
        assert sum(result is not None for result in results)==1
        assert value.count(EventKind.NEWS_HEADLINE)==value.count(EventKind.NEWS_OBSERVATION)==1
        assert value.verify_chain()[0]
        cold=NewsIngress.from_ledger(value)
        at=next(value.iter(EventKind.NEWS_OBSERVATION)).received_time_ms
        assert cold.headlines(as_of_ms=at)==[story()] and cold.headlines(as_of_ms=at-1)==[]
    finally:value.close()


def test_same_time_assessment_with_new_original_evidence_gets_a_distinct_impact(ledger):
    news=NewsIngress(ledger=ledger);h=story();news.ingest(h,now_ms=NOW)
    a=news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    original=next(ledger.iter(EventKind.EVENT_IMPACT))
    news.ingest(story(source_id='relay'),now_ms=NOW)
    b=news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    assert a.impact_id!=b.impact_id and 'relay' not in a.evidence_refs and 'relay' in b.evidence_refs
    assert list(ledger.iter(EventKind.EVENT_IMPACT))[0]==original
    assert ledger.count(EventKind.EVENT_IMPACT)==2
    cold=NewsIngress.from_ledger(ledger)
    assert cold.impacts_for('p')==[a,b]


def test_actual_process_death_after_commit_recovers_without_duplicate_publication(tmp_path):
    import subprocess,sys
    path=tmp_path/'process.sqlite'
    code='''
import os,sys
from decimal import Decimal
from vati.core.ledger import Ledger
from vati.core.events import EventKind
from vati.events.news_ingress import Headline,NewsIngress,SourceTrust
ledger=Ledger(sys.argv[1]);read=ledger.iter
def die_after_commit(kind=None,correlation_id=None):
    if kind is EventKind.NEWS_HEADLINE and not ledger._conn.in_transaction:os._exit(77)
    return read(kind,correlation_id=correlation_id)
ledger.iter=die_after_commit
NewsIngress(ledger=ledger).ingest(Headline(source_id='publisher',trust=SourceTrust.T1_PRIMARY,
    published_ms=1800000000000,observed_ms=1800000000000,title='Emergency policy decision',
    symbols=('EURUSD',),severity=Decimal('1')),now_ms=1800000000100)
'''
    child=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,text=True,timeout=20)
    assert child.returncode==77,child.stderr
    value=Ledger(path)
    try:
        assert value.count(EventKind.NEWS_HEADLINE)==value.count(EventKind.NEWS_OBSERVATION)==1
        head=value.head();cold=NewsIngress.from_ledger(value)
        assert cold.ingest(story(),now_ms=NOW+200) is None and value.head()==head
        assert cold.headlines(as_of_ms=NOW+99)==[] and cold.headlines(as_of_ms=NOW+100)==[story()]
        assert value.verify_chain()[0]
    finally:value.close()


def native_factory(tmp_path,backend):
    if backend=='sqlite':return lambda:Ledger(tmp_path/'native-news.sqlite')
    import os,uuid
    spec=os.environ.get('VATI_TEST_PG_DSN')
    if not spec or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
        pytest.skip('news PostgreSQL cases require an explicitly isolated fixture')
    from vati.core.ledger_pg import PostgresLedger
    name='news_'+uuid.uuid4().hex
    return lambda:PostgresLedger(spec,ledger_name=name)


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_native_writer_arbitration_and_cold_recovery(tmp_path,backend):
    from concurrent.futures import ThreadPoolExecutor
    factory=native_factory(tmp_path,backend);seed=factory();seed.close()
    def publish(_):
        value=factory()
        try:return NewsIngress(ledger=value).ingest(story(),now_ms=NOW)
        finally:value.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(publish,range(4)))
    value=factory()
    try:
        assert sum(h is not None for h in results)==1
        assert value.count(EventKind.NEWS_HEADLINE)==value.count(EventKind.NEWS_OBSERVATION)==1
        cold=NewsIngress.from_ledger(value)
        assert cold.headlines(as_of_ms=NOW)==[story()] and value.verify_chain()[0]
    finally:value.close()


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_native_commit_reply_loss_preserves_original_observation(tmp_path,backend,monkeypatch):
    factory=native_factory(tmp_path,backend);value=factory();news=NewsIngress(ledger=value);atomic=value.atomic
    @contextmanager
    def lose_reply():
        outer=value._atomic_depth==0 if backend=='postgres' else not value._conn.in_transaction
        with atomic():yield value
        if outer:raise OSError('fixture reply lost after committed native news write')
    try:
        with monkeypatch.context() as patch:
            patch.setattr(value,'atomic',lose_reply)
            with pytest.raises(OSError,match='committed native news write'):news.ingest(story(),now_ms=NOW+100)
        assert news.headlines()==[]
        head=value.head();assert news.ingest(story(),now_ms=NOW+200) is None and value.head()==head
        assert value.count(EventKind.NEWS_HEADLINE)==value.count(EventKind.NEWS_OBSERVATION)==1
    finally:value.close()
    value=factory()
    try:
        cold=NewsIngress.from_ledger(value)
        assert cold.headlines(as_of_ms=NOW+99)==[] and cold.headlines(as_of_ms=NOW+100)==[story()]
        assert value.verify_chain()[0]
    finally:value.close()


@pytest.mark.parametrize('kind',[EventKind.NEWS_OBSERVATION,EventKind.EVENT_IMPACT])
def test_observation_and_impact_readback_failure_keeps_completion_unknown_until_reconciled(ledger,monkeypatch,kind):
    news=NewsIngress(ledger=ledger);h=story();read=ledger.iter
    if kind is EventKind.EVENT_IMPACT:news.ingest(h,now_ms=NOW)
    def unavailable_after_commit(selected=None,correlation_id=None):
        if selected is kind and not ledger._conn.in_transaction:return iter(())
        return read(selected,correlation_id=correlation_id)
    def apply():
        if kind is EventKind.NEWS_OBSERVATION:return news.ingest(h,now_ms=NOW)
        return news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'iter',unavailable_after_commit)
        with pytest.raises(OSError,match='not confirmed'):apply()
    assert ledger.count(kind)==1
    if kind is EventKind.NEWS_OBSERVATION:assert news.headlines()==[]
    else:assert news.impacts_for('p')==[]
    head=ledger.head();apply();assert ledger.count(kind)==1 and ledger.head()==head
    assert NewsIngress.from_ledger(ledger).headlines()==[h]
