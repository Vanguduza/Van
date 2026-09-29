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
  observations (EVIDENCED), and carries its own `authority_stratum`: CONFIRMED →
  S0_OWNER_PROJECT_TRUTH, EVIDENCED → S5_ADMITTED_SPMRF (`owner_model_evidenced`). The
  capsule-level stratum is the lowest-authority item present; an empty capsule is S0
  because it asserts nothing (see `EMPTY_CAPSULE_STRATUM`);
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
#: C3/C4 per-item strata (parent amendment). An owner-stated assertion (CONFIRMED, reached
#: only through the owner's confirm/correct) is owner truth. An EVIDENCED assertion is VAN's
#: governed conclusion from its own system observations — admitted inference, not owner
#: truth — and is ranked with admitted SPMRF. Consumers must never promote an item above
#: its own stratum.
STRATUM_OWNER_STATED = "S0_OWNER_PROJECT_TRUTH"
STRATUM_OWNER_MODEL_EVIDENCED = "S5_ADMITTED_SPMRF"
LABEL_OWNER_STATED = "owner_stated"
LABEL_OWNER_MODEL_EVIDENCED = "owner_model_evidenced"
#: C4 ranks: 0 is the highest authority. Only the strata this producer emits are listed.
STRATUM_RANK = {STRATUM_OWNER_STATED: 0, STRATUM_OWNER_MODEL_EVIDENCED: 5}
#: Capsule stratum when `content` holds no items. An empty capsule asserts nothing about the
#: owner, so there is no item a consumer could promote; S0 is used because the only source
#: of an empty answer is the Owner Model itself. Consumers must not read an empty S0 capsule
#: as "the owner has stated they have no preferences" — it means "nothing actionable".
EMPTY_CAPSULE_STRATUM = STRATUM_OWNER_STATED
#: Retained name: the stratum of an empty capsule.
AUTHORITY_STRATUM = EMPTY_CAPSULE_STRATUM


def item_stratum(state: AssertionState) -> tuple[str, str]:
    """(authority_stratum, authority_label) for one actionable assertion state."""
    if state is AssertionState.CONFIRMED:
        return STRATUM_OWNER_STATED, LABEL_OWNER_STATED
    if state is AssertionState.EVIDENCED:
        return STRATUM_OWNER_MODEL_EVIDENCED, LABEL_OWNER_MODEL_EVIDENCED
    raise ValueError(f"PERSONAL_CONTEXT_NOT_ACTIONABLE: {state.value}")


def capsule_stratum(items: list[dict[str, Any]]) -> str:
    """The lowest-authority (highest-rank) stratum among the items present."""
    if not items:
        return EMPTY_CAPSULE_STRATUM
    return max((i["authority_stratum"] for i in items), key=STRATUM_RANK.__getitem__)


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
        stratum, label = item_stratum(a.state)
        items.append({
            "assertion_id": a.assertion_id,
            "authority_stratum": stratum,
            "authority_label": label,
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
        "authority_stratum": capsule_stratum(items),
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
    "EMPTY_CAPSULE_STRATUM",
    "LABEL_OWNER_MODEL_EVIDENCED",
    "LABEL_OWNER_STATED",
    "STRATUM_OWNER_MODEL_EVIDENCED",
    "STRATUM_OWNER_STATED",
    "STRATUM_RANK",
    "capsule_stratum",
    "item_stratum",
    "CAPSULE_SCHEMA",
    "CONTENT_SCHEMA",
    "PRIVACY_CLASS",
    "build_personal_capsule",
    "canonical_json",
    "content_hash",
    "verify_content_hash",
]
