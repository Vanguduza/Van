"""Real source fixture signatures preserve the native direct-control API.

All keys are isolated test data, never the owner's production/device keys.
"""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW
from conftest_owner_authority import OwnerAuthorityHarness
from test_recoverable_lockouts import _cycle
from test_native_risk_history_inputs import native_facts
from test_native_risk_history_index import other_context
from test_physical_financial_history import approval, close
from test_physical_baselines import legacy
from vati.core import EventKind, make_event
from vati.execution.base import Health
from vati.risk.lockouts import ACCOUNT_SCOPE, LockoutPolicy
from vati.risk.physical_runtime import PhysicalRiskRuntime
from vati.risk.physical_history import physical_financial_history


def cycle(ledger,adapter,account,facts):
    c=_cycle(facts.symbol_contract,ledger)
    c.cfg=replace(c.cfg,account_alias=facts.account_alias,venue=adapter.venue,
        contract=facts.symbol_contract)
    c.adapter=adapter
    adapter.sync_account=lambda:account
    adapter.heartbeat=lambda **_:Health(True,0,NOW*1000)
    adapter.positions=lambda:[]
    state=PhysicalRiskRuntime(ledger,facts.native_account_context,LockoutPolicy(5),now_ms=NOW*1000)
    c._physical_risk_runtime=state;c.streaks=state.streaks
    c.peak_equity=state.book.projection(NOW*1000).peak or account.equity
    return c


def test_actual_direct_native_reset_preserves_other_alias_loss_and_archives_original_proof(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    first=approval(ledger,a,'a-loss');close(ledger,first,alias=a.account_alias)
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    second=approval(ledger,b,'b-loss');close(ledger,second,alias=b.account_alias)
    current=replace(account,account_alias=b.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=b.account_alias))
    c=cycle(ledger,adapter,current,b);owner=OwnerAuthorityHarness()
    token=owner.token(act='loss-streak-reset',subject=b.account_alias+':'+ACCOUNT_SCOPE,issued_at_unix=NOW)
    c.reset_loss_streak(ACCOUNT_SCOPE,owner_signature_ref=token,authority=owner.verifier,now_ms=NOW*1000)
    assert c.streaks._scopes[ACCOUNT_SCOPE].losses==1
    assert c.streaks.original_contributors(ACCOUNT_SCOPE)==(a.account_alias,)
    history=physical_financial_history(ledger,b.native_account_context,available_at_ms=(NOW+3600)*1000)
    assert not history.issue
    controls=[f for f in history.facts if f.kind=='SESSION']
    assert len(controls)==1 and controls[0].payload['original_owner_control']['token']==token
    assert ledger.count(EventKind.ORDER_COMMAND)==0


def test_actual_direct_drawdown_resume_only_releases_its_original_alias_peak(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    legacy(ledger,a,'a-original','15000')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    legacy(ledger,b,'b-original','13000')
    current=replace(account,account_alias=b.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=b.account_alias))
    c=cycle(ledger,adapter,current,b);owner=OwnerAuthorityHarness()
    token=owner.token(act='drawdown-resume',subject=b.account_alias,issued_at_unix=NOW)
    c.resume_after_drawdown(owner_signature_ref=token,authority=owner.verifier,now_ms=NOW*1000)
    assert c.peak_equity==D('15000')
    assert c._physical_risk_runtime.book.origins[b.account_alias].peak==current.equity
    assert not c.streaks.recovery_issue


def test_direct_native_control_cannot_be_reapplied_after_verifier_restart(tmp_path,eurusd):
    from vati.authority import OwnerAuthorityVerifier
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    c=cycle(ledger,adapter,account,a);owner=OwnerAuthorityHarness()
    token=owner.token(act='loss-streak-reset',subject=a.account_alias+':'+ACCOUNT_SCOPE,issued_at_unix=NOW)
    c.reset_loss_streak(ACCOUNT_SCOPE,owner_signature_ref=token,authority=owner.verifier,now_ms=NOW*1000)
    before=ledger.count()
    fresh=OwnerAuthorityVerifier(owner.verifier.keys)
    with pytest.raises(ValueError,match='already applied'):
        c.reset_loss_streak(ACCOUNT_SCOPE,owner_signature_ref=token,authority=fresh,now_ms=NOW*1000)
    assert ledger.count()==before


