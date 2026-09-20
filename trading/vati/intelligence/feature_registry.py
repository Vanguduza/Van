"""Venue-aware feature registry (§7, TRD-ENH-012).

A feature computed where its inputs do not mean what its name implies is worse
than a missing feature, because it looks like evidence. `Bar.volume` is the
example the repository already lives with: on FX spot it is a broker's tick or
quote activity, not consolidated traded volume, because spot FX is decentralised
OTC and no such quantity exists. On ZSE it *is* real traded volume.

So every feature declares where it applies and, in `source_semantics`, what its
inputs actually are. That field is the one that stops `volume` silently meaning
traded volume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from vati.validation.certificates import (
    FEATURE_PRODUCTION_ADMITTED,
    FeatureValidationCertificate,
    classify_feature_certificate,
)

#: Venue classes the registry distinguishes. FX_SPOT and SYNTHETIC have no
#: consolidated volume; ZSE_EQUITY and VFEX do.
VENUE_CLASSES = ("FX_SPOT", "CFD", "SYNTHETIC", "ZSE_EQUITY", "VFEX")

FAMILIES = (
    "TREND", "MOMENTUM", "VOLATILITY", "STRUCTURE",
    "LIQUIDITY", "VOLUME_ACTIVITY", "EVENT", "EXECUTION", "CROSS_ASSET",
)

#: Honest labels for what a "volume" input is on each venue class. A feature
#: whose semantics are BROKER_* may not be presented as traded volume.
SOURCE_SEMANTICS = (
    "PRICE_OHLC",
    "BROKER_TICK_ACTIVITY",
    "BROKER_QUOTE_ACTIVITY",
    "BROKER_REPORTED_VOLUME_PROXY",
    "EXCHANGE_TRADED_VOLUME",
    "FUNDAMENTAL_SNAPSHOT",
    "VENUE_SPREAD",
    "DERIVED",
)


class FeatureRegistryError(ValueError):
    """A definition that would let a feature lie about its inputs."""


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    version: str
    family: str
    required_inputs: tuple[str, ...]
    venue_classes: frozenset[str]
    allowed_timeframes: frozenset[str]
    minimum_history: int
    source_semantics: str
    implementation_ref: str
    #: Anything beyond the founding set must carry a FeatureValidationCertificate.
    certificate_required: bool = True

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise FeatureRegistryError(f"{self.feature_id}: unknown family {self.family}")
        if self.source_semantics not in SOURCE_SEMANTICS:
            raise FeatureRegistryError(f"{self.feature_id}: unknown source_semantics {self.source_semantics}")
        bad = sorted(self.venue_classes - set(VENUE_CLASSES))
        if bad:
            raise FeatureRegistryError(f"{self.feature_id}: unknown venue class(es) {bad}")
        # The rule this registry exists for.
        if self.source_semantics == "EXCHANGE_TRADED_VOLUME" and (
            self.venue_classes & {"FX_SPOT", "SYNTHETIC", "CFD"}
        ):
            raise FeatureRegistryError(
                f"{self.feature_id}: EXCHANGE_TRADED_VOLUME claimed for a venue class with no "
                "consolidated traded volume; use a BROKER_* semantic instead"
            )

    def applies_to(self, venue_class: str) -> bool:
        return venue_class in self.venue_classes

    def as_dict(self) -> dict:
        return {
            "feature_id": self.feature_id, "version": self.version, "family": self.family,
            "required_inputs": list(self.required_inputs),
            "venue_classes": sorted(self.venue_classes),
            "allowed_timeframes": sorted(self.allowed_timeframes),
            "minimum_history": self.minimum_history,
            "source_semantics": self.source_semantics,
            "implementation_ref": self.implementation_ref,
            "certificate_required": self.certificate_required,
        }


class FeatureRegistry:
    def __init__(self, definitions: Mapping[str, FeatureDefinition] | None = None) -> None:
        self._d: dict[str, FeatureDefinition] = dict(definitions or {})
        self._admissions: dict[str, str] = {}

    def register(self, d: FeatureDefinition) -> None:
        prior = self._d.get(d.feature_id)
        if prior is not None and prior.version == d.version and prior != d:
            raise FeatureRegistryError(
                f"{d.feature_id}: redefined at the same version {d.version}; bump the version"
            )
        self._d[d.feature_id] = d

    def admit(self, d: FeatureDefinition, certificate: FeatureValidationCertificate) -> str:
        """Admit a certificate-required feature into production dependencies.

        Definition registration alone is not admission. The certificate is
        reclassified here and its identity is retained so FeatureContractValidator
        can distinguish a known research feature from a production-admitted one.
        """
        if certificate.feature_id != d.feature_id or certificate.feature_version != d.version:
            raise FeatureRegistryError(
                f"{d.feature_id}: certificate identity/version does not match definition")
        status, reasons = classify_feature_certificate(certificate)
        if status != FEATURE_PRODUCTION_ADMITTED:
            raise FeatureRegistryError(
                f"{d.feature_id}: feature certificate not production-admitted: "
                + ",".join(reasons or (status,)))
        self.register(d)
        self._admissions[d.feature_id] = certificate.certificate_hash
        return certificate.certificate_hash

    def is_production_admitted(self, feature_id: str) -> bool:
        d = self._d.get(feature_id)
        if d is None:
            return False
        return (not d.certificate_required) or bool(self._admissions.get(feature_id))

    def admission_hash(self, feature_id: str) -> Optional[str]:
        return self._admissions.get(feature_id)

    def get(self, feature_id: str) -> Optional[FeatureDefinition]:
        return self._d.get(feature_id)

    def require(self, feature_id: str) -> FeatureDefinition:
        d = self._d.get(feature_id)
        if d is None:
            raise FeatureRegistryError(f"unknown feature {feature_id}")
        return d

    def for_venue(self, venue_class: str) -> tuple[FeatureDefinition, ...]:
        return tuple(sorted((d for d in self._d.values() if d.applies_to(venue_class)),
                            key=lambda d: d.feature_id))

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._d))

    def __len__(self) -> int:
        return len(self._d)


_ALL_TF = frozenset({"M1", "M5", "M15", "H1", "H4", "D1"})
_PRICE_VENUES = frozenset(VENUE_CLASSES)


def _price(feature_id: str, family: str, inputs: tuple[str, ...], minimum: int, ref: str) -> FeatureDefinition:
    """The founding set: already in production, so no certificate is required."""
    return FeatureDefinition(
        feature_id=feature_id, version="1.0.0", family=family, required_inputs=inputs,
        venue_classes=_PRICE_VENUES, allowed_timeframes=_ALL_TF, minimum_history=minimum,
        source_semantics="PRICE_OHLC", implementation_ref=ref, certificate_required=False,
    )


def default_registry() -> FeatureRegistry:
    """The features `compute_features` already produces, declared honestly."""
    r = FeatureRegistry()
    for fid, fam, inputs, minimum, ref in (
        ("close", "STRUCTURE", ("ohlc",), 1, "vati.intelligence.features"),
        ("ema_fast", "TREND", ("ohlc",), 20, "vati.intelligence.features.ema"),
        ("ema_slow", "TREND", ("ohlc",), 50, "vati.intelligence.features.ema"),
        ("atr", "VOLATILITY", ("ohlc",), 15, "vati.intelligence.features.atr"),
        ("rsi", "MOMENTUM", ("ohlc",), 15, "vati.intelligence.features.rsi"),
        ("realised_vol", "VOLATILITY", ("ohlc",), 21, "vati.intelligence.features.realised_vol"),
        ("vol_percentile", "VOLATILITY", ("ohlc",), 21, "vati.intelligence.features.percentile_rank"),
        ("trend_slope", "TREND", ("ohlc",), 50, "vati.intelligence.features"),
        ("range_compression", "VOLATILITY", ("ohlc",), 15, "vati.intelligence.features"),
        ("swing_high", "STRUCTURE", ("ohlc",), 20, "vati.intelligence.features"),
        ("swing_low", "STRUCTURE", ("ohlc",), 20, "vati.intelligence.features"),
    ):
        r.register(_price(fid, fam, inputs, minimum, ref))

    r.register(FeatureDefinition(
        feature_id="spread_percentile", version="1.0.0", family="LIQUIDITY",
        required_inputs=("spread",), venue_classes=_PRICE_VENUES, allowed_timeframes=_ALL_TF,
        minimum_history=20, source_semantics="VENUE_SPREAD",
        implementation_ref="vati.intelligence.features.percentile_rank", certificate_required=False))

    # ZSE fundamentals and liquidity, which never lived in the price vector.
    zse = frozenset({"ZSE_EQUITY", "VFEX"})
    for fid, fam, sem in (
        ("value_score", "CROSS_ASSET", "FUNDAMENTAL_SNAPSHOT"),
        ("adv_20d", "LIQUIDITY", "EXCHANGE_TRADED_VOLUME"),
        ("median_spread_pct", "LIQUIDITY", "VENUE_SPREAD"),
        ("currency_regime", "CROSS_ASSET", "FUNDAMENTAL_SNAPSHOT"),
        ("trading_days_of_20", "LIQUIDITY", "EXCHANGE_TRADED_VOLUME"),
    ):
        r.register(FeatureDefinition(
            feature_id=fid, version="1.0.0", family=fam, required_inputs=("fundamentals",),
            venue_classes=zse, allowed_timeframes=frozenset({"D1"}), minimum_history=1,
            source_semantics=sem, implementation_ref="vati.strategies.base.ZseSnapshot",
            certificate_required=False))
    return r


def research_tranche() -> tuple[FeatureDefinition, ...]:
    """First research tranche (§7.3). Certificate-required, unlike the founding set.

    Note what is *not* here. MACD is absent because PPO is the same construction
    and the redundant-pair rule admits one; Keltner is absent because Donchian
    is the less colinear of the pair against `atr` and `range_compression`.
    Admitting the second member later requires it to beat the first, not the
    baseline containing neither.
    """
    price = frozenset(VENUE_CLASSES)
    intraday = frozenset({"M5", "M15", "H1", "H4", "D1"})
    return (
        FeatureDefinition("adx", "1.0.0", "TREND", ("ohlc",), price, intraday, 30,
                          "PRICE_OHLC", "vati.intelligence.features.adx"),
        FeatureDefinition("plus_di", "1.0.0", "TREND", ("ohlc",), price, intraday, 15,
                          "PRICE_OHLC", "vati.intelligence.features.dmi"),
        FeatureDefinition("minus_di", "1.0.0", "TREND", ("ohlc",), price, intraday, 15,
                          "PRICE_OHLC", "vati.intelligence.features.dmi"),
        FeatureDefinition("donchian_position", "1.0.0", "STRUCTURE", ("ohlc",), price, intraday, 20,
                          "PRICE_OHLC", "vati.intelligence.features.donchian"),
        FeatureDefinition("ppo", "1.0.0", "MOMENTUM", ("ohlc",), price, intraday, 26,
                          "PRICE_OHLC", "vati.intelligence.features.ppo"),
        FeatureDefinition("roc_5", "1.0.0", "MOMENTUM", ("ohlc",), price, intraday, 6,
                          "PRICE_OHLC", "vati.intelligence.features.roc"),
        FeatureDefinition("roc_20", "1.0.0", "MOMENTUM", ("ohlc",), price, intraday, 21,
                          "PRICE_OHLC", "vati.intelligence.features.roc"),
        FeatureDefinition("roc_60", "1.0.0", "MOMENTUM", ("ohlc",), price, intraday, 61,
                          "PRICE_OHLC", "vati.intelligence.features.roc"),
    )


#: Venue-gated volume (§7.4/7.5, TRD-ENH-019). Two families, deliberately
#: different: real traded volume exists on ZSE/VFEX and does not exist on FX.
def volume_tranche() -> tuple[FeatureDefinition, ...]:
    zse = frozenset({"ZSE_EQUITY", "VFEX"})
    fx = frozenset({"FX_SPOT", "CFD", "SYNTHETIC"})
    return (
        # ZSE: real exchange volume, so a money-flow family is meaningful.
        FeatureDefinition("obv", "1.0.0", "VOLUME_ACTIVITY", ("ohlc", "volume"), zse,
                          frozenset({"D1"}), 20, "EXCHANGE_TRADED_VOLUME",
                          "vati.intelligence.features"),
        FeatureDefinition("money_flow_index", "1.0.0", "VOLUME_ACTIVITY", ("ohlc", "volume"), zse,
                          frozenset({"D1"}), 15, "EXCHANGE_TRADED_VOLUME",
                          "vati.intelligence.features"),
        # FX: tick count is an activity proxy and says so. The registry refuses
        # any attempt to label it traded volume.
        FeatureDefinition("tick_activity_percentile", "1.0.0", "VOLUME_ACTIVITY", ("ticks",), fx,
                          frozenset({"M5", "M15", "H1", "H4", "D1"}), 20,
                          "BROKER_TICK_ACTIVITY", "vati.intelligence.features"),
    )


def venue_class_for(venue: str, symbol: str) -> str:
    """Map the repository's concrete venue/symbol vocabulary to one registry class."""
    v = str(venue).lower()
    s = str(symbol).upper()
    if v == "zse":
        return "ZSE_EQUITY"
    if v == "vfex":
        return "VFEX"
    if v == "deriv" and (s.startswith("R_") or "BOOM" in s or "CRASH" in s):
        return "SYNTHETIC"
    if s.startswith(("XAU", "XAG")):
        return "CFD"
    return "FX_SPOT"


__all__ = [
    "FAMILIES", "SOURCE_SEMANTICS", "VENUE_CLASSES",
    "FeatureDefinition", "FeatureRegistry", "FeatureRegistryError", "default_registry",
    "research_tranche", "volume_tranche", "venue_class_for",
]
