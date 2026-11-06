"""Synthetic SOURCE fixtures, never native qualification or estate activation."""
from contextlib import closing
from copy import deepcopy
from decimal import Decimal as D

import pytest

from conftest_owner_authority import owner_keypair
from vati.authority import OwnerAuthorityVerifier, sign_token, OwnerAuthorityError
from vati.core import Ledger
from vati.core.canonical import canonical_hash
from vati.lifecycle.family_actions import number
from vati.risk.operational_grant import OperationalOptimizationGrants, PolicyAdmissionError, REQUIRED_GATES, subject

NOW=1_800_000_000_000


def fixtures(ledger):
    owner,owner_pem=owner_keypair();issuer,issuer_pem=owner_keypair()
    time=[NOW]
    store=OperationalOptimizationGrants(ledger,
        owner_authority=OwnerAuthorityVerifier({'synthetic-source-owner':owner_pem}),
        qualification_authority=OwnerAuthorityVerifier({'synthetic-independent-source-issuer':issuer_pem}),
        clock=lambda:time[0])
    scope=dict(environment='PAPER',account_alias='source-account',venue='paper',native_cohort='paper-hedged-v1',
        strategy_id='source-strategy',strategy_version='1',native_contract_refs=['source-contract'],
        native_capability_refs=['source-capability'])
    qualification=dict(policy_id='family-partial-reduction',policy_version='PROPORTIONAL_FLOOR_V1',
        policy_hash='source-policy-hash',scope=scope,source_hash='source-revision',
        evidence_refs=['synthetic-source-only-evidence'],gates={g:True for g in REQUIRED_GATES},
        issued_ms=NOW,expires_ms=NOW+60000,issuer_key_id='synthetic-independent-source-issuer',evidence_domain='SOURCE',
        operations=['PARTIAL_CLOSE'],max_requested_quantity=number(D('.04')),max_family_risk_pct=number(D('.004')))
    grant=dict(grant_id='source-grant',policy_id=qualification['policy_id'],policy_version=qualification['policy_version'],
        policy_hash=qualification['policy_hash'],scope=scope,operations=['PARTIAL_CLOSE'],
        max_requested_quantity=number(D('.04')),max_family_risk_pct=number(D('.004')),
        qualification_hash=canonical_hash(qualification),source_hash=qualification['source_hash'],
        evidence_refs=qualification['evidence_refs'],activated_ms=NOW,expires_ms=NOW+60000,
        parent_migration={'mode':'EXPLICIT_ORIGINAL_PARENTS','original_family_revisions':['original-family']},
        lease_epoch=7,fence_ref='source-fence',issuer_key_id=qualification['issuer_key_id'],owner_key_id='synthetic-source-owner')
    def token(key,act,body,kid):
        return sign_token(key,act=act,subject=subject(body),key_id=kid,
            issued_at_unix=NOW//1000,lifetime_seconds=120)
    def signatures(g=grant,q=qualification):
        return dict(owner_signature=token(owner,'lifecycle-policy-grant',g,grant['owner_key_id']),
            qualification_signature=token(issuer,'lifecycle-policy-qualify',q,qualification['issuer_key_id']))
    return store,time,grant,qualification,signatures,owner,token


def test_synthetic_source_admission_exact_readback_restart_and_expiry(tmp_path):
    with closing(Ledger(tmp_path/'grant.sqlite')) as ledger:
        store,time,grant,qualification,signatures,owner,token=fixtures(ledger)
        sig=signatures();admitted=store.admit(grant,qualification,**sig)
        assert store.admit(grant,qualification,**sig).hash==admitted.hash
        assert store.current(grant['grant_id'],expected_ref=admitted.hash).hash==admitted.hash
        with closing(Ledger(ledger.path)) as cold:
            restarted=OperationalOptimizationGrants(cold,owner_authority=store.owner,
                qualification_authority=store.qualifier,clock=store.clock)
            assert restarted.current(grant['grant_id'],expected_ref=admitted.hash).hash==admitted.hash
        time[0]=grant['expires_ms']
        with pytest.raises(PolicyAdmissionError,match='activation'):
            store.current(grant['grant_id'],expected_ref=admitted.hash)


@pytest.mark.parametrize('damage',['missing-issuer','signature','scope','native','gates','same-key','owner'])
def test_no_boolean_or_self_signed_or_wrong_scope_qualification_can_admit(tmp_path,damage):
    with closing(Ledger(tmp_path/'grant.sqlite')) as ledger:
        store,time,grant,qualification,signatures,owner,token=fixtures(ledger)
        sig=signatures()
        if damage=='missing-issuer':store.qualifier=None
        elif damage=='signature':sig['qualification_signature']='synthetic-ref-is-not-a-signature'
        elif damage=='scope':grant['scope']=dict(grant['scope'],account_alias='foreign-account')
        elif damage=='native':grant['scope']=dict(grant['scope'],environment='LIVE')
        elif damage=='gates':qualification['gates']=dict(qualification['gates'],unknown_effect=False)
        elif damage=='owner':sig['owner_signature']='signed-by-owner'
        else:
            store.qualifier=OwnerAuthorityVerifier({qualification['issuer_key_id']:store.owner.keys[grant['owner_key_id']]})
            sig['qualification_signature']=token(owner,'lifecycle-policy-qualify',qualification,qualification['issuer_key_id'])
        with pytest.raises((PolicyAdmissionError,OwnerAuthorityError)):
            store.admit(grant,qualification,**sig)
        assert store.latest(grant['grant_id']) is None


def test_revoke_is_current_owner_signed_cas_and_never_readmits_original(tmp_path):
    with closing(Ledger(tmp_path/'grant.sqlite')) as ledger:
        store,time,grant,qualification,signatures,owner,token=fixtures(ledger)
        sig=signatures();admitted=store.admit(grant,qualification,**sig)
        body={'grant_id':grant['grant_id'],'expected_ref':admitted.hash}
        revoke=token(owner,'lifecycle-policy-revoke',body,grant['owner_key_id'])
        revoked=store.revoke(grant['grant_id'],expected_ref=admitted.hash,owner_signature=revoke)
        assert revoked.payload['revision']==2
        with pytest.raises(PolicyAdmissionError,match='revoked'):
            store.current(grant['grant_id'],expected_ref=admitted.hash)
        with pytest.raises(PolicyAdmissionError,match='revoked'):
            store.admit(grant,qualification,**sig)
        with pytest.raises(PolicyAdmissionError,match='compare-and-swap'):
            store.revoke(grant['grant_id'],expected_ref=admitted.hash,owner_signature=revoke)


def test_last_fence_read_expiry_and_signer_revocation_prevent_new_effect(tmp_path):
    with closing(Ledger(tmp_path/'grant.sqlite')) as ledger:
        store,time,grant,qualification,signatures,owner,token=fixtures(ledger)
        admitted=store.admit(grant,qualification,**signatures());effects=[]
        def fence(epoch):time[0]=grant['expires_ms'];return epoch==7
        with pytest.raises(PolicyAdmissionError):
            with store.effect_guard(grant['grant_id'],expected_ref=admitted.hash,
                    lease_epoch=7,fence_ref='source-fence',lease_fence=fence):effects.append('send')
        assert effects==[]
        time[0]=NOW;store.owner.revoked_key_ids=frozenset({grant['owner_key_id']})
        with pytest.raises(OwnerAuthorityError):
            with store.effect_guard(grant['grant_id'],expected_ref=admitted.hash,
                    lease_epoch=7,fence_ref='source-fence',lease_fence=lambda e:True):effects.append('send')
        assert effects==[]


@pytest.mark.parametrize('change',['quantity','risk','operation','backdated-activation'])
def test_owner_signature_cannot_enlarge_independent_qualification_bounds(tmp_path,change):
    with closing(Ledger(tmp_path/'bounds.sqlite')) as ledger:
        store,time,grant,qualification,signatures,owner,token=fixtures(ledger)
        if change=='quantity':grant['max_requested_quantity']=number(D('.05'))
        elif change=='risk':grant['max_family_risk_pct']=number(D('.005'))
        elif change=='operation':grant['operations'].append('FULL_CLOSE')
        else:grant['activated_ms']-=1000
        with pytest.raises(PolicyAdmissionError):store.admit(grant,qualification,**signatures(grant,qualification))
        assert store.latest(grant['grant_id']) is None
