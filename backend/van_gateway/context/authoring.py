"""Who may write which epistemic tier, and how the authoritative tiers get filled.

P0-CTX-002: the only production write path into `owner_facts` was the Hermes admission
route, correctly gated to `INFERRED` / `MODEL_DERIVED` — a model must not write canonical
truth. But nothing else wrote at all, and readiness, graph and lexical queries exclude
`INFERRED` by default. So `CANONICAL_OWNER`, `PROJECT_TRUTH` and the `VERIFIED_*` tiers
were empty in any deployed system: the only facts production could write were the only
facts retrieval refused to read.

Two writers close that, and the split between them is the whole point.

**The owner writes CANONICAL_OWNER.** A device-signed statement from the paired phone is
the only thing that can. Not Hermes, not an importer, not a heuristic.

**Project Truth imports PROJECT_TRUTH.** It is a file the owner controls, already fetched
and SHA-pinned by the project router, so its facts carry the SHA as their source reference
and are superseded wholesale when the SHA changes. Nothing infers them.

Both refuse to write a tier they are not entitled to, rather than accepting a tier
parameter and trusting the caller — which is the shape the audit found everywhere else.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from van_gateway.context.models import (
    EpistemicState,
    OwnerFactCandidate,
    OwnerFactRecord,
    SensitivityClass,
    SourceTrust,
)
from van_gateway.context.service import OwnerContextService


class ContextAuthoringError(ValueError):
    """A write that names a tier its author is not entitled to."""


#: What each author may write. Stated as data so a new author has to choose, and so the
#: test can assert the sets are disjoint where it matters.
AUTHOR_TIERS: dict[str, tuple[EpistemicState, SourceTrust]] = {
    "owner_device": (EpistemicState.CANONICAL_OWNER, SourceTrust.OWNER_EXPLICIT),
    "project_truth": (EpistemicState.PROJECT_TRUTH, SourceTrust.TRUSTED_OWNER_FILE),
    "hermes": (EpistemicState.INFERRED, SourceTrust.MODEL_DERIVED),
}


def _fact_id(*parts: str) -> str:
    return "fact_" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


class OwnerFactAuthor:
    """The owner's own statements about themselves, their people and their preferences."""

    def __init__(self, context: OwnerContextService) -> None:
        self.context = context

    async def state(
        self,
        *,
        device_id: str,
        subject: str,
        predicate: str,
        value: Any,
        scope: str = "global",
        sensitivity: SensitivityClass = SensitivityClass.OWNER_PRIVATE,
        valid_until_ms: int | None = None,
        now_ms: int | None = None,
    ) -> OwnerFactRecord:
        """Record something the owner said, at CANONICAL_OWNER.

        The source reference names the device, so a fact can always be traced to the
        credential that asserted it. A later statement about the same subject and
        predicate supersedes the earlier one rather than sitting beside it as a conflict:
        the owner changing their mind is not two sources disagreeing.
        """
        stamp = int(time.time() * 1000) if now_ms is None else now_ms
        authority, trust = AUTHOR_TIERS["owner_device"]
        existing = await self.context.current_candidates(
            _requirement(subject, predicate, scope), now_ms=stamp
        )
        supersedes = next(
            (f.fact_id for f in existing if f.authority is EpistemicState.CANONICAL_OWNER), None
        )
        return await self.context.admit_fact(
            OwnerFactCandidate(
                fact_id=_fact_id("owner", device_id, subject, predicate, scope, str(stamp)),
                subject=subject,
                predicate=predicate,
                value=value,
                authority=authority,
                source_trust=trust,
                source_ref=f"owner-device:{device_id}",
                scope=scope,
                valid_from_ms=stamp,
                valid_until_ms=valid_until_ms,
                observed_at_ms=stamp,
                last_verified_at_ms=stamp,
                sensitivity=sensitivity,
                supersedes_fact_id=supersedes,
            )
        )

    async def forget(self, *, subject: str, predicate: str, scope: str = "global",
                     now_ms: int | None = None) -> int:
        """End a fact's validity now. The row stays, so the history is not rewritten."""
        stamp = int(time.time() * 1000) if now_ms is None else now_ms
        facts = await self.context.current_candidates(
            _requirement(subject, predicate, scope), now_ms=stamp
        )
        for fact in facts:
            await self.context.store.execute(
                "UPDATE owner_facts SET valid_until_ms = ? WHERE fact_id = ? "
                "AND (valid_until_ms IS NULL OR valid_until_ms > ?)",
                (stamp, fact.fact_id, stamp),
            )
        return len(facts)


class ProjectTruthImporter:
    """Turns a project's SHA-pinned truth file into PROJECT_TRUTH facts."""

    def __init__(self, context: OwnerContextService) -> None:
        self.context = context

    async def import_truth(
        self, project_id: str, truth: dict[str, Any], *, now_ms: int | None = None
    ) -> list[OwnerFactRecord]:
        """Import the flat scalar keys of a truth document as facts.

        Only scalars, and only from the top level. A truth file's nested structure is
        meaningful to the project and meaningless as a subject/predicate pair; flattening
        it would invent relationships the file never stated. What is wanted here is the
        handful of stable facts a command needs to be answered correctly — the branch, the
        stack, the deployment target — and those are scalars.

        A truth document with no SHA is refused. The SHA is what makes these facts
        supersedable and traceable; without it they would be unattributable and permanent.
        """
        stamp = int(time.time() * 1000) if now_ms is None else now_ms
        sha = str(truth.get("truth_sha") or "").strip()
        if not sha:
            raise ContextAuthoringError(
                f"project truth for {project_id} carries no truth_sha; "
                "facts imported from it could not be attributed or superseded"
            )
        authority, trust = AUTHOR_TIERS["project_truth"]
        document = truth.get("truth") if isinstance(truth.get("truth"), dict) else truth

        written: list[OwnerFactRecord] = []
        for key, value in sorted(document.items()):
            if key in {"truth", "truth_sha", "repo_sha", "ok", "degraded"}:
                continue
            if not isinstance(value, (str, int, float, bool)):
                continue
            requirement = _requirement(project_id, str(key), f"project:{project_id}")
            existing = await self.context.current_candidates(requirement, now_ms=stamp)
            supersedes = next(
                (f.fact_id for f in existing if f.authority is EpistemicState.PROJECT_TRUTH), None
            )
            written.append(
                await self.context.admit_fact(
                    OwnerFactCandidate(
                        fact_id=_fact_id("truth", project_id, str(key), sha),
                        subject=project_id,
                        predicate=str(key),
                        value=value,
                        authority=authority,
                        source_trust=trust,
                        source_ref=f"project-truth:{project_id}:{sha}",
                        scope=f"project:{project_id}",
                        valid_from_ms=stamp,
                        observed_at_ms=stamp,
                        last_verified_at_ms=stamp,
                        sensitivity=SensitivityClass.OWNER_PRIVATE,
                        supersedes_fact_id=supersedes,
                    )
                )
            )
        return written


def _requirement(subject: str, predicate: str, scope: str):
    from van_gateway.context.models import ContextRequirement

    return ContextRequirement(subject=subject, predicate=predicate, scope=scope)


__all__ = [
    "AUTHOR_TIERS",
    "ContextAuthoringError",
    "OwnerFactAuthor",
    "ProjectTruthImporter",
]
