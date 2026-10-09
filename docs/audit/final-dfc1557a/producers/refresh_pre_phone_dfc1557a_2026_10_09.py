from pathlib import Path
import ast, copy, datetime, hashlib, json, subprocess

ROOT=Path('/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09')
REV='dfc1557ab99ad8d41cf84714e1bb671e89b045e6'
OLD_DOC=Path('/workspace/van-audit/VAN_PRE_PHONE_CANARY_CHECKLIST_805F3B67_2026-10-09.md')
OLD_INV=Path('/workspace/van-audit/van-pre-phone-canary-source-and-skip-inventory-805f3b67-2026-10-09.json')
NEW_DOC=Path('/workspace/van-audit/VAN_PRE_PHONE_CANARY_CHECKLIST_DFC1557A_2026-10-09.md')
NEW_INV=Path('/workspace/van-audit/van-pre-phone-canary-source-and-skip-inventory-dfc1557a-2026-10-09.json')
PRIOR_RESULT=Path('/workspace/van-audit/canon-corrected-backend-full-805f3b67-2026-10-09-result.json')
CURRENT_PREFIX='/workspace/van-audit/canon-corrected-backend-full-dfc1557a-2026-10-09'
CURRENT_INPUTS=Path(CURRENT_PREFIX+'-inputs.json')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
assert not NEW_DOC.exists() and not NEW_INV.exists(), 'immutable output paths already exist'
assert git('rev-parse','HEAD')==REV and git('status','--porcelain=v1')==''
old_hashes={str(p):sha(p) for p in [OLD_DOC,OLD_INV,PRIOR_RESULT]}
old=json.loads(OLD_INV.read_text())
prior=json.loads(PRIOR_RESULT.read_text())
current_inputs=json.loads(CURRENT_INPUTS.read_text())
assert prior['complete_run'] is True and prior['qualified_as_full_backend_pass'] is False
assert prior['counts']['passed']==5100 and prior['counts']['failed']==2 and prior['counts']['skipped']==5
assert current_inputs['revision']==REV and len(current_inputs['files'])==4015
assert not Path(CURRENT_PREFIX+'-result.json').exists(), 'full outcomes no longer pending; review actual outcome first'
extra=[
'backend/tests/test_harness_pseudo_hit_ownership.py',
'backend/van_gateway/browser/task_scope.py',
'backend/tests/fixtures/task_scope/url_vectors.v1.json',
'deploy/van-browser-core/browser/egress_proxy.py',
'deploy/van-browser-core/browser/harness_service.py',
'tests/contracts/test_task_scope_shared_url_rule.py',
]
paths=sorted(set(old['input_files'])|set(extra))
before={p:sha(ROOT/p) for p in paths}

# Inventory the original pytest skip call sites from the final source AST, not old line numbers.
def dotted(node):
    if isinstance(node,ast.Name):return node.id
    if isinstance(node,ast.Attribute):return dotted(node.value)+'.'+node.attr
    return ''
skips=[]
for path in sorted((ROOT/'backend/tests').rglob('*.py')):
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'),filename=str(path))):
        if isinstance(node,ast.Call) and dotted(node.func) in {'pytest.skip','pytest.mark.skip','pytest.mark.skipif'}:
            skips.append({'path':str(path.relative_to(ROOT)),'line':node.lineno,'call':ast.unparse(node)})
skips.sort(key=lambda item:(item['path'],item['line']))
assert len(skips)==16
assert not any(s['path']=='backend/tests/test_harness_pseudo_hit_ownership.py' for s in skips)

text=OLD_DOC.read_text().replace('805f3b67c2b9eb68d887cd700f9443f476e26132',REV)
start=text.index('The authoritative full backend run must use the final corrected source.')
end=text.index('The current backend selection is exactly `backend/tests`',start)
section='''The authoritative full backend selection is the clean final
`dfc1557ab99ad8d41cf84714e1bb671e89b045e6`. Its full-run outcomes are **PENDING**
as of this checklist's creation. The new runner uses short `/tmp/vbf-dfc1557a`
and separate immutable receipt prefix
`/workspace/van-audit/canon-corrected-backend-full-dfc1557a-2026-10-09`.
Do not substitute an earlier candidate, a focused pass, or running progress for
this exact final run's completed JUnit/terminal outcomes.

The preceding 805f3b67 full run completed: **5,100 passed, 2 failed, 5 skipped**,
with zero errors or expected failures. Its source and installed dependencies
remained unchanged. This is a complete diagnostic run, not a complete pass. It
exposed two reproducible browser runtime defects: the shared URL parser decoded
encoded dots inside a nondot path segment differently from Chromium, and the
Harness center hit test treated a directly owned CSS pseudo-element as an
unrelated node. Both runtime defects are corrected in the final frozen source;
the original major-5 and major-3 Chromium regression assertions remain intact.
The new pseudo ownership test file adds 17 real-Chromium guarded-click, foreign
normal/pseudo overlay, nested control, late-overlay and live-CDP fault regressions.
The selected-source focused receipt is separate from full backend acceptance.

Earlier candidates remain historical diagnostics. The 4ad run was interrupted
after 440 completed passes; 7526d3e9 was deliberately interrupted after 693 passes
for a stale services-test assertion and README/registry metadata correction.
The 8d0104f5 run was interrupted with 1,192 terminal-confirmed passes, 8 failures,
36 errors and 1 prerequisite skip. Its 44 failure/error records reported AF_UNIX
paths exceeding the Linux limit because the outside runner chose a long temporary
root; one unfinished unannotated JUnit record is unknown. The same first-error
case passed unchanged using a short `/tmp` root. No source assertion or runtime
behavior was weakened to resolve that runner mistake.

'''
text=text[:start]+section+text[end:]
text=text.replace('The current backend selection is exactly `backend/tests`, with all tracked source,', 'The current backend selection is exactly `backend/tests`, with all 4,015 tracked source,')
assert 'SM-S928B' in text and 'RFCX2054F5W' in text and 'No Windows USB prerequisite' in text
assert '--expected-sha '+REV in text
assert 'Final 805f3b67 qualification uses' not in text
NEW_DOC.write_text(text)

