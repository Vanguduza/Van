"""Rev 1.5 §§20.5, 20.10, 34.1 — the session's carriers, driven through the ingress.

Until this file existed the durable session had service-level tests and no route-level
ones, and the difference turned out to matter. `POST /v1/session/resume` grants a new path
epoch on *every* accepted resume — including the first one, which the phone issues the
moment its socket opens. A client that kept the epoch `/open` gave it had every envelope
fenced by `accept_upstream` from the first second, on a session both sides reported as
connected. Nothing in the service tests could see it, because the service was right.

So the first class here pins the contract the two sides actually have to agree on: the
epoch a resume grants is the epoch the next envelope must carry. The second is about the
failover counter, which is the only thing the Gateway can honestly say about a path switch
— that one happened, and whether it went to a different road.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.observability import metrics as metrics_module

INGRESS = "session-ingress-token-0123456789"
INTERNAL = "session-internal-token-0123456789"
SESSION = "/v1/session"


@pytest.fixture
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "session.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(_settings):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


async def _device(app, label="owner-phone"):
    ticket = await app.state.auth.create_pairing_ticket(label)
    return await app.state.auth.pair_device(ticket.token, label, "s" * 32, "PEM", label)


def _headers(enrolled):
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": enrolled.access_token}


async def _open(ac, enrolled, path_id="primary-wss", route_id="primary-ingress"):
    opened = await ac.post(
        f"{SESSION}/open",
        json={"path_id": path_id, "route_id": route_id, "protocol": "WSS",
              "path_class": "A_REALTIME"},
        headers=_headers(enrolled),
    )
    assert opened.status_code == 200, opened.text
    return opened.json()


async def _resume(ac, enrolled, opened, *, path_id="primary-wss",
                  route_id="primary-ingress", session_epoch=None):
    return await ac.post(
        f"{SESSION}/resume",
        json={
            "van_session_id": opened["van_session_id"],
            "session_epoch": (
                opened["session_epoch"] if session_epoch is None else session_epoch
            ),
            "last_event_seq": 0,
            "pending_command_ids": [],
            "path_id": path_id,
            "route_id": route_id,
            "path_class": "A_REALTIME",
        },
        headers=_headers(enrolled),
    )


async def _mission(ac, title="a mission the owner can talk to"):
    """A real mission, made through the internal control route the Gateway already has."""
    created = await ac.post(
        "/v1/missions",
        json={
            "owner_principal_id": "device:owner-phone", "origin": "OWNER_UI",
            "origin_channel": "UI", "title": title, "goal": title,
        },
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["mission_id"]


async def _resume_asking(ac, enrolled, opened, pending_command_ids):
    """A resume that actually asks something, which the shared helper never does."""
    return await ac.post(
        f"{SESSION}/resume",
        json={
            "van_session_id": opened["van_session_id"],
            "session_epoch": opened["session_epoch"],
            "last_event_seq": 0,
            "pending_command_ids": list(pending_command_ids),
            "path_id": "primary-wss",
            "route_id": "primary-ingress",
            "path_class": "A_REALTIME",
        },
        headers=_headers(enrolled),
    )


def _envelope(opened, path_epoch, message_id="msg_1", **over):
    body = {
        "message_id": message_id,
        "van_session_id": opened["van_session_id"],
        "session_epoch": opened["session_epoch"],
        "path_epoch": path_epoch,
        "kind": "session.heartbeat",
        "payload": {},
    }
    body.update(over)
    return body


@pytest.mark.asyncio
class TestTheEpochAResumeGrantsIsTheEpochTheNextEnvelopeMustCarry:

    async def test_the_first_resume_moves_the_epoch_off_the_one_open_gave(self, client):
        """The fact the client has to know, stated once.

        Not a bug in itself — §20.10 says the epoch is granted — but it is the fact that
        makes keeping `/open`'s epoch fatal, and nothing in the repository said it.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        resumed = await _resume(ac, enrolled, opened)
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["new_path_epoch"] > opened["path_epoch"]

    async def test_an_envelope_carrying_the_open_epoch_after_a_resume_is_fenced(self, client):
        """The failure a client sees if it does not adopt the grant.

        Every owner message refused, with the socket open and the status screen green.
        This is here so that a change which stops granting a new epoch on an ordinary
        resume has to be a deliberate one.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        await _resume(ac, enrolled, opened)
        fenced = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(opened, opened["path_epoch"]),
            headers=_headers(enrolled),
        )
        assert fenced.status_code == 400
        assert fenced.json()["detail"] == "session_path_epoch_stale"

    async def test_an_envelope_carrying_the_granted_epoch_is_admitted(self, client):
        """The other half. A route that fenced everything would pass the test above."""
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        granted = (await _resume(ac, enrolled, opened)).json()["new_path_epoch"]
        accepted = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(opened, granted),
            headers=_headers(enrolled),
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["accepted"] is True

    async def test_two_resumes_without_an_envelope_in_between_still_agree(self, client):
        """The shape of the bug that made the local increment wrong.

        A client that incremented its own epoch per socket failure and a Gateway that
        increments per accepted resume agree after one of each and diverge after two. Only
        the granted number is the number.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        await _resume(ac, enrolled, opened)
        granted = (await _resume(ac, enrolled, opened)).json()["new_path_epoch"]
        accepted = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(opened, granted),
            headers=_headers(enrolled),
        )
        assert accepted.status_code == 200, accepted.text


