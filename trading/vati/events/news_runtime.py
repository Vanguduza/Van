"""Declared file snapshots and durable source-health observations; no feed admission."""
from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind,make_event
from vati.events.news_ingress import (
    DEFAULT_RELEVANCE_WINDOW_MS,NewsIngress,NewsIngressError,_milliseconds,
    rows_from_text,sources_from_config,
)
from vati.events.news_feed import FeedCapacityError,capture_snapshot,rss_rows
from vati.events.news_lineage import PublisherOrigin

HEALTH_PRODUCER='vati-news-file-health'


def news_heartbeat(news):
    """Publish the existing owner's news readback before or between bar cycles."""
    health=getattr(news,'source_health',None)
    if health is None:
        health={'state':'DISABLED' if news is None else 'UNQUALIFIED_HISTORY',
            'coverage':'DISABLED' if news is None else 'UNKNOWN',
            'provider_qualified': False,
            'live_eligible': False,'authority_effect':'NONE'}
    return {'source_health':deepcopy(health)}


def _options(config):
    if not isinstance(config,dict):raise NewsIngressError('news configuration must be an object')
    path=config.get('path')
    if path is not None and not isinstance(path,(str,Path)):
        raise NewsIngressError('news file path must be declared text')
    limits={
        'max_file_bytes':(8*1024*1024,64*1024*1024),
        'max_rows':(10000,1000000),
        'max_recovery_events':(100000,1000000),
        'relevance_window_ms':(DEFAULT_RELEVANCE_WINDOW_MS,2**63-1),
    }
    out={'path':None if not path else Path(path)}
    for name,(default,maximum) in limits.items():
        value=config.get(name,default)
        if type(value) is not int or not 1<=value<=maximum:
            raise NewsIngressError('news capacity/window invalid: '+name)
        out[name]=value
    if not isinstance(config.get('sources',[]),list):raise NewsIngressError('news sources must be an array')
    sources=sources_from_config(config);seen={}
    for source in sources:
        if not source.source_id.strip():raise NewsIngressError('news source identity unavailable')
        prior=seen.setdefault(source.source_id,source)
        if prior!=source:raise NewsIngressError('news source declaration conflicts')
    out['sources']=sources
    input_format=config.get('input_format','json')
    if input_format not in ('json','rss2'):raise NewsIngressError('unsupported news input format')
    out['input_format']=input_format
    if input_format=='rss2':
        PublisherOrigin(config.get('publisher_id'),config.get('source_id'))
        out.update(publisher_id=config['publisher_id'],source_id=config['source_id'])
        relevance=config.get('relevance',{})
        if not isinstance(relevance,dict) or set(relevance)-{'currencies','asset_classes','symbols','event_class'}:
            raise NewsIngressError('unsupported RSS relevance declaration')
        NewsIngress().headline_from_row({'source_id':out['source_id'],'title':'profile validation',
            'published_ms':0,'observed_ms':0,**relevance})
        out['relevance']=dict(relevance)
    return out


def _profile(options):
    value={'path_ref':None if options['path'] is None else canonical_hash({'path':str(options['path'])}),
        'sources':[source.body() for source in sorted(options['sources'],key=lambda source:source.source_id)],
        **{name:options[name] for name in ('max_file_bytes','max_rows','max_recovery_events','relevance_window_ms')}}
    if options['input_format']=='rss2':
        value['adapter']={name:options[name] for name in ('input_format','source_id','publisher_id','relevance')}
    return value


def _durable_health(ledger,scope,material,checked_ms):
    def records():
        for event in ledger.iter(EventKind.MARKET_DATA_HEALTH,correlation_id=scope):
            if event.producer!=HEALTH_PRODUCER:continue
            if (event.hash!=canonical_hash(event.body()) or not isinstance(event.payload,dict)
                    or event.payload.get('format')!='news-file-health/1'):
                raise NewsIngressError('news health original is corrupt')
            yield event
    with ledger.atomic():
        previous=None
        for event in records():previous=event
        if previous is not None and previous.payload['material']==material:
            original=previous
        else:
            key=canonical_hash({'previous':None if previous is None else previous.hash,'material':material})
            original=make_event(EventKind.MARKET_DATA_HEALTH,HEALTH_PRODUCER,
                {'format':'news-file-health/1','health_key':key,'material':material,'checked_ms':checked_ms},
                event_time_ms=checked_ms,received_time_ms=checked_ms,correlation_id=scope)
            ledger.append(original)
    confirmed=[event for event in records() if event.hash==original.hash and event.payload==original.payload]
    if not confirmed:raise OSError('news health original durable publication not confirmed')
    return original


