"""Typed, hashed live-evidence references for the LearningBoundary (C5).

EXPERIENCE asks the question. EVIDENCE establishes what happened. AUTHORITY
decides what may change. Hindsight, OpenViking and DEIL may produce
hypotheses, research priorities, explanations and candidate lessons; none of
them is ever evidence for a LiveAdjustment.

A live-evidence reference has exactly one grammar::

    vati-evidence:<CLASS>:<64-hex sha256>

where CLASS is one of the allowlisted `EvidenceClass` values and the hash is
the canonical hash (`vati.core.canonical`) of the evidence content. A
reference is only an address: it carries no weight of its own. An
`EvidenceResolver` turns it into an immutable `EvidenceRecord` whose identity
is re-verified against its content, whose environment is read from that
content (never from the caller), and whose weight comes from the existing VATI
environment tables (`vati.learning.episodes.ENVIRONMENT_WEIGHT` /
`EXECUTION_FACT_WEIGHT`). Unresolvable references are rejected; duplicate
references count once.

A-VATI (review D): a class resolves only an allowlisted (kind, producer)
pair (`EVIDENCE_SOURCE_ALLOWLIST`); derived producers and kinds are never
evidence; and the environment comes from the runtime binding of the ledger the
resolver reads, which a payload may lower but never raise.

Only ledger-resolved evidence is admitted. There is no public registration
path: every record the boundary weighs was read back from the hash-chained
VATI ledger by `LedgerEvidenceResolver` (identity = `Event.hash`), directly or
through a `ResolvedEvidenceCache` that can only be filled by that resolver.
The boundary accepts only these exact resolver types.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from vati.core.canonical import canonical_json
from vati.core.events import EventKind
from vati.learning.episodes import ENVIRONMENT_WEIGHT, EXECUTION_FACT_WEIGHT, Environment

ZERO = Decimal(0)
EVIDENCE_REF_SCHEME = "vati-evidence"


class EvidenceError(ValueError):
    """A reference is malformed, not allowlisted, unresolvable or inconsistent."""


class EvidenceClass(str, Enum):
    LEDGER_EVENT = "LEDGER_EVENT"
    TCA_RECORD = "TCA_RECORD"
    TRADE_REVIEW = "TRADE_REVIEW"
    PNL_ATTRIBUTION = "PNL_ATTRIBUTION"
    STRATEGY_HEALTH_OBSERVATION = "STRATEGY_HEALTH_OBSERVATION"
    SHADOW_BOOK_OUTCOME = "SHADOW_BOOK_OUTCOME"
    VTIL_ARTIFACT = "VTIL_ARTIFACT"


# The mapping from each allowlisted C5 class to the real VATI artifact it names.
# Ledger-backed classes are resolved from the hash-chained `vati.core.ledger.Ledger`
# where identity = Event.hash = canonical_hash(Event.body()).
EVIDENCE_CLASS_SOURCES: Mapping[EvidenceClass, str] = {
    EvidenceClass.LEDGER_EVENT: "RESERVED, not resolvable: a generic ledger event names no fact the boundary can weigh. "
                                "Cite the allowlisted (kind, producer) class instead (A-VATI M1)",
    EvidenceClass.TCA_RECORD: "EventKind.TCA_RECORD ledger event written by the VATI runtime (vati.app.cycle / vati.app.trade_lifecycle, "
                              "compute_tca payload + learning context)",
    EvidenceClass.TRADE_REVIEW: "EventKind.TRADE_REVIEW ledger event written by the VATI runtime (vati.app.cycle / vati.app.trade_lifecycle review)",
    EvidenceClass.PNL_ATTRIBUTION: "EventKind.PNL_ATTRIBUTION ledger event (vati.cognition.attribution.AttributionEngine)",
    EvidenceClass.STRATEGY_HEALTH_OBSERVATION: "RESERVED, not resolvable: a vati.learning.health.HealthObservation is derived from a "
                                               "source event; cite that TRADE_REVIEW / TRADE_EXPERIENCE_ARTIFACT instead",
    EvidenceClass.SHADOW_BOOK_OUTCOME: "EventKind.SHADOW_DECISION ledger event (vati.cognition.shadow_book.ShadowBook)",
    EvidenceClass.VTIL_ARTIFACT: "EventKind.TRADE_EXPERIENCE_ARTIFACT ledger event written by the VATI runtime "
                                 "(ExperienceEpisode proposed to vati.vtil.admission)",
}

# The producers that write authoritative trade facts: the decision cycle and the
# account lifecycle. They are the only sources of TCA, review and experience
# artifacts; nothing derived (Hindsight, research, synthesis, lessons) is one.
RUNTIME_PRODUCERS = frozenset({"vati-cycle", "vati-account-lifecycle"})
PNL_ATTRIBUTION_PRODUCERS = frozenset({"vati-pnl-attribution"})   # vati.cognition.attribution.PRODUCER
SHADOW_BOOK_PRODUCERS = frozenset({"vati-shadow-book"})           # vati.cognition.shadow_book.PRODUCER

# A.VATI M1: every resolvable class is an allowlisted (kind, producers) pair. A
# class resolves only an event of exactly that kind written by one of those
# producers; there is no "any kind" class and no "any producer" class.
EVIDENCE_SOURCE_ALLOWLIST: Mapping[EvidenceClass, tuple[EventKind, frozenset[str]]] = {
    EvidenceClass.TCA_RECORD: (EventKind.TCA_RECORD, RUNTIME_PRODUCERS),
    EvidenceClass.TRADE_REVIEW: (EventKind.TRADE_REVIEW, RUNTIME_PRODUCERS),
    EvidenceClass.PNL_ATTRIBUTION: (EventKind.PNL_ATTRIBUTION, PNL_ATTRIBUTION_PRODUCERS),
    EvidenceClass.SHADOW_BOOK_OUTCOME: (EventKind.SHADOW_DECISION, SHADOW_BOOK_PRODUCERS),
    EvidenceClass.VTIL_ARTIFACT: (EventKind.TRADE_EXPERIENCE_ARTIFACT, RUNTIME_PRODUCERS),
}

# The decision-quality verdict of a trade (GAP-F-003) is the authoritative
# process_ok for strategy health when it exists (A-VATI M3).
DECISION_QUALITY_PRODUCERS = frozenset({"vati-decision-quality"})   # vati.cognition.attribution.DecisionQualityLedger

# Kept for callers: the event kind each resolvable class names.
LEDGER_EVENT_KIND: Mapping[EvidenceClass, EventKind] = {c: k for c, (k, _) in EVIDENCE_SOURCE_ALLOWLIST.items()}

# Classes whose authoritative payload carries no environment (e.g. TradeReview).
# Their environment is the runtime session environment bound into the resolver
# by its constructor (LearningHooks.environment, from the mandate mode) — never a
# per-call caller value.
SESSION_ENVIRONMENT_CLASSES = frozenset({EvidenceClass.TRADE_REVIEW})

# A class whose nature fixes its environment: a shadow-book outcome is a SHADOW
# fact whatever its payload claims.
CLASS_FIXED_ENVIRONMENT: Mapping[EvidenceClass, Environment] = {
    EvidenceClass.SHADOW_BOOK_OUTCOME: Environment.SHADOW,
}

# Experiential / derived / semantic sources. They may ask questions; they never
# answer them for the live path.
EXPERIENTIAL_SCHEMES = ("hindsight", "openviking", "viking", "deil")

# Producer names that mark a derived source. An event written by one of them is
# refused before the allowlist is even consulted, so widening the allowlist by
# mistake still cannot turn a derived output into live evidence.
DERIVED_PRODUCER_MARKERS = EXPERIENTIAL_SCHEMES + ("research", "synthesis", "lesson", "hypothes", "derived", "counterfactual", "evolution", "proposal")
# Event kinds that are derived outputs, never authoritative trade facts.
DERIVED_EVENT_KINDS = frozenset({
    EventKind.RESEARCH_MISSION, EventKind.RESEARCH_PACKET, EventKind.RESEARCH_SYNTHESIS, EventKind.RESEARCH_YIELD,
    EventKind.EXIT_POLICY_RESEARCH, EventKind.EVOLUTION_CANDIDATE, EventKind.IMPROVEMENT_PROPOSAL, EventKind.PROPOSAL_ADMISSION,
    EventKind.COGNITIVE_CONTEXT, EventKind.COGNITIVE_ASSESSMENT, EventKind.TRADE_LESSON, EventKind.CAPITAL_BUDGET_PROPOSAL,
})


def _is_derived_producer(producer: str) -> bool:
    low = producer.strip().lower()
    return any(m in low for m in DERIVED_PRODUCER_MARKERS)


assert not any(k in DERIVED_EVENT_KINDS for k, _ in EVIDENCE_SOURCE_ALLOWLIST.values()), "a derived event kind is allowlisted as live evidence"
assert not any(_is_derived_producer(p) for _, ps in EVIDENCE_SOURCE_ALLOWLIST.values() for p in ps), "a derived producer is allowlisted as live evidence"

_REF_RE = re.compile(r"vati-evidence:([A-Z_]+):([0-9a-f]{64})")
_HEX_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class EvidenceRef:
    evidence_class: EvidenceClass
    identity: str

    def __str__(self) -> str:
        return make_evidence_ref(self.evidence_class, self.identity)


def make_evidence_ref(evidence_class: EvidenceClass, identity: str) -> str:
    if not _HEX_RE.fullmatch(identity):
        raise EvidenceError("evidence identity must be a lowercase 64-hex sha256")
    return f"{EVIDENCE_REF_SCHEME}:{EvidenceClass(evidence_class).value}:{identity}"


def parse_evidence_ref(ref: object) -> EvidenceRef:
    if not isinstance(ref, str):
        raise EvidenceError(f"evidence reference must be a string, got {type(ref).__name__}")
    scheme = ref.split(":", 1)[0].strip().lower()
    if scheme in EXPERIENTIAL_SCHEMES or any(scheme.startswith(s) for s in EXPERIENTIAL_SCHEMES):
        raise EvidenceError(f"{scheme!r} is an experiential/derived source: it may propose a hypothesis, never live evidence")
    m = _REF_RE.fullmatch(ref)
    if m is None:
        raise EvidenceError(f"not a typed live-evidence reference (expected {EVIDENCE_REF_SCHEME}:<CLASS>:<64-hex>): {ref[:80]!r}")
    try:
        cls = EvidenceClass(m.group(1))
    except ValueError:
        raise EvidenceError(f"evidence class {m.group(1)!r} is not allowlisted") from None
    return EvidenceRef(cls, m.group(2))


def evidence_weight(environment: Environment, *, execution_facts: bool) -> Decimal:
    """Weight from the existing VATI tables. Execution facts from simulated
    environments (BACKTEST/REPLAY/COUNTERFACTUAL) weigh zero."""
    table = EXECUTION_FACT_WEIGHT if execution_facts else ENVIRONMENT_WEIGHT
    return table[environment]


# ---------------------------------------------------------------- records
def _payload(evidence_class: EvidenceClass, content: Mapping[str, Any]) -> Mapping[str, Any]:
    """Ledger bodies carry the fact in `payload`; flat in-memory records are the fact.

    A ledger body is admitted only when its (kind, producer) pair is allowlisted
    for the cited class (A-VATI M1). Derived producers are refused by name first."""
    if "kind" in content and "payload" in content and "producer" in content:
        if evidence_class not in EVIDENCE_SOURCE_ALLOWLIST:
            raise EvidenceError(f"{evidence_class.value} is not a ledger-backed class")
        want, producers = EVIDENCE_SOURCE_ALLOWLIST[evidence_class]
        producer = str(content["producer"])
        if _is_derived_producer(producer):
            raise EvidenceError(f"producer {producer!r} is a derived source: it may propose a hypothesis, never live evidence")
        if content["kind"] != want.value:
            raise EvidenceError(f"{evidence_class.value} must be a {want.value} ledger event, got {content['kind']}")
        if producer not in producers:
            raise EvidenceError(f"producer {producer!r} is not an allowlisted source of {evidence_class.value} (allowed: {sorted(producers)})")
        p = content["payload"]
        if not isinstance(p, Mapping):
            raise EvidenceError("ledger payload is not an object")
        return p
    return content


def _least_authoritative(fixed: Environment, ceiling: Environment) -> Environment:
    """The less authoritative of two environments, by (environment weight,
    execution-fact weight). On a tie the ledger binding wins."""
    rank = lambda e: (ENVIRONMENT_WEIGHT[e], EXECUTION_FACT_WEIGHT[e])
    return fixed if rank(fixed) < rank(ceiling) else ceiling


def _environment(evidence_class: EvidenceClass, p: Mapping[str, Any], session_environment: Optional[Environment],
                 environment_ceiling: Optional[Environment]) -> Environment:
    """The environment is the source's, not the payload author's (A-VATI M1).

    The resolver is bound to the runtime environment of the ledger it reads
    (`session_environment`, or `environment_ceiling` for a replay). That binding
    is the most authoritative environment any of the ledger's facts can carry: a
    payload may record a *less* authoritative one (a replayed or simulated fact
    written to a live ledger), never a more authoritative one. Without a binding
    nothing can be weighted.

    A class-fixed environment (a shadow-book outcome is SHADOW) is bounded by
    the same binding (A-MIN-VAN, reviewer D2): the record weighs as the less
    authoritative of the two, so a shadow outcome read from a BACKTEST/REPLAY
    ledger is a BACKTEST/REPLAY fact, never a SHADOW one."""
    ceiling = environment_ceiling if environment_ceiling is not None else session_environment
    if ceiling is None:
        raise EvidenceError(f"no environment is bound to this ledger: {evidence_class.value} evidence cannot be weighted")
    if evidence_class in CLASS_FIXED_ENVIRONMENT:
        return _least_authoritative(CLASS_FIXED_ENVIRONMENT[evidence_class], Environment(ceiling))
    raw = p.get("learning_environment", p.get("environment"))
    if raw is None and session_environment is not None and evidence_class in SESSION_ENVIRONMENT_CLASSES:
        return Environment(session_environment)
    if raw is None:
        raise EvidenceError(f"{evidence_class.value} evidence records no environment; it cannot be weighted")
    try:
        env = Environment(str(raw))
    except ValueError:
        raise EvidenceError(f"unknown evidence environment {raw!r}") from None
    if ENVIRONMENT_WEIGHT[env] > ENVIRONMENT_WEIGHT[Environment(ceiling)]:
        raise EvidenceError(f"{evidence_class.value} evidence claims environment {env.value}, more authoritative than the "
                            f"{Environment(ceiling).value} runtime its ledger is bound to")
    return env


def _subjects(p: Mapping[str, Any]) -> frozenset[str]:
    out = set()
    if p.get("strategy_id"):
        out.add(str(p["strategy_id"]))
    if all(p.get(k) for k in ("broker", "symbol", "session")):
        out.add(f"{p['broker']}:{p['symbol']}:{p['session']}")
    if p.get("regime"):
        out.add(str(p["regime"]))
    return frozenset(out)


# Payload fields that name the trade a fact is about. When present they must
# agree with the ledger correlation id, which is the trade identity (A-VATI M2).
TRADE_ID_FIELDS = ("trade_intent_id", "episode_id")


def _trade_id(content: Mapping[str, Any], p: Mapping[str, Any], identity: str) -> str:
    """One trade is one sample: the identity of the trade a record is about.

    For a ledger event it is the correlation id (= trade_intent_id), which every
    artifact of that trade (TCA, review, experience artifact, attribution)
    carries. A payload that names a different trade is inconsistent."""
    if "kind" in content and "payload" in content and "producer" in content:
        corr = content.get("correlation_id")
        if not isinstance(corr, str) or not corr.strip():
            raise EvidenceError("ledger evidence names no trade (empty correlation_id); it cannot be a sample")
        for k in TRADE_ID_FIELDS:
            if p.get(k) is not None and str(p[k]) != corr:
                raise EvidenceError(f"evidence payload {k}={p[k]!r} disagrees with its ledger correlation_id {corr!r}")
        return corr
    for k in TRADE_ID_FIELDS:
        if p.get(k):
            return str(p[k])
    return identity


@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable resolved evidence. Content is held as canonical JSON so it
    cannot be mutated after its identity was verified. `trade_id` is the trade
    the fact is about: several records of one trade are one sample."""
    evidence_class: EvidenceClass
    identity: str
    canonical: str
    environment: Environment
    subjects: frozenset[str]
    trade_id: str

    @classmethod
    def from_content(cls, evidence_class: EvidenceClass, content: Mapping[str, Any], *, identity: Optional[str] = None,
                     session_environment: Optional[Environment] = None,
                     environment_ceiling: Optional[Environment] = None) -> "EvidenceRecord":
        evidence_class = EvidenceClass(evidence_class)
        canonical = canonical_json(content)
        computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if identity is not None and identity != computed:
            raise EvidenceError("evidence identity does not match its content hash")
        # Re-read from the canonical form: what is weighted is what was hashed.
        body = json.loads(canonical)
        p = _payload(evidence_class, body)
        return cls(evidence_class, computed, canonical, _environment(evidence_class, p, session_environment, environment_ceiling), _subjects(p),
                   _trade_id(body, p, computed))

    def verify(self) -> None:
        if hashlib.sha256(self.canonical.encode("utf-8")).hexdigest() != self.identity:
            raise EvidenceError("evidence content no longer matches its identity")

    @property
    def ref(self) -> str:
        return make_evidence_ref(self.evidence_class, self.identity)

    @property
    def content(self) -> Any:
        return json.loads(self.canonical)

    def weight(self, *, execution_facts: bool) -> Decimal:
        return evidence_weight(self.environment, execution_facts=execution_facts)


