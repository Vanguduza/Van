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

import fnmatch
import hashlib
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
#: Unit G12 (owner answers 2026-09-30 after review I7, "Egress proxy" and "Firewall UDP in
#: zone"): the browser's egress proxy and zone firewall must be qualified on the host before
#: the browser capability, Stagehand ("stays production-disabled until it exists") or Jev's
#: browser effect may be production-activated. PENDING until a live qualify.sh report.
BROWSER_EGRESS_DECISION = "VAN-BROWSER-CORE-EGRESS-001.yaml"
CAPABILITY_DECISIONS: dict[str, tuple[str, ...]] = {
    "n8n": ("VAN-ADOPT-N8N-001.yaml", SECURITY_POLICY_DECISION),
    "browser_harness": ("VAN-ADOPT-BROWSER-HARNESS-001.yaml", BROWSER_EGRESS_DECISION, SECURITY_POLICY_DECISION),
    "stagehand": (
        "VAN-ADOPT-STAGEHAND-001.yaml", "VAN-ADOPT-BROWSER-HARNESS-001.yaml", BROWSER_EGRESS_DECISION,
        SECURITY_POLICY_DECISION,
    ),
    # Review I2 N-7 — VAN's own gate on Jev browser effect. Blueprint §11: no Jev module can
    # carry effect today; PROPOSE_ACTION stays SHADOW until a separate owner decision. The
    # record starts SHADOW_ONLY (pending). Jev's actions go through the Harness, so the
    # Harness decision is inherited like Stagehand's.
    "jev_browser_effect": (
        JEV_BROWSER_EFFECT_DECISION, "VAN-ADOPT-BROWSER-HARNESS-001.yaml", BROWSER_EGRESS_DECISION,
        SECURITY_POLICY_DECISION,
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
    #: Review I4 MINOR-B — a gate whose GREEN value is a *reference* to an owner decision.
    #: GREEN only when the reference resolves to an existing file under the declared
    #: directory, the record pins that file's sha256 and the pin matches, and the record
    #: names an existing, unrevoked Project Truth authorization record for that file.
    OWNER_REFERENCE = "owner_reference"
    #: Unit G12 — a production gate whose GREEN value must be backed by a host qualification
    #: report: the record names a report file under ``report_dir`` and pins its sha256, the
    #: report is for the declared zone, and every ``required_checks`` entry is in it, required
    #: and GREEN. A GREEN word without that report is UNKNOWN; a required check RED is BLOCKED.
    QUALIFY_REPORT = "qualify_report"


#: Kinds that report as an owner decision in ``owner_decisions_pending``.
_OWNER_KINDS = frozenset({GateKind.OWNER_DECISION.value, GateKind.OWNER_REFERENCE.value})


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


_SHA256 = re.compile(r"[0-9a-f]{64}")
_AUTHORIZATION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,127}")


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except (ValueError, OSError):
        return False
    return True


def _classify_owner_reference(
    spec: dict[str, Any], record: dict[str, Any], raw: Any, root: Path, record_source: str
) -> tuple[GateStatus, str | None]:
    """Review I4 MINOR-B. The shape of a reference is not the reference.

    Review I3 MINOR-4 made the Jev effect gate need an owner decision *reference*, but
    checked only that the string looked like ``docs/decisions/OWNER-DECISIONS-*.md``. Three
    plain-text edits citing a file that does not exist made the capability GREEN (probe
    ``jev_spoof.py``). GREEN now needs all of:

    * the reference matches ``green_pattern`` and names a regular file inside
      ``reference_dir`` (no ``..``, no absolute path, no symlink out of the directory);
    * the record carries, at ``sha256_path``, the sha256 of that file, and it matches;
    * the record names, at ``authorization_path``, an authorization id whose record
      ``<authorizations_dir>/<id>.json`` exists, states the same ``authorization_id``, is
      not revoked, has an ``authority`` in ``authorization_authority``, whose
      ``owner_instruction_record`` is the referenced file, and whose ``authorized_paths``
      names this decision record exactly (a glob does not count). The last binding stops an
      existing authorization for a *different* change (e.g. the Stagehand gates record) from
      being cited to open this gate.

    Anything missing, unresolvable or mismatched is UNKNOWN. What this cannot establish is
    who wrote those files; that control is Project Truth owner authority over commits.
    """
    if not isinstance(raw, str) or not raw:
        return GateStatus.UNKNOWN, "owner decision reference is missing"
    pattern = spec["green_pattern"]
    if not re.fullmatch(pattern, raw):
        return GateStatus.UNKNOWN, f"{raw!r} does not have the declared reference shape"
    reference = Path(raw)
    if reference.is_absolute() or ".." in reference.parts:
        return GateStatus.UNKNOWN, f"{raw!r} is not a repository-relative path"
    target = root / reference
    if not _inside(target, root / spec["reference_dir"]):
        return GateStatus.UNKNOWN, f"{raw!r} does not resolve inside {spec['reference_dir']}"
    if not target.is_file():
        return GateStatus.UNKNOWN, f"{raw!r} does not resolve to an existing file"

    try:
        pinned = _resolve(record, spec["sha256_path"])
    except KeyError:
        return GateStatus.UNKNOWN, "owner decision sha256 pin is missing"
    if not isinstance(pinned, str) or not _SHA256.fullmatch(pinned):
        return GateStatus.UNKNOWN, "owner decision sha256 pin is not a lower-case sha256"
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != pinned:
        return GateStatus.UNKNOWN, f"owner decision sha256 mismatch: pinned {pinned}, file {actual}"

    try:
        auth_id = _resolve(record, spec["authorization_path"])
    except KeyError:
        return GateStatus.UNKNOWN, "authorization id is missing"
    if not isinstance(auth_id, str) or not _AUTHORIZATION_ID.fullmatch(auth_id):
        return GateStatus.UNKNOWN, "authorization id is missing or malformed"
    auth_dir = root / spec["authorizations_dir"]
    auth_path = auth_dir / f"{auth_id}.json"
    if not _inside(auth_path, auth_dir) or not auth_path.is_file():
        return GateStatus.UNKNOWN, f"authorization record {auth_id!r} does not exist"
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return GateStatus.UNKNOWN, f"authorization record unreadable: {type(exc).__name__}"
    if not isinstance(auth, dict) or auth.get("authorization_id") != auth_id:
        return GateStatus.UNKNOWN, f"authorization record does not state authorization_id {auth_id!r}"
    if auth.get("revoked") is not False:
        return GateStatus.UNKNOWN, "authorization record is revoked or does not say it is not"
    # Review I6 m8 — an authorization that states an expiry is honoured: expired, or an
    # expiry that cannot be read, is not GREEN (fail closed).
    expired = _authorization_expired(auth)
    if expired is not None:
        return GateStatus.UNKNOWN, expired
    if auth.get("authority") not in spec["authorization_authority"]:
        return GateStatus.UNKNOWN, f"authorization authority {auth.get('authority')!r} is not accepted"
    if auth.get("owner_instruction_record") != raw:
        return GateStatus.UNKNOWN, "authorization record is for a different owner instruction record"
    # Review I5 J1 — the authorization binds the owner's instruction by content, not only by
    # name: it must pin the same bytes the gate record pins (and the file holds).
    if auth.get("owner_instruction_sha256") != pinned:
        return GateStatus.UNKNOWN, "authorization owner_instruction_sha256 does not match the pinned owner decision"
    paths = auth.get("authorized_paths")
    if not isinstance(paths, list) or not any(
        isinstance(entry, str) and entry.split(maxsplit=1)[:1] == [record_source] for entry in paths
    ):
        return GateStatus.UNKNOWN, f"authorization record does not authorize {record_source}"
    # Review I5 J1 — an exclusion wins over an authorization (exactly or by glob).
    excluded = auth.get("excluded_paths", [])
    if not isinstance(excluded, list):
        return GateStatus.UNKNOWN, "authorization excluded_paths is not a list"
    for entry in excluded:
        head = entry.split(maxsplit=1)[:1] if isinstance(entry, str) else []
        if head and (head[0] == record_source or fnmatch.fnmatchcase(record_source, head[0])):
            return GateStatus.UNKNOWN, f"authorization record excludes {record_source}"
    return GateStatus.GREEN, None


def _classify_qualify_report(
    spec: dict[str, Any], record: dict[str, Any], raw: Any, root: Path
) -> tuple[GateStatus, str | None]:
    """Unit G12. GREEN needs the report, not the word (see ``GateKind.QUALIFY_REPORT``)."""
    status, reason = _classify(spec, raw)
    if status is not GateStatus.GREEN:
        return status, reason
    try:
        reference = _resolve(record, spec["report_path"])
        pinned = _resolve(record, spec["sha256_path"])
    except KeyError:
        return GateStatus.UNKNOWN, "qualify report reference or sha256 pin is missing"
    if not isinstance(reference, str) or not reference:
        return GateStatus.UNKNOWN, "qualify report reference is missing"
    path = Path(reference)
    if path.is_absolute() or ".." in path.parts:
        return GateStatus.UNKNOWN, f"{reference!r} is not a repository-relative path"
    target = root / path
    if not _inside(target, root / spec["report_dir"]) or not target.is_file():
        return GateStatus.UNKNOWN, f"{reference!r} is not a file inside {spec['report_dir']}"
    if not isinstance(pinned, str) or not _SHA256.fullmatch(pinned):
        return GateStatus.UNKNOWN, "qualify report sha256 pin is not a lower-case sha256"
    data = target.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != pinned:
        return GateStatus.UNKNOWN, f"qualify report sha256 mismatch: pinned {pinned}, file {actual}"
    try:
        report = json.loads(data)
        checks = {c["check"]: c for c in report["checks"]}
    except (ValueError, KeyError, TypeError) as exc:
        return GateStatus.UNKNOWN, f"qualify report unreadable: {type(exc).__name__}"
    if report.get("zone") != spec["zone"]:
        return GateStatus.UNKNOWN, f"qualify report is for zone {report.get('zone')!r}, not {spec['zone']!r}"
    # Review I8 MINOR-1: a report is GREEN only as a whole. qualify.sh exits non-zero when any
    # required check is not GREEN (``fails`` counts them); a report with fails > 0, or a
    # required check that is not GREEN among checks the model does not list, is not a pass.
    fails = report.get("fails")
    if isinstance(fails, bool) or not isinstance(fails, int) or fails < 0:
        return GateStatus.UNKNOWN, "qualify report has no valid fails count"
    failing = sorted(name for name, c in checks.items() if c.get("required") == 1 and c.get("status") != "GREEN")
    if fails or failing:
        return GateStatus.BLOCKED, f"qualify report failed: fails={fails}; required checks not GREEN: {', '.join(failing) or '-'}"
    missing = [name for name in spec["required_checks"] if name not in checks]
    if missing:
        return GateStatus.UNKNOWN, f"qualify report lacks checks: {', '.join(missing)}"
    red = [name for name in spec["required_checks"] if checks[name].get("status") == "RED"]
    if red:
        return GateStatus.BLOCKED, f"qualify report checks RED: {', '.join(red)}"
    not_green = [name for name in spec["required_checks"]
                 if checks[name].get("status") != "GREEN" or checks[name].get("required") != 1]
    if not_green:
        return GateStatus.UNKNOWN, f"qualify report checks not GREEN and required: {', '.join(not_green)}"
    return GateStatus.GREEN, None


#: Expiry fields an authorization record may carry (any one present is honoured).
AUTHORIZATION_EXPIRY_FIELDS = ("expires_at", "expires_at_utc", "not_after", "not_after_utc")


def _authorization_expired(auth: dict[str, Any], now: Any = None) -> str | None:
    """None when no expiry field is present or every present one is in the future; else why
    the authorization is not usable (expired, or an unreadable/naive timestamp)."""
    from datetime import datetime, timezone

    current = now or datetime.now(timezone.utc)
    for field in AUTHORIZATION_EXPIRY_FIELDS:
        if field not in auth:
            continue
        value = auth[field]
        if value is None:
            continue
        if not isinstance(value, str):
            return f"authorization {field} is not an ISO-8601 timestamp"
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return f"authorization {field} is not an ISO-8601 timestamp"
        if moment.tzinfo is None:
            return f"authorization {field} has no time zone"
        if moment <= current:
            return f"authorization expired ({field} {value})"
    return None


def _gate_spec_problem(spec: Any) -> str | None:
    if not isinstance(spec, dict):
        return "gate spec is not an object"
    for field in ("id", "kind", "path"):
        if not isinstance(spec.get(field), str) or not spec[field]:
            return f"gate spec lacks {field}"
    if spec["kind"] not in {k.value for k in GateKind}:
        return f"unknown gate kind {spec['kind']!r}"
    if spec["kind"] == GateKind.OWNER_REFERENCE.value:
        for field in ("green_pattern", "reference_dir", "sha256_path", "authorization_path",
                      "authorizations_dir"):
            if not isinstance(spec.get(field), str) or not spec[field]:
                return f"owner_reference gate lacks {field}"
        accepted = spec.get("authorization_authority")
        if not isinstance(accepted, list) or not accepted or not all(isinstance(a, str) for a in accepted):
            return "owner_reference gate lacks authorization_authority"
        try:
            re.compile(spec["green_pattern"])
        except re.error:
            return "gate green_pattern is not a valid regular expression"
        return None
    if spec["kind"] == GateKind.QUALIFY_REPORT.value:
        for field in ("report_path", "sha256_path", "report_dir", "zone"):
            if not isinstance(spec.get(field), str) or not spec[field]:
                return f"qualify_report gate lacks {field}"
        checks = spec.get("required_checks")
        if not isinstance(checks, list) or not checks or not all(isinstance(c, str) and c for c in checks):
            return "qualify_report gate lacks required_checks"
    # Review I4 MINOR-B: a pattern match is a shape, never a GREEN on its own. Only an
    # owner_reference gate, which also resolves and pins the file, may declare one.
    if spec.get("green_pattern") is not None:
        return "green_pattern is only accepted on an owner_reference gate"
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
            if kind == GateKind.OWNER_REFERENCE.value:
                status, reason = _classify_owner_reference(spec, record, raw, root, source)
            elif kind == GateKind.QUALIFY_REPORT.value:
                status, reason = _classify_qualify_report(spec, record, raw, root)
            else:
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
            if r.kind in _OWNER_KINDS
            and r.status is not GateStatus.GREEN
            and r.decision not in missing
        }
    )
    not_green = [
        f"{r.decision}:{r.gate}"
        for r in results
        if r.kind in (GateKind.PRODUCTION.value, GateKind.QUALIFY_REPORT.value) and r.status is not GateStatus.GREEN
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


__all__ = ["BROWSER_EGRESS_DECISION", "CAPABILITY_DECISIONS", "GATE_MODEL", "JEV_BROWSER_EFFECT_DECISION", "DuplicateKeyError", "GateKind", "GateResult", "GateStatus", "evaluate_production_gates"]
