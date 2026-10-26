"""Bounded RSS2 snapshots. Capture, publication and admission are distinct clocks."""
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import xml.etree.ElementTree as ET

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.events.news_lineage import PublisherOrigin

SNAPSHOT_PRODUCER = 'vati-news-feed-snapshot'
PARSER_VERSION = 'news-rss2/1'


class FeedCapacityError(ValueError):
    pass


def _profile_capacity(profile):
    if not isinstance(profile,dict):raise ValueError('snapshot profile must be an object')
    cap=profile.get('max_file_bytes')
    if type(cap) is not int or not 1<=cap<=64*1024*1024:
        raise ValueError('snapshot byte capacity invalid')
    adapter=profile.get('adapter')
    if not isinstance(adapter,dict) or adapter.get('input_format')!='rss2':
        raise ValueError('snapshot RSS adapter profile unavailable')
    PublisherOrigin(adapter.get('publisher_id'),adapter.get('source_id'))
    return cap


def checked_snapshot(event):
    value = event.payload
    try:
        if not isinstance(value, dict):
            raise ValueError('snapshot must be an object')
        if set(value) != {'format','snapshot_key','scope','profile','raw_sha256','raw_base64',
                'captured_ms','parser_version','provider_qualified','native_clock_qualified','authority_effect'}:
            raise ValueError('snapshot fields differ')
        cap=_profile_capacity(value['profile'])
        if not isinstance(value['raw_base64'],str) or len(value['raw_base64'])>((cap+2)//3)*4:
            raise ValueError('snapshot raw byte capacity exceeded')
        raw = base64.b64decode(value['raw_base64'], validate=True)
        if len(raw)>cap:raise ValueError('snapshot raw byte capacity exceeded')
        at = value['captured_ms']
        if type(at) is not int or not -(2**63) <= at <= 2**63-1:
            raise ValueError('snapshot clock invalid')
        key = canonical_hash({'scope':value['scope'],'profile':value['profile'],'raw_sha256':value['raw_sha256'],
                              'parser_version':PARSER_VERSION})
        if (value['format'] != 'news-source-snapshot/1' or value['parser_version'] != PARSER_VERSION
                or hashlib.sha256(raw).hexdigest() != value['raw_sha256']
                or key != value['snapshot_key'] or event.correlation_id != key
                or event.event_time_ms != at or event.received_time_ms != at
                or event.producer != SNAPSHOT_PRODUCER or event.kind is not EventKind.NEWS_SOURCE_SNAPSHOT
                or event.hash != canonical_hash(event.body()) or value['provider_qualified'] is not False
                or value['native_clock_qualified'] is not False or value['authority_effect'] != 'NONE'):
            raise ValueError('snapshot identity, original bytes, scope, seal or qualification differ')
        return value
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError('news source snapshot original unavailable: ' + str(exc)) from exc


def capture_snapshot(ledger, *, scope, profile, raw, now_ms, known=None):
    """Serialize original capture identity and read its exact bytes back independently."""
    if type(now_ms) is not int or not -(2**63)<=now_ms<=2**63-1:
        raise ValueError('snapshot capture clock must be signed integer milliseconds')
    if not isinstance(scope,str) or not scope.strip():raise ValueError('snapshot scope unavailable')
    if not isinstance(raw,bytes) or len(raw)>_profile_capacity(profile):
        raise FeedCapacityError('snapshot byte capacity exceeded')
    digest = hashlib.sha256(raw).hexdigest()
    key = canonical_hash({'scope':scope,'profile':profile,'raw_sha256':digest,'parser_version':PARSER_VERSION})
    def read():
        found = None
        for event in ledger.iter(EventKind.NEWS_SOURCE_SNAPSHOT, correlation_id=key):
            value = checked_snapshot(event)
            if value['scope'] != scope or value['profile'] != profile or value['raw_sha256'] != digest:
                raise ValueError('news source snapshot original terms conflict')
            if found is not None:
                raise ValueError('news source snapshot original is ambiguous')
            found = event
        return found
    with ledger.atomic():
        original = read()
        if original is None:
            if known is not None and key in known:
                raise ValueError('news source snapshot original missing; not recreated')
            payload = {'format':'news-source-snapshot/1','snapshot_key':key,'scope':scope,'profile':profile,
                'raw_sha256':digest,'raw_base64':base64.b64encode(raw).decode('ascii'),'captured_ms':now_ms,
                'parser_version':PARSER_VERSION,'provider_qualified':False,'native_clock_qualified':False,
                'authority_effect':'NONE'}
            original = make_event(EventKind.NEWS_SOURCE_SNAPSHOT,SNAPSHOT_PRODUCER,payload,
                event_time_ms=now_ms,received_time_ms=now_ms,correlation_id=key)
            ledger.append(original)
    confirmed = read()
    if confirmed is None or confirmed.hash != original.hash or confirmed.payload != original.payload:
        raise OSError('news source snapshot original durable publication not confirmed')
    if known is not None and key in known and known[key]!=original.hash:
        raise ValueError('news source snapshot known original differs')
    return {'snapshot_key':key,'receipt_hash':original.hash,'raw_sha256':digest,
            'captured_ms':original.payload['captured_ms'],'parser_version':PARSER_VERSION,
            'provider_qualified':False,'native_clock_qualified':False,'authority_effect':'NONE'}


class _BoundedTree(ET.TreeBuilder):
    def __init__(self, max_rows):
        super().__init__(); self.depth=0; self.nodes=0; self.items=0; self.max_rows=max_rows

    def start(self, tag, attrs):
        self.depth += 1; self.nodes += 1
        if tag == 'item': self.items += 1
        if self.depth > 64 or self.nodes > 1_000_000 or self.items > self.max_rows:
            raise FeedCapacityError('RSS depth/node/item capacity exceeded')
        return super().start(tag, attrs)

    def end(self, tag):
        result=super().end(tag); self.depth -= 1; return result

    def doctype(self, name, pubid, system):
        raise ValueError('RSS DTD/entity declarations are unsupported')


def _text(item, name, *, required=False):
    matches=item.findall(name)
    if len(matches)>1: raise ValueError('ambiguous RSS field: '+name)
    value='' if not matches else ''.join(matches[0].itertext()).strip()
    if required and not value: raise ValueError('RSS field unavailable: '+name)
    return value


def rss_rows(raw, *, source_id, publisher_id, observed_ms, max_rows,relevance=None):
    from vati.events.news_ingress import NewsRowFailure
    # Decode explicitly before XML parsing: no hidden alternate-encoding DTD path.
    text=raw.decode('utf-8-sig')
    tree=ET.fromstring(text,parser=ET.XMLParser(target=_BoundedTree(max_rows)))
    channels=tree.findall('channel')
    if tree.tag!='rss' or tree.get('version')!='2.0' or len(channels)!=1:
        raise ValueError('expected one RSS2 channel')
    rows=[]
    for position,item in enumerate(channels[0].findall('item'),1):
        try:
            title=_text(item,'title',required=True)
            link=_text(item,'link')
            key=_text(item,'guid') or link
            origin=PublisherOrigin(publisher_id,key)
            date=parsedate_to_datetime(_text(item,'pubDate',required=True))
            if date.tzinfo is None or date.utcoffset() is None:
                raise ValueError('RSS publication requires an explicit timezone')
            delta=date.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
            published=(delta.days*86400+delta.seconds)*1000+delta.microseconds//1000
            rows.append({**(relevance or {}),'source_id':source_id,'title':title,'url':link,'body_excerpt':_text(item,'description'),
                'published_ms':published,'observed_ms':observed_ms,'original_publisher':origin.body()})
        except (ValueError,TypeError,OverflowError) as exc:
            rows.append(NewsRowFailure('RSS item '+str(position),'RSS item '+str(position),str(exc)))
    return rows
