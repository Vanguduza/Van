from __future__ import annotations

"""Cue-clock speech sync model used by Android/TTS binding.

GAP-F-013 — `SpeechCueClock` used to be defined in this test file: a decision function
written, exercised here, and imported by nothing that runs. It now lives in production at
`van_gateway.voice.speech_cues`, re-exported here so these tests keep exercising the exact
class the Gateway ships rather than a copy of it.
"""

from van_gateway.voice.speech_cues import SpeechCueClock

__all__ = ["SpeechCueClock"]


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
