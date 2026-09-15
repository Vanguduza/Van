from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mounts_and_registry_cover_the_same_six_projects():
    projects = {p["id"] for p in json.loads((ROOT / "registries" / "projects.json").read_text(encoding="utf-8"))["projects"]}
    mounts = {m["project_id"] for m in json.loads((ROOT / "registries" / "project_mounts.json").read_text(encoding="utf-8"))["mounts"]}
    expected = {"van", "dial", "dde", "gtr", "goat", "aeci"}
    assert projects == expected
    assert mounts == expected


def test_each_mount_path_is_unique_per_project():
    mounts = json.loads((ROOT / "registries" / "project_mounts.json").read_text(encoding="utf-8"))["mounts"]
    paths = [Path(m["path"]).resolve().as_posix().lower() for m in mounts]
    assert len(paths) == len(set(paths))


def test_offline_truth_cache_artifacts_are_self_labelled():
    cache = ROOT / "artifacts" / "project-truth"
    for project_id in ("van", "dial", "dde", "gtr", "goat", "aeci"):
        payload = json.loads((cache / f"{project_id}.json").read_text(encoding="utf-8"))
        assert payload["truth"]["project_id"] == project_id
        assert len(payload["truth_sha"]) == 64
