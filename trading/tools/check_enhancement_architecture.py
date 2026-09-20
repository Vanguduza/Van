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

    commander = (ROOT / "commander" / "app.py").read_text()
    commander_strategy = (ROOT / "commander" / "strategies.py").read_text()
    gateway = (ROOT.parent / "backend" / "van_gateway" / "app.py").read_text()
    capsule = (ROOT / "vati" / "strategies" / "capsule.py").read_text()
    if "capsule_promote" not in commander or "capsule_promote" not in commander_strategy:
        failures.append(
            "strategy-promotion-live-join: private commander promotion command is absent")
    if "AGENT_HIDDEN_COMMANDS" not in commander or "PROMOTION_COMMANDS" not in commander:
        failures.append(
            "strategy-promotion-agent-boundary: promotion is not attached to the hidden command set")
    if "/v1/trading/strategies/promote" not in gateway:
        failures.append(
            "strategy-promotion-live-join: gateway owner promotion route is absent")
    if "CapsuleRegistry" not in commander_strategy or ".promote(" not in commander_strategy:
        failures.append(
            "strategy-promotion-live-join: commander no longer reaches CapsuleRegistry.promote")
    if "def promote(" not in capsule:
        failures.append(
            "strategy-promotion-live-join: capsule promotion gate is absent")
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
    failures.extend(check_certificate_producer_boundary())

    if failures:
        print("Architecture guardrails FAILED:\n", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"Architecture guardrails OK ({len(RULES)} rules + confidence + store placement + production joins + certificate producer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
