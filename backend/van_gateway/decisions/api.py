"""Owner-only detail and immutable answer, on the gateway's normal proved ingress."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from van_gateway.decisions.models import DecisionAnswer, DecisionRecord
from van_gateway.decisions.service import DecisionError, DecisionService


def build_decision_router(decisions: DecisionService) -> APIRouter:
    router = APIRouter(prefix="/v1/decisions", tags=["owner-decisions"])

    def owner_device(request: Request) -> str:
        # Set by the real ingress auth/proof middleware, never a caller header/body.
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=401, detail="paired_owner_required")
        return device_id

    @router.get("/{decision_id}", response_model=DecisionRecord)
    async def detail(decision_id: str, request: Request):
        owner_device(request)
        record = await decisions.get(decision_id)
        if record is None:
            raise HTTPException(status_code=404, detail="decision_not_found")
        return record

    @router.post("/{decision_id}/answer", response_model=DecisionRecord)
    async def answer(decision_id: str, body: DecisionAnswer, request: Request):
        device_id = owner_device(request)
        try:
            return await decisions.answer(decision_id, body, owner_device_id=device_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="decision_not_found") from exc
        except DecisionError as exc:
            code = 403 if exc.reason == "decision_owner_device_revoked" else 409
            raise HTTPException(status_code=code, detail=exc.reason) from exc

    return router
