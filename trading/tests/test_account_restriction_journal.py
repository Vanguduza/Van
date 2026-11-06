"""PAPER metadata and in-memory journal only; no provider or credentials."""
from dataclasses import replace

import pytest

import json
import copy
from commander.account_effects import AccountEffectIntent, AccountEffectJournal, AccountEffectConflict, AccountEffectUnknown, AccountEffectAuthorityExpired, JOURNALED_COMMANDS, PRODUCER, SCHEMA
from vati.accounts import Account, AccountRegistry
from vati.accounts.resource_version import resource_snapshot
from vati.accounts.restrictions import initial_record, transition_record, public_record
from vati.core.canonical import canonical_hash
from vati.core.ledger import Ledger
from vati.core.events import EventKind, make_event


def seal_admission(admission, *, before=None, related=()):
    context=admission['context'];request=admission['native_request']
    view={'alias':context['alias'],'owner_device_id':admission['device_id'],
        'account_control_domain':context['account_control_domain'],'restriction_id':context['restriction_id'],
        'incarnation':context['incarnation'],'expected_revision':context['expected_revision'],
        'expected_digest':context['expected_digest'],'reason_code':context['reason_code'],'before':before,
        'enabled':before is None,'mode':'OBSERVE','mode_or_mandate_granted':False,'entry_permitted':False,
        'protective_exits_preserved':True,'native_identity_required':request['variant']=='COMPLETE_REAUTH',
        'native_identity_scope_ref':'7'*64 if request['variant']=='COMPLETE_REAUTH' else None,
        'parent_admission_digest':context['parent_admission_digest'],'related_operations':list(related)}
    body={'schema':'vati.account-restriction-review/1','semantic_digest':context['semantic_digest'],
          'resource_version':context['resource_version'],'view':view}
    body['context_digest']=canonical_hash(body);body['request_digest']=canonical_hash(request)
    body['review_digest']=canonical_hash(body);context['review_digest']=body['context_digest']
    admission['native_review']=body;admission['native_review_digest']=body['review_digest']
    admission['approval_parameters_digest']=canonical_hash({'restriction_review':body,'native_request':request,
                                                              'reauth_fact_digest':admission['reauth_fact_digest']})
    admission['request_digest']=canonical_hash({'context':context,'fact_id':admission['reauth_fact_id'],
        'challenge_id':admission['operation_id'],'text_digest':admission['approval_text_digest'],
        'parameters_digest':admission['approval_parameters_digest']})
    admission['admission_digest']=canonical_hash({k:v for k,v in admission.items() if k!='admission_digest'})
    return admission


def test_restriction_is_registered_without_removing_existing_journal_commands():
    assert JOURNALED_COMMANDS=={'account_upsert','account_credentials','account_remove','mt5_ea_issue_key','deriv_create_demo','account_restrict'}


def metadata_child_admission(op_id,parent,original_admission,request,refs):
    context={'alias':'paper','original_device_id':'device','resource_version':parent.resource_version,
             'account_control_domain':'d'*64,'incarnation':parent.resource_version,'variant':'RECONCILE_DATA',
             'expected_revision':0,'expected_digest':None,'restriction_id':parent.operation_id,
             'review_digest':'a'*64,'semantic_digest':canonical_hash({k:v for k,v in request.items() if k not in {'reauth_fact_id','reauth_fact_digest'}}),
             'reason_code':'OWNER_REQUEST','parent_operation_id':parent.operation_id,
             'parent_admission_digest':original_admission['admission_digest']}
    admission={'schema':'van.account-restriction-admission/1','action':'account_restrict',
        'purpose':'ACCOUNT_RESTRICTION_CONTROL','owner_id':'owner','device_id':'device','operation_id':op_id,
        'native_request':request,'authority_ref':'b'*64,'context':context,
        'reauth_purpose':'ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA','actor_key_ref':'c'*64,'request_digest':None,
        'reauth_fact_digest':request['reauth_fact_digest'],'reauth_proof_ref':'5'*64,'created_at_unix':2,'expires_at_unix':1000,
        'approval_text_digest':'f'*64,'approval_parameters_digest':'9'*64,'native_review_digest':'6'*64,
        'reauth_fact_id':request['reauth_fact_id'],'state':'ADMITTED_NOT_NATIVE_COMPLETION'}
    return seal_admission(admission,related=refs)


