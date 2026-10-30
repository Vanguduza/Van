"""Versioned original-publisher declarations, separate from admission and news IDs."""
from dataclasses import dataclass

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event


def _identity(value):
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('publisher/story identity must be bounded nonempty text without controls')
    return value


@dataclass(frozen=True)
class PublisherOrigin:
    publisher_id: str
    story_id: str

    def __post_init__(self):
        _identity(self.publisher_id)
        _identity(self.story_id)

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {'publisher_id', 'story_id'}:
            raise ValueError('original_publisher requires exactly publisher_id and story_id')
        return cls(**value)

    def body(self):
        return {'publisher_id': self.publisher_id, 'story_id': self.story_id}


def lineage_payload(origin, observation_id, headline_id, available_ms):
    return {'format': 'news-publisher-lineage/1', 'observation_id': observation_id,
            'headline_id': headline_id, 'origin': origin.body(), 'available_ms': available_ms,
            'provider_qualified': False, 'independence_qualified': False, 'authority_effect': 'NONE'}


def checked_lineage(event):
    value = event.payload
    try:
        origin = PublisherOrigin.parse(value['origin'])
        at = value['available_ms']
        if type(at) is not int or not -(2**63) <= at <= 2**63-1:
            raise ValueError('lineage declaration clock invalid')
        for name, size in (('observation_id', 64), ('headline_id', 32)):
            text = value[name]
            if not isinstance(text, str) or len(text) != size or any(c not in '0123456789abcdef' for c in text):
                raise ValueError('lineage observation identity invalid')
        if (value != lineage_payload(origin, value['observation_id'], value['headline_id'], at)
                or event.hash != canonical_hash(event.body())
                or event.correlation_id != value['headline_id']
                or event.event_time_ms != at or event.received_time_ms != at):
            raise ValueError('lineage original terms, seal or scope differ')
        return value
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('news publisher lineage original unavailable: ' + str(exc)) from exc


def read_lineage(ledger, producer, observation_id, headline_id):
    found = None
    for event in ledger.iter(EventKind.NEWS_LINEAGE, correlation_id=headline_id):
        if event.producer != producer:
            continue
        value = checked_lineage(event)
        if value['observation_id'] != observation_id:
            continue
        if found is not None:
            raise ValueError('news publisher lineage original is ambiguous')
        found = value
    return found


def append_lineage(ledger, producer, origin, observation_id, headline_id, available_ms):
    value = lineage_payload(origin, observation_id, headline_id, available_ms)
    ledger.append(make_event(EventKind.NEWS_LINEAGE, producer, value,
        event_time_ms=available_ms, received_time_ms=available_ms, correlation_id=headline_id))
    return value


def lineage_report(claims, origins, now_ms):
    """Connected declared stories; transport multiplicity cannot imply independence.

    Exact headline identity connects copies; an explicit publisher/story key also
    connects rewritten titles. Unknown origins stay unknown. No text similarity,
    publisher URL inference or caller qualification flag is a source authority.
    """
    parents = {}
    def find(key):
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key
    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parents[max(a, b)] = min(a, b)
    visible = []
    for oid, headline, available in claims:
        if max(headline.published_ms, available) > now_ms:
            continue
        hid = headline.headline_id
        key = 'headline:' + hid
        find(key)
        origin = origins.get(oid)
        if origin is not None and origin['available_ms'] > now_ms:
            origin = None
        if origin is not None:
            union(key, 'origin:' + canonical_hash(origin['origin']))
        visible.append((oid, headline, origin))
    groups = {}
    for oid, headline, origin in visible:
        group = groups.setdefault(find('headline:' + headline.headline_id), [])
        group.append((oid, headline, origin))
    clusters = []
    for values in groups.values():
        original_keys = {canonical_hash(v['origin']): v['origin'] for _, _, v in values if v is not None}
        unknown = sorted(oid for oid, _, value in values if value is None)
        hids = sorted({h.headline_id for _, h, _ in values})
        cluster = {'cluster_id': canonical_hash({'headlines': hids, 'origin_keys': sorted(original_keys)}),
            'headline_ids': hids, 'observation_ids': sorted(oid for oid, _, _ in values),
            'transport_source_ids': sorted({h.source_id for _, h, _ in values}),
            'declared_original_publishers': sorted({v['publisher_id'] for v in original_keys.values()}),
            'original_story_keys': [dict(original_keys[k]) for k in sorted(original_keys)],
            'unknown_origin_observations': unknown,
            'state': ('CONFLICTING_ORIGIN' if len(original_keys) > 1 else
                      'DECLARED_ORIGIN' if original_keys else 'UNKNOWN_ORIGIN'),
            'provider_qualified': False, 'independence_qualified': False}
        clusters.append(cluster)
    clusters.sort(key=lambda c: c['cluster_id'])
    return {'format': 'news-story-clusters/1', 'story_clusters': len(clusters),
            'unknown_origin_observations': sum(len(c['unknown_origin_observations']) for c in clusters),
            'qualified_independent_sources': 0, 'independence_state': 'UNQUALIFIED',
            'authority_effect': 'NONE', 'clusters': clusters}
