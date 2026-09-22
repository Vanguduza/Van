"""Static architecture guardrails for the enhancement (§50, TRD-ENH-087).

These are AST checks, not greps: a docstring mentioning `ExecutionRouter` must
not fail the build, and a real import must not pass it.

They are guardrails rather than proof. A class can import nothing forbidden and
still be wrong; these catch the specific structural mistakes that would quietly
undo the authority boundaries.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Rule:
    name: str
    module: str
    forbidden_imports: tuple[str, ...] = ()
    forbidden_attrs: tuple[str, ...] = ()
    forbidden_fields: tuple[str, ...] = ()
    why: str = ""


RULES: tuple[Rule, ...] = (
    Rule("candidate-cannot-execute", "vati/arbiter/candidate.py",
         forbidden_imports=("vati.execution",),
         forbidden_fields=("requested_risk_pct", "approved_size", "approved_risk_pct",
                           "decision_hash", "idempotency_key"),
         why="a CandidateOpportunity must be weaker than a TradeIntent"),
    Rule("allocator-cannot-size", "vati/arbiter/portfolio_allocator.py",
         forbidden_imports=("vati.execution.router", "vati.risk.authority"),
         forbidden_attrs=("reserve_heat", "allocate_size", "preapprove"),
         why="the allocator selects; the Risk Authority sizes"),
    Rule("allocator-v0-ignores-confidence", "vati/arbiter/portfolio_allocator.py",
         forbidden_attrs=(),
         why="checked separately below"),
    Rule("evaluator-cannot-execute", "vati/app/instrument_evaluator.py",
         forbidden_imports=("vati.execution.router",),
         forbidden_attrs=("execute", "send_order"),
         why="an InstrumentEvaluator produces candidates, not orders"),
    Rule("proposal-cannot-mutate-mandate", "vati/risk/capital_promotion.py",
         forbidden_imports=("vati.risk.mandate",),
         forbidden_attrs=("update_mandate", "apply", "commit"),
         why="only an owner-signed mandate version changes a ceiling"),
    Rule("exit-research-cannot-touch-protection", "vati/learning/exit_research.py",
         forbidden_imports=("vati.execution.protection", "vati.execution.router"),
         why="exit research produces candidates, never live mutation"),
    Rule("drift-cannot-mutate-capsules", "vati/learning/drift.py",
         forbidden_imports=("vati.strategies.capsule",),
         forbidden_attrs=("promote", "demote"),
         why="drift proposes; it does not rewrite a live capsule"),
    Rule("browser-evidence-cannot-reach-execution", "vati/research/trading_evidence.py",
         forbidden_imports=("vati.execution", "vati.risk.authority"),
         why="browser evidence is research, not authority"),
    Rule("execution-policy-cannot-create-trades", "vati/execution/policy.py",
         forbidden_imports=("vati.execution.router",),
         forbidden_attrs=("approve", "create_intent", "submit"),
         why="it decides how to execute, never whether"),
    # --- GAP-F-003 / GAP-F-004 -------------------------------------------
    # Four modules were added that reason about live positions. Each of them
    # produces evidence or a proposal, and each would be dangerous in a
    # different way if it could reach the gates directly, so each is pinned
    # here rather than trusted to stay well behaved.
    Rule("thesis-cannot-execute", "vati/lifecycle/thesis.py",
         forbidden_imports=("vati.execution", "vati.risk.authority"),
         forbidden_attrs=("execute", "submit", "approve", "size"),
         why="a thesis describes and withholds; it never sizes or sends"),
    Rule("adjustment-cannot-execute", "vati/lifecycle/scale_policy.py",
         forbidden_imports=("vati.execution.router", "vati.execution.protection",
                            "vati.risk.authority"),
         forbidden_attrs=("execute", "submit", "approve"),
         why="a PositionAdjustmentProposal must reach RiskAuthority and "
             "ExecutionRouter through the lifecycle, never by itself"),
    Rule("news-cannot-execute", "vati/events/news_ingress.py",
         forbidden_imports=("vati.execution", "vati.risk.authority",
                            "vati.intelligence.calendar_feed"),
         forbidden_attrs=("execute", "submit", "approve", "blackout"),
         why="news is reduce-only evidence; the economic calendar keeps the "
             "blackout authority"),
    Rule("cognition-invoker-cannot-execute", "vati/cognition/invokers.py",
         forbidden_imports=("vati.execution", "vati.risk.authority",
                            "vati.arbiter.intent_factory"),
         forbidden_attrs=("execute", "submit", "approve", "size"),
         why="a model invoker fetches a result; contracts.py decides what it means"),
    Rule("active-readmodel-cannot-execute", "vati/readmodels/active.py",
         forbidden_imports=("vati.execution", "vati.risk.authority"),
         forbidden_attrs=("execute", "submit", "approve", "halt"),
         why="a read model classifies what happened; it cannot act"),
)


def _tree(module: str) -> ast.Module:
    return ast.parse((ROOT / module).read_text())


def _imports(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _defined_names(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
    return out


def check_rule(rule: Rule) -> list[str]:
    tree = _tree(rule.module)
    failures: list[str] = []

    imported = _imports(tree)
    for banned in rule.forbidden_imports:
        hits = sorted(m for m in imported if m == banned or m.startswith(banned + "."))
        if hits:
            failures.append(f"{rule.name}: {rule.module} imports {hits} — {rule.why}")

    defined = _defined_names(tree)
    for attr in rule.forbidden_attrs:
        if attr in defined:
            failures.append(f"{rule.name}: {rule.module} defines `{attr}` — {rule.why}")
    for field in rule.forbidden_fields:
        if field in defined:
            failures.append(f"{rule.name}: {rule.module} declares field `{field}` — {rule.why}")
    return failures


def check_allocator_v0_ignores_confidence() -> list[str]:
    """The B3 correction, as a build check.

    Allocator V0's utility must not read `confidence_score`: ranking decides
    which candidate reaches the Risk Authority, so an uncalibrated score
    ranking would decide which trade happens.
    """
    tree = _tree("vati/arbiter/portfolio_allocator.py")
    banned = {"confidence_score", "confidence_multiplier"}
    failures: list[str] = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_utility"):
            read = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
            hit = sorted(read & banned)
            if hit:
                failures.append(
                    f"allocator-{cls.name}-ignores-confidence: reads {hit} — "
                    "an uncalibrated score must not decide which trade happens")
    return failures


def check_no_trading_table_in_gateway_schema() -> list[str]:
    """B1: trading truth belongs on the VATI authority store, not the gateway."""
    gateway = ROOT.parent / "backend" / "van_gateway" / "storage" / "db.py"
    if not gateway.exists():
        return []
    text = gateway.read_text()
    trading_tables = (
        "candidate_opportunities", "allocation_epochs", "allocation_decisions",
        "allocation_episodes", "account_runtime_leases", "portfolio_dependency_snapshots",
        "execution_policy_decisions", "capital_budget_proposals",
        "strategy_validation_certificates", "feature_validation_certificates",
    )
    hits = [t for t in trading_tables if t in text]
    return [f"gateway-holds-no-trading-truth: {hits} found in the gateway schema — "
            "these belong on the VATI transactional authority store"] if hits else []


def _has_fastapi_route(tree: ast.Module, *, method: str, route: str) -> bool:
    """Return True only for an exact @app.<method>(route) decorator."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            if dec.func.attr.lower() != method.lower() or not dec.args:
                continue
            first = dec.args[0]
            if isinstance(first, ast.Constant) and first.value == route:
                return True
    return False


