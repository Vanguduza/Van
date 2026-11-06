"""Restriction controls: existing Gateway authority, native journal and DATA owner.

Native identity observations are not approvals. Direct effects require the
bootstrap-bound Store verifier or the actual authenticated Gateway ingress.
"""
from copy import deepcopy
from dataclasses import replace
import re
import time

from fastapi import HTTPException
from vati.accounts.registry import AccountRegistry,AccountRegistryError
from vati.accounts.lifecycle import require_attached
from vati.accounts.restrictions import REASONS,initial_record,transition_record,public_record,validate_record
from vati.core.canonical import canonical_hash
from commander.account_effects import (AccountEffectJournal,AccountEffectError,AccountOperationUnconfirmed,
    invoke_account_effect,operation_intent,require_current_account_effect,mark_account_effect,targets_overlap)
from commander.account_restriction_identity import expected_identity_scope,observe_readonly_identity

VARIANTS={'RESTRICT','BEGIN_REAUTH','COMPLETE_REAUTH','RECONCILE_DATA'}
HASH=re.compile(r'^[0-9a-f]{64}$')
ID=re.compile(r'^[A-Za-z0-9_-]{20,128}$')

def refuse(code,status=409):raise HTTPException(status,{'code':code,'execution_authority':False})
def semantic(args):return {k:v for k,v in args.items() if k not in {'reauth_fact_id','reauth_fact_digest'}}
def public_args(args):return {k:v for k,v in args.items() if not k.startswith('_')}

def arguments(raw):
    if type(raw) is not dict or any(type(k) is not str for k in raw):refuse('RESTRICTION_INPUT_INVALID',422)
    args=public_args(raw);variant=args.get('variant');alias=args.get('alias')
    if type(variant) is not str or variant not in VARIANTS or type(alias) is not str or re.fullmatch(r'[a-z0-9_]{3,32}',alias) is None:
        refuse('RESTRICTION_INPUT_INVALID',422)
    required={'alias','variant'};allowed=set(required)
    controls={'restriction_id','expected_revision','expected_digest'}
    if variant=='RESTRICT':
        required.add('reason_code');allowed.add('reason_code')
        if type(args.get('reason_code')) is not str or args['reason_code'] not in REASONS:refuse('RESTRICTION_REASON_INVALID',422)
        if controls.intersection(args):required|={'restriction_id','expected_revision'};allowed|=controls
    else:
        required|={'restriction_id','expected_revision'};allowed|=controls|{'reauth_fact_id','reauth_fact_digest'}
    if variant=='RECONCILE_DATA':required.add('parent_operation_id');allowed.add('parent_operation_id')
    if not required.issubset(args) or set(args)-allowed:refuse('RESTRICTION_INPUT_INVALID',422)
    if 'restriction_id' in args:
        if type(args['restriction_id']) is not str or ID.fullmatch(args['restriction_id']) is None:refuse('RESTRICTION_INPUT_INVALID',422)
        revision=args['expected_revision'];minimum=0 if variant=='RECONCILE_DATA' else 1
        if type(revision) is not int or not minimum<=revision<2**63:refuse('RESTRICTION_INPUT_INVALID',422)
        if revision==0:
            if args.get('expected_digest') is not None:refuse('RESTRICTION_INPUT_INVALID',422)
        elif type(args.get('expected_digest')) is not str or HASH.fullmatch(args['expected_digest']) is None:refuse('RESTRICTION_INPUT_INVALID',422)
    if variant=='RECONCILE_DATA' and (type(args['parent_operation_id']) is not str or ID.fullmatch(args['parent_operation_id']) is None):
        refuse('RESTRICTION_INPUT_INVALID',422)
    if ('reauth_fact_id' in args)!=('reauth_fact_digest' in args):refuse('RESTRICTION_REAUTH_INPUT_INVALID',422)
    if 'reauth_fact_id' in args and (type(args['reauth_fact_id']) is not str or ID.fullmatch(args['reauth_fact_id']) is None
            or type(args['reauth_fact_digest']) is not str or HASH.fullmatch(args['reauth_fact_digest']) is None):refuse('RESTRICTION_REAUTH_INPUT_INVALID',422)
    return {k:v for k,v in args.items() if v is not None}


