"""Owner lifecycle governance for everything VAN concluded about the owner.

P2-CTX-003. The graph holds people, devices, accounts, decisions, policies, habits and
relationships. Retention existed. Export, revision history and conflict semantics did not,
and correction recorded its effect without recording itself.

Four things were wrong, and they are worth separating because they fail differently.

**VAN could forget what it would not show.** `context/forget.py` names thirteen stores of
owner-derived material and can clear every one of them. The only export, `export_scope`,
covered two, was reachable only through the internal-control runtime API, and took a scope
rather than an owner. So the owner could destroy material they had never been permitted to
read. That asymmetry is the defect this module exists to remove, and it is asserted as an
invariant rather than left to whoever adds the fourteenth store: `export()` iterates
`FORGETTABLE` itself rather than keeping a second list beside it, and the test compares the
export's actual output against that list. A constant derived from `FORGETTABLE` and then
compared back to it would have proved nothing — it is true by construction.

**A correction recorded its effect and not itself.** `supersedes_fact_id` was read, used to
close the prior record's validity window, and discarded — there was no column. Two facts
with adjacent windows are indistinguishable from two that expired independently, so "what
did VAN believe before, and what changed its mind?" had no answer. Migration 25 adds the
column; this module walks it.

**A contradiction was only visible to whoever tripped over it.** `resolve_requirement`
detects two same-authority facts with different content and reports CONFLICTED — but only
for a requirement somebody asked about. A contradiction nothing queries is held silently and
forever.

**Conflicts are surfaced, not resolved.** VAN has no business deciding which of the owner's
two contradictory statements is the true one. `conflicts()` reports the fact ids and their
values and stops. Anything more would be VAN overwriting the owner with an inference, which
is the failure the whole epistemic-state ladder exists to prevent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from van_gateway.context.forget import DELIBERATELY_KEPT, FORGETTABLE
from van_gateway.context.models import ContextRequirement, ReadinessState
from van_gateway.context.service import OwnerContextService
from van_gateway.storage.db import Store

#: Per-store row cap. An export that silently truncates teaches the owner that VAN knows
#: less than it does, so the cap is generous and every store reports whether it was hit.
MAX_ROWS_PER_STORE = 5000


@dataclass(frozen=True)
class Revision:
    """One step in a fact's history: what was believed, and what ended it."""

    fact_id: str
    value: Any
    authority: str
    source_trust: str
    source_ref: str
    valid_from_ms: int
    valid_until_ms: int | None
    revision: int
    supersedes_fact_id: str | None
    #: The fact that replaced this one, if any. The stored link points backwards; this is
    #: the same edge read forwards, because "what replaced this" is the owner's question.
    superseded_by_fact_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "value": self.value,
            "authority": self.authority,
            "source_trust": self.source_trust,
            "source_ref": self.source_ref,
            "valid_from_ms": self.valid_from_ms,
            "valid_until_ms": self.valid_until_ms,
            "revision": self.revision,
            "supersedes_fact_id": self.supersedes_fact_id,
            "superseded_by_fact_id": self.superseded_by_fact_id,
        }


