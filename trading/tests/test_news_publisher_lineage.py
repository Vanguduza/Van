"""Publisher declarations are durable evidence, never independent-source admission."""
from contextlib import contextmanager
from copy import deepcopy

import pytest

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.events.news_ingress import NewsIngress

NOW = 1_800_000_000_000


@pytest.fixture
def ledger(tmp_path):
    value = Ledger(tmp_path / 'lineage.sqlite')
    try:
        yield value
    finally:
        value.close()


def row(source='wire-a', title='Policy decision', **changes):
    return dict(source=source, title=title, published_ms=NOW, observed_ms=NOW,
                original_publisher={'publisher_id': 'central-bank', 'story_id': 'release-7'}) | changes


def lineage(news, now=NOW):
    result = news.report(now_ms=now)
    assert 'publisher_lineage' in result, 'original publisher lineage is absent from the actual ingress report'
    return result['publisher_lineage']


def records(ledger):
    return [e for e in ledger.iter() if e.kind.value == 'NEWS_LINEAGE']


def test_rewritten_syndicated_stories_form_one_declared_cluster(ledger):
    news = NewsIngress(ledger=ledger)
    assert news.ingest_rows([row(), row('wire-b', 'Central bank publishes its policy decision')], now_ms=NOW)['accepted'] == 2
    report = lineage(news)
    assert report['story_clusters'] == 1
    cluster, = report['clusters']
    assert cluster['transport_source_ids'] == ['wire-a', 'wire-b']
    assert cluster['declared_original_publishers'] == ['central-bank']
    assert len(cluster['headline_ids']) == 2
    assert report['qualified_independent_sources'] == 0
    assert cluster['provider_qualified'] is False


@pytest.mark.parametrize('origin', [None, {}, {'publisher_id': 'bank'},
    {'publisher_id': True, 'story_id': 'r'}, {'publisher_id': 'bank', 'story_id': ''},
    {'publisher_id': 'bank', 'story_id': 'r', 'qualified': True}])
def test_invalid_explicit_origin_is_skipped_without_publishing_a_headline(ledger, origin):
    news = NewsIngress(ledger=ledger)
    counts = news.ingest_rows([row(original_publisher=origin)], now_ms=NOW)
    assert counts == {'accepted': 0, 'duplicates': 0, 'skipped': 1}
    assert ledger.count() == 0 and news.headlines() == []


def test_originless_legacy_rows_stay_unknown_and_do_not_infer_publisher_from_transport(ledger):
    news = NewsIngress(ledger=ledger)
    value = row(); value.pop('original_publisher')
    news.ingest_rows([value], now_ms=NOW)
    report = lineage(news)
    assert report['unknown_origin_observations'] == 1
    assert report['clusters'][0]['declared_original_publishers'] == []
    assert report['clusters'][0]['state'] == 'UNKNOWN_ORIGIN'


def test_cold_recovery_restores_lineage_without_republishing_originals(ledger):
    news = NewsIngress(ledger=ledger)
    news.ingest_rows([row(), row('wire-b', 'Policy announcement')], now_ms=NOW)
    head = ledger.head(); count = ledger.count()
    expected = lineage(news)
    restored = NewsIngress.from_ledger(ledger)
    assert lineage(restored) == expected
    restored.ingest_rows([row()], now_ms=NOW+1000)
    assert ledger.head() == head and ledger.count() == count
    assert len(records(ledger)) == 2


def test_declared_origin_does_not_backdate_earlier_unknown_observation(ledger):
    news = NewsIngress(ledger=ledger)
    value = row(); value.pop('original_publisher')
    news.ingest_rows([value], now_ms=NOW)
    news.ingest_rows([row()], now_ms=NOW+10)
    assert lineage(news, NOW)['unknown_origin_observations'] == 1
    assert lineage(news, NOW+10)['unknown_origin_observations'] == 0
    assert lineage(NewsIngress.from_ledger(ledger), NOW) == lineage(news, NOW)


def test_lineage_result_cannot_mutate_original_evidence(ledger):
    news = NewsIngress(ledger=ledger); news.ingest_rows([row()], now_ms=NOW)
    before = deepcopy(lineage(news))
    lineage(news)['clusters'][0]['declared_original_publishers'].append('forged')
    assert lineage(news) == before