class _GatewayRestrictionRead:
    """Authenticated ingress marker only; not an issuer or approval."""
    def __init__(self,payload,current,binding):
        self.payload=canonical_hash({k:v for k,v in payload.items() if not k.startswith('_')})
        self.current,self.binding=current,binding
    def require(self,payload):
        self.current()
        if self.payload!=canonical_hash({k:v for k,v in payload.items() if not k.startswith('_')}):
            refuse('RESTRICTION_READ_SCOPE_CHANGED',403)
        return payload['owner_device_id']


class _GatewayRestrictionAdmission:
    """Existing authenticated Gateway transport attestation; no Owner authority."""
    def __init__(self,record,current,binding):
        self.record=deepcopy(record);self.current,self.binding=current,binding
    def require(self,args,now):
        self.current();record=self.record
        try:
            context=record['context'];operation=args['_native_operation'];request=arguments(args)
            if (record!=args['_restriction_admission'] or record['schema']!='van.account-restriction-admission/1'
                    or record['owner_id']!='owner' or record['action']!='account_restrict'
                    or record['purpose']!='ACCOUNT_RESTRICTION_CONTROL' or record['state']!='ADMITTED_NOT_NATIVE_COMPLETION'
                    or record['admission_digest']!=canonical_hash({k:v for k,v in record.items() if k!='admission_digest'})
                    or record['native_request']!=request or context['alias']!=request['alias'] or context['variant']!=request['variant']
                    or context['semantic_digest']!=canonical_hash(semantic(request))
                    or context['resource_version']!=args['_expected_resource_version']
                    or context['review_digest']!=args['_expected_restriction_context_digest']
                    or context['account_control_domain']!=args['_expected_account_control_domain']
                    or context['original_device_id']!=record['device_id'] or record['device_id']!=operation['device_id']
                    or record['operation_id']!=operation['operation_id'] or operation['request_digest']!=canonical_hash(request)
                    or record['native_review_digest']!=args['_expected_review_digest']
                    or record['native_review_digest']!=canonical_hash({k:v for k,v in record['native_review'].items() if k!='review_digest'})
                    or record['native_review']['context_digest']!=context['review_digest']
                    or operation['authority_ref']!=record['authority_ref']+'::review:'+record['native_review_digest']
                    or operation['expires_at_unix']!=record['expires_at_unix']
                    or type(record['created_at_unix']) is not int or type(record['expires_at_unix']) is not int
                    or not 0<=record['created_at_unix']<=now<record['expires_at_unix']
                    or record['request_digest']!=canonical_hash({'context':context,'fact_id':record['reauth_fact_id'],
                        'challenge_id':record['operation_id'],'text_digest':record['approval_text_digest'],
                        'parameters_digest':record['approval_parameters_digest']})):
                raise ValueError()
            for key in ('actor_key_ref','authority_ref','approval_text_digest','approval_parameters_digest','request_digest','native_review_digest'):
                if type(record[key]) is not str or HASH.fullmatch(record[key]) is None:raise ValueError()
            if request['variant']=='RESTRICT':
                if any(record[k] is not None for k in ('reauth_purpose','reauth_fact_id','reauth_fact_digest','reauth_proof_ref')):raise ValueError()
            elif (record['reauth_purpose']!='ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA'
                    or record['reauth_fact_id']!=request['reauth_fact_id'] or record['reauth_fact_digest']!=request['reauth_fact_digest']
                    or record['reauth_fact_id']==record['operation_id'] or record['reauth_proof_ref']==record['authority_ref']
                    or any(type(record[k]) is not str or HASH.fullmatch(record[k]) is None for k in ('reauth_fact_digest','reauth_proof_ref'))):
                raise ValueError()
            if request['variant']=='RECONCILE_DATA':
                parent=args['_restriction_original_admission']
                if (parent['admission_digest']!=context['parent_admission_digest']
                        or parent['admission_digest']!=canonical_hash({k:v for k,v in parent.items() if k!='admission_digest'})
                        or parent['operation_id']!=request['parent_operation_id'] or parent['device_id']!=record['device_id']
                        or parent['context']['account_control_domain']!=context['account_control_domain']
                        or parent['context']['alias']!=context['alias'] or parent['schema']!=record['schema']
                        or parent['action']!='account_restrict' or parent['purpose']!='ACCOUNT_RESTRICTION_CONTROL'):
                    raise ValueError()
        except (KeyError,TypeError,ValueError,AttributeError):refuse('RESTRICTION_GATEWAY_ADMISSION_UNVERIFIED',403)
        return record


