from fastapi import APIRouter, HTTPException, Header
from typing import Literal
from van_gateway.cognitive.service import CognitiveCandidate, CognitiveService
from van_gateway.context.service import ContextAdmissionError


def build_cognitive_router(*, store, context, trading, require_internal=None, twin_client=None):
    router = APIRouter()
    service = CognitiveService(store, context)

    @router.get('/v1/cognitive/twin')
    async def twin(project_id: str = 'van'):
        if twin_client is None:
            return {'state': 'DEGRADED', 'reason': 'TWIN_CONSUMER_UNCONFIGURED', 'projection': None}
        return await twin_client.read(project_id)

    @router.get('/v1/cognitive/providers')
    async def providers():
        return service.providers()

    @router.get('/v1/cognitive/candidates')
    async def candidates():
        return {'authority': 'ADVISORY_CANDIDATE', 'candidates': [{k: c[k] for k in ('candidate_id', 'candidate_type', 'provider_product', 'state', 'content_hash', 'expires_at_ms')} for c in await service.candidates()]}

    @router.post('/v1/cognitive/candidates')
    async def ingest(body: CognitiveCandidate):
        try:
            return await service.ingest(body)
        except ContextAdmissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get('/v1/cognitive/guardian')
    async def guardian():
        return await service.guardian_projection(trading)

    @router.get('/v1/runtime/cognitive/projection')
    async def machine_projection(x_van_internal_token: str | None = Header(default=None)):
        require_internal(x_van_internal_token)
        return {'schema_version': 1, 'authority': 'DERIVED_READ_ONLY',
                'project_id': 'van', 'data_class': 'INTERNAL_SANITIZED',
                'provider_approval_required': True, 'source_revision': await context.kernel_revision(),
                'context_revision': await context.kernel_revision(),
                'providers': service.providers(),
                'guardian': await service.guardian_projection(trading),
                'candidates': [{k: c[k] for k in ('candidate_id', 'candidate_type', 'provider_product', 'state', 'content_hash', 'expires_at_ms')} for c in await service.candidates()]}

    @router.post('/v1/runtime/cognitive/candidates')
    async def machine_candidate(body: CognitiveCandidate, x_van_internal_token: str | None = Header(default=None)):
        require_internal(x_van_internal_token)
        try:
            return await service.ingest(body, trusted_ingress='DOT_COGNITIVE_MACHINE')
        except ContextAdmissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get('/v1/runtime/cognitive/{slice_name}')
    async def machine_slice(slice_name: Literal['missions', 'attention', 'owner-context', 'capability-utilization',
            'trading-market', 'strategy-health', 'performance', 'tca', 'learning-episodes'],
            x_van_internal_token: str | None = Header(default=None)):
        require_internal(x_van_internal_token)
        return await service.slice(slice_name, trading)

    return router
