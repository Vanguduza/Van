"""Venue-generic event registry (TRD-REV51-115, G7b).

The existing EventMatrix decides whether a release touches an instrument by
asking `base in currencies or quote in currencies`. That works for FX and
quietly fails for everything else: gold has no currency leg that matches
"FOMC", an equity index has no base currency in the FX sense, and a Zimbabwe
Stock Exchange listing has neither. The failure is silent — the instrument
simply never appears to be in a blackout — which is the worst shape a
protection gap can take.

So exposure is declared rather than inferred. An instrument says what it is:
its currency legs, its asset class, its venue. An event class says what it
moves: currencies, asset classes, and how long its windows run. An instrument
is affected if either dimension matches, and an instrument nobody has declared
is treated as affected by every tier-1 event rather than by none — the
fail-closed reading, and the one that makes a missing declaration show up as
excess caution instead of as silent exposure (INV-FAIL-001).

Loading is from configuration at service startup or explicit reload, never
lazily mid-session: a registry that can change under a running decision cycle
would make two instruments in the same pass answer to different rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from vati.core.canonical import canonical_hash
from vati.intelligence.events import Tier1Event

REGISTRY_VERSION = "event-registry/5.1.0"


class AssetClass(str, Enum):
    FX = "FX"
    METAL = "METAL"
    ENERGY = "ENERGY"
    INDEX = "INDEX"
    EQUITY = "EQUITY"
    CRYPTO = "CRYPTO"
    RATE = "RATE"
    SYNTHETIC = "SYNTHETIC"      # venue-constructed; no external macro exposure


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class InstrumentExposure:
    """What an instrument is, for the purpose of deciding what moves it."""

    symbol: str
    venue: str
    asset_class: AssetClass
    currencies: frozenset[str] = frozenset()

    def body(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "venue": self.venue,
                "asset_class": self.asset_class.value,
                "currencies": sorted(self.currencies)}


@dataclass(frozen=True)
class EventClass:
    """What a kind of release moves, and for how long."""

    name: str
    tier: int
    currencies: frozenset[str]
    asset_classes: frozenset[AssetClass] = frozenset()
    blackout_before_ms: int = 5 * 60_000
    blackout_after_ms: int = 15 * 60_000
    quiet_until_ms: int = 45 * 60_000
    drift_until_ms: int = 4 * 3_600_000
    #: Standard deviation of past surprises, in the release's own units. The
    #: surprise engine needs it and will not invent one.
    surprise_scale: Optional[str] = None
    higher_is_stronger: bool = True

    def __post_init__(self) -> None:
        if self.tier < 1:
            raise RegistryError(f"{self.name} has tier {self.tier}")
        if not self.currencies and not self.asset_classes:
            raise RegistryError(
                f"{self.name} names neither a currency nor an asset class; it would "
                "affect nothing, which is never what a tier-1 event does")
        if AssetClass.FX in self.asset_classes:
            # An FX instrument's exposure is exactly its currency legs, so
            # listing FX here would make a US payrolls print black out GBPJPY
            # and every other unrelated cross — the whole book, quietly.
            # asset_classes exists for instruments whose legs cannot express
            # their exposure: metals, indices, rates, crypto.
            raise RegistryError(
                f"{self.name} lists FX as an affected asset class; FX exposure is "
                "expressed by currency legs, and listing it here blacks out every "
                "unrelated cross")

    def affects(self, inst: InstrumentExposure) -> bool:
        """Currency legs first; asset class only for exposure legs cannot express."""
        if inst.asset_class is AssetClass.SYNTHETIC:
            # A venue-constructed instrument has no external macro exposure by
            # definition. If that stops being true it is a new asset class.
            return False
        if self.asset_classes and inst.asset_class in self.asset_classes:
            return True
        return bool(self.currencies & inst.currencies)

    def body(self) -> dict[str, Any]:
        return {
            "name": self.name, "tier": self.tier,
            "currencies": sorted(self.currencies),
            "asset_classes": sorted(a.value for a in self.asset_classes),
            "blackout_before_ms": self.blackout_before_ms,
            "blackout_after_ms": self.blackout_after_ms,
            "quiet_until_ms": self.quiet_until_ms,
            "drift_until_ms": self.drift_until_ms,
            "surprise_scale": self.surprise_scale,
            "higher_is_stronger": self.higher_is_stronger,
        }


#: The classes Rev 5.1 ships with. Windows are the existing Tier1Event
#: defaults unless a release plainly deserves longer: a rate decision moves
#: the whole complex for hours, a jobs print for one.
DEFAULT_EVENT_CLASSES: tuple[EventClass, ...] = (
    EventClass("NFP", 1, frozenset({"USD"}),
               frozenset({AssetClass.METAL, AssetClass.INDEX}),
               surprise_scale="75000"),
    EventClass("CPI", 1, frozenset({"USD"}),
               frozenset({AssetClass.METAL, AssetClass.INDEX, AssetClass.RATE}),
               surprise_scale="0.2"),
    EventClass("FOMC_RATE_DECISION", 1, frozenset({"USD"}),
               frozenset({AssetClass.METAL, AssetClass.INDEX,
                          AssetClass.RATE, AssetClass.CRYPTO}),
               blackout_before_ms=15 * 60_000, blackout_after_ms=30 * 60_000,
               quiet_until_ms=90 * 60_000, drift_until_ms=8 * 3_600_000,
               surprise_scale="0.25"),
    EventClass("ECB_RATE_DECISION", 1, frozenset({"EUR"}),
               frozenset({AssetClass.RATE}),
               blackout_before_ms=15 * 60_000, blackout_after_ms=30 * 60_000,
               surprise_scale="0.25"),
    EventClass("BOE_RATE_DECISION", 1, frozenset({"GBP"}),
               frozenset({AssetClass.RATE}),
               blackout_before_ms=15 * 60_000, blackout_after_ms=30 * 60_000,
               surprise_scale="0.25"),
    EventClass("PCE", 1, frozenset({"USD"}),
               frozenset({AssetClass.METAL}), surprise_scale="0.2"),
    EventClass("RETAIL_SALES", 1, frozenset({"USD"}), surprise_scale="0.6"),
    EventClass("GDP_ADVANCE", 1, frozenset({"USD"}),
               frozenset({AssetClass.INDEX}), surprise_scale="0.5"),
)


class EventRegistry:
    """Event classes and instrument exposures, loaded at startup."""

    def __init__(self, *, classes: Optional[Iterable[EventClass]] = None,
                 instruments: Optional[Iterable[InstrumentExposure]] = None) -> None:
        self._classes: dict[str, EventClass] = {}
        self._instruments: dict[str, InstrumentExposure] = {}
        for c in (classes if classes is not None else DEFAULT_EVENT_CLASSES):
            self.register_class(c)
        for i in instruments or ():
            self.register_instrument(i)

    def register_class(self, cls: EventClass) -> EventClass:
        self._classes[cls.name.upper()] = cls
        return cls

    def register_instrument(self, inst: InstrumentExposure) -> InstrumentExposure:
        self._instruments[inst.symbol.upper()] = inst
        return inst

    def event_class(self, name: str) -> Optional[EventClass]:
        return self._classes.get(name.upper())

    def instrument(self, symbol: str) -> Optional[InstrumentExposure]:
        return self._instruments.get(symbol.upper())

    def affects(self, event_name: str, symbol: str) -> bool:
        """Whether a release touches an instrument.

        An undeclared instrument is affected by every tier-1 event. A missing
        declaration then shows up as excess caution rather than as silent
        exposure, which is the only acceptable direction for this to fail.
        """
        cls = self.event_class(event_name)
        if cls is None:
            return False
        inst = self.instrument(symbol)
        if inst is None:
            return cls.tier == 1
        return cls.affects(inst)

    def affected_symbols(self, event_name: str,
                         universe: Optional[Iterable[str]] = None) -> list[str]:
        symbols = list(universe) if universe is not None else sorted(self._instruments)
        return sorted(s for s in symbols if self.affects(event_name, s))

    def tier1_event(self, *, event_id: str, name: str, release_ms: int,
                    verified_sources: int = 1) -> Tier1Event:
        """Build the existing matrix's event from a registered class.

        Keeps one source of truth for window lengths: the matrix stays the
        component that decides blackout state, and this decides the numbers it
        decides with.
        """
        cls = self.event_class(name)
        if cls is None:
            raise RegistryError(f"{name} is not a registered event class")
        return Tier1Event(
            event_id=event_id, name=cls.name, release_ms=release_ms,
            currencies=frozenset(cls.currencies),
            blackout_before_ms=cls.blackout_before_ms,
            blackout_after_ms=cls.blackout_after_ms,
            quiet_until_ms=cls.quiet_until_ms,
            drift_until_ms=cls.drift_until_ms,
            verified_sources=verified_sources)

    # -------------------------------------------------------------- reporting
    def body(self) -> dict[str, Any]:
        return {
            "registry_version": REGISTRY_VERSION,
            "classes": [self._classes[k].body() for k in sorted(self._classes)],
            "instruments": [self._instruments[k].body() for k in sorted(self._instruments)],
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())

    def undeclared(self, universe: Iterable[str]) -> list[str]:
        """Symbols with no exposure declaration. Worth surfacing: each one is
        being blacked out by every tier-1 event."""
        return sorted(s for s in universe if self.instrument(s) is None)


def registry_from_config(config: Mapping[str, Any]) -> EventRegistry:
    """Build from a config mapping at startup or explicit reload."""
    classes = [
        EventClass(
            name=str(c["name"]).upper(), tier=int(c.get("tier", 1)),
            currencies=frozenset(str(x).upper() for x in c.get("currencies", ())),
            asset_classes=frozenset(AssetClass(str(x).upper())
                                    for x in c.get("asset_classes", ())),
            blackout_before_ms=int(c.get("blackout_before_ms", 5 * 60_000)),
            blackout_after_ms=int(c.get("blackout_after_ms", 15 * 60_000)),
            quiet_until_ms=int(c.get("quiet_until_ms", 45 * 60_000)),
            drift_until_ms=int(c.get("drift_until_ms", 4 * 3_600_000)),
            surprise_scale=(None if c.get("surprise_scale") is None
                            else str(c["surprise_scale"])),
            higher_is_stronger=bool(c.get("higher_is_stronger", True)),
        )
        for c in config.get("event_classes", ())
    ]
    instruments = [
        InstrumentExposure(
            symbol=str(i["symbol"]).upper(), venue=str(i.get("venue", "")),
            asset_class=AssetClass(str(i["asset_class"]).upper()),
            currencies=frozenset(str(x).upper() for x in i.get("currencies", ())),
        )
        for i in config.get("instruments", ())
    ]
    return EventRegistry(classes=classes or None, instruments=instruments)