inv=copy.deepcopy(old)
inv.update({
'reviewed_revision':REV,
'source_checkout':str(ROOT),
'recorded_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
'checklist_path':str(NEW_DOC),
'checklist_sha256':sha(NEW_DOC),
'input_files':before,
'input_file_count':len(before),
'new_source_binding_paths':extra,
'changed_existing_source_binding_paths':[p for p,h in old['input_files'].items() if before[p]!=h],
'existing_skip_calls':skips,
'existing_skip_call_count':len(skips),
'skip_inventory_method':'Python AST Call locations over every backend/tests/**/*.py in the final clean checkout',
'current_corrected_freeze_pending':False,
'final_backend_outcomes_pending':True,
'final_backend_outcome_status':'PENDING',
'final_backend_receipt_prefix':CURRENT_PREFIX,
'final_backend_basetemp':'/tmp/vbf-dfc1557a',
'final_backend_inputs_path':str(CURRENT_INPUTS),
'final_backend_inputs_sha256':sha(CURRENT_INPUTS),
'final_backend_input_file_count':len(current_inputs['files']),
'final_backend_terminal_outcomes':None,
'previous_diagnostic_inventory_path':str(OLD_INV),
'previous_diagnostic_inventory_sha256':sha(OLD_INV),
'previous_diagnostic_checklist_path':str(OLD_DOC),
'previous_diagnostic_checklist_sha256':sha(OLD_DOC),
'prior_805f_backend_evidence':{
    'revision':prior['revision'],'status':'COMPLETE_DIAGNOSTIC_WITH_FAILURES',
    'complete_run':True,'qualified_as_full_backend_pass':False,
    'counts':prior['counts'],'terminal_pytest_outcomes':prior['terminal_pytest_outcomes'],
    'exit_code':prior['exit_code'],'source_unchanged':prior['source_unchanged_during_test'],
    'installed_dependencies_unchanged':prior['installed_dependencies_unchanged_during_test'],
    'receipt_path':str(PRIOR_RESULT),'receipt_sha256':sha(PRIOR_RESULT),
    'failure_cases':[{'classname':f['classname'],'name':f['name']} for f in prior['failures']],
    'failures_corrected_in_final_source':True,
},
'final_browser_runtime_corrections':{
    'shared_url_parser':'Preserve encoded nondot segments to match Chromium; ambiguous encoded delimiters remain refused',
    'pseudo_hit_ownership':'Fresh exact direct before/after CDP ownership only; foreign overlay and nested control hits retain rejection',
    'new_real_chromium_regression_file':extra[0],
    'new_regression_file_sha256':before[extra[0]],
    'new_regression_case_count':17,
    'new_regression_adds_environment_skips':False,
},
'observed_environment_origin_inventory':str(OLD_INV),
'observed_environment_are_prior_local_executor_observations':True,
'pre_phone_ready_claimed':False,'production_deployed':False,
'host_calls_executed':0,'provider_calls_executed':0,'handset_tests_executed':0,
'source_status_after':git('status','--porcelain=v1'),
})
after={p:sha(ROOT/p) for p in paths}
assert before==after and git('rev-parse','HEAD')==REV and git('status','--porcelain=v1')==''
assert old_hashes=={str(p):sha(p) for p in [OLD_DOC,OLD_INV,PRIOR_RESULT]}
inv['source_hashes_unchanged_during_inventory_refresh']=True
inv['previous_immutable_receipts_unchanged']=True
NEW_INV.write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n')
print(json.dumps({'checklist':str(NEW_DOC),'checklist_sha256':sha(NEW_DOC),'inventory':str(NEW_INV),'inventory_sha256':sha(NEW_INV),'bound_sources':len(before),'skip_calls':len(skips),'source_revision':REV,'source_clean_and_unchanged':True,'old_receipts_unchanged':True,'current_full_backend_outcomes':'PENDING','host_provider_handset_calls':0},indent=2))
