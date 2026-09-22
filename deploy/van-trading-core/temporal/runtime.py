from __future__ import annotations

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from workflows import VanDurableWorkflow


TEMPORAL_ADDRESS = os.environ.get("VAN_TEMPORAL_ADDRESS", "").strip()
TEMPORAL_NAMESPACE = os.environ.get("VAN_TEMPORAL_NAMESPACE", "van").strip() or "van"
TASK_QUEUE = os.environ.get("VAN_TEMPORAL_TASK_QUEUE", "van-critical").strip() or "van-critical"
BRIDGE_HOST = os.environ.get("VAN_TEMPORAL_BRIDGE_HOST", "127.0.0.1").strip() or "127.0.0.1"
BRIDGE_PORT = int(os.environ.get("VAN_TEMPORAL_BRIDGE_PORT", "9150"))
TOKEN_FILE = os.environ.get(
    "VAN_TEMPORAL_BRIDGE_TOKEN_FILE",
    "/opt/van-trading/secrets/temporal-bridge.token",
)
EVIDENCE_ROOT = Path(
    os.environ.get(
        "VAN_TEMPORAL_EVIDENCE_ROOT",
        "/var/lib/van-trading/evidence/temporal",
    )
)


class StartBody(BaseModel):
    workflow_id: str = Field(min_length=3, max_length=256)
    process_kind: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=86_400, ge=1, le=30 * 24 * 3600)


class SignalBody(BaseModel):
    command: str = Field(pattern="^(COMPLETE|FAIL|CANCEL|CHECKPOINT)$")
    detail: str = Field(default="", max_length=4000)
    evidence_pointer: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


def _read_token() -> str:
    try:
        token = Path(TOKEN_FILE).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"temporal_bridge_token_unavailable:{exc}") from exc
    if len(token) < 32:
        raise RuntimeError("temporal_bridge_token_too_short")
    return token


BRIDGE_TOKEN = _read_token()
CLIENT: Client | None = None


def _authorize(token: str | None) -> None:
    if token is None or not hmac.compare_digest(token, BRIDGE_TOKEN):
        raise HTTPException(status_code=401, detail="temporal_bridge_unauthorized")


@activity.defn(name="record_temporal_checkpoint")
async def record_temporal_checkpoint(row: dict[str, Any]) -> dict[str, Any]:
    """Append token-free lifecycle evidence for a durable workflow."""

    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    workflow_id = str(row.get("workflow_id", "unknown"))
    safe = "".join(ch for ch in workflow_id if ch.isalnum() or ch in "-_.")[:180] or "unknown"
    path = EVIDENCE_ROOT / f"{safe}.jsonl"
    record = {
        "workflow_id": workflow_id,
        "process_kind": str(row.get("process_kind", "")),
        "status": str(row.get("status", "")),
        "detail": str(row.get("detail", "")),
        "evidence_pointer": row.get("evidence_pointer"),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return {"recorded": True, "path": str(path)}


async def _status(workflow_id: str) -> dict[str, Any]:
    assert CLIENT is not None
    handle = CLIENT.get_workflow_handle(workflow_id)
    try:
        state = await handle.query("status")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"temporal_workflow_unavailable:{exc}") from exc
    return dict(state)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global CLIENT
    if not TEMPORAL_ADDRESS:
        raise RuntimeError("VAN_TEMPORAL_ADDRESS is required")
    CLIENT = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    worker = Worker(
        CLIENT,
        task_queue=TASK_QUEUE,
        workflows=[VanDurableWorkflow],
        activities=[record_temporal_checkpoint],
    )
    worker_task = asyncio.create_task(worker.run(), name="van-temporal-worker")
    try:
        yield
    finally:
        await worker.shutdown()
        await worker_task
        CLIENT = None


app = FastAPI(title="VAN Temporal Runtime", version="1.0", lifespan=lifespan)


@app.get("/health")
async def health(x_van_temporal_token: str | None = Header(default=None)):
    _authorize(x_van_temporal_token)
    if CLIENT is None:
        raise HTTPException(status_code=503, detail="temporal_client_not_ready")
    return {
        "ok": True,
        "state": "READY",
        "runtime": "temporalio",
        "namespace": TEMPORAL_NAMESPACE,
        "task_queue": TASK_QUEUE,
        "authority": "DURABLE_COORDINATION_ONLY",
        "executes_live_orders": False,
    }


@app.post("/v1/workflows/start")
async def start_workflow(
    body: StartBody,
    x_van_temporal_token: str | None = Header(default=None),
):
    _authorize(x_van_temporal_token)
    if CLIENT is None:
        raise HTTPException(status_code=503, detail="temporal_client_not_ready")

    existing = False
    try:
        await CLIENT.start_workflow(
            VanDurableWorkflow.run,
            body.model_dump(mode="json"),
            id=body.workflow_id,
            task_queue=TASK_QUEUE,
        )
    except Exception as exc:
        # SDK 1.33 raises WorkflowAlreadyStartedError. Avoid importing an unstable location
        # for the exception type; the existing workflow is queried and its idempotency key
        # is checked before a retry is accepted.
        if exc.__class__.__name__ != "WorkflowAlreadyStartedError":
            raise HTTPException(status_code=502, detail=f"temporal_start_failed:{exc}") from exc
        existing = True

    state = await _status(body.workflow_id)
    if state.get("idempotency_key") != body.idempotency_key:
        raise HTTPException(status_code=409, detail="workflow_id_idempotency_conflict")
    return {
        "accepted": True,
        "existing": existing,
        "workflow_id": body.workflow_id,
        "state": state,
    }


@app.get("/v1/workflows/{workflow_id}")
async def workflow_status(
    workflow_id: str,
    x_van_temporal_token: str | None = Header(default=None),
):
    _authorize(x_van_temporal_token)
    return await _status(workflow_id)


@app.post("/v1/workflows/{workflow_id}/signal")
async def workflow_signal(
    workflow_id: str,
    body: SignalBody,
    x_van_temporal_token: str | None = Header(default=None),
):
    _authorize(x_van_temporal_token)
    if CLIENT is None:
        raise HTTPException(status_code=503, detail="temporal_client_not_ready")
    handle = CLIENT.get_workflow_handle(workflow_id)
    try:
        await handle.signal("command", body.model_dump(mode="json"))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"temporal_signal_failed:{exc}") from exc
    return await _status(workflow_id)


if __name__ == "__main__":
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT, log_level="info")
