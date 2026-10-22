"""Account identity for risk recovery, without rewriting historical facts.

Only native input/order records can bind an old unlabelled trade review.
Configured account names and the set of accounts seen so far are not evidence
of ownership. Unbound or contradictory financial history stays unresolved.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from vati.core.canonical import canonical_hash


NATIVE_PRODUCERS = {
    "RISK_DECISION": frozenset({"vati-cycle", "vati-account-coordinator"}),
    "ORDER_COMMAND": frozenset({"vati-execution-router"}),
    "TRADE_REVIEW": frozenset({"vati-cycle", "vati-account-lifecycle"}),
    "SESSION": frozenset({"vati-cycle", "vati-account-service"}),
}
CONTROL_EVENTS = frozenset({"LOSS_STREAK_RESET", "DRAWDOWN_RESUMED"})


class RiskHistoryScopeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccountRiskHistory:
    events: tuple
    unresolved_refs: tuple[str, ...]

    @property
    def issue(self):
        return (f"account risk history has {len(self.unresolved_refs)} unresolved, unbound or conflicting records; native reconciliation required"
                if self.unresolved_refs else "")


def risk_history_for_account(events, account_alias: str) -> AccountRiskHistory:
    if not isinstance(account_alias, str) or not account_alias.strip():
        raise ValueError("risk recovery requires an explicit account alias")
    rows = list(events)
    bindings: dict[str, set[str]] = {}
    binding_refs: dict[str, list[str]] = {}
    invalid = set()
    relevant = []
    for event in rows:
        kind = getattr(event.kind, "value", event.kind)
        if kind not in NATIVE_PRODUCERS:
            continue
        p = event.payload
        if not isinstance(p, dict):
            invalid.add(event.hash)
            continue
        if kind == "SESSION":
            if p.get("event") is None:
                continue  # ordinary router/diagnostic session payload
            if not isinstance(p.get("event"), str):
                invalid.add(event.hash)
                continue
            if p["event"] not in CONTROL_EVENTS:
                continue
        if event.hash != canonical_hash(event.body()) or event.producer not in NATIVE_PRODUCERS[kind]:
            invalid.add(event.hash)
            continue
        if kind == "TRADE_REVIEW":
            if p.get("record_revision", 0) != 0 or type(p.get("record_revision", 0)) is not int:
                invalid.add(event.hash)
                continue  # revisions use their own analytical channel, never a second financial close
            try:
                valid = (isinstance(p.get("strategy_id"), str) and bool(p["strategy_id"])
                         and Decimal(str(p["pnl"])).is_finite()
                         and p.get("broker_ok") is not False
                         and p.get("outcome") not in {"UNKNOWN", "BROKER_FAILURE"}
                         and not str(p.get("pnl_basis", "")).startswith("UNKNOWN"))
            except (KeyError, ValueError, InvalidOperation):
                valid = False
            if not valid:
                invalid.add(event.hash)
                continue
        if kind != "ORDER_COMMAND":
            relevant.append(event)
        if kind not in {"RISK_DECISION", "ORDER_COMMAND"}:
            continue
        inputs = p.get("inputs")
        intent = inputs.get("intent") if kind == "RISK_DECISION" and isinstance(inputs, dict) else (p if kind == "ORDER_COMMAND" else None)
        if not isinstance(intent, dict):
            invalid.add(event.hash)
            continue
        alias = intent.get("account_alias")
        explicit = p.get("account_alias")
        trade = intent.get("trade_intent_id") or event.correlation_id
        if (not isinstance(alias, str) or not alias or not trade or trade != event.correlation_id
            or (explicit is not None and explicit != alias)):
            invalid.add(event.hash)
            continue
        bindings.setdefault(trade, set()).add(alias)
        binding_refs.setdefault(trade, []).append(event.hash)

    for trade, owners in bindings.items():
        if len(owners) != 1:
            invalid.update(binding_refs[trade])

    selected = []
    for event in relevant:
        if event.hash in invalid:
            continue
        p = event.payload
        kind = getattr(event.kind, "value", event.kind)
        explicit = p.get("account_alias")
        if kind == "RISK_DECISION":
            explicit = ((p.get("inputs") or {}).get("intent") or {}).get("account_alias")
        if kind == "TRADE_REVIEW" and p.get("trade_intent_id") not in (None, "", event.correlation_id):
            invalid.add(event.hash)
            continue
        owners = set(bindings.get(event.correlation_id, ())) if kind != "SESSION" else set()
        if explicit is not None and explicit != "":
            if not isinstance(explicit, str) or not explicit:
                invalid.add(event.hash)
                continue
            owners.add(explicit)
        if len(owners) != 1:
            invalid.add(event.hash)
        elif account_alias in owners:
            selected.append(event)
    return AccountRiskHistory(tuple(selected), tuple(sorted(invalid)))
