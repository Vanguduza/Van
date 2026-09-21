"""Rev 1.5 §38 items 12, 17, 18 — the three floods.

A flood is the attack where every individual request is legitimate. That is why these
three had no bound: one more tab, one more download and one more input packet are each
exactly what the system is for, and the harm is only in the count.

The tests are mostly about the two ways a bound goes wrong. It can be too tight, in which
case the first person it inconveniences removes it — so each bound is exercised at the
level ordinary use actually reaches. Or it can be shaped so that a patient attacker walks
around it, which is what the sliding-window tests below are for.
"""

from __future__ import annotations

import pytest

from van_gateway.browser.flood_bounds import (
    INPUT_WINDOW_MS,
    MAX_CONCURRENT_DOWNLOADS_PER_SESSION,
    MAX_INPUT_PACKETS_PER_SECOND,
    MAX_OPEN_TABS_PER_SESSION,
    InputRateLimiter,
)


class TestTheInputRateBound:

    def test_a_burst_under_the_bound_is_admitted_whole(self):
        limiter = InputRateLimiter()
        assert all(limiter.admit("ibs_1", 1_000) for _ in range(MAX_INPUT_PACKETS_PER_SECOND))

    def test_one_packet_past_the_bound_is_refused(self):
        limiter = InputRateLimiter()
        for _ in range(MAX_INPUT_PACKETS_PER_SECOND):
            limiter.admit("ibs_1", 1_000)
        assert limiter.admit("ibs_1", 1_000) is False

    def test_an_owner_dragging_on_a_120hz_display_never_reaches_it(self):
        """The bound that matters: the one nobody removes because it never fires.

        §8.7 coalesces motion to one MOVE per frame, so a finger on a 120 Hz panel
        produces about 120 packets a second at its busiest, plus edges. A bound set near
        that would refuse the owner mid-drag, and the first person that happened to would
        delete it — leaving no bound at all.
        """
        limiter = InputRateLimiter()
        # Three seconds of continuous dragging at 120 Hz with an edge on every frame.
        for frame in range(360):
            now = 1_000 + int(frame * 1000 / 120)
            assert limiter.admit("ibs_1", now), frame
            assert limiter.admit("ibs_1", now), frame

    def test_the_window_slides_so_a_stopped_flood_recovers(self):
        limiter = InputRateLimiter()
        for _ in range(MAX_INPUT_PACKETS_PER_SECOND):
            limiter.admit("ibs_1", 1_000)
        assert limiter.admit("ibs_1", 1_000) is False
        assert limiter.admit("ibs_1", 1_000 + INPUT_WINDOW_MS + 1) is True

    def test_a_refused_packet_does_not_extend_the_refusal(self):
        """The bug a naive implementation has, and it is self-sustaining.

        If a refused packet were still recorded, every refusal would push the window
        forward by its own timestamp — so the owner's next packet is refused, *that*
        refusal extends the window again, and the session never recovers. A bound that
        cannot be escaped is an outage, not a defence.

        The shape of this test is the point, and the first version of it did not have it.
        It sent ten thousand refusals at one timestamp and then checked a moment past the
        window, which recovers under either implementation because a single timestamp ages
        out in one step. A mutation that appended refused packets survived it. What
        distinguishes the two is a flood *spread over time* that then stops: below, the
        correct implementation admits the owner's very next packet and the broken one
        never admits another.
        """
        limiter = InputRateLimiter()
        # Twelve times the bound, sustained for two seconds, one millisecond at a time.
        for millisecond in range(0, 2_000):
            for _ in range(5):
                limiter.admit("ibs_1", millisecond)
        # The flood stops. The owner taps.
        recovered_at = next(
            (t for t in range(2_000, 2_000 + 2 * INPUT_WINDOW_MS)
             if limiter.admit("ibs_1", t)),
            None,
        )
        assert recovered_at == 2_000, recovered_at

    def test_a_patient_flood_at_the_bound_stays_at_the_bound(self):
        """A sliding window, not a bucket.

        A token bucket permits a long-run rate above the bound if the burst shape is
        right, which is precisely what an attacker with time would do.
        """
        limiter = InputRateLimiter(limit=10, window_ms=1_000)
        admitted = 0
        for millisecond in range(0, 5_000, 50):  # 20 packets/second, sustained
            if limiter.admit("ibs_1", 1_000 + millisecond):
                admitted += 1
        # Five seconds at the bound is fifty packets, not a hundred.
        assert admitted <= 10 * 5 + 10, admitted

    def test_one_session_under_attack_does_not_throttle_another(self):
        """The owner's session is the one that must keep working."""
        limiter = InputRateLimiter()
        for _ in range(MAX_INPUT_PACKETS_PER_SECOND * 2):
            limiter.admit("ibs_attacked", 1_000)
        assert limiter.admit("ibs_owner", 1_000) is True

    def test_a_closed_session_leaves_nothing_behind(self):
        limiter = InputRateLimiter()
        limiter.admit("ibs_1", 1_000)
        assert limiter.depth("ibs_1") == 1
        limiter.forget("ibs_1")
        assert limiter.depth("ibs_1") == 0


