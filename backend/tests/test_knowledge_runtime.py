from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest

from van_gateway.action.models import ExecutionStatus
from van_gateway.action.registry import install_builtin_actions
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.browser.models import BrowserObservation
from van_gateway.browser.service import BrowserTaskService
from van_gateway.config import Settings
from van_gateway.context.models import EpistemicState, SourceTrust
from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
from van_gateway.knowledge.models import (
    KnowledgeOperationStatus,
    KnowledgeProvider,
    NotebookConsumerAskRequest,
    NotebookEnterpriseAddSourcesRequest,
    NotebookEnterpriseCreateRequest,
    NotebookEnterpriseDeleteRequest,
    NotebookOperationResult,
    NotebookSourceInput,
    NotebookSourceKind,
    ObsidianQueryRequest,
    ProviderState,
    VeklQueryRequest,
)
from van_gateway.knowledge.notebook import (
    CloudAccessTokenProvider,
    NotebookConsumerProvider,
    NotebookEnterpriseProvider,
    NotebookProviderError,
)
from van_gateway.knowledge.obsidian import ObsidianKnowledgeProvider
from van_gateway.knowledge.schema import KnowledgeSchema
from van_gateway.knowledge.service import KnowledgeRuntime
from van_gateway.knowledge.vekl import VeklKnowledgeProvider
from van_gateway.models import PrincipalType
from van_gateway.storage.db import Store


async def prepared_store(tmp_path: Path) -> tuple[Store, KnowledgeSchema, KnowledgeEvidenceStore]:
    store = Store(str(tmp_path / "knowledge.sqlite3"))
    await store.migrate()
    schema = KnowledgeSchema(store)
    await schema.ensure()
    return store, schema, KnowledgeEvidenceStore(store)


@pytest.mark.asyncio
async def test_vekl_is_bounded_read_only_evidence_and_canary_certifies(tmp_path):
    store, _schema, evidence = await prepared_store(tmp_path)
    mission_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/missions/{mission_id}/vekl"
        assert request.headers["x-session-id"] == "session-1"
        assert request.headers["x-principal-id"] == "van-owner"
        assert request.headers["authorization"] == "Bearer vekl-token"
        return httpx.Response(200, json={
            "mission": {"id": mission_id, "name": "VAN"},
            "resources": [
                {"name": "Auth policy", "summary": "A1-A5 owner authorization"},
                {"name": "Visual policy", "summary": "Rive state contract"},
            ],
        })

    provider = VeklKnowledgeProvider(
        evidence,
        enabled=True,
        base_url="https://vekl.example",
        session_id="session-1",
        principal_id="van-owner",
        bearer_token="vekl-token",
        transport=httpx.MockTransport(handler),
    )
    request = VeklQueryRequest(mission_id=mission_id, query="auth", max_results=4, scope="VAN")
    result = await provider.query(request)
    assert result.evidence
    assert result.evidence[0].provider == KnowledgeProvider.VEKL
    assert all(item.source_trust == SourceTrust.VERIFIED_SYSTEM for item in result.evidence)
    assert all(item.epistemic_state == EpistemicState.EXTERNAL_EVIDENCE for item in result.evidence)
    assert all(item.source_ref.startswith(f"vekl://mission/{mission_id}#") for item in result.evidence)

    status = await provider.certify(request)
    assert status.state == ProviderState.READY
    row = await store.fetchone("SELECT COUNT(*) AS n FROM knowledge_evidence WHERE provider='VEKL'")
    assert row is not None and int(row["n"]) >= 2
    # Evidence storage must not side-effect canonical owner facts.
    facts = await store.fetchone("SELECT COUNT(*) AS n FROM owner_facts")
    assert facts is not None and int(facts["n"]) == 0


