from __future__ import annotations

from typing import Any

from .rig_ir import require_valid_rig_ir

SUPPORTED_ATTACHMENT_TYPES = {"mesh"}


def _skins(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("skins") or []
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        return [{"name": name, "attachments": attachments} for name, attachments in raw.items()]
    raise ValueError("Spine skins must be a list or object")


def _decode_mesh_vertices(attachment: dict[str, Any], bone_names: list[str]) -> tuple[list[list[float]], list[list[dict[str, Any]]]]:
    uvs = attachment.get("uvs") or []
    raw = attachment.get("vertices") or []
    if len(uvs) % 2:
        raise ValueError("Spine mesh UV count is odd")
    vertex_count = len(uvs) // 2

    if len(raw) == vertex_count * 2:
        vertices = [[float(raw[i]), float(raw[i + 1])] for i in range(0, len(raw), 2)]
        default_bone = str(attachment.get("_slot_bone") or "")
        return vertices, [[{"bone": default_bone, "weight": 1.0}] for _ in vertices]

    vertices: list[list[float]] = []
    weights: list[list[dict[str, Any]]] = []
    cursor = 0
    for _ in range(vertex_count):
        if cursor >= len(raw):
            raise ValueError("Spine weighted mesh vertex stream ended early")
        bone_count = int(raw[cursor])
        cursor += 1
        if bone_count <= 0 or bone_count > 32:
            raise ValueError("Spine weighted mesh has invalid bone count")
        local_x = 0.0
        local_y = 0.0
        influences: list[dict[str, Any]] = []
        for _ in range(bone_count):
            if cursor + 3 >= len(raw):
                raise ValueError("Spine weighted mesh influence stream ended early")
            bone_index = int(raw[cursor])
            x = float(raw[cursor + 1])
            y = float(raw[cursor + 2])
            weight = float(raw[cursor + 3])
            cursor += 4
            if bone_index < 0 or bone_index >= len(bone_names):
                raise ValueError("Spine weighted mesh references invalid bone index")
            local_x += x * weight
            local_y += y * weight
            influences.append({"bone": bone_names[bone_index], "weight": weight})
        total = sum(x["weight"] for x in influences)
        if total <= 0:
            raise ValueError("Spine weighted mesh has zero total weight")
        for influence in influences:
            influence["weight"] = influence["weight"] / total
        if len(influences) > 4:
            influences = sorted(influences, key=lambda x: x["weight"], reverse=True)[:4]
            total = sum(x["weight"] for x in influences)
            for influence in influences:
                influence["weight"] /= total
        vertices.append([local_x, local_y])
        weights.append(influences)

    if cursor != len(raw):
        raise ValueError("Spine weighted mesh vertex stream has trailing data")
    return vertices, weights


def import_spine_json(
    payload: dict[str, Any],
    *,
    source_master_sha256: str,
    part_provenance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    skeleton = payload.get("skeleton") or {}
    spine_version = str(skeleton.get("spine") or "")
    if not spine_version.startswith("4."):
        raise ValueError(f"only Spine 4.x proposals are supported, got {spine_version!r}")

    raw_bones = payload.get("bones") or []
    if not raw_bones:
        raise ValueError("Spine proposal has no bones")
    bone_names = [str(row.get("name") or "") for row in raw_bones]
    if any(not name for name in bone_names):
        raise ValueError("Spine proposal contains an unnamed bone")
    bones = [{
        "id": name,
        "name": name,
        "parent": row.get("parent"),
        "x": float(row.get("x", 0.0)),
        "y": float(row.get("y", 0.0)),
        "rotation": float(row.get("rotation", 0.0)),
        "scale_x": float(row.get("scaleX", 1.0)),
        "scale_y": float(row.get("scaleY", 1.0)),
    } for name, row in zip(bone_names, raw_bones)]

    slot_bone: dict[str, str] = {}
    slot_order: list[str] = []
    for slot in payload.get("slots") or []:
        name = str(slot.get("name") or "")
        bone = str(slot.get("bone") or "")
        if not name or not bone:
            raise ValueError("Spine slot missing name or bone")
        slot_bone[name] = bone
        slot_order.append(name)

    meshes: list[dict[str, Any]] = []
    draw_order: list[str] = []
    for skin in _skins(payload):
        attachments = skin.get("attachments") or {}
        if not isinstance(attachments, dict):
            continue
        for slot_name in slot_order:
            slot_attachments = attachments.get(slot_name) or {}
            if not isinstance(slot_attachments, dict):
                continue
            for attachment_name, attachment in slot_attachments.items():
                if not isinstance(attachment, dict):
                    continue
                kind = attachment.get("type", "region")
                if kind != "mesh":
                    continue
                part = str(attachment.get("name") or attachment_name)
                provenance = part_provenance.get(part)
                if provenance is None:
                    raise ValueError(f"no provenance supplied for imported part {part}")
                copy = dict(attachment)
                copy["_slot_bone"] = slot_bone.get(slot_name, "")
                vertices, weights = _decode_mesh_vertices(copy, bone_names)
                triangles_raw = attachment.get("triangles") or []
                if len(triangles_raw) % 3:
                    raise ValueError(f"Spine mesh {part} triangle stream is not divisible by 3")
                triangles = [[int(triangles_raw[i]), int(triangles_raw[i+1]), int(triangles_raw[i+2])]
                             for i in range(0, len(triangles_raw), 3)]
                meshes.append({
                    "part": part,
                    "vertices": vertices,
                    "triangles": triangles,
                    "weights": weights,
                    "provenance": provenance["provenance"],
                    "approved_occlusion_receipt": provenance.get("approved_occlusion_receipt"),
                })
                draw_order.append(part)

    rig = {
        "schema_version": 1,
        "source_master_sha256": source_master_sha256,
        "toolchain": {
            "source": "stretchy_studio_spine_export",
            "spine_version": spine_version,
        },
        "bones": bones,
        "meshes": meshes,
        "draw_order": draw_order,
        "constraints": [],
        "animations": {},
        "provenance": {"source": "Spine proposal imported fail-closed"},
    }
    require_valid_rig_ir(rig)
    return rig
