"""Calendar effect results require separate target content readback."""
import copy
import json

import httpx
import pytest
from cryptography.fernet import Fernet

from conftest_automation import enroll_device, make_action_runtime, make_store
from van_gateway.google.service import GoogleService
from van_gateway.google.transport import GoogleHttpTransport
from van_gateway.models import PrincipalType


class BoundHttpTransport(GoogleHttpTransport):
    requires_access_token = False


_EVENT = {"summary": "Owner approved call", "location": "Room 4",
    "start": {"dateTime": "2026-10-09T10:00:00+02:00"},
    "end": {"dateTime": "2026-10-09T11:00:00+02:00"},
    "attendees": [{"email": "first@example.invalid"}, {"email": "second@example.invalid"}]}


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("fault", [None, "summary", "start", "location", "attendee", "cancelled", "missing_etag"])
async def test_calendar_write_verifies_approved_content_from_separate_read(tmp_path, operation, fault):
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path))
        observed = {"id": "event-1", "etag": "version-2", **copy.deepcopy(_EVENT)}
        if request.method != "GET":
            assert json.loads(request.content) == _EVENT
            if operation == "update":
                assert request.headers["if-match"] == "version-1"
            return httpx.Response(200, json=observed)
        observed["start"]["dateTime"] = "2026-10-09T08:00:00Z"
        observed["attendees"].reverse()
        if fault == "start":
            observed["start"]["dateTime"] = "2026-10-09T09:00:00Z"
        elif fault == "attendee":
            observed["attendees"][0]["email"] = "other@example.invalid"
        elif fault == "cancelled":
            observed["status"] = "cancelled"
        elif fault == "missing_etag":
            del observed["etag"]
        elif fault:
            observed[fault] = "Unapproved value"
        return httpx.Response(200, json=observed)
    store = await make_store(tmp_path)
    await enroll_device(store)
    actions = await make_action_runtime(store)
    parameters = {"event": copy.deepcopy(_EVENT)}
    if operation == "update":
        parameters.update(event_id="event-1", expected_version="version-1")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        google = GoogleService(store, Fernet.generate_key().decode(), BoundHttpTransport(client))
        await google.store_refresh_token("owner", "synthetic-token", ["https://www.googleapis.com/auth/calendar"])
        execution = await actions.begin(execution_id="exec-calendar", command_id="cmd-calendar", turn_id="turn-calendar",
            action_id="google.calendar." + operation, principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", idempotency_key="calendar-effect", parameters=parameters,
            snapshot_id=None, owner_approved=True)
        result = await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
    valid = fault is None or (fault == "missing_etag" and operation == "create")
    assert result["verification"]["status"] == ("VERIFIED_SUCCESS" if valid else "PARTIAL_SUCCESS")
    assert [method for method, _ in calls] == [("POST" if operation == "create" else "PATCH"), "GET"]


@pytest.mark.parametrize("readback", ["cancelled", "wrong_id", "404", "503"])
async def test_calendar_delete_requires_matching_absence_readback(tmp_path, readback):
    methods = []
    def handler(request):
        methods.append(request.method)
        if request.method == "DELETE":
            return httpx.Response(204)
        if readback in {"404", "503"}:
            return httpx.Response(int(readback))
        return httpx.Response(200, json={"id": "event-1" if readback == "cancelled" else "other-event", "status": "cancelled"})
    store = await make_store(tmp_path)
    await enroll_device(store)
    actions = await make_action_runtime(store)
    parameters = {"event_id": "event-1", "expected_version": "version-1"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        google = GoogleService(store, Fernet.generate_key().decode(), BoundHttpTransport(client))
        await google.store_refresh_token("owner", "synthetic-token", ["https://www.googleapis.com/auth/calendar"])
        execution = await actions.begin(execution_id="exec-calendar", command_id="cmd-calendar", turn_id="turn-calendar",
            action_id="google.calendar.delete", principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", idempotency_key="calendar-effect", parameters=parameters,
            snapshot_id=None, owner_approved=True)
        result = await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
    assert result["verification"]["status"] == ("VERIFIED_SUCCESS" if readback in {"cancelled", "404"} else "PARTIAL_SUCCESS")
    assert methods == ["DELETE", "GET"]
