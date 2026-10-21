"""Closed, bounded data operations. Nothing here evaluates code or expressions."""
from __future__ import annotations

import math
import re
from typing import Any

from van_gateway.automation.canonical import canonical_json

MAX_DEPTH = 8
MAX_NODES = 64
MAX_FIELDS = 64
MAX_CASES = 10
_PATH = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*")
_MISSING = object()


class DslError(ValueError):
    pass


def bounded_json(value: Any) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 16 or count > 8192:
            raise DslError("DSL_DATA_LIMIT")
        if isinstance(item, dict):
            if any(not isinstance(key, str) or len(key) > 128 for key in item):
                raise DslError("DSL_DATA_KEY_INVALID")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif type(item) not in (str, int, float, bool, type(None)) or (type(item) is float and not math.isfinite(item)):
            raise DslError("DSL_DATA_INVALID")
    if len(canonical_json(value)) > 1024 * 1024:
        raise DslError("DSL_DATA_LIMIT")


def validate_value(spec: Any) -> None:
    if not isinstance(spec, dict):
        raise DslError("DSL_VALUE_INVALID")
    if spec.get("kind") == "LITERAL" and set(spec) == {"kind", "value"}:
        bounded_json(spec["value"])
    elif spec.get("kind") == "PATH" and set(spec) == {"kind", "path"}:
        path = spec["path"]
        if not isinstance(path, str) or len(path) > 256 or not _PATH.fullmatch(path):
            raise DslError("DSL_PATH_INVALID")
    else:
        raise DslError("DSL_VALUE_INVALID")


def value_of(spec: dict, context: dict, *, missing: bool = False) -> Any:
    validate_value(spec)
    if spec["kind"] == "LITERAL":
        return spec["value"]
    value: Any = context
    for part in spec["path"].split("."):
        if not isinstance(value, dict) or part not in value:
            if missing:
                return _MISSING
            raise DslError("DSL_PATH_MISSING")
        value = value[part]
    return value


