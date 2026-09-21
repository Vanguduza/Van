"""Capsule schema migration with mechanically verified provenance (§6.8, TRD-ENH-005).

Adding a timeframe contract changes `capsule_hash`, which covers the whole
document. `silent_strategy_mutation` is a hard-forbidden behaviour and an
unexplained rehash is indistinguishable from one — so a migration asserting
`strategy_logic_changed = false` must be *checked*, not trusted.

The check is narrow on purpose: the fields that decide what a strategy does must
be byte-identical to the parent. If any of them moved, the change is a strategy
revision and takes the owner-signed promotion path instead of a migration record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from vati.core.canonical import canonical_hash

#: The fields that decide what a strategy does. A migration may not touch them.
LOGIC_FIELDS = (
    "entry_logic_ref",
    "invalidation_logic_ref",
    "stop_model",
    "target_model",
    "eligible_regimes",
    "forbidden_regimes",
    "risk_limits",
    "instruments",
    "horizons",
    "event_rules",
    "execution_model",
    "required_data_granularity",
)

#: Fields a migration is allowed to introduce or change.
MIGRATION_FIELDS = ("timeframe_contract", "capsule_hash", "version")

MIGRATION_REASONS = frozenset({"MTF_SCHEMA_ADOPTION"})


class MigrationError(ValueError):
    """A migration that would hide a logic change."""


@dataclass(frozen=True)
class CapsuleMigrationRecord:
    strategy_id: str
    old_capsule_hash: str
    new_capsule_hash: str
    migration_reason: str
    strategy_logic_changed: bool
    owner_authority_changed: bool
    migrated_at_unix: int
    changed_fields: tuple[str, ...] = ()
    record_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id, "old_capsule_hash": self.old_capsule_hash,
            "new_capsule_hash": self.new_capsule_hash, "migration_reason": self.migration_reason,
            "strategy_logic_changed": self.strategy_logic_changed,
            "owner_authority_changed": self.owner_authority_changed,
            "migrated_at_unix": self.migrated_at_unix, "changed_fields": list(self.changed_fields),
        }

    def sealed(self) -> "CapsuleMigrationRecord":
        return CapsuleMigrationRecord(**{**self.__dict__, "record_hash": canonical_hash(self.as_dict())})


def _identical(a: Any, b: Any) -> bool:
    """Byte-identical under canonical serialisation, so ordering cannot hide a change."""
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def logic_unchanged(old: Mapping[str, Any], new: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """True when every logic-bearing field survived the migration untouched."""
    moved = tuple(f for f in LOGIC_FIELDS if not _identical(old.get(f), new.get(f)))
    return (not moved), moved


def verify_migration(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    *,
    migration_reason: str,
    migrated_at_unix: int,
) -> CapsuleMigrationRecord:
    """Build the migration record, refusing anything that is really a revision."""
    if migration_reason not in MIGRATION_REASONS:
        raise MigrationError(f"unknown migration_reason:{migration_reason}")
    if old.get("strategy_id") != new.get("strategy_id"):
        raise MigrationError("migration cannot change strategy_id")

    unchanged, moved = logic_unchanged(old, new)
    if not unchanged:
        raise MigrationError(
            "strategy_logic_changed: " + ",".join(moved) + " — this is a strategy revision, "
            "not a schema migration; use the owner-signed promotion path"
        )

    # Anything outside the allowed set is also a revision, even if it is not
    # logic: state and evidence are owner-authority surfaces.
    allowed = set(MIGRATION_FIELDS)
    touched = tuple(
        k for k in set(old) | set(new)
        if k not in allowed and not _identical(old.get(k), new.get(k))
    )
    if touched:
        raise MigrationError("migration touched non-migration fields: " + ",".join(sorted(touched)))

    owner_changed = not _identical(old.get("state"), new.get("state"))
    return CapsuleMigrationRecord(
        strategy_id=str(new.get("strategy_id")),
        old_capsule_hash=str(old.get("capsule_hash", "")),
        new_capsule_hash=str(new.get("capsule_hash", "")),
        migration_reason=migration_reason,
        strategy_logic_changed=False,
        owner_authority_changed=owner_changed,
        migrated_at_unix=migrated_at_unix,
        changed_fields=tuple(sorted(k for k in allowed if not _identical(old.get(k), new.get(k)))),
    ).sealed()


__all__ = [
    "LOGIC_FIELDS",
    "MIGRATION_FIELDS",
    "MIGRATION_REASONS",
    "CapsuleMigrationRecord",
    "MigrationError",
    "logic_unchanged",
    "verify_migration",
]
