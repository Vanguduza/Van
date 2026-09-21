"""Concrete orchestration for VATI's slow research plane.

Every method is deliberately non-authoritative: it records research evidence,
diagnostics or proposals. It cannot submit an order, mutate a mandate, promote a
capsule or rewrite protection. This module exists so research components have a
real caller instead of a prose label saying "research workflow".
"""

from __future__ import annotations

import time
from dataclasses import asdict
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence

from vati.core.events import EventKind, make_event
from vati.learning.allocation import AllocationEpisode, RejectedOutcome
from vati.learning.coverage import StrategyCoverageMap
from vati.learning.drift import DriftSegment, EdgeDriftMonitor, FeatureDriftMonitor
from vati.learning.exit_research import ExitPolicyResearchEngine, PostEntryPath
from vati.market_data.bars import Bar
from vati.risk.contracts import Direction
from vati.learning.overlap import OverlapEvidence, StrategyOverlapDetector
from vati.research.market_data_disagreement import FeedSample, MarketDataDisagreementDetector
from vati.research.trading_evidence import TradingEvidenceArtifact, TradingEvidenceCollector
from vati.risk.capital_promotion import CapitalBudgetProposal, evaluate_proposal
from vati.validation.builder import (
    build_feature_validation_certificate,
    build_strategy_validation_certificate,
)