# -------------------------------------------------------------- resolvers
class TrustedEvidenceResolver:
    """Base of the resolver types the boundary accepts. Only the exact types in
    `TRUSTED_RESOLVER_TYPES` are honoured; a subclass is not trusted."""

    def resolve(self, ref: EvidenceRef, *, correlation_hint: Optional[str] = None) -> EvidenceRecord:   # pragma: no cover
        raise NotImplementedError


EvidenceResolver = TrustedEvidenceResolver   # public name kept for callers/typing


def _ledger_types() -> tuple[type, ...]:
    from vati.core.ledger import Ledger
    types: list[type] = [Ledger]
    try:
        from vati.core.ledger_pg import PostgresLedger
        types.append(PostgresLedger)
    except Exception:   # pragma: no cover - optional backend
        pass
    return tuple(types)


class LedgerEvidenceResolver(TrustedEvidenceResolver):
    """Resolves ledger-backed classes from the hash-chained VATI ledger.

    The resolver is bound to the runtime environment of that ledger:
    `session_environment` (the live runtime, bound once by LearningHooks) also
    supplies the environment of SESSION_ENVIRONMENT_CLASSES whose payload
    records none; `environment_ceiling` (replay) bounds recorded environments
    without supplying one. One of the two is required. `correlation_hint` only
    narrows the search; the hash must still match."""

    def __init__(self, ledger: Any, *, session_environment: Optional[Environment] = None,
                 environment_ceiling: Optional[Environment] = None) -> None:
        if not isinstance(ledger, _ledger_types()):
            raise EvidenceError("live evidence resolves only from a VATI ledger")
        if session_environment is None and environment_ceiling is None:
            raise EvidenceError("no environment is bound to this ledger: bind the runtime session_environment "
                                "(or an environment_ceiling for replay)")
        self.ledger = ledger
        self.session_environment = Environment(session_environment) if session_environment is not None else None
        self.environment_ceiling = Environment(environment_ceiling) if environment_ceiling is not None else None
        self._cache: dict[str, EvidenceRecord] = {}

    def _find(self, ref: EvidenceRef, correlation_hint: Optional[str]):
        kind = LEDGER_EVENT_KIND[ref.evidence_class]
        if correlation_hint is not None:
            for ev in self.ledger.iter(kind, correlation_id=correlation_hint):
                if ev.hash == ref.identity:
                    return ev
        for ev in self.ledger.iter(kind):
            if ev.hash == ref.identity:
                return ev
        return None

    def trade_fact(self, evidence_class: EvidenceClass, trade_id: str) -> Optional[EvidenceRecord]:
        """The latest allowlisted `evidence_class` event of one trade, resolved
        (e.g. the TCA_RECORD that holds a reviewed trade's cost ratio)."""
        kind, producers = EVIDENCE_SOURCE_ALLOWLIST[evidence_class]
        hit = None
        for ev in self.ledger.iter(kind, correlation_id=trade_id):
            if ev.producer in producers:
                hit = ev
        return None if hit is None else self.resolve(EvidenceRef(evidence_class, hit.hash), correlation_hint=trade_id)

    def decision_quality(self, trade_id: str) -> Optional[Mapping[str, Any]]:
        """The latest decision-quality verdict payload of one trade, if any."""
        hit = None
        for ev in self.ledger.iter(EventKind.DECISION_QUADRANT, correlation_id=trade_id):
            if ev.producer in DECISION_QUALITY_PRODUCERS and str(ev.payload.get("trade_intent_id", trade_id)) == trade_id:
                hit = ev
        return None if hit is None else json.loads(canonical_json(hit.payload))

    def resolve(self, ref: EvidenceRef, *, correlation_hint: Optional[str] = None) -> EvidenceRecord:
        if ref.evidence_class not in LEDGER_EVENT_KIND:
            raise EvidenceError(f"{ref.evidence_class.value} is not resolvable from the ledger")
        hit = self._cache.get(ref.identity)
        if hit is None:
            ev = self._find(ref, correlation_hint)
            if ev is not None:
                hit = EvidenceRecord.from_content(ref.evidence_class, ev.body(), identity=ref.identity,
                                                  session_environment=self.session_environment,
                                                  environment_ceiling=self.environment_ceiling)
                self._cache[ref.identity] = hit
        if hit is None or hit.evidence_class is not ref.evidence_class:
            raise EvidenceError(f"unresolvable evidence reference {ref}")
        hit.verify()
        return hit


