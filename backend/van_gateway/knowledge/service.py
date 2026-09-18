from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from van_gateway.action.models import ExecutionStatus, VerificationObservation
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.config import Settings
from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
from van_gateway.knowledge.models import (
    KnowledgeProvider,
    KnowledgeOperationStatus,
    NotebookConsumerAskRequest,
    NotebookConsumerNoteCreateRequest,
    NotebookEnterpriseAddSourcesRequest,
    NotebookEnterpriseCreateRequest,
    NotebookEnterpriseDeleteRequest,
    NotebookEnterpriseDeleteSourcesRequest,
    ObsidianQueryRequest,
    ProviderStatus,
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
from van_gateway.knowledge.vekl import VeklKnowledgeProvider
from van_gateway.storage.db import Store


class KnowledgeRuntime:
    """Deterministic knowledge capability plane beneath Hermes.

    Providers return evidence or verified mutation receipts; none can write
    canonical Owner Facts or Project Truth directly.
    """

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.schema = KnowledgeSchema(store)
        self.evidence = KnowledgeEvidenceStore(store)
        self.vekl = VeklKnowledgeProvider(
            self.evidence,
            enabled=settings.vekl_enabled,
            base_url=settings.vekl_base_url,
            session_id=settings.vekl_session_id,
            principal_id=settings.vekl_principal_id,
            bearer_token=settings.vekl_bearer_token,
            timeout_seconds=settings.vekl_timeout_seconds,
        )
        self.obsidian = ObsidianKnowledgeProvider(
            store, self.schema, self.evidence,
            enabled=settings.obsidian_enabled,
            vault_path=settings.obsidian_vault_path,
            max_file_bytes=settings.obsidian_max_file_bytes,
            max_files=settings.obsidian_max_files,
            refresh_interval_seconds=settings.obsidian_refresh_interval_seconds,
        )
        cloud_auth = CloudAccessTokenProvider(
            service_account_file=settings.notebook_enterprise_service_account_file,
            access_token_file=settings.notebook_enterprise_access_token_file,
        )
        self.notebook_enterprise = NotebookEnterpriseProvider(
            store, self.evidence,
            enabled=settings.notebook_enterprise_enabled,
            project_number=settings.notebook_enterprise_project_number,
            location=settings.notebook_enterprise_location,
            auth=cloud_auth,
            timeout_seconds=settings.notebook_enterprise_timeout_seconds,
            upload_root=settings.notebook_enterprise_upload_root,
            max_upload_bytes=settings.notebook_enterprise_max_upload_bytes,
        )
        self.notebook_consumer = NotebookConsumerProvider(
            store, self.evidence,
            enabled=settings.notebook_consumer_enabled,
            profile_dir=settings.notebook_consumer_profile_dir,
            base_url=settings.notebook_consumer_base_url,
            headless=settings.notebook_consumer_headless,
            timeout_seconds=settings.notebook_consumer_timeout_seconds,
        )

    async def startup(self) -> None:
        await self.schema.ensure()

    async def status(self) -> dict[str, Any]:
        providers: list[ProviderStatus] = [
            await self.vekl.status(),
            await self.obsidian.status(),
            await self.notebook_enterprise.status(),
            await self.notebook_consumer.status(),
        ]
        return {
            "providers": [item.model_dump(mode="json") for item in providers],
            "canonical_truth_writes_exposed": False,
            "secret_content_admitted": False,
            "evidence_store": True,
            "provider_certification_required_for_ready": True,
        }

    async def query_vekl(self, request: VeklQueryRequest):
        return await self.vekl.query(request)

    async def certify_vekl(self, request: VeklQueryRequest):
        return await self.vekl.certify(request)

    async def index_obsidian(self, *, force: bool = False):
        return await self.obsidian.index(force=force)

    async def query_obsidian(self, request: ObsidianQueryRequest):
        return await self.obsidian.query(request)

    async def certify_obsidian(self):
        return await self.obsidian.certify()

    async def create_enterprise_notebook(self, request: NotebookEnterpriseCreateRequest):
        return await self.notebook_enterprise.create_notebook(request)

    async def add_enterprise_sources(self, request: NotebookEnterpriseAddSourcesRequest):
        return await self.notebook_enterprise.add_sources(request)

    async def create_consumer_note(self, request: NotebookConsumerNoteCreateRequest):
        return await self.notebook_consumer.create_note(request)


    async def notebook_enterprise_recent(self, page_size: int = 100):
        return await self.notebook_enterprise.list_recent(page_size)

    async def notebook_enterprise_get(self, notebook_id: str):
        return await self.notebook_enterprise.get_notebook(notebook_id)

    async def certify_notebook_enterprise(self):
        return await self.notebook_enterprise.certify()

    async def ask_consumer_notebook(self, request: NotebookConsumerAskRequest):
        return await self.notebook_consumer.ask(request)

    async def certify_consumer_notebook(self, request: NotebookConsumerAskRequest):
        return await self.notebook_consumer.certify(request)

    @staticmethod
    def _provider_failure_status(code: str) -> ExecutionStatus:
        lowered = code.casefold()
        if any(token in lowered for token in ("disabled", "unconfigured", "credential", "auth_required", "authorization_failed", "profile", "playwright_unavailable", "browser_unavailable")):
            return ExecutionStatus.PRECONDITION_FAILED
        if any(token in lowered for token in ("timeout", "unavailable", "still_processing", "connect")):
            return ExecutionStatus.RETRYABLE_FAILURE
        return ExecutionStatus.EXECUTION_FAILED

    async def execute_authorized_action(
        self,
        actions: ActionRuntime,
        *,
        execution_id: str,
        parameters: dict[str, Any],
    ):
        execution = await actions.get_execution(execution_id)
        if execution is None:
            raise ActionPolicyError("unknown_execution")
        if execution.action_id not in {
            "google.notebook.note.create",
            "google.notebook.enterprise.create",
            "google.notebook.enterprise.sources.add",
            "google.notebook.enterprise.delete",
            "google.notebook.enterprise.sources.delete",
        }:
            raise ActionPolicyError("knowledge_action_not_supported")
        if execution.status not in {ExecutionStatus.AUTHORIZED, ExecutionStatus.RETRYABLE_FAILURE}:
            if execution.terminal:
                return execution
            raise ActionPolicyError("knowledge_action_not_authorized")
        if actions.digest_parameters(parameters) != execution.parameters_digest:
            raise ActionPolicyError("knowledge_action_parameter_digest_mismatch")
        await actions.mark_executing(execution_id)
        try:
            if execution.action_id == "google.notebook.note.create":
                request = NotebookConsumerNoteCreateRequest(
                    notebook_id=parameters["notebook_id"],
                    title=parameters["title"],
                    body=parameters.get("body", ""),
                    idempotency_key=execution.idempotency_key,
                )
                result = await self.create_consumer_note(request)
            elif execution.action_id == "google.notebook.enterprise.create":
                request = NotebookEnterpriseCreateRequest(
                    title=parameters["title"], idempotency_key=execution.idempotency_key,
                )
                result = await self.create_enterprise_notebook(request)
            elif execution.action_id == "google.notebook.enterprise.sources.add":
                request = NotebookEnterpriseAddSourcesRequest(
                    notebook_id=parameters["notebook_id"],
                    sources=parameters["sources"],
                    idempotency_key=execution.idempotency_key,
                )
                result = await self.add_enterprise_sources(request)
            elif execution.action_id == "google.notebook.enterprise.delete":
                request = NotebookEnterpriseDeleteRequest(
                    notebook_id=parameters["notebook_id"], idempotency_key=execution.idempotency_key,
                )
                result = await self.notebook_enterprise.delete_notebook(request)
            else:
                request = NotebookEnterpriseDeleteSourcesRequest(
                    notebook_id=parameters["notebook_id"],
                    source_names=parameters["source_names"],
                    idempotency_key=execution.idempotency_key,
                )
                result = await self.notebook_enterprise.delete_sources(request)
        except (KeyError, ValidationError) as exc:
            return await actions.fail_execution(
                execution_id, status=ExecutionStatus.PRECONDITION_FAILED,
                error_code=f"INVALID_KNOWLEDGE_ACTION_PARAMETERS:{type(exc).__name__}",
            )
        except NotebookProviderError as exc:
            return await actions.fail_execution(
                execution_id, status=self._provider_failure_status(str(exc)), error_code=str(exc),
            )

        if result.status == KnowledgeOperationStatus.VERIFIED_SUCCESS:
            await actions.mark_submitted(
                execution_id, correlation=result.correlation, evidence_pointer=result.evidence_pointer,
            )
            await actions.mark_verifying(execution_id)
            return await actions.verify(VerificationObservation(
                execution_id=execution_id,
                success=True,
                correlation=result.correlation,
                observed_postcondition=result.observed_postcondition,
                evidence_pointer=result.evidence_pointer,
            ))
        if result.status == KnowledgeOperationStatus.SUBMITTED:
            return await actions.mark_submitted(
                execution_id, correlation=result.correlation, evidence_pointer=result.evidence_pointer,
            )
        if result.status == KnowledgeOperationStatus.VERIFYING:
            await actions.mark_submitted(
                execution_id, correlation=result.correlation, evidence_pointer=result.evidence_pointer,
            )
            return await actions.mark_verifying(execution_id)
        mapping = {
            KnowledgeOperationStatus.CONFIGURATION_REQUIRED: ExecutionStatus.PRECONDITION_FAILED,
            KnowledgeOperationStatus.EXECUTION_FAILED: ExecutionStatus.EXECUTION_FAILED,
            KnowledgeOperationStatus.VERIFICATION_FAILED: ExecutionStatus.VERIFICATION_FAILED,
            KnowledgeOperationStatus.RETRYABLE_FAILURE: ExecutionStatus.RETRYABLE_FAILURE,
            KnowledgeOperationStatus.CONFLICTED_STATE: ExecutionStatus.CONFLICTED_STATE,
            KnowledgeOperationStatus.PREFLIGHT: ExecutionStatus.EXECUTION_FAILED,
        }
        return await actions.fail_execution(
            execution_id,
            status=mapping[result.status],
            error_code=result.error_code or f"KNOWLEDGE_OPERATION_{result.status.value}",
            evidence_pointer=result.evidence_pointer,
        )