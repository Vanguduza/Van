from pathlib import Path
import os,subprocess,json,hashlib,xml.etree.ElementTree as ET
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-movement-supplemental-final-20261026');out.mkdir(exist_ok=False)
mutants=[
 ('minor-capacity','trading/vati/core/units.py','abs(value) > MAX_MINOR','False','trading/tests/test_exact_units.py::test_minor_unit_types_and_capacity_refuse_without_truncation'),
 ('asset-identity','trading/vati/core/units.py','(other.currency, other.asset_ref) != (self.currency, self.asset_ref)','other.currency != self.currency','trading/tests/test_exact_units.py::test_matching_display_names_do_not_allow_cross_currency_provider_or_realm_arithmetic'),
 ('balanced-assets','trading/vati/core/units.py','if any(total != 0 or len(accounts[key]) < 2 for key,total in totals.items()):','if False:','trading/tests/test_exact_units.py::test_offsetting_labels_cannot_conceal_an_unbalanced_or_foreign_asset'),
 ('credit-control','trading/vati/funding/postings.py',"state, basis = 'RESTRICTED_CREDIT_MEMORANDUM', 'NONWITHDRAWABLE_CREDIT_CONTROL'","state, basis = 'OBSERVED_CASH_NOT_SETTLEMENT', 'ORIGINAL_NATIVE_CASH_DELTA'",'trading/tests/test_financial_movement_projection.py::test_native_economic_classes_keep_exact_original_sources_and_balanced_legs'),
 ('source-clock','trading/vati/funding/postings.py','source.event_time_ms != statement.to_ms','False','trading/tests/test_financial_movement_projection.py::test_even_sealed_incompatible_native_envelopes_cannot_be_projected'),
 ('caller-transaction','trading/vati/funding/movement_journal.py',"if active and (publication or not getattr(self.ledger,'_read_snapshot_depth',0)):",'if False:','trading/tests/test_financial_movement_journal.py::test_unknown_and_caller_owned_transactions_cannot_claim_committed_projection'),
 ('unknown-request','trading/vati/funding/movement_journal.py','self.request_id=request_id','self.request_id=None','trading/tests/test_financial_movement_runtime.py::test_actual_projection_commit_lost_ack_is_unknown_then_original_recovers'),
 ('readonly-posting','trading/vati/funding/runtime.py','if not materialize:return book.projection(scope_hash)','if not materialize:return book.materialize(scope_hash)','trading/tests/test_financial_movement_runtime.py::test_projection_failure_preserves_native_facts_and_owner_read_never_writes'),
]
mutants.append(('json-wire-type','trading/vati/funding/movement_journal.py',"canonical_json(actual) != canonical_json(p['movement'])","actual != p['movement']",'trading/tests/test_financial_movement_journal.py::test_resealed_numeric_values_cannot_impersonate_exact_json_boolean_or_integer_types'))
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='backend:backend/tests:trading:trading/tests:.');env.pop('VATI_TEST_PG_DSN',None);env.pop('VATI_TEST_PG_ISOLATED_FIXTURE',None)
controls=list(dict.fromkeys(m[4] for m in mutants))
def run(name,targets):
 with (out/(name+'.log')).open('wb') as log:
  p=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),*targets,'-k','not postgres','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
 cases=list(ET.parse(out/(name+'.xml')).getroot().iter('testcase'));result={'exit':p.returncode,'tests':len(cases),'failures':sum(c.find('failure') is not None for c in cases),'errors':sum(c.find('error') is not None for c in cases),'skips':sum(c.find('skipped') is not None for c in cases),'audit':json.loads((out/(name+'-audit.json')).read_text())['forbidden_events']}
 return result
receipt={'scope':'SUPPLEMENTAL_SOURCE_ASSERTION_FAULTS_NOT_CANONICAL374','positive':run('positive',controls),'faults':[]}
assert receipt['positive']['exit']==0
for name,path,before,after,target in mutants:
 p=root/path;data=p.read_bytes();text=data.decode();assert text.count(before)==1,(name,text.count(before))
 try:
  p.write_text(text.replace(before,after));r=run(name,[target]);r.update(name=name,path=path,original_sha256=hashlib.sha256(data).hexdigest())
  assert r['exit']==1 and r['failures']>0 and r['errors']==r['skips']==0 and not r['audit'],r
  receipt['faults'].append(r)
 finally:
  p.write_bytes(data);assert p.read_bytes()==data
receipt['restored']=run('restored',controls);assert receipt['restored']['exit']==0
receipt['all_restored']=all(hashlib.sha256((root/r['path']).read_bytes()).hexdigest()==r['original_sha256'] for r in receipt['faults'])
assert receipt['all_restored'];(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
