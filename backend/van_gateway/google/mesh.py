from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.models import ActionClass, GoogleConnectionStatus
from van_gateway.storage.db import Store


class GoogleCredentialPlane(str, Enum):
    WORKSPACE_OAUTH = "workspace_oauth"
    GEMINI_RUNTIME = "gemini_runtime"
    CLOUD_SERVICE = "cloud_service"
    CONSUMER_SESSION = "consumer_session"


class GoogleCapabilityState(str, Enum):
    READY = "READY"
    CONFIGURED = "CONFIGURED"
    UNVERIFIED = "UNVERIFIED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    CAPACITY_LIMITED = "CAPACITY_LIMITED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    UNAVAILABLE = "UNAVAILABLE"


class GoogleRouteRequest(BaseModel):
    owner_intent_id: str
    intent: str
    action_class: ActionClass = ActionClass.A1
    project_id: str | None = None
    truth_sha: str | None = None
    grant_id: str | None = None
    owner_approved: bool = False
    input_refs: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class GoogleRouteDecision(BaseModel):
    status: str
    capability_id: str | None = None
    fallback_capability_id: str | None = None
    state: GoogleCapabilityState | None = None
    identity_alias: str | None = None
    action_class: ActionClass
    requires_approval: bool = False
    reason: str
    job_id: str | None = None
    degraded: list[str] = Field(default_factory=list)


class GooglePrincipalStatus(BaseModel):
    owner_id: str
    registered: bool
    account_kind: str = "unknown"
    ai_plan: str = "UNKNOWN"
    subject_hash_present: bool = False
    status: str = "UNVERIFIED"
    updated_at_unix: int | None = None


class GoogleCapabilityStatus(BaseModel):
    capability_id: str
    family: str
    display_name: str
    credential_plane: GoogleCredentialPlane
    identity_alias: str
    state: GoogleCapabilityState
    reason: str
    public_api: bool
    hermes_owned: bool = True
    configured_by_account: bool = False
    evidence_pointer: str | None = None
    verified_at_unix: int | None = None


class GoogleArtifactRecord(BaseModel):
    artifact_id: str
    job_id: str
    project_id: str | None = None
    source_provider: str = "google"
    source_tool: str
    tool_version: str | None = None
    input_hashes: list[str] = Field(default_factory=list)
    output_hash: str
    trust: str = "UNTRUSTED"
    validation_state: str = "PENDING"
    parent_artifact_ids: list[str] = Field(default_factory=list)
    created_at_unix: int


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    display_name: str
    family: str
    credential_plane: GoogleCredentialPlane
    public_api: bool
    intents: tuple[str, ...]
    fallback: str | None
    action_classes: tuple[str, ...]
    identity_alias: str
    notes: str


class GoogleCapabilityRegistry:
    def __init__(self, path: str) -> None:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.version = str(raw.get("version", "1"))
        identity_policy = raw.get("identity_policy", {})
        self.default_identity = str(identity_policy.get("default_identity", "owner_google_account"))
        self.delegated_identities = dict(identity_policy.get("delegated_identities", {}))
        self._descriptors: dict[str, CapabilityDescriptor] = {}
        for item in raw["capabilities"]:
            descriptor = CapabilityDescriptor(
                capability_id=item["id"],
                display_name=item["display_name"],
                family=item["family"],
                credential_plane=GoogleCredentialPlane(item["credential_plane"]),
                public_api=bool(item["public_api"]),
                intents=tuple(item.get("intents", [])),
                fallback=item.get("fallback"),
                action_classes=tuple(item.get("action_classes", ["A1", "A2"])),
                identity_alias=str(item.get("identity_alias", self.default_identity)),
                notes=item.get("notes", ""),
            )
            if descriptor.identity_alias != self.default_identity:
                delegated = self.delegated_identities.get(descriptor.identity_alias)
                allowed = set(delegated.get("allowed_capabilities", [])) if delegated else set()
                if descriptor.capability_id not in allowed:
                    raise ValueError(f"invalid_google_identity_binding:{descriptor.capability_id}:{descriptor.identity_alias}")
            self._descriptors[descriptor.capability_id] = descriptor

    def get(self, capability_id: str) -> CapabilityDescriptor:
        try:
            return self._descriptors[capability_id]
        except KeyError as exc:
            raise KeyError(f"unknown_google_capability:{capability_id}") from exc

    def list(self) -> list[CapabilityDescriptor]:
        return list(self._descriptors.values())

    def candidates_for_intent(self, intent: str) -> list[CapabilityDescriptor]:
        return [d for d in self.list() if intent in d.intents]


