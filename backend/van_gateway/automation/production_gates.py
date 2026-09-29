"""Explicit production activation gate model (owner decision 2026-09-29 §6).

The health surface used to declare ``production_activation_permitted`` whenever no required
decision file contained the literal string ``owner_signature_status: PENDING``. That read one
field of one kind of gate and ignored every production gate recorded beside it — Stagehand's
``production_gate.status: PENDING`` among them — so the surface said "permitted" while Project
Truth said "pending".

This module replaces the string test with a model:

* ``registries/production_activation_gates.json`` names the required decisions, the gates each
  must satisfy, where each gate's status lives (a dotted path into the decision record) and
  the closed vocabulary that maps a raw value to GREEN / PENDING / BLOCKED.
* Each gate is evaluated from the decision record itself. The registry never holds a status;
  an agent cannot make a gate GREEN by editing the model, only by the record changing.
* Anything the model cannot establish is UNKNOWN: a missing registry, an empty model, a
  missing or unparseable decision, a missing path, a value outside the declared vocabulary.
  UNKNOWN is not GREEN, so every one of those fails closed.

``production_activation_permitted`` is true only when every gate of every required decision
is GREEN.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE_MODEL = REPO_ROOT / "registries" / "production_activation_gates.json"


#: Reviewer I minor 8 — which required decisions each capability's production activation
#: rests on. The global ``production_activation_permitted`` stays "every gate GREEN"; this
#: lets the health surface say, for example, that Stagehand's pending gates do not bear on
#: the deterministic Harness path (owner decision 2026-09-29 §1: "The deterministic browser
#: path ... may continue according to [its] own policy"). Stagehand acts only through the
#: Harness, so it inherits the Harness decision. A decision named here that the gate model
#: does not require makes that capability UNKNOWN, never permitted.
SECURITY_POLICY_DECISION = "VAN-AMEND-SECURITY-POLICY-001.md"
JEV_BROWSER_EFFECT_DECISION = "VAN-JEV-BROWSER-EFFECT-001.yaml"
CAPABILITY_DECISIONS: dict[str, tuple[str, ...]] = {
    "n8n": ("VAN-ADOPT-N8N-001.yaml", SECURITY_POLICY_DECISION),
    "browser_harness": ("VAN-ADOPT-BROWSER-HARNESS-001.yaml", SECURITY_POLICY_DECISION),
    "stagehand": (
        "VAN-ADOPT-STAGEHAND-001.yaml", "VAN-ADOPT-BROWSER-HARNESS-001.yaml", SECURITY_POLICY_DECISION,
    ),
    # Review I2 N-7 — VAN's own gate on Jev browser effect. Blueprint §11: no Jev module can
    # carry effect today; PROPOSE_ACTION stays SHADOW until a separate owner decision. The
    # record starts SHADOW_ONLY (pending). Jev's actions go through the Harness, so the
    # Harness decision is inherited like Stagehand's.
    "jev_browser_effect": (
        JEV_BROWSER_EFFECT_DECISION, "VAN-ADOPT-BROWSER-HARNESS-001.yaml", SECURITY_POLICY_DECISION,
    ),
}


class GateStatus(str, Enum):
    GREEN = "GREEN"
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class GateKind(str, Enum):
    OWNER_DECISION = "owner_decision"
    PRODUCTION = "production"


@dataclass(frozen=True)
class GateResult:
    decision: str
    gate: str
    kind: str
    status: GateStatus
    raw_value: str | None
    source: str
    path: str
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["status"] = self.status.value
        return out


_MARKDOWN_FIELD = re.compile(r"^\*\*(?P<key>[^*:]+):\*\*\s*`(?P<value>[^`]+)`", re.MULTILINE)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


class DuplicateKeyError(ValueError):
    """A decision record states the same key twice in one mapping."""


def _unique_key_yaml_load(text: str) -> Any:
    """``yaml.safe_load`` that refuses a mapping with a repeated key.

    Reviewer I minor 2: ``safe_load`` keeps the *last* of two equal keys, so appending a
    second ``owner_decisions_20260929:`` block (all GREEN) to a record silently replaced the
    real one and flipped ``production_activation_permitted`` to true. Decision records are
    append-only by rule; a repeated key is a record this model cannot read, i.e. UNKNOWN.
    Keys merged in with ``<<:`` count too, so a merge cannot override a stated key either.
    """
    import yaml  # PyYAML is pinned in backend/requirements.lock; absent => fail closed.

    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):  # type: ignore[override]
            if isinstance(node, yaml.MappingNode):
                self.flatten_mapping(node)
                seen: set[Any] = set()
                for key_node, _ in node.value:
                    key = self.construct_object(key_node, deep=deep)
                    try:
                        duplicate = key in seen
                    except TypeError:  # unhashable key: let the base loader reject it
                        continue
                    if duplicate:
                        raise DuplicateKeyError(
                            f"duplicate key {key!r} at line {key_node.start_mark.line + 1}"
                        )
                    seen.add(key)
            return super().construct_mapping(node, deep=deep)

    return yaml.load(text, Loader=UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass


def _load_record(path: Path, fmt: str) -> dict[str, Any]:
    """Parse a decision record into a mapping. Raises on anything it cannot read."""
    text = path.read_text(encoding="utf-8")
    if fmt == "yaml":
        data = _unique_key_yaml_load(text)
        if not isinstance(data, dict):
            raise ValueError("decision record is not a mapping")
        return data
    if fmt == "markdown":
        # The first `**Key:** `VALUE`` occurrence of each key, e.g. `**Status:** `OWNER_APPROVED``.
        fields: dict[str, Any] = {}
        for match in _MARKDOWN_FIELD.finditer(text):
            fields.setdefault(match.group("key").strip(), match.group("value").strip())
        return fields
    raise ValueError(f"unsupported decision format {fmt!r}")


def _resolve(data: Any, dotted: str) -> Any:
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


def _classify(spec: dict[str, Any], raw: Any) -> tuple[GateStatus, str | None]:
    if not isinstance(raw, str):
        return GateStatus.UNKNOWN, f"value is {type(raw).__name__}, not a status string"
    for status, key in (
        (GateStatus.GREEN, "green"),
        (GateStatus.BLOCKED, "blocked"),
        (GateStatus.PENDING, "pending"),
    ):
        if raw in (spec.get(key) or []):
            return status, None
    return GateStatus.UNKNOWN, f"{raw!r} is outside the declared vocabulary"


def _gate_spec_problem(spec: Any) -> str | None:
    if not isinstance(spec, dict):
        return "gate spec is not an object"
    for field in ("id", "kind", "path"):
        if not isinstance(spec.get(field), str) or not spec[field]:
            return f"gate spec lacks {field}"
    if spec["kind"] not in {k.value for k in GateKind}:
        return f"unknown gate kind {spec['kind']!r}"
    if not spec.get("green"):
        return "gate declares no GREEN value"
    return None


def evaluate_production_gates(
    model_path: Path | None = None, repo_root: Path | None = None
) -> dict[str, Any]:
    """Evaluate every required gate. Never raises; every failure is a closed gate."""
    root = repo_root or REPO_ROOT
    model_file = model_path or GATE_MODEL
    model_source = _relative(model_file, root)
    base = {
        "gate_model": model_source,
        "gate_model_error": None,
        "required_decisions": [],
        "owner_decisions_pending": [],
        "owner_decisions_missing": [],
        "production_gates_not_green": [],
        "gates": [],
        "production_activation_permitted": False,
        "capabilities": {
            name: {
                "decisions": list(decisions),
                "production_activation_permitted": False,
                "gates_not_green": [],
                "error": "gate model unreadable",
            }
            for name, decisions in CAPABILITY_DECISIONS.items()
        },
    }

    try:
        model = json.loads(model_file.read_text(encoding="utf-8"))
        required = model["required_decisions"]
        decisions_dir = root / model.get("decisions_dir", "docs/decisions")
        if not isinstance(required, list) or not required:
            raise ValueError("model declares no required decisions")
        # Review I2 N-7: decisions that gate one capability only (e.g. Jev browser effect,
        # which stays SHADOW_ONLY as a legitimate production posture). Evaluated exactly like
        # required ones, reported per capability, and not part of the global summary.
        capability_only = model.get("capability_decisions", [])
        if not isinstance(capability_only, list):
            raise ValueError("capability_decisions is not a list")
    except Exception as exc:  # noqa: BLE001 — any unreadable model is a closed gate
        base["gate_model_error"] = f"{type(exc).__name__}: {exc}"
        return base

    results: list[GateResult] = []
    missing: list[str] = []
    names: list[str] = []
    capability_names: list[str] = []
    global_count = len(required)
    for index, entry in enumerate(list(required) + list(capability_only)):
        is_global = index < global_count
        name = entry.get("decision") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name:
            results.append(
                GateResult("<unnamed>", "<model>", GateKind.PRODUCTION.value, GateStatus.UNKNOWN,
                           None, model_source, "", "decision entry has no name")
            )
            continue
        (names if is_global else capability_names).append(name)
        path = decisions_dir / name
        source = _relative(path, root)
        gates = entry.get("gates")
        if not isinstance(gates, list) or not gates:
            results.append(
                GateResult(name, "<model>", GateKind.PRODUCTION.value, GateStatus.UNKNOWN,
                           None, source, "", "decision declares no gates")
            )
            continue

        record: dict[str, Any] | None = None
        load_error: str | None = None
        if not path.is_file():
            missing.append(name)
            load_error = "decision record is missing"
        else:
            try:
                record = _load_record(path, entry.get("format", "yaml"))
            except Exception as exc:  # noqa: BLE001 — unparseable is UNKNOWN
                load_error = f"unparseable: {type(exc).__name__}: {exc}"

        for spec in gates:
            problem = _gate_spec_problem(spec)
            gate_id = spec.get("id", "<unnamed>") if isinstance(spec, dict) else "<unnamed>"
            kind = (
                spec.get("kind") if isinstance(spec, dict) and spec.get("kind") in {k.value for k in GateKind}
                else GateKind.PRODUCTION.value
            )
            dotted = spec.get("path", "") if isinstance(spec, dict) else ""
            if problem or record is None:
                results.append(
                    GateResult(name, gate_id, kind, GateStatus.UNKNOWN, None, source, dotted,
                               problem or load_error)
                )
                continue
            try:
                raw = _resolve(record, dotted)
            except KeyError:
                results.append(
                    GateResult(name, gate_id, kind, GateStatus.UNKNOWN, None, source, dotted,
                               "path not present in decision record")
                )
                continue
            status, reason = _classify(spec, raw)
            results.append(
                GateResult(name, gate_id, kind, status, raw if isinstance(raw, str) else None,
                           source, dotted, reason)
            )

    all_results = results
    capability_only_names = set(capability_names) - set(names)
    results = [r for r in all_results if r.decision not in capability_only_names]
    pending_owner = sorted(
        {
            r.decision
            for r in results
            if r.kind == GateKind.OWNER_DECISION.value
            and r.status is not GateStatus.GREEN
            and r.decision not in missing
        }
    )
    not_green = [
        f"{r.decision}:{r.gate}"
        for r in results
        if r.kind == GateKind.PRODUCTION.value and r.status is not GateStatus.GREEN
    ]
    capabilities: dict[str, Any] = {}
    declared = set(names) | set(capability_names)
    for capability, decisions in CAPABILITY_DECISIONS.items():
        scoped = [r for r in all_results if r.decision in decisions]
        unrequired = sorted(set(decisions) - declared)
        capabilities[capability] = {
            "decisions": list(decisions),
            "production_activation_permitted": bool(scoped) and not unrequired
            and all(r.status is GateStatus.GREEN for r in scoped),
            "gates_not_green": [f"{r.decision}:{r.gate}" for r in scoped if r.status is not GateStatus.GREEN],
            "error": f"not required by the gate model: {', '.join(unrequired)}" if unrequired else None,
        }
    base.update(
        capabilities=capabilities,
        required_decisions=names,
        capability_decisions=capability_names,
        capability_gates=[r.as_dict() for r in all_results if r.decision in capability_only_names],
        owner_decisions_pending=pending_owner,
        owner_decisions_missing=sorted(m for m in missing if m not in capability_only_names),
        production_gates_not_green=not_green,
        gates=[r.as_dict() for r in results],
        production_activation_permitted=bool(results)
        and all(r.status is GateStatus.GREEN for r in results),
    )
    return base


__all__ = ["CAPABILITY_DECISIONS", "GATE_MODEL", "JEV_BROWSER_EFFECT_DECISION", "DuplicateKeyError", "GateKind", "GateResult", "GateStatus", "evaluate_production_gates"]
