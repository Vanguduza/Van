"""Existing CLI reaches durable RSS source contracts and preserves JSON compatibility."""
from contextlib import closing,contextmanager
import base64
import json

import pytest

from vati.__main__ import main
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.events.news_ingress import NewsIngress
from test_news_rss_feed import rss,NOW


@pytest.fixture
def files(tmp_path):
    feed=tmp_path/'feed.xml';feed.write_bytes(rss())
    config=tmp_path/'news.json';config.write_text(json.dumps({'input_format':'rss2','path':str(feed),
        'source_id':'transport','publisher_id':'publisher'}))
    return config,feed,tmp_path/'ledger.sqlite'


def invoke(files,capsys,*,now=NOW,ledger=True,extra=()):
    config,feed,store=files
    args=['news-ingest','--config',str(config),'--now',str(now),*extra]
    if ledger:args+=['--ledger',str(store)]
    result=main(args);return result,json.loads(capsys.readouterr().out)


def test_actual_cli_records_original_rss_and_reports_first_batch_counts(files,capsys):
    code,report=invoke(files,capsys)
    assert code==0 and report['counts']=={'accepted':1,'duplicates':0,'skipped':0}
    assert report['headlines_recorded'][0]['title']=='Policy decision'
    health=report['source_health'];assert health['state']=='READY_DECLARED' and health['live_eligible'] is False
    with closing(Ledger(files[2])) as ledger:
        snapshot,=ledger.iter(EventKind.NEWS_SOURCE_SNAPSHOT)
        assert base64.b64decode(snapshot.payload['raw_base64'])==files[1].read_bytes()
        assert ledger.count(EventKind.NEWS_HEADLINE)==ledger.count(EventKind.NEWS_OBSERVATION)==1


def test_actual_cli_cold_replay_reuses_original_capture_without_growing_ledger(files,capsys):
    assert invoke(files,capsys)[0]==0
    with closing(Ledger(files[2])) as ledger:head=ledger.head()
    code,report=invoke(files,capsys,now=NOW+200)
    assert code==0 and report['counts']=={'accepted':0,'duplicates':1,'skipped':0}
    assert len(report['headlines_recorded'])==1
    assert report['source_health']['last_known_source_snapshot']['captured_ms']==NOW
    with closing(Ledger(files[2])) as ledger:assert ledger.head()==head


def test_actual_cli_uses_explicit_file_override_in_snapshot_profile(files,capsys,tmp_path):
    other=tmp_path/'override.xml';other.write_bytes(rss().replace(b'Policy decision',b'Overridden source'))
    code,report=invoke(files,capsys,extra=['--file',str(other)])
    assert code==0 and report['headlines_recorded'][0]['title']=='Overridden source'
    with closing(Ledger(files[2])) as ledger:
        original,=ledger.iter(EventKind.NEWS_SOURCE_SNAPSHOT)
        assert base64.b64decode(original.payload['raw_base64'])==other.read_bytes()


@pytest.mark.parametrize('raw',[b'<rss><broken',b'<!DOCTYPE rss SYSTEM "file:///etc/passwd"><rss/>'])
def test_actual_cli_retains_bad_original_bytes_and_refuses_empty_success(files,capsys,raw):
    files[1].write_bytes(raw);code,report=invoke(files,capsys)
    assert code==2 and report['source_health']['state']=='UNREADABLE'
    assert report['source_health']['coverage']=='UNKNOWN' and report['headlines_recorded']==[]
    with closing(Ledger(files[2])) as ledger:
        original,=ledger.iter(EventKind.NEWS_SOURCE_SNAPSHOT)
        assert base64.b64decode(original.payload['raw_base64'])==raw
        assert ledger.count(EventKind.NEWS_HEADLINE)==0


def test_actual_cli_preserves_valid_neighbor_and_nonzero_partial_exit(files,capsys):
    valid=rss().decode().split('<item>',1)[1].split('</item>',1)[0]
    files[1].write_bytes(rss('<item>'+valid+'</item><item><title>Missing original identity</title></item>'))
    code,report=invoke(files,capsys)
    assert code==1 and report['counts']=={'accepted':1,'duplicates':0,'skipped':1}
    assert report['source_health']['state']=='PARTIAL' and len(report['headlines_recorded'])==1


def test_rss_cli_requires_original_durable_sink_before_reading_feed(files,capsys):
    code,report=invoke(files,capsys,ledger=False)
    assert code==2 and report.get('error')=='RSS_DURABLE_LEDGER_REQUIRED'
    assert not files[2].exists()


def test_unknown_cli_input_format_is_explicit_configuration_error(files,capsys):
    value=json.loads(files[0].read_text());value['input_format']='future-reader';files[0].write_text(json.dumps(value))
    code,report=invoke(files,capsys)
    assert code==2 and report['source_health']['state']=='CONFIGURATION_ERROR'
    with closing(Ledger(files[2])) as ledger:assert ledger.count(EventKind.NEWS_SOURCE_SNAPSHOT)==0


