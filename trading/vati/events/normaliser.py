"""Event release normaliser (TRD-REV51-112, G7b).

The calendar recorder (090) answers "what did each source say". This turns an
agreed record into the one shape the surprise engine can score: an actual, a
forecast, a previous, a unit, and — the part that is easy to get wrong — which
direction counts as *stronger*.

That last field is the reason this module exists as something other than a
rename. "Higher is better" is true of payrolls and false of unemployment
claims, and a pipeline that assumes one convention silently inverts the sign
of every surprise in the other. It is declared per event class (115), never
inferred from the name.

Normalisation is refused, not approximated, in three cases: a release the
recorder has not VERIFIED, a release with no forecast to be surprising
against, and a release whose class is unregistered. Each returns a
NormalisedRelease marked unusable with the reason attached, rather than None,
so the episode record shows that a release happened and could not be scored —
which is a different fact from no release at all (INV-EVID-001).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.calendar.recorder import ReleaseRecord, ReleaseStatus
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.events.registry import EventClass, EventRegistry

PRODUCER = "vati-event-normaliser"
NORMALISER_VERSION = "event-normaliser/5.1.0"


class DirectionConvention(str, Enum):
    """Which way is 'stronger' for this release."""

    HIGHER_IS_STRONGER = "HIGHER_IS_STRONGER"
    LOWER_IS_STRONGER = "LOWER_IS_STRONGER"


class Unusable(str, Enum):
    NOT_VERIFIED = "NOT_VERIFIED"
    NO_FORECAST = "NO_FORECAST"
    UNREGISTERED_CLASS = "UNREGISTERED_CLASS"
    NO_SURPRISE_SCALE = "NO_SURPRISE_SCALE"


@dataclass(frozen=True)
class NormalisedRelease:
    event_key: str
    name: str
    tier: int
    currencies: tuple[str, ...]
    released_ms: int
    actual: Optional[Decimal]
    forecast: Optional[Decimal]
    previous: Optional[Decimal]
    convention: DirectionConvention
    surprise_scale: Optional[Decimal]
    status: ReleaseStatus
    unusable_reason: Optional[Unusable] = None
    normaliser_version: str = NORMALISER_VERSION

    @property
    def usable(self) -> bool:
        return self.unusable_reason is None

    @property
    def deviation(self) -> Optional[Decimal]:
        """Actual minus forecast, signed so positive always means stronger."""
        if self.actual is None or self.forecast is None:
            return None
        raw = self.actual - self.forecast
        return raw if self.convention is DirectionConvention.HIGHER_IS_STRONGER else -raw

    def body(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key, "name": self.name, "tier": self.tier,
            "currencies": list(self.currencies), "released_ms": self.released_ms,
            "actual": None if self.actual is None else str(self.actual),
            "forecast": None if self.forecast is None else str(self.forecast),
            "previous": None if self.previous is None else str(self.previous),
            "convention": self.convention.value,
            "surprise_scale": None if self.surprise_scale is None else str(self.surprise_scale),
            "status": self.status.value,
            "usable": self.usable,
            "unusable_reason": None if self.unusable_reason is None else self.unusable_reason.value,
            "deviation": None if self.deviation is None else str(self.deviation),
            "normaliser_version": self.normaliser_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class ReleaseNormaliser:
    """Turns calendar records into scoreable releases, or says why not."""

    def __init__(self, registry: EventRegistry, *, ledger=None,
                 producer: str = PRODUCER) -> None:
        self.registry = registry
        self._ledger = ledger
        self._producer = producer

    def normalise(self, record: ReleaseRecord, *, now_ms: Optional[int] = None
                  ) -> NormalisedRelease:
        sched = record.scheduled
        cls: Optional[EventClass] = self.registry.event_class(sched.name)
        convention = (DirectionConvention.HIGHER_IS_STRONGER
                      if cls is None or cls.higher_is_stronger
                      else DirectionConvention.LOWER_IS_STRONGER)
        scale = (Decimal(cls.surprise_scale)
                 if cls is not None and cls.surprise_scale is not None else None)

        reason: Optional[Unusable] = None
        if cls is None:
            reason = Unusable.UNREGISTERED_CLASS
        elif record.status is not ReleaseStatus.VERIFIED:
            reason = Unusable.NOT_VERIFIED
        elif sched.forecast is None:
            reason = Unusable.NO_FORECAST
        elif scale is None or scale <= 0:
            reason = Unusable.NO_SURPRISE_SCALE

        out = NormalisedRelease(
            event_key=sched.event_key,
            name=sched.name,
            tier=cls.tier if cls is not None else sched.tier,
            currencies=tuple(sched.currencies),
            released_ms=record.first_observed_ms or sched.scheduled_ms,
            actual=record.agreed_actual,
            forecast=sched.forecast,
            previous=sched.previous,
            convention=convention,
            surprise_scale=scale,
            status=record.status,
            unusable_reason=reason,
        )
        if self._ledger is not None:
            t = now_ms if now_ms is not None else out.released_ms
            self._ledger.append(make_event(
                EventKind.EVENT_RELEASE, self._producer, out.body(),
                event_time_ms=out.released_ms, received_time_ms=t,
                correlation_id=out.event_key))
        return out