class NativeRestriction:
    def __init__(self,settings,ledger,domain,resource_version,*,clock=None):
        self.st,self.ledger,self.domain,self.resource_version=settings,ledger,domain,resource_version
        self.clock=clock or (lambda:int(time.time()))
    def registry(self):return AccountRegistry(self.st.registry_path)
    def require_admission(self,args):
        verifier=getattr(self.st,'restriction_admission_verifier',None)
        if callable(verifier):
            record=verifier(args)
            attestation=_GatewayRestrictionAdmission(record,lambda:None,None)
        else:
            attestation=args.get('_restriction_admission_guard')
            binding=getattr(self.st,'restriction_transport_binding',None)
            if binding is None or type(attestation) is not _GatewayRestrictionAdmission or attestation.binding is not binding:
                refuse('RESTRICTION_GATEWAY_ADMISSION_REQUIRED',403)
        record=attestation.require(args,self.clock())
        if record['context']['account_control_domain']!=self.domain(self.ledger):refuse('RESTRICTION_DOMAIN_CHANGED')
        return record
    def require_read(self,payload):
        verifier=getattr(self.st,'restriction_read_verifier',None)
        if callable(verifier):device=verifier(payload)
        else:
            marker=payload.get('_restriction_read_guard');binding=getattr(self.st,'restriction_transport_binding',None)
            if binding is None or type(marker) is not _GatewayRestrictionRead or marker.binding is not binding:
                refuse('RESTRICTION_CURRENT_OWNER_REQUIRED',403)
            device=marker.require(payload)
        if type(device) is not str or not device or device!=payload.get('owner_device_id'):refuse('RESTRICTION_CURRENT_OWNER_REQUIRED',403)
        return device
    def _row(self,registry,alias,restriction_id=None):
        row=registry._restrictions.get(alias)
        if restriction_id is not None and (row is None or row['restriction_id']!=restriction_id):
            row=registry._restriction_history.get(restriction_id)
        if row is None or row['alias']!=alias:refuse('RESTRICTION_ORIGINAL_NOT_FOUND',404)
        return validate_record(row)
    def read(self,payload):
        device=self.require_read(payload);args=payload['args'];alias=args.get('alias');restriction_id=args.get('restriction_id')
        if (type(alias) is not str or re.fullmatch(r'[a-z0-9_]{3,32}',alias) is None
                or restriction_id is not None and (type(restriction_id) is not str or ID.fullmatch(restriction_id) is None)):
            refuse('RESTRICTION_INPUT_INVALID',422)
        registry=self.registry();row=self._row(registry,alias,restriction_id)
        if row['device_id']!=device or row['account_control_domain']!=self.domain(self.ledger):refuse('RESTRICTION_ORIGINAL_SCOPE_REFUSED',403)
        return {'schema':'vati.account-restriction-read/1','restriction':public_record(row),'execution_authority':False}
    def pending(self,payload):
        device=self.require_read(payload);alias=payload['args'].get('alias')
        if type(alias) is not str or re.fullmatch(r'[a-z0-9_]{3,32}',alias) is None:refuse('RESTRICTION_INPUT_INVALID',422)
        journal=AccountEffectJournal(self.ledger,cleanup_secrets_root=self.st.secrets_dir)
        with self.ledger.atomic():
            ids=[]
            for state in journal._states().values():
                if state.phase not in {'IN_FLIGHT','UNKNOWN'} or not targets_overlap(('account:'+alias,),state.intent.targets):continue
                if journal._resolved_safety_obligation(state):continue
                if (state.intent.command!='account_restrict' or state.intent.device_id!=device
                        or 'account-control-domain:'+self.domain(self.ledger) not in state.intent.targets):
                    refuse('RESTRICTION_UNRELATED_EFFECT_REQUIRES_ORIGINAL_OWNER')
                ids.append(state.intent.operation_id)
            if len(ids)>64:refuse('RESTRICTION_CAUSAL_PROOF_CAPACITY')
            return {'schema':'vati.account-restriction-pending/1','operation_ids':sorted(ids),'execution_authority':False}
    def resolution(self,payload):
        device=self.require_read(payload);args=payload['args'];journal=AccountEffectJournal(self.ledger,cleanup_secrets_root=self.st.secrets_dir)
        result=journal.restriction_resolution(args.get('operation_id'),device)
        if result is not None and result['alias']!=args.get('alias'):refuse('RESTRICTION_ORIGINAL_SCOPE_REFUSED',403)
        return {'schema':'vati.account-restriction-resolution-read/1','resolution':result,'execution_authority':False}
    def _causal(self,args,device,sources,child_operation_id=None):
        if type(sources) is not list or not 1<=len(sources)<=64:refuse('RESTRICTION_CAUSAL_PROOF_CAPACITY')
        selected=args['parent_operation_id'];records={r.get('operation_id'):r for r in sources if type(r) is dict}
        if len(records)!=len(sources) or selected not in records:refuse('RESTRICTION_CAUSAL_SOURCE_INCOMPLETE')
        original=records[selected];journal=AccountEffectJournal(self.ledger,cleanup_secrets_root=self.st.secrets_dir)
        if (original.get('device_id')!=device or original.get('context',{}).get('alias')!=args['alias']
                or original['context'].get('account_control_domain')!=self.domain(self.ledger)):
            refuse('RESTRICTION_ORIGINAL_SCOPE_REFUSED',403)
        related=[r for r in sources if r['operation_id']!=selected]
        try:refs=journal.restriction_operation_refs(selected,original,related_admissions=related)
        except AccountEffectError:refuse('RESTRICTION_CAUSAL_SOURCE_UNVERIFIED')
        expected={r['operation_id'] for r in refs}
        # Complete current overlapping UNKNOWN obligations, not merely the
        # caller-selected branch. Terminal anchors remain lineage DATA only.
        with self.ledger.atomic():
            for state in journal._states().values():
                if (state.phase in {'IN_FLIGHT','UNKNOWN'} and targets_overlap(('account:'+args['alias'],),state.intent.targets)
                        and state.intent.operation_id not in expected and state.intent.operation_id!=child_operation_id and not journal._resolved_safety_obligation(state)):
                    refuse('RESTRICTION_UNLISTED_EFFECT_REQUIRES_FRESH_REVIEW')
        return journal,original,related,refs
    def _review(self,args,device,sources=(),child_operation_id=None):
        values=arguments(args);alias=values['alias'];variant=values['variant'];registry=self.registry()
        require_attached(registry,alias)
        try:account=registry.get(alias)
        except AccountRegistryError:refuse('RESTRICTION_ACCOUNT_NOT_REGISTERED',404)
        domain=self.domain(self.ledger);version=self.resource_version(alias);row=registry._restrictions.get(alias)
        if row is not None:
            row=validate_record(row)
            if row['device_id']!=device or row['account_control_domain']!=domain:refuse('RESTRICTION_ORIGINAL_SCOPE_REFUSED',403)
        original=None;refs=[]
        if variant=='RECONCILE_DATA':
            _,original,_,refs=self._causal(values,device,list(sources),child_operation_id)
            restriction_id=row['restriction_id'] if row else values['parent_operation_id']
            incarnation=row['incarnation'] if row else original['context']['incarnation']
            revision=row['revision'] if row else 0;digest=canonical_hash(row) if row else None
            reason=row['reason_code'] if row else original['context']['reason_code']
            if (values['restriction_id']!=restriction_id or values['expected_revision']!=revision
                    or values.get('expected_digest')!=digest or incarnation!=original['context']['incarnation']):
                refuse('RESTRICTION_RECONCILIATION_CURRENT_DATA_CHANGED')
        elif variant=='RESTRICT' and 'restriction_id' not in values:
            if row is not None:refuse('RESTRICTION_EXACT_ORIGINAL_REQUIRED')
            restriction_id='proposed:'+version;incarnation=version;revision=0;digest=None;reason=values['reason_code']
        else:
            if row is None or row['restriction_id']!=values['restriction_id']:refuse('RESTRICTION_CURRENT_GENERATION_CHANGED')
            if values['expected_revision']!=row['revision'] or values.get('expected_digest')!=canonical_hash(row):refuse('RESTRICTION_REVIEW_CHANGED')
            expected={'RESTRICT':{'LINKED_READ_ONLY','REAUTH_PENDING'},'BEGIN_REAUTH':{'RESTRICTED'},'COMPLETE_REAUTH':{'REAUTH_PENDING'}}[variant]
            if row['phase'] not in expected:refuse('RESTRICTION_TRANSITION_REFUSED')
            if variant=='RESTRICT' and values['reason_code']!=row['reason_code']:refuse('RESTRICTION_ORIGINAL_REASON_CHANGED')
            restriction_id=row['restriction_id'];incarnation=row['incarnation'];revision=row['revision'];digest=canonical_hash(row);reason=row['reason_code']
        view={'alias':alias,'owner_device_id':device,'account_control_domain':domain,'restriction_id':restriction_id,
              'incarnation':incarnation,'expected_revision':revision,'expected_digest':digest,'reason_code':reason,
              'before':public_record(row) if row else None,'enabled':account.enabled,'mode':account.mode,
              'mode_or_mandate_granted':False,'entry_permitted':False,'protective_exits_preserved':True,
              'native_identity_required':variant=='COMPLETE_REAUTH',
              'native_identity_scope_ref':canonical_hash(expected_identity_scope(account)) if variant=='COMPLETE_REAUTH' else None,
              'parent_admission_digest':original['admission_digest'] if original else None,'related_operations':refs}
        body={'schema':'vati.account-restriction-review/1','semantic_digest':canonical_hash(semantic(values)),
              'resource_version':version,'view':view}
        body['context_digest']=canonical_hash(body);body['request_digest']=canonical_hash(values)
        return {**body,'review_digest':canonical_hash(body)}
    def review(self,payload):
        device=self.require_read(payload);values=arguments(payload['args']);registry=self.registry()
        with registry.operation_lock(values['alias']),registry._mutation_lock():return self._review(values,device,payload.get('_restriction_related_admissions',[]))
    def execute(self,args):
        admitted=self.require_admission(args);values=arguments(args);alias=values['alias'];registry=self.registry()
        intent=operation_intent('account_restrict',args);journal=AccountEffectJournal(self.ledger,cleanup_secrets_root=self.st.secrets_dir)
        with registry.operation_lock(alias),registry._mutation_lock():
            original=journal.status(intent.operation_id,intent.device_id)
            if original is not None:
                if original.intent!=intent:refuse('RESTRICTION_ORIGINAL_OPERATION_CONFLICT')
                if original.phase=='APPLIED':return original.result
                if original.phase=='REFUSED':raise HTTPException(original.result['status_code'],original.result['detail'])
                raise AccountOperationUnconfirmed(intent.operation_id)
            review=self._review(values,intent.device_id,args.get('_restriction_related_admissions',[]))
            if (review['resource_version']!=args.get('_expected_resource_version')
                    or review['review_digest']!=args.get('_expected_review_digest')
                    or review['context_digest']!=args.get('_expected_restriction_context_digest')
                    or review!=admitted['native_review']):refuse('RESTRICTION_REVIEW_CHANGED')
            self.require_admission(args)
            if values['variant']=='RECONCILE_DATA':
                qualification=self._qualification(args,intent,review)
                # Adapter selects only the separately qualified metadata claim;
                # the real journal still owns every event, outcome and fence.
                class QualifiedJournal:
                    def __getattr__(inner,name):return getattr(journal,name)
                    def claim(inner,current):
                        self.require_admission(args)
                        return journal.claim_restriction_resolution(current,qualification)
                def effect():
                    self.require_admission(args);require_current_account_effect()
                    claim=journal.status(intent.operation_id,intent.device_id)
                    def before_append():
                        self.require_admission(args);require_current_account_effect()
                        fresh=self._qualification(args,intent,review)
                        if fresh!=qualification:refuse('RESTRICTION_CAUSAL_PROOF_CHANGED')
                        if self.clock()>=admitted['expires_at_unix']:refuse('RESTRICTION_PERMISSION_EXPIRED',403)
                        mark_account_effect()
                    resolution=journal.append_restriction_resolution(claim,qualification,before_append=before_append,clock=self.clock)
                    return {'schema':'vati.account-restriction-result/1','action':'account_restrict','variant':'RECONCILE_DATA',
                        'restriction':review['view']['before'],'native_identity':None,'data_resolution':resolution,
                        'entry_permitted':False,'mode_or_mandate_granted':False,'protective_exits_preserved':True}
                return invoke_account_effect(QualifiedJournal(),intent,effect,dispatch_guard=lambda:self.require_admission(args))
            def effect():return self._apply(args,admitted,review)
            return invoke_account_effect(journal,intent,effect,dispatch_guard=lambda:self.require_admission(args))
    def _qualification(self,args,intent,review):
        values=arguments(args);journal,original,related,refs=self._causal(values,intent.device_id,args.get('_restriction_related_admissions',[]),intent.operation_id)
        if (refs!=review['view']['related_operations'] or self._review(values,intent.device_id,args.get('_restriction_related_admissions',[]),intent.operation_id)!=review):
            refuse('RESTRICTION_CAUSAL_PROOF_CHANGED')
        try:
            return journal.qualify_restriction_resolution(intent,parent_operation_id=values['parent_operation_id'],
                child_request=values,original_request=original['native_request'],original_admission=original,
                expected_admission_digest=original['admission_digest'],registry=self.registry(),
                current_resource_version=self.resource_version(values['alias']),related_admissions=related,expected_operation_refs=refs)
        except AccountEffectError:refuse('RESTRICTION_METADATA_RESOLUTION_UNPROVEN')
    def _apply(self,args,admitted,review):
        # Repeating these real ingress checks is intentional: calling this
        # effect seam directly cannot replace authority with a noop callback.
        self.require_admission(args);require_current_account_effect()
        values=arguments(args);alias=values['alias'];variant=values['variant'];registry=self.registry();account=registry.get(alias)
        owner=observe_readonly_identity(account,registry,self.st) if variant=='COMPLETE_REAUTH' else None
        observed=None
        try:
            now=self.clock();prior=registry._restrictions.get(alias)
            if variant=='RESTRICT' and prior is None:
                row=initial_record(alias=alias,operation_id=admitted['operation_id'],device_id=admitted['device_id'],
                    domain=admitted['context']['account_control_domain'],resource_version=review['resource_version'],
                    request_digest=canonical_hash(values),review_digest=review['context_digest'],
                    admission_digest=admitted['admission_digest'],reason_code=values['reason_code'],now=now)
            else:
                phase={'RESTRICT':'RESTRICTED','BEGIN_REAUTH':'REAUTH_PENDING','COMPLETE_REAUTH':'LINKED_READ_ONLY'}.get(variant)
                if phase is None:refuse('RESTRICTION_TRANSITION_REFUSED')
                row=transition_record(prior,operation_id=admitted['operation_id'],device_id=admitted['device_id'],phase=phase,
                    request_digest=canonical_hash(values),resource_version=review['resource_version'],
                    admission_digest=admitted['admission_digest'],now=now)
            def change(current):
                current._restrictions[alias]=row;current.accounts[alias]=replace(current.get(alias),enabled=False)
            def before_replace():
                nonlocal observed
                self.require_admission(args);require_current_account_effect()
                fresh=self._review(values,admitted['device_id'])
                if fresh!=review:refuse('RESTRICTION_REVIEW_CHANGED')
                # Last selected-source predicate after Store/actor callbacks.
                # Its local EA queue read may block; no provider refresh here.
                if owner is not None:observed=owner.require_current()
                if self.clock()>=admitted['expires_at_unix']:refuse('RESTRICTION_PERMISSION_EXPIRED',403)
                mark_account_effect()
            registry.restriction_update(alias,change,before_replace=before_replace)
            return {'schema':'vati.account-restriction-result/1','action':'account_restrict','variant':variant,
                    'restriction':public_record(row),'native_identity':observed,'data_resolution':None,
                    'entry_permitted':False,'mode_or_mandate_granted':False,'protective_exits_preserved':True}
        finally:
            if owner is not None:owner.close()
