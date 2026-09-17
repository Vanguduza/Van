"""Continuous learning (Rev 4 Part L). Learning is continuous; production
authority is not. Everything here produces evidence, candidates and bounded
reduce-only adjustments. Nothing here can size, send, promote or widen."""

from vati.learning.episodes import Environment, ENVIRONMENT_WEIGHT, ExperienceEpisode, MissedOpportunityEpisode, CounterfactualResult, MacroEventEpisode, episode_from_ledger
from vati.learning.boundary import LearningBoundary, LearningBoundaryError, LiveAdjustment
from vati.learning.health import HealthObservation, StrategyHealthTracker, HealthVerdict
from vati.learning.broker import BrokerExecutionProfile, BrokerLearner, BrokerState
from vati.learning.counterfactual import CounterfactualVariant, run_counterfactuals
from vati.learning.missed import evaluate_missed_opportunity
from vati.learning.priority import ResearchPriorityEngine, ResearchTask
from vati.learning.evolution import FailureCluster, StrategyCandidate, cluster_failures, propose_candidate
from vati.learning.cycles import LearningReport, daily_report, weekly_report, monthly_report
from vati.learning.memory_bridge import ContinuityRecord, HermesMemoryBridge, MemoryBridgeError
from vati.learning.curriculum import CURRICULUM, CurriculumStage, curriculum_gate
from vati.learning.hooks import LearningHooks, to_payload

__all__ = [n for n in dir() if not n.startswith("_")]
