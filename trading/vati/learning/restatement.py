"""Native parent-level trade observations, with separate original/restated views.

This reducer owns analytical evidence only. It never changes a mandate, model
binding, order or the immutable evidence an earlier decision actually used.
"""
from __future__ import annotations

import json
from decimal import Decimal, localcontext, ROUND_HALF_EVEN

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import EventKind
from vati.core.ledger import GENESIS, LedgerError, history_through
from vati.execution.review import initial_risk_from_ledger
from vati.learning.projection_store import ProjectionStore, ProjectionCorrupt, ProjectionConflict
from vati.learning.scope import FACT_PRODUCERS


CODE_VERSION = "native-trade-restatement/1.0.0"
POPULATION = "mature-parent-net-pnl-over-original-approved-money-risk/1"
NUMERIC_PRECISION = "decimal-50-half-even"
FINALITY_FLAGS = ("parent_final", "fees_final", "cash_reconciled")


class ObservationError(ValueError):
    pass


def _decimal(value):
    if isinstance(value, (bool, float)) or value is None:
        raise ObservationError("observation number is missing or inexact")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ObservationError("observation number is nonfinite")
    return result


class _AvailableSource:
    def __init__(self, rows):
        self.rows = tuple(rows)

    def iter(self, kind=None, correlation_id=None):
        return iter(row for row in self.rows if (kind is None or row.kind is kind)
                    and (correlation_id is None or row.correlation_id == correlation_id))


