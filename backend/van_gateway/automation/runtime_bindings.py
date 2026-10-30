"""Persist semantic candidates separately from concrete, verified n8n bindings."""
from __future__ import annotations

import json
import time
from typing import Any

from van_gateway.automation.canonical import digest
from van_gateway.storage.db import Store


class RuntimeBindingStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def ensure(self) -> None:
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_runtime_bindings (
            artifact_id TEXT PRIMARY KEY REFERENCES automation_artifacts(artifact_id),
            ir_json TEXT NOT NULL, semantic_graph_json TEXT NOT NULL, runtime_graph_json TEXT,
            semantic_digest TEXT NOT NULL, full_digest TEXT,
            dependencies_json TEXT NOT NULL DEFAULT '{}',
            binding_state TEXT NOT NULL DEFAULT 'CANDIDATE', n8n_workflow_id TEXT,
            readiness_errors_json TEXT NOT NULL, created_at_ms INTEGER NOT NULL, updated_at_ms INTEGER NOT NULL
        )""")

    async def get(self, artifact_id: str) -> dict[str, Any] | None:
        await self.ensure()
        row = await self.store.fetchone("SELECT * FROM automation_runtime_bindings WHERE artifact_id=?", (artifact_id,))
        if row is None:
            return None
        value = dict(row)
        for column, key in (("ir_json", "ir"), ("semantic_graph_json", "semantic_graph"),
                            ("runtime_graph_json", "runtime_graph"), ("readiness_errors_json", "readiness_errors")):
            value[key] = json.loads(value.pop(column)) if value[column] is not None else None
        value["dependencies"] = json.loads(value.pop("dependencies_json"))
        return value

    @staticmethod
    def compute_full_digest(runtime_graph, dependencies=None):
        return digest({"parent": runtime_graph, "dependencies": dependencies}) if dependencies else digest(runtime_graph)

    @staticmethod
    def dependency_ids(runtime_graph):
        return {node.get("parameters", {}).get("workflowId", {}).get("value")
                for node in runtime_graph.get("nodes", []) if node.get("type") == "n8n-nodes-base.executeWorkflow"}

    async def record(self, *, artifact_id: str, ir: dict[str, Any], semantic_graph: dict[str, Any],
                     runtime_graph: dict[str, Any] | None, readiness_errors: list[str],
                     dependencies: dict[str, Any] | None = None) -> dict[str, Any]:
        await self.ensure()
        prior = await self.get(artifact_id)
        if prior and prior["binding_state"] == "DEPLOYED":
            raise ValueError("deployed_runtime_binding_is_immutable")
        now = int(time.time() * 1000)
        await self.store.execute("""INSERT INTO automation_runtime_bindings(
            artifact_id,ir_json,semantic_graph_json,runtime_graph_json,semantic_digest,full_digest,dependencies_json,
            binding_state,n8n_workflow_id,readiness_errors_json,created_at_ms,updated_at_ms
        ) VALUES (?,?,?,?,?,?,?,'CANDIDATE',NULL,?,?,?)
        ON CONFLICT(artifact_id) DO UPDATE SET ir_json=excluded.ir_json,
            semantic_graph_json=excluded.semantic_graph_json,runtime_graph_json=excluded.runtime_graph_json,
            semantic_digest=excluded.semantic_digest,full_digest=excluded.full_digest,
            dependencies_json=excluded.dependencies_json,
            readiness_errors_json=excluded.readiness_errors_json,updated_at_ms=excluded.updated_at_ms""",
            (artifact_id, Store.dumps(ir), Store.dumps(semantic_graph), Store.dumps(runtime_graph) if runtime_graph else None,
             digest(semantic_graph), self.compute_full_digest(runtime_graph, dependencies) if runtime_graph else None,
             Store.dumps(dependencies or {}), Store.dumps(sorted(readiness_errors)), now, now))
        return await self.get(artifact_id)

    async def mark_deployed(self, artifact_id: str, workflow_id: str) -> dict[str, Any]:
        value = await self.get(artifact_id)
        if value is None or not value["runtime_graph"] or value["readiness_errors"]:
            raise ValueError("runtime_binding_not_deployable")
        if self.dependency_ids(value["runtime_graph"]) != set(value["dependencies"]):
            raise ValueError("runtime_dependencies_not_sealed")
        if value["binding_state"] == "DEPLOYED":
            if value["n8n_workflow_id"] != workflow_id:
                raise ValueError("deployed_runtime_binding_is_immutable")
            return value
        await self.store.execute("UPDATE automation_runtime_bindings SET binding_state='DEPLOYED',n8n_workflow_id=?,updated_at_ms=? WHERE artifact_id=? AND binding_state='CANDIDATE'",
                                 (workflow_id, int(time.time() * 1000), artifact_id))
        return await self.get(artifact_id)
