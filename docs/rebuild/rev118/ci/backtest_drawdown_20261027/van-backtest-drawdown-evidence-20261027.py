from pathlib import Path
import datetime,hashlib,json,shutil,xml.etree.ElementTree as E
repo=Path('/workspace/van-review-2026-10-18/publish');docs=repo/'docs/rebuild/rev118';work=Path('/workspace')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
actual=json.loads((work/'van-backtest-drawdown-final-r1-20261027/receipt.json').read_text())
assert actual['exit']==0 and actual['completed'] is actual['cleaned'] is actual['owned_fixture_independently_absent'] is True
assert len(actual['source_sha256'])==1161 and all(sha(repo/name)==value for name,value in actual['source_sha256'].items())
cases=list(E.parse(work/'van-backtest-drawdown-final-r1-20261027/full-trading.xml').getroot().iter('testcase'))
assert len(cases)==605 and not any(c.find(k) is not None for c in cases for k in ['failure','error','skipped'])
assert not json.loads((work/'van-backtest-drawdown-final-r1-20261027/storage-audit.json').read_text())['forbidden_events']
assert '91 passed' in (work/'van-backtest-drawdown-focused-r1-20261027.log').read_text()
for name in ['owner','frontend','registry','consolidation']:
 value=json.loads((work/f'van-backtest-drawdown-{name}-check-20261027.json').read_text())
 if name=='owner':assert value['changed']==[]
 elif name=='frontend':assert value['changed'] is False
 else:assert value['findings']==[]
faults=json.loads((work/'van-backtest-drawdown-mutations-20261027.json').read_text())
assert len(faults['faults'])==2 and all(x['caught_by'] for x in faults['faults']) and faults['source_unchanged']
out=docs/'ci/backtest_drawdown_20261027';out.mkdir(exist_ok=False)
shutil.copytree(work/'van-backtest-drawdown-final-r1-20261027',out/'actual_sql_http_validation_final')
for pattern in ['van-backtest-drawdown-baseline*20261027*','van-backtest-drawdown-focused*20261027*','van-backtest-drawdown-*-check-20261027.json','van-backtest-drawdown-mutations-20261027*']:
 for p in work.glob(pattern):
  if p.is_file():shutil.copy2(p,out/p.name)
for name in ['van-backtest-drawdown-final-r1-20261027.py','van-backtest-drawdown-evidence-20261027.py','van_pytest_live_diagnostics.py','van-a4-binding-ledger-verify-20261027.log']:
 shutil.copy2(work/name,out/name)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=('The existing backtest metrics owner now accumulates the original equity path with exact rational arithmetic and tracks maximum currency and percentage drawdown independently, converting only the final existing float report fields. '
 'An earlier50percent loss is retained after a later100currency/10percent loss; negative equity preserves150percent drawdown; a cent is not erased by large starting equity. '
 'The actual strategy-validation source producer retains that original worst percentage. Nine actual regressions/2controls reproduced against unchanged committed source. '
 'Eleven new tests include independent prefix-curve/scaling, hostile Decimal contexts and the real source producer.91focused and605final actual SQL/HTTP/accounting/authority/validation cases pass0skip/audit0, all1161 pinned hashes match, owned PostgreSQL fixture independently absent. '
 'Two supplemental in-memory faults caught with3positive/3restored controls; active source unchanged. Existing client fields/types, statistical/admission/owner gates and historical reports remain. No unit/native/production/economic/S24 acceptance.')
