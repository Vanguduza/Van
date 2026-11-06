from van_gateway.voice.speech_stream import SpeechStreamService


def stream():
    service = SpeechStreamService()
    value = service.open(response_id="response", turn_id="turn", device_id="phone", text="The answer is ready.")
    return service, value


def test_resume_state_does_not_claim_segment_zero_was_heard():
    service, _ = stream()
    state = service.response_state("phone")
    assert state["last_received_segment"] == -1
    assert state["last_spoken_segment"] == -1
    assert state["resume_from_segment"] == 0
    assert state["segments"][0]["segment_index"] == 0


def test_interrupted_speech_is_not_served_by_a_direct_resume_call():
    service, value = stream()
    service.interrupt(value.speech_stream_id)
    assert service.resume_from(value.speech_stream_id) == []


def test_an_empty_append_does_not_remove_the_final_segment():
    service, value = stream()
    original = [s.as_json() for s in value.segments]
    assert service.append(value.speech_stream_id, "   ") == []
    assert [s.as_json() for s in value.segments] == original
