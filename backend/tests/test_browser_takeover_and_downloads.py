"""Rev 1.5 §§18, 22 — what Hermes is handed, what the owner takes back, and what a
download is allowed to become.

Two subjects, one file, because they share a property: both are about VAN holding something
dangerous carefully. An agent grant is delegated authority over a browser that holds the
owner's logged-in sessions; a download is a file a page chose to hand over. In both cases
the interesting tests are refusals.

§22.3 is marked mandatory in the blueprint and names the insufficient implementation
directly: "a UI-only 'Take over' button without server control-generation invalidation is
not sufficient." The generation already moved before this checkpoint. What did not happen
was the other half of the same sentence — **queued agent actions discarded** — and that is
what the first class below is about.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from conftest_automation import make_store
from van_gateway.app import create_app
from van_gateway.browser.agent_grant import (
    FORBIDDEN_GRANT_FIELDS,
    AgentGrant,
    AgentGrantError,
    AgentGrantService,
    AgentGrantState,
    domain_allowed,
    scope_payload,
)
from van_gateway.browser.downloads import (
    DownloadBroker,
    DownloadError,
    DownloadState,
    OwnerAction,
    classify,
    owner_actions,
    sanitise_name,
)
from van_gateway.browser.stream_grants import generate_signing_key
from van_gateway.config import get_settings

NOW = 1_700_000_000_000
LATER = NOW + 600_000


def _service() -> tuple[AgentGrantService, AgentGrant]:
    service = AgentGrantService()
    grant = service.issue(
        grant_id="ag_1",
        session_id="ibs_1",
        target_id="tgt_1",
        goal="find the delivery date",
        allowed_domains=("example.com",),
        action_class="A1",
        step_budget=5,
        deadline_ms=LATER,
        control_lease_id="bctl_1",
        control_generation=3,
    )
    return service, grant


class TestWhatTheAgentIsGiven:

    def test_the_scope_is_exactly_the_nine_fields(self):
        """§22.2. Built explicitly rather than by serialising the grant, so a field added
        for the Gateway's own bookkeeping does not silently become something the agent
        receives — which is how a forbidden field arrives: not a decision, a default."""
        _, grant = _service()
        assert set(scope_payload(grant)) == {
            "session_id", "target_id", "goal", "allowed_domains", "action_class",
            "step_budget", "steps_remaining", "deadline_ms", "control_lease_id",
            "control_generation",
        }

    def test_no_credential_reaches_the_agent(self):
        """§22.2's five: device HMAC, owner signing key, internal token, raw cookies,
        unbounded scope. An agent holding any one could do its task and then anything."""
        _, grant = _service()
        payload = scope_payload(grant)
        serialized = repr(payload).lower()
        for forbidden in FORBIDDEN_GRANT_FIELDS:
            assert forbidden not in payload
            assert forbidden not in serialized

    def test_a_caller_cannot_attach_a_credential_through_a_passthrough(self):
        """The realistic path: a dictionary from somewhere else, passed along unchecked."""
        service = AgentGrantService()
        with pytest.raises(AgentGrantError) as caught:
            service.issue(
                grant_id="ag_2", session_id="ibs_1", target_id="t", goal="g",
                allowed_domains=("example.com",), action_class="A1", step_budget=1,
                deadline_ms=LATER, control_lease_id="b", control_generation=1,
                extra={"goal_note": "fine", "browser_cookies": "session=abc"},
            )
        assert "carries_credential" in caught.value.reason

    def test_an_empty_domain_list_is_not_everywhere(self):
        """Treating it as unbounded is how an unbounded scope arrives without a decision."""
        service = AgentGrantService()
        with pytest.raises(AgentGrantError) as caught:
            service.issue(
                grant_id="ag_3", session_id="ibs_1", target_id="t", goal="g",
                allowed_domains=(), action_class="A1", step_budget=1,
                deadline_ms=LATER, control_lease_id="b", control_generation=1,
            )
        assert caught.value.reason == "agent_grant_needs_allowed_domains"

    def test_a_grant_with_no_budget_is_refused(self):
        service = AgentGrantService()
        with pytest.raises(AgentGrantError):
            service.issue(
                grant_id="ag_4", session_id="ibs_1", target_id="t", goal="g",
                allowed_domains=("example.com",), action_class="A1", step_budget=0,
                deadline_ms=LATER, control_lease_id="b", control_generation=1,
            )

    @pytest.mark.parametrize(
        "url,allowed",
        [
            ("https://example.com/page", True),
            ("https://www.example.com/page", True),
            ("https://deep.sub.example.com/page", True),
            # The one a naive endswith gets wrong, and the way an agent ends up on a
            # domain an attacker registered to look like the one it was allowed.
            ("https://notexample.com/page", False),
            ("https://example.com.evil.net/page", False),
            ("https://evil.net/?x=example.com", False),
            ("file:///etc/passwd", False),
            ("https://user@evil.net/", False),
        ],
    )
    def test_the_domain_boundary(self, url, allowed):
        assert domain_allowed(url, ("example.com",)) is allowed


class TestOwnerPreemption:

    def test_a_grant_that_already_ended_is_left_alone(self):
        """Preemption reaches active grants, and only those.

        The `steps_used` and the completion of a grant that finished cleanly are part of
        the Mission's record of what the agent did. A preemption pass that rewrote every
        grant on the session would turn "the agent completed its task and then the owner
        picked the phone up" into "the owner interrupted the agent" — the same evidence,
        telling the owner something that did not happen.
        """
        service, _grant = _service()
        service.complete("ag_1")

        discarded = service.owner_preempted("ibs_1", new_generation=4, now_ms=LATER)

        assert discarded == []
        ended = service.get("ag_1")
        assert ended.state is AgentGrantState.COMPLETED
        assert ended.preempted_at_ms is None

    def test_preempting_twice_keeps_the_first_moment(self):
        """The owner took control, and then touched the screen again a minute later.

        `preempted_at_ms` is when the agent lost authority. Moving it on the second touch
        would make every measurement of "how long did the agent keep going after the owner
        took over" read as zero, which is precisely the number §26 asks for.
        """
        service, _grant = _service()
        service.queue("ag_1", "submit the order form")

        first = service.owner_preempted("ibs_1", new_generation=4, now_ms=LATER)
        at_first = service.get("ag_1").preempted_at_ms
        second = service.owner_preempted("ibs_1", new_generation=5, now_ms=LATER + 60_000)

        assert first == ["submit the order form"]
        assert second == [], "nothing is discarded twice"
        assert service.get("ag_1").preempted_at_ms == at_first

    def test_a_queued_action_is_discarded_not_merely_refused_later(self):
        """§22.3's mandatory half.

        An action already accepted and waiting is one the owner has taken the browser back
        from. Letting it run because it was queued before the preemption is exactly what
        the section forbids.
        """
        service, _ = _service()
        service.queue("ag_1", "click #submit")
        service.queue("ag_1", "type into #address")

        discarded = service.owner_preempted("ibs_1", new_generation=4, now_ms=NOW)

        assert discarded == ["click #submit", "type into #address"]
        assert service.get("ag_1").queued_actions == []

    def test_the_discarded_actions_are_named_rather_than_counted(self):
        """An agent that was about to submit a form and did not is a fact the owner may
        need, and "2 actions discarded" is not that fact."""
        service, _ = _service()
        service.queue("ag_1", "submit the order form")
        discarded = service.owner_preempted("ibs_1", new_generation=4)
        assert discarded == ["submit the order form"]

    def test_a_preempted_agent_is_told_which_refusal_this_is(self):
        """Not "expired", not "denied". The agent needs to know the owner intervened."""
        service, _ = _service()
        service.owner_preempted("ibs_1", new_generation=4)
        with pytest.raises(AgentGrantError) as caught:
            service.spend("ag_1", "anything", now_ms=NOW)
        assert caught.value.reason == "agent_grant_preempted_by_owner"

    def test_a_grant_already_on_the_new_generation_is_untouched(self):
        """The owner's own new lease must not preempt itself."""
        service, _ = _service()
        service.issue(
            grant_id="ag_new", session_id="ibs_1", target_id="t", goal="g",
            allowed_domains=("example.com",), action_class="A1", step_budget=3,
            deadline_ms=LATER, control_lease_id="bctl_2", control_generation=4,
        )
        service.owner_preempted("ibs_1", new_generation=4)
        assert service.get("ag_new").state is AgentGrantState.ACTIVE
        assert service.get("ag_1").state is AgentGrantState.PREEMPTED

    def test_another_session_is_not_affected(self):
        service, _ = _service()
        service.issue(
            grant_id="ag_other", session_id="ibs_2", target_id="t", goal="g",
            allowed_domains=("example.com",), action_class="A1", step_budget=3,
            deadline_ms=LATER, control_lease_id="b", control_generation=1,
        )
        service.owner_preempted("ibs_1", new_generation=4)
        assert service.get("ag_other").state is AgentGrantState.ACTIVE

    def test_the_budget_is_spent_by_the_service_not_the_caller(self):
        service, grant = _service()
        service.spend("ag_1", "navigate", now_ms=NOW)
        assert grant.steps_used == 1
        assert grant.steps_remaining == 4

    def test_a_budget_that_runs_out_stops_the_agent(self):
        service, _ = _service()
        for _ in range(5):
            service.spend("ag_1", "step", now_ms=NOW)
        with pytest.raises(AgentGrantError) as caught:
            service.spend("ag_1", "step", now_ms=NOW)
        assert caught.value.reason == "agent_grant_step_budget_exhausted"

    def test_a_deadline_that_passes_stops_the_agent(self):
        service, _ = _service()
        with pytest.raises(AgentGrantError) as caught:
            service.spend("ag_1", "step", now_ms=LATER + 1)
        assert caught.value.reason == "agent_grant_deadline_passed"


