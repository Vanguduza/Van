"""A public RSS snapshot is original evidence, not freshness/licence admission."""
from contextlib import contextmanager

import pytest

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.events.news_runtime import build_news_file, refresh_news_file

NOW = 1_800_000_000_000


def rss(items=None):
    if items is None:
        items = '<item><title>Policy decision</title><guid isPermaLink="false">release-7</guid><link>https://publisher.test/r7</link><pubDate>Fri, 16 Oct 2026 15:00:00 GMT</pubDate></item>'
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            '<title>Declared primary feed</title>' + items + '</channel></rss>').encode()


@pytest.fixture
def setup(tmp_path):
    ledger = Ledger(tmp_path/'rss.sqlite'); path = tmp_path/'feed.xml'; path.write_bytes(rss())
    config = {'path':str(path), 'input_format':'rss2', 'source_id':'transport', 'publisher_id':'publisher'}
    try:
        yield ledger, path, config
    finally:
        ledger.close()


def snapshots(ledger):
    return [e for e in ledger.iter() if e.kind.value == 'NEWS_SOURCE_SNAPSHOT']


def build(ledger, config, now=NOW):
    return build_news_file(config, ledger=ledger, scope='acct/EURUSD', now_ms=now)


def test_real_file_builder_ingests_rss_with_declared_guid_and_original_publication_clock(setup):
    ledger, path, config = setup; news = build(ledger, config)
    h, = news.headlines(since_ms=-(2**63), as_of_ms=NOW)
    assert h.title == 'Policy decision' and h.observed_ms == NOW
    assert h.published_ms == 1_792_162_800_000
    report = news.report(now_ms=NOW)
    assert report['publisher_lineage']['clusters'][0]['original_story_keys'] == [{'publisher_id':'publisher','story_id':'release-7'}]
    assert report['source_health']['state'] == 'READY_DECLARED'
    assert report['source_health']['live_eligible'] is False
    assert report['source_health']['last_known_source_snapshot']['provider_qualified'] is False
    assert report['source_health']['last_known_source_snapshot']['native_clock_qualified'] is False
    original, = snapshots(ledger)
    assert original.payload['raw_sha256'] == report['source_health']['input_sha256']


def test_repeated_same_rss_bytes_reuse_first_capture_and_observation_after_cold_recovery(setup):
    ledger, path, config = setup; news = build(ledger, config)
    snapshot, = snapshots(ledger); head = ledger.head()
    refresh_news_file(news, config, ledger=ledger, scope='acct/EURUSD', now_ms=NOW+100)
    assert snapshots(ledger) == [snapshot] and ledger.head() == head
    restored = build(ledger, config, NOW+200)
    assert snapshots(ledger) == [snapshot] and ledger.head() == head
    assert restored.headlines(since_ms=-(2**63), as_of_ms=NOW)[0].observed_ms == NOW


@pytest.mark.parametrize('items', [
    '<item><title>Missing publication</title><guid>x</guid></item>',
    '<item><title>Unzoned</title><guid>x</guid><pubDate>16 Oct 2026 15:00:00</pubDate></item>',
    '<item><title>No original key</title><pubDate>16 Oct 2026 15:00:00 GMT</pubDate></item>',
])
def test_missing_publication_or_original_key_is_partial_without_a_guessed_clock(setup, items):
    ledger, path, config = setup; path.write_bytes(rss(items))
    news = build(ledger, config)
    assert news.headlines() == []
    assert news.source_health['state'] == 'PARTIAL' and len(news.skipped) == 1
    assert len(snapshots(ledger)) == 1


def test_bad_rss_item_preserves_its_valid_neighbors(setup):
    ledger, path, config = setup
    valid = rss().decode().split('<item>',1)[1].split('</item>',1)[0]
    path.write_bytes(rss('<item>'+valid+'</item><item><title>Bad</title></item><item>'+valid.replace('release-7','release-8').replace('Policy decision','Next decision')+'</item>'))
    news = build(ledger, config)
    assert len(news.headlines(since_ms=-(2**63), as_of_ms=NOW)) == 2
    assert news.source_health['state'] == 'PARTIAL' and len(news.skipped) == 1


