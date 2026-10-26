"""Headline ingress and event impact (GAP-F-003, REQ-TRD-05, REQ-FLOW-08).

The audit's finding was precise: "no news path beyond the calendar". The
economic calendar recorder (090) knows what is *scheduled* and what *printed*,
and that drives the tier-1 blackout. It knows nothing about the central bank
speaking off-diary, the counter suspended on the ZSE, or the export ban that
moves a metal — and so "does this news change my thesis" had no input at all.

This module is that input, and it is built so that it can only ever make VAN
more careful.

The authority boundary
----------------------
The economic calendar remains the **blackout authority**. Nothing here can put
an instrument into or out of a blackout window; `authority.py:tier1_event_blackout_active`
still comes from the calendar path alone. What this produces is an
`EventImpactAssessment` with a materiality score in [0, 1], and that score is
only ever consumed in two reduce-only places:

* the meta-labeller's `event_risk_multiplier`, which is bounded ≤ 1 and can
  only shrink a position (INV-RISK-001); and
* the `event impact` term of a `ThesisAssessment`, which can move a thesis
  toward RISKIER or WEAKER and never toward STRONGER.

`event_risk_multiplier_for` is the function that enforces this: it returns a
value in [floor, 1] and there is no code path through which a headline raises a
multiplier. A news source that could increase risk would be a news source worth
attacking.

Trust, not truth
----------------
A headline is not a fact. Sources carry a declared trust state — T1 for a
primary publisher (a central bank, an exchange, a statistics office), T2 for
secondary reporting, UNTRUSTED for anything unregistered — and materiality is
scaled by it. An unregistered source is admitted and recorded, because knowing
that something was said is useful, but it is weighted as the least reliable
input rather than silently dropped: a record that says "we saw this and trusted
it least" is evidence, and a missing record is not (INV-EVID-001).

Deduplication is by content hash over the normalised headline, so the same wire
story arriving twice through two transports is one record with two observations
rather than two events that look like corroboration.

Relevance is declared, never guessed
------------------------------------
The same argument `events/registry.py` makes about blackouts applies harder
here: inferring that a headline about "the Fed" touches XAUUSD by string
matching is how a protection gap gets built. Relevance goes through currency
legs, asset classes and explicitly declared counters, reusing `EventRegistry`'s
`InstrumentExposure`, and an instrument with no declaration is treated as
*potentially* affected by a T1 headline — the fail-closed direction, showing up
as excess caution rather than silent exposure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash, dec
from vati.core.calendar_time import parse_calendar_ms
from vati.core.events import EventKind, make_event
from vati.events.registry import AssetClass, EventRegistry, InstrumentExposure

PRODUCER = "vati-news-ingress"
INGRESS_VERSION = "news-ingress/5.1.2"
IMPACT_VERSION = "event-impact/5.1.2"

ZERO, ONE = Decimal("0"), Decimal("1")

#: The least a headline-derived multiplier may fall to. News reduces exposure;
#: it does not stand a mandated position down on its own — the calendar
#: blackout and the Risk Authority do that, with their own evidence.
EVENT_MULTIPLIER_FLOOR = Decimal("0.25")

#: How much of the available reduction a fully material T1 headline may apply.
MAX_EVENT_REDUCTION = ONE - EVENT_MULTIPLIER_FLOOR

#: Materiality below this is recorded and surfaced but changes no multiplier:
#: a permanently slightly-reduced book is a book whose risk controls have
#: stopped meaning anything.
MATERIALITY_ACTIONABLE = Decimal("0.2")

#: Trust weights. A T2 report of a T1 event is still a report.
TRUST_WEIGHT: dict[str, Decimal] = {
    "T1_PRIMARY": ONE,
    "T2_SECONDARY": Decimal("0.6"),
    "UNTRUSTED": Decimal("0.2"),
}

#: How long a headline is treated as bearing on an open position.
DEFAULT_RELEVANCE_WINDOW_MS = 6 * 3_600_000


class NewsIngressError(ValueError):
    pass


@dataclass(frozen=True)
class NewsRowFailure:
    position: str
    excerpt: str
    error: str


def _finite_decimal(value: Any, name: str) -> Decimal:
    try:
        result=dec(value)
    except (ValueError,TypeError,ArithmeticError) as exc:
        raise NewsIngressError(f'{name} must be a finite number') from exc
    if not result.is_finite():
        raise NewsIngressError(f'{name} must be a finite number')
    return result


def _milliseconds(value: Any) -> int:
    if type(value) is not int or not -(2**63)<=value<=2**63-1:
        raise NewsIngressError('news milliseconds must be a signed integer')
    return value


class SourceTrust(str, Enum):
    """What kind of source said it. Declared per source, never inferred."""

    T1_PRIMARY = "T1_PRIMARY"        # the issuer itself: central bank, exchange, agency
    T2_SECONDARY = "T2_SECONDARY"    # reporting on a primary
    UNTRUSTED = "UNTRUSTED"          # unregistered; recorded, weighted least

    @property
    def weight(self) -> Decimal:
        return TRUST_WEIGHT[self.value]


class Concern(str, Enum):
    """Which way a headline argues, from the position's point of view.

    Deliberately not "bullish"/"bearish": VAN is not forecasting from news. It
    is asking whether an open claim is more exposed than it was.
    """

    ADVERSE_TO_LONG = "ADVERSE_TO_LONG"
    ADVERSE_TO_SHORT = "ADVERSE_TO_SHORT"
    TWO_SIDED = "TWO_SIDED"          # raises uncertainty in both directions
    UNCLEAR = "UNCLEAR"              # relevant, direction not declared


@dataclass(frozen=True)
class NewsSource:
    """A registered publisher and the trust it carries."""

    source_id: str
    trust: SourceTrust
    label: str = ""

    def body(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "trust": self.trust.value, "label": self.label}


@dataclass(frozen=True)
class Headline:
    """One observed headline. Content-addressed, so duplicates collapse."""

    source_id: str
    trust: SourceTrust
    published_ms: int
    observed_ms: int
    title: str
    #: Currencies the publisher says this is about.
    currencies: tuple[str, ...] = ()
    #: Asset classes the publisher says this is about.
    asset_classes: tuple[AssetClass, ...] = ()
    #: Explicit instrument symbols (ZSE counters, index tickers).
    symbols: tuple[str, ...] = ()
    #: A registered event class name, when the headline is a scheduled release
    #: arriving early. The calendar still owns the blackout for it.
    event_class: str = ""
    #: Publisher-declared severity in [0, 1]. Absent means "unstated", which is
    #: scored as moderate rather than as zero.
    severity: Optional[Decimal] = None
    concern: Concern = Concern.UNCLEAR
    url: str = ""
    body_excerpt: str = ""

    def __post_init__(self) -> None:
        if not self.source_id:
            raise NewsIngressError("a headline with no source cannot be weighted")
        if not self.title.strip():
            raise NewsIngressError("a headline with no title carries nothing")
        _milliseconds(self.published_ms)
        _milliseconds(self.observed_ms)
        if self.severity is not None:
            severity=_finite_decimal(self.severity,'severity')
            if not ZERO<=severity<=ONE:
                raise NewsIngressError(f"severity {self.severity} is outside [0, 1]")
            object.__setattr__(self,'severity',severity)

    @property
    def normalised_title(self) -> str:
        return " ".join(self.title.upper().split())

    @property
    def dedupe_hash(self) -> str:
        """Identity is what was said and when it was published, not who relayed it."""
        return canonical_hash({
            "title": self.normalised_title,
            "published_ms": self.published_ms,
            "currencies": sorted(self.currencies),
            "event_class": self.event_class.upper(),
            "symbols": sorted(s.upper() for s in self.symbols),
        })

    @property
    def headline_id(self) -> str:
        return self.dedupe_hash[:32]

    def body(self) -> dict[str, Any]:
        return {
            "headline_id": self.headline_id,
            "dedupe_hash": self.dedupe_hash,
            "source_id": self.source_id,
            "trust": self.trust.value,
            "published_ms": self.published_ms,
            "observed_ms": self.observed_ms,
            "title": self.title[:500],
            "currencies": sorted(self.currencies),
            "asset_classes": sorted(a.value for a in self.asset_classes),
            "symbols": sorted(s.upper() for s in self.symbols),
            "event_class": self.event_class.upper(),
            "severity": None if self.severity is None else str(self.severity),
            "concern": self.concern.value,
            "url": self.url[:500],
            "body_excerpt": self.body_excerpt[:1000],
            "ingress_version": INGRESS_VERSION,
        }


@dataclass(frozen=True)
class EventImpactAssessment:
    """What one relevant headline means for one open position or candidate.

    `materiality` is bounded [0, 1] and is the only number that leaves this
    module. `uncertainty` says how much of the score rests on a source we do
    not fully trust, so a high-materiality/high-uncertainty pair reads as
    "something may have happened" rather than as "something happened".
    """

    impact_id: str
    headline_id: str
    subject_kind: str          # POSITION | CANDIDATE
    subject_id: str            # trade_intent_id or candidate_id
    symbol: str
    concern: Concern
    materiality: Decimal
    uncertainty: Decimal
    relevance_basis: str       # CURRENCY_LEG | ASSET_CLASS | DECLARED_SYMBOL | UNDECLARED
    evidence_refs: tuple[str, ...]
    assessed_ms: int
    impact_version: str = IMPACT_VERSION

    def __post_init__(self) -> None:
        if not (ZERO <= self.materiality <= ONE):
            raise NewsIngressError(f"materiality {self.materiality} is outside [0, 1]")
        if not (ZERO <= self.uncertainty <= ONE):
            raise NewsIngressError(f"uncertainty {self.uncertainty} is outside [0, 1]")

    @property
    def actionable(self) -> bool:
        return self.materiality >= MATERIALITY_ACTIONABLE

    def body(self) -> dict[str, Any]:
        return {
            "impact_id": self.impact_id,
            "headline_id": self.headline_id,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "symbol": self.symbol,
            "concern": self.concern.value,
            "materiality": str(self.materiality),
            "uncertainty": str(self.uncertainty),
            "relevance_basis": self.relevance_basis,
            "evidence_refs": list(self.evidence_refs),
            "actionable": self.actionable,
            "authority": "REDUCE_ONLY_CALENDAR_REMAINS_BLACKOUT_AUTHORITY",
            "assessed_ms": self.assessed_ms,
            "impact_version": self.impact_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


def event_risk_multiplier_for(materiality: Decimal, *,
                              floor: Decimal = EVENT_MULTIPLIER_FLOOR) -> Decimal:
    """Materiality -> a multiplier in [floor, 1]. Never above 1, by construction.

    This is the single function through which news reaches sizing, and it is
    written as `1 - reduction` rather than as a lookup so that "news cannot
    raise risk" is a property of the arithmetic rather than of a table somebody
    might extend.
    """
    floor=_finite_decimal(floor,'event multiplier floor')
    if not ZERO<=floor<=ONE:
        raise NewsIngressError('event multiplier floor is outside [0, 1]')
    m = max(ZERO, min(ONE, _finite_decimal(materiality,'materiality')))
    if m < MATERIALITY_ACTIONABLE:
        return ONE
    reduction = (ONE - floor) * m
    return max(floor, min(ONE, ONE - reduction))


@dataclass
class RelevanceMapper:
    """Which instruments a headline touches, from declared exposure only.

    Backed by `EventRegistry` so FX legs, metals, indices and rates use exactly
    the declarations the blackout path already uses. ZSE and other exchange
    counters are declared as `EQUITY` exposures with a venue, and a headline
    naming a counter matches it directly.
    """

    registry: EventRegistry

    def exposure_for(self, symbol: str) -> Optional[InstrumentExposure]:
        return self.registry.instrument(symbol)

    def relevance(self, headline: Headline, symbol: str) -> tuple[bool, str]:
        """(relevant, basis). Undeclared instruments are relevant to T1 news."""
        sym = symbol.upper()
        if sym in {s.upper() for s in headline.symbols}:
            return True, "DECLARED_SYMBOL"
        exposure = self.exposure_for(sym)
        if exposure is None:
            # Fail closed in the direction of caution, exactly as
            # EventRegistry.affects does for an undeclared instrument.
            return (headline.trust is SourceTrust.T1_PRIMARY), "UNDECLARED"
        if exposure.asset_class is AssetClass.SYNTHETIC:
            # A venue-constructed instrument has no external macro exposure.
            return False, "SYNTHETIC"
        if headline.event_class:
            cls = self.registry.event_class(headline.event_class)
            if cls is not None and cls.affects(exposure):
                return True, "EVENT_CLASS"
        legs = {c.upper() for c in headline.currencies} & {c.upper() for c in exposure.currencies}
        if legs:
            return True, "CURRENCY_LEG"
        if headline.asset_classes and exposure.asset_class in headline.asset_classes:
            return True, "ASSET_CLASS"
        return False, "NOT_RELEVANT"

    def affected(self, headline: Headline, universe: Iterable[str]) -> list[tuple[str, str]]:
        out = []
        for sym in universe:
            relevant, basis = self.relevance(headline, sym)
            if relevant:
                out.append((sym.upper(), basis))
        return sorted(out)


class NewsIngress:
    """Append-only headline store with dedupe, trust and impact assessment.

    Mirrors `CalendarRecorder`: a bad row is counted and skipped, never guessed
    at, and the ledger is the record of what was seen.
    """

    def __init__(self, *, registry: Optional[EventRegistry] = None, ledger=None,
                 sources: Optional[Iterable[NewsSource]] = None,
                 producer: str = PRODUCER,
                 relevance_window_ms: int = DEFAULT_RELEVANCE_WINDOW_MS) -> None:
        self.registry = registry or EventRegistry()
        self.mapper = RelevanceMapper(self.registry)
        self._ledger = ledger
        self._producer = producer
        self.relevance_window_ms = relevance_window_ms
        self._sources: dict[str, NewsSource] = {s.source_id: s for s in (sources or ())}
        self._headlines: dict[str, Headline] = {}
        self._observations: dict[str, list[str]] = {}
        self._relay_times: dict[str, dict[str, Optional[int]]] = {}
        self._claims: dict[str, list[tuple[Headline,int]]] = {}
        self._impacts: dict[str, list[EventImpactAssessment]] = {}
        self._published_observations: set[str] = set()
        self._published_impacts: set[str] = set()
        self._recovered=False
        self._legacy_headlines: set[str] = set()
        self._legacy_relays: dict[str,list[str]] = {}
        self.source_health: Optional[dict[str,Any]] = None
        self.skipped: list[dict[str, str]] = []

    @classmethod
    def from_ledger(cls,ledger,*,max_events: int=100000,**kwargs):
        """Restore a consistent checked snapshot without republishing originals.

        Full chain verification is deliberately a recovery operation, not an
        interruptible per-decision host budget or native feed qualification.
        """
        if type(max_events) is not int or not 1<=max_events<=1000000:
            raise NewsIngressError('news recovery capacity must be a positive bounded integer')
        try:
            recovered=cls(**kwargs)
            kinds=(EventKind.NEWS_HEADLINE,EventKind.NEWS_OBSERVATION,EventKind.EVENT_IMPACT)
            with ledger.read_snapshot():
                if sum(ledger.count(kind) for kind in kinds)>max_events:
                    raise NewsIngressError('news recovery capacity exhausted')
                if not ledger.verify_chain()[0]:raise NewsIngressError('news recovery ledger integrity unavailable')
                originals={}
                for event in ledger.iter(EventKind.NEWS_HEADLINE):
                    if event.producer!=recovered._producer:continue
                    if event.hash!=canonical_hash(event.body()):raise NewsIngressError('news original seal invalid')
                    headline=_headline_from_original(event.payload);hid=headline.headline_id
                    if (hid in originals or event.correlation_id!=hid
                            or event.event_time_ms!=headline.published_ms):
                        raise NewsIngressError('news original identity/scope is ambiguous')
                    at=_original_available_ms(event,headline);originals[hid]=event
                    recovered.ingest(headline,now_ms=at)
                    if 'full_claim' not in event.payload:
                        recovered._legacy_headlines.add(hid)
                        relays=event.payload.get('relayed_by',[headline.source_id])
                        if not isinstance(relays,list) or any(not isinstance(s,str) or not s.strip() for s in relays):
                            raise NewsIngressError('news legacy relay labels invalid')
                        for source in relays:
                            if source not in recovered._observations[hid]:
                                recovered._observations[hid].append(source)
                                recovered._relay_times[hid][source]=None
                                recovered._legacy_relays.setdefault(hid,[]).append(source)
                seen={}
                for event in ledger.iter(EventKind.NEWS_OBSERVATION):
                    if event.producer!=recovered._producer:continue
                    headline,at=_observation_from_event(event);oid=event.payload['observation_id'];hid=headline.headline_id
                    if oid in seen or hid not in originals:
                        raise NewsIngressError('news observation original is ambiguous or orphaned')
                    original=_headline_from_original(originals[hid].payload)
                    if original.dedupe_hash!=headline.dedupe_hash:
                        raise NewsIngressError('news observation original scope conflicts')
                    recovered.ingest(headline,now_ms=at);seen[oid]=at
                for hid,event in originals.items():
                    if 'full_claim' in event.payload:
                        headline=recovered._headlines[hid];oid=_observation_id(headline)
                        if seen.get(oid)!=_original_available_ms(event,headline):
                            raise NewsIngressError('news original observation missing or availability conflicts')
                recovered._published_observations=set(seen)
                for event in ledger.iter(EventKind.EVENT_IMPACT):
                    if event.producer!=recovered._producer:continue
                    impact=_impact_from_event(event)
                    if impact.headline_id not in originals or impact.impact_id in recovered._published_impacts:
                        raise NewsIngressError('news impact original is orphaned or ambiguous')
                    recovered._impacts.setdefault(impact.subject_id,[]).append(impact)
                    recovered._published_impacts.add(impact.impact_id)
            recovered._ledger=ledger;recovered._recovered=True
            return recovered
        except NewsIngressError:raise
        except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
            raise NewsIngressError('news recovery original format unavailable: '+str(exc)) from exc

    # ------------------------------------------------------------- sources
    def register_source(self, source: NewsSource) -> NewsSource:
        self._sources[source.source_id] = source
        return source

    def trust_for(self, source_id: str) -> SourceTrust:
        source = self._sources.get(source_id)
        return source.trust if source is not None else SourceTrust.UNTRUSTED

    # ------------------------------------------------------------ ingestion
    def ingest(self, headline: Headline, *, now_ms: Optional[int] = None) -> Optional[Headline]:
        """Record one headline. Returns None when it is a duplicate.

        A duplicate still records which source relayed it, because "three feeds
        carried it" is a fact about reach, not about corroboration.
        """
        hid = headline.headline_id
        if now_ms is not None:
            _milliseconds(now_ms)
        available_ms=max(headline.observed_ms,now_ms) if now_ms is not None else headline.observed_ms
        created=hid not in self._headlines
        original=headline
        original_available_ms=available_ms
        if self._ledger is not None:
            event,created,available_ms=self._publish_headline(headline,available_ms,now_ms)
            original=_headline_from_original(event.payload)
            original_available_ms=_original_available_ms(event,original)
            self._published_observations.add(_observation_id(headline))
        if hid not in self._headlines:
            self._headlines[hid]=original
            self._claims[hid]=[(original,original_available_ms)]
            self._relay_times[hid]={original.source_id:original_available_ms}
            self._observations[hid]=[original.source_id]
        claims=self._claims.setdefault(hid,[])
        original_capture=next((at for h,at in claims if h==headline),None)
        if original_capture is not None:
            available_ms=original_capture
        relayed=self._relay_times.setdefault(hid,{})
        prior_relay=relayed.get(headline.source_id)
        relayed[headline.source_id]=available_ms if prior_relay is None else min(prior_relay,available_ms)
        legacy=self._legacy_relays.get(hid,[])
        if headline.source_id in legacy:legacy.remove(headline.source_id)
        if original_capture is None:
            claims.append((headline,available_ms))
        relayers = self._observations.setdefault(hid, [])
        if headline.source_id not in relayers:
            relayers.append(headline.source_id)
        return headline if created else None

    def _publish_headline(self,headline: Headline,available_ms: int,ingress_ms):
        hid=headline.headline_id
        oid=_observation_id(headline)
        def read():
            found=None
            for event in self._ledger.iter(EventKind.NEWS_HEADLINE,correlation_id=hid):
                if event.producer!=self._producer:continue
                if event.hash!=canonical_hash(event.body()):
                    raise NewsIngressError('news original publication is corrupt')
                stored=_headline_from_original(event.payload)
                if (stored.dedupe_hash!=headline.dedupe_hash or event.event_time_ms!=stored.published_ms):
                    raise NewsIngressError('news original publication scope conflicts')
                _original_available_ms(event,stored)
                if found is not None:
                    raise NewsIngressError('news original publication is ambiguous')
                found=event
            return found
        created=False
        def read_observation(target_id=oid,expected=headline):
            found=None
            for event in self._ledger.iter(EventKind.NEWS_OBSERVATION,correlation_id=hid):
                if event.producer!=self._producer:continue
                stored,at=_observation_from_event(event)
                if event.payload['observation_id']!=target_id:continue
                if stored!=expected:
                    raise NewsIngressError('news observation original terms conflict')
                if found is not None:raise NewsIngressError('news observation original is ambiguous')
                found=(event,at)
            return found
        with self._ledger.atomic():
            original=read()
            if original is None:
                orphaned=any(event.producer==self._producer for event in
                    self._ledger.iter(EventKind.NEWS_OBSERVATION,correlation_id=hid))
                if hid in self._headlines or orphaned:
                    raise NewsIngressError('news original publication missing; not recreated')
                self._ledger.append(make_event(EventKind.NEWS_HEADLINE,self._producer,
                    headline.body()|{'relayed_by':[headline.source_id],
                    'full_claim':_full_claim(headline),'original_available_ms':available_ms,
                    'native_clock_qualified':False},event_time_ms=headline.published_ms,
                    received_time_ms=available_ms,correlation_id=hid))
                created=True
            elif 'full_claim' in original.payload:
                first=_headline_from_original(original.payload)
                if read_observation(_observation_id(first),first) is None:
                    raise NewsIngressError('news required original observation missing; not recreated')
            if read_observation() is None:
                if oid in self._published_observations:
                    raise NewsIngressError('news observation original missing; not recreated')
                self._ledger.append(make_event(EventKind.NEWS_OBSERVATION,self._producer,
                    {'format':'news-observation/1','observation_id':oid,
                     'headline_id':hid,'dedupe_hash':headline.dedupe_hash,
                     'full_claim':_full_claim(headline),'available_ms':available_ms,
                     'supplied_ingress_ms':ingress_ms,'provider_qualified':False,'authority_effect':'NONE'},
                    event_time_ms=headline.published_ms,received_time_ms=available_ms,correlation_id=hid))
        original=read()
        if original is None:
            raise OSError('news original durable publication not confirmed')
        observation=read_observation()
        if observation is None:raise OSError('news observation original durable publication not confirmed')
        return original,created,observation[1]

    def ingest_rows(self, rows: Iterable[Mapping[str, Any] | NewsRowFailure], *,
                    now_ms: Optional[int] = None) -> dict[str, int]:
        accepted = duplicates = 0
        for row in rows:
            if isinstance(row,NewsRowFailure):
                self.skipped.append({'row':row.excerpt,'error':row.position+': '+row.error})
                continue
            try:
                headline = self.headline_from_row(row)
            except Exception as exc:  # noqa: BLE001 — a bad row is skipped, never guessed
                self.skipped.append({"row": str(row)[:200], "error": str(exc)[:200]})
                continue
            if self.ingest(headline, now_ms=now_ms) is None:
                duplicates += 1
            else:
                accepted += 1
        return {"accepted": accepted, "duplicates": duplicates, "skipped": len(self.skipped)}

    def headline_from_row(self, row: Mapping[str, Any]) -> Headline:
        source_id = str(row.get("source") or row.get("source_id") or "").strip()
        if not source_id:
            raise NewsIngressError("headline row has no source")
        declared = row.get("trust")
        registered=self.trust_for(source_id)
        requested=SourceTrust(str(declared).upper()) if declared else registered
        trust=min((requested,registered),key=lambda state:state.weight)
        published=_row_time(row,('published','published_ms','observed','observed_ms'))
        observed=_row_time(row,('observed','observed_ms'),default=published)
        severity = row.get("severity")
        return Headline(
            source_id=source_id,
            trust=trust,
            published_ms=published,
            observed_ms=observed,
            title=str(row.get("title") or row.get("headline") or ""),
            currencies=tuple(sorted(_split(row.get("currencies")))),
            asset_classes=tuple(AssetClass(a) for a in sorted(_split(row.get("asset_classes")))),
            symbols=tuple(sorted(_split(row.get("symbols")))),
            event_class=str(row.get("event_class") or "").strip(),
            severity=(None if severity is None or str(severity).strip() == ""
                      else dec(str(severity))),
            concern=Concern(str(row.get("concern") or "UNCLEAR").upper()),
            url=str(row.get("url") or ""),
            body_excerpt=str(row.get("body") or row.get("body_excerpt") or ""),
        )

    # -------------------------------------------------------------- reading
    def headlines(self, *, since_ms: int = 0, limit: Optional[int] = None,
                  as_of_ms: Optional[int] = None) -> list[Headline]:
        if as_of_ms is not None:
            _milliseconds(as_of_ms)
        available=[]
        for hid,original in self._headlines.items():
            if as_of_ms is None:
                available.append(original)
                continue
            claims=[(h,available_ms) for h,available_ms in self._claims.get(hid,())
                    if h.published_ms<=as_of_ms and available_ms<=as_of_ms]
            if claims:
                available.append(min(claims,key=lambda claim:claim[1])[0])
        rows = sorted(
            (h for h in available if h.published_ms >= since_ms),
            key=lambda h: (h.published_ms, h.headline_id), reverse=True)
        return rows[:limit] if limit else rows

    def relayed_by(self, headline_id: str, *, as_of_ms: Optional[int] = None) -> tuple[str, ...]:
        if as_of_ms is not None:
            _milliseconds(as_of_ms)
        return tuple(source for source in self._observations.get(headline_id, ())
                     if as_of_ms is None or (self._relay_times[headline_id].get(source) is not None
                         and self._relay_times[headline_id][source]<=as_of_ms))

    # ------------------------------------------------------------ materiality
    def _available_at(self,headline: Headline,now_ms: int) -> bool:
        if headline.published_ms>now_ms or headline.observed_ms>now_ms:
            return False
        captures=[at for h,at in self._claims.get(headline.headline_id,()) if h==headline]
        return not captures or min(captures)<=now_ms

    def materiality(self, headline: Headline, *, basis: str,
                    now_ms: int) -> tuple[Decimal, Decimal]:
        """(materiality, uncertainty), both in [0, 1].

        Built from three declared facts and nothing inferred: the publisher's
        severity (moderate when unstated), the source's trust weight, and how
        directly the instrument is exposed. Age decays it linearly across the
        relevance window, so an old headline stops arguing rather than arguing
        forever.
        """
        _milliseconds(now_ms)
        if not self._available_at(headline,now_ms):
            return ZERO,ONE
        severity = headline.severity if headline.severity is not None else Decimal("0.5")
        basis_weight = {
            "DECLARED_SYMBOL": ONE,
            "EVENT_CLASS": Decimal("0.9"),
            "CURRENCY_LEG": Decimal("0.8"),
            "ASSET_CLASS": Decimal("0.6"),
            "UNDECLARED": Decimal("0.5"),
        }.get(basis, Decimal("0.4"))
        age = max(0, now_ms - headline.published_ms)
        if self.relevance_window_ms <= 0 or age >= self.relevance_window_ms:
            freshness = ZERO
        else:
            freshness = ONE - Decimal(age) / Decimal(self.relevance_window_ms)
        score = severity * headline.trust.weight * basis_weight * freshness
        materiality = max(ZERO, min(ONE, score))
        uncertainty = max(ZERO, min(ONE, ONE - headline.trust.weight))
        return materiality, uncertainty

    def assess(self, headline: Headline, *, subject_kind: str, subject_id: str,
               symbol: str, now_ms: int, persist: bool = True,
               extra_evidence: tuple[str, ...] = ()) -> Optional[EventImpactAssessment]:
        """Link one headline to one position or candidate, or return None.

        None means "not relevant to this instrument", which is a different fact
        from "relevant with materiality zero" and is not written to the ledger.
        """
        _milliseconds(now_ms)
        if not self._available_at(headline,now_ms):
            return None
        relevant, basis = self.mapper.relevance(headline, symbol)
        if not relevant:
            return None
        materiality, uncertainty = self.materiality(headline, basis=basis, now_ms=now_ms)
        evidence_refs=tuple(dict.fromkeys(
            (headline.dedupe_hash,) + self.relayed_by(headline.headline_id,as_of_ms=now_ms)
            + tuple(extra_evidence)))
        impact = EventImpactAssessment(
            impact_id=canonical_hash({
                "headline_claim":_full_claim(headline),"subject": subject_id,
                "subject_kind":subject_kind,
                "symbol": symbol.upper(), "at": now_ms,
                "basis":basis,"evidence_refs":evidence_refs,
                "materiality":str(materiality),"uncertainty":str(uncertainty),
                "impact_version":IMPACT_VERSION,
            })[:24],
            headline_id=headline.headline_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            symbol=symbol.upper(),
            concern=headline.concern,
            materiality=materiality,
            uncertainty=uncertainty,
            relevance_basis=basis,
            evidence_refs=evidence_refs,
            assessed_ms=now_ms,
        )
        if persist:
            self.persist_impact(impact, headline, now_ms=now_ms)
        existing=self._impacts.setdefault(subject_id,[])
        prior=next((item for item in existing if item.impact_id==impact.impact_id),None)
        if prior is not None and prior!=impact:
            raise NewsIngressError('news impact identity conflicts with original terms')
        if prior is None:
            existing.append(impact)
        return impact

    def persist_impact(self, impact: EventImpactAssessment, headline: Headline,
                       *, now_ms: Optional[int] = None) -> None:
        """Write one assessed impact to the ledger. No-op without a ledger.

        Separated from `assess` so a caller that assesses a whole universe can
        decide what is worth keeping — a candidate scan touches every symbol on
        every cycle, and recording a non-actionable impact for each of them on
        each pass would bury the ones that argue for something.
        """
        if self._ledger is None:
            return
        at = now_ms if now_ms is not None else impact.assessed_ms
        _milliseconds(at)
        self.ingest(headline,now_ms=at)
        payload=impact.body()|{'impact_hash':impact.digest,'headline_title':headline.title[:300]}
        def read():
            found=None
            for event in self._ledger.iter(EventKind.EVENT_IMPACT,correlation_id=impact.subject_id):
                if event.producer!=self._producer:continue
                if not isinstance(event.payload,dict) or event.hash!=canonical_hash(event.body()):
                    raise NewsIngressError('news impact original is corrupt')
                if event.payload.get('impact_id')!=impact.impact_id:continue
                if event.payload!=payload or event.event_time_ms!=impact.assessed_ms:
                    raise NewsIngressError('news impact original terms conflict')
                if found is not None:raise NewsIngressError('news impact original is ambiguous')
                found=event
            return found
        with self._ledger.atomic():
            if read() is None:
                # persist=False assessments may be recorded later. They are not
                # evidence that a durable original already existed.
                if impact.impact_id in self._published_impacts:
                    raise NewsIngressError('news impact original missing; not recreated')
                self._ledger.append(make_event(EventKind.EVENT_IMPACT,self._producer,payload,
                    event_time_ms=impact.assessed_ms,received_time_ms=max(at,impact.assessed_ms),
                    correlation_id=impact.subject_id))
        if read() is None:raise OSError('news impact original durable publication not confirmed')
        self._published_impacts.add(impact.impact_id)

    def assess_subject(self, *, subject_kind: str, subject_id: str, symbol: str,
                       direction: Optional[str] = None, now_ms: int,
                       since_ms: Optional[int] = None,
                       persist: bool = True) -> list[EventImpactAssessment]:
        """Every relevant headline in the window, assessed against one subject.

        `direction` filters to headlines whose declared concern argues against
        the position held: a LONG is not made riskier by news that is adverse
        to shorts. TWO_SIDED and UNCLEAR always count, because raised
        uncertainty is adverse to any open claim.
        """
        floor = since_ms if since_ms is not None else now_ms - self.relevance_window_ms
        adverse_for = {
            "LONG": (Concern.ADVERSE_TO_LONG, Concern.TWO_SIDED, Concern.UNCLEAR),
            "SHORT": (Concern.ADVERSE_TO_SHORT, Concern.TWO_SIDED, Concern.UNCLEAR),
        }
        wanted = adverse_for.get((direction or "").upper())
        out: list[EventImpactAssessment] = []
        for headline in self.headlines(since_ms=floor,as_of_ms=now_ms):
            if wanted is not None and headline.concern not in wanted:
                continue
            impact = self.assess(
                headline, subject_kind=subject_kind, subject_id=subject_id,
                symbol=symbol, now_ms=now_ms, persist=persist)
            if impact is not None:
                out.append(impact)
        return out

    def impacts_for(self, subject_id: str) -> list[EventImpactAssessment]:
        return list(self._impacts.get(subject_id, ()))

    def candidate_subject_id(self, symbol: str) -> str:
        """The stable subject id a candidate scan links its impacts to."""
        return f"candidate:{symbol.upper()}"

    def candidate_risk(self, symbol: str, *, now_ms: int,
                       persist: bool = True) -> tuple[Decimal, Decimal, tuple[str, ...]]:
        """`(multiplier, materiality, evidence_refs)` for a candidate on `symbol`.

        This is the one place news reaches *sizing*, and it reaches it through
        `event_risk_multiplier_for`, which cannot return a number above 1. The
        meta-labeller then takes the `min` of this and its own event-window
        term, so a headline can only ever shrink a position (INV-RISK-001).

        No `direction` filter: a candidate has not chosen a side yet, so every
        relevant headline counts, including one that is adverse to the opposite
        side. Only actionable impacts are persisted — see `persist_impact`.
        """
        impacts = self.assess_subject(
            subject_kind="CANDIDATE", subject_id=self.candidate_subject_id(symbol),
            symbol=symbol, now_ms=now_ms, persist=False)
        materiality, refs = self.peak(impacts)
        if persist:
            for impact in impacts:
                if impact.actionable:
                    headline = self._headlines.get(impact.headline_id)
                    if headline is not None:
                        self.persist_impact(impact, headline, now_ms=now_ms)
        return event_risk_multiplier_for(materiality), materiality, refs

    @staticmethod
    def peak(impacts: Sequence[EventImpactAssessment]) -> tuple[Decimal, tuple[str, ...]]:
        """The worst materiality across a set, with its evidence refs.

        Max rather than sum: two reports of one event are not twice the event,
        and summing would let a busy news day stand a book down on arithmetic.
        """
        if not impacts:
            return ZERO, ()
        worst = max(impacts, key=lambda i: i.materiality)
        refs: list[str] = []
        for impact in impacts:
            for ref in impact.evidence_refs:
                if ref not in refs:
                    refs.append(ref)
        return worst.materiality, tuple(refs)

    # --------------------------------------------------------------- report
    def report(self, *, now_ms: int) -> dict[str, Any]:
        available=self.headlines(since_ms=-(2**63),as_of_ms=now_ms)
        by_trust: dict[str, int] = {}
        for h in available:
            by_trust[h.trust.value] = by_trust.get(h.trust.value, 0) + 1
        return {
            "ingress_version": INGRESS_VERSION,
            "headlines": len(available),
            "by_trust": dict(sorted(by_trust.items())),
            "sources": [s.body() for s in sorted(self._sources.values(),
                                                 key=lambda s: s.source_id)],
            "impacts": sum(i.assessed_ms<=now_ms for v in self._impacts.values() for i in v),
            "skipped": self.skipped,
            "relevance_window_ms": self.relevance_window_ms,
            "authority": "REDUCE_ONLY_CALENDAR_REMAINS_BLACKOUT_AUTHORITY",
            "provider_qualified":False,
            "authority_effect":"NONE",
            "availability_basis":"DECLARED_OBSERVATION_AND_SUPPLIED_INGRESS_CLOCK_NOT_NATIVE_CLOCK_ADMISSION",
            "timing_unqualified":[h.headline_id for h in available if h.observed_ms<h.published_ms],
            "recovered_from_ledger":self._recovered,
            "legacy_envelope_availability_unqualified":sorted(self._legacy_headlines & {h.headline_id for h in available}),
            "legacy_unqualified_relays":{h.headline_id:list(self._legacy_relays[h.headline_id])
                for h in available if self._legacy_relays.get(h.headline_id)},
            "source_health":None if self.source_health is None else dict(self.source_health),
            "now_ms": now_ms,
        }


# --------------------------------------------------------------------- parsing
def _full_claim(headline: Headline) -> dict[str, Any]:
    """Lossless internal claim; the existing display body remains bounded."""
    return {name:(value.value if isinstance(value,Enum) else
                  str(value) if isinstance(value,Decimal) else
                  [item.value if isinstance(item,Enum) else item for item in value]
                  if isinstance(value,tuple) else value)
            for name,value in vars(headline).items()}


def _headline_from_original(payload: dict[str,Any]) -> Headline:
    try:
        if not isinstance(payload,dict):raise ValueError('original payload must be an object')
        raw=payload.get('full_claim',payload)
        headline=_headline_from_claim(raw)
        expected=headline.body();expected.pop('ingress_version')
        if any(payload.get(name)!=value for name,value in expected.items()):
            raise ValueError('original headline terms or identity differ')
        if payload.get('ingress_version') not in {'news-ingress/5.1.0','news-ingress/5.1.1',INGRESS_VERSION}:
            raise ValueError('original headline version unavailable')
        if 'full_claim' in payload and _full_claim(headline)!=raw:
            raise ValueError('original full claim format differs')
        if 'full_claim' in payload and payload.get('native_clock_qualified') is not False:
            raise ValueError('raw news receipt cannot declare native clock qualification')
        return headline
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        raise NewsIngressError('news original format unavailable: '+str(exc)) from exc


def _headline_from_claim(raw) -> Headline:
    if not isinstance(raw,dict):raise ValueError('news claim must be an object')
    for name in ('source_id','title','event_class','url','body_excerpt'):
        if not isinstance(raw[name],str):raise ValueError('news claim text field invalid: '+name)
    for name in ('currencies','asset_classes','symbols'):
        if not isinstance(raw[name],list) or any(not isinstance(item,str) for item in raw[name]):
            raise ValueError('news claim scope field invalid: '+name)
    return Headline(source_id=raw['source_id'],trust=SourceTrust(raw['trust']),
        published_ms=raw['published_ms'],observed_ms=raw['observed_ms'],title=raw['title'],
        currencies=tuple(raw['currencies']),asset_classes=tuple(AssetClass(x) for x in raw['asset_classes']),
        symbols=tuple(raw['symbols']),event_class=raw['event_class'],
        severity=None if raw['severity'] is None else _finite_decimal(raw['severity'],'severity'),
        concern=Concern(raw['concern']),url=raw['url'],body_excerpt=raw['body_excerpt'])


def _observation_id(headline: Headline) -> str:
    return canonical_hash(_full_claim(headline))


def _observation_from_event(event):
    try:
        payload=event.payload
        if not isinstance(payload,dict) or event.hash!=canonical_hash(event.body()):
            raise ValueError('original observation seal invalid')
        headline=_headline_from_claim(payload['full_claim'])
        available=_milliseconds(payload['available_ms'])
        supplied=payload['supplied_ingress_ms']
        if supplied is not None:_milliseconds(supplied)
        expected_available=max(headline.observed_ms,supplied) if supplied is not None else headline.observed_ms
        expected={'format':'news-observation/1','observation_id':_observation_id(headline),
            'headline_id':headline.headline_id,'dedupe_hash':headline.dedupe_hash,
            'full_claim':_full_claim(headline),'available_ms':available,'supplied_ingress_ms':supplied,
            'provider_qualified':False,'authority_effect':'NONE'}
        if (payload!=expected or event.event_time_ms!=headline.published_ms
                or event.correlation_id!=headline.headline_id or event.received_time_ms!=available
                or expected_available!=available):
            raise ValueError('original observation scope/availability/format differs')
        return headline,available
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        raise NewsIngressError('news observation original unavailable: '+str(exc)) from exc


def _impact_from_event(event) -> EventImpactAssessment:
    try:
        payload=event.payload
        if not isinstance(payload,dict) or event.hash!=canonical_hash(event.body()):
            raise ValueError('original impact seal invalid')
        impact=EventImpactAssessment(impact_id=payload['impact_id'],headline_id=payload['headline_id'],
            subject_kind=payload['subject_kind'],subject_id=payload['subject_id'],symbol=payload['symbol'],
            concern=Concern(payload['concern']),materiality=_finite_decimal(payload['materiality'],'materiality'),
            uncertainty=_finite_decimal(payload['uncertainty'],'uncertainty'),relevance_basis=payload['relevance_basis'],
            evidence_refs=tuple(payload['evidence_refs']),assessed_ms=_milliseconds(payload['assessed_ms']),
            impact_version=payload['impact_version'])
        for name in ('impact_id','headline_id','subject_kind','subject_id','symbol','relevance_basis'):
            if not isinstance(payload[name],str) or not payload[name]:raise ValueError('original impact identity invalid')
        if not isinstance(payload['evidence_refs'],list) or any(not isinstance(ref,str) for ref in payload['evidence_refs']):
            raise ValueError('original impact references invalid')
        if (payload!=impact.body()|{'impact_hash':impact.digest,'headline_title':payload['headline_title']}
                or event.correlation_id!=impact.subject_id or event.event_time_ms!=impact.assessed_ms
                or impact.impact_version not in {'event-impact/5.1.0','event-impact/5.1.1',IMPACT_VERSION}
                or not isinstance(payload['headline_title'],str) or len(payload['headline_title'])>300):
            raise ValueError('original impact terms/scope/format differ')
        return impact
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        raise NewsIngressError('news impact original unavailable: '+str(exc)) from exc


def _original_available_ms(event,headline: Headline) -> int:
    if 'original_available_ms' in event.payload:
        available=_milliseconds(event.payload['original_available_ms'])
        if available!=event.received_time_ms or available<headline.observed_ms:
            raise NewsIngressError('news original availability conflicts')
        return available
    return max(_milliseconds(event.received_time_ms),headline.observed_ms)


def _split(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [str(v) for v in value]
    else:
        items = str(value).replace(",", "|").split("|")
    return {i.strip().upper() for i in items if i.strip()}


def _parse_ms(value: Any) -> int:
    return parse_calendar_ms(value)


def _row_time(row: Mapping[str, Any], names: tuple[str,...], *, default=None) -> int:
    for name in names:
        value=row.get(name)
        if value is not None and value!='':
            if name.endswith('_ms'):
                # A field explicitly named milliseconds has no seconds heuristic.
                if isinstance(value,str) and value.lstrip('-').isascii() and value.lstrip('-').isdigit():
                    value=int(value)
                return _milliseconds(value)
            return _parse_ms(value)
    if default is not None:
        return _milliseconds(default)
    raise NewsIngressError('headline timestamp unavailable')


def rows_from_file(path: str | Path, key: str = "headlines") -> list[dict | NewsRowFailure]:
    """JSON array, `{"headlines": [...]}`, or JSON Lines.

    JSON Lines is the shape a tailing transport produces, and a malformed line
    in the middle of a stream must not discard the lines around it.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return rows_from_text(text,suffix=p.suffix,key=key)


