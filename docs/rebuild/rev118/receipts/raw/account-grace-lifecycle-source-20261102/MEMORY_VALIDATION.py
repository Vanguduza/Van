"""NON-SENSITIVE in-memory callback validation. No product imports or effects.

Compile only actual source guard functions, with all source/owner/epoch/time
callbacks replaced by ordinary Python state. No account, credential, provider,
network, integrity key, or filesystem lock operation is called by a case.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import zipfile

R=Path(__file__).resolve().parents[1]
P='trading/commander/account_lifecycle.py'
current=(R/'source'/P).read_bytes()
with zipfile.ZipFile(R/'FROZEN_SOURCE_R4/SOURCE21.zip') as archive:
    old=archive.read(P)


def function(raw,name):
    tree=ast.parse(raw)
    if name=='_check_source_after_waits':
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    else:
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='NativeLifecycle')
        deletion=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='delete')
        nodes=[n for n in ast.walk(deletion) if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(nodes)==1,(name,len(nodes))
    return copy.deepcopy(nodes[0])


# Static retention: the actual pure mark, composite actor/readback guard, pure
# times, credential callbacks and the physical helper invocation are unchanged.
unchanged=[]
for name in ('mark_pure','final_times','credential_guard','overwrite_before','overwrite_after','unlink_before','unlink_after'):
    # final_times has multiple local definitions; compare all in source order.
    values=lambda raw:[ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.FunctionDef) and n.name==name]
    assert values(old)==values(current),name
    unchanged.append(name)
shred=lambda raw:[ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_shred']
assert shred(old)==shred(current)


class Refused(Exception):
    pass


class Memory:
    pass


def execute(label,*,version='current',entry='protected',mutate=None,negative=None):
    state={'source':'A','owner':True,'epoch':True,'now':0,'lease_until':10,'permission_until':10,'readback_until':10}
    trace=[];guard_count=[0];source_count=[0]
    if negative in ('owner','epoch'):
        state[negative]=False
    if negative in ('lease','permission','readback'):
        state[negative+'_until']=0

    def pure_time():
        trace.append('pure_time')
        for name in ('lease','permission','readback'):
            if state['now']>=state[name+'_until']:
                raise Refused(name+'_expired')

    def guard():
        trace.append('guard');guard_count[0]+=1
        if not state['owner']:
            raise Refused('owner_not_current')
        if mutate=='last_guard' and guard_count[0]==3 or mutate=='reservation_guard' and guard_count[0]==1:
            state['source']='B'
        pure_time()
    guard.check_time=pure_time

    def selected(*unused):
        trace.append('source');source_count[0]+=1
        if mutate=='source_error':
            raise Refused('source_unavailable')
        if mutate=='final_source_time' and source_count[0]>=2:
            state['now']=10
        return ([state['source']],[])

    def epoch_check(*unused):
        trace.append('epoch')
        if not state['epoch']:
            raise Refused('epoch_changed')
        if mutate=='epoch':
            state['source']='B'

    holder=Memory();holder.st='IN_MEMORY_ONLY'
    def resource(*unused):
        trace.append('resource')
        return 'REV_A'
    holder.resource_version=resource
    intent=Memory();intent.operation_id='IN_MEMORY_ONLY';intent.resource_version='REV_A'
    book=Memory();book.require_epoch=epoch_check
    namespace={'__builtins__':{},'guard':guard,'selected_sessions':selected,'self':holder,
        'account':None,'row':{'strategies':['A'],'session_sources':[]},'book':book,
        'intent':intent,'plan_ref':'IN_MEMORY_ONLY','epoch':1,'alias':'IN_MEMORY_ONLY',
        'HTTPException':Refused,'mark_account_effect':lambda:trace.append('effect_mark_stub')}
    raw=current if version=='current' else old
    names=[entry]
    if version=='current':
        names=['_check_source_after_waits','source_current','mark_pure',entry]
    elif entry!='protected':
        names=['mark_pure',entry]
    nodes=[function(raw,name) for name in dict.fromkeys(names)]
    prohibited=(ast.Import,ast.ImportFrom,ast.With,ast.AsyncWith,ast.Await,ast.Global,ast.Nonlocal)
    assert not any(isinstance(n,prohibited) for node in nodes for n in ast.walk(node))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual-source-guard-memory-only>','exec'),namespace)
    refused=None
    try:
        namespace[entry]()
        trace.append('effect_stub')
    except Refused as error:
        refused=str(error)
    allowed='effect_stub' in trace
    if version=='current' and allowed:
        last=max(i for i,item in enumerate(trace) if item=='source')
        assert not set(trace[last+1:])&{'guard','epoch','resource'},trace
        assert 'pure_time' in trace[last+1:],trace
    return {'case':label,'entry':entry,'version':version,'allowed_stub':allowed,'refusal':refused,'trace':trace}


cases=[]
def check(label,expected,**kwargs):
    result=execute(label,**kwargs)
    assert result['allowed_stub'] is expected,result
    if not expected:
        assert 'effect_mark_stub' not in result['trace'],result
    cases.append(result)

# Historical production order, in memory only: a later callback changes the
# source after its first sample. This is a retained counterexample, not a fix.
check('R4_later_epoch_callback_exposes_stale_sample',True,version='old',mutate='epoch')
check('R5_stable_source_all_guards_allow_stub',True)
check('R5_later_epoch_changes_source_refuses_stub',False,mutate='epoch')
check('R5_last_owner_callback_changes_source_refuses_stub',False,mutate='last_guard')
for predicate in ('owner','epoch','lease','permission','readback'):
    check('R5_'+predicate+'_negative_still_refuses',False,negative=predicate)
check('R5_final_source_callback_advances_deadline_refuses',False,mutate='final_source_time')
check('R5_source_unavailable_refuses_stub',False,mutate='source_error')
check('R5_reservation_stable_source_allows_stub',True,entry='reservation_before')
check('R5_reservation_post_sample_callback_change_refuses',False,entry='reservation_before',mutate='reservation_guard')
check('R5_completion_stable_source_allows_stub',True,entry='before')
check('R5_completion_post_sample_callback_change_refuses',False,entry='before',mutate='reservation_guard')

result={'method':'Actual source AST guard functions with NON-SENSITIVE in-memory callbacks/state ONLY',
    'source_sha256':hashlib.sha256(current).hexdigest(),'historical_R4_source_sha256':hashlib.sha256(old).hexdigest(),
    'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':len(cases),'passed':len(cases),
    'cases':cases,'static_unchanged_functions':unchanged,'physical_helper_call_ast_unchanged':True,
    'no_product_imports_or_account_credential_key_lock_provider_network_operations':True,
    'scope':'Ordering/control-flow only. No active native/credential probe or feature suite run; no production/native/provider/integration qualification.'}
print(json.dumps(result,indent=2))