def fixture(tmp_path, applied=False, uncertain=True):
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='paper',broker='PAPER',mode='OBSERVE',currency='USD'))
    version=resource_snapshot(registry,'paper')['resource_version']
    domain='d'*64; parent_id='parent_operation_123456789';child_id='child_operation_1234567890'
    original={'alias':'paper','variant':'RESTRICT','reason_code':'OWNER_REQUEST'}
    parent=AccountEffectIntent(parent_id,'device','b'*64+'::review:'+'6'*64,'account_restrict',
        ('account:paper','account-control-domain:'+domain),canonical_hash(original),version,1000)
    context={'alias':'paper','original_device_id':'device','resource_version':version,
             'account_control_domain':domain,'incarnation':version,'variant':'RESTRICT',
             'expected_revision':0,'expected_digest':None,'restriction_id':'proposed:'+version,
             'review_digest':'a'*64,'semantic_digest':canonical_hash(original),'reason_code':'OWNER_REQUEST',
             'parent_operation_id':None,'parent_admission_digest':None}
    admission={'schema':'van.account-restriction-admission/1','action':'account_restrict',
        'purpose':'ACCOUNT_RESTRICTION_CONTROL','owner_id':'owner','device_id':'device','operation_id':parent_id,
        'native_request':original,'authority_ref':'b'*64,'context':context,'reauth_purpose':None,
        'actor_key_ref':'c'*64,'request_digest':None,'reauth_fact_digest':None,'reauth_proof_ref':None,
        'created_at_unix':1,'expires_at_unix':1000,'approval_text_digest':'f'*64,
        'approval_parameters_digest':'9'*64,'native_review_digest':'6'*64,'reauth_fact_id':None,'state':'ADMITTED_NOT_NATIVE_COMPLETION'}
    seal_admission(admission)
    parent=replace(parent,authority_ref=admission['authority_ref']+'::review:'+admission['native_review_digest'])
    ledger=Ledger();journal=AccountEffectJournal(ledger)
    claimed=journal.claim(parent,now_unix=1)
    if uncertain:journal.uncertain(claimed,now_unix=2)
    if applied:
        def create(current):
            current.accounts['paper']=replace(current.accounts['paper'],enabled=False)
            current._restrictions['paper']=initial_record(alias='paper',operation_id=parent_id,device_id='device',
                domain=domain,resource_version=version,request_digest=parent.request_digest,review_digest=context['review_digest'],
                admission_digest=admission['admission_digest'],reason_code='OWNER_REQUEST',now=2)
        registry.restriction_update('paper',create)
        registry=AccountRegistry(registry.path)
    row=registry._restrictions.get('paper')
    request={'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':parent_id,
             'restriction_id':row['restriction_id'] if row else parent_id,'expected_revision':row['revision'] if row else 0}
    if row:request['expected_digest']=canonical_hash(row)
    current=resource_snapshot(registry,'paper')['resource_version']
    child=AccountEffectIntent(child_id,'device','new-proof','account_restrict',parent.targets,canonical_hash(request),current,1000)
    def qualify(**changes):
        values={'parent_operation_id':parent_id,'child_request':request,'original_request':original,
                'original_admission':admission,'expected_admission_digest':admission['admission_digest'],
                'registry':registry,'current_resource_version':current,
                'expected_operation_refs':journal.restriction_operation_refs(parent_id,admission)}
        values.update(changes)
        return journal.qualify_restriction_resolution(child,**values)
    return journal,parent,child,qualify,request,admission,ledger


@pytest.mark.parametrize('applied',[False,True])
def test_resolution_preserves_original_unknown_and_supports_both_observations(tmp_path,applied):
    journal,parent,child,qualify,request,admission,ledger=fixture(tmp_path,applied)
    qualified=qualify()
    assert qualified.summary['outcome']==('TRANSITION_OBSERVED' if applied else 'CURRENT_PREIMAGE_OBSERVED')
    claim=journal.claim_restriction_resolution(child,qualified,now_unix=3)
    result=journal.append_restriction_resolution(claim,qualify(),now_unix=4,clock=lambda:4)
    assert result['outcome']==qualified.summary['outcome']
    journal.uncertain(claim,now_unix=5)
    assert journal.status(parent.operation_id,'device').phase=='UNKNOWN'
    assert journal.status(parent.operation_id,'device').result is None
    journal.require_clear_targets(parent.targets)
    assert journal.restriction_resolution(parent.operation_id,'device')==result
    with pytest.raises(AccountEffectConflict):qualify()
    with pytest.raises(AccountEffectConflict):journal.restriction_resolution(parent.operation_id,'other-device')
    assert len(journal.business_events())==4
    ledger.close()