report={'schema':'van.rebuild.backtest-drawdown-source/1','base_head':actual['base_head'],'updated_at_utc':now,'units':['BE-013','BE-035'],'status':'SOURCE_TESTED_COMPONENT_NOT_UNIT_ACCEPTANCE','acceptance':'NOT_ISSUED','implementation':summary,
 'source_sha256':{name:sha(repo/name) for name in ['trading/vati/backtest/metrics.py','trading/tests/test_backtest_drawdown_paths.py']},
 'tests':{'baseline_failed':9,'baseline_passed_controls':2,'baseline_errors':0,'baseline_source_equals_committed':True,'new_cases':11,'focused':91,'final_actual_SQLite_Postgres_HTTP_accounting_authority_validation':605,'final_skips':0,'final_audit_violations':0,'pinned_hashes':1161,'owned_fixture_independently_absent':True,'supplemental_faults_caught':2,'positive_controls':3,'restored_controls':3,'active_source_unchanged_by_faults':True,'counts_overlap':True},
 'canonical_checks':{'owner_frontend_drift':False,'registry':[483,376],'original_coverage':[42,105,78],'mutation_registry_cases':374,'mutation_registry_edits':383,'registry_check_execution':'NOT_RUN','consolidation_findings':[]},
 'qualification':'Exact intermediate drawdown arithmetic with existing approximate float report fields; not a replacement for typed native Money, unitized funding returns, independent economic evidence or the full statistical/trial/admission programme. Other statistical fields retain their existing numerical semantics. Historical reports/certificates are not rewritten or requalified; recalculation lineage/policy/cohort migration remain required before admission. Source fixtures and self-hashed test containers do not issue an owner/independent certificate or guarantee profitability.',
 'evidence':'ci/backtest_drawdown_20261027'}
(docs/'receipts/BACKTEST_DRAWDOWN_SOURCE_20261027.json').write_text(json.dumps(report,indent=2)+'\n')
(docs/'backend/BE-013_035_BACKTEST_DRAWDOWN_PATHS.md').write_text('''# Preserve the original worst backtest drawdown

This repairs the existing metric producer and its strategy-validation source consumer. It does not qualify strategy edge or native promotion.

The original path100→50→1000→900 reported maximum currency drawdown100 and percentage drawdown10percent, overwriting the earlier50percent loss. Negative equity could similarly lose an earlier150percent drawdown. Converting starting equity to float before accumulation also erased a one-cent loss against1e30 starting equity. Three read-only probes and nine failing tests reproduced the incorrect source behavior; two ordinary controls passed. The actual validation producer sealed the understated percentage into its source fixture, independently confirming the consumer consequence.

The existing owner now accumulates original account values with rational arithmetic. Maximum currency and percentage drawdown are tracked independently. Only the final existing report fields convert to float. Their names and types remain compatible; this does not make every other statistic exact or support every possible magnitude through a float field. Negative equity remains observable rather than being clamped. It does not reinterpret deposits, restricted credit or transfers as trade P&L, change risk ceilings, or bypass any statistical/owner/native admission gate.

Eleven new cases cover known original paths, hostile Decimal contexts, an independently recomputed prefix curve, scale invariance and the actual validation producer.91focused checks and605final actual SQLite/PostgreSQL/HTTP/accounting/authority/validation cases pass with no skips or storage-audit violations. All1161 pinned runtime/test hashes match; the owned PostgreSQL fixture is independently absent. Two supplemental in-memory source faults are caught by the regression oracles, with3positive and3restored controls and no active-source mutation. These counts overlap. Canonical registry preflight remains374cases/383edits with no findings; that preflight is not execution.

Existing stored reports and source certificates remain historical. This patch does not silently regenerate them, change their lineage or requalify an old calculation. Recalculation policy/cohort migration and all independent/native acceptance remain required. The test producer creates only a synthetic self-hashed source container; no owner or independent certificate is issued. Float statistic range, full trial accounting, chance-versus-edge/causal interpretation, costs, chronological native inputs and all remaining BE-013/035/ML requirements remain open. Profitability needs evidence and is never guaranteed.

See `../receipts/BACKTEST_DRAWDOWN_SOURCE_20261027.json` and raw `../ci/backtest_drawdown_20261027/`. Zero whole-unit, native, production, economic or S24 acceptances. No frontend redesign precedes BG-001.
''')
p=docs/'CANDIDATE_SOURCE_PROGRESS.json';value=json.loads(p.read_text());value['updated_at_utc']=now
for unit in ['BE-013','BE-035']:
 assert value['units'][unit]['unit_acceptance']=='NOT_ISSUED'
 value['units'][unit]['milestones'].append({'description':summary,'evidence':'backend/BE-013_035_BACKTEST_DRAWDOWN_PATHS.md;receipts/BACKTEST_DRAWDOWN_SOURCE_20261027.json'})
