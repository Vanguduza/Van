"""Rev 5.1 trading cognition (TRD-REV51-091..103, 132).

Everything in this package is offline-evolution or shadow-live. Nothing here
sizes a position, sends an order, or relaxes a deterministic control: the
contract module refuses a model result that even carries order fields, and the
translator (098) can only reduce what the deterministic path already decided.
"""

from vati.cognition.analogues import (
    Analogue,
    AnalogueIndex,
    Episode,
    EpisodeFeatures,
    RetrievalResult,
)
from vati.cognition.context import (
    CompiledContext,
    ContextCompiler,
    ContextIncomplete,
    compile_decision_context,
)
from vati.cognition.contracts import (
    CONTRACT_VERSION,
    REASON_VOCABULARY,
    AssessmentRejected,
    CognitiveAssessment,
    ModelRole,
    Verdict,
    abstention,
    normalise,
)

from vati.cognition.blind_reviewer import BlindReviewer, CanaryHealth, ReviewVerdict
from vati.cognition.budget import CognitiveBudget, Rung
from vati.cognition.attribution import AttributionEngine, TradeFacts
from vati.cognition.exam import ExamPaper, run_exam, standard_paper
from vati.cognition.handoff import ContinuityState, HandoffReason, HandoffRecorder
from vati.cognition.providers import (
    CONTROL_PROFILE,
    ProviderRegistry,
    QuotaScheduler,
    default_registry,
)
from vati.cognition.performance_ledger import CognitivePerformanceLedger, ModelRecord
from vati.cognition.shadow_book import DeterministicOutcome, ShadowBook, ShadowEntry
from vati.cognition.world_model import CognitionStore, TradingWorldModel

__all__ = [
    "Analogue",
    "AttributionEngine",
    "BlindReviewer",
    "CanaryHealth",
    "CognitiveBudget",
    "ReviewVerdict",
    "Rung",
    "CognitivePerformanceLedger",
    "DeterministicOutcome",
    "ExamPaper",
    "ModelRecord",
    "ShadowBook",
    "ShadowEntry",
    "TradeFacts",
    "run_exam",
    "standard_paper",
    "AnalogueIndex",
    "CONTROL_PROFILE",
    "CognitionStore",
    "CompiledContext",
    "ContextCompiler",
    "ContextIncomplete",
    "ContinuityState",
    "Episode",
    "EpisodeFeatures",
    "HandoffReason",
    "HandoffRecorder",
    "ProviderRegistry",
    "QuotaScheduler",
    "RetrievalResult",
    "TradingWorldModel",
    "compile_decision_context",
    "default_registry",
    "CONTRACT_VERSION",
    "REASON_VOCABULARY",
    "AssessmentRejected",
    "CognitiveAssessment",
    "ModelRole",
    "Verdict",
    "abstention",
    "normalise",
]