def test_raw_snapshot_bytes_survive_malformed_feed_without_fabricated_coverage(setup):
    import base64
    ledger, path, config = setup; raw = b'<rss version="2.0"><broken'; path.write_bytes(raw)
    news = build(ledger, config)
    original, = snapshots(ledger)
    assert base64.b64decode(original.payload['raw_base64'], validate=True) == raw
    assert news.source_health['state'] == 'UNREADABLE' and news.source_health['coverage'] == 'UNKNOWN'
    assert news.headlines() == []


@pytest.mark.parametrize('change', [{'input_format':'invented'}, {'publisher_id':''}, {'source_id':True}])
def test_bad_adapter_profile_is_configuration_error_before_capture(setup, change):
    ledger, path, config = setup; news = build(ledger, config | change)
    assert news.source_health['state'] == 'CONFIGURATION_ERROR'
    assert snapshots(ledger) == [] and news.headlines() == []


def test_lost_snapshot_commit_reply_publishes_no_headline_then_reuses_original_capture(setup, monkeypatch):
    ledger, path, config = setup; atomic = ledger.atomic
    @contextmanager
    def lost():
        outer = not ledger._conn.in_transaction; before = len(snapshots(ledger))
        with atomic():
            yield ledger
        if outer and len(snapshots(ledger)) > before:
            raise OSError('fixture snapshot commit reply lost')
    with monkeypatch.context() as patch:
        patch.setattr(ledger, 'atomic', lost); news = build(ledger, config)
    original, = snapshots(ledger)
    assert news.source_health['state'] == 'PUBLICATION_UNKNOWN' and news.headlines() == []
    assert ledger.count(EventKind.NEWS_HEADLINE) == 0
    result = refresh_news_file(news, config, ledger=ledger, scope='acct/EURUSD', now_ms=NOW+100)
    assert result['source_health']['state'] == 'READY_DECLARED'
    assert snapshots(ledger) == [original]
    assert news.headlines(since_ms=-(2**63), as_of_ms=NOW) == []
    assert news.headlines(since_ms=-(2**63), as_of_ms=NOW+100)[0].observed_ms == NOW


@pytest.mark.parametrize('prefix', [b'<!DOCTYPE rss [<!ENTITY x "replacement">]>',
    b'<!DOCTYPE rss SYSTEM "file:///etc/passwd">'])
def test_rss_dtd_is_never_resolved_or_treated_as_feed_coverage(setup, prefix):
    ledger, path, config = setup; path.write_bytes(prefix+rss().split(b'?>',1)[1])
    news = build(ledger, config)
    assert news.source_health['state'] == 'UNREADABLE' and news.headlines() == []
    assert len(snapshots(ledger)) == 1


def test_declared_rss_relevance_is_used_without_inferring_currency_from_publisher(setup):
    from datetime import datetime,timedelta,timezone
    from email.utils import format_datetime
    ledger, path, config = setup
    fresh=format_datetime(datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=NOW),usegmt=True)
    path.write_bytes(rss().replace(b'Fri, 16 Oct 2026 15:00:00 GMT',fresh.encode()))
    config |= {'relevance':{'currencies':['USD'],'symbols':['EURUSD']},
               'sources':[{'source_id':'transport','trust':'T1_PRIMARY'}]}
    news = build(ledger, config); h, = news.headlines(since_ms=-(2**63),as_of_ms=NOW)
    assert h.currencies == ('USD',) and h.symbols == ('EURUSD',)
    assert news.candidate_risk('EURUSD',now_ms=NOW,persist=False)[0] < 1
    assert news.report(now_ms=NOW)['publisher_lineage']['qualified_independent_sources'] == 0


def test_stale_rss_retrieval_does_not_turn_an_old_publication_into_current_risk(setup):
    ledger,path,config=setup
    config |= {'relevance':{'symbols':['EURUSD']},'sources':[{'source_id':'transport','trust':'T1_PRIMARY'}]}
    news=build(ledger,config)
    assert len(news.headlines(since_ms=-(2**63),as_of_ms=NOW))==1
    assert news.candidate_risk('EURUSD',now_ms=NOW,persist=False)[0]==1


