"""Source-only broker family directory; no provider state or execution authority.

The directory is a discovery projection.  It deliberately does not turn an
adapter name or a local policy into a claim about a broker's current terms,
instruments, capabilities, eligibility, or a particular account.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .account_operations import BROKER_NAMES, capabilities_for


_METHODS = {
    "DERIV": ("OAUTH", "deriv_oauth_link"),
    "CTRADER": ("OAUTH_DISCOVERY", "ctrader_link"),
    "MT5": ("WINDOWS_BRIDGE_REGISTRATION", "account_upsert"),
    "MT5_EA": ("EA_BRIDGE_KEY", "mt5_ea_issue_key"),
    "PAPER": ("LOCAL_SIMULATION", "account_upsert"),
    "ZSE_OWNER_TICKET": ("OWNER_TICKET_REGISTRATION", "account_upsert"),
}

# Values are absent until an admitted, appropriately scoped provider source is
# available; an empty list would falsely imply a known absence of capability.
_PROVIDER_FIELDS = (
    "order_types", "fill_policies", "expiries", "stop_mode", "hedging_netting",
    "minimum_lot", "instruments", "regulator", "account_currencies",
    "minimum_deposit", "open_account_url",
)

_ADDITIONAL_REQUIREMENTS = (
    ("VFEX", "VAN master 7.9.2 requires VFEX owner-ticket linking; a distinct native VFEX provider is not admitted here."),
    ("CEX_SPOT", "BE-004 requires an eligible versioned CEX spot integration and real matching, settlement, protection and recovery; no adapter eligibility is established by this directory."),
)
_CEX_REQUIREMENTS = ("VAN-CRYPTO-001", "VAN-CRYPTO-002", "VAN-CRYPTO-013", "VAN-RV-008")
_CEX_IDENTITIES = ("api_family", "account_subaccount", "native_product", "spot_type",
                   "base", "quote", "network")


class _DirectoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnknownProviderFact(_DirectoryModel):
    state: Literal["UNKNOWN"]
    value: None
    provenance: Literal["NO_ADMITTED_PROVIDER_SOURCE"]
    freshness: Literal["NOT_OBSERVED"]


class DirectoryLink(_DirectoryModel):
    method: str | None
    action: str | None
    state: Literal["SOURCE_IMPLEMENTED", "REQUIRED_UNQUALIFIED"]
    provenance: str
    freshness: Literal["NOT_PROVIDER_READBACK"]
    reason: str | None = None


class DirectoryDemo(_DirectoryModel):
    state: Literal["SOURCE_IMPLEMENTED", "PROVIDER_ADMISSION_REQUIRED", "UNKNOWN"]
    action: str | None = None
    value: None = None
    provenance: str
    freshness: Literal["NOT_PROVIDER_READBACK", "NOT_OBSERVED"]


class DirectoryOperation(_DirectoryModel):
    state: str
    reason: str
    authority: str
    action: str | None


class DirectoryFamily(_DirectoryModel):
    family: Literal["CTRADER", "DERIV", "MT5", "MT5_EA", "PAPER", "ZSE_OWNER_TICKET", "VFEX", "CEX_SPOT"]
    native_broker_kind: str | None
    family_state: Literal["SOURCE_FAMILY", "REQUIRED_UNADMITTED"]
    linking: DirectoryLink
    additional_linking_requirements: list[DirectoryLink]
    demo_availability: DirectoryDemo
    capabilities: dict[str, UnknownProviderFact]
    operations: dict[str, DirectoryOperation] | None
    operations_provenance: str
    canonical_requirements: list[str] | None = None
    required_versioned_identity: dict[str, UnknownProviderFact] | None = None


class DirectoryRevision(_DirectoryModel):
    algorithm: Literal["SHA-256"]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: Literal["SOURCE_PROJECTION_CONTENT"]
    freshness: Literal["NOT_PROVIDER_READBACK"]


class BrokerDirectoryResponse(_DirectoryModel):
    schema_name: Literal["van.broker-directory/1"] = Field(alias="schema")
    source: Literal["VAN_ACCOUNT_SOURCE"]
    freshness: Literal["NOT_PROVIDER_READBACK"]
    execution_authority: Literal[False]
    content_revision: DirectoryRevision
    families: list[DirectoryFamily]


def _unknown():
    return {"state": "UNKNOWN", "value": None,
            "provenance": "NO_ADMITTED_PROVIDER_SOURCE", "freshness": "NOT_OBSERVED"}


def broker_directory() -> dict:
    """Return a fresh deterministic, JSON-safe projection of source families.

    Callers must apply their own existing authenticated read boundary. The
    result is neither provider readback nor permission to execute an action.
    """
    if set(_METHODS) != set(BROKER_NAMES):
        raise RuntimeError("Broker directory source family inventory changed")
    rows = []
    for family in sorted(BROKER_NAMES):
        method, action = _METHODS[family]
        operations = capabilities_for(broker=family, demo=True, safety_identity="READ ONLY")
        demo = operations["create_demo"]
        rows.append({
            "family": family,
            "native_broker_kind": family,
            "family_state": "SOURCE_FAMILY",
            "linking": {"method": method, "action": action,
                        "state": "SOURCE_IMPLEMENTED", "provenance": "VAN_ACCOUNT_SOURCE",
                        "freshness": "NOT_PROVIDER_READBACK"},
            "additional_linking_requirements": ([{
                "method": "INVESTOR_PASSWORD_READ_ONLY", "action": None,
                "state": "REQUIRED_UNQUALIFIED", "provenance": "VAN_MASTER_7_9_2",
                "freshness": "NOT_PROVIDER_READBACK",
                "reason": "Investor-password observation requires an independently qualified native binding."
            }] if family in {"MT5", "MT5_EA"} else []),
            "demo_availability": {"state": "SOURCE_IMPLEMENTED" if family in {"DERIV", "PAPER"}
                                  else "PROVIDER_ADMISSION_REQUIRED",
                                  "action": demo["action"],
                                  "provenance": "VAN_ACCOUNT_OPERATION_POLICY",
                                  "freshness": "NOT_PROVIDER_READBACK"},
            "capabilities": {field: _unknown() for field in _PROVIDER_FIELDS},
            "operations": operations,
            "operations_provenance": "SOURCE_POLICY_ONLY_NOT_CURRENT_ADMISSION",
        })
    for family, reason in _ADDITIONAL_REQUIREMENTS:
        row = {
            "family": family, "native_broker_kind": None, "family_state": "REQUIRED_UNADMITTED",
            "linking": {"method": "OWNER_TICKET" if family == "VFEX" else None,
                        "action": None, "state": "REQUIRED_UNQUALIFIED",
                        "provenance": "VAN_MASTER_7_9_2" if family == "VFEX" else "BE_004_CRYPTO_REQUIREMENTS",
                        "freshness": "NOT_PROVIDER_READBACK", "reason": reason},
            "additional_linking_requirements": [],
            "demo_availability": _unknown(),
            "capabilities": {field: _unknown() for field in _PROVIDER_FIELDS},
            "operations": None,
            "operations_provenance": "NO_ADMITTED_PROVIDER_SOURCE",
        }
        if family == "CEX_SPOT":
            row["canonical_requirements"] = list(_CEX_REQUIREMENTS)
            row["required_versioned_identity"] = {key: _unknown() for key in _CEX_IDENTITIES}
        rows.append(row)
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return {"schema": "van.broker-directory/1", "source": "VAN_ACCOUNT_SOURCE",
            "freshness": "NOT_PROVIDER_READBACK", "execution_authority": False,
            "content_revision": {"algorithm": "SHA-256", "digest": hashlib.sha256(encoded).hexdigest(),
                                 "scope": "SOURCE_PROJECTION_CONTENT", "freshness": "NOT_PROVIDER_READBACK"},
            "families": rows}
