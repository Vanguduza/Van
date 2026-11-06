"""Fail-closed adapter for the proposed owner-artifact provider contract.

This is not a claim that Oracle/VEKL exposes this API. Target implementation,
Oracle job admission and host qualification remain required external bindings.
No caller can turn a local file copy into an Oracle or VEKL receipt.
"""
from __future__ import annotations
import hashlib
import json
import re
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Request, HTTPException

from van_gateway.browser.action_plans import digest

NAMESPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ArtifactProviderError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactProviderBinding:
    provider: str  # ORACLE_OWNER_ARCHIVE or VEKL_OWNER_CANDIDATE_INGRESS
    origin: str
    ca_file: str
    client_cert_file: str
    client_key_file: str
    provider_identity: str
    capability_receipt_sha256: str
    owner_namespace: str
    project_namespace: str
    provider_principal_sha256: str | None = None

    def validate(self):
        parsed = urlsplit(self.origin)
        if (self.provider not in {"ORACLE_OWNER_ARCHIVE", "VEKL_OWNER_CANDIDATE_INGRESS"}
            or parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not NAMESPACE.fullmatch(self.owner_namespace) or not NAMESPACE.fullmatch(self.project_namespace)
            or not re.fullmatch(r"[0-9a-f]{64}", self.capability_receipt_sha256)
            or not isinstance(self.provider_identity,str) or not NAMESPACE.fullmatch(self.provider_identity)
            or not all((self.ca_file, self.client_cert_file, self.client_key_file))
            or (self.provider_principal_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}",self.provider_principal_sha256))):
            raise ArtifactProviderError("owner_artifact_provider_binding_invalid")


class OwnerArtifactProvider:
    """Exactly one bounded write and independent GET; uncertain writes never retry."""
    CONTRACT = "VAN_OWNER_ARTIFACT_ADMISSION_V1"

    def __init__(self, binding=None, *, transport=None):
        self.binding, self.transport = binding, transport

    def _binding(self):
        if self.binding is None:
            raise ArtifactProviderError("owner_artifact_provider_contract_unbound")
        self.binding.validate()
        return self.binding

    def _tls_context(self, binding):
        context = ssl.create_default_context(cafile=binding.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(binding.client_cert_file, binding.client_key_file)
        return context

    def _client(self, binding):
        context = self._tls_context(binding)
        return httpx.AsyncClient(base_url=binding.origin.rstrip("/"), verify=context,
            timeout=httpx.Timeout(30, connect=5), follow_redirects=False, trust_env=False,
            transport=self.transport)

    def _receipt(self, value, *, sha, size, admission_id):
        binding = self._binding()
        exact = {"contract": self.CONTRACT, "provider": binding.provider,
            "provider_identity": binding.provider_identity, "owner_namespace": binding.owner_namespace,
            "project_namespace": binding.project_namespace, "content_sha256": sha,
            "byte_size": size, "admission_id": admission_id, "executed_content": False,
            "project_truth_promoted": False, "owner_truth_promoted": False,
            "source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE"}
        if not isinstance(value, dict) or any(value.get(k) != v or type(value.get(k)) is not type(v) for k,v in exact.items()):
            raise ArtifactProviderError("owner_artifact_provider_readback_mismatch")
        if not isinstance(value.get("receipt_id"), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}",value["receipt_id"]):
            raise ArtifactProviderError("owner_artifact_provider_receipt_missing")
        required_status = "ARCHIVED" if binding.provider == "ORACLE_OWNER_ARCHIVE" else "CANDIDATE_RECORDED"
        if value.get("status") != required_status:
            raise ArtifactProviderError("owner_artifact_provider_admission_not_observed")
        if binding.provider == "VEKL_OWNER_CANDIDATE_INGRESS" and (not isinstance(value.get("canonical_candidate_id"),str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}",value["canonical_candidate_id"])):
            raise ArtifactProviderError("vekl_canonical_candidate_not_observed")
        # External metadata cannot smuggle credentials or unbounded page
        # content into owner receipts. Only contract evidence is projected.
        allowed=set(exact)|{"receipt_id","status","admission_claim_id","canonical_candidate_id"}
        return {key:item for key,item in value.items() if key in allowed}

    async def _json(self,client,path,*,limit,headers=None):
        output=bytearray()
        async with client.stream("GET",path,headers={"Accept-Encoding":"identity",**(headers or {})}) as response:
            if response.status_code!=200 or response.headers.get("Content-Encoding","identity")!="identity":
                raise ArtifactProviderError("owner_artifact_provider_response_unavailable")
            async for chunk in response.aiter_bytes(chunk_size=65536):
                output.extend(chunk)
                if len(output)>limit:
                    raise ArtifactProviderError("owner_artifact_provider_response_too_large")
        def unique(pairs):
            value={}
            for key,item in pairs:
                if key in value:
                    raise ValueError()
                value[key]=item
            return value
        def reject_constant(_):
            raise ValueError()
        try:
            return json.loads(output,object_pairs_hook=unique,parse_constant=reject_constant)
        except (ValueError,UnicodeError):
            raise ArtifactProviderError("owner_artifact_provider_response_invalid") from None

    async def _capability(self, client):
        binding = self._binding()
        capability = await self._json(client,"/v1/owner-artifacts/capabilities",limit=32768)
        if (not isinstance(capability,dict) or digest(capability) != binding.capability_receipt_sha256
            or capability.get("contract") != self.CONTRACT or capability.get("provider") != binding.provider
            or capability.get("provider_identity") != binding.provider_identity
            or capability.get("current_admission_introspection") is not True
            or capability.get("namespace_admissions") != [{"owner_namespace":binding.owner_namespace,"project_namespace":binding.project_namespace}]
            or (binding.provider == "VEKL_OWNER_CANDIDATE_INGRESS" and (not isinstance(capability.get("oracle_instruction_job_id"),str)
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}",capability["oracle_instruction_job_id"])) )):
            raise ArtifactProviderError("owner_artifact_provider_capability_mismatch")
        return capability

    async def probe(self):
        async with self._client(self._binding()) as client:
            return await self._capability(client)

    async def _readback(self, client, *, content_sha256, byte_size, admission_id, signed_admission):
        binding = self._binding()
        path = f"/v1/owner-artifacts/{binding.owner_namespace}/{binding.project_namespace}/{content_sha256}"
        headers = {"Authorization":"Bearer "+signed_admission,"X-Van-Admission-ID":admission_id}
        value = await self._json(client,path,limit=65536,headers=headers)
        receipt = self._receipt(value,sha=content_sha256,size=byte_size,admission_id=admission_id)
        observed_hash, observed_size = hashlib.sha256(), 0
        async with client.stream("GET",path+"/content",headers={**headers,"Accept":"application/octet-stream","Accept-Encoding":"identity"}) as target_bytes:
            if (target_bytes.status_code != 200 or target_bytes.headers.get("Content-Type","").split(";",1)[0] != "application/octet-stream"
                or target_bytes.headers.get("Content-Encoding","identity") != "identity"):
                raise ArtifactProviderError("owner_artifact_provider_content_unavailable")
            async for chunk in target_bytes.aiter_bytes(chunk_size=65536):
                observed_size += len(chunk)
                if observed_size > byte_size:
                    raise ArtifactProviderError("owner_artifact_provider_content_mismatch")
                observed_hash.update(chunk)
        if observed_size != byte_size or observed_hash.hexdigest() != content_sha256:
            raise ArtifactProviderError("owner_artifact_provider_content_mismatch")
        return {**receipt,"independent_content_readback":{"content_sha256":observed_hash.hexdigest(),
            "byte_size":observed_size,"observer":"VAN_BOUNDED_PERSISTED_BYTES_READBACK"}}

    async def readback(self, *, content_sha256, byte_size, admission_id, signed_admission):
        async with self._client(self._binding()) as client:
            await self._capability(client)
            return await self._readback(client,content_sha256=content_sha256,byte_size=byte_size,
                admission_id=admission_id,signed_admission=signed_admission)

    async def submit(self, *, content: bytes, content_sha256: str, admission_id: str,
                     signed_admission: str, idempotency_key: str):
        """Admission is a short-lived core-signed exact A4 token, never a body boolean.

        The target must introspect it against current device/mission/execution
        authority. This adapter cannot mint it or certify target introspection.
        """
        binding = self._binding()
        if (not isinstance(content, bytes) or len(content) > 64*1024*1024
            or hashlib.sha256(content).hexdigest() != content_sha256
            or not NAMESPACE.fullmatch(admission_id) or not NAMESPACE.fullmatch(idempotency_key)
            or not isinstance(signed_admission, str) or not 32 <= len(signed_admission) <= 8192):
            raise ArtifactProviderError("owner_artifact_admission_invalid")
        path = f"/v1/owner-artifacts/{binding.owner_namespace}/{binding.project_namespace}/{content_sha256}"
        async with self._client(binding) as client:
            await self._capability(client)
            try:
                async with client.stream("PUT",path, content=content, headers={
                    "Content-Type": "application/octet-stream", "X-Van-Content-SHA256": content_sha256,
                    "X-Van-Admission-ID": admission_id, "Authorization": "Bearer " + signed_admission,
                    "Idempotency-Key": idempotency_key}) as written:
                    status=written.status_code
            except httpx.TransportError as exc:
                raise ArtifactProviderError("owner_artifact_write_outcome_unknown") from exc
            if status not in {200, 201}:
                raise ArtifactProviderError("owner_artifact_provider_write_refused")
            return await self._readback(client,content_sha256=content_sha256,byte_size=len(content),
                admission_id=admission_id,signed_admission=signed_admission)


def build_artifact_provider_router(*, sessions, providers=None, admissions=None):
    """Owner-visible preparation state; configured is never a live qualification."""
    router = APIRouter(prefix="/v1/browser/interactive-sessions", tags=["owner-file-providers"])
    providers = providers or {}

    @router.get("/{session_id}/file-provider-contracts")
    async def contracts(request: Request, session_id: str):
        device = getattr(request.state,"van_device_id",None)
        if not device:
            raise HTTPException(401,"device_proof_required")
        session = await sessions.get(session_id)
        if session is None or session.owner_device_id != device:
            raise HTTPException(404,"interactive_session_unknown")
        if admissions is not None:
            return await admissions.catalog(session_id=session_id,owner_device_id=device)
        result = []
        for provider, action in (("ORACLE_OWNER_ARCHIVE","SAVE_ON_ORACLE"),
                                 ("VEKL_OWNER_CANDIDATE_INGRESS","ADD_TO_VEKL")):
            implementation = providers.get(provider)
            configured = implementation is not None and implementation.binding is not None
            result.append({"owner_action":action,"provider":provider,"contract":OwnerArtifactProvider.CONTRACT,
                "adapter_implemented":True,"target_contract_qualified":False,"executable":False,
                "state":"CONFIGURED_UNVERIFIED" if configured else "UNAVAILABLE",
                "reason":"TARGET_QUALIFICATION_REQUIRED" if configured else "TARGET_CONTRACT_UNBOUND",
                "required_action_class":"A4","exact_owner_project_admission_required":True,
                "source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE","automatic_truth_promotion":False,
                "required_target_prerequisites":["governed_target_implementation","current_signed_admission_introspection",
                    "approved_owner_project_namespace","private_mtls_identity","independent_persisted_bytes_readback"]})
        return {"session_id":session_id,"contracts":result,"live_effects_verified":0}
    return router
