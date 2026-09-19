"""P2-COH-002, attention half: one decision path, not two implementations.

AttentionEngine was live and decided nothing beyond a severity enum. AttentionScorer had
§29's five dispositions, real deduplication and a recorded reason for every decision, and
was reached only by the understanding report's metrics — a 2.0 built beside a live 1.0.

The direction of the merge is the part worth defending. Retiring the scorer in favour of
the simpler engine would have been a downgrade dressed as consolidation, so the scorer
makes the decision and the engine remains what it always was: the durable owner-facing
queue.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from conftest_automation import make_store
from van_gateway.attention.engine import SEVERITY_DIMENSIONS, AttentionEngine
from van_gateway.attention.scoring import AttentionCandidate, Disposition
from van_gateway.models import AttentionSeverity


@pytest_asyncio.fixture
async def engine(tmp_path):
    return AttentionEngine(await make_store(tmp_path))


@pytest.mark.asyncio
class TestTheScorerIsOnThePath:
    async def test_an_upsert_records_a_scored_decision(self, engine):
        item = await engine.upsert(
            title="Deploy failed", severity=AttentionSeverity.BLOCKER,
            source="ci", dedupe_key="ci:deploy",
        )
        assert item.payload["attention_disposition"]
        assert item.payload["attention_reason"]
        assert item.payload["attention_candidate_id"]

    async def test_the_decision_is_persisted_as_a_candidate_row(self, engine):
        """A decision nobody can inspect afterwards is not a recorded decision."""
        await engine.upsert(
            title="Deploy failed", severity=AttentionSeverity.URGENT,
            source="ci", dedupe_key="ci:deploy",
        )
        rows = await engine.store.fetchall(
            "SELECT dedupe_key, disposition, reason FROM attention_candidates", ()
        )
        assert len(rows) == 1
        assert rows[0]["dedupe_key"] == "ci:deploy"
        assert rows[0]["reason"]

    async def test_urgent_interrupts_and_info_does_not(self, engine):
        urgent = await engine.upsert(
            title="Trading halted", severity=AttentionSeverity.URGENT,
            source="vati", dedupe_key="vati:halt",
        )
        info = await engine.upsert(
            title="Nightly backup finished", severity=AttentionSeverity.INFO,
            source="ops", dedupe_key="ops:backup",
        )
        assert AttentionEngine.interrupts(urgent)
        assert not AttentionEngine.interrupts(info)

    async def test_a_repeat_within_the_window_is_digested_not_repeated(self, engine):
        """§29 — one decision request, not a stream of reminders about it."""
        first = await engine.upsert(
            title="Deploy failed", severity=AttentionSeverity.BLOCKER,
            source="ci", dedupe_key="ci:deploy",
        )
        second = await engine.upsert(
            title="Deploy failed again", severity=AttentionSeverity.BLOCKER,
            source="ci", dedupe_key="ci:deploy",
        )
        assert AttentionEngine.interrupts(first)
        assert second.payload["attention_reason"] == "duplicate_within_window"
        assert not AttentionEngine.interrupts(second)

    async def test_quiet_hours_hold_everything_except_a_genuine_urgent(self, engine):
        held = await engine.upsert(
            title="Statement ready", severity=AttentionSeverity.FOLLOW_UP,
            source="bank", dedupe_key="bank:statement", quiet_hours=True,
        )
        urgent = await engine.upsert(
            title="Trading halted", severity=AttentionSeverity.URGENT,
            source="vati", dedupe_key="vati:halt", quiet_hours=True,
        )
        assert held.payload["attention_disposition"] == Disposition.DIGEST.value
        assert AttentionEngine.interrupts(urgent)

    async def test_a_caller_may_supply_the_full_candidate(self, engine):
        """The dimensions are available to a caller that knows more than a severity."""
        item = await engine.upsert(
            title="VAN retried the sync and it worked",
            severity=AttentionSeverity.BLOCKER,
            source="sync", dedupe_key="sync:retry",
            candidate=AttentionCandidate(
                source="sync", dedupe_key="sync:retry", internally_recoverable=True
            ),
        )
        assert item.payload["attention_reason"] == "internally_recoverable"
        assert not AttentionEngine.interrupts(item), (
            "VAN recovering from its own transient failure is not the owner's problem"
        )


class TestTheSeverityBridgeIsHonest:
    def test_every_severity_has_dimensions(self):
        for severity in AttentionSeverity:
            assert severity in SEVERITY_DIMENSIONS, severity

    def test_the_dimensions_are_monotonic_in_severity(self):
        """A more severe item must not score lower, or the bridge inverts the enum."""
        order = [
            AttentionSeverity.INFO,
            AttentionSeverity.FOLLOW_UP,
            AttentionSeverity.BLOCKER,
            AttentionSeverity.URGENT,
        ]
        scores = [
            AttentionEngine.candidate_for(
                title="t", severity=s, source="x", dedupe_key="k"
            ).score
            for s in order
        ]
        assert scores == sorted(scores), scores

    def test_urgent_clears_the_interrupt_threshold_and_info_does_not(self):
        from van_gateway.attention.scoring import NOTIFY_THRESHOLD

        urgent = AttentionEngine.candidate_for(
            title="t", severity=AttentionSeverity.URGENT, source="x", dedupe_key="k"
        )
        info = AttentionEngine.candidate_for(
            title="t", severity=AttentionSeverity.INFO, source="x", dedupe_key="k"
        )
        assert urgent.score >= NOTIFY_THRESHOLD
        assert info.score < NOTIFY_THRESHOLD


@pytest.mark.asyncio
class TestAnUndecidedItemIsNotSilenced:
    async def test_an_item_written_before_this_was_wired_still_interrupts(self, engine):
        """Under-notifying about something already queued is the worse failure."""
        from van_gateway.models import AttentionItem, AttentionState

        legacy = AttentionItem(
            id="a1", title="old", severity=AttentionSeverity.BLOCKER,
            state=AttentionState.OPEN, source="x", created_at_unix=1,
            updated_at_unix=1, dedupe_key="k", payload={},
        )
        assert AttentionEngine.interrupts(legacy)
