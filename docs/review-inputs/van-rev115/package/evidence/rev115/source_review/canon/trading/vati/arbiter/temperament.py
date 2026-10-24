"""Deterministic opportunity temperaments, orthogonal to trading authority.

No profile can size, submit, or widen an order. The deterministic Risk
Authority alone sizes signed mandates. AGGRESSIVE requires independently
admitted, current evidence of positive statistical edge (not AI confidence).
Without a verified evidence provider its correct outcome is NO_TRADE.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional, Sequence

from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.portfolio_allocator import (
    AllocationDecision, OpportunityPortfolioAllocator, NOT_SELECTED, SELECTED,
)
from vati.core.canonical import canonical_hash
from vati.risk.mandate import TradingMandate, TradingTemperament

ZERO, ONE = Decimal("0"), Decimal("1")
POLICY_VERSION = "temperament-opportunity/1.0.0"


def _bounded(value: object) -> Optional[Decimal]:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() and ZERO <= number <= ONE else None


@dataclass(frozen=True)
class AdmittedEdge:
    """Externally admitted strategy evidence, scoped to a sealed candidate.

    The caller of admitted_edge_fn MUST obtain this from an independently
    verified validation/ledger registry. Sealing detects tampering but is NOT
    a signature; the source registry, not this dataclass, admits evidence.
    """
    candidate_hash: str
    account_alias: str
    strategy_id: str
    capsule_hash: str
    edge_floor_R: Decimal
    expected_R_per_risk_day: Decimal
    execution_quality: Decimal
    regime_stability: Decimal
    validated_trade_count: int
    valid_until_ms: int
    validation_certificate_hash: str
    evidence_hash: str = ""

    def body(self) -> dict:
        return dict(candidate_hash=self.candidate_hash,
                    account_alias=self.account_alias,
                    strategy_id=self.strategy_id,
                    capsule_hash=self.capsule_hash,
                    edge_floor_R=str(self.edge_floor_R),
                    expected_R_per_risk_day=str(self.expected_R_per_risk_day),
                    execution_quality=str(self.execution_quality),
                    regime_stability=str(self.regime_stability),
                    validated_trade_count=self.validated_trade_count,
                    valid_until_ms=self.valid_until_ms,
                    validation_certificate_hash=self.validation_certificate_hash)

    def sealed(self) -> "AdmittedEdge":
        return replace(self, evidence_hash=canonical_hash(self.body()))

    def valid_for(self, candidate: CandidateOpportunity, *, now_ms: int) -> bool:
        if not self.evidence_hash or self.evidence_hash != canonical_hash(self.body()):
            return False
        if (self.candidate_hash != candidate.candidate_hash or
            self.account_alias != candidate.account_alias or
            self.strategy_id != candidate.strategy_id or
            self.capsule_hash != candidate.capsule_hash):
            return False
        if not self.validation_certificate_hash or self.valid_until_ms <= now_ms:
            return False
        if type(self.validated_trade_count) is not int or self.validated_trade_count < 50:
            return False
        try:
            edge, eff = Decimal(str(self.edge_floor_R)), Decimal(str(self.expected_R_per_risk_day))
        except (InvalidOperation, ValueError, TypeError):
            return False
        if not edge.is_finite() or edge <= ZERO or not eff.is_finite() or eff <= ZERO:
            return False
        return _bounded(self.execution_quality) is not None and _bounded(self.regime_stability) is not None


@dataclass(frozen=True)
class TemperamentVerdict:
    candidate_id: str
    temperament: str
    eligible: bool
    grade: str
    quality_score: Decimal
    risk_fraction: Decimal
    reason: str
    policy_version: str = POLICY_VERSION
    evidence_hash: str = ""
    decision_hash: str = ""

    def sealed(self) -> "TemperamentVerdict":
        body = dict(candidate_id=self.candidate_id, temperament=self.temperament,
                    eligible=self.eligible, grade=self.grade,
                    quality_score=str(self.quality_score),
                    risk_fraction=str(self.risk_fraction), reason=self.reason,
                    policy_version=self.policy_version, evidence_hash=self.evidence_hash)
        return replace(self, decision_hash=canonical_hash(body))


class TemperamentPolicy:
    """Deterministic gates and reduce-only fractions of a signed risk budget."""

    def __init__(
        self, mandate: TradingMandate,
        *, admitted_edge_fn: Optional[Callable[[CandidateOpportunity], Optional[AdmittedEdge]]] = None,
    ) -> None:
        self.mandate, self.admitted_edge_fn = mandate, admitted_edge_fn

    def verdict(self, c: CandidateOpportunity, *, now_ms: int) -> TemperamentVerdict:
        mode = self.mandate.temperament_for(c.strategy_id)
        name = "LEGACY" if mode is None else mode.value

        def result(ok: bool, grade: str, score: Decimal, fraction: Decimal, reason: str,
                   evidence_hash: str = "") -> TemperamentVerdict:
            fraction = fraction if ok and fraction.is_finite() and ZERO <= fraction <= ONE else ZERO
            return TemperamentVerdict(c.candidate_id, name, ok, grade, score, fraction,
                                      reason, evidence_hash=evidence_hash).sealed()

        if not c.candidate_hash or c.candidate_hash != canonical_hash(c.as_dict()):
            return result(False, "NO_TRADE", ZERO, ZERO, "candidate seal invalid")
        if not c.fresh_at(now_ms):
            return result(False, "NO_TRADE", ZERO, ZERO, "candidate stale")
        if (c.account_alias != self.mandate.account_alias or
            c.strategy_id not in self.mandate.allowed_strategies or
            c.symbol.upper() not in self.mandate.instruments):
            return result(False, "NO_TRADE", ZERO, ZERO, "outside mandate scope")
        cost, regime, freshness = c.cost_multiple, _bounded(c.regime_multiplier), c.freshness(now_ms)
        if not cost.is_finite() or cost <= ZERO or regime is None or freshness <= ZERO:
            return result(False, "NO_TRADE", ZERO, ZERO, "invalid market-quality evidence")
        if mode is None:
            return result(True, "LEGACY", cost, ONE, "existing mandate behaviour unchanged")
        if not c.mtf_state_hash or not c.feature_contract_hash or not all(c.source_state_hashes):
            return result(False, "NO_TRADE", ZERO, ZERO, "missing market/feature provenance")

        # Observable cost/regime/freshness, not uncalibrated confidence or
        # a claimed probability of profit.
        base = ((min(cost, Decimal("6")) / Decimal("6")) * Decimal("50") +
                regime * Decimal("35") + freshness * Decimal("15")).quantize(Decimal("0.01"))
        if mode is TradingTemperament.NORMAL:
            if cost < Decimal("2") or regime < Decimal("0.40"):
                return result(False, "NO_TRADE", base, ZERO, "normal quality gate")
            fraction = min(Decimal("0.55"), Decimal("0.25") + base / Decimal("300"))
            return result(True, "STANDARD", base, fraction, "conservative qualified setup")

        if mode is TradingTemperament.RISKY:
            if cost < Decimal("2") or regime < Decimal("0.35"):
                return result(False, "NO_TRADE", base, ZERO, "risky quality gate")
            fraction = min(Decimal("0.85"), Decimal("0.45") + base / Decimal("250"))
            return result(True, "OPPORTUNISTIC", base, fraction, "moderate qualified utilisation")

        if cost < Decimal("3") or regime < Decimal("0.80") or freshness < Decimal("0.50"):
            return result(False, "NO_TRADE", base, ZERO, "aggressive quality gate")
        if self.admitted_edge_fn is None:
            return result(False, "NO_TRADE", base, ZERO, "independent edge authority unavailable")
        try:
            evidence = self.admitted_edge_fn(c)
        except Exception:  # noqa: BLE001 — a validator outage suspends admission
            evidence = None
        try:
            proof_ok = isinstance(evidence, AdmittedEdge) and evidence.valid_for(c, now_ms=now_ms)
        except (ValueError, TypeError, AttributeError, ArithmeticError):
            proof_ok = False
        if not proof_ok:
            return result(False, "NO_TRADE", base, ZERO, "missing independently admitted edge")
        if evidence.execution_quality < Decimal("0.80") or evidence.regime_stability < Decimal("0.80"):
            return result(False, "NO_TRADE", base, ZERO, "execution/regime evidence insufficient")
        if evidence.edge_floor_R < Decimal("0.15"):
            return result(False, "NO_TRADE", base, ZERO, "edge lower bound insufficient")
        quality = min(
            Decimal("100"), base +
            min(Decimal("10"), evidence.edge_floor_R * Decimal("20")) +
            min(Decimal("5"), evidence.expected_R_per_risk_day * Decimal("5")),
        ).quantize(Decimal("0.01"))
        fraction = (ONE if quality >= Decimal("90") and evidence.edge_floor_R >= Decimal("0.30")
                    else Decimal("0.70"))
        return result(True, "EXCEPTIONAL" if fraction == ONE else "HIGH_CONVICTION",
                      quality, fraction, "validated edge and strong market", evidence.evidence_hash)


class TemperedOpportunityAllocator:
    """Profile-aware ranking only: no capital reservation, risk sizing or orders."""

    def __init__(self, base: OpportunityPortfolioAllocator, policy: TemperamentPolicy):
        self.base, self.policy = base, policy

    def rank(self, candidates: Sequence[CandidateOpportunity], *, now_ms: int
             ) -> tuple[AllocationDecision, ...]:
        ranked = self.base.rank(candidates, now_ms=now_ms)
        by_id = {c.candidate_id: c for c in candidates}
        rows = [(r, self.policy.verdict(by_id[r.candidate_id], now_ms=now_ms))
                for r in ranked]
        # Exceptional validated setups take scarce admission slots before
        # ordinary positions. Lower-graded signals cannot exhaust the heat
        # simply because their bar closed first. The Risk Authority still
        # checks aggregate portfolio heat after each actual execution.
        priority = {"EXCEPTIONAL": 5, "HIGH_CONVICTION": 4,
                    "OPPORTUNISTIC": 3, "STANDARD": 2, "LEGACY": 1}
        rows.sort(key=lambda p: (not p[1].eligible,
                                 -priority.get(p[1].grade, 0),
                                 -p[1].quality_score if p[1].eligible else ZERO,
                                 -p[0].allocation_utility,
                                 p[0].candidate_id))
        out = []
        for i, (r, v) in enumerate(rows):
            out.append(replace(
                r, rank=i,
                decision=SELECTED if r.decision == SELECTED and v.eligible else NOT_SELECTED,
                score_components=dict(r.score_components) | {
                    "temperament": v.temperament, "quality_score": str(v.quality_score),
                    "profile_fraction": str(v.risk_fraction),
                    "profile_verdict_hash": v.decision_hash,
                    "evidence_hash": v.evidence_hash},
                explanation=r.explanation + (f"temperament={v.temperament}", v.reason),
                policy_version=POLICY_VERSION, decision_hash="",
            ).sealed())
        return tuple(out)


__all__ = ["AdmittedEdge", "TemperamentPolicy", "TemperamentVerdict",
           "TemperedOpportunityAllocator", "POLICY_VERSION"]