def _health(news,ledger,scope,state,now_ms,*,source_ref=None,input_hash=None,rows=None,
            skipped=None,error=None,persist=True):
    try:_milliseconds(now_ms)
    except (ValueError,TypeError):
        state='CLOCK_UNAVAILABLE';now_ms=None;persist=False;error='INVALID_SERVICE_CLOCK'
    coverage=('DECLARED_SNAPSHOT_ONLY' if state in {'READY_DECLARED','EMPTY_DECLARED'} else
              'PARTIAL' if state=='PARTIAL' else 'DISABLED' if state=='DISABLED' else 'UNKNOWN')
    material={'source':'news','source_kind':'FILE_SNAPSHOT','source_scope':scope,
        'state':state,'coverage':coverage,'source_ref':source_ref,'input_sha256':input_hash,
        'source_profile':getattr(news,'_file_profile',None),
        'records_in_input':rows,'skipped_in_batch':skipped,'error_code':error,
        'provider_qualified':False,'live_eligible':False,'authority_effect':'NONE'}
    if getattr(news,'source_snapshot',None) is not None:
        material['last_known_source_snapshot']=dict(news.source_snapshot)
    health=dict(material,checked_ms=now_ms,clock_basis='SUPPLIED_SERVICE_CLOCK_NOT_NATIVE_PUBLISHER_ADMISSION',
        last_known_headlines=None if now_ms is None else len(news.headlines(since_ms=-(2**63),as_of_ms=now_ms)),
        durable_health='NOT_REQUESTED')
    if persist and ledger is not None and now_ms is not None:
        try:
            original=_durable_health(ledger,scope,material,now_ms)
            health.update(durable_health='CONFIRMED_ORIGINAL',receipt_hash=original.hash,
                transition_observed_ms=original.event_time_ms)
        except Exception as exc:
            health.update(state='PERSISTENCE_UNAVAILABLE',coverage='UNKNOWN',
                observed_file_state=state,durable_health='UNKNOWN',error_code=type(exc).__name__)
    elif not persist:health['durable_health']='UNCONFIRMED'
    news.source_health=health
    return health


def build_news_file(config,*,ledger,scope,now_ms,registry=None):
    if not config:return None
    options_error=None
    try:options=_options(config)
    except Exception as exc:
        options_error=exc;options=_options({})
    try:
        news=NewsIngress.from_ledger(ledger,registry=registry,sources=options['sources'],
            relevance_window_ms=options['relevance_window_ms'],max_events=options['max_recovery_events'])
        news._file_recovery_required=False
        news._file_recovery_limit_used=options['max_recovery_events']
    except Exception as exc:
        news=NewsIngress(ledger=ledger,registry=registry,sources=options['sources'],
            relevance_window_ms=options['relevance_window_ms'])
        news._file_recovery_required=True
        _health(news,ledger,scope,'RECOVERY_UNAVAILABLE',now_ms,error=type(exc).__name__,persist=False)
        return news
    if options_error is not None:
        _health(news,ledger,scope,'CONFIGURATION_ERROR',now_ms,error=type(options_error).__name__)
        return news
    refresh_news_file(news,config,ledger=ledger,scope=scope,now_ms=now_ms,registry=registry)
    return news