def rows_from_text(text: str,*,suffix: str,key: str='headlines') -> list[dict | NewsRowFailure]:
    if suffix.lower() in (".jsonl", ".ndjson"):
        out = []
        for number,line in enumerate(text.splitlines(),1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row=json.loads(line)
                if not isinstance(row,dict):raise ValueError('row must be an object')
                out.append(row)
            except (ValueError,TypeError) as exc:
                out.append(NewsRowFailure(f'line {number}',line[:200],
                    'invalid JSON' if isinstance(exc,json.JSONDecodeError) else 'row must be an object'))
        return out
    data = json.loads(text)
    if isinstance(data,list):rows=data
    elif isinstance(data,dict) and key in data:rows=data[key]
    else:raise NewsIngressError('news file requires a row array or '+key+' array')
    if not isinstance(rows,list):raise NewsIngressError('news file rows must be an array')
    return [row if isinstance(row,dict) else NewsRowFailure(f'row {index}',str(row)[:200],
        'row must be an object') for index,row in enumerate(rows,1)]


def sources_from_config(config: Mapping[str, Any]) -> list[NewsSource]:
    return [
        NewsSource(
            source_id=str(s["source_id"]),
            trust=SourceTrust(str(s.get("trust", "UNTRUSTED")).upper()),
            label=str(s.get("label", "")),
        )
        for s in config.get("sources", ())
    ]


__all__ = [
    "EVENT_MULTIPLIER_FLOOR", "IMPACT_VERSION", "INGRESS_VERSION",
    "MATERIALITY_ACTIONABLE", "Concern", "EventImpactAssessment", "Headline",
    "NewsIngress", "NewsIngressError", "NewsSource", "RelevanceMapper",
    "SourceTrust", "event_risk_multiplier_for", "rows_from_file",
    "sources_from_config",
]
