"""Rev 1.3 §§45-46, 203-204, 367.2 — credential classes and alias resolution.

The classes come from ``config/automation/credentials.yaml.example``, landed by
the trading-core bootstrap work. This module enforces them:

* **C0/C1/C2 may never reach n8n.** Owner signing keys, device HMAC secrets, VAN
  internal tokens, broker execution credentials and VATI authority-store
  credentials stay in the gateway. When a VAN-native capability already holds the
  canonical credential, the workflow calls that capability instead of duplicating
  the secret (§45).
* **The IR carries aliases, never values** (§46). Resolution to an n8n credential
  *identifier* happens here, after authorization, and the value never appears.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from van_gateway.automation.policy import (
    N8N_FORBIDDEN_CREDENTIAL_CLASSES,
    PolicyError,
)


class CredentialClass(str, Enum):
    C0_OWNER_ROOT = "C0_OWNER_ROOT"
    C1_FINANCIAL_EXECUTION = "C1_FINANCIAL_EXECUTION"
    C2_CANONICAL_SERVICE = "C2_CANONICAL_SERVICE"
    C3_SENSITIVE_INTEGRATION = "C3_SENSITIVE_INTEGRATION"
    C4_LOW_RISK_INTEGRATION = "C4_LOW_RISK_INTEGRATION"

    @property
    def may_be_stored_in_n8n(self) -> bool:
        return self.value not in N8N_FORBIDDEN_CREDENTIAL_CLASSES


@dataclass(frozen=True)
class CredentialAlias:
    """A reference, never a secret. ``n8n_credential_id`` is an opaque n8n handle."""

    alias: str
    credential_class: CredentialClass
    n8n_credential_id: str | None = None
    #: Set when the canonical secret stays in the gateway and n8n must call a
    #: VAN capability instead of holding anything itself (§45).
    gateway_capability: str | None = None
    admitted: bool = False


class CredentialResolver:
    """Resolves IR aliases to n8n credential identifiers under least privilege."""

    def __init__(self, aliases: dict[str, CredentialAlias] | None = None) -> None:
        self._aliases = dict(aliases or {})

    def register(self, alias: CredentialAlias) -> CredentialAlias:
        if not alias.admitted and alias.credential_class in (
            CredentialClass.C3_SENSITIVE_INTEGRATION,
            CredentialClass.C4_LOW_RISK_INTEGRATION,
        ):
            # config/automation/credentials.yaml.example: C3 requires explicit
            # admission, C4 is permitted *after* admission. Neither is automatic.
            raise PolicyError(f"credential_requires_admission:{alias.alias}")
        if not alias.credential_class.may_be_stored_in_n8n and alias.n8n_credential_id is not None:
            raise PolicyError(f"credential_class_forbidden_in_n8n:{alias.credential_class.value}")
        self._aliases[alias.alias] = alias
        return alias

    def get(self, alias: str) -> CredentialAlias:
        try:
            return self._aliases[alias]
        except KeyError as exc:
            raise PolicyError(f"unknown_credential_alias:{alias}") from exc

    def assert_storable_in_n8n(self, alias: str) -> CredentialAlias:
        """§367.2 — the check the Security Policy amendment asks to be enforced."""
        entry = self.get(alias)
        if not entry.credential_class.may_be_stored_in_n8n:
            raise PolicyError(f"credential_class_forbidden_in_n8n:{entry.credential_class.value}")
        return entry

    def resolve_for_compilation(self, aliases: list[str]) -> dict[str, str]:
        """Map IR aliases to n8n credential IDs, refusing anything n8n may not hold.

        An alias whose canonical secret lives in the gateway resolves to nothing
        here by design — the compiler must route that step through a VAN
        capability sub-workflow instead.
        """
        resolved: dict[str, str] = {}
        for alias in aliases:
            entry = self.get(alias)
            if entry.gateway_capability is not None:
                raise PolicyError(
                    f"credential_is_gateway_mediated:{alias}:{entry.gateway_capability}"
                )
            self.assert_storable_in_n8n(alias)
            if entry.n8n_credential_id is None:
                raise PolicyError(f"credential_not_provisioned:{alias}")
            resolved[alias] = entry.n8n_credential_id
        return resolved


__all__ = ["CredentialAlias", "CredentialClass", "CredentialResolver"]
