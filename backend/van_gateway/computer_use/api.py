from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .fabric import ComputerInteractionFabric, ComputerUseError, OperationRequest


def build_computer_use_router(fabric: ComputerInteractionFabric) -> APIRouter:
    router = APIRouter(prefix="/v1/computer-use", tags=["computer-use"])

    @router.post("/operations")
    async def execute_operation(body: OperationRequest):
        try:
            return await fabric.execute_operation(body)
        except ComputerUseError as exc:
            unavailable = exc.code in {
                "OPERATION_NO_WORKER_FOR_SURFACE",
                "OPERATION_WORKER_UNBOUND",
                "COMPUTER_UNCONFIGURED",
                "COMPUTER_DOCKER_UNAVAILABLE",
                "COMPUTER_DOCKER_TIMEOUT",
                "COMPUTER_DOCKER_CONTROL_FAILED",
            }
            status = 503 if unavailable else 409
            raise HTTPException(status_code=status, detail=exc.code) from exc

    @router.get("/operations/mission/{mission_id}")
    async def operations_for_mission(mission_id: str):
        return await fabric.for_mission(mission_id)

    return router
