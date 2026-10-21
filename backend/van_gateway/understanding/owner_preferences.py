"""Explicit owner declarations, kept separate from inferred traits and authority.

These local setters establish what the owner meant or asked for. They cannot
mint execution grants or certify psychological claims, task evidence, or VAN's
ability. A hardware-bound request and current logical session are required even
on deployments that still allow legacy unbound-device mutations elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import uuid
from typing import Annotated, Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from van_gateway.storage.db import Store


BoundedText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4000)]
ExampleText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]
ScopeText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
PROJECT = re.compile(r"[a-z][a-z0-9_-]{0,63}")
DOMAIN = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*){0,7}")
PREFIX = "owner_memory_declaration:"


def _text(value: str, *, multiline: bool = True) -> str:
    value = value.strip()
    if not value or any(unicodedata.category(c).startswith("C") and
                        not (multiline and c in "\n\t") for c in value):
        raise ValueError("owner_memory_text_invalid")
    return value


def normalize_term(value: str) -> str:
    return " ".join(_text(value, multiline=False).lower().split())


def normalize_project(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if not PROJECT.fullmatch(value):
        raise ValueError("owner_memory_project_invalid")
    return value


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not DOMAIN.fullmatch(value):
        raise ValueError("owner_memory_domain_invalid")
    return value


class OwnerDeclarationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    van_session_id: ScopeText
    session_epoch: int = Field(strict=True, ge=1, le=2_147_483_647)

    @field_validator("van_session_id")
    @classmethod
    def session_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("owner_memory_session_invalid")
        return value


class VocabularyDefinitionBody(OwnerDeclarationBody):
    term: ScopeText
    owner_meaning: BoundedText
    system_operationalization: BoundedText
    examples: list[ExampleText] = Field(default_factory=list, max_length=16)
    anti_examples: list[ExampleText] = Field(default_factory=list, max_length=16)
    project_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64)] | None = None

    @field_validator("term")
    @classmethod
    def term_normalized(cls, value: str) -> str:
        return normalize_term(value)

    @field_validator("project_id")
    @classmethod
    def project_normalized(cls, value: str | None) -> str | None:
        return normalize_project(value)

    @field_validator("owner_meaning", "system_operationalization")
    @classmethod
    def text_normalized(cls, value: str) -> str:
        return _text(value)

    @field_validator("examples", "anti_examples")
    @classmethod
    def examples_normalized(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_text(v) for v in values))

    def content(self) -> dict[str, Any]:
        return self.model_dump(exclude={"van_session_id", "session_epoch"})


class ComplementPreferenceBody(OwnerDeclarationBody):
    domain: ScopeText
    preferred_collaboration_pattern: BoundedText

    @field_validator("domain")
    @classmethod
    def domain_normalized(cls, value: str) -> str:
        return normalize_domain(value)

    @field_validator("preferred_collaboration_pattern")
    @classmethod
    def pattern_normalized(cls, value: str) -> str:
        return _text(value)

    def content(self) -> dict[str, str]:
        return self.model_dump(exclude={"van_session_id", "session_epoch"})


def _digest(content: dict) -> str:
    return hashlib.sha256(Store.dumps(content).encode()).hexdigest()


def _key(kind: str, content: dict) -> str:
    scope = {"term": content["term"], "project_id": content["project_id"]} if kind == "vocabulary" else {"domain": content["domain"]}
    return PREFIX + kind + ":" + _digest(scope)


class OwnerDeclarationStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def _owner(self, db: Any, device_id: str) -> None:
        device = await (await db.execute("SELECT revoked_at_unix FROM devices WHERE device_id=?", (device_id,))).fetchone()
        binding = await (await db.execute("SELECT device_id FROM owner_device_bindings WHERE owner_principal_id='owner' AND status='ACTIVE'", ())).fetchone()
        if not device or device["revoked_at_unix"] is not None:
            raise HTTPException(403, "owner_device_revoked_or_unknown")
        if not binding or binding["device_id"] != device_id:
            raise HTTPException(403, "owner_bound_device_required")

    async def require_read(self, request: Request) -> str:
        device_id = str(getattr(request.state, "van_device_id", ""))
        if not device_id:
            raise HTTPException(401, "owner_device_required")
        async with self.store.connection() as db:
            await self._owner(db, device_id)
        return device_id

    async def _write_context(self, db: Any, request: Request, body: OwnerDeclarationBody) -> str:
        device_id = str(getattr(request.state, "van_device_id", ""))
        if not device_id or not getattr(request.state, "van_device_proved", False):
            raise HTTPException(403, "owner_bound_device_proof_required")
        await self._owner(db, device_id)
        session = await (await db.execute("SELECT device_id,state,session_epoch,principal_type FROM van_sessions WHERE van_session_id=?", (body.van_session_id,))).fetchone()
        if not session or session["device_id"] != device_id or session["principal_type"] != "OWNER_DEVICE":
            raise HTTPException(403, "owner_memory_session_device_mismatch")
        if session["session_epoch"] != body.session_epoch:
            raise HTTPException(409, "owner_memory_session_epoch_stale")
        if session["state"] != "ACTIVE":
            raise HTTPException(409, "owner_memory_session_not_active")
        return device_id

    async def save(self, kind: str, body: OwnerDeclarationBody, request: Request) -> dict:
        content = body.content()
        now = int(time.time() * 1000)
        write_id = "omd_" + uuid.uuid4().hex
        ref = "owner-memory://" + write_id
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                device_id = await self._write_context(db, request, body)
                witness = {"state": "OWNER_CONFIRMED", "source": "OWNER_AUTHORED", "write_id": write_id,
                    "evidence_ref": ref, "device_id": device_id, "van_session_id": body.van_session_id,
                    "session_epoch": body.session_epoch, "recorded_at_ms": now, "content_sha256": _digest(content)}
                if kind == "vocabulary":
                    await db.execute("INSERT INTO shared_vocabulary(term,project_id,owner_meaning,system_operationalization,examples_json,anti_examples_json,confidence,evidence_refs_json,created_at_ms,updated_at_ms) VALUES(?,?,?,?,?,?,1.0,?,?,?) ON CONFLICT(term,project_id) DO UPDATE SET owner_meaning=excluded.owner_meaning,system_operationalization=excluded.system_operationalization,examples_json=excluded.examples_json,anti_examples_json=excluded.anti_examples_json,confidence=excluded.confidence,evidence_refs_json=excluded.evidence_refs_json,updated_at_ms=excluded.updated_at_ms",
                        (content["term"], content["project_id"] or "", content["owner_meaning"], content["system_operationalization"], Store.dumps(content["examples"]), Store.dumps(content["anti_examples"]), Store.dumps([ref]), now, now))
                else:
                    # Owner collaboration preferences do not overwrite inferred task
                    # strengths, vulnerabilities, or their independent confidence.
                    await db.execute("INSERT INTO cognitive_complement_map(entry_id,domain,preferred_collaboration_pattern,confidence,evidence_refs_json,created_at_ms,updated_at_ms) VALUES(?,?,?,0.0,?,?,?) ON CONFLICT(domain) DO UPDATE SET preferred_collaboration_pattern=excluded.preferred_collaboration_pattern,updated_at_ms=excluded.updated_at_ms",
                        ("ccm_" + uuid.uuid4().hex, content["domain"], content["preferred_collaboration_pattern"], Store.dumps([]), now, now))
                await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms", (_key(kind, content), Store.dumps(witness), now))
                await db.commit()
            except BaseException:
                await db.rollback()
                raise
        # A new connection observes the committed target rather than returning the
        # request or upsert's newly generated but discarded conflict identifier.
        observed = await self.exact(kind, content)
        if observed["provenance"].get("write_id") != write_id:
            raise HTTPException(409, "owner_memory_write_superseded")
        observed["status"] = "SAVED"
        return observed

    async def _view(self, db: Any, kind: str, row: Any) -> dict:
        if kind == "vocabulary":
            content = {"term": row["term"], "owner_meaning": row["owner_meaning"], "system_operationalization": row["system_operationalization"], "examples": json.loads(row["examples_json"]), "anti_examples": json.loads(row["anti_examples_json"]), "project_id": row["project_id"] or None}
            entry = {**content, "confidence": row["confidence"], "evidence_refs": json.loads(row["evidence_refs_json"]), "is_operational": bool(content["system_operationalization"] and content["anti_examples"])}
        else:
            content = {"domain": row["domain"], "preferred_collaboration_pattern": row["preferred_collaboration_pattern"]}
            entry = {**content, "entry_id": row["entry_id"], "evidence_refs": []}
        receipt = await (await db.execute("SELECT value FROM runtime_meta WHERE key=?", (_key(kind, content),))).fetchone()
        provenance = json.loads(receipt["value"]) if receipt else {}
        confirmed = provenance.get("content_sha256") == _digest(content) and provenance.get("state") == "OWNER_CONFIRMED" and provenance.get("source") == "OWNER_AUTHORED"
        if not confirmed:
            provenance = {"state": "UNCONFIRMED", "source": "EXISTING_UNDERSTANDING"}
        elif kind == "complement":
            entry["evidence_refs"] = [provenance["evidence_ref"]]
        return {"entry": entry, "provenance": provenance, "execution_grant": False, "status": "SAVED" if confirmed else "OBSERVED"}

    async def exact(self, kind: str, content: dict) -> dict:
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            if kind == "vocabulary":
                row = await (await db.execute("SELECT * FROM shared_vocabulary WHERE term=? AND project_id=?", (content["term"], content.get("project_id") or ""))).fetchone()
            else:
                row = await (await db.execute("SELECT * FROM cognitive_complement_map WHERE domain=?", (content["domain"],))).fetchone()
            if not row:
                raise HTTPException(404, "owner_memory_entry_not_found")
            return await self._view(db, kind, row)

    async def all(self, kind: str) -> dict:
        table = "shared_vocabulary" if kind == "vocabulary" else "cognitive_complement_map"
        order = "term,project_id" if kind == "vocabulary" else "domain"
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            rows = await (await db.execute(f"SELECT * FROM {table} ORDER BY {order}")).fetchall()
            return {"entries": [await self._view(db, kind, row) for row in rows], "execution_grant": False}
