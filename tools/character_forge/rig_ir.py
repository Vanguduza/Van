from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

from .provenance import classify_layer

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_CONSTRAINTS = {"two_bone_ik", "rotation_limit", "transform_copy"}


@dataclass(frozen=True)
class RigValidation:
    ok: bool
    problems: tuple[str, ...]


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def validate_rig_ir(data: dict[str, Any]) -> RigValidation:
    problems: list[str] = []
    if data.get("schema_version") != 1:
        problems.append("schema_version must be 1")

    source_sha = str(data.get("source_master_sha256") or "")
    if not SHA256.fullmatch(source_sha):
        problems.append("source_master_sha256 must be 64 lowercase hex characters")

    bones = data.get("bones")
    if not isinstance(bones, list) or not bones:
        problems.append("bones must be a non-empty list")
        bones = []
    bone_ids = [str(row.get("id") or "") for row in bones if isinstance(row, dict)]
    for duplicate in _duplicates(bone_ids):
        problems.append(f"duplicate bone id: {duplicate}")
    bone_set = set(bone_ids)

    roots = []
    parents: dict[str, str | None] = {}
    for row in bones:
        if not isinstance(row, dict):
            problems.append("bone row is not an object")
            continue
        bone_id = str(row.get("id") or "")
        parent = row.get("parent")
        parent = None if parent is None else str(parent)
        parents[bone_id] = parent
        if parent is None:
            roots.append(bone_id)
        elif parent not in bone_set:
            problems.append(f"bone {bone_id} references missing parent {parent}")
        for field in ("x", "y", "rotation", "scale_x", "scale_y"):
            if not isinstance(row.get(field), (int, float)):
                problems.append(f"bone {bone_id} field {field} is not numeric")

    if bones and len(roots) != 1:
        problems.append(f"rig must have exactly one root bone, found {len(roots)}")

    for bone_id in bone_ids:
        cursor = bone_id
        visited: set[str] = set()
        while cursor is not None:
            if cursor in visited:
                problems.append(f"bone cycle detected at {cursor}")
                break
            visited.add(cursor)
            cursor = parents.get(cursor)

    meshes = data.get("meshes")
    if not isinstance(meshes, list):
        problems.append("meshes must be a list")
        meshes = []
    parts = [str(row.get("part") or "") for row in meshes if isinstance(row, dict)]
    for duplicate in _duplicates(parts):
        problems.append(f"duplicate mesh part: {duplicate}")

    for mesh in meshes:
        if not isinstance(mesh, dict):
            problems.append("mesh row is not an object")
            continue
        part = str(mesh.get("part") or "<unnamed>")
        vertices = mesh.get("vertices") or []
        triangles = mesh.get("triangles") or []
        weights = mesh.get("weights") or []
        if not vertices:
            problems.append(f"mesh {part} has no vertices")
        if len(weights) != len(vertices):
            problems.append(f"mesh {part} weights length differs from vertices")
        for index, vertex in enumerate(vertices):
            if not isinstance(vertex, list) or len(vertex) != 2 or not all(isinstance(x, (int, float)) for x in vertex):
                problems.append(f"mesh {part} vertex {index} is invalid")
        for tri in triangles:
            if not isinstance(tri, list) or len(tri) != 3 or not all(isinstance(x, int) for x in tri):
                problems.append(f"mesh {part} has invalid triangle")
                continue
            if any(x < 0 or x >= len(vertices) for x in tri):
                problems.append(f"mesh {part} triangle index out of range")
        for index, row in enumerate(weights):
            if not isinstance(row, list) or not row:
                problems.append(f"mesh {part} vertex {index} has no weights")
                continue
            if len(row) > 4:
                problems.append(f"mesh {part} vertex {index} has more than four bone weights")
            total = 0.0
            for influence in row:
                if not isinstance(influence, dict):
                    problems.append(f"mesh {part} vertex {index} has invalid influence")
                    continue
                bone = str(influence.get("bone") or "")
                weight = influence.get("weight")
                if bone not in bone_set:
                    problems.append(f"mesh {part} vertex {index} references missing bone {bone}")
                if not isinstance(weight, (int, float)) or not 0 <= float(weight) <= 1:
                    problems.append(f"mesh {part} vertex {index} has invalid weight")
                else:
                    total += float(weight)
            if row and abs(total - 1.0) > 1e-3:
                problems.append(f"mesh {part} vertex {index} weights sum to {total:.6f}, not 1")
        report = classify_layer(mesh)
        problems.extend(f"mesh {part}: {finding.code}" for finding in report.findings)

    draw_order = data.get("draw_order")
    if not isinstance(draw_order, list):
        problems.append("draw_order must be a list")
    else:
        unknown = [part for part in draw_order if part not in set(parts)]
        if unknown:
            problems.append("draw_order references unknown parts: " + ",".join(map(str, unknown)))
        missing = [part for part in parts if part not in draw_order]
        if missing:
            problems.append("draw_order omits parts: " + ",".join(missing))
        if len(draw_order) != len(set(draw_order)):
            problems.append("draw_order contains duplicates")

    constraints = data.get("constraints")
    if not isinstance(constraints, list):
        problems.append("constraints must be a list")
        constraints = []
    for constraint in constraints:
        if not isinstance(constraint, dict):
            problems.append("constraint row is not an object")
            continue
        kind = constraint.get("type")
        target = str(constraint.get("target") or "")
        if kind not in SUPPORTED_CONSTRAINTS:
            problems.append(f"unsupported constraint: {kind}")
        if target not in bone_set:
            problems.append(f"constraint target missing bone: {target}")

    return RigValidation(not problems, tuple(dict.fromkeys(problems)))


def require_valid_rig_ir(data: dict[str, Any]) -> None:
    report = validate_rig_ir(data)
    if not report.ok:
        raise ValueError("invalid CF Rig IR:\n- " + "\n- ".join(report.problems))
