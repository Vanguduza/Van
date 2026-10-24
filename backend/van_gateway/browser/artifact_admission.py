"""Exact owner file admission; an unbound target never becomes an archive.

Only operator-bound routes/identities and a separately provisioned signing key
can execute this contract. This module creates no production key or Oracle job.
"""
from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import os
import re
import ssl
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.auth.provider_transport import ProviderPrincipal, ProviderTransportBinding, require_provider_target
from van_gateway.browser.artifact_provider import ArtifactProviderBinding, ArtifactProviderError, OwnerArtifactProvider, NAMESPACE
from van_gateway.browser.action_plans import digest
from van_gateway.command.authority import AuthoritySource
from van_gateway.models import ActionClass, PrincipalType

PURPOSE = "OWNER_ARTIFACT_WRITE_ADMISSION"
PROVIDERS = {"ORACLE_OWNER_ARCHIVE", "VEKL_OWNER_CANDIDATE_INGRESS"}
SHA = r"^[0-9a-f]{64}$"


class ArtifactAdmissionError(ArtifactProviderError):
    pass


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)


class CreateProviderRequest(Strict):
    download_id: str = Field(min_length=1,max_length=128,pattern=r"^[A-Za-z0-9_-]+$")
    provider: str = Field(pattern=r"^(ORACLE_OWNER_ARCHIVE|VEKL_OWNER_CANDIDATE_INGRESS)$")
    owner_namespace: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    project_namespace: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    content_sha256: str = Field(pattern=SHA)
    byte_size: int = Field(ge=0,le=64*1024*1024)
    deadline_ms: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8,max_length=128,pattern=r"^[A-Za-z0-9_.:-]+$")


class AdmissionBody(Strict):
    signed_admission: str = Field(min_length=32,max_length=8192)


FILE_PROVIDER_ACTION = ActionDefinition(action_id="browser.file.provider.submit",action_class=ActionClass.A4,
    mutates_state=True,allowed_principals={PrincipalType.OWNER_DEVICE},verifier_type=VerifierType.STATE_PREDICATE,
    no_stale_replay=True,max_age_seconds=30,parameter_schema={"type":"object","additionalProperties":False,
    "required":["session_id","request_id","request_sha256"],"properties":{"session_id":{"type":"string"},
        "request_id":{"type":"string"},"request_sha256":{"type":"string","pattern":SHA}}})


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value):
    return base64.urlsafe_b64decode(value+"="*((-len(value))%4))


def _unique(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate_field")
        result[key] = value
    return result


def _read_operator_file(path,limit,*,private=False):
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        mode = os.fstat(fd)
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & (0o077 if private else 0o022):
            raise ArtifactAdmissionError("artifact_operator_file_permissions_invalid")
        with os.fdopen(fd,"rb",closefd=False) as handle:
            data = handle.read(limit+1)
        if len(data)>limit:
            raise ArtifactAdmissionError("artifact_operator_file_too_large")
        return data
    finally:
        os.close(fd)


class OwnerArtifactAdmissionSigner:
    def __init__(self,*,kid,private_pem,issuer="van-trading-core"):
        if not isinstance(kid,str) or not NAMESPACE.fullmatch(kid) or issuer != "van-trading-core":
            raise ArtifactAdmissionError("artifact_signer_binding_invalid")
        key = serialization.load_pem_private_key(private_pem,password=None)
        if not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1):
            raise ArtifactAdmissionError("artifact_signer_ec_p256_required")
        self.kid,self.issuer,self._key = kid,issuer,key
        self.public_sha256 = hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()

    @classmethod
    def from_config(cls,*,kid,private_key_file,issuer="van-trading-core"):
        return cls(kid=kid,private_pem=_read_operator_file(private_key_file,8192,private=True),issuer=issuer)

    def sign(self,claims):
        header={"alg":"ES256","typ":"VAN-OWNER-ARTIFACT","kid":self.kid}
        data=_b64(json.dumps(header,sort_keys=True,separators=(",",":")).encode())+"."+_b64(json.dumps(claims,sort_keys=True,separators=(",",":")).encode())
        signature=self._key.sign(data.encode(),ec.ECDSA(hashes.SHA256()))
        r,s=utils.decode_dss_signature(signature)
        return data+"."+_b64(r.to_bytes(32,"big")+s.to_bytes(32,"big"))

    def verify(self,token,*,now_ms,observation=False):
        try:
            if not isinstance(token,str) or len(token)>8192:
                raise ValueError()
            header,body,signature=token.split(".")
            envelope=json.loads(_unb64(header),object_pairs_hook=_unique)
            claims=json.loads(_unb64(body),object_pairs_hook=_unique)
            raw=_unb64(signature)
            if envelope!={"alg":"ES256","typ":"VAN-OWNER-ARTIFACT","kid":self.kid} or len(raw)!=64:
                raise ValueError()
            self._key.public_key().verify(utils.encode_dss_signature(int.from_bytes(raw[:32],"big"),int.from_bytes(raw[32:],"big")),
                (header+"."+body).encode(),ec.ECDSA(hashes.SHA256()))
            if (not isinstance(claims,dict) or claims.get("purpose")!=PURPOSE or claims.get("iss")!=self.issuer
                or claims.get("schema_version")!=1 or type(claims.get("expires_at_ms")) is not int
                or type(claims.get("issued_at_ms")) is not int or claims["issued_at_ms"]>now_ms
                or not claims["issued_at_ms"]<claims["expires_at_ms"]<=claims["issued_at_ms"]+30000):
                raise ValueError()
            if observation:
                expiry=claims.get("observation_expires_at_ms")
                if type(expiry) is not int or not claims["expires_at_ms"]<=expiry<=claims["issued_at_ms"]+300000 or now_ms>=expiry:
                    raise ValueError()
            elif now_ms>=claims["expires_at_ms"]:
                raise ValueError()
            return claims
        except Exception:
            raise ArtifactAdmissionError("artifact_admission_signature_or_expiry_invalid") from None


