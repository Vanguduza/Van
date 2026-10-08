"""Owner reads expose bounded local facts and preserve authority/verification boundaries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from tests.conftest_automation import enroll_device, make_store
from van_gateway.action.registry import install_builtin_actions
from van_gateway.action.service import ActionRuntime
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry, ReadinessEvidence
from van_gateway.computer_use.fabric import ComputerInteractionFabric
from van_gateway.config import get_settings
from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
from van_gateway.knowledge.models import KnowledgeProvider, ProviderState, ProviderStatus
from van_gateway.knowledge.service import KnowledgeRuntime
from van_gateway.context.models import SourceTrust
from van_gateway.owner_api import OwnerServiceApi
from van_gateway.research.exa import ExaResearchService
from van_gateway.storage.db import Store

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "owner.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal")
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "test-enrolment")
    monkeypatch.setenv("VAN_OBSIDIAN_VAULT_PATH", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class LocalRuntime:
    def __init__(self, registry, name):
        self.registry, self.name = registry, name

    async def status(self):
        return await self.registry.resolve(
            capability=self.name, configured=True, egress_enabled=True, expected_version="1.0",
        )


@pytest_asyncio.fixture
async def projections(tmp_path):
    store = await make_store(tmp_path)
    await enroll_device(store)
    await install_builtin_actions(ActionRuntime(store))
    knowledge = KnowledgeRuntime(store, get_settings())
    await knowledge.startup()
    registry = ExternalRuntimeRegistry(store)
    automation = SimpleNamespace(
        settings=SimpleNamespace(automation_ingress_enabled=False, automation_egress_enabled=False),
        n8n=LocalRuntime(registry, "n8n"), harness=LocalRuntime(registry, "browser_harness"),
        stagehand=LocalRuntime(registry, "stagehand"), computer_use=ComputerInteractionFabric(store),
    )

    async def ops():
        return {
            "scheduler": {"running": True, "jobs": [{"name": "reminders.fire_due", "interval_seconds": 30,
                "next_due_unix": 123, "last_run": {"run_at_unix": 120, "finished_at_unix": 121,
                "outcome": "FAILED", "detail": {"error": "password=do-not-leak /opt/private/key"}}}]},
            "pki": {"present": True, "days_remaining": 29, "pki_dir": "/opt/private/pki",
                "certificates": [{"subject": "secret host", "fingerprint_sha256": "private"}]},
            "device_pki": {"configured": False, "present": False, "days_remaining": None},
            "backup": {"configured": True, "present": True, "age_seconds": 50, "created_at_unix": 123,
                "path": "/opt/private/backup"},
        }

    api = OwnerServiceApi(store, knowledge=knowledge,
        research=ExaResearchService(store, api_key="synthetic-test-key", egress_enabled=True),
        automation_health=automation, ops_health=ops)
    app = FastAPI()

    @app.middleware("http")
    async def owner_context(request: Request, call_next):
        # Stand-in for the actual gateway token middleware, not a handler auth bypass.
        if request.headers.get("X-Test-Paired-Device"):
            request.state.van_device_id = request.headers["X-Test-Paired-Device"]
        return await call_next(request)

    app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield api, store, registry, client


HEADERS = {"X-Test-Paired-Device": "dev-owner-1"}


async def test_owner_reads_require_current_paired_device_and_are_bounded(projections):
    _, store, _, client = projections
    schema = (await client.get("/openapi.json")).json()
    for path, model in {"knowledge": "OwnerKnowledgeView", "research": "OwnerResearchView",
        "automation": "OwnerAutomationView", "diagnostics": "OwnerDiagnosticsView",
        "browser/tasks/{task_id}/outcome": "OwnerBrowserOutcomeView"}.items():
        documented = schema["paths"][f"/v1/owner/{path}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert documented["$ref"] == f"#/components/schemas/{model}"
        assert schema["components"]["schemas"][model]["additionalProperties"] is False
    browser_fields = schema["components"]["schemas"]["OwnerBrowserOutcomeView"]["properties"]
    assert browser_fields["owner_success"]["const"] is False
    assert browser_fields["verification_state"]["const"] == "UNVERIFIED"
    for path in ("knowledge", "research", "automation", "diagnostics"):
        assert (await client.get(f"/v1/owner/{path}")).status_code == 401
        result = await client.get(f"/v1/owner/{path}", headers=HEADERS)
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["status"] == "AVAILABLE"
    assert (await client.get("/v1/owner/knowledge?limit=101", headers=HEADERS)).status_code == 422
    assert (await client.post("/v1/owner/automation", headers=HEADERS, json={})).status_code == 405
    await store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='dev-owner-1'")
    assert (await client.get("/v1/owner/knowledge", headers=HEADERS)).status_code == 403


async def test_knowledge_citations_and_operations_are_safe_and_citable(projections):
    _, store, _, client = projections
    evidence = KnowledgeEvidenceStore(store)
    good = await evidence.persist(
        provider=KnowledgeProvider.VEKL, query_id="query-1",
        source_ref="https://docs.example/guide?token=private", title="Guide",
        source_trust=SourceTrust.UNTRUSTED_EXTERNAL, retrieved_at_ms=1234,
        scope="global", content="Citable answer", snippet="Citable answer", metadata={"access_token": "private"},
    )
    secret = await evidence.persist(
        provider=KnowledgeProvider.OBSIDIAN, query_id="query-2", title=None,
        source_ref="/opt/private/vault/note.md", source_trust=SourceTrust.UNTRUSTED_EXTERNAL,
        retrieved_at_ms=1235, scope="global", content="private", snippet='{"password":"private"}',
    )
    result = await client.get("/v1/owner/knowledge", headers=HEADERS)
    body = result.json()
    citations = {item["evidence_id"]: item for item in body["evidence"]}
    assert citations[good.evidence_id]["source_ref"] == "https://docs.example/guide"
    assert citations[secret.evidence_id]["source_ref"] is None
    assert citations[secret.evidence_id]["snippet"] == "[redacted]"
    assert "private" not in result.text
    assert body["canonical_truth_writes_exposed"] is False
    assert body["controls"][0]["submission_path"] == "/v1/commands"
    assert body["controls"][0]["available"] is False


async def test_configured_runtime_is_not_ready_and_versions_remain_independent(projections):
    _, _, registry, client = projections
    result = (await client.get("/v1/owner/diagnostics", headers=HEADERS)).json()
    assert {s["state"] for s in result["services"]} == {"CONFIGURED"}
    await registry.record_evidence(ReadinessEvidence(
        capability="n8n", evidence_pointer="test://canary-n8n", runtime_version="1.0", verified_at_ms=1234,
    ))
    await registry.record_evidence(ReadinessEvidence(
        capability="stagehand", evidence_pointer="test://canary-stagehand", runtime_version="2.0", verified_at_ms=1235,
    ))
    response = await client.get("/v1/owner/diagnostics", headers=HEADERS)
    body = response.json()
    states = {s["capability"]: s["state"] for s in body["services"]}
    assert states == {"n8n": "READY", "browser_harness": "CONFIGURED", "stagehand": "VERSION_MISMATCH"}
    assert body["computer_use"]["surfaces_with_a_worker"] == []
    assert body["scheduler"]["jobs"][0]["last_run"]["outcome"] == "FAILED"
    assert body["pki"]["days_remaining"] == 29
    assert body["backup"]["age_seconds"] == 50
    assert body["live_provider_probe_performed"] is False
    assert "private" not in response.text and "certificates" not in response.text


async def test_provider_failure_preserves_other_sections_and_no_error_text_leaks(projections, monkeypatch):
    api, _, _, client = projections

    async def fail():
        raise RuntimeError("authorization=Bearer private /opt/host/secret")

    monkeypatch.setattr(api.automation_health.harness, "status", fail)
    result = await client.get("/v1/owner/diagnostics", headers=HEADERS)
    body = result.json()
    assert body["status"] == "PARTIAL"
    assert body["errors"] == [{"section": "harness", "code": "LOCAL_STATE_UNAVAILABLE"}]
    assert len(body["services"]) == 2 and body["scheduler"]["running"] is True
    assert "private" not in result.text


async def test_research_cached_evidence_does_not_certify_provider(projections):
    _, store, _, client = projections
    await store.execute(
        "INSERT INTO research_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("research-ev", "research-1", "query-hash", "https://source.example/article?key=private", "Article",
         "source.example", "UNTRUSTED_EXTERNAL", None, 1234, "digest", Store.dumps({
             "highlights": ["Useful citation", "password=private"], "api_key": "private"
         })),
    )
    body = (await client.get("/v1/owner/research", headers=HEADERS)).json()
    assert body["provider"]["state"] == "CONFIGURED"
    assert body["evidence"][0]["source_url"] == "https://source.example/article"
    assert body["evidence"][0]["highlights"] == ["Useful citation", "[redacted]"]
    assert body["controls"][0]["available"] is True
    assert body["cached_evidence_is_current_provider_readiness"] is False


async def test_standalone_completed_browser_task_remains_unverified_with_evidence(projections):
    _, store, _, client = projections
    await store.execute("INSERT INTO browser_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        "task-1", None, None, None, "public_research", "STAGEHAND", "L3_STAGEHAND_OBSERVE", "A2",
        "example.com", "Find correct answer", "COMPLETED", "browser-evidence://ev-1", None, 1, 2, 2,
    ))
    await store.execute("INSERT INTO browser_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
        "ev-1", "task-1", "OBSERVATION", "url-digest", None, None, "extraction-digest",
        "UNTRUSTED_EXTERNAL", "NONE_DETECTED", 0, 2, '{"password":"private"}',
    ))
    result = await client.get("/v1/owner/browser/tasks/task-1/outcome", headers=HEADERS)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["execution_completed"] is True
    assert body["worker_goal_reported"] is None
    assert body["owner_success"] is False and body["verification_state"] == "UNVERIFIED"
    assert len(body["evidence"]) == 1 and body["missing_postconditions"] and body["next_action"]
    assert "private" not in result.text
    assert (await client.get("/v1/owner/browser/tasks/missing/outcome", headers=HEADERS)).status_code == 404


async def test_uncorroborated_ready_provider_and_lost_tables_do_not_create_ready(projections, monkeypatch):
    api, store, _, client = projections

    async def unsupported_ready():
        return ProviderStatus(provider=KnowledgeProvider.NOTEBOOK_CONSUMER,
                              state=ProviderState.READY, credential_locus="gateway")

    monkeypatch.setattr(api.knowledge.notebook_consumer, "status", unsupported_ready)
    await store.execute("DROP TABLE notebook_operations")
    result = await client.get("/v1/owner/knowledge", headers=HEADERS)
    body = result.json()
    assert next(p for p in body["providers"] if p["provider"] == "NOTEBOOK_CONSUMER")["state"] == "UNVERIFIED"
    assert body["status"] == "PARTIAL"
    assert body["errors"] == [{"section": "operations", "code": "LOCAL_STATE_UNAVAILABLE"}]
    assert body["controls"][0]["available"] is False


async def test_executable_citations_and_one_time_codes_are_not_exposed(projections):
    _, store, _, client = projections
    evidence = KnowledgeEvidenceStore(store)
    for ref in ("javascript:alert(1)", "data:text/plain,private", "intent://open#private"):
        await evidence.persist(provider=KnowledgeProvider.VEKL, query_id="unsafe-citations",
            source_ref=ref, title=None, source_trust=SourceTrust.UNTRUSTED_EXTERNAL, scope="global",
            content="otp: 123456", snippet="otp: 123456")
    result = await client.get("/v1/owner/knowledge", headers=HEADERS)
    assert all(e["source_ref"] is None and e["snippet"] == "[redacted]" for e in result.json()["evidence"])
    assert "123456" not in result.text


async def test_governance_or_surface_failure_does_not_erase_independent_health(projections, monkeypatch):
    api, _, _, client = projections

    def fail():
        raise OSError("private governance path")

    monkeypatch.setattr("van_gateway.owner_api.governance_state", fail)
    monkeypatch.setattr(api.automation_health.computer_use, "surfaces", fail)
    result = await client.get("/v1/owner/diagnostics", headers=HEADERS)
    body = result.json()
    assert body["status"] == "PARTIAL"
    assert {e["section"] for e in body["errors"]} == {"governance", "computer_use"}
    assert len(body["services"]) == 3 and body["backup"]["present"] is True
    assert "private" not in result.text


async def test_empty_canary_pointer_does_not_create_research_ready(projections):
    _, store, _, client = projections
    await store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES('exa_ready_evidence_pointer','',1)")
    body = (await client.get("/v1/owner/research", headers=HEADERS)).json()
    assert body["provider"]["state"] == "UNVERIFIED"
    assert body["controls"][0]["available"] is False
