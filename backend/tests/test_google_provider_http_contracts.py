"""Exercise real Workspace URL/payload contracts, not FakeGoogleTransport routes."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
from cryptography.fernet import Fernet

from conftest_automation import enroll_device, make_action_runtime, make_store
from van_gateway.action.models import ExecutionStatus
from van_gateway.google.service import GoogleAuthError, GoogleService
from van_gateway.google.transport import FakeGoogleTransport, GoogleHttpTransport, GoogleOAuthTokenClient
from van_gateway.models import PrincipalType


async def test_gmail_send_uses_gmails_draft_resource_endpoint():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "POST"
        assert request.url.path == "/gmail/v1/users/me/drafts/send"
        assert json.loads(request.content) == {"id": "draft-owner-1"}
        return httpx.Response(200, json={"id": "message-1", "labelIds": ["SENT"]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GoogleHttpTransport(client).gmail_send("short-lived", "draft-owner-1")
    assert result["id"] == "message-1"
    assert len(seen) == 1


def _event(**changes):
    return {
        "id": "event-1", "etag": '"revision-7"', "status": "confirmed",
        "start": {"dateTime": "2026-10-07T10:00:00+02:00"},
        "end": {"dateTime": "2026-10-07T11:30:00+02:00"},
        **changes,
    }


async def test_calendar_reschedule_preserves_duration_and_fences_concurrent_edits():
    seen = []
    new_start = int(datetime.fromisoformat("2026-10-08T14:00:00+02:00").timestamp())

    def handler(request):
        seen.append(request.method)
        assert request.url.path == "/calendar/v3/calendars/primary/events/event-1"
        if request.method == "GET":
            assert "etag" in request.url.params["fields"]
            return httpx.Response(200, json=_event())
        assert request.headers["If-Match"] == '"revision-7"'
        assert request.headers["Authorization"] == "Bearer short-lived"
        body = json.loads(request.content)
        assert body == {
            "start": {"dateTime": "2026-10-08T12:00:00Z"},
            "end": {"dateTime": "2026-10-08T13:30:00Z"},
        }
        return httpx.Response(200, json={"id": "event-1", **body})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GoogleHttpTransport(client).calendar_reschedule("short-lived", "event-1", new_start)
    assert result["end"]["dateTime"] == "2026-10-08T13:30:00Z"
    assert seen == ["GET", "PATCH"]


@pytest.mark.parametrize("event,reason", [
    (_event(status="cancelled"), "google_calendar_event_not_active"),
    (_event(id="other-event"), "google_calendar_event_not_active"),
    (_event(etag=""), "google_calendar_event_etag_missing"),
    (_event(start={"date": "2026-10-07"}, end={"date": "2026-10-08"}), "google_calendar_timed_interval_required"),
    (_event(start={"dateTime": "2026-10-07T10:00:00"}), "google_calendar_timed_interval_required"),
    (_event(end={"dateTime": "2026-10-07T08:00:00Z"}), "google_calendar_timed_interval_required"),
])
async def test_calendar_preconditions_refuse_before_mutating(event, reason):
    seen = []

    def handler(request):
        seen.append(request.method)
        return httpx.Response(200, json=event)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match=reason):
            await GoogleHttpTransport(client).calendar_reschedule("short-lived", "event-1", 100)
    assert seen == ["GET"]


async def test_calendar_concurrent_edit_does_not_retry_patch():
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(200, json=_event()) if request.method == "GET" else httpx.Response(412)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="google_http_412"):
            await GoogleHttpTransport(client).calendar_reschedule("short-lived", "event-1", 100)
    assert methods == ["GET", "PATCH"]


@pytest.mark.parametrize("failure,reason", [
    (httpx.ReadTimeout("transport detail"), "google_timeout"),
    (httpx.ConnectError("transport detail"), "google_unreachable"),
    (httpx.Response(200, text="not JSON"), "google_response_malformed"),
    (httpx.Response(200, json=[]), "google_response_malformed"),
    (httpx.Response(307, headers={"Location": "https://other.invalid"}), "google_http_307"),
])
async def test_workspace_failures_have_stable_codes(failure, reason):
    def handler(request):
        if isinstance(failure, Exception):
            raise failure
        return failure

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match=reason) as raised:
            await GoogleHttpTransport(client).tasks_list("short-lived")
    assert str(raised.value) == reason


@pytest.mark.parametrize("items", ["a string", {}, ["not an object"], None])
async def test_workspace_collection_response_requires_an_array_of_objects(items):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"items": items}))) as client:
        with pytest.raises(RuntimeError, match="google_response_malformed"):
            await GoogleHttpTransport(client).tasks_list("short-lived")


@pytest.mark.parametrize("method,args", [
    ("gmail_search", ("query",)), ("calendar_agenda", ()),
    ("drive_search", ("query",)), ("contacts_resolve", ("query",)), ("tasks_list", ()),
])
async def test_live_provider_read_failure_reaches_service_unavailable_boundary(tmp_path, method, args):
    store = await make_store(tmp_path)

    class ReadFailureTransport(FakeGoogleTransport):
        pass

    transport = ReadFailureTransport()

    async def failure(*provider_args):
        raise RuntimeError("google_timeout")

    setattr(transport, method, failure)
    google = GoogleService(store, Fernet.generate_key().decode(), transport)
    await google.store_refresh_token("owner", "refresh-test", [])
    with pytest.raises(GoogleAuthError, match="google_timeout"):
        await getattr(google, method)(*args)


@pytest.mark.parametrize("response,reason", [
    (httpx.Response(200, text="not JSON"), "google_oauth_response_malformed"),
    (httpx.Response(200, json=[]), "google_oauth_response_malformed"),
    (httpx.Response(200, json={"access_token": 42}), "google_oauth_access_token_missing"),
    (httpx.Response(302), "google_oauth_refresh_302"),
])
async def test_oauth_malformed_or_redirect_response_is_not_an_access_token(response, reason):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(RuntimeError, match=reason):
            await GoogleOAuthTokenClient("client-id", "client-secret", client).access_token("refresh")


@pytest.mark.parametrize("end_matches", [True, False])
async def test_authorized_calendar_readback_verifies_end_as_well_as_start(tmp_path, end_matches):
    store = await make_store(tmp_path)
    await enroll_device(store)
    actions = await make_action_runtime(store)
    parameters = {"event_id": "event-1", "new_start_unix": 1791453600}
    execution = await actions.begin(
        execution_id="exec-calendar-1", command_id="command-calendar-1", turn_id="turn-calendar-1",
        action_id="google.calendar.reschedule", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="dev-owner-1", idempotency_key="calendar-execution-1", parameters=parameters,
        snapshot_id=None, owner_approved=True,
    )
    assert execution.status is ExecutionStatus.AUTHORIZED

    class CalendarTransport(FakeGoogleTransport):
        async def calendar_event_get(self, token, event_id):
            observed = await super().calendar_event_get(token, event_id)
            if not end_matches:
                observed["end"] = {"dateTime": "2026-10-08T15:00:00Z"}
            return observed

    google = GoogleService(store, Fernet.generate_key().decode(), CalendarTransport())
    await google.store_refresh_token("owner", "refresh-test", ["https://www.googleapis.com/auth/calendar"])
    result = await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
    assert result["verification"]["status"] == ("VERIFIED_SUCCESS" if end_matches else "PARTIAL_SUCCESS")
    assert "end" in result["verification"]["observed_postcondition"]


async def test_calendar_transport_failure_closes_canonical_execution(tmp_path):
    store = await make_store(tmp_path)
    await enroll_device(store)
    actions = await make_action_runtime(store)
    parameters = {"event_id": "event-1", "new_start_unix": 100}
    execution = await actions.begin(
        execution_id="exec-calendar-failure", command_id="command-calendar-failure", turn_id="turn-calendar-failure",
        action_id="google.calendar.reschedule", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="dev-owner-1", idempotency_key="calendar-execution-failure", parameters=parameters,
        snapshot_id=None, owner_approved=True,
    )

    class BrokenTransport(FakeGoogleTransport):
        async def calendar_reschedule(self, *args):
            raise RuntimeError("google_timeout")

    google = GoogleService(store, Fernet.generate_key().decode(), BrokenTransport())
    await google.store_refresh_token("owner", "refresh-test", ["https://www.googleapis.com/auth/calendar"])
    with pytest.raises(GoogleAuthError, match="google_timeout"):
        await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
    failed = await actions.get_execution(execution.execution_id)
    assert failed.status is ExecutionStatus.EXECUTION_FAILED
    assert failed.error_code == "google_timeout"
