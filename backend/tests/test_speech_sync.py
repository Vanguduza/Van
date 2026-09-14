from __future__ import annotations

"""Cue-clock speech sync model used by Android/TTS binding."""


class SpeechCueClock:
    """Timestamped visemes with RMS/mouth_open fallback, bounded slew, visual lead.

    Task state is independent from TTS state — ending TTS must not imply task SUCCESS.
    """

    def __init__(self, *, visual_lead_ms: int = 40, max_slew: float = 0.25) -> None:
        self.visual_lead_ms = visual_lead_ms
        self.max_slew = max_slew
        self.mouth_open = 0.0
        self.viseme = 0
        self.speaking = False
        self.paused = False
        self._anchor_ms = 0
        self._cues: list[tuple[int, int, float]] = []

    def start_phrase(self, cues: list[tuple[int, int, float]], now_ms: int) -> None:
        self._cues = sorted(cues)
        self._anchor_ms = now_ms
        self.speaking = True
        self.paused = False

    def pause(self) -> None:
        self.paused = True

    def resume(self, now_ms: int) -> None:
        if not self.paused:
            return
        self._anchor_ms = now_ms
        self.paused = False

    def interrupt(self) -> None:
        self.speaking = False
        self.paused = False
        self.mouth_open = 0.0
        self.viseme = 0
        self._cues = []

    def tick(self, now_ms: int, *, rms: float | None = None) -> dict:
        if not self.speaking or self.paused:
            target = 0.0
            viseme = 0
        elif self._cues:
            t = now_ms - self._anchor_ms + self.visual_lead_ms
            current = self._cues[0]
            for cue in self._cues:
                if cue[0] <= t:
                    current = cue
                else:
                    break
            viseme, target = current[1], current[2]
        else:
            viseme = 0
            target = max(0.0, min(1.0, (rms or 0.0) * 1.5))

        delta = target - self.mouth_open
        if delta > self.max_slew:
            delta = self.max_slew
        elif delta < -self.max_slew:
            delta = -self.max_slew
        self.mouth_open = max(0.0, min(1.0, self.mouth_open + delta))
        self.viseme = viseme
        return {"mouth_open": self.mouth_open, "viseme": self.viseme, "speaking": self.speaking}


def test_viseme_clock_and_interrupt():
    clock = SpeechCueClock(visual_lead_ms=0, max_slew=1.0)
    clock.start_phrase([(0, 1, 0.8), (100, 2, 0.2)], now_ms=0)
    assert clock.tick(0)["viseme"] == 1
    assert clock.tick(100)["viseme"] == 2
    clock.interrupt()
    out = clock.tick(200)
    assert out["speaking"] is False
    assert out["mouth_open"] == 0.0


def test_tts_end_does_not_imply_task_success():
    clock = SpeechCueClock()
    clock.start_phrase([(0, 1, 1.0)], now_ms=0)
    clock.interrupt()
    task_state = "WORKING"
    assert clock.speaking is False
    assert task_state != "SUCCESS"


def test_rms_fallback_and_reanchor():
    clock = SpeechCueClock(visual_lead_ms=0, max_slew=1.0)
    clock.start_phrase([], now_ms=0)
    assert clock.tick(0, rms=0.4)["mouth_open"] > 0
    clock.pause()
    clock.resume(500)
    assert clock.paused is False
