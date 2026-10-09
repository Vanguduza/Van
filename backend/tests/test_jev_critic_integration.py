from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.jev.advisor import JevAnnotation
from van_gateway.reasoning.kernel import ChallengeMode, CriticalReasoningKernel


class FakeCriticAdvisor:
    configured = True

    def __init__(self, *, apply_effect: bool, unsupported: float = 0.95, missing: float = 0.1):
        self.apply_effect = apply_effect
        self.unsupported = unsupported
        self.missing = missing

    async def critic(self, _state):
        return JevAnnotation(
            module_id="van.reasoning.critic.v1",
            provider="jev",
            apply_effect=self.apply_effect,
            answers={
                "unsupported_claim": {"type": "noul", "noul": self.unsupported},
                "missing_prerequisite": {"type": "noul", "noul": self.missing},
            },
            result_fingerprint="c" * 64,
            fallback_reason=None,
        )


@pytest.mark.asyncio
async def test_shadow_jev_critic_cannot_change_reasoning_findings(tmp_path):
    store = await make_store(tmp_path)
    kernel = CriticalReasoningKernel(
        store, jev_advisor=FakeCriticAdvisor(apply_effect=False)
    )
    assessment = await kernel.assess(
        problem_statement="Review a bounded claim.",
        challenge_mode=ChallengeMode.BALANCED,
        known_facts=[{"statement": "fact", "source": "evidence:1"}],
        confidence=0.5,
    )
    assert assessment.critic_findings == []


@pytest.mark.asyncio
async def test_active_jev_critic_is_raise_only_and_adds_a_finding(tmp_path):
    store = await make_store(tmp_path)
    kernel = CriticalReasoningKernel(
        store, jev_advisor=FakeCriticAdvisor(apply_effect=True)
    )
    assessment = await kernel.assess(
        problem_statement="Review a bounded claim.",
        challenge_mode=ChallengeMode.BALANCED,
        known_facts=[{"statement": "fact", "source": "evidence:1"}],
        confidence=0.5,
    )
    assert len(assessment.critic_findings) == 1
    finding = assessment.critic_findings[0]
    assert finding.kind == "evidence_quality"
    assert finding.severity == "HIGH"
    assert finding.evidence_ref == "c" * 64


@pytest.mark.asyncio
async def test_jev_can_never_remove_deterministic_critic_findings(tmp_path):
    store = await make_store(tmp_path)
    kernel = CriticalReasoningKernel(
        store,
        jev_advisor=FakeCriticAdvisor(
            apply_effect=True, unsupported=0.1, missing=0.1
        ),
    )
    assessment = await kernel.assess(
        problem_statement="Choose an approach.",
        challenge_mode=ChallengeMode.BALANCED,
        known_facts=[{"statement": "fact", "source": "evidence:1"}],
        alternatives=["A", "B"],
        failure_modes=[],
        recommended_next_action="Use A",
        confidence=0.95,
    )
    kinds = {finding.kind for finding in assessment.critic_findings}
    assert "missing_constraint" in kinds
    assert "motivated_reasoning" in kinds


@pytest.mark.asyncio
async def test_jev_critic_failure_preserves_deterministic_path(tmp_path):
    class FailingAdvisor:
        configured = True

        async def critic(self, _state):
            raise RuntimeError("provider unavailable")

    store = await make_store(tmp_path)
    kernel = CriticalReasoningKernel(store, jev_advisor=FailingAdvisor())
    assessment = await kernel.assess(
        problem_statement="Review a claim.",
        challenge_mode=ChallengeMode.BALANCED,
        known_facts=[{"statement": "fact", "source": "evidence:1"}],
        confidence=0.5,
    )
    assert assessment.critic_findings == []