p.write_text(json.dumps(value,indent=2)+'\n')
p=docs/'EXECUTION_LEDGER.json';value=json.loads(p.read_text());value['updated_at_utc']=now;value['checkpoint']['updated_utc']=now;value['checkpoint']['last_validation']=summary;value['observations'].append(summary)
value['observations'].append('Local5c584b2af6135660d46ba66216330b1c18704b2b completed genuine hooks and actual committed GREEN170 exit0 against4fd466dec3910ed5de614bfbf95887ad619df5ca;manifest5900/zero mismatch/alltracked. Publishedf00495cf996aaf9adb0a177db61c083640c2965e remains genuineGREEN169/manifest5702/normalpush+readback. Preserve exactf004 main40428024966 until terminal before nextpush. Forecast40428025041 independently verified in prior packet, not later A4/metrics source. No separate hosted qualification is assigned to unpushed local5c.')
value['continuation']['verified_source_head']='local5c584b2af6135660d46ba66216330b1c18704b2b/genuineGREEN170/manifest5900;publishedf00495cf996aaf9adb0a177db61c083640c2965e/GREEN169/manifest5702/remote readback; metrics candidate uncommitted at generation'
value['continuation']['latest_checkpoint_report']='docs/rebuild/rev118/CHECKPOINT_20261027_BACKTEST_DRAWDOWN.md'
value['current_action']='Finish current drawdown evidence/real manifest/verified staged ZIP/genuine hook using auth-20261022-owner-autonomous-candidate-build; actual committed verification against required4fd baseline. Preserve exactf004 main40428024966 until terminal, reconcile original artifacts and failures, normalpush and independent remote readback/exact newCI. If coalesced, do not invent separate hosted acceptance for intermediate5c. Continue all canonical backend operations and native/Android gates;0formal accepted units.'
p.write_text(json.dumps(value,indent=2)+'\n')
(docs/'CHECKPOINT_20261027_BACKTEST_DRAWDOWN.md').write_text('# Backtest drawdown continuation\n\n'+now+'\n\n'+summary+'\n\nLocal5c584b2af6135660d46ba66216330b1c18704b2b is genuineGREEN170 against required4fd466dec3910ed5de614bfbf95887ad619df5ca, manifest5900/zero mismatch/alltracked; not yet pushed at generation. Publishedf00495cf996aaf9adb0a177db61c083640c2965e remains genuineGREEN169/manifest5702/normalpush and remote readback. Metrics packet is uncommitted at generation; inspect actual Git. Finish realmanifest/verifiedstagedZIP/genuinehook with existingcandidate-build auth, actual committed baselineverify, then normalpush/readback only after exactpublishedf004 main40428024966 is terminal. Do not guess next GREEN count or give intermediate5c its own hosted result if coalesced.\n\nExactf004forecast40428025041 was independentlyverified114native+6synthetic+3cold/parity0/232versions/kernel/cleanup/hashes/tree-equivalentb00aefba269ac245bc65fdf11688068d01801156 in5c packet. Main40428024966 remains separate. Exact2a main retains CANCELLED publicbackend/two mandatory failures; raw17archives reconciled in5c; exact2aforecast previously qualified its own source fixtures. No parent run qualifies later A4/metrics changes.\n\nContinue canonical dependency-ready full backend financial/sharedreservation/provider/assistant/forecast work. Earlier report/certificate recalculation lineage/policy/cohort migration remains required. Physical-account alias issue remains primitive-only evidence; no native exposure bypass or lease-key fix is claimed. No formal unit, independent/native, production, economic, signing/deployment, Android or S24 acceptance. All frozen131units/324requirements/1610acceptanceidentities/234contexts/349actions/93features and original42groups/105functions/78surfaces remain. Artemis tools are advertised but require a protected native adapter/trace authority, exact Root-bound GREENOwner and actual device serial; no bound S24 was observed or actuated. No new frontend design beforeBG001, no /workspace/Van access, no delegation. Van trading core remains chosen host; profitability needs evidence, never guaranteed.\n')
print(json.dumps({'final_actual_passes':605,'new_tests':11,'pinned_hashes':1161,'supplemental_faults':2,'scope':'BE-013/035 components;NOT_ISSUED unit acceptance'}))
