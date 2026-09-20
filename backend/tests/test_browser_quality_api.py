"""Rev 1.5 §§26, 27 — the link report, driven through the ingress.

`BrowserQualityController` has been correct since the checkpoint that wrote it and had no
caller, which is the shape this programme keeps finding: logic that is right, tested, and
unreachable. These tests are about the route, so they are mostly about the two things a
route can get wrong that the controller cannot.

The first is §26.2's: `high_quality_certified` is a property of the verdict and must not be
something a caller can assert. A request body with a field for it would let a phone certify
its own session, and the telemetry claiming a certification it did not earn is the failure
that section names.

The second is §27.4's: the controller holds the hysteresis streak, so one controller per
session for as long as the session lives. A router that built one per request would upgrade
on every third sample forever, and the owner would watch the badge change more often than
the page.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.browser.quality import QualityMode
from van_gateway.config import get_settings
from van_gateway.observability import metrics as metrics_module
from van_gateway.browser.stream_grants import generate_signing_key

INGRESS = "quality-ingress-token-0123456789"
INTERNAL = "quality-internal-token-0123456789"
SIGNING_KID = "browser-stream-signing-test"
SESSIONS = "/v1/browser/interactive-sessions"


@pytest.fixture
def _settings(tmp_path, monkeypatch):
    key = generate_signing_key(SIGNING_KID)
    key_path = tmp_path / "stream-signing.pem"
    key_path.write_text(key.private_pem)
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "quality.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KEY_FILE", str(key_path))
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KID", SIGNING_KID)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNAL_URL", "https://stream.example/rtc")
    monkeypatch.setenv(
        "VAN_BROWSER_STREAM_ICE_SERVERS", '[{"urls": ["stun:stun.example:3478"]}]'
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(_settings):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            await app.state.browser.broker.register_profile(profile_alias="authenticated_owner")
            # §22.1 — a profile is leased to one session at a time, so a test that needs
            # two live sessions needs two profiles. The lease is the point, not an
            # obstacle: two sessions sharing one authenticated profile is the thing it
            # exists to refuse.
            await app.state.browser.broker.register_profile(profile_alias="public_research")
            yield ac, app


async def _device(app, label="owner-phone"):
    ticket = await app.state.auth.create_pairing_ticket(label)
    return await app.state.auth.pair_device(ticket.token, label, "s" * 32, "PEM", label)


def _headers(enrolled):
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": enrolled.access_token}


async def _session(ac, app, label="owner-phone", profile="authenticated_owner"):
    enrolled = await _device(app, label)
    created = await ac.post(
        SESSIONS,
        json={
            "profile_alias": profile,
            "viewport": {"width": 1080, "height": 2016, "device_scale_factor": 1.0},
        },
        headers=_headers(enrolled),
    )
    assert created.status_code == 200, created.text
    return enrolled, created.json()["session_id"]


def _sample(**overrides):
    body = {
        "rtt_ms": 40.0,
        "jitter_ms": 5.0,
        "packet_loss": 0.001,
        "available_bitrate_kbps": 9_000.0,
        "rendered_fps": 60.0,
        "metered": False,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
class TestTheVerdictIsTheGatewaysToMake:

    async def test_a_body_has_no_field_for_the_certification(self, client):
        """§26.2 — the failure is the telemetry claiming what it did not earn.

        Not "the route ignores it": a field pydantic silently drops is a field the next
        maintainer can wire up. The model forbids extras, so an attempt to certify is a
        refusal the caller can see.
        """
        from van_gateway.browser.quality_api import LinkReportBody

        assert "high_quality_certified" not in LinkReportBody.model_fields
        assert "quality_mode" not in LinkReportBody.model_fields
        assert "status" not in LinkReportBody.model_fields

    async def test_a_body_claiming_the_certification_is_refused_not_ignored(self, client):
        """The claim is refused where it is made.

        pydantic ignores unknown fields by default, and an ignored
        `high_quality_certified` is worse than a rejected one: the caller believes it set
        something, and the next person to add the field finds it already arriving from
        devices in the field. `extra="forbid"` turns that into a 422 the caller reads.
        """
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        refused = await ac.post(
            f"{SESSIONS}/{session_id}/link-report",
            json=_sample(high_quality_certified=True),
            headers=_headers(enrolled),
        )
        assert refused.status_code == 422, refused.text

    async def test_a_body_naming_its_own_quality_mode_is_refused_too(self, client):
        """The rung is the Gateway's verdict; §27.1's ladder is not a client preference."""
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        refused = await ac.post(
            f"{SESSIONS}/{session_id}/link-report",
            json=_sample(quality_mode="ULTRA"), headers=_headers(enrolled),
        )
        assert refused.status_code == 422, refused.text

    async def test_a_metered_link_meeting_its_own_profile_is_not_certified(self, client):
        """§26.2's other half, and the one worth an assertion.

        A metered session that meets the metered profile is `OK` — it has not failed. What
        it has not done is earn high-quality certification, and a route that read `status`
        and called that certified would be the exact misreport §26.2 names.
        """
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        reported = await ac.post(
            f"{SESSIONS}/{session_id}/link-report",
            json=_sample(metered=True, rtt_ms=90.0, rendered_fps=31.0,
                         available_bitrate_kbps=2_000.0),
            headers=_headers(enrolled),
        )
        assert reported.status_code == 200, reported.text
        payload = reported.json()
        assert payload["profile"] == "metered"
        assert payload["high_quality_certified"] is False

    async def test_an_unmetered_link_that_is_actually_good_is_certified(self, client):
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        payload = (await ac.post(
            f"{SESSIONS}/{session_id}/link-report",
            json=_sample(), headers=_headers(enrolled),
        )).json()
        assert payload["profile"] == "unmetered"
        assert payload["high_quality_certified"] is True


@pytest.mark.asyncio
class TestTheControllerOutlivesTheRequest:

    async def test_the_upgrade_streak_survives_across_reports(self, client):
        """§27.4 — three agreeing samples, not three independent first samples.

        This is the test that fails if the router builds a controller per request: each
        report would start a new streak, the mode would sit where it started forever, and
        every individual response would still look correct.
        """
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        good = _sample(available_bitrate_kbps=12_000.0, rtt_ms=20.0, jitter_ms=2.0)
        modes = []
        for _ in range(4):
            modes.append((await ac.post(
                f"{SESSIONS}/{session_id}/link-report",
                json=good, headers=_headers(enrolled),
            )).json()["quality_mode"])
        assert modes[0] == QualityMode.NORMAL.value
        assert QualityMode.ULTRA.value in modes, modes

    async def test_the_byte_accounting_accumulates_rather_than_restarting(self, client):
        """§27.3 — what the session cost the owner, not what the last report cost."""
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        for _ in range(3):
            payload = (await ac.post(
                f"{SESSIONS}/{session_id}/link-report",
                json=_sample(media_bytes_received=1_000, control_bytes=10),
                headers=_headers(enrolled),
            )).json()
        assert payload["accounting"]["media_bytes_received"] == 3_000
        assert payload["accounting"]["control_bytes"] == 30

    async def test_two_sessions_do_not_share_one_accounting(self, client):
        """A controller keyed by nothing would bill the second session for the first."""
        ac, app = client
        first_device, first = await _session(ac, app, "phone-one")
        second_device, second = await _session(ac, app, "phone-two", "public_research")
        await ac.post(
            f"{SESSIONS}/{first}/link-report",
            json=_sample(media_bytes_received=5_000), headers=_headers(first_device),
        )
        payload = (await ac.post(
            f"{SESSIONS}/{second}/link-report",
            json=_sample(media_bytes_received=7), headers=_headers(second_device),
        )).json()
        assert payload["accounting"]["media_bytes_received"] == 7

    async def test_ending_the_session_forgets_its_accounting(self, client):
        """§27.3 is per session, and the router's `on_session_ended` is what makes it so.

        Without the hook the controller outlives the session it was built for: a process
        that runs for a week accumulates one per session forever, and a session id that
        came round again would be handed the previous owner's data figure.
        """
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        await ac.post(
            f"{SESSIONS}/{session_id}/link-report",
            json=_sample(media_bytes_received=9_000), headers=_headers(enrolled),
        )
        assert app.state.browser_quality.summary(session_id) is not None
        ended = await ac.delete(f"{SESSIONS}/{session_id}", headers=_headers(enrolled))
        assert ended.status_code == 200, ended.text
        assert app.state.browser_quality.summary(session_id) is None


@pytest.mark.asyncio
class TestTheRouteIsTheOwnersAlone:

    async def test_another_paired_device_cannot_report_for_this_session(self, client):
        ac, app = client
        _, session_id = await _session(ac, app)
        intruder = await _device(app, "second-phone")
        refused = await ac.post(
            f"{SESSIONS}/{session_id}/link-report",
            json=_sample(), headers=_headers(intruder),
        )
        # 404 rather than 403: a device that does not own the session does not learn it
        # exists.
        assert refused.status_code == 404

    async def test_a_report_for_an_ended_session_is_refused(self, client):
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        await ac.delete(f"{SESSIONS}/{session_id}", headers=_headers(enrolled))
        refused = await ac.post(
            f"{SESSIONS}/{session_id}/link-report",
            json=_sample(), headers=_headers(enrolled),
        )
        assert refused.status_code == 409
        assert refused.json()["detail"] == "interactive_session_not_live"

    async def test_reading_the_quality_does_not_move_the_hysteresis(self, client):
        """A status page that changed the thing it reports would be unreadable.

        The GET returns the last verdict. If it invented a sample the streak would move on
        every poll, and a dashboard refreshing every second would drive the ladder.
        """
        ac, app = client
        enrolled, session_id = await _session(ac, app)
        before = (await ac.get(
            f"{SESSIONS}/{session_id}/quality", headers=_headers(enrolled),
        )).json()
        assert before["observed"] is False
        for _ in range(6):
            await ac.get(f"{SESSIONS}/{session_id}/quality", headers=_headers(enrolled))
        after = (await ac.get(
            f"{SESSIONS}/{session_id}/quality", headers=_headers(enrolled),
        )).json()
        assert after["observed"] is False
        assert after["quality_mode"] == before["quality_mode"]


@pytest.mark.asyncio
async def test_a_link_report_produces_the_declared_metric(client):
    """§27's instrument had a declared producer and no caller until this route existed."""
    ac, app = client
    enrolled, session_id = await _session(ac, app)
    await ac.post(
        f"{SESSIONS}/{session_id}/link-report",
        json=_sample(metered=True), headers=_headers(enrolled),
    )
    rendered = metrics_module.render_prometheus(metrics_module.REGISTRY)
    assert "van_browser_quality_mode" in rendered
    assert 'metered="true"' in rendered