@pytest.mark.asyncio
async def test_obsidian_index_excludes_secret_material_and_tracks_deletion(tmp_path):
    store, schema, evidence = await prepared_store(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "safe.md").write_text(
        "---\ntitle: VAN Canon\ntags: [van, canon]\n---\n# VAN Canon\nDial architecture decision evidence.",
        encoding="utf-8",
    )
    (vault / "secret.md").write_text("# Secret\napi_key = sk-super-secret-1234567890", encoding="utf-8")

    provider = ObsidianKnowledgeProvider(
        store, schema, evidence, enabled=True, vault_path=str(vault), refresh_interval_seconds=1,
    )
    indexed = await provider.index(force=True)
    assert indexed.scanned == 2
    assert indexed.blocked == 1
    result = await provider.query(ObsidianQueryRequest(query="architecture", scope="VAN", refresh=False))
    assert len(result.evidence) == 1
    assert result.evidence[0].source_trust == SourceTrust.TRUSTED_OWNER_FILE
    assert "safe.md" in result.evidence[0].source_ref

    blocked = await store.fetchone("SELECT body_text, blocked_reason FROM obsidian_documents WHERE relative_path='secret.md'")
    assert blocked is not None
    assert blocked["body_text"] == ""
    assert blocked["blocked_reason"] == "SECRET_LIKE_MATERIAL"
    assert "sk-super-secret" not in json.dumps(dict(blocked))

    (vault / "safe.md").unlink()
    reindexed = await provider.index(force=True)
    assert reindexed.deleted == 1
    empty = await provider.query(ObsidianQueryRequest(query="architecture", scope="VAN", refresh=False))
    assert empty.evidence == []


@pytest.mark.asyncio
async def test_notebook_enterprise_create_is_idempotent_and_readback_verified(tmp_path):
    store, _schema, evidence = await prepared_store(tmp_path)
    token_file = tmp_path / "token"
    token_file.write_text("short-lived-token", encoding="utf-8")
    created = False
    create_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal created, create_calls
        assert request.headers.get("authorization") == "Bearer short-lived-token"
        if request.method == "GET" and request.url.path.endswith("/notebooks:listRecentlyViewed"):
            return httpx.Response(200, json={"notebooks": ([{"notebookId": "nb-1", "title": "Dial Health"}] if created else [])})
        if request.method == "POST" and request.url.path.endswith("/notebooks"):
            create_calls += 1
            created = True
            return httpx.Response(200, json={"notebookId": "nb-1", "title": "Dial Health"})
        if request.method == "GET" and request.url.path.endswith("/notebooks/nb-1"):
            return httpx.Response(200, json={"notebookId": "nb-1", "title": "Dial Health"})
        return httpx.Response(404, json={})

    provider = NotebookEnterpriseProvider(
        store, evidence, enabled=True, project_number="123456", location="global",
        auth=CloudAccessTokenProvider(access_token_file=str(token_file)),
        transport=httpx.MockTransport(handler),
    )
    req = NotebookEnterpriseCreateRequest(title="Dial Health", idempotency_key="idem-create-001")
    first = await provider.create_notebook(req)
    second = await provider.create_notebook(req)
    assert first.status == KnowledgeOperationStatus.VERIFIED_SUCCESS
    assert second.status == KnowledgeOperationStatus.VERIFIED_SUCCESS
    assert first.resource_id == "nb-1"
    assert create_calls == 1
    assert first.evidence_pointer == "google://notebook-enterprise/nb-1"