class ContextLifecycle:
    """Export, revision history and conflict reporting over the owner context graph."""

    def __init__(self, store: Store, context: OwnerContextService) -> None:
        self.store = store
        self.context = context

    # ---------------------------------------------------------------- export

    async def export(self, owner_principal_id: str = "owner") -> dict[str, Any]:
        """Everything VAN holds about the owner, store by store, with provenance.

        Rows are returned as stored rather than reshaped into a presentation model. That is
        deliberate: a summary is a place for material to go missing, and the owner asking
        what VAN knows is entitled to the columns, not a paraphrase. Provenance travels for
        free because the authority, source_trust and source_ref columns are part of the row.
        """
        stores: dict[str, Any] = {}
        for entry in FORGETTABLE:
            row = await self.store.fetchone(
                f"SELECT COUNT(*) AS n FROM {entry.table}"  # noqa: S608
                + (f" WHERE {entry.owner_column} = ?" if entry.owner_column else ""),
                (owner_principal_id,) if entry.owner_column else (),
            )
            held = int(row["n"]) if row else 0
            rows = await self.store.fetchall(
                f"SELECT * FROM {entry.table}"  # noqa: S608
                + (f" WHERE {entry.owner_column} = ?" if entry.owner_column else "")
                + f" LIMIT {MAX_ROWS_PER_STORE}",
                (owner_principal_id,) if entry.owner_column else (),
            )
            exported = [self._row_to_dict(r) for r in rows]
            stores[entry.table] = {
                "holds": entry.description,
                "rows_held": held,
                "rows_exported": len(exported),
                # Stated per store rather than inferred by the reader comparing two numbers.
                "truncated": held > len(exported),
                "records": exported,
            }
        return {
            "owner_principal_id": owner_principal_id,
            "stores": stores,
            "max_rows_per_store": MAX_ROWS_PER_STORE,
            # The same disclosure the forget report makes, for the same reason: what is not
            # covered should be visible in the thing that does not cover it.
            "not_covered": DELIBERATELY_KEPT,
        }

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in row.keys():
            value = row[key]
            # Stored JSON is unwrapped so the export is readable as data rather than as a
            # string containing data. A column that is not JSON is left exactly as it is.
            if isinstance(value, str) and key.endswith("_json"):
                try:
                    out[key[: -len("_json")]] = json.loads(value)
                    continue
                except (ValueError, TypeError):
                    pass
            out[key] = value
        return out

    # --------------------------------------------------------------- history

    async def history(
        self, *, subject: str, predicate: str, scope: str = "global"
    ) -> dict[str, Any]:
        """Every record VAN has held for one claim, newest first, with the chain.

        Ordered by validity rather than by insertion, because the owner's question is about
        what VAN believed *when*, not about the order rows happened to arrive in.
        """
        rows = await self.store.fetchall(
            """
            SELECT * FROM owner_facts
            WHERE subject = ? AND predicate = ? AND scope = ?
            ORDER BY valid_from_ms DESC, revision DESC
            """,
            (subject, predicate, scope),
        )
        records = [self.context.row_to_fact(row) for row in rows]
        # The stored link points backwards. Invert it once so each entry can also say what
        # replaced it without the caller walking the list.
        replaced_by = {
            record.supersedes_fact_id: record.fact_id
            for record in records
            if record.supersedes_fact_id
        }
        revisions = [
            Revision(
                fact_id=record.fact_id,
                value=record.value,
                authority=record.authority.value,
                source_trust=record.source_trust.value,
                source_ref=record.source_ref,
                valid_from_ms=record.valid_from_ms,
                valid_until_ms=record.valid_until_ms,
                revision=record.revision,
                supersedes_fact_id=record.supersedes_fact_id,
                superseded_by_fact_id=replaced_by.get(record.fact_id),
            )
            for record in records
        ]
        return {
            "subject": subject,
            "predicate": predicate,
            "scope": scope,
            "revisions": [r.as_dict() for r in revisions],
            # A record whose validity ended with nothing replacing it was withdrawn, not
            # corrected. The two are different things to have done and the owner can see
            # which happened without inferring it from a null.
            "withdrawn_without_replacement": [
                r.fact_id
                for r in revisions
                if r.valid_until_ms is not None and r.superseded_by_fact_id is None
            ],
        }

    # ------------------------------------------------------------- conflicts

    async def conflicts(self, now_ms: int | None = None) -> dict[str, Any]:
        """Every claim VAN currently holds two contradictory answers to.

        Detection is delegated to `resolve_requirement` rather than reimplemented. That is
        the point: a second copy of the rule would drift, and the owner's conflict list
        would stop agreeing with the readiness signal that blocks their commands — which is
        precisely the class of divergence this programme keeps finding.

        Each identity is resolved twice, mirroring the blocking/advisory split that
        `ContextReadiness` already makes. `blocking` conflicts are the ones a default
        requirement would hit, and they stop work. `inferred_only` conflicts appear once
        inferences are admitted; nothing will ever trip over them, which is exactly why they
        need somewhere to be seen.
        """
        identities = await self.store.fetchall(
            """
            SELECT DISTINCT subject, predicate, scope FROM owner_facts
            ORDER BY subject, predicate, scope
            """,
            (),
        )
        blocking: list[dict[str, Any]] = []
        inferred_only: list[dict[str, Any]] = []
        for identity in identities:
            subject = str(identity["subject"])
            predicate = str(identity["predicate"])
            scope = str(identity["scope"])
            strict = await self.context.resolve_requirement(
                ContextRequirement(
                    subject=subject, predicate=predicate, scope=scope, allow_inferred=False
                ),
                now_ms=now_ms,
            )
            if strict.state is ReadinessState.CONFLICTED:
                blocking.append(
                    await self._describe(subject, predicate, scope, strict.conflicting_fact_ids)
                )
                continue
            loose = await self.context.resolve_requirement(
                ContextRequirement(
                    subject=subject, predicate=predicate, scope=scope, allow_inferred=True
                ),
                now_ms=now_ms,
            )
            if loose.state is ReadinessState.CONFLICTED:
                inferred_only.append(
                    await self._describe(subject, predicate, scope, loose.conflicting_fact_ids)
                )
        return {
            "blocking": blocking,
            "inferred_only": inferred_only,
            "total": len(blocking) + len(inferred_only),
            # VAN states the disagreement and stops. Choosing between two things the owner
            # is recorded as having said is not a retrieval decision.
            "resolution": "owner_only",
        }

    async def _describe(
        self, subject: str, predicate: str, scope: str, fact_ids: list[str]
    ) -> dict[str, Any]:
        """A conflict with the values in it.

        Reporting bare fact ids would make the owner issue a second request per side to find
        out what VAN actually disagrees with itself about.
        """
        sides = []
        for fact_id in fact_ids:
            row = await self.store.fetchone(
                "SELECT * FROM owner_facts WHERE fact_id = ?", (fact_id,)
            )
            if row is None:
                continue
            record = self.context.row_to_fact(row)
            sides.append(
                {
                    "fact_id": record.fact_id,
                    "value": record.value,
                    "authority": record.authority.value,
                    "source_trust": record.source_trust.value,
                    "source_ref": record.source_ref,
                    "observed_at_ms": record.observed_at_ms,
                }
            )
        return {
            "subject": subject,
            "predicate": predicate,
            "scope": scope,
            "sides": sides,
        }


__all__ = ["MAX_ROWS_PER_STORE", "ContextLifecycle", "Revision"]