def test_rss_row_capacity_is_explicit_and_never_admits_a_partial_prefix_as_complete(setup):
    ledger, path, config = setup
    item='<item><title>x</title><guid>x</guid><pubDate>16 Oct 2026 15:00:00 GMT</pubDate></item>'
    path.write_bytes(rss(item*2)); news = build(ledger,config | {'max_rows':1})
    assert news.source_health['state'] == 'CAPACITY_EXCEEDED' and news.source_health['coverage'] == 'UNKNOWN'
    assert news.headlines() == [] and len(snapshots(ledger)) == 1


def test_snapshot_publication_requires_independent_original_readback(setup,monkeypatch):
    ledger, path, config = setup; iterate=ledger.iter; atomic=ledger.atomic; committed=False
    @contextmanager
    def note_commit():
        nonlocal committed
        with atomic():yield ledger
        committed=True
    def hidden(kind=None,**kwargs):
        if committed and kind is not None and kind.value=='NEWS_SOURCE_SNAPSHOT':return iter(())
        return iterate(kind,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'atomic',note_commit);patch.setattr(ledger,'iter',hidden)
        news=build(ledger,config)
    assert news.source_health['state']=='PUBLICATION_UNKNOWN' and news.headlines()==[]
    original,=snapshots(ledger)
    assert refresh_news_file(news,config,ledger=ledger,scope='acct/EURUSD',now_ms=NOW+10)['source_health']['state']=='READY_DECLARED'
    assert snapshots(ledger)==[original]


def test_snapshot_corruption_cannot_be_recovered_or_extended_with_health_success(setup):
    ledger, path, config = setup;build(ledger,config)
    ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE kind='NEWS_SOURCE_SNAPSHOT'")
    head=ledger.head();count=ledger.count();news=build(ledger,config,NOW+1)
    assert news.source_health['state']=='RECOVERY_UNAVAILABLE' and ledger.count()==count and ledger.head()==head
    assert news.headlines()==[]


def test_missing_warm_snapshot_refuses_recreation_without_publishing_health_into_corruption(setup,monkeypatch):
    ledger,path,config=setup;news=build(ledger,config);iterate=ledger.iter;head=ledger.head()
    def hidden(kind=None,**kwargs):
        if kind is not None and kind.value=='NEWS_SOURCE_SNAPSHOT':return iter(())
        return iterate(kind,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'iter',hidden)
        report=refresh_news_file(news,config,ledger=ledger,scope='acct/EURUSD',now_ms=NOW+1)
    assert report['source_health']['state']=='RECOVERY_UNAVAILABLE'
    assert len(snapshots(ledger))==1 and ledger.head()==head


def test_cold_recovery_refuses_hidden_original_snapshot_instead_of_appending_another(setup,monkeypatch):
    ledger,path,config=setup;build(ledger,config);iterate=ledger.iter;head=ledger.head()
    def hidden(kind=None,**kwargs):
        if kind is not None and kind.value=='NEWS_SOURCE_SNAPSHOT':return iter(())
        return iterate(kind,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'iter',hidden);news=build(ledger,config,NOW+1)
    assert news.source_health['state']=='RECOVERY_UNAVAILABLE'
    assert len(snapshots(ledger))==1 and ledger.head()==head


def test_report_cannot_mutate_last_known_raw_snapshot_or_captured_profile(setup):
    ledger,path,config=setup;news=build(ledger,config)
    report=news.report(now_ms=NOW)
    report['source_health']['last_known_source_snapshot']['receipt_hash']='forged'
    report['source_health']['source_profile']['adapter']['publisher_id']='forged'
    original,=snapshots(ledger)
    current=news.report(now_ms=NOW)['source_health']
    assert current['last_known_source_snapshot']['receipt_hash']==original.hash
    assert current['source_profile']['adapter']['publisher_id']=='publisher'