@dataclass(frozen=True)
class NativeArtifactSource:
    origin: str
    ca_file: str
    client_cert_file: str | None = None
    client_key_file: str | None = None

    def _tls_context(self):
        parsed=urlsplit(self.origin)
        if (parsed.scheme!="https" or not parsed.hostname or parsed.path not in {"","/"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or not self.ca_file
            or bool(self.client_cert_file)!=bool(self.client_key_file)):
            raise ArtifactAdmissionError("artifact_source_binding_invalid")
        context=ssl.create_default_context(cafile=self.ca_file)
        context.minimum_version=ssl.TLSVersion.TLSv1_3
        if self.client_cert_file:
            context.load_cert_chain(self.client_cert_file,self.client_key_file)
        return context

    def _client(self):
        context=self._tls_context()
        return httpx.AsyncClient(base_url=self.origin.rstrip("/"),verify=context,follow_redirects=False,
            trust_env=False,timeout=httpx.Timeout(30,connect=5))

    async def read(self,request,grant):
        output=bytearray()
        async with self._client() as client:
            async with client.stream("GET","/files/download/"+quote(request["download_id"],safe=""),headers={
                "Authorization":"Bearer "+grant["transfer_grant"],"X-Van-Producer-Session":grant["producer_session_id"],
                "Accept-Encoding":"identity"}) as response:
                if response.status_code!=200 or response.headers.get("Content-Encoding","identity")!="identity":
                    raise ArtifactAdmissionError("artifact_native_source_unavailable")
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    output.extend(chunk)
                    if len(output)>request["byte_size"]:
                        raise ArtifactAdmissionError("artifact_native_source_bytes_mismatch")
        if len(output)!=request["byte_size"] or hashlib.sha256(output).hexdigest()!=request["content_sha256"]:
            raise ArtifactAdmissionError("artifact_native_source_bytes_mismatch")
        return bytes(output)


def load_artifact_provider_config(path,*,disallowed_signer_public_sha256=()):
    empty={"providers":{},"source_clients":{},"signer":None,"transport_bindings":(),"configuration_sha256":None}
    if not path:
        return empty
    try:
        encoded=_read_operator_file(path,65536)
        value=json.loads(encoded,object_pairs_hook=_unique)
        if (not isinstance(value,dict) or set(value)!={"schema_version","providers","source_clients","signer"}
            or type(value["schema_version"]) is not int or value["schema_version"]!=1
            or not isinstance(value["providers"],list) or len(value["providers"])>16
            or not isinstance(value["source_clients"],dict) or len(value["source_clients"])>16):
            raise ValueError()
        providers,bindings={},[]
        for row in value["providers"]:
            binding=ArtifactProviderBinding(**row)
            binding.validate()
            if not binding.provider_principal_sha256 or binding.provider in providers:
                raise ValueError()
            provider=OwnerArtifactProvider(binding)
            provider._tls_context(binding)
            # Construct TLS contexts now; malformed configured identities fail
            # startup. No remote qualification follows from constructing one.
            providers[binding.provider]=provider
            transport_binding=ProviderTransportBinding(certificate_sha256=binding.provider_principal_sha256,
                provider_identity=binding.provider_identity,provider=binding.provider,
                owner_namespace=binding.owner_namespace,project_namespace=binding.project_namespace)
            transport_binding.validate()
            if any(row.certificate_sha256==transport_binding.certificate_sha256 for row in bindings):
                raise ValueError()
            bindings.append(transport_binding)
        sources={}
        for alias,row in value["source_clients"].items():
            if not isinstance(alias,str) or not NAMESPACE.fullmatch(alias):
                raise ValueError()
            source=NativeArtifactSource(**row)
            source._tls_context()
            sources[alias]=source
        signer_value=value["signer"]
        signer=None
        if signer_value is not None:
            if not isinstance(signer_value,dict) or set(signer_value)!={"kid","private_key_file","issuer"}:
                raise ValueError()
            signer=OwnerArtifactAdmissionSigner.from_config(**signer_value)
            if signer.public_sha256 in disallowed_signer_public_sha256:
                raise ArtifactAdmissionError("artifact_signer_must_be_separate_from_stream_signer")
        return {"providers":providers,"source_clients":sources,"signer":signer,"transport_bindings":tuple(bindings),
            "configuration_sha256":hashlib.sha256(encoded).hexdigest()}
    except Exception as error:
        if isinstance(error,ArtifactAdmissionError):
            raise
        raise ArtifactAdmissionError("artifact_provider_configuration_invalid") from None


class OwnerArtifactAdmissionService:
    PREFIX="browser_file_provider_request:"
    ADMISSION="browser_file_provider_admission:"
    IMMUTABLE=("download_id","provider","owner_namespace","project_namespace","content_sha256","byte_size","deadline_ms","idempotency_key",
        "session_id","owner_device_id","target_id","producer_session_id","artifact_producer_session_id","profile_alias","profile_lease_id",
        "profile_generation","source_mission_id","source_mission_state_at_creation","provider_identity","provider_principal_sha256",
        "capability_receipt_sha256","source_authority","automatic_truth_promotion")

    def __init__(self,*,store,sessions,producers,command_authority,providers=None,source_clients=None,signer=None,current_configuration=None):
        self.store,self.sessions,self.producers,self.command_authority=store,sessions,producers,command_authority
        self.providers,self.source_clients,self.signer=providers or {},source_clients or {},signer
        self.current_configuration=current_configuration or (lambda:False)
        self._submission=asyncio.Lock()

    def _configuration(self):
        if self.current_configuration() is not True:
            raise ArtifactAdmissionError("artifact_provider_configuration_changed_or_unbound")

    async def _qualified(self,provider):
        self._configuration()
        if self.signer is None or provider not in self.providers:
            raise ArtifactAdmissionError("artifact_provider_contract_unbound")
        implementation=self.providers[provider]
        binding=implementation._binding()
        try:
            capability=await implementation.probe()
        except (httpx.HTTPError,OSError):
            raise ArtifactAdmissionError("artifact_provider_capability_unavailable") from None
        if (not binding.provider_principal_sha256 or capability.get("admission_issuer")!=self.signer.issuer
            or capability.get("admission_signer_public_sha256")!=self.signer.public_sha256
            or capability.get("provider_transport_principal_sha256")!=binding.provider_principal_sha256
            or capability.get("atomic_one_use_admission_claim") is not True
            or capability.get("claimed_readback_expiry_field")!="observation_expires_at_ms"):
            raise ArtifactAdmissionError("artifact_provider_admission_contract_unqualified")
        return implementation,binding

    async def is_ready(self):
        if self.producers is None or self.signer is None or not self.source_clients or not self.providers:
            return False,"artifact_provider_contract_unbound"
        for provider in self.providers:
            try:
                await self._qualified(provider)
                return True,None
            except Exception:
                continue
        return False,"artifact_provider_current_capability_unqualified"

    async def catalog(self,*,session_id,owner_device_id):
        session=await self.sessions.get(session_id)
        if session is None or session.owner_device_id!=owner_device_id:
            raise ArtifactAdmissionError("artifact_session_unknown")
        source_ready=False
        try:
            async with self.store.connection() as db:
                await db.execute("BEGIN")
                await self._source(db,session_id=session_id,device_id=owner_device_id)
            source_ready=session.profile_alias in self.source_clients
        except Exception:
            pass
        rows=[]
        for provider,owner_action in (("ORACLE_OWNER_ARCHIVE","SAVE_ON_ORACLE"),("VEKL_OWNER_CANDIDATE_INGRESS","ADD_TO_VEKL")):
            binding=self.providers.get(provider).binding if provider in self.providers else None
            ready=False
            reason="TARGET_CONTRACT_UNBOUND"
            if binding:
                reason="TARGET_QUALIFICATION_REQUIRED"
                try:
                    await self._qualified(provider)
                    ready=source_ready
                    reason=None if ready else "NATIVE_SOURCE_BINDING_REQUIRED"
                except Exception:
                    pass
            rows.append({"owner_action":owner_action,"provider":provider,"contract":OwnerArtifactProvider.CONTRACT,
                "action_id":FILE_PROVIDER_ACTION.action_id,"adapter_implemented":True,"target_contract_qualified":ready,
                "executable":ready,"state":"QUALIFIED" if ready else ("CONFIGURED_UNVERIFIED" if binding else "UNAVAILABLE"),
                "reason":reason,"required_action_class":"A4","freshness_seconds":30,
                "exact_owner_project_admission_required":True,"source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE",
                "automatic_truth_promotion":False,"provider_identity":binding.provider_identity if binding else None,
                "owner_namespace":binding.owner_namespace if binding else None,"project_namespace":binding.project_namespace if binding else None,
                "provider_principal_sha256":binding.provider_principal_sha256 if binding else None,
                "capability_receipt_sha256":binding.capability_receipt_sha256 if binding else None})
        return {"session_id":session_id,"contracts":rows,"live_effects_verified":0}

    async def _one(self,db,sql,args=()):
        return await (await db.execute(sql,args)).fetchone()

    async def _request(self,db,request_id):
        row=await self._one(db,"SELECT value FROM runtime_meta WHERE key=?",(self.PREFIX+request_id,))
        if row is None:
            raise ArtifactAdmissionError("artifact_request_unknown")
        try:
            value=json.loads(row["value"],object_pairs_hook=_unique)
            if value["request_id"]!=request_id or digest({key:value[key] for key in self.IMMUTABLE})!=value["request_sha256"]:
                raise ValueError()
            return value
        except (ValueError,KeyError,TypeError):
            raise ArtifactAdmissionError("artifact_immutable_request_integrity_failed") from None

    async def _write(self,db,value):
        await db.execute("UPDATE runtime_meta SET value=?,updated_at_unix_ms=? WHERE key=?",(json.dumps(value),int(time.time()*1000),self.PREFIX+value["request_id"]))

    async def _source(self,db,*,session_id,device_id,expected=None):
        from van_gateway.browser.producer_service import ProducerError
        from van_gateway.browser.policy import BrowserPolicyError
        try:
            return await self._source_current(db,session_id=session_id,device_id=device_id,expected=expected)
        except (ProducerError,BrowserPolicyError) as error:
            reason=str(error)
            raise ArtifactAdmissionError(reason if re.fullmatch(r"[A-Za-z0-9_:-]{1,128}",reason) else "artifact_native_source_authority_refused") from None

    async def _source_current(self,db,*,session_id,device_id,expected=None):
        self._configuration()
        if self.producers is None:
            raise ArtifactAdmissionError("artifact_native_source_unbound")
        now=int(time.time()*1000)
        session,profile=await self.producers._live(db,session_id,now)
        self.sessions.broker.policy.check_profile(session["profile_alias"])
        if session["owner_device_id"]!=device_id:
            raise ArtifactAdmissionError("artifact_session_unknown")
        await self.producers._check_control(db,session,session["control_lease_id"],session["control_generation"],now,
            holder="OWNER",issued_for=device_id)
        producer=await self._one(db,"SELECT * FROM browser_stream_producers WHERE session_id=? AND revoked_at_ms IS NULL",(session_id,))
        if (producer is None or session["acked_media_epoch"]!=producer["producer_session_id"]
            or session["acked_viewport_revision"]!=session["viewport_revision"]):
            raise ArtifactAdmissionError("artifact_current_native_frame_required")
        await self.producers._stream_binding(db,producer["producer_session_id"],producer["producer_principal_sha256"],now)
        if expected and "profile_alias" in expected and (session["profile_alias"]!=expected["profile_alias"] or profile["lease_holder"]!=expected["profile_lease_id"]
            or profile["lease_generation"]!=expected["profile_generation"] or producer["producer_session_id"]!=expected["producer_session_id"]):
            raise ArtifactAdmissionError("artifact_source_authority_stale")
        if expected:
            download=await self._one(db,"SELECT * FROM browser_downloads WHERE session_id=? AND download_id=?",(session_id,expected["download_id"]))
            if (download is None or download["state"]!="COMPLETED" or download["failure_reason"]
                or download["producer_session_id"] is None or download["host_deleted_at_ms"] is not None
                or download["content_sha256"]!=expected["content_sha256"] or download["byte_size"]!=expected["byte_size"]
                or ("artifact_producer_session_id" in expected and download["producer_session_id"]!=expected["artifact_producer_session_id"])):
                raise ArtifactAdmissionError("artifact_source_record_mismatch")
        return session,profile,producer

    async def create(self,*,session_id,owner_device_id,body):
        _,binding=await self._qualified(body.provider)
        if (body.owner_namespace,body.project_namespace)!=(binding.owner_namespace,binding.project_namespace):
            raise ArtifactAdmissionError("artifact_provider_namespace_not_admitted")
        request_body=body.model_dump()
        idem="browser_file_provider_idempotency:"+digest([session_id,owner_device_id,body.idempotency_key])
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            existing=await self._one(db,"SELECT value FROM runtime_meta WHERE key=?",(idem,))
            if existing:
                previous=await self._request(db,existing["value"])
                if previous["body_sha256"]!=digest(request_body):
                    raise ArtifactAdmissionError("artifact_request_idempotency_conflict")
                return previous
            now=int(time.time()*1000)
            if not now<body.deadline_ms<=now+900000:
                raise ArtifactAdmissionError("artifact_request_deadline_invalid")
            session,profile,producer=await self._source(db,session_id=session_id,device_id=owner_device_id,expected=request_body)
            if session["profile_alias"] not in self.source_clients:
                raise ArtifactAdmissionError("artifact_native_source_unbound")
            # The bounded owner history is not a proof that an earlier write
            # settled. Fence the exact target/content across all sessions while
            # holding the same writer lock that creates a replacement draft.
            unsettled=await self._one(db,"SELECT value FROM runtime_meta AS r WHERE key LIKE ? AND json_extract(value,'$.provider')=? AND json_extract(value,'$.provider_identity')=? AND json_extract(value,'$.owner_namespace')=? AND json_extract(value,'$.project_namespace')=? AND json_extract(value,'$.content_sha256')=? AND (json_extract(value,'$.status') IN ('DRAFT','UNKNOWN') OR (json_extract(value,'$.status')='RUNNING' AND (COALESCE(json_type(value,'$.effect_receipt'),'null')!='object' OR COALESCE(json_array_length(value,'$.verification_receipts'),0)!=2 OR NOT EXISTS (SELECT 1 FROM action_executions AS e WHERE e.execution_id=json_extract(r.value,'$.execution_id') AND e.status='VERIFIED_SUCCESS') OR NOT EXISTS (SELECT 1 FROM missions AS m WHERE json_extract(m.authority_envelope_json,'$.source_command_id')=json_extract(r.value,'$.command_id') AND m.state='VERIFIED_SUCCESS')))) LIMIT 1",
                (self.PREFIX+"%",body.provider,binding.provider_identity,body.owner_namespace,body.project_namespace,body.content_sha256))
            if unsettled:
                raise ArtifactAdmissionError("artifact_target_write_unsettled")
            download=await self._one(db,"SELECT * FROM browser_downloads WHERE session_id=? AND download_id=?",(session_id,body.download_id))
            source_mission=await self._one(db,"SELECT state FROM missions WHERE mission_id=?",(session["mission_id"],)) if session["mission_id"] else None
            if session["mission_id"] and source_mission is None:
                raise ArtifactAdmissionError("artifact_source_mission_unknown")
            immutable={**request_body,"session_id":session_id,"owner_device_id":owner_device_id,
                "target_id":download["target_id"],"producer_session_id":producer["producer_session_id"],
                "artifact_producer_session_id":download["producer_session_id"],"profile_alias":session["profile_alias"],
                "profile_lease_id":profile["lease_holder"],"profile_generation":profile["lease_generation"],
                "source_mission_id":session["mission_id"],"source_mission_state_at_creation":source_mission["state"] if source_mission else None,
                "provider_identity":binding.provider_identity,
                "provider_principal_sha256":binding.provider_principal_sha256,"capability_receipt_sha256":binding.capability_receipt_sha256,
                "source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE","automatic_truth_promotion":False}
            request_id="bfile_"+uuid.uuid4().hex
            value={**immutable,"request_id":request_id,"request_sha256":digest(immutable),"body_sha256":digest(request_body),
                "status":"DRAFT","execution_id":None,"command_id":None,"admission_id":None,"effect_receipt":None,
                "effect_attempted":False,"dispatch_intent_ms":None,"failure_reason":None,"effect_observation":None,
                "verification_receipts":[],"created_at_ms":now,"approval_command":"submit browser file "+json.dumps({
                    "session_id":session_id,"request_id":request_id,"request_sha256":digest(immutable)},sort_keys=True,separators=(",",":"))}
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",(self.PREFIX+request_id,json.dumps(value),now))
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",(idem,request_id,now))
            await db.commit()
            return value

    async def get(self,*,session_id,owner_device_id,request_id):
        from van_gateway.action.models import TERMINAL_EXECUTION_STATUSES
        from van_gateway.mission.models import TERMINAL_STATES
        async with self.store.connection() as db:
            value=await self._request(db,request_id)
            if value["session_id"]!=session_id or value["owner_device_id"]!=owner_device_id:
                raise ArtifactAdmissionError("artifact_request_unknown")
            if value["status"]=="RUNNING" and await self._verified(db,value):
                value["status"]="VERIFIED_SUCCESS"
            elif value["status"]=="RUNNING":
                execution=await self._one(db,"SELECT status FROM action_executions WHERE execution_id=?",(value["execution_id"],))
                mission=await self._one(db,"SELECT state FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(value["command_id"],))
                if ((execution and execution["status"]!="VERIFIED_SUCCESS" and execution["status"] in {status.value for status in TERMINAL_EXECUTION_STATUSES})
                    or (mission and mission["state"]!="VERIFIED_SUCCESS" and mission["state"] in {state.value for state in TERMINAL_STATES})):
                    value["status"]="UNVERIFIABLE" if value.get("effect_receipt") else ("UNKNOWN" if value.get("effect_attempted") else "REFUSED")
                    value["failure_reason"]=value.get("failure_reason") or "artifact_canonical_verification_not_complete"
        return value

    async def _verified(self,db,value):
        if not value.get("effect_receipt") or len(value.get("verification_receipts",[]))!=2:
            return False
        execution=await self._one(db,"SELECT status FROM action_executions WHERE execution_id=?",(value["execution_id"],))
        mission=await self._one(db,"SELECT state FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(value["command_id"],))
        return bool(execution and execution["status"]=="VERIFIED_SUCCESS" and mission and mission["state"]=="VERIFIED_SUCCESS")

    async def list(self,*,session_id,owner_device_id):
        session=await self.sessions.get(session_id)
        if session is None or session.owner_device_id!=owner_device_id:
            raise ArtifactAdmissionError("artifact_session_unknown")
        rows=await self.store.fetchall("SELECT value FROM runtime_meta WHERE key LIKE ? AND json_extract(value,'$.session_id')=? AND json_extract(value,'$.owner_device_id')=? ORDER BY updated_at_unix_ms DESC LIMIT 100",(self.PREFIX+"%",session_id,owner_device_id))
        return {"session_id":session_id,"requests":[await self.get(session_id=session_id,owner_device_id=owner_device_id,request_id=json.loads(row["value"])["request_id"]) for row in rows]}

    async def cancel(self,*,session_id,owner_device_id,request_id):
        await self.get(session_id=session_id,owner_device_id=owner_device_id,request_id=request_id)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            value=await self._request(db,request_id)
            if value["status"]=="DRAFT":
                value["status"]="CANCELLED"
                await self._write(db,value)
            elif value["status"]=="RUNNING":
                # Dispatch may already be waiting for the target's claim. This
                # fences subsequent claims without pretending the write did
                # not happen or allowing a replacement request.
                if await self._verified(db,value):
                    value["status"]="VERIFIED_SUCCESS"
                else:
                    value["status"]="UNKNOWN" if value.get("effect_attempted") else "CANCELLED"
                    await self._write(db,value)
            await db.commit()
        return value

    async def _execution(self,db,value,*,allow_verified=False,terminal_observation=False):
        from van_gateway.capability.owner_permissions import OwnerPermissionDenied
        from van_gateway.mission.control import MissionControlError
        try:
            return await self._execution_current(db,value,allow_verified=allow_verified,terminal_observation=terminal_observation)
        except (OwnerPermissionDenied,MissionControlError) as error:
            reason=str(error)
            raise ArtifactAdmissionError(reason if re.fullmatch(r"[A-Za-z0-9_:-]{1,128}",reason) else "artifact_current_owner_authority_refused") from None

    async def _execution_current(self,db,value,*,allow_verified=False,terminal_observation=False):
        self._configuration()
        from van_gateway.capability.owner_permissions import enforce_permission_scope,recheck_permission_execution
        from van_gateway.mission.control import require_mission_dispatch
        from van_gateway.mission.models import TERMINAL_STATES
        now=int(time.time()*1000)
        execution=await self._one(db,"SELECT * FROM action_executions WHERE execution_id=? AND command_id=?",(value["execution_id"],value["command_id"]))
        row=await self._one(db,"SELECT value FROM runtime_meta WHERE key=?",("command_authority:"+value["command_id"],))
        seal=json.loads(row["value"]) if row else {}
        exact={name:value[name] for name in ("session_id","request_id","request_sha256")}
        statuses={"PREFLIGHT_PASSED","EXECUTING","SUBMITTED","VERIFYING"}|({"VERIFIED_SUCCESS"} if allow_verified else set())
        if terminal_observation and allow_verified:
            from van_gateway.action.models import TERMINAL_EXECUTION_STATUSES
            statuses|={status.value for status in TERMINAL_EXECUTION_STATUSES}
        if (not execution or execution["status"] not in statuses or execution["action_id"]!=FILE_PROVIDER_ACTION.action_id
            or execution["parameters_digest"]!=digest(exact) or execution["principal_type"]!="OWNER_DEVICE"
            or seal.get("authority_source")!="OWNER_COMMAND" or seal.get("principal_type")!="OWNER_DEVICE"
            or seal.get("effective_action_class")!="A4" or seal.get("owner_approved") is not True
            or seal.get("typed_action_id")!=FILE_PROVIDER_ACTION.action_id or seal.get("typed_parameter_constraints")!=exact
            or seal.get("device_id")!=value["owner_device_id"] or seal.get("snapshot_id")!=execution["snapshot_id"]
            or seal.get("requested_by")!=execution["requested_by"] or seal.get("expires_at_unix") is None
            or seal.get("no_stale_replay") is not True
            or (not allow_verified and (now>=seal["expires_at_unix"]*1000 or not 0<=now-seal.get("issued_at_unix",0)*1000<=30000))):
            raise ArtifactAdmissionError("artifact_exact_owner_execution_not_live")
        device=await self._one(db,"SELECT revoked_at_unix FROM devices WHERE device_id=?",(value["owner_device_id"],))
        if not device or device["revoked_at_unix"] is not None:
            raise ArtifactAdmissionError("artifact_owner_device_revoked")
        device_binding=await self._one(db,"SELECT status,revoked_at_ms FROM owner_device_bindings WHERE device_id=?",(value["owner_device_id"],))
        if device_binding and (device_binding["status"]!="ACTIVE" or device_binding["revoked_at_ms"] is not None):
            raise ArtifactAdmissionError("artifact_owner_device_binding_revoked")
        mission=await self._one(db,"SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(value["command_id"],))
        if not mission:
            raise ArtifactAdmissionError("artifact_canonical_mission_required")
        if not allow_verified:
            await require_mission_dispatch(self.store,mission["mission_id"],db=db)
        if not allow_verified and value["source_mission_id"] and value["source_mission_id"]!=mission["mission_id"]:
            previous=await self._one(db,"SELECT state FROM missions WHERE mission_id=?",(value["source_mission_id"],))
            terminal={state.value for state in TERMINAL_STATES}
            original=value.get("source_mission_state_at_creation")
            if original in terminal:
                if not previous or previous["state"]!=original:
                    raise ArtifactAdmissionError("artifact_source_mission_state_changed")
            else:
                await require_mission_dispatch(self.store,value["source_mission_id"],db=db)
        if not terminal_observation:
            await recheck_permission_execution(self.store,value["execution_id"],db=db)
            await enforce_permission_scope(self.store,action_id=FILE_PROVIDER_ACTION.action_id,parameters=exact,
                execution_id=value["execution_id"],claim=False,db=db)
        return seal

    async def submit(self,execution,parameters):
        # One bounded64MiB transfer at a time per runtime. Waiting silently
        # would spend the owner's short approval window before dispatch.
        if self._submission.locked():
            raise ArtifactAdmissionError("artifact_transfer_busy")
        async with self._submission:
            return await self._submit(execution,parameters)

    async def _submit(self,execution,parameters):
        record,age=await self.command_authority.authorize_action(command_id=execution.command_id,action=FILE_PROVIDER_ACTION,
            principal_type=execution.principal_type,requested_by=execution.requested_by,snapshot_id=execution.snapshot_id,
            turn_id=execution.turn_id,parameters=parameters)
        if (age>30 or record.authority_source is not AuthoritySource.OWNER_COMMAND or record.principal_type is not PrincipalType.OWNER_DEVICE
            or record.effective_action_class is not ActionClass.A4 or not record.owner_approved or set(parameters)!={"session_id","request_id","request_sha256"}):
            raise ArtifactAdmissionError("artifact_fresh_exact_owner_a4_required")
        value=await self.get(session_id=parameters["session_id"],owner_device_id=record.device_id,request_id=parameters["request_id"])
        if value["request_sha256"]!=parameters["request_sha256"]:
            raise ArtifactAdmissionError("artifact_request_digest_mismatch")
        if value["status"]!="DRAFT":
            return {**value,"success":False,"effect_observed":False}
        implementation,binding=await self._qualified(value["provider"])
        if (binding.provider_identity!=value["provider_identity"] or binding.capability_receipt_sha256!=value["capability_receipt_sha256"]
            or binding.provider_principal_sha256!=value["provider_principal_sha256"]):
            raise ArtifactAdmissionError("artifact_provider_binding_changed")
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            value=await self._request(db,value["request_id"])
            if value["status"]!="DRAFT" or value["deadline_ms"]<=int(time.time()*1000):
                raise ArtifactAdmissionError("artifact_request_already_dispatched_or_expired")
            value.update(status="RUNNING",execution_id=execution.execution_id,command_id=execution.command_id)
            await self._execution(db,value)
            await self._source(db,session_id=value["session_id"],device_id=value["owner_device_id"],expected=value)
            await self._write(db,value)
            await db.commit()
        try:
            grant=await self.producers.issue_transfer_grant(session_id=value["session_id"],owner_device_id=value["owner_device_id"],
                operation="download",target_id=value["target_id"],download_id=value["download_id"])
            content=await self.source_clients[value["profile_alias"]].read(value,grant)
            if not isinstance(content,bytes) or len(content)!=value["byte_size"] or hashlib.sha256(content).hexdigest()!=value["content_sha256"]:
                raise ArtifactAdmissionError("artifact_native_source_bytes_mismatch")
            consumed=await self.store.fetchone("SELECT * FROM browser_owner_transfer_grants WHERE transfer_id=?",(grant["transfer_id"],))
            if (not consumed or consumed["consumed_at_ms"] is None or consumed["resource_id"]!=value["download_id"]
                or consumed["session_id"]!=value["session_id"] or consumed["producer_session_id"]!=value["producer_session_id"]):
                raise ArtifactAdmissionError("artifact_native_one_use_read_not_observed")
            admission_id="bfa_"+uuid.uuid4().hex
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                current=await self._request(db,value["request_id"])
                if current["status"]!="RUNNING":
                    raise ArtifactAdmissionError("artifact_request_cancelled")
                seal=await self._execution(db,current)
                await self._source(db,session_id=value["session_id"],device_id=value["owner_device_id"],expected=value)
                now=int(time.time()*1000)
                claims={"schema_version":1,"purpose":PURPOSE,"iss":self.signer.issuer,"aud":binding.provider_identity,
                    "jti":admission_id,"issued_at_ms":now,"expires_at_ms":min(now+30000,value["deadline_ms"],seal["expires_at_unix"]*1000,(seal["issued_at_unix"]+30)*1000),
                    "observation_expires_at_ms":now+300000,
                    **{name:value[name] for name in ("request_id","request_sha256","session_id","download_id","producer_session_id","content_sha256","byte_size","provider","owner_namespace","project_namespace","provider_identity","provider_principal_sha256","command_id","execution_id","owner_device_id")},
                    "requested_by":seal["requested_by"],"snapshot_id":seal["snapshot_id"]}
                if claims["expires_at_ms"]<=now:
                    raise ArtifactAdmissionError("artifact_owner_approval_expired_before_write")
                await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",(self.ADMISSION+admission_id,json.dumps({"claims":claims,"claimed_at_ms":None,"claim_id":None}),now))
                current.update(admission_id=admission_id,source_readback={"content_sha256":hashlib.sha256(content).hexdigest(),
                    "byte_size":len(content),"transfer_id":grant["transfer_id"],"observer":"VAN_NATIVE_PERSISTED_BYTES_READBACK"})
                await self._write(db,current)
                await db.commit()
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                current=await self._request(db,value["request_id"])
                if current["status"]!="RUNNING":
                    raise ArtifactAdmissionError("artifact_request_cancelled")
                await self._execution(db,current)
                await self._source(db,session_id=current["session_id"],device_id=current["owner_device_id"],expected=current)
                current.update(effect_attempted=True,dispatch_intent_ms=int(time.time()*1000))
                await self._write(db,current)
                await db.commit()
            receipt=await implementation.submit(content=content,content_sha256=value["content_sha256"],admission_id=admission_id,
                signed_admission=self.signer.sign(claims),idempotency_key=value["request_id"])
            await self._validate_receipt(current,receipt)
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                latest=await self._request(db,value["request_id"])
                latest["effect_receipt"]=receipt
                await self._write(db,latest)
                await db.commit()
            return {**latest,"success":True,"effect_observed":True,"status":"OBSERVED"}
        except (Exception,asyncio.CancelledError) as error:
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                latest=await self._request(db,value["request_id"])
                if latest["status"]=="RUNNING":
                    latest["status"]="UNKNOWN" if latest.get("effect_attempted") else "REFUSED"
                    reason=str(error)
                    latest["failure_reason"]=reason if isinstance(error,ArtifactProviderError) and re.fullmatch(r"[A-Za-z0-9_:-]{1,128}",reason) else "artifact_source_or_admission_refused"
                    await self._write(db,latest)
                await db.commit()
            if not isinstance(error,Exception):
                raise
            return {**latest,"success":False,"effect_observed":False}

    async def _validate_receipt(self,value,receipt):
        row=await self.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(self.ADMISSION+value["admission_id"],))
        admission=json.loads(row["value"]) if row else {}
        if (not admission.get("claimed_at_ms") or not admission.get("claim_id") or receipt.get("admission_claim_id")!=admission["claim_id"]
            or receipt.get("source_authority")!="UNTRUSTED_OWNER_FILE_EVIDENCE"
            or receipt.get("independent_content_readback",{}).get("content_sha256")!=value["content_sha256"]
            or receipt.get("independent_content_readback",{}).get("byte_size")!=value["byte_size"]):
            raise ArtifactAdmissionError("artifact_actual_claim_and_readback_required")

    async def verify(self,execution,parameters):
        record=await self.command_authority.get(execution.command_id)
        if record is None:
            raise ArtifactAdmissionError("artifact_owner_authority_unknown")
        value=await self.get(session_id=parameters["session_id"],owner_device_id=record.device_id,request_id=parameters["request_id"])
        if value["execution_id"]!=execution.execution_id or value["request_sha256"]!=parameters["request_sha256"]:
            raise ArtifactAdmissionError("artifact_verification_binding_mismatch")
        if not value["effect_receipt"] or value["status"] not in {"RUNNING","VERIFIED_SUCCESS"}:
            return {"success":False,"request_id":value["request_id"],"request_sha256":value["request_sha256"],"status":value["status"]}
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            await self._execution(db,value,allow_verified=True)
        implementation,_=await self._qualified(value["provider"])
        row=await self.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(self.ADMISSION+value["admission_id"],))
        claims=json.loads(row["value"])["claims"]
        self.signer.verify(self.signer.sign(claims),now_ms=int(time.time()*1000),observation=True)
        receipt=await implementation.readback(content_sha256=value["content_sha256"],byte_size=value["byte_size"],
            admission_id=value["admission_id"],signed_admission=self.signer.sign(claims))
        await self._validate_receipt(value,receipt)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            latest=await self._request(db,value["request_id"])
            if latest["status"] not in {"RUNNING","VERIFIED_SUCCESS"}:
                raise ArtifactAdmissionError("artifact_request_cancelled")
            latest["verification_receipts"].append(receipt)
            latest["verification_receipts"]=latest["verification_receipts"][-2:]
            await self._write(db,latest)
            await db.commit()
        return {"success":True,"request_id":value["request_id"],"request_sha256":value["request_sha256"],
            "independent_readback":receipt,"evidence_pointer":"browser-file-provider://"+value["request_id"]+"/"+digest(receipt)}

    async def introspect(self,*,admission_id,signed_admission,principal,claim=False):
        if self.signer is None:
            raise ArtifactAdmissionError("artifact_admission_signer_unbound")
        now=int(time.time()*1000)
        claims=self.signer.verify(signed_admission,now_ms=now,observation=not claim)
        if claims.get("jti")!=admission_id:
            raise ArtifactAdmissionError("artifact_admission_path_mismatch")
        require_provider_target(principal,provider=claims["provider"],provider_identity=claims["provider_identity"],
            owner_namespace=claims["owner_namespace"],project_namespace=claims["project_namespace"])
        if principal.certificate_sha256!=claims["provider_principal_sha256"]:
            raise ArtifactAdmissionError("artifact_admission_provider_pin_mismatch")
        implementation,binding=await self._qualified(claims["provider"])
        if binding.provider_principal_sha256!=principal.certificate_sha256:
            raise ArtifactAdmissionError("artifact_admission_provider_pin_changed")
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE" if claim else "BEGIN")
            row=await self._one(db,"SELECT value FROM runtime_meta WHERE key=?",(self.ADMISSION+admission_id,))
            admission=json.loads(row["value"]) if row else {}
            if admission.get("claims")!=claims:
                raise ArtifactAdmissionError("artifact_admission_unknown_or_changed")
            value=await self._request(db,claims["request_id"])
            allowed={"RUNNING"} if claim else {"RUNNING","UNKNOWN"}
            if value["status"] not in allowed or value["admission_id"]!=admission_id or value.get("effect_attempted") is not True:
                raise ArtifactAdmissionError("artifact_admission_request_not_live")
            observation=not claim and admission.get("claimed_at_ms") is not None
            self.signer.verify(signed_admission,now_ms=int(time.time()*1000),observation=observation)
            await self._execution(db,value,allow_verified=observation,terminal_observation=observation)
            if claim:
                if admission.get("claimed_at_ms") is not None:
                    raise ArtifactAdmissionError("artifact_admission_already_claimed")
                await self._source(db,session_id=value["session_id"],device_id=value["owner_device_id"],expected=value)
                admission.update(claimed_at_ms=now,claim_id="bfclaim_"+uuid.uuid4().hex)
                await db.execute("UPDATE runtime_meta SET value=?,updated_at_unix_ms=? WHERE key=?",(json.dumps(admission),now,self.ADMISSION+admission_id))
            await db.commit()
        return {"admitted":True,"claimed":claim,"admission_id":admission_id,"admission_claim_id":admission.get("claim_id"),
            "request_id":claims["request_id"],"request_sha256":claims["request_sha256"],"provider":claims["provider"],
            "owner_namespace":claims["owner_namespace"],"project_namespace":claims["project_namespace"],
            "content_sha256":claims["content_sha256"],"byte_size":claims["byte_size"],"expires_at_ms":claims["expires_at_ms"]}

    async def observe(self,*,session_id,owner_device_id,request_id):
        """Read an already claimed effect, without renewing write authority.

        This observation cannot rescue a terminal command or release its write
        fence. A missing receipt is uncertainty, never proof of absence.
        """
        value=await self.get(session_id=session_id,owner_device_id=owner_device_id,request_id=request_id)
        observation={"status":"STILL_UNKNOWN","receipt":None,"reason":None,"observed_at_ms":int(time.time()*1000),
            "automatic_replacement_authorized":False,"governed_reconciliation_required":True}
        try:
            row=await self.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(self.ADMISSION+(value.get("admission_id") or ""),))
            admission=json.loads(row["value"]) if row else {}
            if value.get("effect_attempted") is not True or admission.get("claimed_at_ms") is None:
                raise ArtifactAdmissionError("artifact_claimed_observation_scope_required")
            claims=admission["claims"]
            token=self.signer.sign(claims) if self.signer else ""
            if not self.signer:
                raise ArtifactAdmissionError("artifact_admission_signer_unbound")
            self.signer.verify(token,now_ms=int(time.time()*1000),observation=True)
            async with self.store.connection() as db:
                await db.execute("BEGIN")
                await self._execution(db,value,allow_verified=True,terminal_observation=True)
            implementation,_=await self._qualified(value["provider"])
            receipt=await implementation.readback(content_sha256=value["content_sha256"],byte_size=value["byte_size"],
                admission_id=value["admission_id"],signed_admission=token)
            await self._validate_receipt(value,receipt)
            observation.update(status="OBSERVED_EXTERNAL_EFFECT",receipt=receipt,governed_reconciliation_required=value["status"]!="VERIFIED_SUCCESS")
        except Exception as error:
            reason=str(error)
            observation["reason"]=reason if isinstance(error,ArtifactProviderError) and re.fullmatch(r"[A-Za-z0-9_:-]{1,128}",reason) else "artifact_external_observation_unavailable"
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            current=await self._request(db,request_id)
            current["effect_observation"]=observation
            await self._write(db,current)
            await db.commit()
        fresh=await self.get(session_id=session_id,owner_device_id=owner_device_id,request_id=request_id)
        return {"session_id":session_id,"request_id":request_id,"request_sha256":value["request_sha256"],
            "canonical_status":fresh["status"],"effect_observation":observation}


def build_artifact_admission_router(service):
    router=APIRouter(prefix="/v1/browser/interactive-sessions",tags=["owner-file-admissions"])
    def owner(request):
        device=getattr(request.state,"van_device_id",None)
        if not device:
            raise HTTPException(401,"device_proof_required")
        return device
    async def guarded(operation):
        try:
            return await operation
        except ArtifactProviderError as error:
            raise HTTPException(409,str(error)) from None
    @router.post("/{session_id}/file-provider-requests")
    async def create(request:Request,session_id:str,body:CreateProviderRequest):
        return await guarded(service.create(session_id=session_id,owner_device_id=owner(request),body=body))
    @router.get("/{session_id}/file-provider-requests")
    async def list_requests(request:Request,session_id:str):
        return await guarded(service.list(session_id=session_id,owner_device_id=owner(request)))
    @router.get("/{session_id}/file-provider-requests/{request_id}")
    async def get(request:Request,session_id:str,request_id:str):
        return await guarded(service.get(session_id=session_id,owner_device_id=owner(request),request_id=request_id))
    @router.post("/{session_id}/file-provider-requests/{request_id}/cancel")
    async def cancel(request:Request,session_id:str,request_id:str):
        return await guarded(service.cancel(session_id=session_id,owner_device_id=owner(request),request_id=request_id))
    @router.get("/{session_id}/file-provider-requests/{request_id}/observation")
    async def observation(request:Request,session_id:str,request_id:str):
        return await guarded(service.observe(session_id=session_id,owner_device_id=owner(request),request_id=request_id))
    return router


def build_artifact_provider_claim_router(service,authenticate_provider):
    router=APIRouter(prefix="/v1/browser/artifact-provider/admissions",tags=["private-artifact-admission"])
    async def admitted(request,admission_id,body,claim):
        principal=await authenticate_provider(request)
        try:
            return await service.introspect(admission_id=admission_id,signed_admission=body.signed_admission,principal=principal,claim=claim)
        except ArtifactProviderError as error:
            raise HTTPException(403,str(error)) from None
    @router.post("/{admission_id}/introspect")
    async def introspect(request:Request,admission_id:str,body:AdmissionBody):
        return await admitted(request,admission_id,body,False)
    @router.post("/{admission_id}/claim")
    async def claim(request:Request,admission_id:str,body:AdmissionBody):
        return await admitted(request,admission_id,body,True)
    return router
