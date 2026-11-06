"""Declared headline availability and feed trust cannot create earlier evidence."""
from decimal import Decimal

import pytest

from vati.events.news_ingress import (
    Headline, NewsIngress, NewsIngressError, NewsSource, SourceTrust,
    event_risk_multiplier_for,
)

NOW=1_800_000_000_000


def story(**changes):
    return Headline(**dict(source_id='publisher',trust=SourceTrust.T1_PRIMARY,
        published_ms=NOW,observed_ms=NOW,title='Emergency policy decision',
        symbols=('EURUSD',),severity=Decimal('1'))|changes)


@pytest.mark.parametrize('changes',[
    {'observed_ms':NOW+1000}, {'published_ms':NOW+1000},
])
def test_future_publication_or_observation_cannot_affect_an_earlier_subject(changes):
    news=NewsIngress();h=story(**changes);news.ingest(h)
    assert news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW) is None
    assert news.candidate_risk('EURUSD',now_ms=NOW)==(Decimal('1'),Decimal('0'),())
    assert news.impacts_for('p')==[]


def test_a_future_relay_cannot_enter_an_earlier_impact_evidence_set():
    news=NewsIngress();h=story();news.ingest(h)
    news.ingest(story(source_id='future-relay',observed_ms=NOW+1000))
    before=news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    after=news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW+1000)
    assert 'publisher' in before.evidence_refs and 'future-relay' not in before.evidence_refs
    assert 'future-relay' in after.evidence_refs
    assert news.relayed_by(h.headline_id)==('publisher','future-relay')


@pytest.mark.parametrize('registered,requested,expected',[
    (None,'T1_PRIMARY',SourceTrust.UNTRUSTED),
    (SourceTrust.T2_SECONDARY,'T1_PRIMARY',SourceTrust.T2_SECONDARY),
    (SourceTrust.T1_PRIMARY,'UNTRUSTED',SourceTrust.UNTRUSTED),
])
def test_a_feed_row_cannot_promote_its_own_source_trust(registered,requested,expected):
    news=NewsIngress(sources=[] if registered is None else [NewsSource('publisher',registered)])
    parsed=news.headline_from_row(dict(source='publisher',trust=requested,title='Policy decision',
        published_ms=NOW,observed_ms=NOW))
    assert parsed.trust is expected


def test_explicit_zero_milliseconds_is_not_replaced_by_another_time():
    news=NewsIngress()
    h=news.headline_from_row(dict(source='publisher',title='Historical event',published_ms=0,observed_ms=1000))
    assert h.published_ms==0 and h.observed_ms==1000


@pytest.mark.parametrize('floor',[Decimal('-0.1'),Decimal('2'),Decimal('NaN')])
def test_an_invalid_floor_cannot_make_the_reduce_only_multiplier_exceed_its_contract(floor):
    with pytest.raises(NewsIngressError):event_risk_multiplier_for(Decimal('1'),floor=floor)


@pytest.mark.parametrize('value',[Decimal('NaN'),Decimal('Infinity')])
def test_nonfinite_news_materiality_has_a_controlled_domain_error(value):
    with pytest.raises(NewsIngressError):event_risk_multiplier_for(value)


def test_same_subject_identifier_in_different_subject_kinds_keeps_distinct_impacts():
    news=NewsIngress();h=story();news.ingest(h)
    a=news.assess(h,subject_kind='POSITION',subject_id='same',symbol='EURUSD',now_ms=NOW)
    b=news.assess(h,subject_kind='CANDIDATE',subject_id='same',symbol='EURUSD',now_ms=NOW)
    assert a.impact_id!=b.impact_id


def test_available_original_story_keeps_reduce_only_sizing_and_its_reference():
    news=NewsIngress();h=story();news.ingest(h)
    multiplier,materiality,refs=news.candidate_risk('EURUSD',now_ms=NOW)
    assert multiplier==Decimal('0.25') and materiality==Decimal('1')
    assert h.dedupe_hash in refs


def test_supplied_ingress_clock_prevents_a_backdated_claim_from_entering_earlier_decisions():
    news=NewsIngress();h=story();news.ingest(h,now_ms=NOW+1000)
    assert news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW) is None
    assert news.candidate_risk('EURUSD',now_ms=NOW)==(Decimal('1'),Decimal('0'),())
    assert news.candidate_risk('EURUSD',now_ms=NOW+1000)[1]>0


def test_a_backdated_relay_stays_out_of_evidence_before_its_supplied_ingress_clock():
    news=NewsIngress();h=story();news.ingest(h,now_ms=NOW)
    news.ingest(story(source_id='backdated-relay'),now_ms=NOW+1000)
    impact=news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW)
    assert 'backdated-relay' not in impact.evidence_refs


def test_replaying_the_same_observation_cannot_move_its_original_ingress_clock_backwards():
    news=NewsIngress();h=story();news.ingest(h,now_ms=NOW+1000)
    news.ingest(h,now_ms=NOW)
    assert news.relayed_by(h.headline_id,as_of_ms=NOW)==()
    assert news.candidate_risk('EURUSD',now_ms=NOW)==(Decimal('1'),Decimal('0'),())


def test_report_cutoff_does_not_count_unavailable_headlines_or_impacts():
    news=NewsIngress();h=story();news.ingest(h,now_ms=NOW+1000)
    news.assess(h,subject_kind='POSITION',subject_id='p',symbol='EURUSD',now_ms=NOW+1000)
    before=news.report(now_ms=NOW)
    assert before['headlines']==0 and before['by_trust']=={} and before['impacts']==0
    after=news.report(now_ms=NOW+1000)
    assert after['headlines']==1 and after['impacts']==1
    assert after['provider_qualified'] is False and after['authority_effect']=='NONE'


def test_first_available_claim_keeps_its_terms_when_an_equal_time_relay_arrives():
    news=NewsIngress();h=story();news.ingest(h)
    news.ingest(story(source_id='alphabetically-earlier',trust=SourceTrust.UNTRUSTED))
    assert news.headlines(as_of_ms=NOW)==[h]


def test_an_earlier_observation_is_available_even_if_the_future_original_was_loaded_first():
    news=NewsIngress();news.ingest(story(observed_ms=NOW+1000))
    earlier=story(source_id='earlier',observed_ms=NOW)
    news.ingest(earlier)
    assert news.headlines(as_of_ms=NOW)==[earlier]
    assert news.candidate_risk('EURUSD',now_ms=NOW)[1]==Decimal('1')


@pytest.mark.parametrize('timestamp',[
    '2026-10-14T12:30:00', '2026-10-14T12:30:00.0000001Z',
])
def test_news_rows_share_the_exact_explicit_calendar_time_boundary(timestamp):
    with pytest.raises(ValueError):
        NewsIngress().headline_from_row(dict(source='publisher',title='Decision',published=timestamp))


@pytest.mark.parametrize('value',[True,1.5,-(2**63)-1])
def test_typed_headlines_require_exact_signed_millisecond_clocks(value):
    with pytest.raises(NewsIngressError):story(observed_ms=value)