@pytest.mark.asyncio
async def test_notebook_enterprise_sources_support_batch_and_guarded_file_upload(tmp_path):
    store, _schema, evidence = await prepared_store(tmp_path)
    token_file = tmp_path / "token"
    token_file.write_text("short-lived-token", encoding="utf-8")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "brief.md").write_text("# Brief\nGrounded evidence", encoding="utf-8")
    source_ids: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/sources:batchCreate"):
            source_ids.append("s-text")
            return httpx.Response(200, json={"sources": [{"sourceId": {"id": "s-text"}}]})
        if request.method == "POST" and "/upload/v1alpha/" in request.url.path:
            assert request.headers["x-goog-upload-file-name"] == "Brief file"
            source_ids.append("s-file")
            return httpx.Response(200, json={"sourceId": {"id": "s-file"}})
        if request.method == "GET" and request.url.path.endswith("/sources/s-text"):
            return httpx.Response(200, json={"sources": [{"sourceId": {"id": "s-text"}, "settings": {"status": "SOURCE_STATUS_COMPLETE"}}]})
        if request.method == "GET" and request.url.path.endswith("/sources/s-file"):
            return httpx.Response(200, json={"sources": [{"sourceId": {"id": "s-file"}, "settings": {"status": "SOURCE_STATUS_COMPLETE"}}]})
        return httpx.Response(404, json={})

    provider = NotebookEnterpriseProvider(
        store, evidence, enabled=True, project_number="123456", location="global",
        auth=CloudAccessTokenProvider(access_token_file=str(token_file)),
        transport=httpx.MockTransport(handler), upload_root=str(uploads),
    )
    result = await provider.add_sources(NotebookEnterpriseAddSourcesRequest(
        notebook_id="nb-1", idempotency_key="idem-sources-001",
        sources=[
            NotebookSourceInput(kind=NotebookSourceKind.TEXT, source_name="Inline", content="text evidence"),
            NotebookSourceInput(kind=NotebookSourceKind.FILE, source_name="Brief file", file_path="brief.md", mime_type="text/markdown"),
        ],
    ))
    assert result.status == KnowledgeOperationStatus.VERIFIED_SUCCESS
    assert result.correlation["source_ids"] == ["s-text", "s-file"]
    assert source_ids == ["s-text", "s-file"]

    outside = tmp_path / "outside.md"
    outside.write_text("not allowed", encoding="utf-8")
    denied = await provider.add_sources(NotebookEnterpriseAddSourcesRequest(
        notebook_id="nb-1", idempotency_key="idem-sources-002",
        sources=[NotebookSourceInput(kind=NotebookSourceKind.FILE, source_name="Outside", file_path=str(outside), mime_type="text/markdown")],
    ))
    assert denied.status == KnowledgeOperationStatus.EXECUTION_FAILED
    assert denied.error_code == "notebook_enterprise_upload_path_denied"


@pytest.mark.asyncio
async def test_consumer_notebook_fails_closed_without_authenticated_browser_profile(tmp_path):
    store, _schema, evidence = await prepared_store(tmp_path)
    provider = NotebookConsumerProvider(
        store, evidence, enabled=True, profile_alias="authenticated_owner",
    )
    with pytest.raises(NotebookProviderError, match="browser_fabric_unconfigured"):
        await provider.ask(NotebookConsumerAskRequest(notebook_id="nb", question="What changed?"))
    status = await provider.status()
    assert status.state == ProviderState.UNCONFIGURED


@pytest.mark.asyncio
async def test_authorized_notebook_mutation_reaches_verified_success_and_rejects_parameter_swap(tmp_path):
    store = Store(str(tmp_path / "bridge.sqlite3"))
    await store.migrate()
    runtime = KnowledgeRuntime(store, Settings(database_path=str(tmp_path / "bridge.sqlite3")))
    await runtime.startup()
    actions = ActionRuntime(store)
    await install_builtin_actions(actions)
    params = {"notebook_id": "nb-owner", "title": "Dial Health", "body": "Owner note"}
    execution = await actions.begin(
        execution_id="exec-note-knowledge", command_id="cmd-note-knowledge", turn_id="turn-note-knowledge",
        action_id="google.notebook.note.create", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1", idempotency_key="turn-note-knowledge:note",
        parameters=params, snapshot_id=None, owner_approved=True,
    )
    assert execution.status == ExecutionStatus.AUTHORIZED

    async def fake_create(_request, **_lineage):
        return NotebookOperationResult(
            operation_id="op-note-1", provider=KnowledgeProvider.NOTEBOOK_CONSUMER,
            operation="CREATE_NOTE", status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
            idempotency_key=execution.idempotency_key, resource_id="Dial Health",
            correlation={"notebook_id": "nb-owner", "title": "Dial Health", "submitted_by_operation": True},
            observed_postcondition={"title": "Dial Health", "visible": True},
            evidence_pointer="google://notebook-consumer/nb-owner/note/Dial%20Health",
        )

    runtime.create_consumer_note = fake_create  # type: ignore[method-assign]
    receipt = await runtime.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=params)
    assert receipt.status == ExecutionStatus.VERIFIED_SUCCESS
    assert receipt.evidence_pointer is not None

    second_params = {"notebook_id": "nb-owner", "title": "Other"}
    second = await actions.begin(
        execution_id="exec-note-swap", command_id="cmd-note-swap", turn_id="turn-note-swap",
        action_id="google.notebook.note.create", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1", idempotency_key="turn-note-swap:note",
        parameters=second_params, snapshot_id=None, owner_approved=True,
    )
    with pytest.raises(ActionPolicyError, match="parameter_digest_mismatch"):
        await runtime.execute_authorized_action(
            actions, execution_id=second.execution_id,
            parameters={"notebook_id": "nb-owner", "title": "Tampered"},
        )