def test_actual_cli_lost_raw_ack_remains_unknown_and_recovers_original_once(files,capsys,monkeypatch):
    atomic=Ledger.atomic
    @contextmanager
    def lost(self):
        outer=not self._conn.in_transaction;before=self.count(EventKind.NEWS_SOURCE_SNAPSHOT)
        with atomic(self):yield self
        if outer and self.count(EventKind.NEWS_SOURCE_SNAPSHOT)>before:raise OSError('fixture raw commit ACK lost')
    with monkeypatch.context() as patch:
        patch.setattr(Ledger,'atomic',lost);code,report=invoke(files,capsys)
    assert code==2 and report['source_health']['state']=='PUBLICATION_UNKNOWN'
    assert report['reconcile_required'] is True and report['counts']=={'accepted':None,'duplicates':None,'skipped':None}
    with closing(Ledger(files[2])) as ledger:
        original,=ledger.iter(EventKind.NEWS_SOURCE_SNAPSHOT);assert ledger.count(EventKind.NEWS_HEADLINE)==0
    code,report=invoke(files,capsys,now=NOW+100)
    assert code==0 and report['counts']['accepted']==1
    with closing(Ledger(files[2])) as ledger:
        assert list(ledger.iter(EventKind.NEWS_SOURCE_SNAPSHOT))==[original]
        restored=NewsIngress.from_ledger(ledger)
        assert restored.headlines(since_ms=-(2**63),as_of_ms=NOW)==[]
        assert restored.headlines(since_ms=-(2**63),as_of_ms=NOW+100)[0].observed_ms==NOW


def test_json_cli_keeps_optional_ledger_and_original_counts(files,capsys,tmp_path):
    config,feed,store=files;feed=tmp_path/'legacy.jsonl'
    feed.write_text(json.dumps({'source_id':'transport','title':'Legacy row','published_ms':NOW})+'\n')
    config.write_text(json.dumps({'path':str(feed),'sources':[]}))
    code,report=invoke(files,capsys,ledger=False)
    assert code==0 and report['counts']=={'accepted':1,'duplicates':0,'skipped':0}
    assert report['headlines_recorded'][0]['title']=='Legacy row' and not store.exists()


def test_actual_cli_missing_file_retains_history_with_nonzero_unavailable_state(files,capsys):
    assert invoke(files,capsys)[0]==0
    files[1].unlink();code,report=invoke(files,capsys,now=NOW+100)
    assert code==2 and report['source_health']['state']=='MISSING'
    assert report['counts']=={'accepted':0,'duplicates':0,'skipped':0}
    assert len(report['headlines_recorded'])==1 and report['source_health']['coverage']=='UNKNOWN'


def test_actual_cli_corrupt_original_refuses_recreation_or_health_append(files,capsys):
    assert invoke(files,capsys)[0]==0
    with closing(Ledger(files[2])) as ledger:
        ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE kind='NEWS_SOURCE_SNAPSHOT'")
        before=ledger.count();head=ledger.head()
    code,report=invoke(files,capsys,now=NOW+100)
    assert code==2 and report['source_health']['state']=='RECOVERY_UNAVAILABLE'
    assert report['counts']=={'accepted':None,'duplicates':None,'skipped':None} and report['reconcile_required'] is True
    with closing(Ledger(files[2])) as ledger:assert ledger.count()==before and ledger.head()==head


def test_actual_cli_health_publication_failure_does_not_acknowledge_ready_source(files,capsys,monkeypatch):
    append=Ledger.append
    def fail(self,event):
        if event.kind is EventKind.MARKET_DATA_HEALTH:raise OSError('fixture health storage unavailable')
        return append(self,event)
    monkeypatch.setattr(Ledger,'append',fail)
    code,report=invoke(files,capsys)
    assert code==2 and report['source_health']['state']=='PERSISTENCE_UNAVAILABLE'
    assert report['source_health']['durable_health']=='UNKNOWN' and report['counts']['accepted']==1
    with closing(Ledger(files[2])) as ledger:assert ledger.count(EventKind.NEWS_HEADLINE)==1


def test_actual_cli_valid_empty_channel_is_only_an_empty_declared_snapshot(files,capsys):
    files[1].write_bytes(rss(''));code,report=invoke(files,capsys)
    assert code==0 and report['source_health']['state']=='EMPTY_DECLARED'
    assert report['counts']=={'accepted':0,'duplicates':0,'skipped':0} and report['headlines_recorded']==[]
    assert report['source_health']['coverage']=='DECLARED_SNAPSHOT_ONLY' and report['source_health']['provider_qualified'] is False


def test_actual_cli_closes_its_own_durable_connection(files,capsys,monkeypatch):
    close=Ledger.close;closed=[]
    def observed(self):
        close(self);closed.append(self)
    monkeypatch.setattr(Ledger,'close',observed)
    assert invoke(files,capsys)[0]==0
    assert len(closed)==1