class RestatedTradeProjection:
    def __init__(self, ledger, native_scope, *, fault=None):
        if native_scope is None or native_scope.ledger is not ledger:
            raise ValueError("trade projection requires its native runtime account/cohort")
        self.ledger, self.native_scope = ledger, native_scope
        self.scope = {"account_alias": native_scope.account_alias,
                      "environment": native_scope.environment.value,
                      "population_definition": POPULATION, "code_version": CODE_VERSION,
                      "numeric_precision": NUMERIC_PRECISION}
        self.store = ProjectionStore(ledger, self.scope, fault=fault)
        self.snapshot = None
        self.recovery_reason = ""

    @staticmethod
    def empty_state():
        return {"parents": {}, "applied": {}, "unresolved_scope_refs": [],
                "view": "RESTATED_ANALYSIS", "as_decided_preserved": True}

    def _contribution(self, event):
        p = event.payload
        maturity = p.get("maturity")
        if (p.get("review_version") != "trade-review/5.2.0" or not isinstance(maturity, dict)
            or any(maturity.get(flag) is not True for flag in FINALITY_FLAGS)):
            return None, "IMMATURE_REQUIRED_LABELS"
        if maturity.get("source_environment") != self.native_scope.environment.value:
            return None, "SOURCE_ENVIRONMENT_UNPROVEN"
        if (p.get("broker_ok") is not True or p.get("r_basis") != "NET_PNL_OVER_APPROVED_MONEY_RISK"
            or p.get("outcome") == "UNKNOWN" or p.get("pnl_basis") not in {
                "REPORTED_GROSS_NET_RECORDED_CHARGES", "PRICE_DERIVED_NET_RECORDED_CHARGES", "REPORTED_NET_CONFIRMED"}):
            return None, "ECONOMIC_OUTCOME_UNRESOLVED"
        rows = history_through(self.ledger, event.correlation_id, event.hash)
        risk = initial_risk_from_ledger(_AvailableSource(rows), event.correlation_id)
        if risk is None or p.get("initial_risk_evidence_ref") != risk.evidence_ref:
            return None, "ORIGINAL_MONEY_RISK_UNRESOLVED"
        amount, pnl = _decimal(p.get("initial_money_risk")), _decimal(p.get("pnl"))
        if amount <= 0 or amount != risk.amount:
            raise ObservationError("review money risk disagrees with original approval")
        source_ref = risk.evidence_ref.removeprefix("risk-decision://")
        decision = next(row for row in rows if row.hash == source_ref)
        inputs = decision.payload["inputs"]
        if inputs["intent"]["strategy_id"] != p.get("strategy_id"):
            raise ObservationError("review strategy disagrees with native intent")
        contract = inputs["snapshot"]["symbol_contract"]
        currency = contract["account_currency"]
        if not isinstance(currency, str) or not currency.strip():
            raise ObservationError("native account currency is missing")
        if maturity.get("account_currency") != currency:
            return None, "SOURCE_CURRENCY_UNPROVEN"
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            net_r = pnl / amount
            if _decimal(p.get("r_multiple")) != net_r.quantize(Decimal("0.01")):
                raise ObservationError("review return multiple disagrees with native cash and approved risk")
        return {"net_pnl": str(pnl), "initial_money_risk": str(amount), "net_r": str(net_r),
                "currency": currency, "strategy_id": p["strategy_id"],
                "source_ref": event.hash, "risk_evidence_ref": risk.evidence_ref}, "MATURE"

    def _apply(self, state, event):
        if event.kind not in {EventKind.TRADE_REVIEW, EventKind.TRADE_REVIEW_REVISION}:
            return
        if event.hash in state["applied"]:
            return
        if event.producer not in FACT_PRODUCERS:
            state["applied"][event.hash] = "DISALLOWED_SOURCE"
            return
        if not self.native_scope.admit(event):
            unresolved = event.hash in self.native_scope.unresolved_refs
            state["applied"][event.hash] = "UNRESOLVED_SCOPE" if unresolved else "EXCLUDED_SCOPE"
            if unresolved:
                state["unresolved_scope_refs"] = sorted(set(state["unresolved_scope_refs"]) | {event.hash})
            return
        p = event.payload
        identity = event.correlation_id
        parent = state["parents"].setdefault(identity, {
            "versions": {}, "head_revision": -1, "head_digest": None,
            "original": None, "current": None, "quarantine": None, "maturity": "UNRESOLVED",
        })
        try:
            digest = p.get("artifact_hash")
            if not isinstance(digest, str) or digest != canonical_hash({k: v for k, v in p.items() if k != "artifact_hash"}):
                raise ObservationError("native review seal mismatch")
            revision = p.get("record_revision", 0)
            predecessor = p.get("supersedes_review_ref")
            if (event.kind is EventKind.TRADE_REVIEW and revision != 0
                or event.kind is EventKind.TRADE_REVIEW_REVISION and revision == 0):
                raise ObservationError("review revision used the wrong source channel")
            if type(revision) is not int or revision < 0 or (predecessor is not None and not isinstance(predecessor, str)):
                raise ObservationError("native review revision is invalid")
            known = parent["versions"].get(str(revision))
            if known is not None:
                if known != digest:
                    raise ObservationError("equal native revision has conflicting content")
                state["applied"][event.hash] = "DUPLICATE_OR_OLDER_REVISION"
                return
            parent["versions"][str(revision)] = digest
            if parent["quarantine"]:
                state["applied"][event.hash] = "RECONCILIATION_REQUIRED"
                return
            if revision != parent["head_revision"] + 1 or predecessor != parent["head_digest"]:
                raise ObservationError("native revision predecessor is missing or incompatible")
            with localcontext() as context:
                context.prec = 50
                context.rounding = ROUND_HALF_EVEN
                contribution, maturity = self._contribution(event)
            parent.update(head_revision=revision, head_digest=digest,
                          current=contribution, maturity=maturity, source_ref=event.hash)
            if revision == 0:
                parent["original"] = contribution
            state["applied"][event.hash] = "APPLIED_" + maturity
        except (ObservationError, ValueError, KeyError, TypeError, ArithmeticError, StopIteration) as exc:
            parent["quarantine"] = str(exc)[:200]
            parent["current"] = None
            state["applied"][event.hash] = "QUARANTINED"

    @staticmethod
    def _aggregate(state, view):
        populations = {}
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            for identity, parent in sorted(state["parents"].items()):
                value = parent["original" if view == "AS_DECIDED" else "current"]
                if value is None:
                    continue
                key = value["currency"]
                population = populations.setdefault(key, {"count": 0, "net_pnl": "0", "initial_money_risk": "0", "net_r": "0"})
                population["count"] += 1
                for field in ("net_pnl", "initial_money_risk", "net_r"):
                    population[field] = str(_decimal(population[field]) + _decimal(value[field]))
        return populations

    def _validate_state(self, snapshot):
        state = snapshot["state"]
        if (state.get("view") != "RESTATED_ANALYSIS" or state.get("as_decided_preserved") is not True
            or not isinstance(state.get("parents"), dict) or not isinstance(state.get("applied"), dict)
            or not isinstance(state.get("unresolved_scope_refs"), list)):
            raise ProjectionCorrupt("trade projection state contract mismatch")
        expected = {"AS_DECIDED": self._aggregate(state, "AS_DECIDED"),
                    "RESTATED_ANALYSIS": self._aggregate(state, "RESTATED_ANALYSIS")}
        if state.get("aggregates") != expected:
            raise ProjectionCorrupt("trade projection contribution aggregate mismatch")
        fingerprint = canonical_hash({"scope": self.scope, "parents": state["parents"],
                                      "unresolved_scope_refs": state["unresolved_scope_refs"], "aggregates": expected})
        if state.get("learned_state_hash") != fingerprint:
            raise ProjectionCorrupt("trade projection learned-state seal mismatch")

    def catch_up(self):
        """Replay source facts only; a damaged cache cannot become fresh healthy state."""
        if not self.ledger.verify_chain()[0]:
            raise ProjectionCorrupt("native source journal failed integrity verification")
        recovery = ""
        recovery_expected = None
        try:
            snapshot = self.store.load()
            if snapshot is not None:
                self._validate_state(snapshot)
        except (ProjectionCorrupt, ValueError, KeyError, TypeError, ArithmeticError) as exc:
            pointer = self.store._pointer()
            recovery_expected = pointer[1] if pointer else None
            snapshot = None
            recovery = "verified_native_source_rebuild:" + type(exc).__name__
        while True:
            state = json.loads(canonical_json(snapshot["state"])) if snapshot is not None else self.empty_state()
            after = snapshot["cursor"]["seq"] if snapshot is not None else 0
            rows = self.store.publication_rows(after)
            if not rows and snapshot is not None:
                self.snapshot = snapshot
                return self.summary()
            for sequence, event, chain_hash in rows:
                self._apply(state, event)
            state["aggregates"] = {"AS_DECIDED": self._aggregate(state, "AS_DECIDED"),
                                   "RESTATED_ANALYSIS": self._aggregate(state, "RESTATED_ANALYSIS")}
            state["learned_state_hash"] = canonical_hash({"scope": self.scope, "parents": state["parents"],
                "unresolved_scope_refs": state["unresolved_scope_refs"], "aggregates": state["aggregates"]})
            cursor = rows[-1][0] if rows else 0
            chain = rows[-1][2] if rows else GENESIS
            updated = self.store.envelope(state, cursor_seq=cursor, cursor_hash=chain)
            try:
                self.store.save(updated, expected_hash=recovery_expected if recovery else snapshot["snapshot_hash"] if snapshot else None,
                                recovery_reason=recovery)
            except ProjectionConflict:
                snapshot = self.store.load()
                if snapshot is not None:
                    self._validate_state(snapshot)
                continue
            snapshot = updated
            self.recovery_reason = recovery or self.recovery_reason
            recovery = ""
            if len(rows) < 256:
                self.snapshot = snapshot
                return self.summary()

    def summary(self):
        if self.snapshot is None:
            return {"status": "NOT_RECONSTRUCTED", "selection_authority": False}
        state = self.snapshot["state"]
        quarantined = sum(bool(parent["quarantine"]) for parent in state["parents"].values())
        immature = sum(parent["current"] is None and not parent["quarantine"] for parent in state["parents"].values())
        status = ("RECONCILIATION_REQUIRED" if quarantined or state["unresolved_scope_refs"] else
                  "MATURITY_PENDING" if immature else "ANALYSIS_ONLY" if state["parents"] else "NO_OBSERVATIONS")
        return {"status": status,
                "scope": self.scope, "cursor": self.snapshot["cursor"],
                "snapshot_hash": self.snapshot["snapshot_hash"], "learned_state_hash": state["learned_state_hash"],
                "views": state["aggregates"], "parent_count": len(state["parents"]),
                "quarantined_parents": quarantined, "immature_parents": immature, "unresolved_scope_count": len(state["unresolved_scope_refs"]),
                "selection_authority": False, "as_decided_preserved": True,
                "recovery_reason": self.recovery_reason}