class TestDownloadClassification:

    @pytest.mark.parametrize(
        "name,mime,dangerous",
        [
            ("report.pdf", "application/pdf", False),
            ("notes.txt", "text/plain", False),
            ("photo.jpg", "image/jpeg", False),
            # The name says it. The server's declared type is irrelevant.
            ("setup.exe", "text/plain", True),
            ("run.sh", "text/plain", True),
            ("bundle.zip", "text/plain", True),
            # The declared type says it. The name is irrelevant.
            ("invoice.pdf", "application/x-msdownload", True),
            ("photo.jpg", "application/vnd.android.package-archive", True),
        ],
    )
    def test_either_signal_is_enough(self, name, mime, dangerous):
        """§18.2. The server chooses both the name and the type, so requiring them to
        agree would mean the attacker only has to lie once."""
        assert classify(suggested_name=name, declared_mime=mime).dangerous is dangerous

    @pytest.mark.parametrize(
        "name", ["../../.bashrc", "a/b.txt", "..\\windows\\system32", "", "   ", "."]
    )
    def test_a_name_that_is_not_a_name_is_refused(self, name):
        """Refused rather than repaired. A "cleaned" version of `../../.bashrc` is a
        filename nobody asked for, and the owner then sees a name never on the server."""
        with pytest.raises(DownloadError):
            sanitise_name(name)

    def test_a_quarantined_file_is_not_offered_anything_that_opens_it(self):
        """§18.2 — dangerous content is not automatically executed, and the actions that
        would put it somewhere it could run are the ones it loses."""
        actions = owner_actions(DownloadState.QUARANTINED, dangerous=True)
        assert OwnerAction.OPEN_IN_VAN not in actions
        assert OwnerAction.SEND_TO_PHONE not in actions
        # Looking at it is the whole point of having quarantined it.
        assert OwnerAction.ANALYSE in actions
        assert OwnerAction.DELETE in actions

    def test_the_state_alone_is_enough_to_withhold_the_opening_actions(self):
        """The two conditions in `owner_actions` separated, because together neither is
        falsifiable and this programme has now been caught by that nine times.

        This half: a caller that knows the file is quarantined but has lost the reason —
        a row read back without `failure_reason`, a client that only has the state — still
        gets the restricted list. Quarantine is a conclusion; it does not need re-arguing.
        """
        actions = owner_actions(DownloadState.QUARANTINED, dangerous=False)
        assert OwnerAction.OPEN_IN_VAN not in actions
        assert OwnerAction.SEND_TO_PHONE not in actions
        assert OwnerAction.ANALYSE in actions

    def test_a_callers_own_dangerous_verdict_is_enough_on_its_own(self):
        """The other half: a caller that classified the content itself and is asking what
        to offer. Deferring to the state alone would mean a surface that knows more than
        the record does has no way to say so."""
        actions = owner_actions(DownloadState.COMPLETED, dangerous=True)
        assert OwnerAction.OPEN_IN_VAN not in actions
        assert OwnerAction.SEND_TO_PHONE not in actions
        assert OwnerAction.ANALYSE in actions

    def test_a_safe_completed_file_is_offered_everything(self):
        assert set(owner_actions(DownloadState.COMPLETED, dangerous=False)) == set(OwnerAction)

    def test_a_deleted_file_is_offered_nothing(self):
        assert owner_actions(DownloadState.DELETED, dangerous=False) == []


