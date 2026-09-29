"""Personal context capsule producer (Memory Fabric Programme A, contract C3).

A capsule is what leaves the Owner Model when some other part of the system needs to
know how the owner works. It is fenced, not trusted: it carries the
``owner_model_revision`` it was built at, and a consumer must serve it only while a live
read of that revision (C2) still returns the same number. A correction therefore
invalidates every outstanding capsule synchronously, whether or not the outbox has been
drained yet.

What goes in ``content``:

* only assertions VAN may act on — CONFIRMED or EVIDENCED, not superseded — and each is
  labelled with whether the *owner* stated it (CONFIRMED) or VAN concluded it from its own
  observations (EVIDENCED);
* nothing whose support is derived-origin only. Derived episodes (Hindsight, OpenViking,
  model inference) cannot make an assertion actionable (C1), so such assertions never
  reach the actionable set; they are excluded from the capsule entirely rather than
  labelled, which is the stricter of the two options C3 allows;
* no floats. ``content_hash`` is sha256 over canonical JSON, and floats are where
  canonical JSON implementations disagree across languages.

Canonical JSON here: ``json.dumps(content, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`` encoded as UTF-8. A consumer re-hashing ``content`` must use the
same rule.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from van_gateway.understanding.owner_model import (
    AssertionState,
    OwnerCognitiveModel,
)

CAPSULE_SCHEMA = "dial.context_capsule.v1"
CONTENT_SCHEMA = "van.owner_model.personal_context.v1"
PRIVACY_CLASS = "OWNER_PRIVATE"
#: C4. The Owner Model is the owner's own plane. EVIDENCED items inside it are labelled
#: `owner_stated: false` rather than given a separate stratum, because C4 has no stratum
#: for "VAN's own system-observed conclusion about the owner" (reported to the parent).
AUTHORITY_STRATUM = "S0_OWNER_PROJECT_TRUTH"


def canonical_json(content: Any) -> bytes:
    return json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_hash(content: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(content)).hexdigest()


def verify_content_hash(capsule: dict[str, Any]) -> bool:
    return capsule.get("content_hash") == content_hash(capsule.get("content"))


async def build_personal_capsule(
    model: OwnerCognitiveModel,
    owner_principal_id: str,
    *,
    purpose: str,
    project_id: str | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Build a C3 capsule of what VAN may act on about this owner, at one revision.

    The revision and the assertions are read inside one read transaction, so the
    revision stamped on the capsule is the revision its content was read at — a mutation
    that commits between the two reads cannot produce a capsule whose content is newer or
    older than its fence.

    Scope: assertions with no project, plus those of ``project_id`` when one is given.
    """
    if not purpose or not purpose.strip():
        raise ValueError("PERSONAL_CONTEXT_PURPOSE_REQUIRED")
    now = int(time.time() * 1000) if now_ms is None else now_ms
    sql = ("SELECT * FROM owner_cognitive_model WHERE owner_principal_id = ? "
           "AND state IN (?, ?) AND superseded_by IS NULL AND "
           + ("(project_id IS NULL OR project_id = ?)" if project_id else "project_id IS NULL")
           + " ORDER BY field, value, assertion_id")
    params: list[Any] = [owner_principal_id, AssertionState.CONFIRMED.value,
                         AssertionState.EVIDENCED.value]
    if project_id:
        params.append(project_id)

    async with model.store.connection() as db:
        await db.execute("BEGIN")  # one snapshot for the revision and the content
        try:
            cursor = await db.execute(
                "SELECT owner_model_revision FROM owner_model_revisions "
                "WHERE owner_principal_id = ?",
                (owner_principal_id,),
            )
            row = await cursor.fetchone()
            revision = 0 if row is None else int(row[0])
            cursor = await db.execute(sql, tuple(params))
            assertions = await model._hydrate(db, list(await cursor.fetchall()))  # noqa: SLF001
        finally:
            await db.rollback()

    items: list[dict[str, Any]] = []
    provenance: list[str] = [f"van-owner-model:revision:{owner_principal_id}:{revision}"]
    for a in assertions:
        # Belt and braces over the SQL filter: never let a non-actionable row through.
        if not a.may_act_on:
            continue
        items.append({
            "assertion_id": a.assertion_id,
            "field": a.field.value,
            "value": a.value,
            "state": a.state.value,
            "owner_stated": a.state.is_owner_stated,
            "autonomy_bearing": a.is_autonomy_bearing,
            "project_id": a.project_id,
            "evidencing_episode_count": a.evidencing_episode_count,
            "actionable": True,
        })
        provenance.append(f"van-owner-model:assertion:{a.assertion_id}")
        provenance.extend(sorted(a.supporting_episode_refs))

    content = {
        "schema": CONTENT_SCHEMA,
        "owner_principal_id": owner_principal_id,
        "assertions": items,
    }
    return {
        "schema": CAPSULE_SCHEMA,
        "context_capsule_id": f"cc_{uuid.uuid4().hex}",
        "principal_scope": owner_principal_id,
        "project_scope": project_id,
        "authority_stratum": AUTHORITY_STRATUM,
        "purpose": purpose,
        "privacy_class": PRIVACY_CLASS,
        "provenance_refs": list(dict.fromkeys(provenance)),
        "source_revisions": {"owner_model_revision": revision},
        "owner_model_revision": revision,
        "freshness": "FRESH",
        "content": content,
        "content_hash": content_hash(content),
        "issued_at_ms": now,
    }


__all__ = [
    "AUTHORITY_STRATUM",
    "CAPSULE_SCHEMA",
    "CONTENT_SCHEMA",
    "PRIVACY_CLASS",
    "build_personal_capsule",
    "canonical_json",
    "content_hash",
    "verify_content_hash",
]
