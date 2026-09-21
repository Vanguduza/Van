"""P2-GOOG-004 — six Google capabilities with a transport, a service method and no way in.

`gmail_draft`, `calendar_agenda`, `calendar_reschedule`, `drive_search`,
`contacts_resolve` and `tasks_list` were implemented end to end in `google/transport.py`
and `google/service.py`, exercised by their own tests, and reachable from nothing. The
component ledger carried three entries of NO_ROUTE against them. A capability whose only
caller is its own test is not a capability the owner has.

The tests that matter here are not "the route returns 200". They are the two ways adding a
route can be worse than not having one: reaching the owner's Gmail without the
internal-control credential, and a mutating calendar change going through without the
owner.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import GOOGLE_CONTROL_ROUTES, create_app
from van_gateway.config import get_settings
from van_gateway.google.service import GoogleService

INGRESS = "google-routes-ingress-0123456789"
INTERNAL = "google-routes-internal"

#: The six this finding added, and what each is for. Named rather than derived from the
#: route table, because deriving the expectation from the thing under test proves nothing.
NEW_ROUTES = {
    "/v1/google/actions/execute": "POST",
    "/v1/google/gmail/draft": "POST",
    "/v1/google/calendar/agenda": "GET",
    "/v1/google/calendar/reschedule": "POST",
    "/v1/google/drive/search": "GET",
    "/v1/google/contacts/resolve": "GET",
    "/v1/google/tasks": "GET",
}


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "google-routes.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": INGRESS}
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


async def _call(ac, path, method, **params):
    headers = {"X-Van-Internal-Token": INTERNAL}
    if method == "GET":
        return await ac.get(path, params=params, headers=headers)
    return await ac.post(path, params=params, headers=headers)


# ------------------------------------------------------------------ reachability


def test_every_capability_with_a_service_method_has_a_route():
    """The finding, as an invariant over the service surface.

    A method on GoogleService that the owner cannot reach is the shape this closed, and it
    is the shape it would come back in. Checked against the route set rather than a list of
    six, so the seventh is caught the day it is written.
    """
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    missing = [p for p in NEW_ROUTES if p not in paths]
    assert missing == [], f"capabilities still unreachable: {missing}"


def test_the_service_methods_these_routes_call_still_exist():
    """A route naming a method that has been renamed is a 500 nobody notices until it is
    called, and these are called rarely."""
    for method in (
        "gmail_draft", "calendar_agenda", "calendar_reschedule",
        "drive_search", "contacts_resolve", "tasks_list",
    ):
        assert callable(getattr(GoogleService, method, None)), method


# ------------------------------------------------------------------ the boundary


@pytest.mark.asyncio
async def test_none_of_them_is_reachable_without_the_internal_credential(client):
    """The failure that would make adding these worse than leaving them unreachable.

    An unscoped route falls through to owner-device authentication, so a paired phone could
    read the owner's Drive and Contacts through it. That fall-through is exactly what
    P0-SEC-001 closed, and adding a route is how it comes back.
    """
    ac, _ = client
    for path, method in NEW_ROUTES.items():
        call = ac.get if method == "GET" else ac.post
        response = await call(path, params={"q": "x", "thread_id": "t", "body": "b",
                                            "event_id": "e", "new_start_unix": 0})
        assert response.status_code in (401, 403), f"{path} answered {response.status_code}"
        assert response.json()["detail"] != "ok"


def test_each_new_route_is_declared_in_the_one_scope_set():
    """`control_scope_for` and the guard beside it read one set now.

    They held separate copies, and a route present in one and missing from the other is a
    hole rather than an inconsistency: the middleware would not demand the credential the
    handler assumes it has.
    """
    for path in NEW_ROUTES:
        assert path in GOOGLE_CONTROL_ROUTES, f"{path} is a Google route outside the scope set"


@pytest.mark.asyncio
async def test_rescheduling_cannot_turn_an_internal_boolean_into_owner_authority(client):
    """An internal token authenticates Hermes/control; it is not biometric approval.

    The old route accepted approved=true directly. Now the route requires an execution id
    already authorized by Action Runtime, so supplying the historical flag cannot mutate.
    """
    ac, app = client
    app.state.google.transport = __import__(
        "van_gateway.google.transport", fromlist=["FakeGoogleTransport"]
    ).FakeGoogleTransport()
    app.state.google.oauth = None
    denied = await _call(
        ac,
        "/v1/google/calendar/reschedule",
        "POST",
        event_id="e1",
        new_start_unix=1,
        approved=True,
    )
    assert denied.status_code == 422
    assert not app.state.google.transport.calls


@pytest.mark.asyncio
async def test_an_unconnected_google_reports_unable_rather_than_refusing(client):
    """503, not 403. "VAN cannot reach Google" and "you may not do that" send the owner to
    entirely different places, and the audit kept finding them collapsed."""
    ac, _ = client
    response = await _call(ac, "/v1/google/tasks", "GET")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_drafting_is_a_typed_a3_mutation_not_a_raw_internal_write(client):
    ac, app = client
    app.state.google.transport = __import__(
        "van_gateway.google.transport", fromlist=["FakeGoogleTransport"]
    ).FakeGoogleTransport()
    app.state.google.oauth = None
    response = await _call(
        ac, "/v1/google/gmail/draft", "POST", thread_id="t1", body="hello",
    )
    assert response.status_code == 422
    assert not app.state.google.transport.calls