@pytest.mark.asyncio
class TestTheDownloadPipeline:

    async def _broker(self, tmp_path):
        store = await make_store(tmp_path)
        await store.execute(
            """
            INSERT INTO browser_interactive_sessions (
              session_id, owner_device_id, profile_alias, profile_lease_id, state,
              viewport_width, viewport_height, device_scale_factor, viewport_revision,
              acked_viewport_revision, control_holder, control_lease_id,
              control_generation, active_target_id, requested_fps, mission_id,
              created_at_ms, expires_at_ms
            ) VALUES ('ibs_1','dev','authenticated_owner','pl','INTERACTIVE',
                      1080,2016,1.0,1,1,'OWNER',NULL,0,NULL,60,NULL,1,9999999999999)
            """,
            (),
        )
        return DownloadBroker(store), store

    async def test_a_safe_file_reaches_completed(self, tmp_path):
        broker, store = await self._broker(tmp_path)
        await broker.create(
            download_id="dl_1", session_id="ibs_1", target_id="t",
            suggested_name="report.pdf", declared_mime="application/pdf",
            url_digest="abc", now_ms=NOW,
        )
        await broker.start("dl_1")
        state = await broker.finish(
            download_id="dl_1", byte_size=1024, content_sha256="d" * 64, now_ms=NOW,
        )
        assert state is DownloadState.COMPLETED

    async def test_a_dangerous_file_stops_at_quarantine(self, tmp_path):
        """And stays there. Quarantine is not a step on the way to completed — if it were,
        the dangerous case would eventually reach the same place as the safe one."""
        broker, store = await self._broker(tmp_path)
        await broker.create(
            download_id="dl_2", session_id="ibs_1", target_id="t",
            suggested_name="setup.exe", declared_mime="application/octet-stream",
            url_digest="abc", now_ms=NOW,
        )
        await broker.start("dl_2")
        state = await broker.finish(
            download_id="dl_2", byte_size=2048, content_sha256="e" * 64, now_ms=NOW,
        )
        assert state is DownloadState.QUARANTINED

        row = await store.fetchone("SELECT * FROM browser_downloads WHERE download_id='dl_2'", ())
        assert row["content_sha256"] == "e" * 64, (
            "a quarantined file nobody can identify later is a quarantined file nobody "
            "can look up"
        )

    async def test_content_sniffing_overrides_a_lying_server(self, tmp_path):
        """A server that declared text/plain for an ELF binary is not one to take a hint
        from, so the stricter of the two readings wins."""
        broker, _ = await self._broker(tmp_path)
        await broker.create(
            download_id="dl_3", session_id="ibs_1", target_id="t",
            suggested_name="notes.txt", declared_mime="text/plain",
            url_digest="abc", now_ms=NOW,
        )
        await broker.start("dl_3")
        state = await broker.finish(
            download_id="dl_3", byte_size=9, content_sha256="f" * 64,
            observed_mime="application/x-executable", now_ms=NOW,
        )
        assert state is DownloadState.QUARANTINED

    async def test_a_benign_sniff_does_not_clear_a_dangerous_declaration(self, tmp_path):
        """The verdict at creation is not re-litigated by the verdict at completion.

        The server declared an archive and the host sniffed plain text. §18.2's rule is
        that **either** signal is enough, so the answer is still quarantine — and the
        reason it has to be is that the sniff is one heuristic on the first few hundred
        bytes, which a file can be arranged to satisfy. Taking the later reading as an
        overruling would let an attacker clear their own classification by shaping the
        first block of the file.

        The name carries nothing here on purpose: `archive.data` is not a dangerous
        extension, so the only thing standing between this file and COMPLETED is the
        declaration recorded at creation.
        """
        broker, store = await self._broker(tmp_path)
        await broker.create(
            download_id="dl_1", session_id="ibs_1", target_id="t",
            suggested_name="archive.data", declared_mime="application/zip",
            url_digest="abc", now_ms=NOW,
        )
        await broker.start("dl_1")
        state = await broker.finish(
            download_id="dl_1", byte_size=64, content_sha256="e" * 64,
            observed_mime="text/plain", now_ms=NOW,
        )
        assert state is DownloadState.QUARANTINED

    async def test_a_quarantined_file_cannot_be_advanced_to_completed(self, tmp_path):
        broker, _ = await self._broker(tmp_path)
        await broker.create(
            download_id="dl_4", session_id="ibs_1", target_id="t",
            suggested_name="tool.jar", declared_mime=None, url_digest="a", now_ms=NOW,
        )
        await broker.start("dl_4")
        await broker.finish(
            download_id="dl_4", byte_size=1, content_sha256="a" * 64, now_ms=NOW,
        )
        with pytest.raises(DownloadError) as caught:
            await broker._transition("dl_4", DownloadState.COMPLETED)
        assert "transition_refused" in caught.value.reason

    async def test_finishing_something_that_never_started_is_refused(self, tmp_path):
        broker, _ = await self._broker(tmp_path)
        await broker.create(
            download_id="dl_5", session_id="ibs_1", target_id="t",
            suggested_name="a.pdf", declared_mime="application/pdf",
            url_digest="a", now_ms=NOW,
        )
        with pytest.raises(DownloadError) as caught:
            await broker.finish(
                download_id="dl_5", byte_size=1, content_sha256="a" * 64, now_ms=NOW,
            )
        assert "not_in_progress" in caught.value.reason

    async def test_an_unsafe_name_never_reaches_the_table(self, tmp_path):
        broker, store = await self._broker(tmp_path)
        with pytest.raises(DownloadError):
            await broker.create(
                download_id="dl_6", session_id="ibs_1", target_id="t",
                suggested_name="../../../etc/passwd", declared_mime="text/plain",
                url_digest="a", now_ms=NOW,
            )
        row = await store.fetchone(
            "SELECT * FROM browser_downloads WHERE download_id='dl_6'", ()
        )
        assert row is None


