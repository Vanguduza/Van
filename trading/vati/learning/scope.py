"""Native account/cohort identity at the availability of a learning source.

Configuration selects a consumer; it does not assign ownership to old records.
Unknown identity is kept unresolved instead of resetting a learned restriction.
"""
from dataclasses import dataclass, field

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.core.ledger import history_through, LedgerError
from vati.learning.episodes import Environment
from vati.risk.mandate import AuthorizationMode


ENVIRONMENT_FOR_MODE = {
    AuthorizationMode.OBSERVE: Environment.SHADOW,
    AuthorizationMode.ADVISOR: Environment.SHADOW,
    AuthorizationMode.DEMO_TRADER: Environment.DEMO,
    AuthorizationMode.SHADOW_TRADER: Environment.SHADOW,
    AuthorizationMode.LIMITED_LIVE: Environment.LIMITED_LIVE,
    AuthorizationMode.AUTONOMOUS_LIVE: Environment.LIVE,
    AuthorizationMode.HALTED: Environment.SHADOW,
}
RISK_PRODUCERS = frozenset({"vati-cycle", "vati-account-coordinator"})
FACT_PRODUCERS = frozenset({"vati-cycle", "vati-account-lifecycle"})


class LearningScopeError(ValueError):
    pass


@dataclass
class LearningScope:
    ledger: object
    account_alias: str
    environment: Environment
    unresolved_refs: set[str] = field(default_factory=set)
    excluded_refs: set[str] = field(default_factory=set)

    def __post_init__(self):
        if not isinstance(self.account_alias, str) or not self.account_alias.strip():
            raise ValueError("learning requires an explicit account alias")
        self.environment = Environment(self.environment)

    @property
    def issue(self):
        return (f"learning history has {len(self.unresolved_refs)} unbound or conflicting records; native reconciliation required"
                if self.unresolved_refs else "")

    def admit(self, event, *, trade_id: str | None = None) -> bool:
        """True for this native cohort, False for known other cohorts or unresolved rows.

        Only the original source prefix is read. A later guessed account or
        correction cannot rewrite what was available when learning occurred.
        """
        try:
            return self._admit(event, trade_id or event.correlation_id)
        except (LearningScopeError, LedgerError, ValueError, KeyError, TypeError, AttributeError):
            self.unresolved_refs.add(event.hash)
            return False

    def _admit(self, event, trade_id: str) -> bool:
        if not isinstance(trade_id, str) or not trade_id:
            raise LearningScopeError("learning source has no trade identity")
        if event.hash != canonical_hash(event.body()):
            raise LearningScopeError("learning source seal mismatch")
        rows = history_through(self.ledger, trade_id, event.hash)
        owners = set()
        environments = set()
        for row in rows:
            p = row.payload
            if row.kind is EventKind.RISK_DECISION and row.producer in RISK_PRODUCERS:
                if row.hash != canonical_hash(row.body()):
                    raise LearningScopeError("native risk identity seal mismatch")
                intent = p["inputs"]["intent"]
                alias = intent["account_alias"]
                if intent.get("trade_intent_id") != trade_id:
                    raise LearningScopeError("native risk trade identity conflict")
                if not isinstance(alias, str) or not alias:
                    raise LearningScopeError("native risk account missing")
                owners.add(alias)
                mandate = p["inputs"].get("mandate")
                if mandate is not None:
                    if mandate.get("account_alias") != alias:
                        raise LearningScopeError("native mandate account conflict")
                    mode = AuthorizationMode(mandate["mode"])
                    if "execution_cohort" in p:
                        from vati.learning.runtime_cohort import recorded_cohort
                        environments.add(recorded_cohort(p["execution_cohort"], mode))
                    else:
                        environments.add(ENVIRONMENT_FOR_MODE[mode])
            elif row.kind is EventKind.ORDER_COMMAND and row.producer == "vati-execution-router":
                if row.hash != canonical_hash(row.body()):
                    raise LearningScopeError("native order identity seal mismatch")
                alias = p["account_alias"]
                if not isinstance(alias, str) or not alias or p.get("trade_intent_id") != trade_id:
                    raise LearningScopeError("native order account/trade missing")
                owners.add(alias)
            elif row.kind in {EventKind.TCA_RECORD, EventKind.TRADE_REVIEW, EventKind.TRADE_EXPERIENCE_ARTIFACT} and row.producer in FACT_PRODUCERS:
                if row.hash != canonical_hash(row.body()):
                    raise LearningScopeError("native learning fact seal mismatch")
                explicit = p.get("account_alias")
                if explicit is not None and (not isinstance(explicit, str) or not explicit):
                    raise LearningScopeError("malformed explicit learning account")
                # A fact label can challenge a native binding, never create one.
                if explicit is not None:
                    if not owners or explicit not in owners:
                        raise LearningScopeError("learning account disagrees with native input")
                raw_environment = p.get("learning_environment", p.get("environment"))
                if raw_environment is not None:
                    environments.add(Environment(raw_environment))
        if len(owners) != 1:
            raise LearningScopeError("learning account is unbound or conflicting")
        explicit = event.payload.get("account_alias")
        if explicit is not None and explicit not in owners:
            raise LearningScopeError("source account disagrees with native input")
        if self.account_alias not in owners:
            self.excluded_refs.add(event.hash)
            return False
        source_environment = event.payload.get("learning_environment", event.payload.get("environment"))
        if source_environment is not None:
            environments.add(Environment(source_environment))
        if len(environments) != 1:
            raise LearningScopeError("learning environment is unbound or conflicting")
        if self.environment not in environments:
            self.excluded_refs.add(event.hash)
            return False
        return True

    def admit_lesson(self, payload, *, source_event=None) -> bool:
        """A lesson is scoped by its original native quadrant, before publication.

        Its historical correlation is a strategy ID. Neither that ID nor a
        later invented trade/account label is evidence of ownership.
        """
        identity = source_event.hash if source_event is not None else str(payload.get("artifact_hash", "unpublished"))
        try:
            if source_event is not None and source_event.hash != canonical_hash(source_event.body()):
                raise LearningScopeError("lesson event seal mismatch")
            for row in self.ledger.iter():
                if source_event is not None and row.hash == source_event.hash:
                    break
                if (row.kind is not EventKind.DECISION_QUADRANT or row.producer != "vati-decision-quality"
                    or row.payload.get("verdict_hash") not in payload.get("evidence_refs", ())):
                    continue
                p = row.payload
                expected_id = canonical_hash({"trade": p["trade_intent_id"], "quadrant": p["quadrant"]})[:24]
                if payload.get("lesson_id") != expected_id:
                    continue
                if (row.hash != canonical_hash(row.body())
                    or p["verdict_hash"] != canonical_hash({k:v for k,v in p.items() if k != "verdict_hash"})
                    or p["strategy_id"] != payload.get("strategy_id") or p["symbol"] != payload.get("symbol")):
                    raise LearningScopeError("lesson source identity conflict")
                if not self.admit(row):
                    if row.hash in self.unresolved_refs:
                        self.unresolved_refs.add(identity)
                    else:
                        self.excluded_refs.add(identity)
                    return False
                if Environment(payload["environment"]) != self.environment:
                    raise LearningScopeError("lesson cohort disagrees with its native source")
                return True
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
        self.unresolved_refs.add(identity)
        return False