class GoogleIdentityBroker:
    """Canonical owner principal plus explicitly bounded delegated identities."""

    def __init__(
        self,
        store: Store,
        registry: GoogleCapabilityRegistry,
        *,
        ai_plan: str = "UNKNOWN",
        cloud_project_id: str = "",
        gemini_runtime_configured: bool = False,
        cloud_runtime_configured: bool = False,
        consumer_connected_capabilities: str = "",
    ) -> None:
        self.store = store
        self.registry = registry
        self.default_ai_plan = ai_plan.upper()
        self.cloud_project_id = cloud_project_id
        self.gemini_runtime_configured = gemini_runtime_configured
        self.cloud_runtime_configured = cloud_runtime_configured
        self.consumer_connected = {item.strip() for item in consumer_connected_capabilities.split(",") if item.strip()}

    @staticmethod
    def hash_subject(subject: str) -> str:
        return hashlib.sha256(subject.encode("utf-8")).hexdigest()

    async def register_principal(self, *, subject: str, owner_id: str = "owner_google_account", account_kind: str = "personal", ai_plan: str | None = None) -> GooglePrincipalStatus:
        if not subject.strip():
            raise ValueError("google_subject_required")
        now = int(time.time())
        await self.store.execute(
            """
            INSERT INTO google_principal(owner_id, subject_hash, account_kind, ai_plan, status, updated_at_unix)
            VALUES (?, ?, ?, ?, 'VERIFIED_OWNER_ACCOUNT', ?)
            ON CONFLICT(owner_id) DO UPDATE SET
              subject_hash=excluded.subject_hash,
              account_kind=excluded.account_kind,
              ai_plan=excluded.ai_plan,
              status='VERIFIED_OWNER_ACCOUNT',
              updated_at_unix=excluded.updated_at_unix
            """,
            (owner_id, self.hash_subject(subject), account_kind, (ai_plan or self.default_ai_plan).upper(), now),
        )
        return await self.principal_status(owner_id)

    async def principal_status(self, owner_id: str = "owner_google_account") -> GooglePrincipalStatus:
        row = await self.store.fetchone("SELECT * FROM google_principal WHERE owner_id = ?", (owner_id,))
        if row is None:
            return GooglePrincipalStatus(owner_id=owner_id, registered=False)
        return GooglePrincipalStatus(owner_id=owner_id, registered=True, account_kind=row["account_kind"], ai_plan=row["ai_plan"], subject_hash_present=bool(row["subject_hash"]), status=row["status"], updated_at_unix=row["updated_at_unix"])

    async def record_capability_evidence(self, capability_id: str, *, state: GoogleCapabilityState, credential_plane: GoogleCredentialPlane | None = None, evidence_pointer: str | None = None, metadata: dict[str, Any] | None = None, owner_id: str | None = None) -> None:
        descriptor = self.registry.get(capability_id)
        selected_identity = descriptor.identity_alias
        if owner_id is not None and owner_id != selected_identity:
            raise ValueError("google_identity_binding_mismatch")
        owner_id = selected_identity
        plane = credential_plane or descriptor.credential_plane
        now = int(time.time())
        verified_at = now if state == GoogleCapabilityState.READY else None
        await self.store.execute(
            """
            INSERT INTO google_capability_connections(capability_id, owner_id, state, credential_plane, evidence_pointer, verified_at_unix, metadata_json, updated_at_unix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(capability_id) DO UPDATE SET
              owner_id=excluded.owner_id,
              state=excluded.state,
              credential_plane=excluded.credential_plane,
              evidence_pointer=excluded.evidence_pointer,
              verified_at_unix=excluded.verified_at_unix,
              metadata_json=excluded.metadata_json,
              updated_at_unix=excluded.updated_at_unix
            """,
            (capability_id, owner_id, state.value, plane.value, evidence_pointer, verified_at, Store.dumps(metadata or {}), now),
        )

    async def _evidence(self, capability_id: str) -> Any | None:
        return await self.store.fetchone("SELECT * FROM google_capability_connections WHERE capability_id = ?", (capability_id,))

    async def capability_status(self, capability_id: str, *, workspace: GoogleConnectionStatus | None = None, owner_id: str | None = None) -> GoogleCapabilityStatus:
        descriptor = self.registry.get(capability_id)
        selected_identity = descriptor.identity_alias
        if owner_id is not None and owner_id != selected_identity:
            return GoogleCapabilityStatus(capability_id=descriptor.capability_id, family=descriptor.family, display_name=descriptor.display_name, credential_plane=descriptor.credential_plane, identity_alias=selected_identity, state=GoogleCapabilityState.POLICY_BLOCKED, reason="google_identity_binding_mismatch", public_api=descriptor.public_api)
        principal = await self.principal_status(selected_identity)
        evidence = await self._evidence(capability_id)
        if evidence is not None:
            state = GoogleCapabilityState(evidence["state"])
            reason = "certification_evidence"
            if not principal.registered and state in {GoogleCapabilityState.CONFIGURED, GoogleCapabilityState.READY}:
                state = GoogleCapabilityState.UNVERIFIED
                reason = "canonical_google_principal_not_registered"
            return GoogleCapabilityStatus(capability_id=descriptor.capability_id, family=descriptor.family, display_name=descriptor.display_name, credential_plane=descriptor.credential_plane, identity_alias=selected_identity, state=state, reason=reason, public_api=descriptor.public_api, configured_by_account=principal.registered, evidence_pointer=evidence["evidence_pointer"], verified_at_unix=evidence["verified_at_unix"])

        plane = descriptor.credential_plane
        state = GoogleCapabilityState.UNAVAILABLE
        reason = "credential_plane_unavailable"
        if plane == GoogleCredentialPlane.WORKSPACE_OAUTH:
            state = GoogleCapabilityState.CONFIGURED if workspace is not None and workspace.connected else GoogleCapabilityState.AUTH_REQUIRED
            reason = "workspace_oauth_connected" if state == GoogleCapabilityState.CONFIGURED else "workspace_oauth_not_connected"
        elif plane == GoogleCredentialPlane.GEMINI_RUNTIME and self.gemini_runtime_configured:
            state, reason = GoogleCapabilityState.CONFIGURED, "hermes_gemini_runtime_configured"
        elif plane == GoogleCredentialPlane.CLOUD_SERVICE and self.cloud_project_id and self.cloud_runtime_configured:
            state, reason = GoogleCapabilityState.CONFIGURED, "google_cloud_runtime_configured"
        elif plane == GoogleCredentialPlane.CONSUMER_SESSION:
            if capability_id in self.consumer_connected:
                state, reason = GoogleCapabilityState.CONFIGURED, "owner_google_session_configured"
            else:
                state, reason = GoogleCapabilityState.AUTH_REQUIRED, "owner_google_session_not_certified"
        if not principal.registered and state in {GoogleCapabilityState.CONFIGURED, GoogleCapabilityState.READY}:
            state, reason = GoogleCapabilityState.UNVERIFIED, "canonical_google_principal_not_registered"
        return GoogleCapabilityStatus(capability_id=descriptor.capability_id, family=descriptor.family, display_name=descriptor.display_name, credential_plane=descriptor.credential_plane, identity_alias=selected_identity, state=state, reason=reason, public_api=descriptor.public_api, configured_by_account=principal.registered)

    async def mesh_status(self, *, workspace: GoogleConnectionStatus | None = None, owner_id: str | None = None) -> dict[str, Any]:
        principal = await self.principal_status(owner_id or self.registry.default_identity)
        capabilities = [await self.capability_status(d.capability_id, workspace=workspace) for d in self.registry.list()]
        return {"principal": principal.model_dump(), "capabilities": [c.model_dump() for c in capabilities], "registry_version": self.registry.version, "hermes_is_sole_agent_runtime": True}


