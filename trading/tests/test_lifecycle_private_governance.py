"""Internal commander owner integration adds no public/MCP action or authority."""
from contextlib import closing

from test_lifecycle_operational_grant import fixtures
from vati.core import Ledger
from commander.lifecycle_policies import LifecyclePolicyControls, LifecyclePolicySettings, qualification_reader


def test_internal_control_uses_original_ledger_and_exact_separate_verifiers(tmp_path):
    path=tmp_path/'private-grant.sqlite'
    with closing(Ledger(path)) as ledger:
        store,time,grant,qual,signatures,owner,token=fixtures(ledger)
        settings=LifecyclePolicySettings(str(path),store.owner,store.qualifier,store.clock)
        control=LifecyclePolicyControls(settings)
        receipt=control.admit(grant,qual,**signatures())
        assert receipt['state']=='ADMITTED' and receipt['native_qualification_issued'] is False
        assert receipt['estate_activation_performed'] is False
        assert receipt['public_action_binding']=='PROPOSED_UNADMITTED_NO_ROUTE_REGISTERED'
        observed=control.read(grant['grant_id'])
        assert observed['event_ref']==receipt['event_ref']
        assert observed['current_eligibility']=='CURRENT_SOURCE_BINDING_VERIFIED'
        assert 'owner_signature' not in observed and 'qualification_signature' not in observed
        time[0]=grant['expires_ms']
        expired=control.read(grant['grant_id'])
        assert expired['state']=='ADMITTED' and expired['current_eligibility']=='NOT_QUALIFIED'
        assert expired['event_ref']==receipt['event_ref']


def test_missing_independent_issuer_has_no_fallback_to_owner_trust(tmp_path):
    assert qualification_reader('') is None
    assert qualification_reader(str(tmp_path/'missing-issuer-registry.json')) is None