class TestTheBoundsAreSetWhereOrdinaryUseDoesNotReachThem:

    def test_the_tab_bound_leaves_room_for_a_morning_of_research(self):
        assert MAX_OPEN_TABS_PER_SESSION >= 32

    def test_the_download_bound_is_lower_than_the_tab_bound(self):
        """A download is a file on a disk; a tab is a page. They are not the same cost."""
        assert MAX_CONCURRENT_DOWNLOADS_PER_SESSION < MAX_OPEN_TABS_PER_SESSION

    @pytest.mark.parametrize(
        "bound", [MAX_OPEN_TABS_PER_SESSION, MAX_CONCURRENT_DOWNLOADS_PER_SESSION,
                  MAX_INPUT_PACKETS_PER_SECOND],
    )
    def test_no_bound_is_zero_or_negative(self, bound):
        """A bound of zero is not a strict bound, it is a disabled feature."""
        assert bound > 0


# --------------------------------------------------------------- against the real store

import pytest_asyncio  # noqa: E402

from conftest_automation import make_store  # noqa: E402
from van_gateway.browser.downloads import DownloadBroker, DownloadError  # noqa: E402
from van_gateway.browser.flood_bounds import (  # noqa: E402
    REJECT_DOWNLOAD_FLOOD,
    REJECT_TAB_FLOOD,
)


SESSION_ROW = """
    INSERT INTO browser_interactive_sessions (
      session_id, owner_device_id, profile_alias, profile_lease_id, state,
      viewport_width, viewport_height, device_scale_factor, viewport_revision,
      acked_viewport_revision, control_holder, control_lease_id,
      control_generation, active_target_id, requested_fps, mission_id,
      created_at_ms, expires_at_ms
    ) VALUES (?,'dev',?,?,'INTERACTIVE',1080,2016,1.0,1,1,'OWNER',NULL,0,NULL,60,NULL,1,
              9999999999999)
"""


@pytest_asyncio.fixture
async def store(tmp_path):
    """A real store with real sessions: the bounds are SQL, so a fake would not test them."""
    store = await make_store(tmp_path)
    for session in ("ibs_1", "ibs_flood", "ibs_owner"):
        await store.execute(SESSION_ROW, (session, f"profile_{session}", f"pl_{session}"))
    return store


@pytest.mark.asyncio
class TestTheDownloadFloodBound:
    """The bound counts what is in flight, not what has ever happened.

    An owner working through an afternoon legitimately finishes a hundred downloads. A
    page that has sixteen in flight at once is not serving a person, and the difference is
    the only thing that makes the bound usable.
    """

    async def _start(self, broker, n, *, session="ibs_1", prefix="dl"):
        for i in range(n):
            await broker.create(
                download_id=f"{session}_{prefix}_{i}", session_id=session, target_id="t1",
                suggested_name=f"report-{i}.pdf", declared_mime="application/pdf",
                url_digest="d" * 64,
            )

    async def test_the_bound_is_reached_and_named(self, store):
        broker = DownloadBroker(store)
        await self._start(broker, MAX_CONCURRENT_DOWNLOADS_PER_SESSION)
        with pytest.raises(DownloadError) as caught:
            await self._start(broker, 1, prefix="one-too-many")
        assert caught.value.reason == REJECT_DOWNLOAD_FLOOD

    async def test_a_finished_download_frees_a_slot(self, store):
        """Otherwise a long session would silently stop accepting downloads forever."""
        broker = DownloadBroker(store)
        await self._start(broker, MAX_CONCURRENT_DOWNLOADS_PER_SESSION)
        await broker.start("ibs_1_dl_0")
        await broker.finish(
            download_id="ibs_1_dl_0", byte_size=10, content_sha256="a" * 64,
        )
        await self._start(broker, 1, prefix="after")

    async def test_another_session_is_not_bounded_by_this_ones_flood(self, store):
        broker = DownloadBroker(store)
        await self._start(broker, MAX_CONCURRENT_DOWNLOADS_PER_SESSION, session="ibs_flood")
        await self._start(broker, 1, session="ibs_owner", prefix="owner")


    async def test_a_download_for_a_session_that_does_not_exist_says_so(self, store):
        """Found while writing the bound above, and a different bug entirely.

        `browser_downloads` has a foreign key to the session table, and SQLite raises the
        same `IntegrityError` for that as for a duplicate primary key. Both were caught
        and called `download_already_reported`, so a host reporting into a session that
        was never created was told its report had already been recorded — and whoever
        read the log went looking for a record that does not exist.
        """
        from van_gateway.browser.flood_bounds import REJECT_DOWNLOAD_SESSION_UNKNOWN

        broker = DownloadBroker(store)
        with pytest.raises(DownloadError) as caught:
            await broker.create(
                download_id="dl_orphan", session_id="ibs_nobody", target_id=None,
                suggested_name="x.pdf", declared_mime="application/pdf",
                url_digest="d" * 64,
            )
        assert caught.value.reason == REJECT_DOWNLOAD_SESSION_UNKNOWN

    async def test_a_genuine_duplicate_is_still_a_duplicate(self, store):
        """The other half. A fix that renamed both failures would pass the test above."""
        broker = DownloadBroker(store)
        await self._start(broker, 1, prefix="dup")
        with pytest.raises(DownloadError) as caught:
            await self._start(broker, 1, prefix="dup")
        assert caught.value.reason == "download_already_reported"


