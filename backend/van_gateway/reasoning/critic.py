"""An executable critic pass over what an assessment actually contains.

P0-COG-001: `assess()` took facts, assumptions, alternatives, critic findings, verifier
findings and a confidence number as caller-supplied arguments, applied two shape rules and
inserted the row. There was no solver, no critic and no verifier pass — while the
implementation matrix recorded WS9 as BUILT with "solver/critic/verifier separation,
unsourced facts refused". The audit's probe stored a fabricated fact with an invented
source, zero critic findings and 0.99 confidence, and got `is_actionable=True`.

This module is the critic. It is deliberately a small set of checks that can actually run
rather than a description of the ones that cannot:

  * a check must be computable from the assessment alone, with no model call — a critic
    that needs a model to run is the thing being criticised;
  * a check must be able to fail on real input, not only on input constructed to fail it;
  * a check's finding must name what is wrong, not that something is.

Four checks earn their place. Everything a language model would be better at — is this
reasoning *good*, is this evidence *relevant* — is deliberately absent, because the honest
version of that is a critic model VAN does not have, and a stub that returned "looks fine"
would be exactly the defect this closes.

What this cannot do is make an assessment true. It can only refuse to let one claim rigour
it did not undergo, which is the claim the matrix was making.
"""

from __future__ import annotations

import re
from typing import Any

#: Words that assert a causal relationship. Cheap to spot and worth spotting: a causal
#: claim standing on a single piece of evidence is the most common overclaim there is.
_CAUSAL = re.compile(
    r"\b(because|therefore|causes?|caused|leads? to|results? in|due to|so that)\b",
    re.IGNORECASE,
)

#: Language that treats a preference as settled. §17's owner-confirmation-bias check.
_SETTLED = re.compile(
    r"\b(obviously|clearly|of course|as always|the owner always|definitely|certainly)\b",
    re.IGNORECASE,
)

#: A confidence above this, with nothing disconfirming considered, is not calibration.
OVERCONFIDENCE_THRESHOLD = 0.85


def _finding(kind: str, detail: str, severity: str = "MEDIUM") -> dict[str, Any]:
    return {"kind": kind, "detail": detail, "severity": severity}


def critique(
    *,
    problem_statement: str,
    known_facts: list[dict[str, Any]],
    assumptions: list[str],
    alternatives: list[str],
    contradictions: list[str],
    failure_modes: list[str],
    evidence_refs: list[str],
    recommended_next_action: str | None,
    confidence: float,
) -> list[dict[str, Any]]:
    """Findings derived from the assessment, not supplied with it."""
    findings: list[dict[str, Any]] = []

    # 1. Evidence quality. A fact asserting authority with no source is already refused
    #    outright; this catches the softer case — a recommendation resting on facts that
    #    cite nothing at all.
    unsourced = [f for f in known_facts if not str(f.get("source") or "").strip()]
    if unsourced and recommended_next_action:
        findings.append(
            _finding(
                "evidence_quality",
                f"{len(unsourced)} of {len(known_facts)} facts cite no source, and an "
                "action is recommended on them",
                "HIGH" if len(unsourced) == len(known_facts) else "MEDIUM",
            )
        )
    if recommended_next_action and not evidence_refs and not known_facts:
        findings.append(
            _finding(
                "evidence_quality",
                "an action is recommended with neither facts nor evidence references",
                "HIGH",
            )
        )

    # 2. Causal overclaim. A causal statement needs more than one observation behind it.
    causal_text = " ".join(
        [problem_statement or "", recommended_next_action or ""]
        + [str(f.get("statement", "")) for f in known_facts]
    )
    if _CAUSAL.search(causal_text) and len(known_facts) + len(evidence_refs) < 2:
        findings.append(
            _finding(
                "causal_overclaim",
                "a causal claim is made with fewer than two independent observations",
            )
        )

    # 3. Owner confirmation bias. Language that treats a preference as settled, with
    #    nothing recorded that would contradict it.
    settled = _SETTLED.search(
        " ".join([problem_statement or ""] + assumptions + [recommended_next_action or ""])
    )
    if settled and not contradictions:
        findings.append(
            _finding(
                "owner_confirmation_bias",
                f"{settled.group(0)!r} treats a preference as settled and nothing "
                "contradicting it was recorded",
            )
        )

    # 4. Ignored alternatives and unexamined failure. A recommendation with one option and
    #    no failure mode has not been reasoned about, whatever its confidence says.
    if recommended_next_action and len(alternatives) < 2:
        findings.append(
            _finding(
                "ignored_alternative",
                f"{len(alternatives)} alternative(s) considered before recommending an action",
            )
        )
    if recommended_next_action and not failure_modes:
        findings.append(
            _finding("missing_constraint", "no failure mode is recorded for the recommendation")
        )

    # 5. Motivated reasoning, in its measurable form: high confidence with nothing
    #    disconfirming. This is the shape the audit's probe had — 0.99 and zero findings.
    if confidence >= OVERCONFIDENCE_THRESHOLD and not contradictions and not failure_modes:
        findings.append(
            _finding(
                "motivated_reasoning",
                f"confidence {confidence:.2f} with no contradiction or failure mode recorded",
                "HIGH",
            )
        )
    return findings


__all__ = ["OVERCONFIDENCE_THRESHOLD", "critique"]
