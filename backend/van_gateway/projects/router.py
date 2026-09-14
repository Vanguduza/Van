from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from van_gateway.models import DegradedCode
from van_gateway.storage.db import Store


class ProjectRouter:
    def __init__(self, store: Store, registry_path: str) -> None:
        self.store = store
        self.registry_path = registry_path
        self._registry = self._load_registry()

    def _load_registry(self) -> dict[str, Any]:
        path = Path(self.registry_path)
        if not path.exists():
            return {"projects": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def known_projects(self) -> list[str]:
        return [p["id"] for p in self._registry.get("projects", [])]

    async def load_truth(self, project_id: str) -> dict[str, Any]:
        if project_id not in self.known_projects():
            return {"ok": False, "error": "unknown_project", "degraded": DegradedCode.REPO_UNAVAILABLE.value}
        row = await self.store.fetchone(
            "SELECT project_id, truth_sha, repo_sha, truth_json, updated_at_unix, stale FROM project_truth_cache WHERE project_id = ?",
            (project_id,),
        )
        if row is None:
            return {
                "ok": False,
                "project_id": project_id,
                "error": "truth_missing",
                "degraded": DegradedCode.STALE_PROJECT_TRUTH.value,
            }
        if int(row["stale"]) == 1:
            return {
                "ok": False,
                "project_id": project_id,
                "error": "truth_stale",
                "truth_sha": row["truth_sha"],
                "repo_sha": row["repo_sha"],
                "degraded": DegradedCode.STALE_PROJECT_TRUTH.value,
            }
        return {
            "ok": True,
            "project_id": project_id,
            "truth_sha": row["truth_sha"],
            "repo_sha": row["repo_sha"],
            "truth": json.loads(row["truth_json"]) if row["truth_json"] else {},
            "updated_at_unix": int(row["updated_at_unix"]),
        }

    async def cache_truth(self, project_id: str, truth: dict[str, Any], truth_sha: str, repo_sha: str | None = None) -> None:
        now = int(time.time())
        await self.store.execute(
            """
            INSERT INTO project_truth_cache(project_id, truth_sha, repo_sha, truth_json, updated_at_unix, stale)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(project_id) DO UPDATE SET
              truth_sha=excluded.truth_sha,
              repo_sha=excluded.repo_sha,
              truth_json=excluded.truth_json,
              updated_at_unix=excluded.updated_at_unix,
              stale=0
            """,
            (project_id, truth_sha, repo_sha, Store.dumps(truth), now),
        )

    async def mark_stale(self, project_id: str) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE project_truth_cache SET stale = 1, updated_at_unix = ? WHERE project_id = ?",
            (now, project_id),
        )

    def decompose_cross_project(self, text: str) -> list[dict[str, str]]:
        """Deterministic keyword decomposition — not LLM guessing."""
        lowered = text.lower()
        hits = []
        for project_id in self.known_projects():
            if project_id in lowered:
                hits.append({"project_id": project_id, "operation": "status_or_delegate", "excerpt": text})
        return hits
