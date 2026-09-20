"""Rev 5.1 trading cognition (TRD-REV51-091..103, 132).

Everything in this package is offline-evolution or shadow-live. Nothing here
sizes a position, sends an order, or relaxes a deterministic control: the
contract module refuses a model result that even carries order fields, and the
translator (098) can only reduce what the deterministic path already decided.
"""

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

__all__ = [
    "CONTRACT_VERSION",
    "REASON_VOCABULARY",
    "AssessmentRejected",
    "CognitiveAssessment",
    "ModelRole",
    "Verdict",
    "abstention",
    "normalise",
]
