"""Deterministic CDP startup responses, separate from live Chromium security evidence."""
from types import SimpleNamespace
import pytest
import cdp_harness_kit as kit


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        assert 0 < duration <= 0.05
        self.waits.append(duration)
        self.now += duration


class Socket:
    closed = False

    def close(self):
        self.closed = True


def construction(monkeypatch, responses, *, advance=0):
    import websockets.sync.client
    clock, socket, calls = Clock(), Socket(), []
    monkeypatch.setattr(kit, "time", clock)
    monkeypatch.setattr(websockets.sync.client, "connect", lambda *a, **k: socket)
    monkeypatch.setattr(kit, "threading", SimpleNamespace(
        Lock=lambda: None, Thread=lambda **k: SimpleNamespace(start=lambda: None)))
    stream = iter(responses)

    def send(self, method, params=None, session_id=None, timeout=15):
        calls.append((method, params, session_id, timeout))
        if method == "Target.getTargets":
            value = next(stream, {"targetInfos": []})
            clock.now += advance
            if isinstance(value, Exception):
                raise value
            return value
        if method == "Target.attachToTarget":
            return {"sessionId": "page-session"}
        return {}

    monkeypatch.setattr(kit.HarnessSession, "send", send)
    return clock, socket, calls


def test_debug_socket_before_page_waits_for_original_target_without_creating_a_replacement(monkeypatch):
    clock, socket, calls = construction(monkeypatch, [
        {"targetInfos": []},
        {"targetInfos": [{"type": "service_worker", "targetId": "worker"}]},
        {"targetInfos": [{"type": "page", "targetId": "original-page"}]},
    ])
    session = kit.HarnessSession("ws://fixture/browser")
    assert session.session == "page-session" and len(clock.waits) == 2
    assert [c[0] for c in calls].count("Target.getTargets") == 3
    assert next(c for c in calls if c[0] == "Target.attachToTarget")[1] == {
        "targetId": "original-page", "flatten": True}
    assert not any(c[0] == "Target.createTarget" for c in calls)
    assert [(c[0], c[2]) for c in calls if c[0].endswith(".enable")] == [
        ("Page.enable", "page-session"), ("DOM.enable", "page-session"),
        ("Runtime.enable", "page-session"), ("Network.enable", "page-session")]
    assert not socket.closed


def test_ready_page_does_not_wait_or_replace_it(monkeypatch):
    clock, socket, calls = construction(monkeypatch, [
        {"targetInfos": [{"type": "page", "targetId": "already-ready"}]}])
    kit.HarnessSession("ws://fixture/browser")
    assert not clock.waits and not socket.closed
    assert len([c for c in calls if c[0] == "Target.getTargets"]) == 1


def test_missing_page_has_bounded_deadline_and_closes_failed_connection(monkeypatch):
    clock, socket, calls = construction(monkeypatch, [])
    with pytest.raises(TimeoutError, match="CHROMIUM_PAGE_TARGET_NOT_READY"):
        kit.HarnessSession("ws://fixture/browser")
    assert 10 <= clock.now < 10.1 and socket.closed
    assert not any(c[0] == "Target.attachToTarget" for c in calls)
    assert all(0 < c[3] <= 10 for c in calls)


def test_page_arriving_after_original_deadline_is_not_accepted(monkeypatch):
    clock, socket, calls = construction(monkeypatch, [
        {"targetInfos": [{"type": "page", "targetId": "late"}]}], advance=11)
    with pytest.raises(TimeoutError, match="CHROMIUM_PAGE_TARGET_NOT_READY"):
        kit.HarnessSession("ws://fixture/browser")
    assert socket.closed and not any(c[0] == "Target.attachToTarget" for c in calls)


def test_cdp_failure_is_reported_without_restarting_or_hiding_it(monkeypatch):
    clock, socket, calls = construction(monkeypatch, [RuntimeError("real CDP failure")])
    with pytest.raises(RuntimeError, match="real CDP failure"):
        kit.HarnessSession("ws://fixture/browser")
    assert socket.closed and not clock.waits and len(calls) == 1
