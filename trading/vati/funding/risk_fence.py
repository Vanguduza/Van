"""Native funding evidence is a precondition, never an order permission.

Raw equity risk baselines are usable only while original complete native
history proves no external capital or unrelated business-income change. A
capital-changing period needs qualified flow-adjusted risk accounting; this
fence never guesses a new loss baseline from the larger current balance.
"""
from dataclasses import dataclass
from decimal import Decimal

from vati.core.events import EventKind
from vati.core.ledger import committed_source_snapshot
from vati.funding.classification import classify
from vati.funding.journal import FundingBook
from vati.funding.native import NativeAccountMark, native_int
from vati.funding.reconciliation import period_report
from vati.risk.history_scope import risk_history_for_account


@dataclass(frozen=True)
class FundingRiskFence:
    available: bool
    reason: str


def funding_risk_fence(ledger, adapter, account, *, now_ms):
    """Read original facts only; no native read/send or baseline mutation here."""
    from vati.execution.paper import PaperAdapter
    from vati.execution.zse_ticket import OwnerTicketAdapter
    if isinstance(adapter, PaperAdapter):
        return FundingRiskFence(True, "")  # Explicit simulation, not a venue label.
    if isinstance(adapter, OwnerTicketAdapter):
        # This adapter drafts an A4 ticket; submit() sends no broker operation
        # and fills zero quantity. Signed owner reconciliation is separate.
        return FundingRiskFence(True, "OWNER_TICKET_DRAFT_ONLY_NO_NATIVE_SUBMISSION")
    try:
        with committed_source_snapshot(ledger):
            from vati.execution.mt5_pull import Mt5PullAdapter
            from vati.execution.mt5_bridge import Mt5BridgeAdapter
            if isinstance(adapter,(Mt5PullAdapter,Mt5BridgeAdapter)):
                from vati.funding.mt5_runtime import mt5_risk_fence
                return mt5_risk_fence(ledger,adapter,account,now_ms=now_ms)
            return _native_fence(ledger, adapter, account, now_ms=now_ms)
    except Exception as exc:
        # A journal/read failure holds new risk without leaking provider notes
        # or disabling the independent position-protection path.
        return FundingRiskFence(False, "FUNDING_RISK_EVIDENCE_UNAVAILABLE:" + type(exc).__name__[:64])


def _native_fence(ledger, adapter, account, *, now_ms):
    from vati.execution.ctrader.adapter import CtraderAdapter
    from vati.execution.ctrader.transport import DEMO_HOST, LIVE_HOST
    def hold(reason):
        return FundingRiskFence(False, "FUNDING_RISK_UNAVAILABLE:" + reason)
    if not isinstance(adapter, CtraderAdapter):
        return hold("NATIVE_PROVIDER_ACCOUNTING_NOT_IMPLEMENTED")
    mark = getattr(account, "funding_mark", None)
    if not isinstance(mark, NativeAccountMark):
        return hold("CURRENT_NATIVE_MARK_UNAVAILABLE")
    mark = NativeAccountMark.from_body(mark.body())
    native_int(now_ms, minimum=0)
    if now_ms < mark.observed_at_ms:
        return hold("CURRENT_NATIVE_MARK_AFTER_DECISION_TIME")
    environment = {DEMO_HOST: "DEMO", LIVE_HOST: "LIVE"}.get(getattr(adapter.transport, "host", None))
    if (account.verified is not True or mark.account_alias != account.account_alias
        or mark.account_alias != adapter.account_alias or mark.native_account_id != adapter.ctid_trader_account_id
        or mark.environment != environment or mark.currency != account.currency
        or mark.balance != account.balance or mark.net_equity != account.equity):
        return hold("CURRENT_NATIVE_ACCOUNT_BINDING_INVALID")
    with ledger.read_snapshot():
        period = period_report(ledger, mark.scope_hash)
        if (period.get("knowledge_through_received_ms") is not None
            and period["knowledge_through_received_ms"] > now_ms):
            return hold("NATIVE_FUNDING_AFTER_DECISION_TIME")
        if period["balance_state"] != "RECONCILED":
            return hold(period["reason"] or "NATIVE_BALANCE_UNRECONCILED")
        if period["external_flows"]:
            return hold("FLOW_ADJUSTED_RISK_NOT_QUALIFIED")
        if period["state"] != "MEASURED":
            return hold(period["reason"] or "NATIVE_PERIOD_UNMEASURED")
        originals = {e.hash: e for e in ledger.iter(EventKind.ACCOUNT_SNAPSHOT)
                     if e.hash in {period["baseline_ref"], period["closing_ref"]}}
        first, last = originals[period["baseline_ref"]], originals[period["closing_ref"]]
        baseline = NativeAccountMark.from_body(first.payload["native_account_mark"])
        closing = NativeAccountMark.from_body(last.payload["native_account_mark"])
        if (mark.balance_version is None or mark.balance_version != closing.balance_version
            or mark.balance != closing.balance or mark.observed_at_ms < closing.observed_at_ms):
            return hold("CURRENT_NATIVE_BALANCE_CHANGES_NOT_COVERED")
        # Equal native balance version proves no newer balance change. Current
        # native unrealized PnL may change after the older covered observation;
        # it is never frozen to the background collector's earlier valuation.
        facts = FundingBook(ledger).observations(mark.scope_hash)
        for observed in facts["movements"]:
            row = observed["movement"]
            version = row["balance_version"]
            if (version is not None and baseline.balance_version < version <= closing.balance_version
                and Decimal(row["delta"]) != 0
                and classify(row["operation"], Decimal(row["delta"]))["category"] == "OTHER_BUSINESS_INCOME_OR_EXPENSE"):
                return hold("BUSINESS_INCOME_REQUIRES_RISK_NORMALIZATION")
        history = risk_history_for_account(ledger.iter(), mark.account_alias)
        if history.issue:
            return hold("ORIGINAL_RISK_HISTORY_UNRESOLVED")
        for event in history.events:
            if max(event.event_time_ms, event.received_time_ms) > now_ms:
                return hold("ORIGINAL_RISK_AFTER_DECISION_TIME")
            if event.kind not in {EventKind.RISK_DECISION, EventKind.TRADE_REVIEW}:
                continue
            if event.kind == EventKind.RISK_DECISION and event.payload.get("decision", {}).get("decision") == "REJECTED":
                continue
            if event.event_time_ms < baseline.observed_at_ms or event.received_time_ms < first.received_time_ms:
                return hold("ORIGINAL_RISK_PREDATES_NATIVE_FUNDING_BASELINE")
        for event in ledger.iter(EventKind.ORDER_COMMAND):
            if (event.payload.get("account_alias") == mark.account_alias
                and (event.event_time_ms < baseline.observed_at_ms or event.received_time_ms < first.received_time_ms)):
                return hold("ORIGINAL_ORDER_PREDATES_NATIVE_FUNDING_BASELINE")
        return FundingRiskFence(True, "NATIVE_FUNDING_NO_CAPITAL_CHANGE:" + first.hash + ":" + last.hash)