@pytest.mark.asyncio
async def test_enterprise_source_submission_timeout_is_conflicted_and_never_replayed(tmp_path):
    store, _schema, evidence = await prepared_store(tmp_path)
    token_file = tmp_path / "token"
    token_file.write_text("short-lived-token", encoding="utf-8")
    post_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.method == "POST" and request.url.path.endswith("/sources:batchCreate"):
            post_calls += 1
            raise httpx.ReadTimeout("ambiguous source submission", request=request)
        return httpx.Response(404, json={})

    provider = NotebookEnterpriseProvider(
        store, evidence, enabled=True, project_number="123456", location="global",
        auth=CloudAccessTokenProvider(access_token_file=str(token_file)),
        transport=httpx.MockTransport(handler),
    )
    req = NotebookEnterpriseAddSourcesRequest(
        notebook_id="nb-1", idempotency_key="idem-ambiguous-source-001",
        sources=[NotebookSourceInput(kind=NotebookSourceKind.TEXT, source_name="A", content="evidence")],
    )
    first = await provider.add_sources(req)
    second = await provider.add_sources(req)
    assert first.status == KnowledgeOperationStatus.CONFLICTED_STATE
    assert second.status == KnowledgeOperationStatus.CONFLICTED_STATE
    assert first.error_code and first.error_code.startswith("AMBIGUOUS_SUBMISSION:")
    assert post_calls == 1


@pytest.mark.asyncio
async def test_enterprise_delete_timeout_is_conflicted_and_never_replayed(tmp_path):
    store, _schema, evidence = await prepared_store(tmp_path)
    token_file = tmp_path / "token"
    token_file.write_text("short-lived-token", encoding="utf-8")
    post_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.method == "POST" and request.url.path.endswith("/notebooks:batchDelete"):
            post_calls += 1
            raise httpx.ReadTimeout("ambiguous delete", request=request)
        return httpx.Response(404, json={})

    provider = NotebookEnterpriseProvider(
        store, evidence, enabled=True, project_number="123456", location="global",
        auth=CloudAccessTokenProvider(access_token_file=str(token_file)),
        transport=httpx.MockTransport(handler),
    )
    req = NotebookEnterpriseDeleteRequest(notebook_id="nb-danger", idempotency_key="idem-delete-001")
    first = await provider.delete_notebook(req)
    second = await provider.delete_notebook(req)
    assert first.status == KnowledgeOperationStatus.CONFLICTED_STATE
    assert second.status == KnowledgeOperationStatus.CONFLICTED_STATE
    assert first.error_code and first.error_code.startswith("AMBIGUOUS_DELETE:")
    assert post_calls == 1


@pytest.mark.asyncio
async def test_consumer_preexisting_same_title_is_not_claimed_as_van_created(tmp_path):
    store, _schema, evidence = await prepared_store(tmp_path)

    class Harness:
        configured = True
        async def navigate(self, _task, _url):
            return {"ok": True}
        async def page_info(self, _task):
            return {"url": "https://notebooklm.google.com/notebook/nb-owner"}

    class Stagehand:
        configured = True
        async def act(self, _task, _action):
            return {"ok": True}
        async def extract(self, task, _instruction, _schema):
            return BrowserObservation(
                task_id=task.task_id,
                extraction={"exact_title_exists": True, "auth_required": False},
            )

    provider = NotebookConsumerProvider(
        store,
        evidence,
        enabled=True,
        browser_tasks=BrowserTaskService(store),
        harness=Harness(),  # type: ignore[arg-type]
        stagehand=Stagehand(),  # type: ignore[arg-type]
        profile_alias="authenticated_owner",
        profile_secret_ref="secretref://browser/google-primary",
    )

    result = await provider.create_note(
        __import__('van_gateway.knowledge.models', fromlist=['NotebookConsumerNoteCreateRequest']).NotebookConsumerNoteCreateRequest(
            notebook_id="nb-owner", title="Dial Health", body="", idempotency_key="idem-consumer-existing-001",
        )
    )
    assert result.status == KnowledgeOperationStatus.VERIFICATION_FAILED
    assert result.error_code == "PREEXISTING_NOTE_AMBIGUOUS"
    assert result.evidence_pointer is None