@pytest.mark.asyncio
class TestTheFailoverCounterSaysWhatTheGatewayCanSee:

    def _samples(self, outcome: str, route_changed: str) -> float:
        rendered = metrics_module.render_prometheus(metrics_module.REGISTRY)
        needle = (
            f'van_session_failover_total{{outcome="{outcome}",'
            f'route_changed="{route_changed}"}}'
        )
        for line in rendered.splitlines():
            if line.startswith(needle):
                return float(line.rsplit(" ", 1)[1])
        return 0.0

    async def test_a_resume_on_the_same_path_is_a_reconnect_not_a_failover(self, client):
        """Counting a tunnel as a route failure would make the metric unreadable.

        The owner's train goes underground several times an hour; a carrier's ingress
        fails rarely. One counter that could not tell them apart would report the common
        event at the rare one's severity.
        """
        ac, app = client
        enrolled = await _device(app)
        before = self._samples("reconnected", "false")
        opened = await _open(ac, enrolled)
        await _resume(ac, enrolled, opened)
        assert self._samples("reconnected", "false") == before + 1

    async def test_a_resume_on_another_path_over_another_route_is_a_failover(self, client):
        ac, app = client
        enrolled = await _device(app)
        before = self._samples("failed_over", "true")
        opened = await _open(ac, enrolled)
        moved = await _resume(
            ac, enrolled, opened, path_id="fallback-http2", route_id="second-ingress",
        )
        assert moved.status_code == 200, moved.text
        assert self._samples("failed_over", "true") == before + 1

    async def test_a_second_carrier_on_the_same_road_is_not_a_route_change(self, client):
        """§20.6 / §0B — protocol diversity is not route diversity.

        A failover onto another protocol over the same ingress is a failover, and it is
        the one that most often changes nothing. Labelling it `route_changed="true"` would
        report recovery for a session that is still on the road that broke.
        """
        ac, app = client
        enrolled = await _device(app)
        before = self._samples("failed_over", "false")
        opened = await _open(ac, enrolled)
        await _resume(ac, enrolled, opened, path_id="fallback-http2")
        assert self._samples("failed_over", "false") == before + 1

    async def test_a_refused_resume_is_counted_as_its_refusal(self, client):
        """The failover that did not happen.

        A counter that saw only the accepted resumes would report a perfect record for a
        session that never came back, which is the reading an operator most needs to be
        able to trust.
        """
        from van_gateway.session.service import REJECT_STALE_SESSION_EPOCH

        ac, app = client
        enrolled = await _device(app)
        before = self._samples(REJECT_STALE_SESSION_EPOCH, "false")
        opened = await _open(ac, enrolled)
        refused = await _resume(ac, enrolled, opened, session_epoch=9_999)
        assert refused.status_code == 409
        # Named, not read back from the response: reading the label off the thing under
        # test would make this pass whatever the route recorded, including nothing.
        assert refused.json()["detail"] == REJECT_STALE_SESSION_EPOCH
        assert self._samples(REJECT_STALE_SESSION_EPOCH, "false") == before + 1


