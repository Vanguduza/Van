"""Local deletion workflow. Registry DATA and existing account journal owners.

No provider calls beyond existing read-only retirement observations, no standing
permission, and no credential work at archive time. Unknown original effects
remain unknown. Reassignment is intentionally unavailable (BE009).
"""
from dataclasses import asdict,replace
from pathlib import Path
import json,time
from fastapi import HTTPException
from vati.core.canonical import canonical_hash
from vati.accounts.registry import AccountRegistry,Account,CredentialRef
from vati.accounts.lifecycle import public_record
from commander.account_effects import (AccountEffectJournal,operation_intent,invoke_account_effect,
    mark_account_effect,require_current_account_effect,AccountOperationBlocked)
from commander.account_retirement import retirement_scope,credential_cleanup

VARIANTS={'DELETE_GRACE','CANCEL_DELETE'}

def _check_source_after_waits(blocking_checks, source_check, pure_time_check):
    """Finish all existing blocking checks before the final source binding.

    Only the existing pure deadline predicates follow that final read. This
    helper issues no permission and performs no effect; callbacks retain their
    original owners and checks.
    """
    for check in blocking_checks:
        check()
    source_check()
    pure_time_check()

def semantic(args):
    return {k:v for k,v in args.items() if not k.startswith('_') and k not in {'reauth_fact_id','reauth_fact_digest'}}

def selected_sessions(settings,account):
    """Explicit native configuration sources, never caller paths or a scan.

    None/empty is not a claim that there are no assignments. Deployment still
    needs qualification of this exact configured scope; no estate discovery.
    """
    sources=settings.lifecycle_session_sources
    if not isinstance(sources,tuple) or not 1<=len(sources)<=32:raise HTTPException(409,'Native configured strategy scope unavailable; HOLD')
    seen=set();selected=set();proofs=[]
    for source in sources:
        if not isinstance(source,tuple) or len(source)!=2:raise HTTPException(409,'Native strategy source binding unavailable')
        filename,expected=source;path=Path(filename)
        if path.is_symlink() or not path.is_file() or path.resolve() in seen:raise HTTPException(409,'Native strategy source ambiguous')
        if path.stat().st_size>131072:raise HTTPException(409,'Native strategy source exceeds admitted bound')
        seen.add(path.resolve());raw=path.read_bytes()
        import hashlib
        observed=hashlib.sha256(raw).hexdigest()
        if observed!=expected:raise HTTPException(409,'Native strategy configuration changed; HOLD')
        # Use the actual production parser, not an alias-only JSON heuristic.
        from vati.app.service import ServiceConfig
        cfg=ServiceConfig.from_bytes(raw)
        if str(Path(cfg.registry_path).resolve())!=str(Path(settings.registry_path).resolve()):
            raise HTTPException(409,'Native strategy registry scope differs; HOLD')
        if cfg.account_alias==account.alias:
            ids=list(cfg.capsules)
            for spec in cfg.instruments:ids.extend(spec.get('capsules',cfg.capsules))
            if any(not isinstance(s,str) or not s for s in ids):raise HTTPException(409,'Native strategy selection unreadable')
            selected.update(ids)
        proofs.append({'source_ref':canonical_hash(str(path.resolve())),'sha256':observed,'account_alias':cfg.account_alias})
    return sorted(selected),proofs

