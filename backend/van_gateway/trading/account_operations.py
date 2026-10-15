"""Read-only, fail-closed account operation capabilities for the VAN Next trading UI.

This module makes the distinction between VAN-local account registry actions and
broker-owned account provisioning/money movement explicit. A source capability is
never inferred from an APK class, UI button, brokerage brand, or model output.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

# A provider feature can be documented without being installed, authenticated,
# and approved for owner execution in this deployment.
ENABLED = "OWNER_SIGNED_ACTION"
NEEDS_PROVIDER = "PROVIDER_ADMISSION_REQUIRED"
NEEDS_EXPOSURE = "EXPOSURE_READBACK_REQUIRED"
READ_ONLY = "READ_ONLY"
UNSUPPORTED = "UNSUPPORTED"

ALIAS_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")

BROKER_NAMES = frozenset({"PAPER", "DERIV", "CTRADER", "MT5", "MT5_EA", "ZSE_OWNER_TICKET"})

OPERATIONS = (
    "link_existing", "create_demo", "request_live", "edit_local", "edit_broker",
    "rotate_credentials", "unlink_local", "close_broker", "deposit", "withdraw",
    "transfer", "transactions", "kyc_status", "change_leverage", "change_password",
)


@dataclass(frozen=True)
class AccountOperation:
    state: str
    reason: str
    authority: str
    action: str | None = None

    def public(self) -> dict[str, str | None]:
        return {"state": self.state, "reason": self.reason, "authority": self.authority, "action": self.action}


def _operation(state: str, reason: str, authority: str, action: str | None = None) -> AccountOperation:
    return AccountOperation(state=state, reason=reason, authority=authority, action=action)


def capabilities_for(*, broker: str, demo: bool, safety_identity: str) -> dict[str, dict[str, str | None]]:
    """Conservative *deployment* availability, not theoretical vendor API support."""
    kind = broker.strip().upper()
    if kind not in BROKER_NAMES:
        return {name: _operation(UNSUPPORTED, "Unknown broker: no admission or financial access.", "NONE").public() for name in OPERATIONS}

    enabled_local = lambda action, label: _operation(ENABLED, label, "VAN_OWNER_A4", action)
    provider = lambda label: _operation(NEEDS_PROVIDER, label, "BROKER_OR_PAYMENT_PROVIDER")
    operations = {
        "link_existing": enabled_local("oauth_start", "Existing broker linking is available through the signed VAN onboarding flow.") if kind in ("DERIV", "CTRADER") else
            enabled_local("account_upsert", "Register an existing broker or paper account through signed onboarding."),
        "create_demo": enabled_local("deriv_create_demo", "Deriv demo creation is implemented; live provider acceptance still must be verified.") if kind == "DERIV" else
            enabled_local("account_upsert", "Create a local paper-trading account; no real funds.") if kind == "PAPER" else
            provider("New demo accounts require the broker's verified registration service."),
        "request_live": provider("A live account must be opened or approved by the broker; KYC and eligibility are broker-owned."),
        "edit_local": enabled_local("account_upsert", "Edit VAN-local account configuration with exact owner approval."),
        "edit_broker": provider("Broker-side account details require a verified broker account-management API or session."),
        "rotate_credentials": enabled_local("account_credentials", "Update stored broker credentials through owner-approved account action.") if kind in ("DERIV", "CTRADER", "MT5", "MT5_EA") else
            _operation(UNSUPPORTED, "No broker credentials are stored for this account type.", "NONE"),
        "unlink_local": _operation(NEEDS_EXPOSURE, "Require current position/order/protection and lease readback before unlinking; unlinking never closes the broker account.", "BROKER_AND_VATI_RECONCILIATION"),
        "close_broker": provider("Broker account closure is distinct from removing a VAN connection and requires broker verification."),
        "deposit": provider("No qualified funding adapter, payment authorization or broker receipt readback is connected."),
        "withdraw": provider("No qualified withdrawal adapter, beneficiary verification or broker receipt readback is connected."),
        "transfer": provider("No qualified same-owner wallet/platform transfer adapter or fresh quote/receipt is connected."),
        "transactions": provider("Financial history must come from an admitted broker/payment transaction source, not the trading ledger."),
        "kyc_status": provider("Account verification/KYC remains with the broker or an admitted KYC service."),
        "change_leverage": provider("Leverage and margin account type are broker-owned; no in-app provider mutation is admitted."),
        "change_password": provider("Changing the broker password requires an authenticated provider protocol; updating VAN's secret reference is different."),
    }
    if kind == "DERIV":
        # Deriv documents payment-scoped wallet transfers, but the current VAN
        # legacy account tokens are not verified for the newer OAuth payment scope.
        for action in ("deposit", "withdraw", "transfer", "transactions"):
            operations[action] = provider("Deriv documents wallet/platform APIs; payment-scoped OAuth, adapter, idempotency and readback are not yet qualified in VAN.")
    if kind in ("MT5", "MT5_EA"):
        for action in ("deposit", "withdraw", "transactions"):
            operations[action] = provider("MT5 payment availability depends on the selected broker; an EA bridge is not a payment authority.")
    if kind == "PAPER":
        for action in ("deposit", "withdraw", "transfer", "transactions"):
            operations[action] = _operation(UNSUPPORTED, "Paper accounts have no real funding or withdrawal capability.", "NONE")
        operations["close_broker"] = _operation(UNSUPPORTED, "This is a VAN-local simulation account, not a broker account.", "NONE")
    # Safety identity is never a shortcut for funding or live trading privileges.
    if safety_identity == "READ ONLY":
        for action in ("deposit", "withdraw", "transfer"):
            if operations[action].state == ENABLED:
                operations[action] = provider("READ ONLY identity cannot authorize money movement.")
    return {name: operations[name].public() for name in OPERATIONS}


def account_operations_snapshot(account: Mapping[str, Any]) -> dict[str, Any]:
    """Generate a read-only projection from a validated, non-secret registry record."""
    alias = account.get("alias")
    broker = account.get("broker")
    if not isinstance(alias, str) or not ALIAS_PATTERN.fullmatch(alias):
        raise ValueError("account alias is invalid")
    if not isinstance(broker, str) or broker.upper() not in BROKER_NAMES:
        raise ValueError("account broker is invalid")
    safety = str(account.get("safety_identity") or "UNKNOWN")
    return {
        "schema_version": 1,
        "account_alias": alias,
        "broker": broker.upper(),
        "label": str(account.get("label") or alias),
        "currency": str(account.get("currency") or ""),
        "mode": str(account.get("mode") or ""),
        "demo": bool(account.get("demo", True)),
        "safety_identity": safety,
        "operation_source": "VAN_REGISTRY_AND_ADMISSION_POLICY",
        "reconciliation": "UNVERIFIED_FOR_FINANCIAL_ACTIONS",
        "operations": capabilities_for(broker=broker, demo=bool(account.get("demo", True)), safety_identity=safety),
    }
