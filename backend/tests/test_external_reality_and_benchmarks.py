"""P2-EVO-001 — §§22, 24, 79. Two evolution stores, one with no producer and one with
no corpus, and neither absence reported anywhere.

`ExternalRealityModel` is "what available evidence says now", kept deliberately apart from
the owner model because §22 calls that separation mandatory: without it, personalization
becomes an echo chamber. Nothing ever wrote to it, so the separation was protecting an
empty store, and `contradictions()` returned nothing in a way indistinguishable from the
world agreeing with the owner.

`BenchmarkHarness` declares fourteen VAN-specific suites and none has a task corpus. That
is not only a reporting gap: `AIEvolutionRadar.transition` refuses ADMITTED without a
benchmark digest, so no technology can be adopted at all. The behaviour is correct — §23's
discipline is do not auto-adopt — and until now an operator would have discovered it by
watching an adoption fail.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, MockTransport, Response

from van_gateway.evolution.radar import (
    AIEvolutionRadar,
    BenchmarkHarness,
    ExternalRealityModel,
    PipelineState,
    RadarError,
)
from van_gateway.research.exa import ExaResearchService
from van_gateway.research.models import ResearchSearchRequest
from van_gateway.storage.db import Store


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "evo.sqlite3"))
    await s.migrate()
    return s


def _exa(store, results):
    def handler(request):
        return Response(200, json={"results": results, "requestId": "req-1"})

    return ExaResearchService(
        store, api_key="k", egress_enabled=True, transport=MockTransport(handler),
    )


@pytest.mark.asyncio
class TestResearchFeedsExternalReality:
    async def test_a_search_records_what_the_sources_claim(self, store):
        service = _exa(store, [
            {"url": "https://example.test/a", "title": "Rates cut to 3%", "id": "1"},
            {"url": "https://example.test/b", "title": "Rates held at 4%", "id": "2"},
        ])
        await service.search(ResearchSearchRequest(query="interest rates"))
        rows = await store.fetchall("SELECT * FROM external_reality ORDER BY claim")
        assert [str(r["claim"]) for r in rows] == ["Rates cut to 3%", "Rates held at 4%"]
        assert {str(r["subject"]) for r in rows} == {"interest rates"}
        assert {str(r["source_kind"]) for r in rows} == {"web_research"}

    async def test_every_observation_cites_its_source(self, store):
        """§41 — an observation about the world with no source is an opinion wearing
        one's clothes, and the model refuses to record one."""
        service = _exa(store, [{"url": "https://example.test/a", "title": "A claim"}])
        await service.search(ResearchSearchRequest(query="q"))
        row = (await store.fetchall("SELECT * FROM external_reality"))[0]
        assert str(row["source_ref"]) == "https://example.test/a"

        with pytest.raises(ValueError, match="requires_source"):
            await ExternalRealityModel(store).observe(
                subject="s", claim="c", source_kind="web_research", source_ref="",
            )

    async def test_a_result_with_no_title_claims_nothing(self, store):
        """A source with no assertion to record is not an observation."""
        service = _exa(store, [{"url": "https://example.test/a"}])
        await service.search(ResearchSearchRequest(query="q"))
        assert await store.fetchall("SELECT * FROM external_reality") == []

    async def test_a_search_result_is_never_marked_as_contradicting_the_owner(self, store):
        """Nothing compares a result with the owner model.

        Setting the flag on a guess would put VAN in the position of deciding the owner is
        wrong on the strength of a headline, which is the opposite of what §22 asks for:
        the disagreement is meant to be recorded as a fact about the world and reconciled
        in the open, not resolved by whoever VAN knows better.
        """
        service = _exa(store, [
            {"url": "https://example.test/a", "title": "The owner is wrong about everything"},
        ])
        await service.search(ResearchSearchRequest(query="q"))
        assert await ExternalRealityModel(store).contradictions() == []
        row = (await store.fetchall("SELECT * FROM external_reality"))[0]
        assert int(row["contradicts_owner_belief"]) == 0

    async def test_confidence_matches_the_trust_the_evidence_row_records(self, store):
        """research_evidence stores UNTRUSTED_EXTERNAL; a friendlier number here would
        make the same source look more credible depending on which table you read."""
        service = _exa(store, [{"url": "https://example.test/a", "title": "A claim"}])
        await service.search(ResearchSearchRequest(query="q"))
        row = (await store.fetchall("SELECT * FROM external_reality"))[0]
        assert float(row["confidence"]) == 0.0
        evidence = (await store.fetchall("SELECT * FROM research_evidence"))[0]
        assert str(evidence["source_trust"]) == "UNTRUSTED_EXTERNAL"


@pytest.mark.asyncio
class TestTheBenchmarkGapIsReportedRatherThanDiscovered:
    async def test_no_suite_has_a_corpus_and_the_coverage_says_so(self, store):
        coverage = await BenchmarkHarness(store).coverage()
        assert coverage["suites_with_a_corpus"] == []
        assert len(coverage["suites"]) == 14
        assert set(coverage["runs_by_suite"].values()) == {0}
        assert "fail-closed" in coverage["consequence"]

    async def test_the_coverage_distinguishes_no_corpus_from_no_runs(self, store):
        """A suite that cannot be run and one that has not been run are different, and a
        reader who cannot tell them apart will read the second as the first."""
        harness = BenchmarkHarness(store)
        await harness.record_run(suite="coding", results=[{"passed": True}])
        coverage = await harness.coverage()
        assert coverage["runs_by_suite"]["coding"] == 1
        assert coverage["runs_by_suite"]["research"] == 0
        # Running one does not give it a corpus; the corpus is the set of tasks.
        assert coverage["suites_with_a_corpus"] == []

    async def test_a_suite_outside_the_vocabulary_is_refused(self, store):
        with pytest.raises(RadarError, match="SUITE_UNKNOWN"):
            await BenchmarkHarness(store).record_run(suite="vibes", results=[])

    async def test_nothing_can_be_admitted_without_a_benchmark(self, store):
        """The consequence the coverage payload names, asserted rather than described.

        §23's discipline is do not auto-adopt, and with no corpus this is what it means in
        practice: the pipeline stops at VALIDATED.
        """
        radar = AIEvolutionRadar(store)
        record = await radar.discover(
            name="Some Model", category="model", source="vendor",
        )
        for target in (PipelineState.WATCH, PipelineState.BENCHMARK,
                       PipelineState.SHADOW, PipelineState.PROPOSED):
            await radar.transition(record.technology_id, target=target)
        with pytest.raises(RadarError, match="NOT_ADMISSIBLE"):
            await radar.transition(
                record.technology_id, target=PipelineState.ADMITTED,
                owner_decision_ref="decision-1",
            )

    async def test_a_benchmarked_technology_still_needs_the_owner(self, store):
        """The two requirements fail separately, which is why they are separate."""
        radar = AIEvolutionRadar(store)
        record = await radar.discover(name="M", category="model", source="vendor")
        await radar.update(
            record.technology_id, benchmark_digest="sha256:abc",
            security_profile="reviewed", licence="Apache-2.0",
        )
        for target in (PipelineState.WATCH, PipelineState.BENCHMARK,
                       PipelineState.SHADOW, PipelineState.PROPOSED):
            await radar.transition(record.technology_id, target=target)
        with pytest.raises(RadarError, match="REQUIRES_OWNER_DECISION"):
            await radar.transition(record.technology_id, target=PipelineState.ADMITTED)
