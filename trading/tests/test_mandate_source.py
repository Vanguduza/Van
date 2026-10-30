"""Original signed policy stays data across expiry, rotation and tampering."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as N
import json

import pytest

from conftest import NOW, mandate_dict
from test_native_risk_history_inputs import native_facts, record
from vati.core.canonical import canonical_hash, canonical_json
from vati.core import Ledger
from vati.core import EventKind
from vati.risk import TradingMandate
from vati.risk.mandate_source import capture_mandate_source, original_native_risk_mandate, validate_mandate_source
from vati.risk.native_history import original_native_risk_input, native_risk_history_for_context


def original(tmp_path,eurusd,*,damage=None):
    ledger,adapter,account,_,facts=native_facts(tmp_path,eurusd)
    raw=mandate_dict(account_alias=facts.account_alias,venue=facts.symbol_contract.venue)
    mandate=TradingMandate.from_mapping(raw)
    source=capture_mandate_source(mandate,raw,now_ms=NOW*1000)
    assert source['state']=='ORIGINAL_BOUND',source
    def attach(p):
        p['inputs']['original_mandate_source']=deepcopy(source)
        if damage is not None:damage(p)
    event=record(ledger,facts,grant=raw,damage=attach)
    return ledger,mandate,raw,event,facts,source


def test_actual_signed_original_policy_survives_sql_reopen_and_expiry_as_data(tmp_path,eurusd):
    ledger,mandate,raw,event,facts,source=original(tmp_path,eurusd)
    count=ledger.count();reopened=Ledger(ledger.path)
    try:
        body=original_native_risk_mandate(reopened,event.hash,available_at_ms=(NOW+100*86400)*1000)
        assert body['state']=='ORIGINAL_BOUND' and body['origin_alias']==facts.account_alias
        assert body['mandate_hash']==event.payload['decision']['mandate_hash']
        assert body['execution_authority'] is body['current_policy_qualified'] is False
        assert body['effective_policy']['max_open_stop_risk']==str(mandate.max_open_stop_risk)
        assert body['physical_account_key']==facts.native_account_context.physical_account_key
        assert ledger.count()==count and ledger.verify_chain()[0]
        original_policy=validate_mandate_source(source,decision_time_ms=NOW*1000)
        assert not isinstance(original_policy,TradingMandate)
        assert not hasattr(original_policy,'_verified_owner_key_bindings')
        changed=original_policy.body();changed['max_open_stop_risk']='0.50'
        assert original_policy.body()['max_open_stop_risk']==str(mandate.max_open_stop_risk)
    finally:reopened.close()


def test_legacy_unbound_policy_keeps_its_original_native_financial_history(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);event=record(ledger,facts)
    result=original_native_risk_mandate(ledger,event.hash,available_at_ms=NOW*1000)
    assert result['state']=='UNBOUND' and result['effective_policy'] is None
    assert original_native_risk_input(ledger,event.hash,available_at_ms=NOW*1000).event_ref==event.hash
    assert event.hash in {r.event_ref for r in native_risk_history_for_context(ledger,facts.native_account_context,available_at_ms=NOW*1000).original_inputs}


@pytest.mark.parametrize('damage_kind',['policy','policy_resealed','other_alias','other_venue',
    'signature','key_fingerprint','wrong_act','wrong_reference','authority_flag','missing_profile','captured_future'])
def test_resealed_unsigned_envelopes_do_not_bind_a_changed_original_policy(tmp_path,eurusd,damage_kind):
    def damage(p):
        s=p['inputs']['original_mandate_source'];body=s['effective_policy'];proof=s['authorities'][0]
        if damage_kind in {'policy','policy_resealed'}:body['max_open_stop_risk']='0.04'
        elif damage_kind=='other_alias':body['account_alias']='another-account'
        elif damage_kind=='other_venue':body['venue']='ctrader'
        elif damage_kind=='signature':
            from vati.authority import _b64u,_unb64u
            parts=proof['token'].split('.');sig=_unb64u(parts[2]);parts[2]=_b64u(sig[:-1]+bytes([sig[-1]^1]));proof['token']='.'.join(parts)
        elif damage_kind=='key_fingerprint':proof['public_key_sha256']='0'*64
        elif damage_kind=='wrong_act':proof['verified_authority']['act']='drawdown-resume'
        elif damage_kind=='wrong_reference':body['owner_signature_ref']='owner-authority:substituted:nonce'
        elif damage_kind=='authority_flag':s['execution_authority']=True
        elif damage_kind=='missing_profile':body['temperament_owner_signature_ref']='owner-authority:missing:profile'
        elif damage_kind=='captured_future':s['captured_at_ms']+=1
        if damage_kind in {'policy_resealed','other_alias','other_venue','wrong_reference','missing_profile'}:
            s['mandate_hash']=canonical_hash(body)
            p['decision']['mandate_hash']=s['mandate_hash']
            p['decision']['decision_hash']=canonical_hash({k:v for k,v in p['decision'].items() if k!='decision_hash'})
    ledger,_,_,event,facts,_=original(tmp_path,eurusd,damage=damage)
    result=original_native_risk_mandate(ledger,event.hash,available_at_ms=NOW*1000)
    assert result['state']=='UNBOUND' and result['effective_policy'] is None
    assert result['execution_authority'] is False
    assert original_native_risk_input(ledger,event.hash,available_at_ms=NOW*1000).event_ref==event.hash


def test_capture_cannot_copy_a_drifted_or_unadmitted_policy_into_original_authority(tmp_path,eurusd):
    _,mandate,raw,_,_,_=original(tmp_path,eurusd)
    drifted=dict(raw,max_open_stop_risk='0.04')
    assert capture_mandate_source(mandate,drifted,now_ms=NOW*1000)['state']=='UNAVAILABLE'
    assert capture_mandate_source(replace(mandate,max_open_stop_risk=mandate.max_open_stop_risk),raw,now_ms=NOW*1000)['state']=='UNAVAILABLE'
    assert capture_mandate_source(mandate,raw,now_ms=mandate.expires_at_unix*1000)['state']=='UNAVAILABLE'


@pytest.mark.parametrize('change',['rotation','removal','revocation'])
def test_original_verified_policy_is_readable_after_current_key_change_without_new_authority(tmp_path,eurusd,change):
    from conftest_owner_authority import OwnerAuthorityHarness,OWNER_KEY_ID,owner_keypair
    from vati.risk.mandate import mandate_subject
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    owner=OwnerAuthorityHarness();raw=mandate_dict(account_alias=facts.account_alias,venue=facts.symbol_contract.venue)
    raw['owner_signature_ref']=owner.token(act='mandate-admit',subject=mandate_subject(raw),
        issued_at_unix=raw['signed_at_unix'],lifetime_seconds=raw['expires_at_unix']-raw['signed_at_unix'])
    mandate=TradingMandate.from_mapping(raw,authority=owner.verifier)
    source=capture_mandate_source(mandate,raw,now_ms=NOW*1000)
    assert source['state']=='ORIGINAL_BOUND'
    # Record through the real kernel with the same independently verified key.
    from vati.risk import RiskAuthority
    from conftest import intent
    from vati.core import make_event
    from vati.risk.serde import intent_to_dict,snapshot_to_dict
    trade=intent(account_alias=facts.account_alias,venue=facts.symbol_contract.venue)
    decision=RiskAuthority(mandate).evaluate_safe(trade,facts)
    event=make_event(EventKind.RISK_DECISION,'vati-cycle',{'inputs':{'intent':intent_to_dict(trade),
        'snapshot':snapshot_to_dict(facts),'mandate':raw,'original_mandate_source':source},
        'decision':decision.to_dict()},event_time_ms=NOW*1000,received_time_ms=NOW*1000,correlation_id=trade.trade_intent_id)
    ledger.append(event)
    if change=='rotation':owner.verifier.keys[OWNER_KEY_ID]=owner_keypair()[1]
    elif change=='removal':owner.verifier.keys.clear()
    else:owner.verifier.revoked_key_ids=frozenset({OWNER_KEY_ID})
    assert not mandate.owner_keys_current()
    assert capture_mandate_source(mandate,raw,now_ms=NOW*1000)['state']=='UNAVAILABLE'
    restored=original_native_risk_mandate(ledger,event.hash,available_at_ms=(NOW+100*86400)*1000)
    assert restored['state']=='ORIGINAL_BOUND' and restored['execution_authority'] is False
    assert restored['effective_policy']==source['effective_policy']
    assert RiskAuthority(mandate).evaluate_safe(trade,facts).decision.value=='REJECTED'


def test_temperament_retains_both_separately_verified_original_grants(tmp_path,eurusd):
    from conftest import owner_authority
    from vati.risk.mandate import trading_temperament_subject
    raw=mandate_dict(trading_temperament='NORMAL')
    raw['temperament_owner_signature_ref']=owner_authority().token(act='trading-temperament-admit',
        subject=trading_temperament_subject(raw),issued_at_unix=raw['signed_at_unix'],
        lifetime_seconds=raw['expires_at_unix']-raw['signed_at_unix'])
    mandate=TradingMandate.from_mapping(raw)
    source=capture_mandate_source(mandate,raw,now_ms=NOW*1000)
    assert source['state']=='ORIGINAL_BOUND' and len(source['authorities'])==2
    assert validate_mandate_source(source,decision_time_ms=NOW*1000).body()['temperament_owner_signature_ref']==mandate.temperament_owner_signature_ref
    source['authorities'].pop()
    with pytest.raises(ValueError,match='authority count'):validate_mandate_source(source,decision_time_ms=NOW*1000)


@pytest.mark.parametrize('producer',['single','account'])
def test_actual_risk_producer_archives_the_policy_that_the_real_kernel_used(tmp_path,eurusd,monkeypatch,producer):
    from conftest import intent
    from vati.risk import RiskAuthority
    ledger,adapter,account,_,facts=native_facts(tmp_path,eurusd)
    raw=mandate_dict(account_alias=facts.account_alias,venue=facts.symbol_contract.venue,mode='OBSERVE')
    mandate=TradingMandate.from_mapping(raw)
    trade=intent(account_alias=facts.account_alias,venue=facts.symbol_contract.venue)
    if producer=='account':
        from vati.app.account_service import AccountCoordinatorService
        service=AccountCoordinatorService.__new__(AccountCoordinatorService)
        service.authority=RiskAuthority(mandate);service.mandate=mandate;service.adapter=adapter
        service.cfg=N(mandate=raw);service._ledger=ledger;service.clock=lambda:NOW*1000;service.cognition=None
        decision=service._risk(trade,facts)
        assert decision.decision.value=='REJECTED'
    else:
        from test_physical_native_controls import cycle
        import vati.app.cycle as cycle_module
        service=cycle(ledger,adapter,account,facts)
        service.cfg=replace(service.cfg,mandate_dict=raw,warmup_bars=0)
        service.authority=RiskAuthority(mandate)
        state=N(as_of_ms=NOW*1000,state_hash='source-fixture',quote_age_ms=0,
            regime=N(trend=N(value='RANGING')),as_dict=lambda:{'source_fixture':True})
        monkeypatch.setattr(cycle_module,'build_market_state',lambda **_:state)
        service.ctx_fn=lambda *args:N(zse=None)
        service.engine=N(assess=lambda *args,**kw:N(intent=trade,decision='TRADE',abstain_reason='',candidates=(),assessment_hash='source-fixture'))
        service.snapshot=lambda **_:facts
        outcome=service.step([],now_ms=NOW*1000,last_quote_ms=NOW*1000)
        assert outcome.decision.startswith('REJECTED:')
    events=list(ledger.iter(EventKind.RISK_DECISION));assert len(events)==1
    result=original_native_risk_mandate(ledger,events[0].hash,available_at_ms=NOW*1000)
    assert result['state']=='ORIGINAL_BOUND'
    assert result['mandate_hash']==events[0].payload['decision']['mandate_hash']
    assert result['execution_authority'] is result['current_policy_qualified'] is False
    assert ledger.count(EventKind.ORDER_COMMAND)==0


def test_actual_account_positive_approval_also_preserves_its_original_policy(tmp_path,eurusd):
    from conftest import intent
    from vati.app.account_service import AccountCoordinatorService
    from vati.risk import RiskAuthority
    ledger,adapter,_,_,facts=native_facts(tmp_path,eurusd)
    raw=mandate_dict(account_alias=facts.account_alias,venue=facts.symbol_contract.venue)
    mandate=TradingMandate.from_mapping(raw)
    service=AccountCoordinatorService.__new__(AccountCoordinatorService)
    service.authority=RiskAuthority(mandate);service.mandate=mandate;service.adapter=adapter
    service.cfg=N(mandate=raw);service._ledger=ledger;service.clock=lambda:NOW*1000;service.cognition=None
    result=service._risk(intent(account_alias=facts.account_alias,venue=facts.symbol_contract.venue),facts)
    assert result.decision.value in {'APPROVED','REDUCED'}
    event=next(ledger.iter(EventKind.RISK_DECISION))
    original=original_native_risk_mandate(ledger,event.hash,available_at_ms=NOW*1000)
    assert original['state']=='ORIGINAL_BOUND' and original['mandate_hash']==result.mandate_hash
    assert original['execution_authority'] is False and ledger.count(EventKind.ORDER_COMMAND)==0
