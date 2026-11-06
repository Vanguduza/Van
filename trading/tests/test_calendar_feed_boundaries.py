"""Calendar file shape, explicit time and stable declared event identity."""
import json

import pytest

from vati.intelligence.calendar_feed import events_from_records,load_calendar,calendar_report,_parse_ms
from vati.calendar.recorder import scheduled_from_row,observation_from_row
from vati.calendar import recorder


def row(**changes):
    return {'name':'CPI','release':'2026-10-14T12:30:00Z','currencies':'USD','source':'declared-a',**changes}


def test_bare_json_array_keeps_the_same_records_as_the_documented_object(tmp_path):
    p=tmp_path/'calendar.json';p.write_text(json.dumps([row()]))
    bare=load_calendar(p)
    p.write_text(json.dumps({'events':[row()]}))
    assert bare==load_calendar(p) and len(bare)==1


@pytest.mark.parametrize('parser',[_parse_ms,recorder._parse_ms])
def test_naive_release_time_is_rejected_instead_of_using_the_worker_timezone(parser):
    with pytest.raises(ValueError):parser('2026-10-14T12:30:00')


@pytest.mark.parametrize('parser',[_parse_ms,recorder._parse_ms])
@pytest.mark.parametrize('timestamp',[
    '2026-10-14T12:30:00.123001Z',
    '2026-10-14T12:30:00.0000001Z',
    '2026-10-14T12:30:00.1230000000000001Z',
])
def test_sub_millisecond_time_is_not_silently_made_available_earlier(parser,timestamp):
    with pytest.raises(ValueError):parser(timestamp)


def test_different_currency_scopes_cannot_silently_share_a_legacy_event_key():
    with pytest.raises(ValueError):events_from_records([row(currencies='USD'),row(currencies='CAD')])


def test_explicit_native_keys_preserve_two_same_name_and_time_series():
    result=events_from_records([row(event_key='provider:US:CPI:2026-10',currencies='USD'),
        row(event_key='provider:CA:CPI:2026-10',currencies='CAD')])
    assert len(result)==2
    assert {event.event_id for event in result}=={'provider:US:CPI:2026-10','provider:CA:CPI:2026-10'}
    assert {tuple(event.currencies) for event in result}=={('USD',),('CAD',)}


def test_schedule_and_observation_rows_keep_the_same_original_explicit_event_key():
    original=row(event_key='provider:US:CPI:2026-10')
    scheduled=scheduled_from_row(original)
    observed=observation_from_row(original|{'actual':'3.1'})
    assert scheduled.event_key==observed.event_key=='provider:US:CPI:2026-10'


def test_one_explicit_key_cannot_silently_change_its_original_release_or_scope():
    with pytest.raises(ValueError):
        events_from_records([row(event_key='provider:US:CPI'),
            row(event_key='provider:US:CPI',release='2026-10-15T12:30:00Z')])


def test_two_transport_labels_cannot_make_an_unqualified_file_live_eligible():
    events=events_from_records([row(source='transport-a'),row(source='transport-b')])
    report=calendar_report(events,now_ms=events[0].release_ms-1000)
    assert events[0].verified_sources==2  # Preserve the legacy declared count.
    assert report['live_eligible']==0 and report['declared_agreement']==1
    assert report['provider_qualified'] is False and report['authority_effect']=='NONE'


@pytest.mark.parametrize('parser',[_parse_ms,recorder._parse_ms])
def test_explicit_offsets_and_legacy_epoch_units_keep_their_original_instant(parser):
    assert parser('2026-10-14T14:30:00.123+02:00')==parser('2026-10-14T12:30:00.123Z')
    assert parser('2026-10-14T12:30:00.123000000Z')==parser('2026-10-14T12:30:00.123Z')
    assert parser('1790000000')==parser('1790000000000')==1790000000000


@pytest.mark.parametrize('parser',[_parse_ms,recorder._parse_ms])
def test_historical_dates_before_the_unix_epoch_retain_exact_signed_milliseconds(parser):
    assert parser('1969-12-31T23:59:59.999Z')==-1
    assert parser('1960-01-01T00:00:00Z')==-315619200000


@pytest.mark.parametrize('bad',[None,{}, {'events':None},{'events':{}},{'events':[1]}])
def test_malformed_file_envelopes_cannot_become_an_empty_success(tmp_path,bad):
    p=tmp_path/'calendar.json';p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):load_calendar(p)


def test_no_explicit_key_keeps_the_original_legacy_identity():
    original=row();event=events_from_records([original])[0]
    assert event.event_id==f"CPI:{event.release_ms}"
    assert scheduled_from_row(original).event_key==event.event_id
