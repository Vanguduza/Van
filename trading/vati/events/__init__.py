"""Macro event pipeline (TRD-REV51-112..115).

The existing EventMatrix answers "is this currency pair inside a blackout".
This package answers the questions after that one: what did the release
actually say, how surprising was it, what did the market do about it, and
which instruments — not just currency pairs — the release touches at all.
"""

from vati.events.episodes import EpisodeProducer, EpisodeState, MacroEventEpisode
from vati.events.normaliser import (
    DirectionConvention,
    NormalisedRelease,
    ReleaseNormaliser,
)
from vati.events.reaction import (
    MagnitudeClass,
    ReactionEngine,
    Surprise,
    SurpriseDirection,
)
from vati.events.registry import (
    AssetClass,
    EventClass,
    EventRegistry,
    InstrumentExposure,
)

__all__ = [
    "AssetClass",
    "DirectionConvention",
    "EpisodeProducer",
    "EpisodeState",
    "EventClass",
    "EventRegistry",
    "InstrumentExposure",
    "MacroEventEpisode",
    "MagnitudeClass",
    "NormalisedRelease",
    "ReactionEngine",
    "ReleaseNormaliser",
    "Surprise",
    "SurpriseDirection",
]
