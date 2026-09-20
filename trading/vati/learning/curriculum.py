"""Curriculum competency gates (integration doc §27). A capsule cannot be
promoted past the stage it has passed; each stage names a measurable test."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from vati.validation.policy import DEFAULT_POLICY

#: S3 — this string used to carry the only correct DSR threshold in the
#: repository as a literal. It is now rendered from the policy object, so the
#: two cannot drift; `test_curriculum_renders_active_policy` asserts it.
_STAGE_1_CRITERIA = f"expectancy >= 0.2R, {DEFAULT_POLICY.describe()} on backtest"


@dataclass(frozen=True)
class CurriculumStage:
    stage: int
    name: str
    condition: str
    pass_criteria: str
    min_weighted_episodes: Decimal
    allows_state: str      # highest capsule state this stage unlocks


CURRICULUM: tuple[CurriculumStage, ...] = (
    CurriculumStage(1, "quiet normal sessions", "vol NORMAL/LOW, no Tier-1 events", _STAGE_1_CRITERIA, Decimal("100"), "VALIDATION"),
    CurriculumStage(2, "standard intraday", "all sessions, NORMAL vol", "cost ratio ≤ 1.2 on demo, no unprotected-position seconds", Decimal("60"), "DEMO"),
    CurriculumStage(3, "high volatility", "vol HIGH", "drawdown within mandate tier 1 on demo", Decimal("40"), "SHADOW"),
    CurriculumStage(4, "Tier-1 events", "NFP/CPI/FOMC windows", "blackout respected 100%; drift entries only", Decimal("12"), "SHADOW"),
    CurriculumStage(5, "cross-market divergence", "USD/rates/gold divergence days", "no BAD_LOSS cluster share > 0.4", Decimal("30"), "LIMITED_LIVE"),
    CurriculumStage(6, "regime transitions", "CUSUM breaks", "WAIT in TRANSITION 100%; recovery loss ≤ 1 tier", Decimal("10"), "LIMITED_LIVE"),
    CurriculumStage(7, "abnormal liquidity", "integrity ELEVATED/ABNORMAL", "half size in ELEVATED, zero orders in ABNORMAL", Decimal("10"), "LIMITED_LIVE"),
    CurriculumStage(8, "broker disruption / failure injection", "disconnect, reject storm, stop rejection", "flatten-on-stop-reject and kill switch fire every time", Decimal("10"), "CERTIFIED_LIVE"),
)

ORDER = ["RESEARCH", "BACKTEST", "VALIDATION", "DEMO", "SHADOW", "LIMITED_LIVE", "CERTIFIED_LIVE"]


def curriculum_gate(passed_stages: set[int], target_state: str) -> tuple[bool, str]:
    """True if every stage that unlocks up to target_state has been passed."""
    if target_state not in ORDER:
        return False, f"unknown state {target_state}"
    needed = [s for s in CURRICULUM if ORDER.index(s.allows_state) <= ORDER.index(target_state)]
    missing = [s.stage for s in needed if s.stage not in passed_stages]
    return (not missing, "ok" if not missing else f"stages not passed: {missing}")
