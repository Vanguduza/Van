"""VAN native and Site owner clients of one Muse interaction ledger.

The two special POST ingress paths are independently authenticated here; an ordinary
service credential cannot reach owner actions and an owner device cannot ingest source
observations. No HTTP listener, proxy route, browser profile or VPN configuration is created.
"""
from __future__ import annotations
import asyncio
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from .models import Action, MuseError, Outcome, Snapshot, canonical, digest
from .security import require_relay, signer, verify_site
from .service import MuseService
from .tasks import MuseTasks

PREFIX = "/v1/muse"
SPECIAL_POSTS = frozenset({PREFIX + "/relay", PREFIX + "/site"})
OWNER_MUTATIONS = frozenset({PREFIX + "/actions", PREFIX + "/challenge", PREFIX + "/tasks/query"})


async def bounded_json(request: Request, limit=2*1024*1024):
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > limit:
            raise MuseError("muse_body_too_large", 413)
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeDecodeError) as exc:
        raise MuseError("muse_body_invalid", 422) from exc


def failure(exc):
    if isinstance(exc, MuseError):
        return JSONResponse({"error": exc.code}, status_code=exc.status, headers={"Cache-Control":"no-store"})
    return JSONResponse({"error":"muse_request_invalid"}, status_code=422, headers={"Cache-Control":"no-store"})


def build_muse_router(service: MuseService, settings, *, auth=None):
    router = APIRouter(prefix=PREFIX, tags=["muse"])
    tasks = MuseTasks(settings, now=service.now)

    def enabled():
        if not settings.muse_enabled:
            raise MuseError("muse_interaction_disabled", 503)

    def actuation_admitted():
        if not getattr(settings, "muse_actuation_enabled", False):
            raise MuseError("muse_actuation_not_qualified", 503)

    def owner(request, *, mutate=False):
        enabled()
        device = getattr(request.state, "van_device_id", "")
        if not device:
            raise MuseError("owner_device_required", 401)
        if mutate and not getattr(request.state, "van_device_proved", False):
            raise MuseError("device_proof_required", 403)
        return device

    @router.get("/overview")
    async def overview(request: Request):
        try:
            owner(request)
            projection = await service.overview()
            projection["control_admitted"] = bool(getattr(settings,"muse_actuation_enabled",False))
            return JSONResponse(projection, headers={"Cache-Control":"no-store"})
        except MuseError as exc:
            return failure(exc)

    @router.post("/actions")
    async def action(request: Request):
        try:
            device = owner(request, mutate=True)
            actuation_admitted()
            body = Action.model_validate(await bounded_json(request, 32768))
            return JSONResponse(await service.enqueue(body, "device:"+device, device_id=device), status_code=202, headers={"Cache-Control":"no-store"})
        except (MuseError, ValidationError) as exc:
            return failure(exc)

    @router.post("/challenge")
    async def challenge(request: Request):
        try:
            device = owner(request, mutate=True)
            actuation_admitted()
            return await service.challenge(Action.model_validate(await bounded_json(request,32768)), device)
        except (MuseError, ValidationError) as exc:
            return failure(exc)

    @router.get("/tasks")
    async def task_overview(request: Request):
        try:
            device = owner(request)
            return await tasks.call("muse_get_overview", {}, principal="device:"+device)
        except MuseError as exc:
            return failure(exc)

    @router.post("/tasks/query")
    async def task_call(request: Request):
        try:
            device = owner(request, mutate=True)
            body = await bounded_json(request, 65536)
            if set(body) != {"operation", "arguments"}:
                raise MuseError("muse_task_shape_invalid", 422)
            return await tasks.call(body["operation"], body["arguments"], principal="device:"+device)
        except MuseError as exc:
            return failure(exc)

    @router.get("/commands/by-key/{key}")
    async def receipt_by_key(request: Request, key: str):
        try:
            device = owner(request)
            return await service.receipt_by_key(key, "device:"+device)
        except MuseError as exc:
            return failure(exc)

    @router.get("/commands/{command_id}")
    async def receipt(request: Request, command_id: str):
        try:
            device = owner(request)
            return await service.receipt(command_id, "device:"+device)
        except MuseError as exc:
            return failure(exc)

    @router.get("/events")
    async def events(request: Request, after: int = 0):
        try:
            owner(request)
            cursor = max(after, int(request.headers.get("Last-Event-ID", "0")))
            if cursor < 0:
                raise ValueError()
        except (MuseError, ValueError) as exc:
            return failure(exc)
        async def stream():
            nonlocal cursor
            end = time.monotonic()+60
            while time.monotonic() < end and not await request.is_disconnected():
                if auth is not None:
                    try:
                        await auth.require_access_token(request.headers.get("X-Van-Device-Token", ""))
                    except Exception:
                        return
                page = await service.replay(cursor)
                for event in page["events"]:
                    cursor = event["seq"]
                    yield f"id: {cursor}\nevent: muse\ndata: {canonical(event)}\n\n"
                if not page["truncated"]:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(2)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-store","X-Accel-Buffering":"no"})

    @router.post("/relay")
    async def relay(request: Request):
        try:
            enabled()
            require_relay(settings.muse_relay_token_file, request.headers.get("X-Muse-Relay-Token", ""))
            body = await bounded_json(request)
            if set(body) != {"operation", "arguments"}:
                raise MuseError("muse_relay_shape_invalid",422)
            operation, args = body["operation"], body["arguments"]
            if operation == "ingest":
                result = await service.ingest(Snapshot.model_validate(args))
            elif operation == "claim" and args == {}:
                actuation_admitted()
                sign = signer(settings.muse_command_signing_key_file)  # verify key before consuming claims
                result = {"commands":[sign(command) for command in await service.claim()]}
            elif operation == "complete":
                result = await service.complete(Outcome.model_validate(args))
            else:
                raise MuseError("muse_relay_operation_forbidden",403)
            return JSONResponse({"ok":True,"result":result}, headers={"Cache-Control":"no-store"})
        except (MuseError, ValidationError) as exc:
            return failure(exc)

    @router.post("/site")
    async def site(request: Request):
        try:
            enabled()
            envelope = verify_site(await bounded_json(request,65536), settings.muse_site_policy_file, service.now())
            operation, args = envelope["operation"], envelope["arguments"]
            principal = "site:"+envelope["subject"]
            if operation == "muse_interaction_read" and not args:
                result = await service.overview()
                result["control_admitted"] = bool(getattr(settings,"muse_actuation_enabled",False))
            elif operation == "muse_interaction_events" and set(args) == {"after"} and type(args["after"]) is int and args["after"] >= 0:
                result = await service.replay(args["after"])
            elif operation == "muse_interaction_action":
                actuation_admitted()
                body = Action.model_validate(args)
                # Site cannot echo a native biometric proof as if it owned that device.
                result = await service.enqueue(body, principal)
            elif operation == "muse_interaction_receipt" and set(args) == {"command_id"}:
                result = await service.receipt(args["command_id"], principal)
            else:
                raise MuseError("muse_site_operation_forbidden",403)
            return JSONResponse({"ok":True,"result":result}, headers={"Cache-Control":"no-store"})
        except (MuseError, ValidationError) as exc:
            return failure(exc)
    return router