def check_required_production_joins() -> list[str]:
    """Joins whose absence recreates the PR #49 audit findings."""
    failures: list[str] = []

    main_tree = _tree("vati/__main__.py")
    names = {n.id for n in ast.walk(main_tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(main_tree) if isinstance(n, ast.Attribute)}
    if "AccountCoordinatorService" not in names:
        failures.append(
            "account-coordinator-live-entry: vati serve does not reference AccountCoordinatorService")
    if "instruments" not in attrs:
        failures.append(
            "account-coordinator-live-entry: vati serve has no multi-instrument activation condition")

    router_tree = _tree("vati/execution/router.py")
    router_names = {n.id for n in ast.walk(router_tree) if isinstance(n, ast.Name)}
    router_attrs = {n.attr for n in ast.walk(router_tree) if isinstance(n, ast.Attribute)}
    if "resolve_execution_policy" not in {n.name for n in ast.walk(router_tree)
                                          if isinstance(n, ast.FunctionDef)}:
        failures.append("execution-policy-router-join: router has no policy resolver")
    if "EXECUTION_POLICY_DECISION" not in router_attrs:
        failures.append("execution-policy-router-join: policy decision is not ledgered")

    feature_tree = _tree("vati/intelligence/feature_contract.py")
    imports = _imports(feature_tree)
    if "vati.intelligence.feature_registry" not in imports:
        failures.append(
            "feature-registry-contract-join: FeatureContractValidator no longer imports the registry")
    feature_attrs = {n.attr for n in ast.walk(feature_tree) if isinstance(n, ast.Attribute)}
    if "is_production_admitted" not in feature_attrs:
        failures.append(
            "feature-registry-contract-join: production admission is not enforced")

    service_tree = _tree("vati/app/account_service.py")
    service_names = {n.id for n in ast.walk(service_tree) if isinstance(n, ast.Name)}
    if "PostgresLeaseStore" not in service_names:
        failures.append(
            "account-lease-live-join: account service is not bound to the shared PostgreSQL lease")
    if "InMemoryLeaseStore" in service_names:
        failures.append(
            "account-lease-live-join: production account service references an in-memory lease")

    commander_path = ROOT / "commander" / "app.py"
    commander_strategy_path = ROOT / "commander" / "strategies.py"
    gateway_path = ROOT.parent / "backend" / "van_gateway" / "app.py"
    capsule_path = ROOT / "vati" / "strategies" / "capsule.py"
    required_paths = (
        commander_path, commander_strategy_path, gateway_path, capsule_path,
    )
    missing = [p.as_posix() for p in required_paths if not p.is_file()]
    if missing:
        failures.append(
            "strategy-promotion-live-join: repository-spanning guard is missing "
            + ", ".join(missing)
        )
        return failures

    commander = commander_path.read_text()
    commander_strategy = commander_strategy_path.read_text()
    gateway_tree = ast.parse(gateway_path.read_text())
    capsule = capsule_path.read_text()
    if "capsule_promote" not in commander_strategy:
        failures.append(
            "strategy-promotion-live-join: private commander promotion command is absent")
    if (
        "PROMOTION_COMMANDS" not in commander
        or "build_strategy_handlers" not in commander
        or "**build_strategy_handlers(" not in commander
    ):
        failures.append(
            "strategy-promotion-live-join: commander app does not compose the private promotion handlers")
    if "AGENT_HIDDEN_COMMANDS" not in commander or "PROMOTION_COMMANDS" not in commander:
        failures.append(
            "strategy-promotion-agent-boundary: promotion is not attached to the hidden command set")
    if not _has_fastapi_route(
        gateway_tree, method="post", route="/v1/trading/strategies/promote"
    ):
        failures.append(
            "strategy-promotion-live-join: exact gateway owner promotion POST route is absent")
    if "CapsuleRegistry" not in commander_strategy or ".promote(" not in commander_strategy:
        failures.append(
            "strategy-promotion-live-join: commander no longer reaches CapsuleRegistry.promote")
    if "def promote(" not in capsule:
        failures.append(
            "strategy-promotion-live-join: capsule promotion gate is absent")
    return failures


def check_active_trade_intelligence_joins() -> list[str]:
    """GAP-F-003 / GAP-F-004 joins, whose absence recreates the audit findings.

    Each of these was found *implemented and unreachable*. A guardrail that
    only forbids the wrong imports would let them quietly become unreachable
    again, which is the exact failure mode the audit recorded, so the joins
    themselves are asserted.
    """
    failures: list[str] = []

    service_tree = _tree("vati/app/account_service.py")
    names = {n.id for n in ast.walk(service_tree) if isinstance(n, ast.Name)}
    if "build_invoker" not in names:
        failures.append(
            "cognition-invoker-live-join: account service no longer constructs a "
            "provider invoker (GAP-F-004); ShadowCognitionRuntime would abstain "
            "MODEL_UNAVAILABLE with no way to configure otherwise")
    if "CognitionConfig" not in names:
        failures.append(
            "cognition-invoker-live-join: account service has no cognition "
            "configuration; the invoker would have no injection point")
    # GAP-F-003 item 6. The research director, agent factory and mission ledger
    # were composed into the runtime, but a runtime with no research invoker
    # runs no agents at all — which is the same "implemented and unreachable"
    # shape the audit recorded one level down. Asserted here so it cannot
    # silently return to it.
    if "build_research_invoker" not in names:
        failures.append(
            "research-invoker-live-join: account service no longer constructs a "
            "research invoker, so `run_research` can only ever return nothing "
            "and a PROPOSE_RESEARCH verdict commissions no work")
    service_defs = {n.name for n in ast.walk(service_tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # GAP-F-003 item 4, the candidate half. News reaching an *open* position is
    # not the same join as news reaching the next candidate's size; the second
    # one runs entirely through the meta-labeller and would be invisible if it
    # were dropped.
    if "_apply_news_event_risk" not in service_defs:
        failures.append(
            "news-sizing-join: account service no longer feeds recorded headlines "
            "into the meta-labeller's event_risk_multiplier, so news would reach "
            "open positions but never the candidates about to become them")
    labeler_tree = _tree("vati/arbiter/meta_labeler.py")
    labeler_attrs = {n.attr for n in ast.walk(labeler_tree) if isinstance(n, ast.Attribute)}
    if "news_event_risk" not in labeler_attrs:
        failures.append(
            "news-sizing-join: MetaLabeler has no news_event_risk term, so the "
            "reduce-only headline multiplier has nowhere to land")

    lifecycle_tree = _tree("vati/app/trade_lifecycle.py")
    lifecycle_names = {n.id for n in ast.walk(lifecycle_tree) if isinstance(n, ast.Name)}
    lifecycle_defs = {n.name for n in ast.walk(lifecycle_tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if "thesis_from_capsule" not in lifecycle_names:
        failures.append(
            "thesis-live-join: the account lifecycle no longer seals a TradeThesis "
            "on entry (GAP-F-003); open positions would carry no falsifiable claim")
    if "_assess_thesis" not in lifecycle_defs or "_adjust" not in lifecycle_defs:
        failures.append(
            "thesis-live-join: the account lifecycle no longer assesses theses or "
            "proposes adjustments for open positions")
    if "_authorise_delta" not in lifecycle_defs:
        failures.append(
            "adjustment-authority-join: a size-changing adjustment no longer goes "
            "through RiskAuthority.evaluate (INV-AUTH-001)")
    if "DecisionQualityLedger" not in lifecycle_names:
        failures.append(
            "decision-quality-live-join: closed trades are no longer classified on "
            "the decision-quality axis, so capsule_health is fed by outcome alone")

    cycle_tree = _tree("vati/app/cycle.py")
    cycle_defs = {n.name for n in ast.walk(cycle_tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if "_review_open_theses" not in cycle_defs or "_seal_thesis" not in cycle_defs:
        failures.append(
            "thesis-live-join: DecisionCycle no longer seals or reviews theses, so "
            "the single-symbol runtime and the account runtime would disagree")

    runtime_tree = _tree("vati/cognition/runtime.py")
    runtime_names = {n.id for n in ast.walk(runtime_tree) if isinstance(n, ast.Name)}
    if "ResearchAgentFactory" not in runtime_names:
        failures.append(
            "research-cognition-join: ShadowCognitionRuntime no longer composes the "
            "research agent factory, so a PROPOSE_RESEARCH verdict would open a "
            "mission nobody runs")

    main_tree = _tree("vati/__main__.py")
    main_defs = {n.name for n in ast.walk(main_tree) if isinstance(n, ast.FunctionDef)}
    if "cmd_news_ingest" not in main_defs:
        failures.append(
            "news-ingress-runner-join: `python -m vati news-ingest` is absent, so "
            "headlines would have no production producer")

    commander = (ROOT / "commander" / "app.py").read_text()
    if '"positions"' not in commander or '"assessment"' not in commander:
        failures.append(
            "trading-observation-join: the commander no longer exposes the read-only "
            "positions/assessment commands (GAP-F-003), so Hermes has no path to "
            "trading state")
    return failures


def check_certificate_producer_boundary() -> list[str]:
    """Only the certificate module and canonical builder may instantiate certs."""
    allowed = {
        "vati/validation/certificates.py",
        "vati/validation/builder.py",
    }
    constructors = {"StrategyValidationCertificate", "FeatureValidationCertificate"}
    failures: list[str] = []
    for path in (ROOT / "vati").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            name = call.func.id if isinstance(call.func, ast.Name) else (
                call.func.attr if isinstance(call.func, ast.Attribute) else "")
            if name in constructors:
                failures.append(
                    f"certificate-producer-boundary: {rel} constructs {name} directly — "
                    "use vati.validation.builder so statistics and provenance are derived")
    return failures


def main() -> int:
    failures: list[str] = []
    for rule in RULES:
        if rule.name == "allocator-v0-ignores-confidence":
            continue
        failures.extend(check_rule(rule))
    failures.extend(check_allocator_v0_ignores_confidence())
    failures.extend(check_no_trading_table_in_gateway_schema())
    failures.extend(check_required_production_joins())
    failures.extend(check_active_trade_intelligence_joins())
    failures.extend(check_certificate_producer_boundary())

    if failures:
        print("Architecture guardrails FAILED:\n", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"Architecture guardrails OK ({len(RULES)} rules + confidence + store placement + production joins + active-trade joins + certificate producer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