def validate_predicate(predicate: Any) -> None:
    pending = [(predicate, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise DslError("DSL_PREDICATE_LIMIT")
        if not isinstance(item, dict):
            raise DslError("DSL_PREDICATE_INVALID")
        op = item.get("op")
        if not isinstance(op, str):
            raise DslError("DSL_PREDICATE_INVALID")
        if op in {"ALL", "ANY"}:
            if set(item) != {"op", "args"} or not isinstance(item["args"], list) or not 1 <= len(item["args"]) <= 16:
                raise DslError("DSL_PREDICATE_INVALID")
            pending.extend((child, depth + 1) for child in item["args"])
        elif op == "NOT":
            if set(item) != {"op", "arg"}:
                raise DslError("DSL_PREDICATE_INVALID")
            pending.append((item["arg"], depth + 1))
        elif op == "EXISTS":
            if set(item) != {"op", "value"} or not isinstance(item["value"], dict) or item["value"].get("kind") != "PATH":
                raise DslError("DSL_PREDICATE_INVALID")
            validate_value(item["value"])
        elif op in {"EQ", "NE", "LT", "LTE", "GT", "GTE", "IN", "CONTAINS"}:
            if set(item) != {"op", "left", "right"}:
                raise DslError("DSL_PREDICATE_INVALID")
            validate_value(item["left"])
            validate_value(item["right"])
        else:
            raise DslError("DSL_PREDICATE_UNSUPPORTED")


def evaluate(predicate: dict, context: dict) -> bool:
    validate_predicate(predicate)
    bounded_json(context)

    def run(item: dict) -> bool:
        op = item["op"]
        # Evaluate every child. An absent operand cannot hide behind short circuit.
        if op in {"ALL", "ANY"}:
            results = [run(child) for child in item["args"]]
            return all(results) if op == "ALL" else any(results)
        if op == "NOT":
            return not run(item["arg"])
        if op == "EXISTS":
            return value_of(item["value"], context, missing=True) is not _MISSING
        left, right = value_of(item["left"], context), value_of(item["right"], context)
        if op in {"EQ", "NE"}:
            equal = type(left) is type(right) and canonical_json(left) == canonical_json(right)
            return equal if op == "EQ" else not equal
        if op in {"LT", "LTE", "GT", "GTE"}:
            if type(left) not in (int, float) or type(right) not in (int, float):
                raise DslError("DSL_COMPARISON_TYPE_INVALID")
            return {"LT": left < right, "LTE": left <= right, "GT": left > right, "GTE": left >= right}[op]
        if op == "IN":
            if not isinstance(right, list) or len(right) > 256:
                raise DslError("DSL_MEMBERSHIP_TYPE_INVALID")
            return any(type(left) is type(candidate) and canonical_json(left) == canonical_json(candidate) for candidate in right)
        if isinstance(left, list) and len(left) <= 256:
            return any(type(right) is type(candidate) and canonical_json(right) == canonical_json(candidate) for candidate in left)
        if isinstance(left, str) and isinstance(right, str):
            return right in left
        raise DslError("DSL_MEMBERSHIP_TYPE_INVALID")

    return run(predicate)


def map_fields(payload: Any, fields: Any) -> dict:
    validate_mapping(fields)
    result = {target: value_of(spec, {"payload": payload}) for target, spec in fields.items()}
    bounded_json(result)
    return result


def validate_mapping(fields: Any) -> None:
    if not isinstance(fields, dict) or not 1 <= len(fields) <= MAX_FIELDS:
        raise DslError("DSL_MAPPING_INVALID")
    for target, spec in fields.items():
        if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", target):
            raise DslError("DSL_MAPPING_TARGET_INVALID")
        validate_value(spec)


def validate_readback(predicate: Any) -> None:
    """Every clause observes actual target data against a sealed literal."""
    validate_predicate(predicate)
    pending = [predicate]
    while pending:
        item = pending.pop()
        if item["op"] in {"ALL", "ANY"}:
            pending.extend(item["args"])
        elif item["op"] == "NOT":
            pending.append(item["arg"])
        else:
            operands = [item["value"]] if item["op"] == "EXISTS" else [item["left"], item["right"]]
            paths = [operand for operand in operands if operand["kind"] == "PATH"]
            if len(paths) != 1 or not (paths[0]["path"] == "payload" or paths[0]["path"].startswith("payload.")):
                raise DslError("DSL_READBACK_NOT_OBSERVABLE")


def branches(value: dict) -> list[str]:
    if set(value) != {"payload", "cases", "default_branch"} or not isinstance(value["cases"], list) or not 1 <= len(value["cases"]) <= MAX_CASES:
        raise DslError("DSL_SWITCH_INVALID")
    labels = []
    for case in value["cases"]:
        if not isinstance(case, dict) or set(case) != {"branch", "predicate"}:
            raise DslError("DSL_SWITCH_INVALID")
        labels.append(case["branch"])
        validate_predicate(case["predicate"])
    labels.append(value["default_branch"])
    if any(not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", label) for label in labels) or len(labels) != len(set(labels)):
        raise DslError("DSL_BRANCH_LABEL_INVALID")
    return labels


def select_branch(value: dict) -> dict:
    branches(value)
    matches = [evaluate(case["predicate"], {"payload": value["payload"]}) for case in value["cases"]]
    index = next((index for index, matched in enumerate(matches) if matched), None)
    return {"selected_branch": value["default_branch"] if index is None else value["cases"][index]["branch"],
            "matched_case": index, "predicate_results": matches, "payload": value["payload"],
            "source_trust": "UNTRUSTED_EXTERNAL"}


def pure_result(primitive: str, operation: str, value: dict) -> dict | None:
    if primitive == "FILTER" and operation == "evaluate_predicate":
        if set(value) != {"payload", "predicate"}:
            raise DslError("DSL_FILTER_INVALID")
        matched = evaluate(value["predicate"], {"payload": value["payload"]})
        return {"matched": matched, "selected_branch": "true" if matched else "false", "payload": value["payload"], "source_trust": "UNTRUSTED_EXTERNAL"}
    if primitive == "SWITCH" and operation == "select_branch":
        return select_branch(value)
    if primitive == "MAP_FIELDS" and operation == "map_fields":
        if set(value) != {"payload", "fields"}:
            raise DslError("DSL_MAPPING_INVALID")
        return {"payload": map_fields(value["payload"], value["fields"]), "source_trust": "UNTRUSTED_EXTERNAL"}
    if primitive == "MERGE" and operation == "merge_objects":
        if set(value) != {"sources"} or not isinstance(value["sources"], list) or not 1 <= len(value["sources"]) <= 16:
            raise DslError("DSL_MERGE_INVALID")
        merged = {}
        for source in value["sources"]:
            if source is None:
                continue
            if not isinstance(source, dict) or set(source) & set(merged):
                raise DslError("DSL_MERGE_CONFLICT")
            merged.update(source)
        bounded_json(merged)
        return {"payload": merged, "source_trust": "UNTRUSTED_EXTERNAL"}
    return None