def test_late_parent_unknown_keeps_prior_resolution_valid(tmp_path):
    journal,parent,child,qualify,_,_,ledger=fixture(tmp_path,uncertain=False)
    original=journal.status(parent.operation_id,'device')
    claim=journal.claim_restriction_resolution(child,qualify(),now_unix=3)
    journal.append_restriction_resolution(claim,qualify(),now_unix=4,clock=lambda:4)
    journal.uncertain(original,now_unix=5)
    assert journal.status(parent.operation_id,'device').phase=='UNKNOWN'
    assert journal.restriction_resolution(parent.operation_id,'device')['outcome']=='CURRENT_PREIMAGE_OBSERVED'
    ledger.close()


def test_parent_event_change_after_review_requires_fresh_refs(tmp_path):
    journal,parent,child,qualify,_,_,ledger=fixture(tmp_path,uncertain=False)
    original=journal.status(parent.operation_id,'device');q=qualify()
    journal.uncertain(original,now_unix=2)
    with pytest.raises(AccountEffectConflict):journal.claim_restriction_resolution(child,q,now_unix=3)
    ledger.close()


def test_unlisted_unknown_and_transplanted_review_refs_fail_closed(tmp_path):
    journal,parent,child,qualify,_,admission,ledger=fixture(tmp_path)
    refs=journal.restriction_operation_refs(parent.operation_id,admission)
    with pytest.raises(AccountEffectConflict):qualify(expected_operation_refs=[{**refs[0],'event_ref':'0'*64}])
    other=replace(parent,operation_id='unrelated_restriction_123456',request_digest='8'*64)
    journal._append(other,'IN_FLIGHT','',now=2)
    with pytest.raises(AccountEffectConflict):journal.claim_restriction_resolution(child,qualify(),now_unix=3)
    ledger.close()


def test_authority_expiry_after_final_writer_callback_refuses_append(tmp_path):
    journal,parent,child,qualify,_,_,ledger=fixture(tmp_path)
    claim=journal.claim_restriction_resolution(child,qualify(),now_unix=3)
    current=[4]
    def after_wait():current[0]=child.expires_at_unix
    with pytest.raises(AccountEffectAuthorityExpired):
        journal.append_restriction_resolution(claim,qualify(),now_unix=4,before_append=after_wait,clock=lambda:current[0])
    assert journal.restriction_resolution(parent.operation_id,'device') is None
    assert journal.status(parent.operation_id,'device').phase=='UNKNOWN'
    ledger.close()


def test_lost_technical_child_completion_reads_same_proof_without_reopening(tmp_path):
    journal,parent,child,qualify,_,_,ledger=fixture(tmp_path)
    qualification=qualify();claim=journal.claim_restriction_resolution(child,qualification,now_unix=3)
    result=journal.append_restriction_resolution(claim,qualify(),now_unix=4,clock=lambda:4)
    journal.uncertain(claim,now_unix=5)
    assert result['resolution_child_operation_id']==child.operation_id
    assert journal.restriction_resolution(child.operation_id,'device')==result
    assert journal.restriction_resolution(parent.operation_id,'device')==result
    assert journal.status(child.operation_id,'device').phase=='UNKNOWN'
    assert journal.status(child.operation_id,'device').result is None
    assert journal.status(parent.operation_id,'device').phase=='UNKNOWN'
    assert journal.status(parent.operation_id,'device').result is None
    journal.require_clear_targets(parent.targets)
    with pytest.raises(AccountEffectUnknown):journal.claim_restriction_resolution(child,qualification,now_unix=6)
    ledger.close()