@pytest.mark.parametrize('kind',['session','account'])
def test_actual_service_news_builder_wires_rss_ingestion_and_refresh(setup,kind):
    from test_news_runtime_health import service,build as service_build
    ledger,path,config=setup;value=service(kind,ledger,config);news=service_build(value,kind)
    assert len(news.headlines(since_ms=-(2**63),as_of_ms=NOW))==1
    assert value.refresh_news(NOW+1)['source_health']['state']=='READY_DECLARED'
    assert len(snapshots(ledger))==1 and ledger.count(EventKind.NEWS_OBSERVATION)==1


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_native_concurrent_rss_builders_share_one_original_snapshot(setup,tmp_path,backend):
    from concurrent.futures import ThreadPoolExecutor
    from test_news_durable_publication import native_factory
    _unused,path,config=setup;factory=native_factory(tmp_path,backend);seed=factory();seed.close()
    def publish(_):
        value=factory()
        try:return build(value,config).source_health['state']
        finally:value.close()
    with ThreadPoolExecutor(max_workers=2) as pool:states=list(pool.map(publish,range(4)))
    value=factory()
    try:
        assert states==['READY_DECLARED']*4
        assert len(snapshots(value))==value.count(EventKind.NEWS_HEADLINE)==value.count(EventKind.NEWS_OBSERVATION)==1
        assert value.count()==5 and value.verify_chain()[0]
    finally:value.close()


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_native_rss_snapshot_commit_loss_reconciles_original(setup,tmp_path,backend,monkeypatch):
    from test_news_durable_publication import native_factory
    _unused,path,config=setup;factory=native_factory(tmp_path,backend);value=factory();atomic=value.atomic
    @contextmanager
    def lost():
        outer=value._atomic_depth==0 if backend=='postgres' else not value._conn.in_transaction
        before=len(snapshots(value))
        with atomic():yield value
        if outer and len(snapshots(value))>before:raise OSError('fixture native snapshot reply lost')
    try:
        with monkeypatch.context() as patch:
            patch.setattr(value,'atomic',lost);news=build(value,config)
        original,=snapshots(value)
        assert news.source_health['state']=='PUBLICATION_UNKNOWN' and value.count(EventKind.NEWS_HEADLINE)==0
        result=refresh_news_file(news,config,ledger=value,scope='acct/EURUSD',now_ms=NOW+10)
        assert result['source_health']['state']=='READY_DECLARED' and snapshots(value)==[original]
        assert value.count(EventKind.NEWS_HEADLINE)==1 and value.verify_chain()[0]
        assert news.headlines(since_ms=-(2**63),as_of_ms=NOW)==[]
    finally:value.close()


@pytest.mark.parametrize('clock',[True,1.5,'1800000000000',2**63])
def test_capture_clock_rejects_invalid_types_before_sql_publication(setup,clock):
    from vati.events.news_feed import capture_snapshot
    from vati.events.news_runtime import _options,_profile
    ledger,path,config=setup
    with pytest.raises(ValueError,match='clock'):
        capture_snapshot(ledger,scope='acct/EURUSD',profile=_profile(_options(config)),raw=path.read_bytes(),now_ms=clock)
    assert ledger.count()==0


@pytest.mark.parametrize('change',[{'raw_base64':'b3RoZXIgYnl0ZXM='},
    {'provider_qualified':True},{'native_clock_qualified':True}])
def test_correct_event_seal_cannot_hide_wrong_raw_bytes_or_self_admit_a_snapshot(setup,tmp_path,change):
    from vati.core.events import make_event
    ledger,path,config=setup;build(ledger,config);original,=snapshots(ledger)
    value=Ledger(tmp_path/'forged-snapshot.sqlite')
    try:
        value.append(make_event(original.kind,original.producer,original.payload | change,
            event_time_ms=original.event_time_ms,received_time_ms=original.received_time_ms,
            correlation_id=original.correlation_id))
        assert value.verify_chain()[0];head=value.head()
        news=build(value,config)
        assert news.source_health['state']=='RECOVERY_UNAVAILABLE'
        assert value.head()==head and value.count()==1 and news.headlines()==[]
    finally:value.close()
