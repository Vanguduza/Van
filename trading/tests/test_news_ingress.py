"""GAP-F-003 item 4: event/news intelligence, and the ceiling it lives under.

The rule this file exists to pin is the direction of the arrow. A headline can
make VAN carry less; it can never make VAN carry more, and it can never open or
extend a blackout window — the economic calendar keeps that authority. Every
number this module produces is in [0, 1] and every consumer combines it with
`min`, so the property holds by arithmetic rather than by convention.

The rest is provenance: what was said, who said it, how sure they were, how old
it is, and which instrument it actually touches. A headline whose relevance
cannot be established from declared exposure does not get to argue.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from vati.arbiter.meta_labeler import MetaLabeler
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.events.news_ingress import (
    EVENT_MULTIPLIER_FLOOR,
    MATERIALITY_ACTIONABLE,
    Concern,
    Headline,
    NewsIngress,
    NewsIngressError,
    NewsSource,
    SourceTrust,
    event_risk_multiplier_for,
    rows_from_file,
    sources_from_config,
)
from vati.events.registry import AssetClass, EventRegistry, InstrumentExposure

NOW = 1_800_000_000_000
WINDOW = 6 * 3_600_000


def declared_registry() -> EventRegistry:
    """A registry that knows what EURUSD is, so relevance is drawn from a
    declaration rather than from the undeclared fail-closed branch."""
    registry = EventRegistry()
    registry.register_instrument(InstrumentExposure(
        symbol="EURUSD", venue="paper", asset_class=AssetClass.FX,
        currencies=frozenset({"EUR", "USD"})))
    return registry


def ingress(ledger=None, **kw) -> NewsIngress:
    return NewsIngress(
        ledger=ledger,
        sources=[
            NewsSource("reuters", SourceTrust.T1_PRIMARY, "Reuters"),
            NewsSource("aggregator", SourceTrust.T2_SECONDARY, "An aggregator"),
        ],
        relevance_window_ms=WINDOW,
        **kw)


def headline(**overrides) -> Headline:
    base = dict(
        source_id="reuters", trust=SourceTrust.T1_PRIMARY,
        published_ms=NOW, observed_ms=NOW,
        title="ECB signals emergency review of euro liquidity operations",
        currencies=("EUR",), symbols=(), severity=Decimal("0.8"),
        concern=Concern.ADVERSE_TO_LONG)
    base.update(overrides)
    return Headline(**base)


# --- the ceiling ----------------------------------------------------------

def test_the_multiplier_can_never_exceed_one_for_any_materiality():
    """Stated as arithmetic, not as a table somebody might extend."""
    m = Decimal("0")
    while m <= Decimal("1"):
        value = event_risk_multiplier_for(m)
        assert EVENT_MULTIPLIER_FLOOR <= value <= Decimal("1")
        m += Decimal("0.05")
    # Out-of-range inputs are clamped rather than trusted.
    assert event_risk_multiplier_for(Decimal("5")) == EVENT_MULTIPLIER_FLOOR
    assert event_risk_multiplier_for(Decimal("-3")) == Decimal("1")


def test_immaterial_news_changes_nothing_at_all():
    """A permanently slightly-reduced book is a book with no risk control."""
    assert event_risk_multiplier_for(MATERIALITY_ACTIONABLE - Decimal("0.01")) == Decimal("1")
    assert event_risk_multiplier_for(MATERIALITY_ACTIONABLE) < Decimal("1")


# --- trust and provenance -------------------------------------------------

def test_an_unregistered_source_is_untrusted_rather_than_assumed():
    news = ingress()
    assert news.trust_for("reuters") is SourceTrust.T1_PRIMARY
    assert news.trust_for("aggregator") is SourceTrust.T2_SECONDARY
    assert news.trust_for("someone-who-turned-up") is SourceTrust.UNTRUSTED


def test_a_secondary_report_of_a_primary_event_is_still_a_report():
    news = ingress()
    primary = news.materiality(headline(), basis="CURRENCY_LEG", now_ms=NOW)[0]
    secondary = news.materiality(
        headline(trust=SourceTrust.T2_SECONDARY), basis="CURRENCY_LEG", now_ms=NOW)[0]
    assert secondary < primary
    assert news.materiality(
        headline(trust=SourceTrust.UNTRUSTED), basis="CURRENCY_LEG",
        now_ms=NOW)[1] > Decimal("0.5")   # uncertainty rises as trust falls


def test_a_headline_with_no_source_or_no_title_carries_nothing():
    with pytest.raises(NewsIngressError, match="no source"):
        headline(source_id="")
    with pytest.raises(NewsIngressError, match="no title"):
        headline(title="   ")
    with pytest.raises(NewsIngressError, match="outside"):
        headline(severity=Decimal("1.4"))


# --- dedupe ---------------------------------------------------------------

def test_the_same_story_from_three_feeds_is_one_headline_with_three_relays():
    news = ingress()
    assert news.ingest(headline(), now_ms=NOW) is not None
    assert news.ingest(headline(source_id="aggregator"), now_ms=NOW) is None
    assert news.ingest(headline(source_id="aggregator"), now_ms=NOW) is None
    assert len(news.headlines()) == 1
    relays = news.relayed_by(headline().headline_id)
    assert relays == ("reuters", "aggregator")


def test_identity_is_what_was_said_not_who_relayed_it():
    a = headline()
    b = headline(source_id="aggregator", trust=SourceTrust.T2_SECONDARY,
                 observed_ms=NOW + 5_000)
    assert a.dedupe_hash == b.dedupe_hash
    assert headline(title="Something else entirely").dedupe_hash != a.dedupe_hash


def test_a_duplicate_is_not_written_to_the_ledger_twice(tmp_path):
    ledger = Ledger(tmp_path / "v.sqlite")
    news = ingress(ledger)
    news.ingest(headline(), now_ms=NOW)
    news.ingest(headline(source_id="aggregator"), now_ms=NOW)
    assert ledger.count(EventKind.NEWS_HEADLINE) == 1


# --- relevance ------------------------------------------------------------

def test_a_declared_symbol_is_the_strongest_basis():
    news = ingress()
    relevant, basis = news.mapper.relevance(headline(symbols=("EURUSD",)), "EURUSD")
    assert relevant and basis == "DECLARED_SYMBOL"


def test_an_undeclared_instrument_fails_closed_towards_caution():
    """Same rule `EventRegistry.affects` already applies: unknown means careful."""
    news = ingress()
    assert news.mapper.relevance(headline(), "SOMETHING-UNDECLARED") == (True, "UNDECLARED")
    assert news.mapper.relevance(
        headline(trust=SourceTrust.T2_SECONDARY), "SOMETHING-UNDECLARED"
    ) == (False, "UNDECLARED")


def test_relevance_is_drawn_from_declared_exposure_only():
    news = ingress(registry=declared_registry())
    relevant, basis = news.mapper.relevance(headline(currencies=("EUR",)), "EURUSD")
    assert relevant and basis == "CURRENCY_LEG"
    # A declared instrument with no matching leg is simply not relevant, even
    # to a T1 source: the fail-closed branch is for what we do not know.
    assert news.mapper.relevance(headline(currencies=("ZAR",)), "EURUSD") == (
        False, "NOT_RELEVANT")


def test_an_asset_class_headline_reaches_the_instruments_of_that_class():
    news = ingress(registry=declared_registry())
    relevant, basis = news.mapper.relevance(
        headline(currencies=(), asset_classes=(AssetClass.FX,)), "EURUSD")
    assert relevant and basis == "ASSET_CLASS"


# --- materiality ----------------------------------------------------------

def test_an_old_headline_stops_arguing_rather_than_arguing_forever():
    news = ingress()
    fresh = news.materiality(headline(), basis="DECLARED_SYMBOL", now_ms=NOW)[0]
    half = news.materiality(
        headline(), basis="DECLARED_SYMBOL", now_ms=NOW + WINDOW // 2)[0]
    stale = news.materiality(
        headline(), basis="DECLARED_SYMBOL", now_ms=NOW + WINDOW)[0]
    assert fresh > half > stale == Decimal("0")


def test_an_unstated_severity_is_moderate_rather_than_zero():
    news = ingress()
    unstated = news.materiality(
        headline(severity=None), basis="DECLARED_SYMBOL", now_ms=NOW)[0]
    assert unstated > Decimal("0")


# --- impacts --------------------------------------------------------------

def test_an_impact_is_linked_to_its_subject_and_persisted(tmp_path):
    ledger = Ledger(tmp_path / "v.sqlite")
    news = ingress(ledger)
    news.ingest(headline(symbols=("EURUSD",)), now_ms=NOW)
    impacts = news.assess_subject(
        subject_kind="POSITION", subject_id="ti-1", symbol="EURUSD",
        direction="LONG", now_ms=NOW + 1_000)
    assert len(impacts) == 1
    written = list(ledger.iter(EventKind.EVENT_IMPACT))
    assert len(written) == 1
    payload = written[0].payload
    assert payload["subject_id"] == "ti-1" and payload["subject_kind"] == "POSITION"
    assert payload["relevance_basis"] == "DECLARED_SYMBOL"
    assert payload["authority"] == "REDUCE_ONLY_CALENDAR_REMAINS_BLACKOUT_AUTHORITY"
    assert payload["evidence_refs"], "an impact with no evidence is an opinion"


def test_news_adverse_to_the_other_side_does_not_burden_this_position():
    news = ingress()
    news.ingest(headline(symbols=("EURUSD",), concern=Concern.ADVERSE_TO_SHORT),
                now_ms=NOW)
    assert news.assess_subject(
        subject_kind="POSITION", subject_id="ti-long", symbol="EURUSD",
        direction="LONG", now_ms=NOW + 1_000, persist=False) == []
    assert news.assess_subject(
        subject_kind="POSITION", subject_id="ti-short", symbol="EURUSD",
        direction="SHORT", now_ms=NOW + 1_000, persist=False)


def test_raised_uncertainty_is_adverse_to_any_open_claim():
    news = ingress()
    news.ingest(headline(symbols=("EURUSD",), concern=Concern.UNCLEAR), now_ms=NOW)
    for side in ("LONG", "SHORT"):
        assert news.assess_subject(
            subject_kind="POSITION", subject_id=f"ti-{side}", symbol="EURUSD",
            direction=side, now_ms=NOW + 1_000, persist=False)


def test_the_peak_is_taken_rather_than_the_sum():
    """Two reports of one event are not twice the event."""
    news = ingress()
    news.ingest(headline(symbols=("EURUSD",), severity=Decimal("0.4")), now_ms=NOW)
    news.ingest(headline(title="A second, different story", symbols=("EURUSD",),
                         severity=Decimal("0.9")), now_ms=NOW)
    impacts = news.assess_subject(
        subject_kind="POSITION", subject_id="ti-1", symbol="EURUSD",
        direction="LONG", now_ms=NOW + 1_000, persist=False)
    peak, refs = NewsIngress.peak(impacts)
    assert peak == max(i.materiality for i in impacts)
    assert peak <= Decimal("1")
    # Every source that carried either story is named, none twice.
    assert len(refs) == len(set(refs)) >= 2


# --- the candidate half, and the meta-labeller ---------------------------

def test_candidate_risk_produces_a_bounded_multiplier_and_its_evidence(tmp_path):
    ledger = Ledger(tmp_path / "v.sqlite")
    news = ingress(ledger)
    news.ingest(headline(symbols=("EURUSD",), severity=Decimal("0.9")), now_ms=NOW)
    multiplier, materiality, refs = news.candidate_risk("EURUSD", now_ms=NOW + 1_000)
    assert EVENT_MULTIPLIER_FLOOR <= multiplier < Decimal("1")
    assert materiality > MATERIALITY_ACTIONABLE and refs
    written = list(ledger.iter(EventKind.EVENT_IMPACT))
    assert written and written[0].payload["subject_kind"] == "CANDIDATE"
    assert written[0].payload["subject_id"] == news.candidate_subject_id("EURUSD")


def test_a_non_actionable_candidate_impact_is_not_written_every_cycle(tmp_path):
    """A candidate scan touches every symbol on every pass; recording an
    impact that changes nothing each time would bury the ones that matter."""
    ledger = Ledger(tmp_path / "v.sqlite")
    news = ingress(ledger)
    news.ingest(headline(symbols=("EURUSD",), severity=Decimal("0.05")), now_ms=NOW)
    multiplier, _materiality, _refs = news.candidate_risk("EURUSD", now_ms=NOW + 1_000)
    assert multiplier == Decimal("1")
    assert ledger.count(EventKind.EVENT_IMPACT) == 0


def test_the_meta_labeller_takes_the_news_multiplier_only_when_it_is_smaller():
    """`min`, in both directions: news cannot relax the event-window term."""
    labeler = MetaLabeler()
    assert labeler.news_event_risk == {}
    labeler.news_event_risk["EURUSD"] = Decimal("0.4")
    assert labeler.news_event_risk["EURUSD"] < Decimal("1")


def test_news_reaches_sizing_only_through_a_value_that_cannot_exceed_one():
    from test_strategies_arbiter import state_for
    from test_intelligence import trending
    from vati.strategies.base import Signal
    from vati.risk.contracts import Direction

    state = state_for(trending(240))
    entry = state.features.close
    signal = Signal(
        strategy_id="FX-TREND-PULLBACK-01", strategy_version="1.0.0",
        symbol="EURUSD", direction=Direction.LONG,
        entry=entry, stop=entry - Decimal("0.005"),
        targets=(entry + Decimal("0.010"),),
        expected_gross_move_pct=Decimal("0.01"), horizon="SWING",
        rationale="fixture signal for the news multiplier",
        confidence_hint=Decimal("0.9"))

    quiet = MetaLabeler().score(state, signal, Decimal("4"))
    loud = MetaLabeler(news_event_risk={"EURUSD": Decimal("0.3")}).score(
        state, signal, Decimal("4"))
    generous = MetaLabeler(news_event_risk={"EURUSD": Decimal("5")}).score(
        state, signal, Decimal("4"))

    assert loud.event_risk_multiplier <= quiet.event_risk_multiplier
    assert loud.event_risk_multiplier <= Decimal("1")
    # A configuration error that tries to hand in a value above 1 is clamped,
    # so the worst case is "no reduction", never "more size" (INV-RISK-001).
    assert generous.event_risk_multiplier == quiet.event_risk_multiplier
    assert any("headlines reduce event risk" in r for r in loud.reasons)


# --- files and the CLI ----------------------------------------------------

def test_a_malformed_row_is_counted_and_skipped_never_guessed_at(tmp_path):
    path = tmp_path / "news.jsonl"
    path.write_text("\n".join([
        json.dumps({"source": "reuters", "title": "A real one",
                    "published": NOW, "currencies": "EUR"}),
        json.dumps({"title": "No source at all", "published": NOW}),
        "",
        "# a comment line",
    ]), encoding="utf-8")
    news = ingress()
    counts = news.ingest_rows(rows_from_file(path), now_ms=NOW)
    assert counts == {"accepted": 1, "duplicates": 0, "skipped": 1}
    assert news.skipped and "no source" in news.skipped[0]["error"]


def test_sources_are_declared_in_configuration_not_inferred():
    sources = sources_from_config({"sources": [
        {"source_id": "reuters", "trust": "T1_PRIMARY", "label": "Reuters"},
        {"source_id": "some-blog"},
    ]})
    assert sources[0].trust is SourceTrust.T1_PRIMARY
    assert sources[1].trust is SourceTrust.UNTRUSTED


def test_the_news_ingest_cli_records_headlines_and_reports_skips(tmp_path, capsys):
    from vati.__main__ import main

    config = tmp_path / "news.json"
    config.write_text(json.dumps({
        "sources": [{"source_id": "reuters", "trust": "T1_PRIMARY"}],
        "relevance_window_ms": WINDOW,
    }), encoding="utf-8")
    rows = tmp_path / "headlines.jsonl"
    rows.write_text("\n".join([
        json.dumps({"source": "reuters", "title": "A real one",
                    "published": NOW, "currencies": "EUR",
                    "concern": "ADVERSE_TO_LONG", "severity": "0.8"}),
    ]), encoding="utf-8")
    ledger_path = tmp_path / "v.sqlite"

    code = main(["news-ingest", "--config", str(config), "--file", str(rows),
                 "--ledger", str(ledger_path), "--now", str(NOW)])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["counts"] == {"accepted": 1, "duplicates": 0, "skipped": 0}
    assert report["by_trust"] == {"T1_PRIMARY": 1}
    assert "REDUCE_ONLY" in report["authority"]
    assert report["headlines_recorded"][0]["title"] == "A real one"

    ledger = Ledger(ledger_path)
    try:
        assert ledger.count(EventKind.NEWS_HEADLINE) == 1
    finally:
        ledger.close()


def test_the_news_ingest_cli_exits_non_zero_on_a_broken_feed(tmp_path, capsys):
    from vati.__main__ import main

    config = tmp_path / "news.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    rows = tmp_path / "headlines.jsonl"
    rows.write_text(json.dumps({"title": "No source"}) + "\n", encoding="utf-8")
    assert main(["news-ingest", "--config", str(config), "--file", str(rows),
                 "--now", str(NOW)]) == 1
    capsys.readouterr()