@pytest.mark.parametrize('parent_terminal',[False,True])
def test_reconcile_child_unknown_before_fact_is_bound_to_fresh_grandchild(tmp_path,parent_terminal):
    journal,parent,child,_,request,parent_admission,ledger=fixture(tmp_path,uncertain=False)
    parent_claim=journal.status(parent.operation_id,'device')
    registry=AccountRegistry(tmp_path/'accounts.json');version=parent.resource_version
    parent_refs=journal.restriction_operation_refs(parent.operation_id,parent_admission)
    request={**request,'reauth_fact_id':'reauth_fact_1234567890123','reauth_fact_digest':'4'*64}
    context={'alias':'paper','original_device_id':'device','resource_version':version,
             'account_control_domain':'d'*64,'incarnation':version,'variant':'RECONCILE_DATA',
             'expected_revision':0,'expected_digest':None,'restriction_id':parent.operation_id,
             'review_digest':'a'*64,'semantic_digest':canonical_hash({k:v for k,v in request.items() if k not in {'reauth_fact_id','reauth_fact_digest'}}),
             'reason_code':'OWNER_REQUEST','parent_operation_id':parent.operation_id,
             'parent_admission_digest':parent_admission['admission_digest']}
    admission={'schema':'van.account-restriction-admission/1','action':'account_restrict',
        'purpose':'ACCOUNT_RESTRICTION_CONTROL','owner_id':'owner','device_id':'device','operation_id':child.operation_id,
        'native_request':request,'authority_ref':'b'*64,'context':context,
        'reauth_purpose':'ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA','actor_key_ref':'c'*64,'request_digest':None,
        'reauth_fact_digest':'4'*64,'reauth_proof_ref':'5'*64,'created_at_unix':2,'expires_at_unix':1000,
        'approval_text_digest':'f'*64,'approval_parameters_digest':'9'*64,'native_review_digest':'6'*64,
        'reauth_fact_id':request['reauth_fact_id'],'state':'ADMITTED_NOT_NATIVE_COMPLETION'}
    seal_admission(admission,related=parent_refs)
    child=replace(child,authority_ref=admission['authority_ref']+'::review:'+admission['native_review_digest'],request_digest=canonical_hash(request))
    def qualify_original():
        return journal.qualify_restriction_resolution(child,parent_operation_id=parent.operation_id,child_request=request,
            original_request=parent_admission['native_request'],original_admission=parent_admission,
            expected_admission_digest=parent_admission['admission_digest'],registry=registry,current_resource_version=version,
            expected_operation_refs=journal.restriction_operation_refs(parent.operation_id,parent_admission))
    child_claim=journal.claim_restriction_resolution(child,qualify_original(),now_unix=3)
    journal.uncertain(child_claim,now_unix=4)
    if parent_terminal:journal.refuse(parent_claim,409,now_unix=5)
    else:journal.uncertain(parent_claim,now_unix=5)
    selected=child if parent_terminal else parent
    selected_admission=admission if parent_terminal else parent_admission
    related=[parent_admission] if parent_terminal else [admission]
    refs=journal.restriction_operation_refs(selected.operation_id,selected_admission,related_admissions=related)
    next_request={'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':selected.operation_id,
                  'restriction_id':selected.operation_id,'expected_revision':0}
    grandchild=AccountEffectIntent('grandchild_operation_12345','device','new-proof','account_restrict',parent.targets,
                                   canonical_hash(next_request),version,1000)
    def qualify_child():
        return journal.qualify_restriction_resolution(grandchild,parent_operation_id=selected.operation_id,
            child_request=next_request,original_request=selected_admission['native_request'],original_admission=selected_admission,
            expected_admission_digest=selected_admission['admission_digest'],registry=registry,current_resource_version=version,
            related_admissions=related,expected_operation_refs=refs)
    assert qualify_child().summary['outcome']=='CURRENT_PREIMAGE_OBSERVED'
    claim=journal.claim_restriction_resolution(grandchild,qualify_child(),now_unix=6)
    result=journal.append_restriction_resolution(claim,qualify_child(),now_unix=7,clock=lambda:7)
    assert journal.status(child.operation_id,'device').phase=='UNKNOWN'
    assert journal.status(child.operation_id,'device').result is None
    if not parent_terminal:assert journal.status(parent.operation_id,'device').phase=='UNKNOWN'
    else:
        assert journal.status(parent.operation_id,'device').phase=='REFUSED'
        assert parent.operation_id not in result['resolved_operations']
        assert journal.restriction_resolution(parent.operation_id,'device') is None
    journal.require_clear_targets(parent.targets)
    ledger.close()


