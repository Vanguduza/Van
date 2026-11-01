"""Explicit-input auth evidence finalizer under the root-approved recovery policy. Never run during source repair.
All selected run receipts, pins and counterexamples must be actual retained artifacts.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path('/workspace/van-review-2026-10-18/publish')
WORK=Path('/workspace')
RECEIPT='docs/rebuild/rev118/receipts/AUTH_COMMIT_EXPIRY_SOURCE_20261101.json'
DOC='docs/rebuild/rev118/backend/BE-002_003_AUTH_COMMIT_EXPIRY.md'
RAW='docs/rebuild/rev118/ci/auth_commit_expiry_20261101'
SOURCE=['backend/van_gateway/auth/service.py','backend/tests/test_lane_auth_commit_expiry.py','backend/tests/test_lane_auth_commit_expiry_http.py']

def require(ok,message):
    if not ok:raise RuntimeError(message)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def junit(p, modules=None):
    cases=ET.parse(p).findall('.//testcase')
    if modules is not None:
        cases=[t for t in cases if any(m in t.get('classname','').split('.') for m in modules)]
    failures=[t for t in cases if t.find('failure') is not None]
    errors=[t for t in cases if t.find('error') is not None]
    skipped=[t for t in cases if t.find('skipped') is not None]
    return {'tests':len(cases),'passed':len(cases)-len(failures)-len(errors)-len(skipped),'failures':len(failures),'errors':len(errors),'skipped':len(skipped),
            'skip_cases':[{'name':t.get('classname','')+'.'+t.get('name',''),'reason':t.find('skipped').get('message','')} for t in skipped],
            'failure_cases':[{'name':t.get('classname','')+'.'+t.get('name',''),'messages':[x.get('message','') for x in t if x.tag in ('failure','error')]} for t in failures+errors]}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--full-run-prefix',required=True,type=Path,help='Selected qualifying run prefix for terminal .json, .xml and .log; scope label is explicit')
    ap.add_argument('--qualification-scope', choices=['full-backend', 'affected-callgraph', 'full-backend-sharded', 'full-backend-composite-recovery'], default='full-backend')
    ap.add_argument('--selected-isolated-recovery-dir', type=Path)
    ap.add_argument('--selected-recovery-dir', type=Path)
    ap.add_argument('--remainder-recovery-dir', type=Path)
    ap.add_argument('--collection-dir', type=Path, help='Exact full/selected/remainder collection manifests for sharded coverage')
    ap.add_argument('--remainder-run-prefix', type=Path, help='Disjoint corrected-backend remainder terminal prefix')
    ap.add_argument('--selection-receipt', type=Path, help='Required for affected-callgraph: reviewed exact delta, targets, consumer edges and unchanged-input reuse justification')
    ap.add_argument('--source-pins',required=True,type=Path,help='Final run original source-start hash inventory, files or source_sha256 mapping')
    ap.add_argument('--storage-audit',required=True,type=Path)
    ap.add_argument('--focused-xml',required=True,type=Path)
    ap.add_argument('--new-cases-xml',type=Path,help='Optional alias of focused XML only; new cases are derived by exact module classification')
    ap.add_argument('--handoff',type=Path,default=WORK/'van-auth-midtransaction-handoff-20261101.json')
    ap.add_argument('--source-review',type=Path,default=WORK/'van-family-verification-20261101/auth-final-review.json')
    ap.add_argument('--caller-map',type=Path,default=WORK/'van-auth-midtransaction-caller-map-20261101.json')
    ap.add_argument('--caller-selection',type=Path,default=WORK/'van-auth-midtransaction-affected-selection-20261101.json')
    ap.add_argument('--counterexample-xml',required=True,type=Path,action='append',help='New awaited-lookup failure and any additional real source failures; repeatable')
    ap.add_argument('--extra-evidence',type=Path,action='append',default=[])
    ap.add_argument('--expected-parent',required=True)
    args=ap.parse_args()
    for rel in [RECEIPT,DOC,RAW]:require(not (ROOT/rel).exists(),'Duplicate/partial prior finalization: '+rel)
    parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(parent==args.expected_parent,'Parent moved; reconcile before finalizing')
    terminal=read(args.full_run_prefix.with_suffix('.json'))
    composite_mode = args.qualification_scope == 'full-backend-composite-recovery'
    require(terminal.get('state')=='COMPLETED' and (terminal.get('exit')==0 or composite_mode),'Selected run not terminal or explicit composite mode missing')
    full=junit(args.full_run_prefix.with_suffix('.xml'))
    require(full['tests']>0 and (full['failures']==full['errors']==0 or composite_mode),'Selected full XML has unresolved failures/errors or no cases')
    audit=read(args.storage_audit);require(audit.get('forbidden_events')==[],'Selected audit is not clean')
    pins=read(args.source_pins);hashes=pins.get('files',pins.get('source_sha256'))
    require(isinstance(hashes,dict) and all(f in hashes for f in SOURCE),'Final run pin inventory incomplete')
    for f,h in hashes.items():require(sha(ROOT/f)==h,'Final source differs from run pins: '+f)
    inherited=read(WORK/'van-parallel-inherited-tests-20261101.json')
    for f,h in inherited['files'].items():require(sha(ROOT/f)==h,'Inherited test changed: '+f)
    if args.new_cases_xml is not None:
        require(args.new_cases_xml.resolve()==args.focused_xml.resolve(), 'New-case subset must derive from the same final focused XML')
    new_modules=['test_lane_auth_commit_expiry','test_lane_auth_commit_expiry_http']
    focused=junit(args.focused_xml);new=junit(args.focused_xml, new_modules)
    new['subset_of']='focused'
    new['classname_module_filter']=new_modules
    handoff=read(args.handoff)
    require(handoff['files']=={f:hashes[f] for f in SOURCE}, 'Auth handoff differs from final source pins')
    require('--junitxml='+str(args.focused_xml) in handoff['command'], 'Focused XML differs from handoff actual command')
    review=read(args.source_review)
    require(review.get('exit')==0 and review.get('changed_during_run')==[] and review.get('remaining_review_blockers')==[], 'Auth source review unresolved or nonterminal')
    require(review.get('reviewed_handoff_pins_match') is True, 'Auth review handoff mismatch')
    for f in SOURCE:require(review['pins'][f]==hashes[f], 'Auth review changed source mismatch: '+f)
    review_xml=args.source_review.with_suffix('.xml')
    reviewed=junit(review_xml)
    require(reviewed['tests']>0 and reviewed['failures']==reviewed['errors']==reviewed['skipped']==0, 'Auth review XML not all-pass')
    require(reviewed['passed']==review['passed'], 'Auth review count mismatch')
    review_probe=args.source_review.parent/'test_auth_signed_midwrite_review.py'
    require(sha(review_probe)==review['external_probe_sha256'], 'Auth external review probe drift')
    review_differential={f:{'review':h,'integrated':hashes.get(f)} for f,h in review['pins'].items() if hashes.get(f)!=h}
    caller_map=read(args.caller_map);caller_selection=read(args.caller_selection)
    for label,result in [('focused',focused),('new',new)]:
        require(result['tests']>0 and result['failures']==result['errors']==result['skipped']==0,label+' selected XML not all-pass')
    original_prefix=WORK/'van-auth-integrated-backend-full-20261101'
    original_terminal=read(original_prefix.with_suffix('.json'))
    require(original_terminal.get('state')=='COMPLETED','Original first full run must be reconciled to terminal state')
    require(args.full_run_prefix.resolve()!=original_prefix.resolve(),'Original full run predates awaited-device-lookup repair; cannot qualify corrected source')
    scope_label = {'full-backend':'complete backend regression', 'affected-callgraph':'complete affected auth/caller regression selected by callgraph', 'full-backend-sharded':'complete corrected backend source coverage across two disjoint executed shards', 'full-backend-composite-recovery':'complete corrected backend composite source coverage across exact retained passing identities and actual recoveries'}[args.qualification_scope]
    sharded = None
    if args.qualification_scope in ['full-backend-sharded','full-backend-composite-recovery']:
        require(args.collection_dir is not None and args.remainder_run_prefix is not None, 'Sharded coverage requires exact collection and remainder inputs')
        require(original_terminal.get('timed_out') is True and original_terminal.get('exit') != 0, 'Sharded recovery expects retained unsuccessful original timeout')
        if composite_mode:
            require(args.selected_recovery_dir is not None and args.remainder_recovery_dir is not None, 'Composite mode requires both actual recovery directories')
            from van_source_composite_coverage_20261101 import auth
            sharded = auth(args.selected_recovery_dir, args.remainder_recovery_dir, args.source_pins, args.collection_dir, args.selected_isolated_recovery_dir)
        else:
            from van_auth_shard_coverage_20261101 import verify
            sharded = verify(args.collection_dir, [args.full_run_prefix, args.remainder_run_prefix], args.source_pins)
        full = {k:v for k,v in sharded.items() if k in ['tests','passed','failures','errors','skipped','skip_cases']}
        full['failure_cases'] = []
    selection = None
    if args.qualification_scope == 'affected-callgraph':
        require(args.selection_receipt is not None, 'Affected qualification requires explicit reviewed selection receipt')
        selection = read(args.selection_receipt)
        require(original_terminal.get('exit') == 0, 'Cannot reuse original backend run unless terminal exit0')
        original_result = junit(original_prefix.with_suffix('.xml'))
        require(original_result['tests'] > 0 and original_result['failures'] == original_result['errors'] == 0, 'Original backend XML cannot support reuse')
        old_pins_doc = read(WORK/'van-auth-integrated-source-pins-20261101.json')
        old_pins = old_pins_doc.get('files', old_pins_doc.get('source_sha256'))
        require(isinstance(old_pins, dict), 'Original source pins missing')
        delta = {f: {'before': old_pins.get(f), 'after': hashes.get(f)} for f in sorted(set(old_pins)|set(hashes)) if old_pins.get(f) != hashes.get(f)}
        unchanged = {f: h for f,h in sorted(hashes.items()) if old_pins.get(f) == h}
        unchanged_digest = hashlib.sha256(json.dumps(unchanged, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        require(selection.get('source_delta') == delta and bool(delta), 'Selection must identify exact old/new input delta')
        require(selection.get('unchanged_input_set_sha256') == unchanged_digest, 'Selection unchanged-input digest mismatch')
        require(selection.get('original_full_terminal_sha256') == sha(original_prefix.with_suffix('.json')), 'Wrong original run identity')
        require(selection.get('selected_terminal_sha256') == sha(args.full_run_prefix.with_suffix('.json')), 'Wrong selected run identity')
        require(selection.get('selected_source_pins_sha256') == sha(args.source_pins), 'Wrong final pins identity')
        targets = selection.get('selected_targets')
        require(isinstance(targets,list) and targets and all(isinstance(t,str) and t in terminal.get('command',[]) for t in targets), 'Selected target list must occur in actual terminal command')
        require(bool(selection.get('consumer_edges')) and bool(selection.get('selection_justification')) and bool(selection.get('unaffected_reuse_justification')), 'Callgraph/exclusion reasoning is required')
        require(selection.get('scope_review_state') == 'ROOT_REVIEWED_FOR_SOURCE_QUALIFICATION', 'Root source-scope review required before reuse')
    history={}
    copies=[]
    def add(src,dest):copies.append((src,Path(dest)))
    for name in ['before','after-r1','http-r1','new-final']:
        prefix=WORK/f'van-lane-auth-{name}-20261101'
        history[prefix.name]={'junit':junit(prefix.with_suffix('.xml')),'classification':('New HTTP fixture expectation error: expected403 instead of existing400' if name=='http-r1' else 'Original production expiry counterexamples' if name=='before' else 'Historical earlier-source focused evidence; not corrected-source qualification')}
        for ext in ['xml','log']:add(prefix.with_suffix('.'+ext),Path('history')/(prefix.name+'.'+ext))
    for i,p in enumerate(args.counterexample_xml):
        result=junit(p);require(result['failures']+result['errors']>0,'Counterexample has no recorded failure/error: '+str(p))
        history[f'additional_source_counterexample_{i}']={'junit':result,'classification':'Actual source counterexample retained before correction','original_path':str(p)}
        for src in [p,p.with_suffix('.log')]:add(src,Path('history')/f'counterexample-{i}'/src.name)
    for ext in ['json','xml','log']:
        original_file = original_prefix.with_suffix('.'+ext)
        if original_file.is_file():add(original_file,Path('superseded-first-full')/('run.'+ext))
        else:require(args.qualification_scope in ['full-backend-sharded','full-backend-composite-recovery'] and ext == 'xml', 'Missing original full evidence: '+str(original_file))
    for name in ['van-auth-integrated-source-pins-20261101.json','van-auth-integrated-backend-full-audit-20261101.json']:
        original_file=WORK/name
        if original_file.is_file():add(original_file,Path('superseded-first-full')/name)
        else:require(args.qualification_scope in ['full-backend-sharded','full-backend-composite-recovery'] and 'audit' in name, 'Missing original input evidence')
    for ext in ['json','xml','log']:add(args.full_run_prefix.with_suffix('.'+ext),Path('selected-run')/('run.'+ext))
    add(args.source_pins,'selected-run/source-pins.json');add(args.storage_audit,'selected-run/storage-audit.json')
    if sharded is not None:
        for ext in ['json','xml','log']:add(args.remainder_run_prefix.with_suffix('.'+ext),Path('remainder-run')/('run.'+ext))
        add(WORK/'van-auth-corrected-remainder-audit-20261101.json','remainder-run/storage-audit.json')
        add(WORK/'van-auth-corrected-remainder-environment-20261101.json','remainder-run/environment.json')
        add(WORK/'van-auth-corrected-remainder-launch-20261101.py','remainder-run/launcher.py')
        add(WORK/'van_auth_shard_coverage_20261101.py','sharded-coverage-verifier.py')
        add(WORK/'van-auth-shared-shard-environment-20261101.json','shared-shard-environment.json')
        add(WORK/'van-auth-shard-environment-pin-20261101.py','shared-shard-environment-builder.py')
        add(WORK/'van_auth_collection_manifest_20261101.py','collection/plugin.py')
        add(WORK/'van-auth-corrected-collection-r2-20261101.py','collection/controller.py')
        add(WORK/'van-auth-corrected-collection-20261101.py','collection-history-r1/controller.py')
        for path in sorted(args.collection_dir.iterdir()):
            if path.is_file():add(path,Path('collection')/path.name)
        for path in sorted((WORK/'van-auth-corrected-collection-20261101').iterdir()):
            if path.is_file():add(path,Path('collection-history-r1')/path.name)
    if composite_mode:
        add(WORK/'van_source_composite_coverage_20261101.py','composite-coverage-verifier.py')
        add(WORK/'van-owned-test-temp-cleanup-20261101.py','recovery/terminal-temp-cleanup.py')
        add(WORK/'van_owned_basetemp_20261101.py','recovery/owned-basetemp-helper.py')
        add(WORK/'van-auth-storage-recovery-20261101.py','recovery/auth-recovery-controller.py')
        add(WORK/'van-storage-recovery-set-20261101.py','recovery/recovery-set-builder.py')
        if args.selected_isolated_recovery_dir is not None:
            for path in sorted(args.selected_isolated_recovery_dir.iterdir()):
                if path.is_file():add(path,Path('recovery')/'selected-isolated'/path.name)
            for name in ['van-auth-erasure-isolated-plan-20261101.json','van-auth-erasure-isolated-replay-20261101.py','van-auth-owner-erasure-recovery-diagnostic-20261101.json','van-auth-selected-storage-recovery-failures-20261101.json']:
                add(WORK/name,Path('recovery')/'nonstorage-erasure-expiry'/name)
        add(WORK/'van-storage-exhaustion-recovery-20261101.json','recovery/exhaustion-and-cleanup.json')
        for label,directory in [('selected',args.selected_recovery_dir),('remainder',args.remainder_recovery_dir)]:
            for path in sorted(directory.iterdir()):
                if path.is_file():add(path,Path('recovery')/label/path.name)
        for path in sorted((WORK/'van-storage-recovery-sets-20261101').iterdir()):
            if path.is_file():add(path,Path('recovery')/'sets'/path.name)
        for path in sorted(WORK.glob('van-owned-*-temp-inventory-20261101.json')):
            add(path,Path('recovery')/'cleanup-inventories'/path.name)
    if args.selection_receipt is not None:add(args.selection_receipt,'qualification-selection.json')
    for src in [args.focused_xml,args.focused_xml.with_suffix('.log')]:add(src,Path('focused')/src.name)
    for src in [args.source_review,review_xml,args.source_review.with_suffix('.log'),review_probe]:add(src,Path('source-review')/src.name)
    for label,src in [('handoff',args.handoff),('caller-map',args.caller_map),('caller-selection',args.caller_selection)]:add(src,Path('scope')/(label+'.json'))
    add(WORK/'van-parallel-inherited-tests-20261101.json','inherited-tests.json')
    add(Path(__file__),'evidence-builder.py')
    for i,p in enumerate(args.extra_evidence):add(p,Path('extra')/str(i)/p.name)
    require(len({str(dest) for _,dest in copies})==len(copies),'Duplicate raw destination')
    for src,_ in copies:require(src.is_file(),'Missing required actual evidence: '+str(src))
    progress_path=ROOT/'docs/rebuild/rev118/CANDIDATE_SOURCE_PROGRESS.json';progress=read(progress_path)
    for uid in ['BE-002','BE-003']:
        require(not any(Path(RECEIPT).name in json.dumps(m) for m in progress['units'][uid]['milestones']),'Duplicate milestone '+uid)
    at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    data={'schema':'van.rebuild.auth-commit-expiry-source/2','at_utc':at,'source_parent':parent,'source_sha256':{f:hashes[f] for f in SOURCE},'canonical_units':['BE-002','BE-003'],
          'scope':'Original pairing/grant expiry including awaited work inside writer admission; durable original-result recovery',
          'evidence_meaning':'Named source subpaths only; complete unit acceptance not issued',
          'qualification_scope':args.qualification_scope,'composite_mode':composite_mode,'original_failed_runs_remain_failed':composite_mode,'sharded_coverage':sharded,'collection_history':({'r1': {'classification':'Collection fixture path error only: pytest root backend emitted tests/... node paths, passed as repository-relative remainder targets; pytest exit4 before any test execution. Original logs/manifests retained. Corrected collection derives actual item.path relative to source checkout.', 'raw_directory':RAW+'/collection-history-r1', 'test_results_reused':False}} if sharded is not None else None),'qualification_label':scope_label,'selected_suite':full,'selected_terminal':terminal,'selected_command':terminal.get('command'),'selected_targets':selection.get('selected_targets') if selection else None,'selection_and_reuse':selection,'storage_audit':audit,'focused':focused,'new_test_subset':new,'source_review':{'results':reviewed,'auth_source_pins_match':True,'other_review_input_differences':review_differential,'meaning':'Engineering source review at its recorded snapshot; full input differences retained, not independent native acceptance'},'handoff':handoff,'caller_map':caller_map,'caller_selection':caller_selection,
          'historical_results':history,'superseded_first_full':{'terminal':original_terminal,'absent_artifacts_after_recorded_timeout':[str(p) for p in [original_prefix.with_suffix('.xml'),WORK/'van-auth-integrated-backend-full-audit-20261101.json'] if not p.is_file()],'absent_artifact_policy':'Absent output is retained as absent; no JUnit/audit is fabricated or credited for this interrupted predecessor.','junit':junit(original_prefix.with_suffix('.xml')) if original_prefix.with_suffix('.xml').is_file() else None,'meaning':('Original exact-source run supports only explicitly unchanged-input reuse; changed auth/callers qualified by selected new run' if selection else 'Original exact-source run retained; not evidence for later repaired source; timeout partial results are never reused')},
          'suites_overlap':True,'inherited_test_files_byte_identical':len(inherited['files']),'source_pins_matching':len(hashes),'public_interfaces_changed':False,
          'mutation_execution_claimed':False,'unit_acceptance':'NOT_ISSUED','native_provider_production_device_acceptance':False,
          'limitations':['Declared full-suite skips retain their exact reasons.','Grant renewal remains an existing service operation, with no new public endpoint.','An inherited positive erasure case with a10second signed deadline expired under prior run load and failed; its unchanged isolated replay passed in5.337seconds, completing8.541seconds before deadline. Originalfailure and exacttimestamps remain retained as timing sensitivity, not a performance guarantee.','Whole BE002/003, family/session successors and all independent/native/provider/signing/S24 obligations remain open.'],
          'raw_files':{str(Path(RAW)/dest):sha(src) for src,dest in copies}}
    summary=f"Pairing and renewal source authority is rechecked across actual writer admission and awaited lookup boundaries; original committed pairing results remain recoverable. Final {scope_label}: {full['passed']} passed, {full['failures']} failures, {full['errors']} errors, {full['skipped']} declared skips. Focused{focused['passed']} includes {new['passed']} cases from the two new test modules (same XML subset); review{reviewed['passed']} overlaps and retains its own input snapshot. Original production counterexamples, corrected HTTP fixture error and superseded original full run remain retained. All{len(inherited['files'])} inherited tests byte-identical. No full-unit or native acceptance."
    document='# Pairing and grant authority through writer admission\n\n'+summary+'\n\n[Source receipt](../receipts/AUTH_COMMIT_EXPIRY_SOURCE_20261101.json) binds the selected final run, exact source hashes and original failures. Earlier all-pass runs do not qualify subsequent source changes. Sharded/composite complete-source coverage binds exact corrected backend identities. In composite recovery mode the original failed runs remain failed: fully passed identities are retained separately, every failed/errored/unexecuted case is actually rerun, and the verifier proves zero unresolved bad or unexecuted identity. Every declared skip retains its actual reason. No single successful full-suite run or partial-pass credit from the interrupted original predecessor is claimed. When affected-callgraph qualification is selected, the receipt separately binds the new affected suite and reviewed reuse of unchanged inputs from the original terminal-successful backend suite; it does not claim a new complete-backend run. Public API shapes and legacy evidence remain preserved.\n\n'+'\n'.join('- '+x for x in data['limitations'])+'\n'
    raw=ROOT/RAW;raw.mkdir(exist_ok=False)
    for src,dest in copies:
        target=raw/dest;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        require(sha(target)==data['raw_files'][str(Path(RAW)/dest)],'Raw copy mismatch')
    (ROOT/RECEIPT).write_text(json.dumps(data,indent=2)+'\n');(ROOT/DOC).write_text(document)
    for uid in ['BE-002','BE-003']:progress['units'][uid]['milestones'].append({'description':summary,'evidence':DOC.removeprefix('docs/rebuild/rev118/')+';'+RECEIPT.removeprefix('docs/rebuild/rev118/')})
    progress['updated_at_utc']=at;progress_path.write_text(json.dumps(progress,indent=2)+'\n')
    print(json.dumps({'receipt':RECEIPT,'source_parent':parent,'qualification_scope':args.qualification_scope,'selected_suite':full,'raw_files':len(copies),'acceptance_issued':False}))

if __name__=='__main__':main()