@pytest.mark.asyncio
class TestWhatAResumeSaysAboutWhatTheClientLost:
    """§20.12 — the answer a reconnecting phone reconciles against.

    This existed and answered nothing. `_resume_snapshot` resolved each id against the
    *mission* table only, and the phone sent the ids it actually had — message ids — so
    every lookup missed and every answer was `UNKNOWN`. The phone then dropped everything
    it had asked about, unknowns included, which meant a resume silently discarded every
    unacknowledged owner command. Both halves were wrong and they cancelled out, so no
    test could see either.

    These are written from the phone's question: *I am holding this; do you have it?*
    """

    async def test_a_message_the_gateway_admitted_is_not_reported_unknown(self, client):
        """The one that was false. The Gateway holds the envelope and said it did not."""
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        mission_id = await _mission(ac)
        granted = (await _resume(ac, enrolled, opened)).json()["new_path_epoch"]
        # Not a heartbeat: §20.12's admission table deliberately does not record
        # liveness, and a test written on a heartbeat would be asking the Gateway about
        # something it is right to have no memory of.
        accepted = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(
                opened, granted, message_id="msg_held", kind="mission.message",
                idempotency_key="idem_held", command_id="cmd_held",
                payload={"mission_id": mission_id, "text": "any progress?"},
            ),
            headers=_headers(enrolled),
        )
        assert accepted.status_code == 200, accepted.text

        answered = await ac.post(
            f"{SESSION}/resume",
            json={
                "van_session_id": opened["van_session_id"],
                "session_epoch": opened["session_epoch"],
                "last_event_seq": 0,
                "pending_command_ids": ["msg_held"],
                "path_id": "primary-wss",
                "route_id": "primary-ingress",
                "path_class": "A_REALTIME",
            },
            headers=_headers(enrolled),
        )
        assert answered.status_code == 200, answered.text
        states = answered.json()["command_states"]
        assert states["msg_held"] != "UNKNOWN", (
            "the Gateway holds this message and told the phone to send it again"
        )

    async def test_a_message_the_gateway_has_never_seen_is_reported_unknown(self, client):
        """The other half, and the one that must stay true.

        A snapshot that answered something for everything would pass the test above and
        lose the owner's command instead — the phone would settle work that never arrived.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        answered = await _resume_asking(ac, enrolled, opened, ["msg_never_sent"])
        assert answered.json()["command_states"]["msg_never_sent"] == "UNKNOWN"

    async def test_the_answer_is_scoped_to_the_session_that_asked(self, client):
        """A message held under another session is not this session's to settle.

        Two sessions on one device is the ordinary case after a replacement, and an
        answer that ignored the session id would tell the new one it already holds work
        that belongs to the session the owner's commands were abandoned with.
        """
        ac, app = client
        enrolled = await _device(app)
        first = await _open(ac, enrolled)
        mission_id = await _mission(ac)
        granted = (await _resume(ac, enrolled, first)).json()["new_path_epoch"]
        await ac.post(
            f"{SESSION}/messages",
            json=_envelope(
                first, granted, message_id="msg_elsewhere", kind="mission.message",
                idempotency_key="idem_elsewhere",
                payload={"mission_id": mission_id, "text": "any progress?"},
            ),
            headers=_headers(enrolled),
        )

        second = await _open(ac, enrolled)
        answered = await _resume_asking(ac, enrolled, second, ["msg_elsewhere"])
        assert answered.json()["command_states"]["msg_elsewhere"] == "UNKNOWN"

    async def test_every_id_asked_about_is_answered(self, client):
        """Silence and `UNKNOWN` mean the same thing to the phone, so say it.

        An omitted key is indistinguishable from a truncated answer, and a client that
        had to infer the difference would be guessing about whether the owner's command
        was received.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        asked = ["msg_a", "msg_b", "msg_c"]
        answered = await _resume_asking(ac, enrolled, opened, asked)
        assert sorted(answered.json()["command_states"]) == sorted(asked)