def test_origin_enrichment_cannot_precede_the_original_observations_availability(ledger):
    news = NewsIngress(ledger=ledger)
    value = row(); value.pop('original_publisher')
    news.ingest_rows([value], now_ms=NOW+20)
    news.ingest_rows([row()], now_ms=NOW)
    assert records(ledger)[0].payload['available_ms'] == NOW+20
    assert lineage(NewsIngress.from_ledger(ledger), NOW+20)['unknown_origin_observations'] == 0


def test_lineage_append_failure_rolls_back_headline_and_observation_before_memory(ledger, monkeypatch):
    news = NewsIngress(ledger=ledger); append = ledger.append
    def fail(event):
        if event.kind.value == 'NEWS_LINEAGE':
            raise OSError('fixture lineage writer unavailable')
        return append(event)
    with monkeypatch.context() as patch:
        patch.setattr(ledger, 'append', fail)
        with pytest.raises(OSError):
            news.ingest_rows([row()], now_ms=NOW)
    assert ledger.count() == 0 and news.headlines() == []
    assert news.ingest_rows([row()], now_ms=NOW)['accepted'] == 1
    assert len(records(ledger)) == 1


def test_lost_sql_commit_reply_keeps_memory_unknown_and_cold_replay_reads_original(ledger, monkeypatch):
    news = NewsIngress(ledger=ledger); atomic = ledger.atomic
    @contextmanager
    def lose_reply():
        outer = not ledger._conn.in_transaction
        with atomic():
            yield ledger
        if outer:
            raise OSError('fixture committed reply lost')
    with monkeypatch.context() as patch:
        patch.setattr(ledger, 'atomic', lose_reply)
        with pytest.raises(OSError):
            news.ingest_rows([row()], now_ms=NOW)
    original, = records(ledger); head = ledger.head()
    assert news.headlines() == []
    restored = NewsIngress.from_ledger(ledger)
    assert restored.ingest_rows([row()], now_ms=NOW+100)['duplicates'] == 1
    assert records(ledger) == [original] and ledger.head() == head


