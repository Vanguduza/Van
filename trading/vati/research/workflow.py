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
from vati.learning.allocation import AllocationEpisode
from vati.learning.coverage import StrategyCoverageMap
from vati.learning.drift import DriftSegment, EdgeDriftMonitor, FeatureDriftMonitor
from vati.learning.exit_research import ExitPolicyResearchEngine, PostEntryPath
from vati.learning.overlap import OverlapEvidence, StrategyOverlapDetector
from vati.research.market_data_disagreement import FeedSample, MarketDataDisagreementDetector
from vati.research.trading_evidence import TradingEvidenceArtifact, TradingEvidenceCollector
from vati.risk.capital_promotion import CapitalBudgetProposal, evaluate_proposal


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


__all__ = ["TradingResearchWorkflow"]
