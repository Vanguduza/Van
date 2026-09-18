"""Rev 1 §7 — the canonical CapabilityRegistry.

§7's rule is one sentence: *a capability not in the registry must not be
routable for production mutation.* Making that true requires exactly one place
where routability is decided, and that place must be deterministic — same
declaration, same policy, same readiness, same answer, every time, with no model
anywhere in the path.

`routable()` is therefore a pure conjunction of four terms, evaluated in a fixed
order so the *reason* a capability was refused is stable too:

    declared  AND  policy admits  AND  not structurally forbidden  AND  ready

Readiness is the only term this module does not compute itself. It asks a
`ReadinessProbe` — an adapter over whichever subsystem already owned that fact.
That indirection is the reason this registry can be canonical without being a
third copy of state the automation fabric and Google mesh already maintain.

The declaration set is sealed by digest. Syncing the manifest twice produces
byte-identical rows, and a manifest edit changes the digest, so "which
capabilities did VAN believe in at the time" is answerable after the fact.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

from van_gateway.automation.canonical import digest
from van_gateway.capability.models import (
    CLASS_RANK,
    PrivacyClass,
    CapabilityClass,
    CapabilityDeclaration,
    ReadinessSource,
    Routability,
    RoutabilityReason,
    RoutingConstraints,
    VerificationStrategy,
)
from van_gateway.storage.db import Store

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = REPO_ROOT / "registries" / "capabilities.json"


class CapabilityRegistryError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ReadinessProbe(Protocol):
    """Answers "is this ready right now" for one readiness source.

    Deliberately narrow: a probe may say ready or not-ready and why. It cannot
    change a declaration, so a subsystem being healthy can never widen what a
    capability is permitted to do.
    """

    async def is_ready(self, declaration: CapabilityDeclaration) -> tuple[bool, str | None]:
        ...


class StaticReadiness:
    """Always ready. For native reads with no external dependency."""

    async def is_ready(self, declaration: CapabilityDeclaration) -> tuple[bool, str | None]:
        return True, None


class CapabilityRegistry:
    """Loads the sealed declaration set and decides routability."""

    def __init__(
        self,
        store: Store,
        *,
        manifest_path: str | Path | None = None,
        probes: dict[ReadinessSource, ReadinessProbe] | None = None,
    ) -> None:
        self.store = store
        self.manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
        self._declarations: dict[str, CapabilityDeclaration] = {}
        self._manifest_digest: str = ""
        self._manifest_version: str = ""
        self._probes: dict[ReadinessSource, ReadinessProbe] = {
            ReadinessSource.STATIC: StaticReadiness(),
            **(probes or {}),
        }

    # ------------------------------------------------------------- loading

    def load(self) -> None:
        """Read and validate the manifest. Refuses rather than degrades.

        A malformed declaration is a governance failure, not a runtime blip: a
        registry that silently dropped the row it could not parse would make a
        capability unroutable for a reason nobody can see.
        """
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CapabilityRegistryError("CAPABILITY_MANIFEST_UNREADABLE", str(exc)) from exc

        declarations: dict[str, CapabilityDeclaration] = {}
        for item in raw.get("capabilities", []):
            try:
                declaration = CapabilityDeclaration.model_validate(item)
            except Exception as exc:  # noqa: BLE001 - surfaced as a governance error
                raise CapabilityRegistryError(
                    "CAPABILITY_DECLARATION_INVALID", f"{item.get('capability_id')}: {exc}"
                ) from exc
            if declaration.capability_id in declarations:
                raise CapabilityRegistryError(
                    "CAPABILITY_DECLARED_TWICE", declaration.capability_id
                )
            declarations[declaration.capability_id] = declaration

        self._validate_set(declarations)
        self._declarations = declarations
        self._manifest_version = str(raw.get("version", "0"))
        # Digest the declarations, not the file: comments and key order must not
        # change the identity of the capability set.
        self._manifest_digest = digest(
            {
                "version": self._manifest_version,
                "capabilities": [
                    declarations[k].model_dump(mode="json") for k in sorted(declarations)
                ],
            }
        )

    @staticmethod
    def _validate_set(declarations: dict[str, CapabilityDeclaration]) -> None:
        """Cross-declaration rules — the ones a single row cannot check itself."""
        for declaration in declarations.values():
            for fallback in declaration.fallback_capabilities:
                if fallback not in declarations:
                    raise CapabilityRegistryError(
                        "CAPABILITY_FALLBACK_UNDECLARED",
                        f"{declaration.capability_id} -> {fallback}",
                    )
                if fallback == declaration.capability_id:
                    raise CapabilityRegistryError(
                        "CAPABILITY_FALLBACK_SELF", declaration.capability_id
                    )
                # §8 — a fallback that can do more than the thing it stands in
                # for is an escalation wearing a fallback's clothes.
                if CLASS_RANK[declarations[fallback].authority_class] > CLASS_RANK[
                    declaration.authority_class
                ]:
                    raise CapabilityRegistryError(
                        "CAPABILITY_FALLBACK_ESCALATES",
                        f"{declaration.capability_id} -> {fallback}",
                    )
                # The same error in the other currency: a substitute that
                # discloses owner data the original kept inside VAN is not a
                # substitute, it is a different capability with a different
                # consequence. Caught here rather than at routing time because
                # silent disclosure is not something to discover in production.
                if (
                    declaration.privacy_class is PrivacyClass.OWNER_PRIVATE
                    and declarations[fallback].privacy_class is PrivacyClass.EXTERNAL_DISCLOSING
                ):
                    raise CapabilityRegistryError(
                        "CAPABILITY_FALLBACK_DISCLOSES",
                        f"{declaration.capability_id} -> {fallback}",
                    )
            # §34 — a mutation with nothing to verify it cannot be admitted.
            if declaration.mutates and (
                declaration.verification_strategy is VerificationStrategy.NONE
            ):
                raise CapabilityRegistryError(
                    "CAPABILITY_MUTATION_WITHOUT_VERIFIER", declaration.capability_id
                )
            if (
                declaration.readiness_source is ReadinessSource.NEVER_ROUTABLE
                and not declaration.never_routable_reason
            ):
                raise CapabilityRegistryError(
                    "CAPABILITY_NEVER_ROUTABLE_WITHOUT_REASON", declaration.capability_id
                )

    async def sync(self, *, now_ms: int | None = None) -> str:
        """Materialize the declaration set. Idempotent by construction."""
        if not self._declarations:
            self.load()
        now = int(time.time() * 1000) if now_ms is None else now_ms
        for capability_id in sorted(self._declarations):
            declaration = self._declarations[capability_id]
            await self.store.execute(
                """
                INSERT INTO capability_registry(
                  capability_id, manifest_version, manifest_digest, declaration_json,
                  capability_class, authority_class, readiness_source, provider, executor,
                  created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(capability_id) DO UPDATE SET
                  manifest_version=excluded.manifest_version,
                  manifest_digest=excluded.manifest_digest,
                  declaration_json=excluded.declaration_json,
                  capability_class=excluded.capability_class,
                  authority_class=excluded.authority_class,
                  readiness_source=excluded.readiness_source,
                  provider=excluded.provider, executor=excluded.executor,
                  updated_at_ms=excluded.updated_at_ms
                """,
                (
                    capability_id, self._manifest_version, self._manifest_digest,
                    Store.dumps(declaration.model_dump(mode="json")),
                    declaration.capability_class.value, declaration.authority_class.value,
                    declaration.readiness_source.value, declaration.provider,
                    declaration.executor, now, now,
                ),
            )
        # A declaration removed from the manifest must stop being routable, and
        # the row is kept with the stale digest so the removal is auditable.
        await self.store.execute(
            "UPDATE capability_registry SET withdrawn_at_ms = ? "
            "WHERE manifest_digest != ? AND withdrawn_at_ms IS NULL",
            (now, self._manifest_digest),
        )
        return self._manifest_digest

    # ------------------------------------------------------------ accessors

    @property
    def manifest_digest(self) -> str:
        return self._manifest_digest

    @property
    def capability_ids(self) -> list[str]:
        return sorted(self._declarations)

    def get(self, capability_id: str) -> CapabilityDeclaration | None:
        return self._declarations.get(capability_id)

    def require(self, capability_id: str) -> CapabilityDeclaration:
        declaration = self._declarations.get(capability_id)
        if declaration is None:
            raise CapabilityRegistryError("CAPABILITY_NOT_DECLARED", capability_id)
        return declaration

    def of_class(self, capability_class: CapabilityClass) -> list[CapabilityDeclaration]:
        return [
            self._declarations[k]
            for k in sorted(self._declarations)
            if self._declarations[k].capability_class is capability_class
        ]

    # ---------------------------------------------------------- routability

    async def routability(
        self,
        capability_id: str,
        *,
        constraints: RoutingConstraints | None = None,
    ) -> Routability:
        """The single gate. Four terms, fixed order, no model.

        Order matters as much as the terms: policy is evaluated before readiness
        so that a capability the caller was never allowed to use reports
        ABOVE_AUTHORITY_CEILING rather than NOT_READY. Reporting a policy refusal
        as a health problem would invite someone to "fix" it by restarting a
        worker.
        """
        constraints = constraints or RoutingConstraints()
        declaration = self._declarations.get(capability_id)
        if declaration is None:
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.NOT_DECLARED,
                detail="§7 — a capability not declared here is not routable",
            )

        if declaration.readiness_source is ReadinessSource.NEVER_ROUTABLE:
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.NEVER_ROUTABLE,
                detail=declaration.never_routable_reason,
                readiness_source=declaration.readiness_source,
            )

        if CLASS_RANK[declaration.authority_class] > CLASS_RANK[constraints.max_action_class]:
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.ABOVE_AUTHORITY_CEILING,
                detail=f"{declaration.authority_class.value}>"
                       f"{constraints.max_action_class.value}",
                readiness_source=declaration.readiness_source,
            )

        if (
            constraints.allowed_capability_classes
            and declaration.capability_class not in constraints.allowed_capability_classes
        ):
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.CLASS_NOT_PERMITTED,
                detail=declaration.capability_class.value,
                readiness_source=declaration.readiness_source,
            )

        if declaration.requires_owner_presence and not constraints.owner_present:
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.OWNER_PRESENCE_REQUIRED,
                readiness_source=declaration.readiness_source,
            )

        if (
            declaration.privacy_class.value == "EXTERNAL_DISCLOSING"
            and not constraints.permit_external_disclosure
        ):
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.PRIVACY_NOT_PERMITTED,
                readiness_source=declaration.readiness_source,
            )

        probe = self._probes.get(declaration.readiness_source)
        if probe is None:
            # An unprobed source is not assumed healthy. A missing adapter is a
            # wiring bug, and defaulting to ready would hide it behind a
            # capability that silently fails at execution time instead.
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.NOT_READY,
                detail=f"no readiness probe for {declaration.readiness_source.value}",
                readiness_source=declaration.readiness_source,
            )
        ready, detail = await probe.is_ready(declaration)
        if not ready:
            return Routability(
                capability_id=capability_id, routable=False,
                reason=RoutabilityReason.NOT_READY, detail=detail,
                readiness_source=declaration.readiness_source,
            )

        return Routability(
            capability_id=capability_id, routable=True, reason=RoutabilityReason.ROUTABLE,
            readiness_source=declaration.readiness_source,
        )

    async def assert_routable_for_mutation(
        self, capability_id: str, *, constraints: RoutingConstraints | None = None
    ) -> CapabilityDeclaration:
        """§7's rule, as a call site can enforce it."""
        verdict = await self.routability(capability_id, constraints=constraints)
        if not verdict.routable:
            raise CapabilityRegistryError(
                f"CAPABILITY_NOT_ROUTABLE:{verdict.reason.value}",
                verdict.detail or capability_id,
            )
        return self.require(capability_id)


__all__ = [
    "DEFAULT_MANIFEST",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "ReadinessProbe",
    "StaticReadiness",
]
