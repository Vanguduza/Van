import pytest

from van_gateway.voice.speech_stream import SpeechStreamService


def opened(service=None, **changes):
    service = service or SpeechStreamService()
    args = dict(response_id="response", turn_id="turn", device_id="phone", text="The answer is ready.", interruptible=True)
    args.update(changes)
    return service, service.open(**args)


def test_response_identity_does_not_share_a_queue_between_devices():
    service, first = opened()
    _, second = opened(service, device_id="another-phone")
    assert first.speech_stream_id != second.speech_stream_id
    assert second.device_id == "another-phone"
    service.report_cursors(first.speech_stream_id, last_received_segment=0, last_spoken_segment=0)
    assert service.response_state("phone") is None
    assert service.response_state("another-phone")["last_spoken_segment"] == -1


@pytest.mark.parametrize("change", [{"text":"A conflicting answer."}, {"turn_id":"other-turn"}, {"interruptible":False}])
def test_retry_cannot_silently_change_the_original_response(change):
    service, first = opened()
    with pytest.raises(ValueError, match="conflict"):
        opened(service, **change)
    assert service.get(first.speech_stream_id).segments[0].text == "The answer is ready."


@pytest.mark.parametrize("received,spoken", [(True,0),(0,True),(0.5,0),(-2,-1),(0,1),(1,0)])
def test_invalid_audio_cursors_do_not_acknowledge_unserved_speech(received,spoken):
    service, first = opened()
    with pytest.raises(ValueError, match="cursor"):
        service.report_cursors(first.speech_stream_id,last_received_segment=received,last_spoken_segment=spoken)
    state=service.response_state("phone")
    assert state["last_received_segment"]==state["last_spoken_segment"]==-1


def test_exact_response_retry_retains_the_original_stream_and_progress():
    service, first = opened()
    service.report_cursors(first.speech_stream_id,last_received_segment=0,last_spoken_segment=0)
    _, again = opened(service)
    assert again is first and again.complete


def test_expired_stream_is_not_returned_just_because_no_operator_called_sweep():
    service, first = opened()
    first.created_at_ms = 0
    assert service.response_state("phone") is None


def test_empty_speech_is_not_an_unfinishable_active_response():
    with pytest.raises(ValueError, match="empty"):
        opened(text="  ")


def test_same_inputs_after_restart_keep_the_id_but_changed_content_cannot_alias_old_audio():
    _, first = opened()
    _, restored = opened()
    _, revised = opened(text="A revised answer is ready.")
    assert restored.speech_stream_id == first.speech_stream_id
    assert revised.speech_stream_id != first.speech_stream_id


def test_expired_stream_cannot_be_read_or_appended_through_other_methods():
    service, value = opened()
    value.created_at_ms = 0
    assert service.get(value.speech_stream_id) is None
    assert service.resume_from(value.speech_stream_id) == []
    assert service.append(value.speech_stream_id, "More stale text.") == []