# ------------------------------------------------------------------ through the ingress

INGRESS = "takeover-ingress-token-0123456789"
INTERNAL = "takeover-internal-token-0123456789"
SESSIONS = "/v1/browser/interactive-sessions"
REPORTS = "/v1/browser/download-reports"


@pytest.fixture
def _settings(tmp_path, monkeypatch):
    key = generate_signing_key("browser-stream-signing-test")
    key_path = tmp_path / "stream-signing.pem"
    key_path.write_text(key.private_pem)
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "takeover.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KEY_FILE", str(key_path))
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KID", "browser-stream-signing-test")
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNAL_URL", "https://stream.example/rtc")
    monkeypatch.setenv("VAN_BROWSER_STREAM_ICE_SERVERS", "[]")
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
            yield ac, app


@pytest.mark.asyncio
class TestTakeControlThroughTheIngress:

    async def _session(self, ac, app):
        ticket = await app.state.auth.create_pairing_ticket("owner-phone")
        enrolled = await app.state.auth.pair_device(
            ticket.token, "owner-phone", "s" * 32, "PEM", "owner-phone"
        )
        headers = {
            "X-Van-Ingress-Token": INGRESS,
            "X-Van-Device-Token": enrolled.access_token,
        }
        created = await ac.post(
            SESSIONS,
            json={
                "profile_alias": "authenticated_owner",
                "viewport": {"width": 1080, "height": 2016, "device_scale_factor": 1.0},
            },
            headers=headers,
        )
        return created.json()["session_id"], headers

    async def test_taking_control_discards_what_the_agent_had_queued(self, client):
        """The wiring, through the route the phone actually calls.

        The service half is tested above; this is the part that would be missing if the
        route moved the generation and forgot to call it — which is precisely the
        "UI-only Take over button" §22.3 names.
        """
        ac, app = client
        session_id, headers = await self._session(ac, app)

        grants = app.state.browser_agent_grants
        grants.issue(
            grant_id="ag_live", session_id=session_id, target_id="t",
            goal="fill the form", allowed_domains=("example.com",), action_class="A1",
            step_budget=10, deadline_ms=LATER, control_lease_id="bctl", control_generation=0,
        )
        grants.queue("ag_live", "submit the order form")

        response = await ac.post(f"{SESSIONS}/{session_id}/take-control", headers=headers)

        assert response.status_code == 200
        assert response.json()["discarded_agent_actions"] == ["submit the order form"]
        assert grants.get("ag_live").state is AgentGrantState.PREEMPTED

    async def test_the_generation_moves_as_well(self, client):
        """Both halves of §22.3, so neither can be removed alone."""
        ac, app = client
        session_id, headers = await self._session(ac, app)
        first = await ac.post(f"{SESSIONS}/{session_id}/take-control", headers=headers)
        second = await ac.post(f"{SESSIONS}/{session_id}/take-control", headers=headers)
        assert second.json()["control_generation"] > first.json()["control_generation"]

    async def test_taking_control_is_measured(self, client):
        """§26 gives owner takeover acknowledgement a 100ms target, and the owner's whole
        judgement of the feature rests on it. A log line is not a number."""
        from van_gateway.observability.metrics import REGISTRY

        ac, app = client
        session_id, headers = await self._session(ac, app)
        await ac.post(f"{SESSIONS}/{session_id}/take-control", headers=headers)
        unobserved = {metric.name for metric in REGISTRY.unobserved()}
        assert "van_browser_control_preempt_ms" not in unobserved