class TradingResearchWorkflow:
    """Reachable slow-loop orchestrator with no live trading authority."""

    def __init__(self, *, ledger=None, clock=None) -> None:
        self.ledger = ledger
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.overlap = StrategyOverlapDetector()
        self.feature_drift = FeatureDriftMonitor()
        self.edge_drift = EdgeDriftMonitor()
        self.exit_research = ExitPolicyResearchEngine()
        self.evidence = TradingEvidenceCollector()
        self.disagreement = MarketDataDisagreementDetector()

    def _log(self, kind: EventKind, payload: dict, *, correlation_id: str = "") -> None:
        if self.ledger is None:
            return
        now = self.clock()
        self.ledger.append(make_event(
            kind, "vati-trading-research", payload,
            event_time_ms=now, received_time_ms=now,
            correlation_id=correlation_id))

    def coverage(self, capsules: Sequence) -> StrategyCoverageMap:
        result = StrategyCoverageMap.from_capsules(capsules)
        self._log(EventKind.STRATEGY_COVERAGE, {
            "map_hash": result.map_hash(),
            "cells": [cell.as_dict() for cell in result.cells()],
            "gap_count": len(result.gaps()),
        })
        return result

    def assess_overlap(self, evidence: OverlapEvidence):
        verdict = self.overlap.assess(evidence)
        self._log(
            EventKind.STRATEGY_OVERLAP,
            {"evidence": evidence.as_dict(), "verdict": verdict.as_dict()},
            correlation_id=f"{evidence.strategy_a}:{evidence.strategy_b}")
        return verdict

    def record_allocation_episode(self, episode: AllocationEpisode) -> AllocationEpisode:
        if not episode.episode_hash:
            episode = episode.sealed()
        elif episode.episode_hash != episode.sealed().episode_hash:
            raise ValueError("allocation episode seal is invalid")
        self._log(
            EventKind.ALLOCATION_EPISODE,
            episode.as_dict() | {"episode_hash": episode.episode_hash},
            correlation_id=episode.allocation_epoch_id)
        return episode

    def research_exits(self, paths: Sequence[PostEntryPath], *, strategy_id: str):
        results = self.exit_research.search(paths, strategy_id=strategy_id)
        self._log(EventKind.EXIT_POLICY_RESEARCH, {
            "strategy_id": strategy_id,
            "candidate_hashes": [r.candidate_hash for r in results],
            "candidates": [r.as_dict() for r in results],
        }, correlation_id=strategy_id)
        return results

    def evaluate_capital_proposal(
        self,
        proposal: CapitalBudgetProposal,
        *,
        now_ms: int,
        mandate_max_risk_per_trade: Decimal,
        platform_max_risk_per_trade: Decimal,
    ):
        verdict = evaluate_proposal(
            proposal,
            now_ms=now_ms,
            mandate_max_risk_per_trade=mandate_max_risk_per_trade,
            platform_max_risk_per_trade=platform_max_risk_per_trade)
        self._log(EventKind.CAPITAL_BUDGET_PROPOSAL, {
            "proposal": proposal.as_dict() | {"proposal_hash": proposal.proposal_hash},
            "verdict": verdict.as_dict(),
        }, correlation_id=proposal.proposal_id)
        return verdict

    def observe_feature_drift(self, segment: DriftSegment, **kwargs):
        observation = self.feature_drift.observe(segment, **kwargs)
        self._log(
            EventKind.FEATURE_DRIFT,
            observation.as_dict() | {"observation_hash": observation.observation_hash},
            correlation_id=segment.key())
        return observation

    def observe_edge_drift(self, **kwargs):
        observation = self.edge_drift.observe(**kwargs)
        self._log(
            EventKind.EDGE_DRIFT,
            observation.as_dict() | {"observation_hash": observation.observation_hash},
            correlation_id=observation.strategy_id)
        return observation

    def admit_evidence(self, artifact: TradingEvidenceArtifact):
        artifact = self.evidence.admit(artifact)
        self._log(
            EventKind.TRADING_EVIDENCE,
            artifact.as_dict() | {"artifact_hash": artifact.artifact_hash},
            correlation_id=artifact.evidence_id)
        return artifact

    def compare_feeds(
        self,
        *,
        symbol: str,
        execution: FeedSample,
        reference: Optional[FeedSample],
        now_ms: int,
    ):
        observation = self.disagreement.compare(
            symbol=symbol, execution=execution, reference=reference, now_ms=now_ms)
        self._log(
            EventKind.MARKET_DATA_DISAGREEMENT,
            observation.as_dict() | {"observation_hash": observation.observation_hash},
            correlation_id=symbol)
        return observation

    def run_spec(self, spec: Mapping[str, object]):
        """Execute one bounded research operation from a machine-readable spec.

        This is the supported runtime entry point for the slow research plane.
        It intentionally contains no route to RiskAuthority, ExecutionRouter,
        TradingMandate mutation, capsule promotion, or protection mutation.
        """
        op = str(spec.get("operation", "")).strip().lower()

        if op == "strategy_certificate":
            raw = dict(spec["validation"])
            cert = build_strategy_validation_certificate(
                strategy_id=str(raw["strategy_id"]),
                strategy_version=str(raw["strategy_version"]),
                capsule_hash=str(raw["capsule_hash"]),
                data_manifest_hash=str(raw["data_manifest_hash"]),
                evidence_refs=tuple(raw["evidence_refs"]),
                feature_set_version=str(raw["feature_set_version"]),
                cost_model_revision=str(raw["cost_model_revision"]),
                pnls=tuple(Decimal(str(x)) for x in raw["pnls"]),
                r_multiples=tuple(Decimal(str(x)) for x in raw["r_multiples"]),
                start_equity=Decimal(str(raw["start_equity"])),
                trial_returns_matrix=tuple(tuple(float(x) for x in row)
                                           for row in raw["trial_returns_matrix"]),
                walk_forward_windows=int(raw["walk_forward_windows"]),
                cost_stress_2x=str(raw["cost_stress_2x"]),
                latency_slippage_stress=str(raw["latency_slippage_stress"]),
                parameter_perturbation_stability=str(raw["parameter_perturbation_stability"]),
                leakage_switch_result=str(raw["leakage_switch_result"]),
                feature_certificate_refs=tuple(raw.get("feature_certificate_refs", ())),
                regime_breakdown=dict(raw.get("regime_breakdown", {})),
                cpcv_configuration=dict(raw.get("cpcv_configuration", {})),
                cpcv_partitions=int(raw.get("cpcv_partitions", 4)),
            )
            self._log(
                EventKind.STRATEGY_VALIDATION_CERTIFICATE,
                cert.as_dict() | {"validation_hash": cert.validation_hash},
                correlation_id=cert.strategy_id,
            )
            return {
                "operation": op,
                "certificate": cert.as_dict() | {"validation_hash": cert.validation_hash},
            }

        if op == "feature_certificate":
            raw = dict(spec["validation"])
            cert = build_feature_validation_certificate(
                feature_id=str(raw["feature_id"]),
                feature_version=str(raw["feature_version"]),
                baseline_feature_set_hash=str(raw["baseline_feature_set_hash"]),
                candidate_feature_set_hash=str(raw["candidate_feature_set_hash"]),
                data_manifest_hash=str(raw["data_manifest_hash"]),
                evidence_refs=tuple(raw["evidence_refs"]),
                instruments=tuple(raw["instruments"]),
                regimes=tuple(raw["regimes"]),
                timeframes=tuple(raw["timeframes"]),
                baseline_returns=tuple(float(x) for x in raw["baseline_returns"]),
                candidate_returns=tuple(float(x) for x in raw["candidate_returns"]),
                trial_delta_matrix=tuple(tuple(float(x) for x in row)
                                         for row in raw["trial_delta_matrix"]),
                baseline_feature_series=tuple(
                    tuple(float(x) for x in row)
                    for row in raw["baseline_feature_series"]),
                candidate_feature_series=tuple(float(x) for x in raw["candidate_feature_series"]),
                walk_forward_baseline=tuple(float(x) for x in raw["walk_forward_baseline"]),
                walk_forward_candidate=tuple(float(x) for x in raw["walk_forward_candidate"]),
                regime_stability={str(k): float(v) for k, v in dict(raw["regime_stability"]).items()},
                instrument_stability={
                    str(k): float(v) for k, v in dict(raw.get("instrument_stability", {})).items()
                },
                leakage_result=str(raw.get("leakage_result", "RED")),
                mutual_information_delta=(
                    float(raw["mutual_information_delta"])
                    if raw.get("mutual_information_delta") is not None else None
                ),
                cpcv_partitions=int(raw.get("cpcv_partitions", 4)),
            )
            self._log(
                EventKind.FEATURE_VALIDATION_CERTIFICATE,
                cert.as_dict() | {"certificate_hash": cert.certificate_hash},
                correlation_id=cert.feature_id,
            )
            return {
                "operation": op,
                "certificate": cert.as_dict() | {"certificate_hash": cert.certificate_hash},
            }

        if op == "coverage":
            from vati.strategies import CapsuleRegistry
            capsule_dir = str(spec.get("capsule_dir", "trading/strategies/registry"))
            result = self.coverage(CapsuleRegistry.load_dir(capsule_dir).all())
            return {"operation": op, "map_hash": result.map_hash(),
                    "gap_count": len(result.gaps()),
                    "cells": [c.as_dict() for c in result.cells()]}

        if op == "overlap":
            raw = dict(spec["evidence"])
            verdict = self.assess_overlap(OverlapEvidence(**raw))
            return {"operation": op, "verdict": verdict.as_dict()}

        if op == "allocation_episode":
            raw = dict(spec["episode"])
            rejected = tuple(RejectedOutcome(
                candidate_id=str(r["candidate_id"]),
                rejection_reason=str(r["rejection_reason"]),
                counterfactual_r=(Decimal(str(r["counterfactual_r"]))
                                  if r.get("counterfactual_r") is not None else None),
                ex_ante_valid=bool(r.get("ex_ante_valid", True)),
                horizon_window_ms=int(r.get("horizon_window_ms", 0)),
            ) for r in raw.get("rejected", ()))
            episode = AllocationEpisode(
                allocation_epoch_id=str(raw["allocation_epoch_id"]),
                account_alias=str(raw["account_alias"]),
                as_of_ms=int(raw["as_of_ms"]),
                portfolio_snapshot_hash=str(raw["portfolio_snapshot_hash"]),
                ranking_policy_version=str(raw["ranking_policy_version"]),
                selected_candidate_ids=tuple(raw.get("selected_candidate_ids", ())),
                rejected=rejected,
                ranking_features=dict(raw.get("ranking_features", {})),
                realised_selected_outcomes=dict(raw.get("realised_selected_outcomes", {})),
                environment=str(raw.get("environment", "BACKTEST")),
                evidence_weight=Decimal(str(raw.get("evidence_weight", "0.2"))),
            ).sealed()
            saved = self.record_allocation_episode(episode)
            return {"operation": op, "episode": saved.as_dict() | {"episode_hash": saved.episode_hash}}

        if op == "feature_drift":
            raw = dict(spec["observation"])
            segment = DriftSegment(**dict(raw.pop("segment")))
            result = self.observe_feature_drift(
                segment,
                baseline_values=tuple(float(v) for v in raw.pop("baseline_values")),
                recent_values=tuple(float(v) for v in raw.pop("recent_values")),
                baseline_contribution=(Decimal(str(raw.pop("baseline_contribution")))
                                       if raw.get("baseline_contribution") is not None else None),
                recent_contribution=(Decimal(str(raw.pop("recent_contribution")))
                                     if raw.get("recent_contribution") is not None else None),
                missing=int(raw.pop("missing", 0)),
                stale=int(raw.pop("stale", 0)),
            )
            return {"operation": op, "observation": result.as_dict() | {"observation_hash": result.observation_hash}}

        if op == "edge_drift":
            raw = dict(spec["observation"])
            for key in (
                "baseline_expectancy_R", "recent_expectancy_R",
                "baseline_edge_floor_R", "recent_edge_floor_R",
                "cost_adjusted_delta", "hit_rate_delta", "holding_time_delta",
            ):
                if key in raw and raw[key] is not None:
                    raw[key] = Decimal(str(raw[key]))
            result = self.observe_edge_drift(**raw)
            return {"operation": op, "observation": result.as_dict() | {"observation_hash": result.observation_hash}}

        if op == "capital_proposal":
            raw = dict(spec["proposal"])
            for key in (
                "current_budget", "proposed_budget", "expectancy_R", "edge_floor_R",
                "max_drawdown", "tail_risk", "capital_efficiency", "execution_quality",
            ):
                raw[key] = Decimal(str(raw[key]))
            proposal = CapitalBudgetProposal(**raw)
            if not proposal.proposal_hash:
                proposal = proposal.sealed()
            verdict = self.evaluate_capital_proposal(
                proposal,
                now_ms=int(spec["now_ms"]),
                mandate_max_risk_per_trade=Decimal(str(spec["mandate_max_risk_per_trade"])),
                platform_max_risk_per_trade=Decimal(str(spec["platform_max_risk_per_trade"])),
            )
            return {"operation": op, "proposal_hash": proposal.proposal_hash,
                    "verdict": verdict.as_dict()}

        if op == "trading_evidence":
            raw = dict(spec["artifact"])
            artifact = TradingEvidenceArtifact(**raw)
            admitted = self.admit_evidence(artifact)
            return {"operation": op, "artifact": admitted.as_dict() | {"artifact_hash": admitted.artifact_hash}}

        if op == "feed_disagreement":
            def sample(raw):
                if raw is None:
                    return None
                d = dict(raw)
                return FeedSample(
                    source=str(d["source"]), bid=Decimal(str(d["bid"])),
                    ask=Decimal(str(d["ask"])), as_of_ms=int(d["as_of_ms"]))
            result = self.compare_feeds(
                symbol=str(spec["symbol"]),
                execution=sample(spec["execution"]),
                reference=sample(spec.get("reference")),
                now_ms=int(spec["now_ms"]),
            )
            return {"operation": op, "observation": result.as_dict() | {"observation_hash": result.observation_hash}}

        if op == "exit_research":
            paths = []
            for raw in spec.get("paths", ()):
                d = dict(raw)
                bars = tuple(Bar(
                    str(b["symbol"]), int(b["start_ms"]), int(b["end_ms"]),
                    Decimal(str(b["open"])), Decimal(str(b["high"])),
                    Decimal(str(b["low"])), Decimal(str(b["close"])),
                    Decimal(str(b.get("volume", "0"))), int(b.get("ticks", 1)),
                    Decimal(str(b.get("avg_spread", "0"))),
                ) for b in d.get("bars", ()))
                paths.append(PostEntryPath(
                    episode_id=str(d["episode_id"]), strategy_id=str(d["strategy_id"]),
                    symbol=str(d["symbol"]), regime=str(d["regime"]), session=str(d["session"]),
                    direction=Direction(str(d["direction"])), entry=Decimal(str(d["entry"])),
                    stop=Decimal(str(d["stop"])), bars=bars,
                    atr_at_entry=(Decimal(str(d["atr_at_entry"]))
                                  if d.get("atr_at_entry") is not None else None),
                ))
            results = self.research_exits(paths, strategy_id=str(spec["strategy_id"]))
            return {"operation": op,
                    "candidates": [r.as_dict() | {"candidate_hash": r.candidate_hash} for r in results]}

        raise ValueError(f"unknown trading research operation {op!r}")


__all__ = ["TradingResearchWorkflow"]