class NativeLifecycle:
    def __init__(self,settings,ledger,domain,retirement_review,resource_version,*,clock=None):
        self.st,self.ledger,self.domain,self.retirement_review,self.resource_version=settings,ledger,domain,retirement_review,resource_version
        self.clock=clock or (lambda:int(time.time()))
    def registry(self):return AccountRegistry(self.st.registry_path)
    def row(self,alias):
        value=self.registry()._lifecycles.get(alias)
        if value is None:raise HTTPException(404,'No original local deletion')
        return value
    def require_original(self,row):
        # Metadata cannot turn an original UNKNOWN/null into APPLIED. A genuine
        # existing sealed cleanup-child resolution is a separate postcondition.
        journal=AccountEffectJournal(self.ledger,cleanup_secrets_root=self.st.secrets_dir)
        state=journal.status(row['operation_id'],row['device_id'])
        if (state is None or state.intent.command!='account_remove' or state.intent.resource_version!=row['incarnation']
                or state.intent.request_digest!=canonical_hash(row['original_request'])
                or 'account:'+row['alias'] not in state.intent.targets
                or 'account-control-domain:'+row['account_control_domain'] not in state.intent.targets):
            raise HTTPException(409,'Original deletion binding requires reconciliation; HOLD')
        if state.phase=='APPLIED' and isinstance(state.result,dict) and state.result.get('lifecycle')==public_record(row):return state
        if state.phase=='UNKNOWN' and state.result is None and journal._resolved_safety_obligation(state):
            from commander.account_cleanup import UnlinkRecoveryBook
            plan=UnlinkRecoveryBook(self.ledger,initialize=False,secrets_root=self.st.secrets_dir)._history(row['operation_id'])['plan']
            restored=Account(**{**row['restore'],'credential_ref':CredentialRef(**row['restore']['credential_ref'])})
            if plan is not None and canonical_hash(restored.public())==plan.payload['data']['account_public_digest']:
                return state
        raise HTTPException(409,'Original deletion outcome/evidence requires reconciliation; HOLD')

    def reconcile_metadata(self,alias):
        row=self.row(alias)
        if row['phase']!='DELETING':return False
        self.require_original(row) # Only the qualified separate child can do this.
        def update(cur):
            if cur._lifecycles.get(alias)!=row or alias in cur.accounts:
                raise HTTPException(409,'Original lifecycle changed during metadata reconciliation')
            cur._lifecycles[alias]={**row,'phase':'PENDING_ARCHIVE','revision':row['revision']+1}
        def current_data_scope():
            if row["account_control_domain"]!=self.domain(self.ledger):raise HTTPException(409,"Original lifecycle native scope changed")
            self.require_original(row)
        self.registry().lifecycle_update(alias,update,before_replace=current_data_scope,advance_resource=False)
        return True

    def remote_state(self,row):
        # Local unlink's remote_account_closed=False means VAN did not close the
        # broker account, not proof that a broker cannot have closed it later.
        # Real-account cancellation therefore requires an independent native
        # observer; missing/expired/unknown evidence HOLDS without secrets.
        if row['restore']['broker']=='PAPER':return {'state':'NOT_APPLICABLE','source_ref':row['incarnation']},None
        reader=self.st.lifecycle_remote_state_reader
        if not callable(reader):raise HTTPException(409,'Independent broker closure observation unavailable; HOLD')
        start=int(time.time()*1000)
        value=reader({'alias':row['alias'],'incarnation':row['incarnation'],
            'account_control_domain':row['account_control_domain']})
        now=int(time.time()*1000)
        import re
        if (not isinstance(value,dict) or set(value)!={'alias','incarnation','account_control_domain','state','source_ref','observed_at_ms'}
                or any(value[k]!=row[k] for k in ('alias','incarnation','account_control_domain'))
                or value['state']!='OPEN' or not isinstance(value['source_ref'],str)
                or re.fullmatch('[0-9a-f]{64}',value['source_ref']) is None
                or type(value['observed_at_ms']) is not int
                or not 0<=now-value['observed_at_ms']<=30000 or not 0<=now-start<=30000):
            raise HTTPException(409,'Broker closure/currentness unknown or closed; HOLD')
        return {'state':'OPEN','source_ref':value['source_ref']},value['observed_at_ms']+30000

    def review(self,args,device,read_guard,*,inside=False):
        if not callable(read_guard):raise HTTPException(403,'Current native lifecycle owner scope unavailable')
        read_guard();a=semantic(args);alias=a.get('alias');variant=a.get('variant')
        if variant not in VARIANTS:raise HTTPException(422,'Unknown local lifecycle operation')
        domain=self.domain(self.ledger)
        if variant=='DELETE_GRACE':
            if set(a)!={'alias','variant','grace_seconds','oauth_discard_digest'} or type(a['grace_seconds']) is not int or not 0<a['grace_seconds']<2**31:
                raise HTTPException(422,'Explicit positive owner-selected grace required; no default')
            registry=self.registry();account=registry.get(alias)
            if alias in registry._lifecycles:raise HTTPException(409,'Original deletion/detachment must be reconciled; no replacement')
            strategies,sources=selected_sessions(self.st,account)
            unlink=self.retirement_review({**semantic(args),**({"_native_operation":args["_native_operation"]} if "_native_operation" in args else {})},inside_removal=inside,native_ledger=self.ledger)
            cleanup,_=credential_cleanup(self.st,registry,account)
            if cleanup in {'KEEP_SHARED','KEEP_EXTERNAL'}:raise HTTPException(409,'Credential destruction cannot be proven for this account; HOLD')
            value={'variant':variant,'grace_seconds':a['grace_seconds'],'strategies':strategies,'session_sources':sources,
                'unlink_review':unlink,'incarnation':unlink['resource_version'],'account_control_domain':domain,
                'owner_device_id':device,'credential_disposition':cleanup}
        else:
            if set(a)!={'alias','variant','lifecycle_id','expected_revision','expected_digest'}:raise HTTPException(422,'Exact original deletion revision required')
            row=self.row(alias)
            if (row['operation_id']!=a['lifecycle_id'] or row['revision']!=a['expected_revision']
                    or canonical_hash(row)!=a['expected_digest'] or row['device_id']!=device
                    or row['account_control_domain']!=domain):raise HTTPException(409,'Original deletion scope/version changed')
            if row['phase']!='PENDING_ARCHIVE' or self.clock()>=row['archive_at_unix']:raise HTTPException(409,'Deletion cannot be cancelled in this state')
            self.require_original(row)
            # Cancellation is metadata-only, never a statement that broker access
            # is live. No provider-closed account is reconstructed as active.
            if row['remote_account_closed'] is not False:raise HTTPException(409,'Broker closure blocks restoration')
            remote,_=self.remote_state(row)
            value={'variant':variant,'original':public_record(row),'account_control_domain':domain,'owner_device_id':device,'remote_state':remote}
        read_guard()
        body={'schema':'vati.account-lifecycle-review/1','action':'account_remove','alias':alias,
            'resource_version':self.resource_version(alias),'semantic_digest':canonical_hash(a),'view':value}
        body['context_digest']=canonical_hash(body)
        # Existing prospective unlink plans bind this raw native review digest.
        # Full lifecycle context (including strategy selection) is independently
        # parameter-bound by A4 and rechecked by the dispatch writer below.
        binding_digest=value['unlink_review']['review_digest'] if variant=='DELETE_GRACE' else canonical_hash(body)
        return {**body,'request_digest':canonical_hash({k:v for k,v in args.items() if not k.startswith('_')}),
                'review_digest':binding_digest}
    def execute(self,args,guard):
        if not callable(guard):raise HTTPException(403,'Current lifecycle actor required')
        intent=operation_intent('account_remove',args)
        domain=self.domain(self.ledger)
        if domain!=args.get('_expected_account_control_domain'):raise AccountOperationBlocked('Lifecycle native domain changed')
        def current():
            guard()
            if self.domain(self.ledger)!=domain:raise AccountOperationBlocked('Lifecycle native domain changed')
            guard()
        def effect():
            alias=args['alias']
            with retirement_scope(self.st,alias) as lease,self.registry().operation_lock(alias):
                def final_times():
                    # Pure clock predicates only: reused immediately AFTER a
                    # credential fstat, with no subsequent blocking callback.
                    from commander import account_effects as effect_context
                    lease.check_time()
                    if int(effect_context.time.time())>=intent.expires_at_unix:
                        raise HTTPException(403,'Original lifecycle permission expired before native effect')
                def final():
                    current();lease();require_current_account_effect();final_times()
                final.check_time=final_times
                review=self.review(args,intent.device_id,current,inside=True)
                if (review['review_digest']!=args.get('_expected_review_digest')
                    or review['resource_version']!=intent.resource_version
                    or review['context_digest']!=args.get('_expected_lifecycle_context_digest')):raise HTTPException(409,'Lifecycle review changed since approval')
                final()
                if args['variant']=='CANCEL_DELETE':return self.cancel(args,intent,final)
                return self.delete(args,intent,review,final)
        return invoke_account_effect(AccountEffectJournal(self.ledger,cleanup_secrets_root=self.st.secrets_dir),intent,effect,dispatch_guard=current)
    def delete(self,args,intent,review,guard):
        from commander.accounts import _shred,_file_generation
        from vati.core.file_lock import exclusive_state_lock
        from contextlib import nullcontext
        alias=args['alias'];registry=self.registry();account=registry.get(alias)
        readbacks=[]
        unlink=self.retirement_review({**semantic(args),"_native_operation":args["_native_operation"]},inside_removal=True,native_ledger=self.ledger,readback_guards=readbacks)
        if len(readbacks)!=1:raise HTTPException(409,"Native safety readback unavailable")
        original_guard=guard
        def final_times():
            original_guard.check_time()
            readbacks[0].check_time()
        def guard():
            original_guard()
            readbacks[0]()
            final_times()
        guard.check_time=final_times
        if unlink!=review['view']['unlink_review']:raise HTTPException(409,'Native unlink facts changed')
        disposition,target=credential_cleanup(self.st,registry,account)
        if disposition!=review['view']['credential_disposition']:raise HTTPException(409,'Credential ownership changed')
        oauth=args.get('_lifecycle_oauth')
        if not isinstance(oauth,dict) or set(oauth)!={'digest','request_digest'} or oauth['request_digest']!=canonical_hash(semantic(args)) or oauth['digest']!=args['oauth_discard_digest']:
            raise HTTPException(409,'Exact gateway OAuth discard evidence unavailable')
        now=self.clock();incarnation=review['view']['incarnation']
        row={'schema':'vati.account-lifecycle/1','alias':alias,'operation_id':intent.operation_id,'device_id':intent.device_id,
            'account_control_domain':review['view']['account_control_domain'],'incarnation':incarnation,
            'revision':1,'phase':'DELETING','created_at_unix':now,'grace_seconds':args['grace_seconds'],
            'archive_at_unix':now+args['grace_seconds'],'restore':asdict(account),
            'strategies':review['view']['strategies'],'session_sources':review['view']['session_sources'],
            'history_ref':unlink['retirement']['trade_history_ref'],'credential_disposition':disposition,
            'unlink_ref':unlink['review_digest'],'oauth_discard_ref':oauth['digest'],'detached':True,
            'link_intent':'RELINK_REQUIRED','remote_account_closed':False,
            'original_request':{k:v for k,v in args.items() if not k.startswith('_')}}
        def source_current():
            if selected_sessions(self.st,account)!=(row['strategies'],row['session_sources']):
                raise HTTPException(409,'Strategy source changed at protected deletion boundary')
        def mark_pure():
            guard.check_time()
            mark_account_effect()
        def before():
            _check_source_after_waits((guard,),source_current,guard.check_time)
            mark_pure()
        with registry._mutation_lock(), (exclusive_state_lock(target) if target is not None else nullcontext()):
            # Re-read after potentially waiting locks; no carried file identity.
            fresh=self.registry()
            if self.resource_version(alias)!=intent.resource_version:raise HTTPException(409,'Native resource changed before deletion')
            if selected_sessions(self.st,fresh.get(alias))!=(row['strategies'],row['session_sources']):raise HTTPException(409,'Strategy source changed before deletion')
            # Publish persistent detachment DATA before a recoverable plan can
            # exist. A crash or lost ACK before the account-removal replacement
            # must not let a genuine legacy cleanup child lose this incarnation's
            # marker. This changes registry FILE bytes, not account revision or
            # credential identity, and grants no execution/reassignment rights.
            def reserve(cur):
                if alias in cur._lifecycles or cur.accounts.get(alias)!=account:
                    raise HTTPException(409,'Original lifecycle or account changed before reservation')
                cur._lifecycles[alias]=row
            def reservation_before():
                if self.resource_version(alias)!=intent.resource_version:
                    raise HTTPException(409,'Native resource changed before lifecycle reservation')
                if selected_sessions(self.st,account)!=(row['strategies'],row['session_sources']):
                    raise HTTPException(409,'Strategy source changed before lifecycle reservation')
                _check_source_after_waits((guard,),source_current,guard.check_time)
                mark_pure()
            registry.lifecycle_update(alias,reserve,before_replace=reservation_before,advance_resource=False)
            fresh=self.registry()
            if self.resource_version(alias)!=intent.resource_version:
                raise HTTPException(409,'Original logical resource changed after lifecycle reservation')
            generation=_file_generation(target.stat()) if target is not None else None
            from commander.account_cleanup import UnlinkRecoveryBook,prepare_plan
            book=UnlinkRecoveryBook(self.ledger,secrets_root=self.st.secrets_dir)
            plan=prepare_plan(self.st,fresh,account,unlink,target)
            plan['account_control_domain']=row['account_control_domain']
            plan_ref,epoch=book.prepare(intent,plan)
            def protected():
                # Preserve the existing source sample and every actor, lease,
                # readback and epoch check. Their waits can invalidate that
                # sample, so check the actual source binding again LAST.
                # Only existing pure times follow; _shred still performs its
                # physical identity fstat afterward, with clock-only marking.
                guard()
                if selected_sessions(self.st,account)!=(row['strategies'],row['session_sources']):
                    raise HTTPException(409,'Strategy source changed at protected deletion boundary')
                _check_source_after_waits((guard,
                    lambda:book.require_epoch(intent.operation_id,plan_ref,epoch,intent.operation_id),guard),
                    source_current,guard.check_time)
            def step(name,state,**kw):
                # Existing sealed technical schema requires a JSON list, while
                # the actual shred owner returns its immutable stat tuple.
                if kw.get('post_generation') is not None:kw['post_generation']=list(kw['post_generation'])
                book.step(intent.operation_id,plan_ref,epoch,intent.operation_id,name,state,**kw)
            def registry_before():
                if self.resource_version(alias)!=intent.resource_version:raise HTTPException(409,'Native account changed at registry replacement')
                protected();step('REGISTRY_REMOVE','MAY_BEGIN');protected();mark_pure()
            def registry_after():
                step('REGISTRY_REMOVE','DONE',resource_version=self.resource_version(alias))
            def prepare(cur):
                if cur._lifecycles.get(alias)!=row or cur.accounts.get(alias)!=account:
                    raise HTTPException(409,'Original reserved lifecycle or account changed')
                cur.accounts.pop(alias)
            registry.lifecycle_update(alias,prepare,before_replace=registry_before,after_replace=registry_after)
            removed_version=self.resource_version(alias)
            def credential_guard():
                if self.resource_version(alias)!=removed_version:raise HTTPException(409,'Native account changed after original unlink')
                protected()
            def overwrite_before():
                credential_guard();step('CREDENTIAL_OVERWRITE','MAY_BEGIN');credential_guard()
            def overwrite_after(own_generation):
                step('CREDENTIAL_OVERWRITE','DONE',post_generation=own_generation,resource_version=removed_version)
            def unlink_before():
                credential_guard();step('CREDENTIAL_UNLINK','MAY_BEGIN');credential_guard()
            def unlink_after():step('CREDENTIAL_UNLINK','DONE',resource_version=removed_version)
            if target is not None:_shred(target,expected_generation=generation,before_write=overwrite_before,
                before_unlink=unlink_before,before_effect=mark_pure,after_write=overwrite_after,after_unlink=unlink_after)
            def done(cur):
                old=cur._lifecycles[alias]
                if old!=row:raise HTTPException(409,'Lifecycle changed during credential cleanup')
                cur._lifecycles[alias]={**old,'phase':'PENDING_ARCHIVE','revision':2}
            registry.lifecycle_update(alias,done,before_replace=before,advance_resource=False)
        return {'lifecycle':public_record(self.row(alias)),'removed':True,'remote_account_closed':False,'historical_data_retained':True}
    def cancel(self,args,intent,guard):
        alias=args['alias'];row=self.row(alias)
        _,remote_deadline=self.remote_state(row)
        def update(cur):
            current=cur._lifecycles.get(alias)
            if current!=row or current['phase']!='PENDING_ARCHIVE' or self.clock()>=current['archive_at_unix']:
                raise HTTPException(409,'Original deletion changed or grace expired')
            if alias in cur.accounts:raise HTTPException(409,'Alias was reused; original cancellation cannot overwrite it')
            restored=Account(**{**current['restore'],'credential_ref':CredentialRef(**current['restore']['credential_ref'])})
            cur.accounts[alias]=replace(restored,enabled=False,mode='OBSERVE',mandate_ref='')
            cur._lifecycles[alias]={**current,'phase':'RELINK_REQUIRED','restore':None,'revision':current['revision']+1}
        def before():
            guard()
            if self.clock()>=row["archive_at_unix"] or remote_deadline is not None and int(time.time()*1000)>=remote_deadline:
                raise HTTPException(409,"Cancellation grace or broker readback expired before metadata replacement")
            guard.check_time()
            mark_account_effect()
        self.registry().lifecycle_update(alias,update,before_replace=before)
        return {'lifecycle':public_record(self.row(alias)),'removed':False,'remote_account_closed':False,'historical_data_retained':True}
    def read(self,alias,device,guard):
        guard();row=self.row(alias)
        if row['device_id']!=device or row['account_control_domain']!=self.domain(self.ledger):raise HTTPException(403,'Original lifecycle is outside current owner/domain')
        held=None
        try:
            if row['phase']=='DELETING':self.reconcile_metadata(alias)
            self.archive_due(alias)
        except HTTPException as error:
            if error.status_code!=409:raise
            held='ORIGINAL_OUTCOME_REQUIRES_RECONCILIATION'
        state=AccountEffectJournal(self.ledger,cleanup_secrets_root=self.st.secrets_dir).status(row['operation_id'],row['device_id'])
        guard();result=public_record(self.row(alias))
        result['native_original_phase']=state.phase if state is not None else 'UNKNOWN'
        if held is not None:result['metadata_hold']=held
        return result
    def archive_due(self,alias):
        """Metadata-only CAS under the original admitted data intent.

        Never shreds credentials, sends a provider call, clears detachment or
        alters native history. Partial DELETING never ages into success.
        """
        registry=self.registry();row=registry._lifecycles.get(alias)
        if row is None or row['phase']!='PENDING_ARCHIVE' or self.clock()<row['archive_at_unix']:return False
        if row['account_control_domain']!=self.domain(self.ledger):raise HTTPException(409,'Original lifecycle native domain changed; HOLD')
        self.require_original(row)
        def update(cur):
            original=cur._lifecycles.get(alias)
            if original!=row or self.clock()<original['archive_at_unix']:raise HTTPException(409,'Lifecycle changed at archive arbitration')
            cur._lifecycles[alias]={**row,'phase':'ARCHIVED','restore':None,'session_sources':[],
                'revision':row['revision']+1}
        def current_data_scope():
            if row["account_control_domain"]!=self.domain(self.ledger):raise HTTPException(409,"Original lifecycle native scope changed")
            self.require_original(row)
        registry.lifecycle_update(alias,update,before_replace=current_data_scope,advance_resource=False)
        return True


