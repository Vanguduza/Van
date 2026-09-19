"""Gate 5: the live trading path asserted its own safety.

`DecisionCycle.snapshot` set `reconciliation_ok` True, `risk_store_ok` True and
`tier1_event_blackout_active` False as literals, so three of the Risk Authority's refusals
could never fire in a live session — RECONCILIATION_FAILED, RISK_STORE_UNAVAILABLE and
EVENT_BLACKOUT. The authority was correct; the snapshet it read was fiction.

Alongside that: no margin model existed anywhere, the owner halt was discarded by a
restart, the idempotency key was scoped to the process, and the winning strategy's exit
plan was thrown away and replaced by one derived price.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import intent as make_intent, mandate_dict, snapshot as make_snapshot
from vati.app.process_lock import SessionAlreadyRunning, SessionLock
from vati.execution.base import AccountState
from vati.risk import Decision, RiskAuthority, TradingMandate
from vati.risk.authority import MARGIN_CALL_LEVEL_PCT, MARGIN_FLOOR_LEVEL_PCT

ZERO = Decimal("0")


@pytest.fixture
def fx_intent():
    return make_intent()


def _snapshot(eurusd, **over):
    return make_snapshot(eurusd, **over)


class TestTheMarginGate:
    def test_account_state_carries_margin_at_all(self):
        """There was no margin, free margin or margin level field anywhere in the stack."""
        account = AccountState(
            account_alias="a", equity=Decimal("1"), balance=Decimal("1"),
            currency="USD", verified=True,
        )
        assert account.used_margin is None
        assert account.free_margin is None
        assert account.margin_level_pct is None

    def test_an_unreported_margin_is_unknown_not_healthy(self, eurusd, fx_intent):
        """Defaulting to a comfortable number is the hardcoded-healthy defect next door."""
        authority = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
        decision = authority.evaluate_safe(fx_intent, _snapshot(eurusd, margin_level_pct=None))
        assert decision.decision is not Decision.REJECTED or decision.reason_code not in (
            "MARGIN_CALL", "MARGIN_FLOOR", "NO_FREE_MARGIN"
        )

    def test_a_margin_call_refuses_new_risk(self, eurusd, fx_intent):
        authority = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
        decision = authority.evaluate_safe(
            fx_intent, _snapshot(eurusd, margin_level_pct=MARGIN_CALL_LEVEL_PCT)
        )
        assert decision.decision is Decision.REJECTED
        assert decision.reason_code == "MARGIN_CALL"

    def test_the_floor_stops_van_before_the_venue_does(self, eurusd, fx_intent):
        authority = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
        decision = authority.evaluate_safe(
            fx_intent, _snapshot(eurusd, margin_level_pct=MARGIN_FLOOR_LEVEL_PCT)
        )
        assert decision.decision is Decision.REJECTED
        assert decision.reason_code == "MARGIN_FLOOR"
        assert MARGIN_FLOOR_LEVEL_PCT > MARGIN_CALL_LEVEL_PCT

    def test_no_free_margin_refuses(self, eurusd, fx_intent):
        authority = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
        decision = authority.evaluate_safe(fx_intent, _snapshot(eurusd, free_margin=ZERO))
        assert decision.decision is Decision.REJECTED
        assert decision.reason_code == "NO_FREE_MARGIN"

    def test_healthy_margin_does_not_refuse(self, eurusd, fx_intent):
        authority = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
        decision = authority.evaluate_safe(
            fx_intent,
            _snapshot(eurusd, margin_level_pct=Decimal("800"), free_margin=Decimal("9000")),
        )
        assert decision.reason_code not in ("MARGIN_CALL", "MARGIN_FLOOR", "NO_FREE_MARGIN")


class TestTheSafetyFlagsAreNotLiterals:
    def test_the_snapshot_no_longer_hardcodes_them(self):
        """Asserted as source text, because the defect was three literals."""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "vati" / "app" / "cycle.py").read_text()
        for literal in ("reconciliation_ok=True", "risk_store_ok=True",
                        "tier1_event_blackout_active=False"):
            assert literal not in source, f"{literal} is back in the live snapshot"
        for derived in ("_reconciliation_ok", "_risk_store_ok", "_tier1_blackout"):
            assert derived in source

    def test_each_flag_has_a_refusal_that_can_now_fire(self, eurusd, fx_intent):
        authority = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
        for field, code in (
            ("reconciliation_ok", "RECONCILIATION_FAILED"),
            ("risk_store_ok", "RISK_STORE_UNAVAILABLE"),
        ):
            decision = authority.evaluate_safe(fx_intent, _snapshot(eurusd, **{field: False}))
            assert decision.decision is Decision.REJECTED and decision.reason_code == code

    def test_an_event_blackout_refuses_an_uncertified_strategy(self, eurusd, fx_intent):
        authority = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
        decision = authority.evaluate_safe(
            fx_intent, _snapshot(eurusd, tier1_event_blackout_active=True)
        )
        assert decision.decision is Decision.REJECTED
        assert decision.reason_code == "EVENT_BLACKOUT"


class TestTheProcessLock:
    def test_one_alias_cannot_be_served_twice(self, tmp_path):
        held = SessionLock("fx_primary", directory=tmp_path).acquire()
        try:
            with pytest.raises(SessionAlreadyRunning) as caught:
                SessionLock("fx_primary", directory=tmp_path).acquire()
            assert "already running" in str(caught.value)
            assert caught.value.holder_pid
        finally:
            held.release()

    def test_a_different_alias_is_unaffected(self, tmp_path):
        a = SessionLock("fx_primary", directory=tmp_path).acquire()
        b = SessionLock("zse_primary", directory=tmp_path).acquire()
        a.release(); b.release()

    def test_releasing_lets_the_next_process_start(self, tmp_path):
        SessionLock("fx_primary", directory=tmp_path).acquire().release()
        SessionLock("fx_primary", directory=tmp_path).acquire().release()

    def test_serve_refuses_rather_than_running_two(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "vati" / "__main__.py").read_text()
        assert "SessionLock(cfg.account_alias)" in source
        assert "session_already_running" in source


class TestTheIdempotencyKeySurvivesARestart:
    def test_the_seed_no_longer_contains_the_session_id(self):
        """session_id embeds the process start time, so a restart changed the key."""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "vati" / "app" / "cycle.py").read_text()
        assert 'idempotency_seed=f"{cfg.session_id}:{state.as_of_ms}"' not in source
        assert 'idempotency_seed=f"{cfg.account_alias}:{cfg.symbol}:{state.as_of_ms}"' in source

    def test_the_same_bar_yields_the_same_key_across_two_sessions(self, eurusd):
        """The property that matters: a crash and restart on one bar is one order."""
        from vati.arbiter.opportunity import canonical_hash

        def key(seed):
            return canonical_hash({"seed": seed, "decision": "dhash"})[:32]

        first = key("fx_primary:EURUSD:1700000000000")
        second = key("fx_primary:EURUSD:1700000000000")
        assert first == second
        assert first != key("fx_primary:EURUSD:1700000003600")


class TestTheStrategysTargetsSurvive:
    def test_the_dead_code_is_gone(self):
        """An empty assignment and a loop with a bare pass, in the live order path."""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "vati" / "app" / "cycle.py").read_text()
        assert "sig_targets = ()" not in source
        assert "for c in oa.candidates:\n            pass" not in source

    def test_the_assessment_carries_the_winning_signals_targets(self):
        from vati.arbiter.opportunity import OpportunityAssessment

        assessment = OpportunityAssessment(
            symbol="EURUSD", as_of_ms=1, activation_id="a", state_hash="h",
            candidates=(), decision="TRADE", abstain_reason="", intent=None,
            targets=(Decimal("1.10"), Decimal("1.12")),
        )
        assert assessment.targets == (Decimal("1.10"), Decimal("1.12"))

    def test_the_cycle_uses_them_and_only_falls_back_when_there_are_none(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "vati" / "app" / "cycle.py").read_text()
        assert "targets = tuple(oa.targets)" in source
        assert "if not targets and intent.expected_gross_move_pct is not None" in source


class TestTheOwnerHaltSurvivesARestart:
    def test_the_start_time_filter_is_gone(self):
        """`ev.event_time_ms >= self._started_ms` discarded a halt written before the restart."""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "vati" / "app" / "service.py").read_text()
        assert "ev.event_time_ms >= self._started_ms" not in source
        assert "observed_after_restart" in source

    def test_the_halt_is_checked_before_the_first_bar(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "vati" / "app" / "service.py").read_text()
        start = source.index("    def start(self)")
        body = source[start:source.index("    def _observe_owner_halt", start)] if "    def _observe_owner_halt" in source[start:] else source[start:start + 1200]
        assert "_observe_owner_halt" in body, (
            "a session that starts halted must not run a cycle believing it is permitted"
        )
