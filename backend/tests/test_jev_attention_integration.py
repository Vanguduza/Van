from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.attention.engine import AttentionEngine
from van_gateway.attention.scoring import AttentionCandidate
from van_gateway.jev.advisor import JevAnnotation
from van_gateway.models import AttentionSeverity


class FakeAdvisor:
    configured = True

    def __init__(self, *, apply_effect: bool, fail: bool = False) -> None:
        self.apply_effect = apply_effect
        self.fail = fail
        self.calls = 0

    async def attention_fields(self, state):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return JevAnnotation(
            module_id="van.attention.fields.v1",
            provider="jev",
            apply_effect=self.apply_effect,
            answers={
                "urgency": {"type": "score", "score": 3, "confidence": 0.9},
                "owner_relevance": {"type": "score", "score": 3, "confidence": 0.9},
                "novelty": {"type": "score", "score": 3, "confidence": 0.9},
            },
            result_fingerprint="f" * 64,
            fallback_reason=None,
        )


@pytest.mark.asyncio
async def test_shadow_annotation_is_recorded_but_does_not_change_arithmetic_score(tmp_path):
    store = await make_store(tmp_path)
    advisor = FakeAdvisor(apply_effect=False)
    engine = AttentionEngine(store, jev_advisor=advisor)
    candidate = AttentionCandidate(
        source="ci", dedupe_key="shadow:1", summary="routine",
        importance=0.2, urgency=0.0, actionability=0.1,
        novelty=0.0, owner_relevance=0.0, confidence=1.0, interruption_cost=0.2,
    )
    item = await engine.upsert(
        title="routine", severity=AttentionSeverity.INFO, source="ci",
        dedupe_key="shadow:1", candidate=candidate,
    )
    assert advisor.calls == 1
    assert item.payload["attention_score"] == candidate.score
    assert item.payload["jev_attention"]["apply_effect"] is False
    assert item.payload["jev_attention"]["result_fingerprint"] == "f" * 64


@pytest.mark.asyncio
async def test_active_annotation_can_only_change_declared_fields_before_deterministic_score(tmp_path):
    store = await make_store(tmp_path)
    advisor = FakeAdvisor(apply_effect=True)
    engine = AttentionEngine(store, jev_advisor=advisor)
    candidate = AttentionCandidate(
        source="ci", dedupe_key="active:1", summary="review",
        importance=0.2, urgency=0.0, actionability=0.1,
        novelty=0.0, owner_relevance=0.0, confidence=1.0, interruption_cost=0.2,
    )
    expected = candidate.model_copy(
        update={"urgency": 1.0, "owner_relevance": 1.0, "novelty": 1.0}
    ).score
    item = await engine.upsert(
        title="review", severity=AttentionSeverity.INFO, source="ci",
        dedupe_key="active:1", candidate=candidate,
    )
    assert item.payload["attention_score"] == expected
    assert item.payload["jev_attention"]["apply_effect"] is True
    # Jev did not provide or set a disposition; AttentionScorer still did.
    assert item.payload["attention_disposition"]


@pytest.mark.asyncio
async def test_jev_failure_never_makes_attention_unavailable(tmp_path):
    store = await make_store(tmp_path)
    advisor = FakeAdvisor(apply_effect=False, fail=True)
    engine = AttentionEngine(store, jev_advisor=advisor)
    item = await engine.upsert(
        title="Deploy failed", severity=AttentionSeverity.BLOCKER,
        source="ci", dedupe_key="failure:1",
    )
    assert item.payload["attention_disposition"]
    assert item.payload["jev_attention"]["provider"] == "fallback"
    assert item.payload["jev_attention"]["fallback_reason"] == "JEV_UNAVAILABLE"