class ResolvedEvidenceCache(TrustedEvidenceResolver):
    """Holds records that a LedgerEvidenceResolver has already resolved, so a
    producer can re-check its window cheaply. There is no way to register
    content: `admit` only accepts an exact LedgerEvidenceResolver."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    @staticmethod
    def resolve_from_ledger(ref: str | EvidenceRef, resolver: LedgerEvidenceResolver, *, correlation_hint: Optional[str] = None) -> EvidenceRecord:
        """Resolve through an exact LedgerEvidenceResolver without caching, so a
        producer can check a record before it admits it."""
        if type(resolver) is not LedgerEvidenceResolver:
            raise EvidenceError("only ledger-resolved evidence may be admitted")
        parsed = ref if isinstance(ref, EvidenceRef) else parse_evidence_ref(ref)
        rec = resolver.resolve(parsed, correlation_hint=correlation_hint)
        if rec.identity != parsed.identity or rec.evidence_class is not parsed.evidence_class:
            raise EvidenceError(f"resolver returned a different record for {parsed}")
        return rec

    def admit(self, ref: str | EvidenceRef, resolver: LedgerEvidenceResolver, *, correlation_hint: Optional[str] = None) -> EvidenceRecord:
        rec = self.resolve_from_ledger(ref, resolver, correlation_hint=correlation_hint)
        self._records.setdefault(rec.identity, rec)
        return self._records[rec.identity]

    def discard(self, ref: str) -> None:
        self._records.pop(parse_evidence_ref(ref).identity, None)

    def resolve(self, ref: EvidenceRef, *, correlation_hint: Optional[str] = None) -> EvidenceRecord:
        rec = self._records.get(ref.identity)
        if rec is None or rec.evidence_class is not ref.evidence_class:
            raise EvidenceError(f"unresolvable evidence reference {ref}")
        rec.verify()
        return rec

    def __len__(self) -> int:
        return len(self._records)


class CompositeEvidenceResolver(TrustedEvidenceResolver):
    def __init__(self, resolvers: Iterable[TrustedEvidenceResolver]) -> None:
        self.resolvers = tuple(resolvers)
        if not all(type(r) in TRUSTED_RESOLVER_TYPES for r in self.resolvers):
            raise EvidenceError("a composite may only contain trusted evidence resolvers")

    def resolve(self, ref: EvidenceRef, *, correlation_hint: Optional[str] = None) -> EvidenceRecord:
        for r in self.resolvers:
            try:
                return r.resolve(ref, correlation_hint=correlation_hint)
            except EvidenceError:
                continue
        raise EvidenceError(f"unresolvable evidence reference {ref}")


TRUSTED_RESOLVER_TYPES = (LedgerEvidenceResolver, ResolvedEvidenceCache, CompositeEvidenceResolver)


# ------------------------------------------------------------ evidence set
@dataclass(frozen=True)
class EvidenceSet:
    """Resolved, identity-de-duplicated evidence for one adjustment subject.

    Records are de-duplicated by identity, and samples are counted per trade
    (A-VATI M2): a TRADE_REVIEW and the TRADE_EXPERIENCE_ARTIFACT of the same
    trade are one sample, however many artifacts cite it. A trade cited through
    records of different environments weighs as its least authoritative one."""
    records: tuple[EvidenceRecord, ...]

    @classmethod
    def resolve(cls, refs: Iterable[object], resolver: Optional[EvidenceResolver], *, subject: str) -> "EvidenceSet":
        if resolver is None:
            raise EvidenceError("no EvidenceResolver: caller-supplied evidence carries no authority")
        if type(resolver) not in TRUSTED_RESOLVER_TYPES:
            raise EvidenceError(f"untrusted evidence resolver {type(resolver).__name__}: only ledger-rooted resolvers carry authority")
        parsed = [parse_evidence_ref(r) for r in refs]   # every ref must be well-formed, duplicates included
        if not parsed:
            raise EvidenceError("a live adjustment must cite evidence")
        seen: dict[str, EvidenceRecord] = {}
        for ref in parsed:
            if ref.identity in seen:
                continue
            rec = resolver.resolve(ref)
            if rec.identity != ref.identity or rec.evidence_class is not ref.evidence_class:
                raise EvidenceError(f"resolver returned a different record for {ref}")
            if subject not in rec.subjects:
                raise EvidenceError(f"evidence {ref} is not about {subject!r}")
            seen[ref.identity] = rec
        return cls(tuple(seen.values()))

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(r.ref for r in self.records)

    @property
    def trades(self) -> frozenset[str]:
        return frozenset(r.trade_id for r in self.records)

    def weighted_samples(self, *, execution_facts: bool) -> Decimal:
        per_trade: dict[str, Decimal] = {}
        for r in self.records:
            w = r.weight(execution_facts=execution_facts)
            per_trade[r.trade_id] = min(per_trade.get(r.trade_id, w), w)
        return sum(per_trade.values(), ZERO)
