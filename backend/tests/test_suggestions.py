from __future__ import annotations

import pytest

from van_gateway.attention.engine import AttentionEngine
from van_gateway.storage.db import Store
from van_gateway.suggestions.models import SuggestionCreate,SuggestionDecision,SuggestionStatus
from van_gateway.suggestions.service import SuggestionService,SuggestionServiceError


@pytest.mark.asyncio
async def test_suggestion_requires_evidence_and_acceptance_returns_fresh_prompt_only(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=SuggestionService(store,AttentionEngine(store))
    with pytest.raises(SuggestionServiceError,match="SUGGESTION_EVIDENCE_REQUIRED"):
        await service.create(SuggestionCreate(title="x",rationale="r",proposed_prompt="do x"))
    item=await service.create(SuggestionCreate(
        title="Review supplier",rationale="Mail mentions a changed date",
        proposed_prompt="Review the supplier delivery date",source_refs=["mail:m1"],
    ))
    result=await service.decide(item.suggestion_id,SuggestionDecision(action="accept"))
    assert result["status"]==SuggestionStatus.ACCEPTED.value
    assert result["fresh_owner_prompt"]=="Review the supplier delivery date"
    # There is deliberately no execution id or action result here.
    assert "execution_id" not in result


@pytest.mark.asyncio
async def test_suggestion_is_single_decision(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=SuggestionService(store,AttentionEngine(store))
    item=await service.create(SuggestionCreate(
        title="Idea",rationale="evidence",proposed_prompt="inspect it",source_refs=["ev:1"],
    ))
    await service.decide(item.suggestion_id,SuggestionDecision(action="dismiss"))
    with pytest.raises(SuggestionServiceError,match="SUGGESTION_ALREADY_DECIDED"):
        await service.decide(item.suggestion_id,SuggestionDecision(action="accept"))