def test_native_control_missing_original_source_refuses_without_effect(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    c=cycle(ledger,adapter,account,a);owner=OwnerAuthorityHarness()
    adapter.sync_account=lambda:replace(account,funding_mark=None)
    token=owner.token(act='loss-streak-reset',subject=a.account_alias+':'+ACCOUNT_SCOPE,issued_at_unix=NOW)
    before=ledger.count(EventKind.SESSION)
    with pytest.raises(ValueError,match='source unavailable'):
        c.reset_loss_streak(ACCOUNT_SCOPE,owner_signature_ref=token,authority=owner.verifier,now_ms=NOW*1000)
    assert ledger.count(EventKind.SESSION)==before


@pytest.mark.parametrize('change',['expiry','revocation'])
def test_direct_native_control_rechecks_authority_inside_actual_sql_writer(tmp_path,eurusd,change,monkeypatch):
    from contextlib import contextmanager
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    c=cycle(ledger,adapter,account,a);owner=OwnerAuthorityHarness()
    token=owner.token(act='loss-streak-reset',subject=a.account_alias+':'+ACCOUNT_SCOPE,
        issued_at_unix=NOW,lifetime_seconds=60)
    clock={'ms':NOW*1000};c._lease_clock=lambda:clock['ms']
    atomic=ledger.atomic
    metadata=c._direct_native_control_metadata
    armed={'ready':False}
    def prepared(*args,**kwargs):
        result=metadata(*args,**kwargs)
        armed['ready']=True
        return result
    monkeypatch.setattr(c,'_direct_native_control_metadata',prepared)
    @contextmanager
    def delayed_writer():
        with atomic():
            if armed['ready']:
                if change=='expiry':clock['ms']+=61000
                else:owner.verifier.keys.clear()
            yield
    monkeypatch.setattr(ledger,'atomic',delayed_writer)
    before=ledger.count(EventKind.SESSION)
    with pytest.raises(ValueError,match='expired or its original issuer changed'):
        c.reset_loss_streak(ACCOUNT_SCOPE,owner_signature_ref=token,authority=owner.verifier,now_ms=NOW*1000)
    assert ledger.count(EventKind.SESSION)==before


@pytest.mark.parametrize('damage',['signature','subject','key','duplicate'])
def test_original_direct_control_corruption_or_duplicate_remains_unresolved(tmp_path,eurusd,damage):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    c=cycle(ledger,adapter,account,a);owner=OwnerAuthorityHarness()
    token=owner.token(act='loss-streak-reset',subject=a.account_alias+':'+ACCOUNT_SCOPE,issued_at_unix=NOW)
    c.reset_loss_streak(ACCOUNT_SCOPE,owner_signature_ref=token,authority=owner.verifier,now_ms=NOW*1000)
    original=next(e for e in ledger.iter(EventKind.SESSION) if e.payload.get('original_owner_control'))
    p=original.payload
    if damage=='signature':
        parts=token.split('.');parts[2]='AAAA';p['owner_signature_ref']=p['original_owner_control']['token']='.'.join(parts)
    elif damage=='subject':p['scope']='other-strategy'
    elif damage=='key':p['original_owner_control']['public_key_sha256']='0'*64
    bad=make_event(EventKind.SESSION,'vati-cycle',p,event_time_ms=NOW*1000+1,
        received_time_ms=NOW*1000+1)
    ledger.append(bad)
    history=physical_financial_history(ledger,a.native_account_context,available_at_ms=NOW*1000+1)
    assert bad.hash in history.unresolved_refs and history.issue
    if damage=='duplicate':
        assert original.hash in history.unresolved_refs
        assert not [f for f in history.facts if f.kind=='SESSION']
