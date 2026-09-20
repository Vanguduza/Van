"""Offline cognition qualification join for Rev 5.1 G4/G3b.

This module wires the decision exam and blind reviewer into one explicit qualification
surface.  It does not promote a model, change a strategy or touch live execution.
"""

from __future__ import annotations

from typing import Mapping

from vati.cognition.blind_reviewer import BlindReviewer, Review, ReviewFn
from vati.cognition.contracts import CognitiveAssessment, ModelRole
from vati.cognition.exam import AnswerFn, ExamResult, run_exam, standard_paper


class CognitionQualificationRuntime:
    def __init__(self, *, ledger=None) -> None:
        self.ledger = ledger

    def run_baseline_exam(self, answer: AnswerFn, *, model_id: str,
                          role: ModelRole = ModelRole.PRIMARY,
                          now_ms: int) -> ExamResult:
        """Run the sealed Rev 5.1 baseline paper. Passing is evidence, not promotion."""
        return run_exam(
            standard_paper(), answer, model_id=model_id, role=role,
            now_ms=now_ms, ledger=self.ledger)

    def blind_review(self, assessment: CognitiveAssessment,
                     context: Mapping[str, object], *,
                     reviewer_id: str, review_fn: ReviewFn,
                     now_ms: int) -> Review:
        """Run a blinded second opinion with deterministic reviewer canaries."""
        reviewer = BlindReviewer(
            reviewer_id=reviewer_id, review_fn=review_fn, ledger=self.ledger)
        return reviewer.review(assessment, context, now_ms=now_ms)
