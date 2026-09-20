#!/usr/bin/env python3
"""Rev 5.1 deterministic certification harness (TRD-REV51-133).

This harness certifies repository implementation closure only.  Runtime, shadow and live
eligibility are separate evidence states and are never inferred from source/tests.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "trading" / "rev51" / "packets.json"
EXPECTED_PACKET_IDS = tuple(f"TRD-REV51-{n:03d}" for n in range(90, 134))
REPORT_VERSION = "rev51-certification/1.0.0"


def _gate(ok: bool, detail: Any = None, **extra: Any) -> dict[str, Any]:
    row = {"ok": bool(ok), "detail": detail}
    row.update(extra)
    return row


def _ast(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_locations(name: str) -> list[str]:
    out: list[str] = []
    for path in sorted((ROOT / "trading" / "vati").rglob("*.py")):
        tree = _ast(path)
        if any(isinstance(node, ast.ClassDef) and node.name == name for node in ast.walk(tree)):
            out.append(path.relative_to(ROOT).as_posix())
    return out


def _adapter_submit_locations() -> list[str]:
    """Find production calls shaped exactly adapter.submit(...), excluding tests/docs."""
    out: list[str] = []
    for path in sorted((ROOT / "trading" / "vati").rglob("*.py")):
        tree = _ast(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "submit":
                continue
            base = node.func.value
            if isinstance(base, ast.Name) and base.id == "adapter":
                out.append(path.relative_to(ROOT).as_posix())
                break
    return out


def _literal_assignment(path: Path, name: str) -> str | None:
    tree = _ast(path)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant):
            return repr(value.value)
        if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
            return f"{value.value.id}.{value.attr}"
    return None


def evaluate_repository(root: Path = ROOT) -> dict[str, Any]:
    # root is injectable for tests but all helpers operate on ROOT.  Refuse a different
    # root rather than creating a false sense that a partial tree was inspected.
    if root.resolve() != ROOT.resolve():
        raise ValueError("Rev 5.1 harness must run against the repository root")

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    packets = registry.get("packets", [])
    ids = tuple(p.get("packet_id", "") for p in packets)
    gates: dict[str, dict[str, Any]] = {}

    gates["registry_complete"] = _gate(
        ids == EXPECTED_PACKET_IDS,
        {"expected": len(EXPECTED_PACKET_IDS), "observed": len(ids),
         "missing": sorted(set(EXPECTED_PACKET_IDS) - set(ids)),
         "extra": sorted(set(ids) - set(EXPECTED_PACKET_IDS))},
    )

    missing_modules: list[str] = []
    missing_tests: list[str] = []
    for packet in packets:
        module = str(packet.get("module") or "")
        if not module or not (ROOT / module).is_file():
            missing_modules.append(f"{packet.get('packet_id')}:{module}")
        for test in packet.get("tests") or ():
            if not (ROOT / str(test)).is_file():
                missing_tests.append(f"{packet.get('packet_id')}:{test}")
    gates["declared_files_exist"] = _gate(
        not missing_modules and not missing_tests,
        {"missing_modules": missing_modules, "missing_tests": missing_tests},
    )

    risk_classes = _class_locations("RiskAuthority")
    submit_paths = _adapter_submit_locations()
    gates["authority_singletons"] = _gate(
        risk_classes == ["trading/vati/risk/authority.py"]
        and submit_paths == ["trading/vati/execution/router.py"],
        {"risk_authority_classes": risk_classes, "adapter_submit_paths": submit_paths},
    )

    router = (ROOT / "trading/vati/execution/router.py").read_text(encoding="utf-8")
    account_service = (ROOT / "trading/vati/app/account_service.py").read_text(encoding="utf-8")
    cycle = (ROOT / "trading/vati/app/cycle.py").read_text(encoding="utf-8")
    execution_markers = {
        "router_pretrade": "self.pretrade_controls.check(" in router,
        "router_route_resolution": "self.route_registry.resolve(" in router,
        "router_style_selection": "self.style_selector.select(" in router,
        "account_runtime_enforced": "enforce_rev51_controls=True" in account_service,
        "legacy_runtime_enforced": "enforce_rev51_controls=True" in cycle,
    }
    gates["non_bypassable_execution"] = _gate(
        all(execution_markers.values()), execution_markers)

    authority = (ROOT / "trading/vati/risk/authority.py").read_text(encoding="utf-8")
    conformal_markers = {
        "gate_dependency": "ConformalAdmissionGate" in authority,
        "before_sizing": "self.conformal_gate.check(intent, snapshot)" in authority
            and authority.index("self.conformal_gate.check(intent, snapshot)")
            < authority.index("# 11. Sizing"),
    }
    gates["conformal_authority_hook"] = _gate(
        all(conformal_markers.values()), conformal_markers)

    expansion_mode = _literal_assignment(
        ROOT / "trading/vati/lifecycle/expansion.py", "EXPANSION_MODE")
    advisory_enabled = _literal_assignment(
        ROOT / "trading/vati/cognition/translator.py", "LIVE_ADVISORY_ENABLED")
    expected_truth = {
        "cognition_mode": "OFFLINE_EVOLUTION+SHADOW_LIVE",
        "live_advisory": "DISABLED",
        "live_status": "NOT_CLAIMED",
    }
    observed_truth = {k: registry.get(k) for k in expected_truth}
    safety_ok = (
        observed_truth == expected_truth
        and expansion_mode == "Mode.SHADOW"
        and advisory_enabled in ("False", "0")
    )
    gates["first_pass_live_safety"] = _gate(
        safety_ok,
        {
            "registry": observed_truth,
            "expansion_mode": expansion_mode,
            "live_advisory_enabled_literal": advisory_enabled,
        },
    )

    required_invariants = {
        "INV-AUTH-001", "INV-EXEC-001", "INV-MODEL-001", "INV-LIVE-001",
        "INV-RISK-001", "INV-PPC-001", "INV-LEARN-001", "INV-EVID-001",
        "INV-REPLAY-001", "INV-FAIL-001",
    }
    observed_invariants = set(registry.get("invariants") or ())
    gates["invariant_registry"] = _gate(
        required_invariants <= observed_invariants,
        {"missing": sorted(required_invariants - observed_invariants)},
    )

    account_source = (ROOT / "trading/vati/app/account_service.py").read_text(
        encoding="utf-8")
    cognition_source = (ROOT / "trading/vati/cognition/runtime.py").read_text(
        encoding="utf-8")
    lifecycle_source = (ROOT / "trading/vati/app/trade_lifecycle.py").read_text(
        encoding="utf-8")
    event_source = (ROOT / "trading/vati/events/runtime.py").read_text(
        encoding="utf-8")
    evolution_source = (ROOT / "trading/vati/evolution/runtime.py").read_text(
        encoding="utf-8")
    cognition_hooks = {
        "persistent_runtime": "ShadowCognitionRuntime(" in account_source,
        "post_risk_wake": "self.cognition.wake(" in account_source,
        "world_projection": "self.world.apply(event)" in cognition_source,
        "context_compile": "compile_decision_context(" in cognition_source,
        "result_normalise": "normalise(" in cognition_source,
        "shadow_translate": "ActionTranslator(mode=Mode.SHADOW" in cognition_source,
        "shadow_book": "self.shadow.record(" in cognition_source,
        "performance_after_outcome": "self.performance.compile_all(" in cognition_source,
        "handoff": "self.handoffs.record(" in cognition_source,
    }
    gates["cognition_runtime_hooks"] = _gate(
        all(cognition_hooks.values()), cognition_hooks)

    lifecycle_hooks = {
        "family": "FamilyRegistry(" in lifecycle_source,
        "health": "TradeHealthEngine(" in lifecycle_source,
        "envelope": "EnvelopeCalculator(" in lifecycle_source,
        "preservation": "self.preservation.evaluate(" in lifecycle_source,
        "router_preservation": "self.router.apply_preservation(" in lifecycle_source,
        "shadow_expansion": "self.expansion.evaluate(" in lifecycle_source,
        "attribution": "self.attribution.attribute(" in lifecycle_source,
        "risk_block": "preservation_blocks_new_risk" in account_source,
    }
    gates["post_entry_runtime_hooks"] = _gate(
        all(lifecycle_hooks.values()), lifecycle_hooks)

    event_hooks = {
        "calendar_consumer": "self._calendar()" in event_source,
        "normalise": "self.normaliser.normalise(" in event_source,
        "surprise": "self.reactions.score(" in event_source,
        "horizon_callback": "self.reactions.record_mark(" in event_source,
        "episode_close": "self.episodes.close_due(" in event_source,
        "service_feed": "self.event_research.on_mark(" in account_source,
    }
    gates["event_runtime_hooks"] = _gate(
        all(event_hooks.values()), event_hooks)

    evolution_hooks = {
        "mission_orchestration": "self.agents.run(" in evolution_source,
        "synthesis": "self.synthesiser.synthesise(" in evolution_source,
        "yield": "self.yield_ledger.record(" in evolution_source,
        "proposal": "self.proposals.propose(" in evolution_source,
        "admission": "self.admission.assess(" in evolution_source,
        "growth": "self.growth.evaluate(" in evolution_source,
        "archive": "self.archive.append(" in evolution_source,
    }
    gates["offline_evolution_hooks"] = _gate(
        all(evolution_hooks.values()), evolution_hooks)

    qualification_path = ROOT / "trading/vati/cognition/qualification.py"
    qualification_source = (
        qualification_path.read_text(encoding="utf-8")
        if qualification_path.is_file() else "")
    qualification_hooks = {
        "decision_exam": "run_exam(" in qualification_source,
        "blind_review": "BlindReviewer(" in qualification_source,
    }
    gates["cognition_qualification_hooks"] = _gate(
        all(qualification_hooks.values()), qualification_hooks)

    owner_files = (
        ROOT / "trading/vati/readmodels/cognition.py",
        ROOT / "backend/van_gateway/trading/cognition.py",
        ROOT / "android/app/src/main/java/com/dial/van/trading/ui/CognitionScreens.kt",
    )
    gates["owner_surface_hooks"] = _gate(
        all(p.is_file() for p in owner_files),
        [p.relative_to(ROOT).as_posix() for p in owner_files if not p.is_file()],
    )

    repository_ok = all(row["ok"] for row in gates.values())

    # External states are intentionally evidence-bound.  The files are *not* generated
    # by this harness; Trading Core qualification and shadow observation must produce them.
    runtime_attestation = ROOT / "artifacts/trading/rev51/runtime_qualification.json"
    shadow_attestation = ROOT / "artifacts/trading/rev51/shadow_qualification.json"
    runtime_qualified = runtime_attestation.is_file()
    shadow_qualified = runtime_qualified and shadow_attestation.is_file()

    states = {
        "SPEC_CLOSED": True,
        "IMPLEMENTATION_CLOSED": repository_ok,
        "RUNTIME_QUALIFIED": runtime_qualified,
        "SHADOW_QUALIFIED": shadow_qualified,
        # Rev 5.1 first pass explicitly does not claim live eligibility.
        "LIVE_ELIGIBLE": False,
    }
    return {
        "report_version": REPORT_VERSION,
        "revision": registry.get("revision"),
        "baseline_commit": registry.get("baseline_commit"),
        "live_status": registry.get("live_status"),
        "gates": gates,
        "states": states,
        "external_evidence": {
            "runtime_qualification": str(runtime_attestation.relative_to(ROOT)),
            "shadow_qualification": str(shadow_attestation.relative_to(ROOT)),
            "runtime_evidence_present": runtime_qualified,
            "shadow_evidence_present": shadow_qualified,
        },
        "certification_scope": (
            "repository implementation closure only; runtime/shadow/live require "
            "independent external evidence"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail if repository implementation closure is not satisfied")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = evaluate_repository()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if args.check:
        return 0 if report["states"]["IMPLEMENTATION_CLOSED"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
