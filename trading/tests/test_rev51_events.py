"""TRD-REV51-112 normaliser, 113 surprise/reaction, 114 episodes, 115 registry."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.calendar import CalendarRecorder, ReleaseObservation, scheduled_from_row
from vati.calendar.recorder import ReleaseStatus
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.events.episodes import EpisodeProducer, EpisodeState
from vati.events.normaliser import DirectionConvention, ReleaseNormaliser, Unusable
from vati.events.reaction import (
    DEFAULT_HORIZONS_MS,
    MagnitudeClass,
    ReactionEngine,
    SurpriseDirection,
)
from vati.events.registry import (
    DEFAULT_EVENT_CLASSES,
    AssetClass,
    EventClass,
    EventRegistry,
    InstrumentExposure,
    RegistryError,
    registry_from_config,
)
from vati.intelligence.events import EventMatrix, EventWindowState

D = Decimal
RELEASE_MS = 1_700_000_000_000


def _registry(**kw) -> EventRegistry:
    return EventRegistry(instruments=[
        InstrumentExposure("EURUSD", "mt5", AssetClass.FX, frozenset({"EUR", "USD"})),
        InstrumentExposure("XAUUSD", "mt5", AssetClass.METAL, frozenset({"XAU", "USD"})),
        InstrumentExposure("GBPJPY", "mt5", AssetClass.FX, frozenset({"GBP", "JPY"})),
        InstrumentExposure("R_100", "deriv", AssetClass.SYNTHETIC),
        InstrumentExposure("DELTA.ZW", "zse", AssetClass.EQUITY, frozenset({"ZWL"})),
    ], **kw)


def _recorded(*, actual="100000", forecast="160000", sources=2, name="NFP"):
    rec = CalendarRecorder()
    sched = scheduled_from_row({"name": name, "release": str(RELEASE_MS),
                                "currencies": "USD", "forecast": forecast})
    rec.schedule(sched)
    for i, src in enumerate(("vendorA", "vendorB", "vendorC")[:sources]):
        rec.observe(ReleaseObservation(sched.event_key, src, D(actual),
                                       RELEASE_MS + 1_000 + i, RELEASE_MS))
    return rec.record(sched.event_key), sched


# ---------------------------------------------------------------- 115 registry
def test_a_metal_is_affected_by_a_dollar_event_even_without_a_matching_leg():
    """The FX-only rule failed silently for everything that is not a pair."""
    assert _registry().affects("NFP", "XAUUSD")


def test_an_unrelated_pair_is_not_affected():
    assert not _registry().affects("NFP", "GBPJPY")


def test_a_synthetic_instrument_has_no_macro_exposure():
    assert not _registry().affects("FOMC_RATE_DECISION", "R_100")


def test_an_undeclared_instrument_is_blacked_out_by_every_tier_one_event():
    """A missing declaration should show up as excess caution, never as
    silent exposure."""
    assert _registry().affects("NFP", "SOMETHING_NEW")


def test_undeclared_instruments_are_surfaced_for_the_operator():
    assert _registry().undeclared(["EURUSD", "SOMETHING_NEW"]) == ["SOMETHING_NEW"]


def test_an_unknown_event_affects_nothing():
    assert not _registry().affects("NOT_AN_EVENT", "EURUSD")


def test_an_event_class_that_affects_nothing_is_refused():
    with pytest.raises(RegistryError):
        EventClass("NOWHERE", 1, frozenset(), frozenset())


def test_a_zero_tier_is_refused():
    with pytest.raises(RegistryError):
        EventClass("X", 0, frozenset({"USD"}))


def test_affected_symbols_lists_the_universe_that_matters():
    got = _registry().affected_symbols("FOMC_RATE_DECISION",
                                       ["EURUSD", "XAUUSD", "GBPJPY", "R_100"])
    assert got == ["EURUSD", "XAUUSD"]


def test_window_lengths_come_from_the_class_and_feed_the_existing_matrix():
    """One source of truth: the matrix still decides blackout state."""
    reg = _registry()
    ev = reg.tier1_event(event_id="e1", name="FOMC_RATE_DECISION",
                         release_ms=RELEASE_MS, verified_sources=2)
    assert ev.blackout_before_ms == 15 * 60_000
    m = EventMatrix()
    m.add(ev)
    state, _ = m.state_at(RELEASE_MS - 60_000, "EUR", "USD")
    assert state is EventWindowState.PRE_BLACKOUT


def test_building_an_event_for_an_unregistered_class_is_refused():
    with pytest.raises(RegistryError):
        _registry().tier1_event(event_id="e", name="MADE_UP", release_ms=0)


def test_the_registry_loads_from_configuration():
    reg = registry_from_config({
        "event_classes": [{"name": "custom", "tier": 1, "currencies": ["ZAR"],
                           "asset_classes": ["EQUITY"], "surprise_scale": "1.5"}],
        "instruments": [{"symbol": "SOL.JO", "venue": "jse", "asset_class": "EQUITY",
                         "currencies": ["ZAR"]}],
    })
    assert reg.affects("CUSTOM", "SOL.JO")
    assert reg.event_class("CUSTOM").surprise_scale == "1.5"


def test_the_shipped_classes_all_name_something_they_move():
    for c in DEFAULT_EVENT_CLASSES:
        assert c.currencies or c.asset_classes


def test_listing_fx_as_an_affected_asset_class_is_refused():
    """It would make a US payrolls print black out GBPJPY and every other
    unrelated cross — the whole book, quietly."""
    with pytest.raises(RegistryError) as e:
        EventClass("X", 1, frozenset({"USD"}), frozenset({AssetClass.FX}))
    assert "expressed by currency legs" in str(e.value)


def test_no_shipped_class_blacks_out_the_whole_fx_book():
    assert all(AssetClass.FX not in c.asset_classes for c in DEFAULT_EVENT_CLASSES)


def test_the_registry_digest_is_stable():
    assert _registry().digest == _registry().digest


# -------------------------------------------------------------- 112 normaliser
def test_a_verified_release_normalises_with_a_signed_deviation():
    record, _ = _recorded()
    n = ReleaseNormaliser(_registry()).normalise(record)
    assert n.usable and n.deviation == D("-60000")
    assert n.convention is DirectionConvention.HIGHER_IS_STRONGER


def test_a_lower_is_stronger_release_inverts_the_sign():
    """Assuming one convention silently inverts every surprise in the other."""
    reg = EventRegistry(classes=[EventClass("UNEMPLOYMENT_CLAIMS", 1, frozenset({"USD"}),
                                            surprise_scale="15000",
                                            higher_is_stronger=False)])
    record, _ = _recorded(name="UNEMPLOYMENT_CLAIMS", actual="200000", forecast="220000")
    n = ReleaseNormaliser(reg).normalise(record)
    assert n.convention is DirectionConvention.LOWER_IS_STRONGER
    assert n.deviation == D("20000")           # a lower print is stronger


def test_an_unverified_release_is_unusable_but_still_recorded():
    """A release that happened and could not be scored is a different fact
    from no release."""
    record, _ = _recorded(sources=1)
    n = ReleaseNormaliser(_registry()).normalise(record)
    assert not n.usable and n.unusable_reason is Unusable.NOT_VERIFIED
    assert n.status is ReleaseStatus.PROVISIONAL


def test_a_release_without_a_forecast_cannot_be_surprising():
    rec = CalendarRecorder()
    sched = scheduled_from_row({"name": "NFP", "release": str(RELEASE_MS), "currencies": "USD"})
    rec.schedule(sched)
    for src in ("a", "b"):
        rec.observe(ReleaseObservation(sched.event_key, src, D("1"), RELEASE_MS, RELEASE_MS))
    n = ReleaseNormaliser(_registry()).normalise(rec.record(sched.event_key))
    assert n.unusable_reason is Unusable.NO_FORECAST


def test_an_unregistered_class_is_named_rather_than_guessed():
    record, _ = _recorded(name="PPI")
    n = ReleaseNormaliser(EventRegistry(classes=[])).normalise(record)
    assert n.unusable_reason is Unusable.UNREGISTERED_CLASS


def test_releases_are_ledgered_against_their_event_key():
    led = Ledger(":memory:")
    record, sched = _recorded()
    ReleaseNormaliser(_registry(), ledger=led).normalise(record)
    assert led.count(EventKind.EVENT_RELEASE) == 1
    assert [e.correlation_id for e in led.iter(EventKind.EVENT_RELEASE)] == [sched.event_key]


# ---------------------------------------------------------------- 113 surprise
def _normalised(**kw):
    record, sched = _recorded(**kw)
    return ReleaseNormaliser(_registry()).normalise(record), sched


def test_a_weaker_print_scores_a_negative_z():
    n, _ = _normalised()
    s = ReactionEngine().score(n)
    assert s.scored and s.direction is SurpriseDirection.WEAKER and s.z < 0


def test_a_large_miss_is_classified_large():
    n, _ = _normalised(actual="400000")
    s = ReactionEngine().score(n)
    assert s.magnitude is MagnitudeClass.LARGE and s.direction is SurpriseDirection.STRONGER


def test_an_inline_print_has_no_direction():
    n, _ = _normalised(actual="160000")
    s = ReactionEngine().score(n)
    assert s.z == 0 and s.direction is SurpriseDirection.INLINE


def test_an_unscoreable_release_produces_an_unscored_surprise():
    n, _ = _normalised(sources=1)
    s = ReactionEngine().score(n)
    assert not s.scored and s.magnitude is MagnitudeClass.NONE


def test_a_missing_scale_is_refused_rather_than_defaulted():
    """A default scale is a guess wearing a z-score."""
    reg = EventRegistry(classes=[EventClass("NFP", 1, frozenset({"USD"}))])
    record, _ = _recorded()
    n = ReleaseNormaliser(reg).normalise(record)
    assert n.unusable_reason is Unusable.NO_SURPRISE_SCALE
    assert not ReactionEngine().score(n).scored


# ---------------------------------------------------------------- 113 reaction
def _tracked(engine, sched, *, marks=((60_000, "1.095"),)):
    t = engine.track(event_key=sched.event_key, symbol="EURUSD", release_ms=RELEASE_MS,
                     baseline_mark=D("1.10"), typical_range=D("0.01"))
    for horizon, mark in marks:
        engine.record_mark(event_key=sched.event_key, symbol="EURUSD",
                           horizon_ms=horizon, mark=D(mark),
                           observed_ms=RELEASE_MS + horizon)
    return t


def test_a_reaction_is_measured_in_the_instrument_s_own_range():
    """A 0.3% move in a currency pair and in a volatility index are not the
    same event."""
    eng = ReactionEngine()
    _, sched = _normalised()
    t = _tracked(eng, sched)
    assert t.reaction(60_000).move_in_ranges == D("-0.5")


def test_an_undeclared_horizon_is_refused():
    eng = ReactionEngine()
    _, sched = _normalised()
    _tracked(eng, sched)
    with pytest.raises(KeyError):
        eng.record_mark(event_key=sched.event_key, symbol="EURUSD", horizon_ms=7,
                        mark=D("1.1"), observed_ms=RELEASE_MS)


def test_a_horizon_whose_mark_never_arrives_expires_as_missing():
    """A reaction measured against a stale mark is worse than none: it looks
    like data."""
    eng = ReactionEngine()
    _, sched = _normalised()
    t = _tracked(eng, sched)
    late = t.reaction(max(DEFAULT_HORIZONS_MS), now_ms=RELEASE_MS + 10 ** 9)
    assert late.missing and late.mark is None


def test_a_track_is_complete_once_every_horizon_has_resolved():
    eng = ReactionEngine()
    _, sched = _normalised()
    t = _tracked(eng, sched)
    assert not t.complete(now_ms=RELEASE_MS + 60_000)
    assert t.complete(now_ms=RELEASE_MS + 10 ** 9)


def test_an_engine_with_no_horizons_measures_nothing_and_says_so():
    with pytest.raises(ValueError):
        ReactionEngine(horizons_ms=())


# ---------------------------------------------------------------- 114 episodes
def _episode(*, marks=((60_000, "1.095"),), now_ms=RELEASE_MS + 10 ** 9, **kw):
    n, sched = _normalised(**kw)
    eng = ReactionEngine()
    s = eng.score(n)
    t = _tracked(eng, sched, marks=marks) if marks is not None else None
    p = EpisodeProducer()
    p.open(n, s)
    return p, p.close_due(tracks=[t] if t else [], now_ms=now_ms)


def test_an_episode_closes_on_the_schedule_with_whatever_it_has():
    """Waiting for a complete set silently drops exactly the episodes where
    the venue went quiet."""
    _, eps = _episode()
    assert len(eps) == 1
    ep = eps[0]
    assert ep.state is EpisodeState.CLOSED
    assert ep.observed_horizons == 1 and ep.missing_horizons == 3


def test_an_unscoreable_release_still_produces_an_episode():
    _, eps = _episode(sources=1)
    assert eps[0].state is EpisodeState.UNSCORED


def test_an_episode_with_no_observed_horizon_is_empty_not_absent():
    _, eps = _episode(marks=())
    assert eps[0].state is EpisodeState.EMPTY


def test_the_move_direction_is_reported_beside_the_surprise_never_reconciled():
    """Which way a stronger print pushes an instrument depends on which side
    of the quote the currency sits; guessing would be wrong for every
    inverse-quoted pair."""
    _, eps = _episode()
    ep = eps[0]
    assert ep.move_direction == "DOWN"
    assert ep.surprise.direction is SurpriseDirection.WEAKER
    assert "followed_through" not in ep.body()


def test_an_episode_not_yet_due_does_not_close():
    p, eps = _episode(now_ms=RELEASE_MS + 1_000)
    assert eps == []


def test_a_closed_episode_converts_to_a_retrievable_analogue():
    p, _ = _episode()
    analogues = p.analogue_episodes()
    assert len(analogues) == 1
    assert analogues[0].features.event_proximity == D("1")
    assert analogues[0].outcome_r is not None


def test_an_empty_episode_converts_to_nothing_rather_than_to_defaults():
    """Otherwise it would be retrievable as if it were evidence."""
    p, _ = _episode(marks=())
    assert p.analogue_episodes() == []


def test_episodes_are_ledgered_against_their_event_key():
    led = Ledger(":memory:")
    n, sched = _normalised()
    eng = ReactionEngine()
    s = eng.score(n)
    t = _tracked(eng, sched)
    p = EpisodeProducer(ledger=led)
    p.open(n, s)
    p.close_due(tracks=[t], now_ms=RELEASE_MS + 10 ** 9)
    assert led.count(EventKind.MACRO_EVENT_EPISODE) == 1
    assert [e.correlation_id for e in led.iter(EventKind.MACRO_EVENT_EPISODE)] == [sched.event_key]


def test_an_episode_digest_is_stable():
    _, a = _episode()
    _, b = _episode()
    assert a[0].digest == b[0].digest