def test_repeated_unknown_children_are_resolved_by_exact_multilevel_bundle(tmp_path):
    journal,parent,_,_,_,original,ledger=fixture(tmp_path)
    registry=AccountRegistry(tmp_path/'accounts.json');version=parent.resource_version;related=[];unknowns=[parent]
    def request():
        return {'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':parent.operation_id,
                'restriction_id':parent.operation_id,'expected_revision':0,
                'reauth_fact_id':'reauth_fact_1234567890123','reauth_fact_digest':'4'*64}
    def qualification(intent,req,refs):
        return journal.qualify_restriction_resolution(intent,parent_operation_id=parent.operation_id,child_request=req,
            original_request=original['native_request'],original_admission=original,
            expected_admission_digest=original['admission_digest'],registry=registry,current_resource_version=version,
            related_admissions=related,expected_operation_refs=refs)
    for number in (1,2):
        refs=journal.restriction_operation_refs(parent.operation_id,original,related_admissions=related)
        req=request();op='repeated_child_operation_'+str(number)+'_12345'
        adm=metadata_child_admission(op,parent,original,req,refs)
        intent=AccountEffectIntent(op,'device',adm['authority_ref']+'::review:'+adm['native_review_digest'],
            'account_restrict',parent.targets,canonical_hash(req),version,1000)
        claim=journal.claim_restriction_resolution(intent,qualification(intent,req,refs),now_unix=10+number)
        journal.uncertain(claim,now_unix=20+number);related.append(adm);unknowns.append(intent)
    refs=journal.restriction_operation_refs(parent.operation_id,original,related_admissions=related)
    forged=copy.deepcopy(related[0]);forged['context']['parent_operation_id']=forged['operation_id']
    seal_admission(forged,related=forged['native_review']['view']['related_operations'])
    with pytest.raises(AccountEffectConflict):
        journal.restriction_operation_refs(parent.operation_id,original,related_admissions=[forged,*related[1:]])
    req=request();final=AccountEffectIntent('final_reconcile_operation_12345','device','separate-a4','account_restrict',
                                            parent.targets,canonical_hash(req),version,1000)
    q=qualification(final,req,refs)
    assert q.summary['resolved_operations']==sorted(x.operation_id for x in unknowns)
    claim=journal.claim_restriction_resolution(final,q,now_unix=30)
    result=journal.append_restriction_resolution(claim,qualification(final,req,refs),now_unix=31,clock=lambda:31)
    for state in unknowns:
        assert journal.status(state.operation_id,'device').phase=='UNKNOWN'
        assert journal.status(state.operation_id,'device').result is None
    assert journal.restriction_resolution(parent.operation_id,'device')==result
    journal.require_clear_targets(parent.targets)
    ledger.close()


def test_nested_parent_chain_resolves_unknown_ancestor_and_child(tmp_path):
    journal,parent,_,_,_,original,ledger=fixture(tmp_path)
    registry=AccountRegistry(tmp_path/'accounts.json');version=parent.resource_version
    parent_refs=journal.restriction_operation_refs(parent.operation_id,original)
    child_request={'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':parent.operation_id,
                   'restriction_id':parent.operation_id,'expected_revision':0,
                   'reauth_fact_id':'reauth_fact_1234567890123','reauth_fact_digest':'4'*64}
    child_admission=metadata_child_admission('nested_child_operation_12345',parent,original,child_request,parent_refs)
    child=AccountEffectIntent(child_admission['operation_id'],'device',
        child_admission['authority_ref']+'::review:'+child_admission['native_review_digest'],
        'account_restrict',parent.targets,canonical_hash(child_request),version,1000)
    q=journal.qualify_restriction_resolution(child,parent_operation_id=parent.operation_id,
        child_request=child_request,original_request=original['native_request'],original_admission=original,
        expected_admission_digest=original['admission_digest'],registry=registry,current_resource_version=version,
        expected_operation_refs=parent_refs)
    claim=journal.claim_restriction_resolution(child,q,now_unix=3);journal.uncertain(claim,now_unix=4)
    with pytest.raises(AccountEffectConflict):journal.restriction_operation_refs(child.operation_id,child_admission)
    nested_refs=journal.restriction_operation_refs(child.operation_id,child_admission,related_admissions=[original])
    request={'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':child.operation_id,
             'restriction_id':child.operation_id,'expected_revision':0}
    grandchild=AccountEffectIntent('nested_grandchild_operation_12345','device','separate-a4','account_restrict',
                                   parent.targets,canonical_hash(request),version,1000)
    def qualified():
        return journal.qualify_restriction_resolution(grandchild,parent_operation_id=child.operation_id,
            child_request=request,original_request=child_request,original_admission=child_admission,
            expected_admission_digest=child_admission['admission_digest'],registry=registry,current_resource_version=version,
            related_admissions=[original],expected_operation_refs=nested_refs)
    final=journal.claim_restriction_resolution(grandchild,qualified(),now_unix=5)
    journal.append_restriction_resolution(final,qualified(),now_unix=6,clock=lambda:6)
    for state in (parent,child):
        assert journal.status(state.operation_id,'device').phase=='UNKNOWN'
        assert journal.status(state.operation_id,'device').result is None
    assert journal.restriction_resolution(parent.operation_id,'device')==journal.restriction_resolution(child.operation_id,'device')
    journal.require_clear_targets(parent.targets)
    ledger.close()