def configured_session_scope(filename,registry_path):
    """Load only explicit native-owned source selectors; this is NOT a grant.

    No directory enumeration, default paths, bool 'approved' flag, deployment
    edits or new signing authority. A missing binding leaves source unavailable.
    The actual configured scope still needs deployment/provider qualification.
    """
    if not filename:return None
    import os,stat,re
    path=Path(filename)
    if path.is_symlink():raise ValueError('Native session scope cannot be a symlink')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077 or info.st_size>131072:
            raise ValueError('Native session scope must be bounded private owner configuration')
        raw=stream.read(131073)
    value=json.loads(raw)
    if (not isinstance(value,dict) or set(value)!={'schema','registry_path','sources'}
            or value['schema']!='vati.account-session-scope/1'
            or Path(value['registry_path']).resolve()!=Path(registry_path).resolve()
            or not isinstance(value['sources'],list) or not 1<=len(value['sources'])<=32):
        raise ValueError('Native configured session scope is incomplete or foreign')
    result=[]
    for item in value['sources']:
        if (not isinstance(item,dict) or set(item)!={'path','sha256'} or not isinstance(item['path'],str)
                or not Path(item['path']).is_absolute() or not isinstance(item['sha256'],str)
                or re.fullmatch('[0-9a-f]{64}',item['sha256']) is None):raise ValueError('Native session source selector invalid')
        result.append((item['path'],item['sha256']))
    if len({Path(p).resolve() for p,_ in result})!=len(result):raise ValueError('Native session scope has duplicate selectors')
    return tuple(result)