@pytest.mark.asyncio
class TestTheTabFloodBound:
    """§38 item 17 — a page opening tabs on its own.

    Bounded where the tab is *recorded*, because that is the only place that sees all of
    them: a page opens a tab, the Stream Host reports it, and nothing before that point is
    VAN's to refuse.
    """

    async def _service(self, tmp_path):
        from conftest_automation import make_store as _make
        from van_gateway.browser.control_lease import ControlLeaseService
        from van_gateway.browser.interactive_models import Viewport
        from van_gateway.browser.interactive_service import (
            InteractiveSessionError,
            InteractiveSessionService,
        )
        from van_gateway.browser.service import BrowserSessionBroker
        from van_gateway.events.bus import EventBus

        store = await _make(tmp_path)
        broker = BrowserSessionBroker(store)
        await broker.register_profile(profile_alias="authenticated_owner")
        service = InteractiveSessionService(
            store, broker, ControlLeaseService(store), EventBus(store)
        )
        session = await service.create(
            owner_device_id="dev", profile_alias="authenticated_owner",
            viewport=Viewport(width=1080, height=2016, device_scale_factor=1.0),
            now_ms=1_000,
        )
        return service, session, InteractiveSessionError

    async def _open(self, service, session, first, count):
        for i in range(first, first + count):
            await service.record_active_url(
                session_id=session.session_id, target_id=f"t{i}",
                url=f"https://example.test/{i}", title=f"page {i}", now_ms=2_000 + i,
            )

    async def test_the_bound_is_reached_and_named(self, tmp_path):
        service, session, error = await self._service(tmp_path)
        await self._open(service, session, 0, MAX_OPEN_TABS_PER_SESSION)
        with pytest.raises(error) as caught:
            await self._open(service, session, MAX_OPEN_TABS_PER_SESSION, 1)
        assert str(caught.value) == REJECT_TAB_FLOOD

    async def test_navigating_inside_a_tab_that_already_exists_is_never_refused(self, tmp_path):
        """The common case, and the one a naive bound breaks.

        A page navigating in a tab the session already has is ordinary browsing. If the
        bound counted every `record_active_url` rather than every *new* target, a session
        at the limit would stop being able to follow a link — which is the browser not
        working, reported as a security control.
        """
        service, session, _ = await self._service(tmp_path)
        await self._open(service, session, 0, MAX_OPEN_TABS_PER_SESSION)
        for step in range(20):
            await service.record_active_url(
                session_id=session.session_id, target_id="t0",
                url=f"https://example.test/page-{step}", title="same tab",
                now_ms=9_000 + step,
            )

    async def test_the_new_tab_is_refused_rather_than_an_old_one_closed(self, tmp_path):
        """Closing loses the owner's work, which is the harm rather than the defence."""
        service, session, error = await self._service(tmp_path)
        await self._open(service, session, 0, MAX_OPEN_TABS_PER_SESSION)
        with pytest.raises(error):
            await self._open(service, session, 999, 1)
        tabs = await service.targets(session.session_id)
        assert len(tabs) == MAX_OPEN_TABS_PER_SESSION
        assert {t["target_id"] for t in tabs} == {f"t{i}" for i in range(MAX_OPEN_TABS_PER_SESSION)}