@pytest.mark.parametrize('terminal_phase',['APPLIED','REFUSED'])
def test_terminal_anchor_must_agree_with_actual_restriction_transition(tmp_path,terminal_phase):
    journal,parent,_,_,_,original,ledger=fixture(tmp_path,applied=True,uncertain=False)
    parent_claim=journal.status(parent.operation_id,'device')
    registry=AccountRegistry(tmp_path/'accounts.json');row=registry._restrictions['paper']
    version=resource_snapshot(registry,'paper')['resource_version']
    refs=journal.restriction_operation_refs(parent.operation_id,original)
    req={'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':parent.operation_id,
         'restriction_id':row['restriction_id'],'expected_revision':row['revision'],'expected_digest':canonical_hash(row),
         'reauth_fact_id':'reauth_fact_1234567890123','reauth_fact_digest':'4'*64}
    context={'alias':'paper','original_device_id':'device','resource_version':version,
        'account_control_domain':row['account_control_domain'],'incarnation':row['incarnation'],'variant':'RECONCILE_DATA',
        'expected_revision':row['revision'],'expected_digest':canonical_hash(row),'restriction_id':row['restriction_id'],
        'review_digest':'a'*64,'semantic_digest':canonical_hash({k:v for k,v in req.items() if k not in {'reauth_fact_id','reauth_fact_digest'}}),
        'reason_code':row['reason_code'],'parent_operation_id':parent.operation_id,'parent_admission_digest':original['admission_digest']}
    admission={'schema':'van.account-restriction-admission/1','action':'account_restrict','purpose':'ACCOUNT_RESTRICTION_CONTROL',
        'owner_id':'owner','device_id':'device','operation_id':'applied_anchor_child_12345','native_request':req,
        'authority_ref':'b'*64,'context':context,'reauth_purpose':'ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA',
        'actor_key_ref':'c'*64,'request_digest':None,'reauth_fact_digest':'4'*64,'reauth_proof_ref':'5'*64,
        'created_at_unix':2,'expires_at_unix':1000,'approval_text_digest':'f'*64,'approval_parameters_digest':'9'*64,
        'native_review_digest':'6'*64,'reauth_fact_id':req['reauth_fact_id'],'state':'ADMITTED_NOT_NATIVE_COMPLETION'}
    seal_admission(admission,before=public_record(row),related=refs)
    child=AccountEffectIntent(admission['operation_id'],'device',admission['authority_ref']+'::review:'+admission['native_review_digest'],
                              'account_restrict',parent.targets,canonical_hash(req),version,1000)
    q=journal.qualify_restriction_resolution(child,parent_operation_id=parent.operation_id,child_request=req,
        original_request=original['native_request'],original_admission=original,expected_admission_digest=original['admission_digest'],
        registry=registry,current_resource_version=version,expected_operation_refs=refs)
    claim=journal.claim_restriction_resolution(child,q,now_unix=3);journal.uncertain(claim,now_unix=4)
    if terminal_phase=='APPLIED':journal.complete(parent_claim,{'metadata':'recorded'},now_unix=5)
    else:journal.refuse(parent_claim,409,now_unix=5)
    next_req={'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':child.operation_id,
              'restriction_id':row['restriction_id'],'expected_revision':row['revision'],'expected_digest':canonical_hash(row)}
    final=AccountEffectIntent('applied_anchor_final_12345','device','separate-a4','account_restrict',parent.targets,
                              canonical_hash(next_req),version,1000)
    current_refs=journal.restriction_operation_refs(child.operation_id,admission,related_admissions=[original])
    def qualify():
        return journal.qualify_restriction_resolution(final,parent_operation_id=child.operation_id,child_request=next_req,
            original_request=req,original_admission=admission,expected_admission_digest=admission['admission_digest'],
            registry=registry,current_resource_version=version,related_admissions=[original],expected_operation_refs=current_refs)
    if terminal_phase=='REFUSED':
        with pytest.raises(AccountEffectConflict):qualify()
    else:
        fresh=journal.claim_restriction_resolution(final,qualify(),now_unix=6)
        result=journal.append_restriction_resolution(fresh,qualify(),now_unix=7,clock=lambda:7)
        assert result['anchor_outcome']=='TRANSITION_OBSERVED'
        assert parent.operation_id not in result['resolved_operations']
        assert journal.status(parent.operation_id,'device').phase=='APPLIED'
        assert journal.restriction_resolution(parent.operation_id,'device') is None
        assert journal.restriction_resolution(child.operation_id,'device')==result
    ledger.close()