@pytest.mark.asyncio
class TestTheDownloadSurfacesThroughTheIngress:
    """§18 through the two routes that actually exist, which is the half a unit test of
    `DownloadBroker` cannot reach.

    Before this checkpoint the broker was constructed in `create_app` and called by
    nothing: `GET /downloads` read the table directly and no route ever wrote a row. Every
    unit test above passed against that, which is exactly the shape this programme keeps
    finding — a correct component nothing invokes.
    """

    async def _session(self, ac, app):
        ticket = await app.state.auth.create_pairing_ticket("owner-phone")
        enrolled = await app.state.auth.pair_device(
            ticket.token, "owner-phone", "s" * 32, "PEM", "owner-phone"
        )
        headers = {
            "X-Van-Ingress-Token": INGRESS,
            "X-Van-Device-Token": enrolled.access_token,
        }
        created = await ac.post(
            SESSIONS,
            json={
                "profile_alias": "authenticated_owner",
                "viewport": {"width": 1080, "height": 2016, "device_scale_factor": 1.0},
            },
            headers=headers,
        )
        return created.json()["session_id"], headers

    @property
    def _hermes(self):
        return {"X-Van-Ingress-Token": INGRESS, "X-Van-Internal-Token": INTERNAL}

    async def _report(self, ac, session_id, **overrides):
        body = {
            "download_id": "dl_route_1",
            "session_id": session_id,
            "suggested_name": "statement.pdf",
            "declared_mime": "application/pdf",
            "url_digest": "abc123",
        }
        body.update(overrides)
        return await ac.post(REPORTS, json=body, headers=self._hermes)

    async def test_a_reported_download_reaches_the_owner_listing(self, client):
        ac, app = client
        session_id, headers = await self._session(ac, app)

        started = await self._report(ac, session_id)
        assert started.status_code == 200
        assert started.json()["state"] == "IN_PROGRESS"

        finished = await ac.post(
            f"{REPORTS}/dl_route_1/finish",
            json={"byte_size": 2048, "content_sha256": "a" * 64},
            headers=self._hermes,
        )
        assert finished.json()["state"] == "COMPLETED"

        listing = await ac.get(f"{SESSIONS}/{session_id}/downloads", headers=headers)
        rows = listing.json()["downloads"]
        assert [r["download_id"] for r in rows] == ["dl_route_1"]
        assert rows[0]["state"] == "COMPLETED"
        assert rows[0]["dangerous"] is False
        assert "OPEN_IN_VAN" in rows[0]["actions"]

    async def test_the_host_cannot_report_an_executable_into_completed(self, client):
        """The report says what happened; §18.2 decides where it stops.

        This is the counterexample that makes the split worth having: there is no field in
        either body that names a state, so a control agent that has been talked into
        reporting `setup.exe` as a finished download still cannot produce a row the owner
        is offered `OPEN_IN_VAN` on.
        """
        ac, app = client
        session_id, headers = await self._session(ac, app)

        await self._report(
            ac, session_id, suggested_name="setup.exe", declared_mime="application/pdf",
        )
        finished = await ac.post(
            f"{REPORTS}/dl_route_1/finish",
            json={"byte_size": 10, "content_sha256": "b" * 64},
            headers=self._hermes,
        )
        assert finished.json()["state"] == "QUARANTINED"

        listing = await ac.get(f"{SESSIONS}/{session_id}/downloads", headers=headers)
        row = listing.json()["downloads"][0]
        assert row["dangerous"] is True
        assert "OPEN_IN_VAN" not in row["actions"]
        assert "SEND_TO_PHONE" not in row["actions"]
        assert "DELETE" in row["actions"]

    async def test_a_traversal_name_is_refused_at_the_route(self, client):
        ac, app = client
        session_id, _ = await self._session(ac, app)
        refused = await self._report(ac, session_id, suggested_name="../../.bashrc")
        assert refused.status_code == 400
        assert refused.json()["detail"] == "download_name_unsafe"

    async def test_a_retried_report_does_not_create_a_second_record(self, client):
        """The host did not get an answer and sent the report again.

        Refused rather than inserted twice, and refused with the record's *current* state
        rather than with "IN_PROGRESS": the retry may be arriving after the download
        finished, and answering with the state at creation would tell the host something
        that stopped being true before it asked. Before this, the second INSERT raised an
        IntegrityError out of the route as a 500.
        """
        ac, app = client
        session_id, headers = await self._session(ac, app)
        await self._report(ac, session_id, suggested_name="setup.exe")
        await ac.post(
            f"{REPORTS}/dl_route_1/finish",
            json={"byte_size": 1, "content_sha256": "f" * 64},
            headers=self._hermes,
        )

        again = await self._report(ac, session_id, suggested_name="setup.exe")

        assert again.status_code == 409
        assert again.json()["detail"] == "download_already_reported:QUARANTINED"
        listing = await ac.get(f"{SESSIONS}/{session_id}/downloads", headers=headers)
        assert len(listing.json()["downloads"]) == 1

    async def test_a_download_for_a_closed_session_is_refused(self, client):
        """A file does not appear in a browser the owner has already shut.

        The unknown-session case below is the easy one. This is the one that actually
        happens: the owner closes the browser, and a download the host had already begun
        reports in a second later. Accepting it would put a row on a terminated session —
        visible in the listing, attached to nothing the owner can open, with no way to
        tell where it came from.
        """
        ac, app = client
        session_id, headers = await self._session(ac, app)
        closed = await ac.delete(f"{SESSIONS}/{session_id}", headers=headers)
        assert closed.status_code == 200, closed.text
        # Pinned, because "the DELETE returned 200" also holds for a session that was
        # already terminal and returned early. The refusal below is about the state, so
        # the state is what this asserts.
        assert closed.json()["state"] == "TERMINATED", closed.text

        refused = await self._report(ac, session_id)
        assert refused.status_code == 409
        assert refused.json()["detail"] == "interactive_session_not_live"

    async def test_a_download_for_an_unknown_session_is_refused(self, client):
        ac, app = client
        await self._session(ac, app)
        refused = await self._report(ac, "ibs_does_not_exist")
        assert refused.status_code == 404

    async def test_finishing_a_download_nobody_reported_is_a_404(self, client):
        """Not a 409. A host retrying a finish for an id the Gateway never recorded needs
        to know the record is absent, not that a state machine refused the transition —
        the second reads as "try again later" and the first as "start over"."""
        ac, app = client
        await self._session(ac, app)
        missing = await ac.post(
            f"{REPORTS}/dl_never_reported/finish",
            json={"byte_size": 1, "content_sha256": "0" * 64},
            headers=self._hermes,
        )
        assert missing.status_code == 404
        assert missing.json()["detail"] == "download_unknown"

    async def test_the_owner_device_cannot_report_a_download(self, client):
        """The report surface is Hermes-scoped and the phone never saw the download.

        Asserted in this direction as well as the other because the classifier only has to
        be wrong once: a route that fell through to owner-device authentication would let
        any paired phone write download records for a session it does not own.
        """
        ac, app = client
        session_id, headers = await self._session(ac, app)
        refused = await ac.post(
            REPORTS,
            json={
                "download_id": "dl_x", "session_id": session_id,
                "suggested_name": "a.pdf", "url_digest": "d",
            },
            headers=headers,
        )
        assert refused.status_code == 403
        assert refused.json()["detail"] == "internal_control_unauthorized"

    async def test_the_owner_deletes_their_own_download(self, client):
        ac, app = client
        session_id, headers = await self._session(ac, app)
        await self._report(ac, session_id)
        await ac.post(
            f"{REPORTS}/dl_route_1/finish",
            json={"byte_size": 1, "content_sha256": "c" * 64},
            headers=self._hermes,
        )
        deleted = await ac.delete(
            f"{SESSIONS}/{session_id}/downloads/dl_route_1", headers=headers
        )
        assert deleted.status_code == 200
        assert deleted.json()["state"] == "DELETED"

        listing = await ac.get(f"{SESSIONS}/{session_id}/downloads", headers=headers)
        assert listing.json()["downloads"][0]["actions"] == []

    async def test_a_download_belonging_to_another_session_is_not_deletable(self, client):
        """Owning *a* session is not owning *this* download.

        The session check in `_owned` passes here — the caller really does own the session
        named in the path — so without the row's own session check the delete would
        succeed against a file from a session the device never had. A second profile is
        registered because the first one is leased: two live sessions are what makes the
        two ids distinguishable at all.
        """
        ac, app = client
        await app.state.browser.broker.register_profile(profile_alias="public_research")
        first, headers = await self._session(ac, app)
        await self._report(ac, first)

        second = await ac.post(
            SESSIONS,
            json={
                "profile_alias": "public_research",
                "viewport": {"width": 1080, "height": 2016, "device_scale_factor": 1.0},
            },
            headers=headers,
        )
        assert second.status_code == 200, second.text
        other_id = second.json()["session_id"]
        assert other_id != first

        refused = await ac.delete(
            f"{SESSIONS}/{other_id}/downloads/dl_route_1", headers=headers
        )
        assert refused.status_code == 404
        assert refused.json()["detail"] == "download_unknown"