def test_lineage_requires_independent_readback_before_memory_success(ledger, monkeypatch):
    news = NewsIngress(ledger=ledger); iterate = ledger.iter; atomic = ledger.atomic; committed = False
    @contextmanager
    def note_commit():
        nonlocal committed
        with atomic():
            yield ledger
        committed = True
    def hide(kind=None, **kwargs):
        if committed and kind is not None and kind.value == 'NEWS_LINEAGE':
            return iter(())
        return iterate(kind, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(ledger, 'atomic', note_commit); patch.setattr(ledger, 'iter', hide)
        with pytest.raises(OSError, match='lineage.*not confirmed'):
            news.ingest_rows([row()], now_ms=NOW)
    assert news.headlines() == [] and len(records(ledger)) == 1
    assert lineage(NewsIngress.from_ledger(ledger))['story_clusters'] == 1


def test_conflicting_origin_cannot_rewrite_an_original_observation(ledger):
    news = NewsIngress(ledger=ledger); news.ingest_rows([row()], now_ms=NOW)
    head = ledger.head()
    with pytest.raises(ValueError, match='publisher.*conflicts'):
        news.ingest_rows([row(original_publisher={'publisher_id':'other', 'story_id':'x'})], now_ms=NOW+1)
    assert ledger.head() == head and len(records(ledger)) == 1


def test_exact_title_with_contradictory_origins_is_one_conflicted_cluster(ledger):
    news = NewsIngress(ledger=ledger)
    news.ingest_rows([row(), row('wire-b', original_publisher={'publisher_id':'other', 'story_id':'x'})], now_ms=NOW)
    report = lineage(news); cluster, = report['clusters']
    assert cluster['state'] == 'CONFLICTING_ORIGIN'
    assert report['qualified_independent_sources'] == 0


def test_future_origin_does_not_reveal_future_publisher_or_transport(ledger):
    news = NewsIngress(ledger=ledger)
    news.ingest_rows([row(), row('future-wire', 'Changed title', observed_ms=NOW+10)], now_ms=NOW)
    report = lineage(news); cluster, = report['clusters']
    assert cluster['transport_source_ids'] == ['wire-a']
    assert len(cluster['observation_ids']) == 1


def test_atomic_origin_marker_refuses_deleted_lineage_after_cold_start(ledger, monkeypatch):
    news = NewsIngress(ledger=ledger); news.ingest_rows([row()], now_ms=NOW)
    iterate = ledger.iter
    def hide(kind=None, **kwargs):
        if kind is not None and kind.value == 'NEWS_LINEAGE':
            return iter(())
        return iterate(kind, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(ledger, 'iter', hide)
        with pytest.raises(ValueError, match='lineage.*missing'):
            NewsIngress.from_ledger(ledger)
        with pytest.raises(ValueError, match='lineage.*missing'):
            NewsIngress(ledger=ledger).ingest_rows([row()], now_ms=NOW+1)
    assert len(records(ledger)) == 1


@pytest.mark.parametrize('change', [
    {'observation_id': 'f'*64}, {'headline_id': 'f'*32}, {'available_ms': NOW-1},
    {'provider_qualified': True}, {'independence_qualified': True},
    {'authority_effect': 'ORDER'}, {'format': 'news-publisher-lineage/99'},
])
def test_even_correctly_sealed_invalid_or_orphaned_lineage_is_refused(ledger, change):
    from vati.core.events import make_event
    news = NewsIngress(ledger=ledger); news.ingest_rows([row()], now_ms=NOW)
    original, = records(ledger)
    value = original.payload | change
    ledger.append(make_event(EventKind.NEWS_LINEAGE, original.producer, value,
        event_time_ms=value['available_ms'], received_time_ms=value['available_ms'],
        correlation_id=value['headline_id']))
    count = ledger.count()
    with pytest.raises(ValueError, match='lineage'):
        NewsIngress.from_ledger(ledger)
    assert ledger.count() == count


def test_ambiguous_duplicate_lineage_refuses_recovery_and_replay(ledger):
    news = NewsIngress(ledger=ledger); news.ingest_rows([row()], now_ms=NOW)
    ledger.append(records(ledger)[0]); count = ledger.count()
    with pytest.raises(ValueError, match='lineage.*ambiguous'):
        NewsIngress.from_ledger(ledger)
    with pytest.raises(ValueError, match='lineage.*ambiguous'):
        NewsIngress(ledger=ledger).ingest_rows([row()], now_ms=NOW+1)
    assert ledger.count() == count


def test_recovery_capacity_includes_lineage_receipts(ledger):
    news = NewsIngress(ledger=ledger); news.ingest_rows([row()], now_ms=NOW)
    assert ledger.count() == 3
    with pytest.raises(ValueError, match='capacity'):
        NewsIngress.from_ledger(ledger, max_events=2)
    assert lineage(NewsIngress.from_ledger(ledger, max_events=3))['story_clusters'] == 1


def test_actual_service_file_builder_exposes_lineage_and_recovers_it(tmp_path, ledger):
    import json
    from vati.events.news_runtime import build_news_file, news_heartbeat
    path = tmp_path/'headlines.json'; path.write_text(json.dumps([row(), row('b', 'Rewritten')]))
    cfg = {'path':str(path)}
    news = build_news_file(cfg, ledger=ledger, scope='acct/EURUSD', now_ms=NOW)
    assert lineage(news)['story_clusters'] == 1
    path.unlink()
    restored = build_news_file(cfg, ledger=ledger, scope='acct/EURUSD', now_ms=NOW+1)
    assert lineage(restored)['clusters'] == lineage(news)['clusters']
    assert news_heartbeat(restored)['source_health']['state'] == 'MISSING'


@pytest.mark.parametrize('backend', ['sqlite', 'postgres'])
def test_real_sql_lineage_commit_reply_loss_is_reconciled(backend, tmp_path, monkeypatch):
    import os
    if backend == 'sqlite':
        value = Ledger(tmp_path/'native-lineage.sqlite')
    else:
        dsn = os.environ.get('VATI_TEST_PG_DSN')
        if not dsn or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE') != '1':
            pytest.skip('requires isolated PostgreSQL fixture')
        import uuid
        from vati.core.ledger_pg import PostgresLedger
        value = PostgresLedger(dsn, ledger_name='lineage_' + uuid.uuid4().hex)
    try:
        atomic = value.atomic; news = NewsIngress(ledger=value)
        @contextmanager
        def lost():
            outer = value._atomic_depth == 0 if backend == 'postgres' else not value._conn.in_transaction
            with atomic():
                yield value
            if outer:
                raise OSError('fixture native committed lineage reply lost')
        with monkeypatch.context() as patch:
            patch.setattr(value, 'atomic', lost)
            with pytest.raises(OSError):
                news.ingest_rows([row()], now_ms=NOW)
        head = value.head(); original, = records(value)
        restored = NewsIngress.from_ledger(value)
        restored.ingest_rows([row()], now_ms=NOW+10)
        assert value.head() == head and records(value) == [original]
        assert value.count() == 3 and value.verify_chain()[0]
        assert lineage(restored)['qualified_independent_sources'] == 0
    finally:
        value.close()


@pytest.mark.parametrize('backend', ['sqlite', 'postgres'])
def test_concurrent_native_publishers_retain_one_original_lineage(backend, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from test_news_durable_publication import native_factory
    factory = native_factory(tmp_path, backend); seed = factory(); seed.close()
    def publish(_):
        value = factory()
        try:
            return NewsIngress(ledger=value).ingest_rows([row()], now_ms=NOW)['accepted']
        finally:
            value.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = list(pool.map(publish, range(4)))
    value = factory()
    try:
        assert sum(accepted) == 1 and value.count() == 3
        assert len(records(value)) == 1 and value.verify_chain()[0]
        assert lineage(NewsIngress.from_ledger(value))['story_clusters'] == 1
    finally:
        value.close()


def test_actual_child_death_after_sql_commit_restores_lineage_once(tmp_path):
    import json
    import subprocess
    import sys
    path = tmp_path/'death.sqlite'
    script = '''
import os, sys, json
from vati.core.ledger import Ledger
from vati.core.events import EventKind
from vati.events.news_ingress import NewsIngress
ledger=Ledger(sys.argv[1]); read=ledger.iter
def die(kind=None, correlation_id=None):
    if kind is EventKind.NEWS_HEADLINE and not ledger._conn.in_transaction: os._exit(77)
    return read(kind,correlation_id=correlation_id)
ledger.iter=die
NewsIngress(ledger=ledger).ingest_rows([json.loads(sys.argv[2])],now_ms=1800000000000)
'''
    child = subprocess.run([sys.executable, '-c', script, str(path), json.dumps(row())],
                           capture_output=True, text=True, timeout=20)
    assert child.returncode == 77, child.stderr
    value = Ledger(path)
    try:
        original, = records(value); head = value.head()
        restored = NewsIngress.from_ledger(value)
        assert restored.ingest_rows([row()], now_ms=NOW+1)['duplicates'] == 1
        assert records(value) == [original] and value.head() == head and value.count() == 3
        assert lineage(restored)['clusters'][0]['declared_original_publishers'] == ['central-bank']
    finally:
        value.close()


def test_sealed_backdated_lineage_cannot_be_replayed_as_a_valid_original(ledger, tmp_path):
    from vati.core.events import make_event
    NewsIngress(ledger=ledger).ingest_rows([row()], now_ms=NOW+10)
    value = Ledger(tmp_path/'backdated.sqlite')
    try:
        for event in ledger.iter():
            if event.kind is not EventKind.NEWS_LINEAGE:
                value.append(event)
            else:
                value.append(make_event(event.kind, event.producer, event.payload | {'available_ms':NOW},
                    event_time_ms=NOW, received_time_ms=NOW, correlation_id=event.correlation_id))
        assert value.verify_chain()[0]; head = value.head()
        with pytest.raises(ValueError, match='lineage.*(backdated|availability)'):
            NewsIngress.from_ledger(value)
        with pytest.raises(ValueError, match='lineage.*availability'):
            NewsIngress(ledger=value).ingest_rows([row()], now_ms=NOW+20)
        assert value.head() == head
    finally:
        value.close()


def test_orphaned_lineage_cannot_recreate_missing_headline_and_observation(ledger, tmp_path):
    NewsIngress(ledger=ledger).ingest_rows([row()], now_ms=NOW)
    value = Ledger(tmp_path/'orphan.sqlite')
    try:
        value.append(records(ledger)[0]); head = value.head()
        with pytest.raises(ValueError, match='lineage.*orphaned'):
            NewsIngress.from_ledger(value)
        with pytest.raises(ValueError, match='original.*missing'):
            NewsIngress(ledger=value).ingest_rows([row()], now_ms=NOW+1)
        assert value.head() == head and value.count() == 1
    finally:
        value.close()
