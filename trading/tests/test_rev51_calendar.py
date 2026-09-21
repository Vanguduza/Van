"""TRD-REV51-090 — Economic Calendar Recorder.

The recorder's whole job is to be trustworthy about disagreement and about
history. These tests are mostly about what it refuses to do.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.calendar import (
    CalendarRecorder,
    ObservationConflict,
    ReleaseObservation,
    ReleaseStatus,
    observation_from_row,
    scheduled_from_row,
)
from vati.core.events import EventKind
from vati.core.ledger import Ledger

SCHED_MS = 1_700_000_000_000


def _sched(recorder: CalendarRecorder, name: str = "NFP"):
    rel = scheduled_from_row({"name": name, "release": str(SCHED_MS), "currencies": "USD", "forecast": "160000"})
    recorder.schedule(rel)
    return rel


def _obs(key: str, source: str, actual: str, observed_ms: int) -> ReleaseObservation:
    return ReleaseObservation(key, source, Decimal(actual), observed_ms, SCHED_MS)


def test_one_source_is_provisional_never_verified():
    r = CalendarRecorder()
    s = _sched(r)
    r.observe(_obs(s.event_key, "vendorA", "150000", SCHED_MS + 100))
    assert r.record(s.event_key).status is ReleaseStatus.PROVISIONAL
    assert r.verified_only() == []


def test_two_agreeing_sources_verify_the_value():
    r = CalendarRecorder()
    s = _sched(r)
    r.observe(_obs(s.event_key, "vendorA", "150000", SCHED_MS + 100))
    r.observe(_obs(s.event_key, "vendorB", "150000", SCHED_MS + 250))
    rec = r.record(s.event_key)
    assert rec.status is ReleaseStatus.VERIFIED
    assert rec.agreed_actual == Decimal("150000")
    assert rec.agreeing_sources == ("vendorA", "vendorB")
    assert rec.latency_ms == 100


def test_disagreement_is_disputed_and_yields_no_value():
    """A majority does not make a number true. Two feeds disagreeing means one
    of them is broken, and handing the majority value downstream would hide it."""
    r = CalendarRecorder()
    s = _sched(r)
    r.observe(_obs(s.event_key, "vendorA", "150000", SCHED_MS + 100))
    r.observe(_obs(s.event_key, "vendorB", "150000", SCHED_MS + 110))
    r.observe(_obs(s.event_key, "vendorC", "151000", SCHED_MS + 120))
    rec = r.record(s.event_key)
    assert rec.status is ReleaseStatus.DISPUTED
    assert rec.agreed_actual is None
    assert rec.dissenting == (("vendorC", "151000"),)


def test_a_source_changing_its_value_must_declare_the_supersession():
    r = CalendarRecorder()
    s = _sched(r)
    first = r.observe(_obs(s.event_key, "vendorA", "150000", SCHED_MS + 100))
    with pytest.raises(ObservationConflict):
        r.observe(_obs(s.event_key, "vendorA", "142000", SCHED_MS + 9_000))
    revised = ReleaseObservation(s.event_key, "vendorA", Decimal("142000"),
                                 SCHED_MS + 9_000, SCHED_MS, revision_of=first.observation_id)
    r.observe(revised)
    rec = r.record(s.event_key)
    assert rec.agreed_actual == Decimal("142000")
    # The superseded observation is still on the record.
    assert len(rec.observations) == 2
    assert first.actual == Decimal("150000")


def test_missed_release_is_distinguished_from_not_yet_due():
    r = CalendarRecorder()
    s = _sched(r)
    assert r.record(s.event_key, now_ms=SCHED_MS - 1).status is ReleaseStatus.SCHEDULED
    assert r.record(s.event_key, now_ms=SCHED_MS + 60_000).status is ReleaseStatus.MISSED


def test_observation_for_an_unscheduled_event_is_refused():
    r = CalendarRecorder()
    with pytest.raises(ObservationConflict):
        r.observe(_obs("CPI:123", "vendorA", "3.1", SCHED_MS))


def test_identical_observation_is_idempotent():
    r = CalendarRecorder()
    s = _sched(r)
    o = _obs(s.event_key, "vendorA", "150000", SCHED_MS + 100)
    r.observe(o)
    r.observe(o)
    assert len(r.record(s.event_key).observations) == 1


def test_a_source_reporting_before_the_release_shows_negative_latency():
    """Not a scoop: a feed with a clock or a schedule defect."""
    r = CalendarRecorder()
    s = _sched(r)
    r.observe(_obs(s.event_key, "vendorA", "150000", SCHED_MS - 30_000))
    assert r.record(s.event_key).latency_ms == -30_000


def test_unparseable_rows_are_skipped_and_counted_not_guessed():
    r = CalendarRecorder()
    ok = r.ingest_schedule([
        {"name": "NFP", "release": str(SCHED_MS), "currencies": "USD"},
        {"name": "CPI"},                       # no release time
        {"name": "PPI", "release": "not-a-time", "currencies": "USD"},
    ])
    assert ok == 1
    assert len(r.skipped) == 2
    assert all(s["stage"] == "schedule" for s in r.skipped)


def test_records_are_mirrored_into_the_ledger_for_replay():
    led = Ledger(":memory:")
    r = CalendarRecorder(ledger=led)
    s = _sched(r)
    r.observe(_obs(s.event_key, "vendorA", "150000", SCHED_MS + 100))
    assert led.count(EventKind.CALENDAR_SCHEDULE) == 1
    assert led.count(EventKind.CALENDAR_RELEASE) == 1
    ok, n = led.verify_chain()
    assert ok and n == 2


def test_rescheduling_the_same_key_with_different_terms_is_refused():
    r = CalendarRecorder()
    _sched(r)
    changed = scheduled_from_row({"name": "NFP", "release": str(SCHED_MS), "currencies": "USD|EUR"})
    with pytest.raises(ObservationConflict):
        r.schedule(changed)


def test_row_parsing_derives_the_event_key_from_name_and_time():
    row = observation_from_row({"name": "nfp", "release": str(SCHED_MS), "source": "v", "actual": "1"})
    assert row.event_key == f"NFP:{SCHED_MS}"


def test_report_summarises_status_and_names_disputes():
    r = CalendarRecorder()
    s = _sched(r)
    r.observe(_obs(s.event_key, "a", "1", SCHED_MS + 1))
    r.observe(_obs(s.event_key, "b", "2", SCHED_MS + 2))
    rep = r.report(now_ms=SCHED_MS + 10)
    assert rep["by_status"] == {"DISPUTED": 1}
    assert rep["disputed"] == [s.event_key]