def refresh_news_file(news,config,*,ledger,scope,now_ms,registry=None):
    counts={'accepted':0,'duplicates':0,'skipped':0}
    try:_milliseconds(now_ms)
    except (ValueError,TypeError):
        return counts|{'source_health':_health(news,ledger,scope,'CLOCK_UNAVAILABLE',None,persist=False)}
    if not config:return counts|{'source_health':_health(news,ledger,scope,'DISABLED',now_ms)}
    try:options=_options(config)
    except Exception as exc:
        return counts|{'source_health':_health(news,ledger,scope,'CONFIGURATION_ERROR',now_ms,error=type(exc).__name__)}
    if getattr(news,'_file_recovery_limit_used',options['max_recovery_events'])!=options['max_recovery_events']:
        news._file_recovery_required=True
    if getattr(news,'_file_recovery_required',False):
        try:
            recovered=NewsIngress.from_ledger(ledger,registry=registry,sources=options['sources'],
                relevance_window_ms=options['relevance_window_ms'],max_events=options['max_recovery_events'])
            news.__dict__.update(recovered.__dict__);news._file_recovery_required=False
            news._file_recovery_limit_used=options['max_recovery_events']
        except Exception as exc:
            return counts|{'source_health':_health(news,ledger,scope,'RECOVERY_UNAVAILABLE',now_ms,
                error=type(exc).__name__,persist=False)}
    news._sources={source.source_id:source for source in options['sources']}
    news.relevance_window_ms=options['relevance_window_ms']
    news._file_profile=_profile(options)
    path=options['path'];source_ref=canonical_hash(news._file_profile)
    if path is None:
        return counts|{'source_health':_health(news,ledger,scope,'UNCONFIGURED',now_ms,source_ref=source_ref)}
    try:
        with path.open('rb') as stream:data=stream.read(options['max_file_bytes']+1)
        if len(data)>options['max_file_bytes']:
            return counts|{'source_health':_health(news,ledger,scope,'CAPACITY_EXCEEDED',now_ms,source_ref=source_ref,error='FILE_BYTES')}
        digest=hashlib.sha256(data).hexdigest()
        if options['input_format']=='rss2':
            try:
                news.source_snapshot=capture_snapshot(ledger,scope=scope,profile=news._file_profile,
                    raw=data,now_ms=now_ms,known=news._feed_snapshots)
                news._feed_snapshots[news.source_snapshot['snapshot_key']]=news.source_snapshot['receipt_hash']
            except Exception as exc:
                corrupt=isinstance(exc,ValueError)
                health=_health(news,ledger,scope,'RECOVERY_UNAVAILABLE' if corrupt else 'PUBLICATION_UNKNOWN',
                    now_ms,source_ref=source_ref,input_hash=digest,error=type(exc).__name__,persist=not corrupt)
                return {'accepted':None,'duplicates':None,'skipped':None,'reconcile_required':True,'source_health':health}
            rows=rss_rows(data,source_id=options['source_id'],publisher_id=options['publisher_id'],
                observed_ms=news.source_snapshot['captured_ms'],max_rows=options['max_rows'],relevance=options['relevance'])
        else:
            news.source_snapshot=None
            rows=rows_from_text(data.decode('utf-8'),suffix=path.suffix)
        if len(rows)>options['max_rows']:
            return counts|{'source_health':_health(news,ledger,scope,'CAPACITY_EXCEEDED',now_ms,
                source_ref=source_ref,input_hash=digest,error='ROW_COUNT')}
    except FileNotFoundError:
        return counts|{'source_health':_health(news,ledger,scope,'MISSING',now_ms,source_ref=source_ref)}
    except FeedCapacityError:
        return counts|{'source_health':_health(news,ledger,scope,'CAPACITY_EXCEEDED',now_ms,
            source_ref=source_ref,input_hash=digest,error='RSS_CAPACITY')}
    except Exception as exc:
        return counts|{'source_health':_health(news,ledger,scope,'UNREADABLE',now_ms,source_ref=source_ref,error=type(exc).__name__)}
    before=len(news.skipped)
    try:counts=news.ingest_rows(rows,now_ms=now_ms)
    except Exception as exc:
        health=_health(news,ledger,scope,'PUBLICATION_UNKNOWN',now_ms,source_ref=source_ref,
            input_hash=digest,error=type(exc).__name__,persist=False)
        return {'accepted':None,'duplicates':None,'skipped':None,'reconcile_required':True,'source_health':health}
    skipped=len(news.skipped)-before
    state='PARTIAL' if skipped else 'READY_DECLARED' if rows else 'EMPTY_DECLARED'
    return counts|{'source_health':_health(news,ledger,scope,state,now_ms,source_ref=source_ref,
        input_hash=digest,rows=len(rows),skipped=skipped)}
