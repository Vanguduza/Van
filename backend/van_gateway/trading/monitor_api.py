"""Paired owner monitor contracts; all mutations use the gateway's bound-device proof gate."""
from fastapi import APIRouter, HTTPException, Query
from .chart_api import PrivateChartRoute
from .monitor_models import (CreateWatchlist, ReplaceWatchlist, CreateAlert, ReplaceAlert,
    MonitorControl, MonitorWrite, WatchlistView, AlertView, WatchlistPage, AlertPage,
    MonitorCapabilities, MonitorErrorResponse, ScreenRequest, ScreenResult,
    CreateScreenRule, ReplaceScreenRule, RunScreenRule, ScreenRuleView, ScreenRulePage,
    WatchlistMarketRequest, WatchlistMarketResult)
from .monitor_service import MarketMonitorService, MonitorError


def build_monitor_router(service: MarketMonitorService) -> APIRouter:
    router = APIRouter(prefix='/v1/trading/monitors', tags=['market-monitors'],
        route_class=PrivateChartRoute,
        responses={s: {'model': MonitorErrorResponse} for s in (404, 409, 413, 429, 503)})

    async def call(operation):
        try:
            return await operation
        except MonitorError as exc:
            raise HTTPException(exc.status, detail={'code': exc.code, **exc.details}) from exc

    @router.get('/capabilities', response_model=MonitorCapabilities)
    async def capabilities():
        return service.capabilities()

    @router.get('/operations/{request_id}', response_model=MonitorWrite)
    async def operation(request_id: str):
        return await call(service.operation('owner', request_id))

    @router.get('/watchlists', response_model=WatchlistPage)
    async def lists(limit: int = Query(100, ge=1, le=128), after_id: str | None = None):
        return await call(service.listing('owner', 'WATCHLIST', limit=limit, after_id=after_id))

    @router.post('/watchlists', response_model=MonitorWrite)
    async def create_list(body: CreateWatchlist):
        return await call(service.write('owner', 'WATCHLIST', 'CREATE', body))

    @router.get('/watchlists/{object_id}', response_model=WatchlistView)
    async def get_list(object_id: str):
        return await call(service.get('owner', 'WATCHLIST', object_id))

    @router.put('/watchlists/{object_id}', response_model=MonitorWrite)
    async def replace_list(object_id: str, body: ReplaceWatchlist):
        return await call(service.write('owner', 'WATCHLIST', 'REPLACE', body, object_id))

    @router.delete('/watchlists/{object_id}', response_model=MonitorWrite)
    async def delete_list(object_id: str, body: MonitorControl):
        return await call(service.write('owner', 'WATCHLIST', 'DELETE', body, object_id))

    @router.get('/alerts', response_model=AlertPage)
    async def alerts(limit: int = Query(100, ge=1, le=128), after_id: str | None = None):
        return await call(service.listing('owner', 'ALERT', limit=limit, after_id=after_id))

    @router.post('/alerts', response_model=MonitorWrite)
    async def create_alert(body: CreateAlert):
        return await call(service.write('owner', 'ALERT', 'CREATE', body))

    @router.get('/alerts/{object_id}', response_model=AlertView)
    async def get_alert(object_id: str):
        return await call(service.get('owner', 'ALERT', object_id))

    @router.put('/alerts/{object_id}', response_model=MonitorWrite)
    async def replace_alert(object_id: str, body: ReplaceAlert):
        return await call(service.write('owner', 'ALERT', 'REPLACE', body, object_id))

    @router.delete('/alerts/{object_id}', response_model=MonitorWrite)
    async def delete_alert(object_id: str, body: MonitorControl):
        return await call(service.write('owner', 'ALERT', 'DELETE', body, object_id))

    @router.post('/alerts/{object_id}/pause', response_model=MonitorWrite)
    async def pause_alert(object_id: str, body: MonitorControl):
        return await call(service.write('owner', 'ALERT', 'PAUSE', body, object_id))

    @router.post('/alerts/{object_id}/restart', response_model=MonitorWrite)
    async def restart_alert(object_id: str, body: MonitorControl):
        return await call(service.write('owner', 'ALERT', 'RESTART', body, object_id))

    @router.get('/screen-rules', response_model=ScreenRulePage)
    async def screen_rules(limit: int = Query(100, ge=1, le=128), after_id: str | None = None):
        return await call(service.listing('owner', 'SCREEN_RULE', limit=limit, after_id=after_id))

    @router.post('/screen-rules', response_model=MonitorWrite)
    async def create_screen_rule(body: CreateScreenRule):
        return await call(service.write('owner', 'SCREEN_RULE', 'CREATE', body))

    @router.get('/screen-rules/{object_id}', response_model=ScreenRuleView)
    async def get_screen_rule(object_id: str):
        return await call(service.get('owner', 'SCREEN_RULE', object_id))

    @router.put('/screen-rules/{object_id}', response_model=MonitorWrite)
    async def replace_screen_rule(object_id: str, body: ReplaceScreenRule):
        return await call(service.write('owner', 'SCREEN_RULE', 'REPLACE', body, object_id))

    @router.delete('/screen-rules/{object_id}', response_model=MonitorWrite)
    async def delete_screen_rule(object_id: str, body: MonitorControl):
        return await call(service.write('owner', 'SCREEN_RULE', 'DELETE', body, object_id))

    @router.post('/screen-rules/{object_id}/run', response_model=ScreenResult)
    async def run_screen_rule(object_id: str, body: RunScreenRule):
        return await call(service.run_screen_rule('owner', object_id, body))

    @router.post('/watchlists/{object_id}/market', response_model=WatchlistMarketResult)
    async def watchlist_market(object_id: str, body: WatchlistMarketRequest):
        return await call(service.watchlist_market('owner', object_id, body))

    @router.post('/screen', response_model=ScreenResult)
    async def screen(body: ScreenRequest):
        return await call(service.screen('owner', body))

    return router
