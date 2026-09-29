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


def _load_record(path: Path, fmt: str) -> dict[str, Any]:
    """Parse a decision record into a mapping. Raises on anything it cannot read."""
    text = path.read_text(encoding="utf-8")
    if fmt == "yaml":
        import yaml  # PyYAML is pinned in backend/requirements.lock; absent => fail closed.

        data = yaml.safe_load(text)
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
    }

    try:
        model = json.loads(model_file.read_text(encoding="utf-8"))
        required = model["required_decisions"]
        decisions_dir = root / model.get("decisions_dir", "docs/decisions")
        if not isinstance(required, list) or not required:
            raise ValueError("model declares no required decisions")
    except Exception as exc:  # noqa: BLE001 — any unreadable model is a closed gate
        base["gate_model_error"] = f"{type(exc).__name__}: {exc}"
        return base

    results: list[GateResult] = []
    missing: list[str] = []
    names: list[str] = []
    for entry in required:
        name = entry.get("decision") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name:
            results.append(
                GateResult("<unnamed>", "<model>", GateKind.PRODUCTION.value, GateStatus.UNKNOWN,
                           None, model_source, "", "decision entry has no name")
            )
            continue
        names.append(name)
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
    base.update(
        required_decisions=names,
        owner_decisions_pending=pending_owner,
        owner_decisions_missing=sorted(missing),
        production_gates_not_green=not_green,
        gates=[r.as_dict() for r in results],
        production_activation_permitted=bool(results)
        and all(r.status is GateStatus.GREEN for r in results),
    )
    return base


__all__ = ["GATE_MODEL", "GateKind", "GateResult", "GateStatus", "evaluate_production_gates"]