def test_original_or_child_transplant_and_unrelated_unknown_hold(tmp_path):
    journal,parent,child,qualify,request,admission,ledger=fixture(tmp_path)
    with pytest.raises(AccountEffectConflict):qualify(original_request={'alias':'paper','variant':'RESTRICT'})
    with pytest.raises(AccountEffectConflict):qualify(expected_admission_digest='0'*64)
    with pytest.raises(AccountEffectConflict):qualify(child_request={**request,'parent_operation_id':'other_parent_operation_12345'})
    for changed in ({'native_review_digest':'7'*64},{'request_digest':'7'*64}):
        altered={**admission,**changed};altered['admission_digest']=canonical_hash({k:v for k,v in altered.items() if k!='admission_digest'})
        with pytest.raises(AccountEffectConflict):
            qualify(original_admission=altered,expected_admission_digest=altered['admission_digest'])
    other=replace(parent,operation_id='other_operation_1234567890',command='account_upsert',targets=('account:paper',),request_digest='1'*64)
    # Construct another genuinely unresolved overlapping operation before resolving parent.
    journal._append(other,'IN_FLIGHT','',now=2)
    with pytest.raises(AccountEffectConflict):journal.claim_restriction_resolution(child,qualify(),now_unix=3)
    ledger.close()


def test_device_identity_metadata_matches_restriction_owner_text_rules(tmp_path):
    journal,_,_,_,_,admission,ledger=fixture(tmp_path)
    valid=copy.deepcopy(admission);valid['device_id']='Device Ω 1';valid['context']['original_device_id']=valid['device_id']
    seal_admission(valid);journal._restriction_admission_shape(valid)
    with pytest.raises(AccountEffectConflict):
        journal._restriction_admission_shape({**admission,'device_id':'token=secret'})
    ledger.close()


def test_tampered_technical_record_holds_complete_chain(tmp_path):
    journal,parent,child,qualify,_,_,ledger=fixture(tmp_path)
    claim=journal.claim_restriction_resolution(child,qualify(),now_unix=3)
    journal.append_restriction_resolution(claim,qualify(),now_unix=4,clock=lambda:4)
    ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE seq=(SELECT max(seq) FROM events)")
    with pytest.raises(AccountEffectUnknown):journal.require_clear_targets(parent.targets)
    ledger.close()


def test_resealed_technical_record_with_transplanted_original_is_rejected(tmp_path):
    journal,parent,child,qualify,_,_,ledger=fixture(tmp_path)
    q=qualify();claim=journal.claim_restriction_resolution(child,q,now_unix=3)
    evidence=json.loads(q.evidence_json)
    evidence['original_request']['reason_code']='KILL_SWITCH'
    body={'schema':SCHEMA,'record_type':'RESTRICTION_RESOLUTION','parent_id':parent.operation_id,
          'parent_ref':q.parent_ref,'parent_hash':q.parent_hash,'child_id':child.operation_id,
          'child_ref':claim.event_ref,'child_hash':q.child_hash,'child_request':json.loads(q.child_request_json),
          'evidence':evidence,'summary':q.summary,'summary_hash':canonical_hash(q.summary),'authority_issued':False}
    ledger.append(make_event(EventKind.ACCOUNT_OPERATION,PRODUCER,body,event_time_ms=4000,
                             received_time_ms=4000,correlation_id=child.operation_id))
    assert ledger.verify_chain()[0]
    with pytest.raises(AccountEffectUnknown):journal.require_clear_targets(parent.targets)
    ledger.close()


