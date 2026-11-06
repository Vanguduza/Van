"""Original baseline contributions, distinct from a shared risk snapshot.

An aggregate is a projection, never a new contribution by its displaying alias.
Only independently recovered, applied controls release their original scope.
This book supplies historical risk data; it grants no capital or execution.
"""
from dataclasses import asdict, dataclass, replace
from decimal import Decimal

from vati.core import EventKind, make_event
from vati.risk.account_context import inspect_context
from vati.risk.lockouts import _funding_baseline_held, _physical_baseline_unavailable
from vati.risk.physical_history import physical_financial_history


BASIS_EVENT = 'NATIVE_RISK_BASIS'
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS


@dataclass(frozen=True)
class OriginBaseline:
    peak: Decimal
    day: Decimal
    week: Decimal
    day_id: int
    week_id: int
    event_ref: str


@dataclass(frozen=True)
class BaselineProjection:
    peak: Decimal | None
    day: Decimal | None
    week: Decimal | None
    unresolved_refs: tuple[str, ...]

    @property
    def issue(self):
        return ('physical risk baselines require original-source reconciliation'
                if self.unresolved_refs else '')


def _money(value):
    # Zero and debt are real observations, not missing baselines.
    if isinstance(value, (bool, float)):
        raise ValueError('baseline must use exact money')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('baseline must be finite')
    return result


class PhysicalRiskBasisBook:
    def __init__(self, history):
        self.physical_account_key = history.physical_account_key
        self.monetary_scope_hash = history.monetary_scope_hash
        self.origins: dict[str, OriginBaseline] = {}
        self.unresolved_refs = set(history.unresolved_refs)
        self._basis = {}
        for fact in history.facts:
            try:
                self._fold(fact)
            except (KeyError, TypeError, ValueError, ArithmeticError):
                self.unresolved_refs.add(fact.event_ref)

    @classmethod
    def rebuild(cls, ledger, context, *, available_at_ms):
        return cls(physical_financial_history(ledger, context,
            available_at_ms=available_at_ms))

    def projection(self, now_ms):
        def maximum(values):
            return max(values, default=None)
        return BaselineProjection(maximum(v.peak for v in self.origins.values()),
            maximum(v.day for v in self.origins.values() if v.day_id == now_ms // DAY_MS),
            maximum(v.week for v in self.origins.values() if v.week_id == now_ms // WEEK_MS),
            tuple(sorted(self.unresolved_refs)))

    def _observed(self, alias, equity, now_ms, ref):
        old = self.origins.get(alias)
        return OriginBaseline(max(old.peak, equity) if old else equity,
            old.day if old and old.day_id == now_ms // DAY_MS else equity,
            old.week if old and old.week_id == now_ms // WEEK_MS else equity,
            now_ms // DAY_MS, now_ms // WEEK_MS, ref)

    def observation_event(self, context, *, now_ms, producer):
        """Plan a native observation; caller owns append/fence and readback.

        The previous original reference makes stale concurrent plans detectable
        during replay. Do not treat this uncommitted event as persisted evidence.
        """
        if (context.physical_account_key != self.physical_account_key
                or context.monetary_scope_hash != self.monetary_scope_hash):
            raise ValueError('baseline observation belongs to another account scope')
        source = inspect_context(context)
        if source['observed_at_ms'] > now_ms:
            raise ValueError('baseline observation is not available yet')
        own = self._observed(context.account_alias, source['equity'], now_ms, '')
        old = self.origins.get(context.account_alias)
        return make_event(EventKind.SESSION, producer, {
            'event': BASIS_EVENT, 'schema': 1, 'account_alias': context.account_alias,
            'native_account_context': asdict(context),
            'previous_origin_ref': old.event_ref if old else None,
            'peak_equity': str(own.peak), 'day_start_equity': str(own.day),
            'week_start_equity': str(own.week)}, event_time_ms=now_ms,
            received_time_ms=now_ms, correlation_id=context.account_alias)

    def _fold(self, fact):
        p, alias, now = fact.payload, fact.origin_alias, fact.event_time_ms
        if fact.kind == 'RISK_DECISION':
            snap = p['inputs']['snapshot']
            if _physical_baseline_unavailable(snap):
                # The original source reader has independently bound native
                # equity. Retain that natural observation, not a displayed
                # aggregate whose original-basis append/readback failed.
                self.origins[alias] = self._observed(alias, _money(snap['equity']), now, fact.event_ref)
                return
            if _funding_baseline_held(snap):
                return
            ref = snap.get('native_risk_basis_ref')
            if ref is not None:
                basis = self._basis[ref]
                if (basis.origin_alias != alias
                        or basis.payload['native_account_context'] != snap['native_account_context']
                        or self.origins[alias].event_ref != ref):
                    raise ValueError('snapshot does not bind its current original basis')
                expected = self.projection(now)
                if any(_money(snap[k]) != v for k, v in (
                        ('peak_equity', expected.peak), ('day_start_equity', expected.day),
                        ('week_start_equity', expected.week))):
                    raise ValueError('snapshot aggregate differs from original projection')
                return  # Never attribute this aggregate to its displaying alias.
            # Legacy producer snapshots were per alias, before shared projection.
            old = self.origins.get(alias)
            peak, day, week = (_money(snap[k]) for k in
                ('peak_equity', 'day_start_equity', 'week_start_equity'))
            self.origins[alias] = OriginBaseline(max(old.peak, peak) if old else peak,
                old.day if old and old.day_id == now // DAY_MS else day,
                old.week if old and old.week_id == now // WEEK_MS else week,
                now // DAY_MS, now // WEEK_MS, fact.event_ref)
        elif fact.kind == 'SESSION' and p.get('event') == BASIS_EVENT:
            from vati.risk.contracts import NativeAccountRiskContext
            context = NativeAccountRiskContext(**p['native_account_context'])
            equity = inspect_context(context)['equity']
            old = self.origins.get(alias)
            if (type(p['schema']) is not int or p['schema'] != 1
                    or p['previous_origin_ref'] != (old.event_ref if old else None)):
                raise ValueError('stale or unsupported original basis')
            expected = self._observed(alias, equity, now, fact.event_ref)
            if any(_money(p[k]) != v for k, v in (
                    ('peak_equity', expected.peak), ('day_start_equity', expected.day),
                    ('week_start_equity', expected.week))):
                raise ValueError('basis cannot seed itself from an aggregate')
            self.origins[alias] = expected
            self._basis[fact.event_ref] = fact
        elif fact.kind == 'SESSION' and p.get('event') == 'DRAWDOWN_RESUMED':
            equity = _money(p['new_peak_equity'])
            old = self.origins.get(alias)
            if old:
                self.origins[alias] = replace(old, peak=equity, event_ref=fact.event_ref)
            else:
                self.origins[alias] = self._observed(alias, equity, now, fact.event_ref)