class GoogleCapabilityRouter:
    """Deterministic planner only; Hermes owns actual agent execution."""

    USABLE_STATES = {GoogleCapabilityState.READY, GoogleCapabilityState.CONFIGURED}

    def __init__(self, store: Store, broker: GoogleIdentityBroker) -> None:
        self.store = store
        self.broker = broker

    async def plan(self, request: GoogleRouteRequest, *, workspace: GoogleConnectionStatus | None = None) -> GoogleRouteDecision:
        if request.action_class == ActionClass.A5:
            return GoogleRouteDecision(status="denied", action_class=request.action_class, reason="A5 is prohibited")
        if request.action_class == ActionClass.A4 and not request.owner_approved:
            return GoogleRouteDecision(status="approval_required", action_class=request.action_class, requires_approval=True, reason="A4 requires explicit owner approval before provider routing")
        if request.action_class in {ActionClass.A3, ActionClass.A4} and not request.grant_id:
            return GoogleRouteDecision(status="degraded", action_class=request.action_class, reason="mutating Google jobs require an explicit capability grant", degraded=["GOOGLE_CAPABILITY_UNAVAILABLE"])
        if request.action_class in {ActionClass.A3, ActionClass.A4} and request.project_id and not request.truth_sha:
            return GoogleRouteDecision(status="degraded", action_class=request.action_class, reason="mutating project work requires Project Truth SHA", degraded=["STALE_PROJECT_TRUTH"])
        direct = self.broker.registry.candidates_for_intent(request.intent)
        if not direct:
            return GoogleRouteDecision(status="unsupported", action_class=request.action_class, reason=f"no Google capability registered for intent:{request.intent}")
        candidates: list[CapabilityDescriptor] = []
        seen: set[str] = set()
        for descriptor in direct:
            if descriptor.capability_id not in seen:
                candidates.append(descriptor)
                seen.add(descriptor.capability_id)
            if descriptor.fallback and descriptor.fallback not in seen:
                candidates.append(self.broker.registry.get(descriptor.fallback))
                seen.add(descriptor.fallback)
        skipped: list[GoogleCapabilityStatus] = []
        for descriptor in candidates:
            if request.action_class.value not in descriptor.action_classes:
                continue
            status = await self.broker.capability_status(descriptor.capability_id, workspace=workspace)
            if status.state not in self.USABLE_STATES:
                skipped.append(status)
                continue
            job_id = await self._create_job(request, descriptor.capability_id)
            degraded: list[str] = []
            for item in skipped:
                if item.capability_id == "antigravity" and item.state in {
                    GoogleCapabilityState.CAPACITY_LIMITED,
                    GoogleCapabilityState.RATE_LIMITED,
                }:
                    degraded.append("ANTIGRAVITY_CAPACITY_LIMITED")
            return GoogleRouteDecision(
                status="planned",
                capability_id=descriptor.capability_id,
                fallback_capability_id=descriptor.fallback,
                state=status.state,
                identity_alias=descriptor.identity_alias,
                action_class=request.action_class,
                reason="deterministic capability route selected; Hermes must execute the job",
                job_id=job_id,
                degraded=degraded,
            )
        first_unusable = skipped[0] if skipped else None
        degraded_codes = ["GOOGLE_CAPABILITY_UNAVAILABLE"]
        if first_unusable and first_unusable.capability_id == "antigravity" and first_unusable.state in {
            GoogleCapabilityState.CAPACITY_LIMITED,
            GoogleCapabilityState.RATE_LIMITED,
        }:
            degraded_codes = ["ANTIGRAVITY_CAPACITY_LIMITED"]
        identity_alias = None
        if first_unusable is not None:
            identity_alias = self.broker.registry.get(first_unusable.capability_id).identity_alias
        return GoogleRouteDecision(
            status="degraded",
            capability_id=first_unusable.capability_id if first_unusable else None,
            state=first_unusable.state if first_unusable else GoogleCapabilityState.UNAVAILABLE,
            identity_alias=identity_alias,
            action_class=request.action_class,
            reason=first_unusable.reason if first_unusable else "no usable Google capability",
            degraded=degraded_codes,
        )

    async def _create_job(self, request: GoogleRouteRequest, capability_id: str) -> str:
        job_id, now = str(uuid.uuid4()), int(time.time())
        canonical = {"owner_intent_id": request.owner_intent_id, "intent": request.intent, "action_class": request.action_class.value, "project_id": request.project_id, "truth_sha": request.truth_sha, "grant_id": request.grant_id, "input_refs": sorted(request.input_refs), "constraints": request.constraints, "capability_id": capability_id, "identity_alias": self.broker.registry.get(capability_id).identity_alias}
        input_hash = hashlib.sha256(Store.dumps(canonical).encode("utf-8")).hexdigest()
        await self.store.execute("""
            INSERT INTO google_jobs(job_id, owner_intent_id, project_id, capability_id, action_class, truth_sha, grant_id, input_hash, status, created_at_unix, updated_at_unix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PLANNED', ?, ?)
            """, (job_id, request.owner_intent_id, request.project_id, capability_id, request.action_class.value, request.truth_sha, request.grant_id, input_hash, now, now))
        return job_id

    async def job(self, job_id: str) -> dict[str, Any] | None:
        row = await self.store.fetchone("SELECT * FROM google_jobs WHERE job_id = ?", (job_id,))
        return dict(row) if row is not None else None

    async def record_artifact(self, *, job_id: str, source_tool: str, output_hash: str, project_id: str | None = None, tool_version: str | None = None, input_hashes: list[str] | None = None, trust: str = "UNTRUSTED", validation_state: str = "PENDING", parent_artifact_ids: list[str] | None = None) -> GoogleArtifactRecord:
        if trust == "OWNER_SIGNED":
            raise ValueError("provider_artifact_cannot_be_owner_signed")
        job = await self.job(job_id)
        if job is None:
            raise KeyError("google_job_not_found")
        artifact = GoogleArtifactRecord(artifact_id=str(uuid.uuid4()), job_id=job_id, project_id=project_id or job.get("project_id"), source_tool=source_tool, tool_version=tool_version, input_hashes=input_hashes or [job["input_hash"]], output_hash=output_hash, trust=trust, validation_state=validation_state, parent_artifact_ids=parent_artifact_ids or [], created_at_unix=int(time.time()))
        await self.store.execute("""
            INSERT INTO google_artifacts(artifact_id, job_id, project_id, source_provider, source_tool, tool_version, input_hashes_json, output_hash, trust, validation_state, parent_artifact_ids_json, created_at_unix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (artifact.artifact_id, artifact.job_id, artifact.project_id, artifact.source_provider, artifact.source_tool, artifact.tool_version, Store.dumps(artifact.input_hashes), artifact.output_hash, artifact.trust, artifact.validation_state, Store.dumps(artifact.parent_artifact_ids), artifact.created_at_unix))
        await self.store.execute("UPDATE google_jobs SET output_hash = ?, evidence_pointer = ?, status = 'ARTIFACT_RECORDED', updated_at_unix = ? WHERE job_id = ?", (artifact.output_hash, f"artifact:{artifact.artifact_id}", int(time.time()), job_id))
        return artifact