@pytest.mark.parametrize('variant',['BEGIN_REAUTH','COMPLETE_REAUTH'])
@pytest.mark.parametrize('applied',[False,True])
def test_recovery_variant_resolves_exact_validated_transition_or_preimage(tmp_path,variant,applied):
    _,_,_,_,_,_,old_ledger=fixture(tmp_path,applied=True)
    old_ledger.close()
    registry=AccountRegistry(tmp_path/'accounts.json')
    if variant=='COMPLETE_REAUTH':
        def begin(current):
            current._restrictions['paper']=transition_record(current._restrictions['paper'],
                operation_id='earlier_reauth_123456789',device_id='device',phase='REAUTH_PENDING',
                request_digest='1'*64,resource_version='2'*64,admission_digest='3'*64,now=3)
        registry.restriction_update('paper',begin)
        registry=AccountRegistry(registry.path)
    prior=registry._restrictions['paper'];version=resource_snapshot(registry,'paper')['resource_version']
    original={'alias':'paper','variant':variant,'restriction_id':prior['restriction_id'],
              'expected_revision':prior['revision'],'expected_digest':canonical_hash(prior),
              'reauth_fact_id':'reauth_fact_1234567890123','reauth_fact_digest':'4'*64}
    parent=AccountEffectIntent('recovery_parent_123456789','device','b'*64+'::review:'+'6'*64,'account_restrict',
        ('account:paper','account-control-domain:'+prior['account_control_domain']),canonical_hash(original),version,1000)
    context={'alias':'paper','original_device_id':'device','resource_version':version,
             'account_control_domain':prior['account_control_domain'],'incarnation':prior['incarnation'],
             'variant':variant,'expected_revision':prior['revision'],'expected_digest':canonical_hash(prior),
             'restriction_id':prior['restriction_id'],'review_digest':'a'*64,
             'semantic_digest':canonical_hash({k:v for k,v in original.items() if k not in {'reauth_fact_id','reauth_fact_digest'}}),
             'reason_code':prior['reason_code'],'parent_operation_id':None,'parent_admission_digest':None}
    admission={'schema':'van.account-restriction-admission/1','action':'account_restrict',
        'purpose':'ACCOUNT_RESTRICTION_CONTROL','owner_id':'owner','device_id':'device','operation_id':parent.operation_id,
        'native_request':original,'authority_ref':'b'*64,'context':context,
        'reauth_purpose':'ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA','actor_key_ref':'c'*64,'request_digest':None,
        'reauth_fact_digest':'4'*64,'reauth_proof_ref':'5'*64,'created_at_unix':4,'expires_at_unix':1000,
        'approval_text_digest':'f'*64,'approval_parameters_digest':'9'*64,'native_review_digest':'6'*64,
        'reauth_fact_id':original['reauth_fact_id'],'state':'ADMITTED_NOT_NATIVE_COMPLETION'}
    seal_admission(admission,before=public_record(prior))
    parent=replace(parent,authority_ref=admission['authority_ref']+'::review:'+admission['native_review_digest'])
    ledger=Ledger();journal=AccountEffectJournal(ledger)
    journal.uncertain(journal.claim(parent,now_unix=5),now_unix=6)
    def apply(current):
        current._restrictions['paper']=transition_record(current._restrictions['paper'],operation_id=parent.operation_id,
            device_id='device',phase='REAUTH_PENDING' if variant=='BEGIN_REAUTH' else 'LINKED_READ_ONLY',
            request_digest=parent.request_digest,resource_version=version,admission_digest=admission['admission_digest'],now=7)
    if applied:
        registry.restriction_update('paper',apply)
        registry=AccountRegistry(registry.path)
    row=registry._restrictions['paper']
    current=resource_snapshot(registry,'paper')['resource_version']
    request={'alias':'paper','variant':'RECONCILE_DATA','parent_operation_id':parent.operation_id,
             'restriction_id':row['restriction_id'],'expected_revision':row['revision'],'expected_digest':canonical_hash(row)}
    child=AccountEffectIntent('recovery_child_1234567890','device','8'*64,'account_restrict',parent.targets,
                              canonical_hash(request),current,1000)
    def qualified():
        return journal.qualify_restriction_resolution(child,parent_operation_id=parent.operation_id,child_request=request,
            original_request=original,original_admission=admission,expected_admission_digest=admission['admission_digest'],
            registry=registry,current_resource_version=current,
            expected_operation_refs=journal.restriction_operation_refs(parent.operation_id,admission))
    claim=journal.claim_restriction_resolution(child,qualified(),now_unix=8)
    result=journal.append_restriction_resolution(claim,qualified(),now_unix=9,clock=lambda:9)
    assert result['outcome']==('TRANSITION_OBSERVED' if applied else 'CURRENT_PREIMAGE_OBSERVED')
    assert journal.status(parent.operation_id,'device').phase=='UNKNOWN'
    assert journal.status(parent.operation_id,'device').result is None
    assert journal.restriction_resolution(parent.operation_id,'device')==result
    ledger.close()