@pytest.mark.asyncio
class TestTheSessionCarriesEveryKindItClaimsTo:
    """§20.2 — a kind the router admits is a kind something can actually carry out.

    Three of the four delegates were never wired, and the failure was worse than a missing
    feature. The router recorded the envelope in §20.12's admission table *before*
    discovering it had nobody to hand it to, so "cancel it" sent over the durable session
    was written down, refused — and every retry of the same idempotency key came back
    ALREADY_KNOWN with a null result, which reads as success. Acknowledged, never
    performed, and impossible to send again.
    """

    async def test_the_owner_can_cancel_a_mission_over_the_session(self, client):
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        mission_id = await _mission(ac, "a mission the owner changes their mind about")
        granted = (await _resume(ac, enrolled, opened)).json()["new_path_epoch"]

        cancelled = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(
                opened, granted, message_id="msg_cancel", kind="mission.cancel",
                idempotency_key="idem_cancel", payload={"mission_id": mission_id},
            ),
            headers=_headers(enrolled),
        )
        assert cancelled.status_code == 200, cancelled.text
        state = await ac.get(f"/v1/missions/{mission_id}", headers=_headers(enrolled))
        assert state.json()["state"] == "CANCELLED", (
            "the session acknowledged a cancellation it never performed"
        )

    async def test_a_refused_message_does_not_take_its_idempotency_key_with_it(self, client):
        """The corrected resend has to work.

        A refusal that left the row behind made the key permanently taken, so the owner
        fixing the mission id and sending again was told ALREADY_KNOWN — with no result,
        which the client reads as done.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        granted = (await _resume(ac, enrolled, opened)).json()["new_path_epoch"]

        refused = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(
                opened, granted, message_id="msg_wrong", kind="mission.cancel",
                idempotency_key="idem_retry", payload={"mission_id": "m_does_not_exist"},
            ),
            headers=_headers(enrolled),
        )
        assert refused.status_code == 400, refused.text

        mission_id = await _mission(ac, "the one they actually meant")
        corrected = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(
                opened, granted, message_id="msg_right", kind="mission.cancel",
                idempotency_key="idem_retry", payload={"mission_id": mission_id},
            ),
            headers=_headers(enrolled),
        )
        assert corrected.status_code == 200, corrected.text
        state = await ac.get(f"/v1/missions/{mission_id}", headers=_headers(enrolled))
        assert state.json()["state"] == "CANCELLED"

    async def test_a_refused_message_is_not_left_in_the_admission_table(self, client):
        """And therefore is not reported to a resume as something the Gateway holds.

        The two halves of this checkpoint meeting: a row with no result would make the
        resume answer "I have this" about a command that was never carried out, and the
        phone would settle it and never send it again.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        granted = (await _resume(ac, enrolled, opened)).json()["new_path_epoch"]
        await ac.post(
            f"{SESSION}/messages",
            json=_envelope(
                opened, granted, message_id="msg_dropped", kind="mission.cancel",
                idempotency_key="idem_dropped", payload={"mission_id": "m_nope"},
            ),
            headers=_headers(enrolled),
        )
        answered = await _resume_asking(ac, enrolled, opened, ["msg_dropped"])
        assert answered.json()["command_states"]["msg_dropped"] == "UNKNOWN"

    async def test_a_malformed_command_is_refused_rather_than_raised(self, client):
        """A 500 is "try again"; this payload will never succeed.

        Reported as a server failure, the phone's retry policy resends the same malformed
        command indefinitely.
        """
        ac, app = client
        enrolled = await _device(app)
        opened = await _open(ac, enrolled)
        granted = (await _resume(ac, enrolled, opened)).json()["new_path_epoch"]
        answered = await ac.post(
            f"{SESSION}/messages",
            json=_envelope(
                opened, granted, message_id="msg_bad", kind="command.submit",
                idempotency_key="idem_bad", payload={"text": "no signature, no id"},
            ),
            headers=_headers(enrolled),
        )
        assert answered.status_code == 400, answered.text
        assert answered.json()["detail"] == "command_payload_invalid"
