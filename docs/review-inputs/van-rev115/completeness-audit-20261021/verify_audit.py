#!/usr/bin/env python3
"""Audit inventory, evidence identity and coverage checks; no application acceptance."""
from pathlib import Path
import copy,hashlib,json
A=Path(__file__).resolve().parent;P=A.parent/'package'
def read(f):return json.loads((A/f).read_text())
def validate(inv,findings,families):
 errors=[];units={u['id'] for u in inv['units']};services={s['id'] for s in inv['services']};tests={t['id'] for t in inv['tests']}
 expected={'features':93,'contexts':234,'requirements':324,'actions':349,'services':82,'tests':1610,'units':131,'source_atoms':171,'product_truth':22,'external_qualification':82}
 for k,n in expected.items():
  if len(inv[k])!=n or len({x['id'] for x in inv[k]})!=n:errors.append('COUNT_OR_ID:'+k)
 fs={f['id'] for f in findings}
 if len(findings)!=len(fs) or len(fs)!=16:errors.append('FINDING_IDENTITIES')
 if len(families)!=24 or len({f['id'] for f in families})!=24:errors.append('DOMAIN_IDENTITIES')
 covered={u for f in families for u in f['backend_units']}
 if covered!=services:errors.append('BACKEND_COVERAGE')
 for f in findings:
  if not set(f['owners'])<=units:errors.append('FINDING_OWNER:'+f['id'])
  if not f['required_closure'] or not f['closure_evidence'] or not f['evidence']:errors.append('UNACTIONABLE_FINDING:'+f['id'])
  if f['status']!='OPEN_AT_AUDITED_BLUEPRINT':errors.append('FALSE_CLOSURE:'+f['id'])
 for f in families:
  if not set(f['open_findings'])<=fs:errors.append('UNKNOWN_FINDING:'+f['id'])
  if not set(f['frontend_units'])<=units:errors.append('FRONTEND_OWNER:'+f['id'])
  if not f['positive_journey'] or not f['error_and_recovery_journey']:errors.append('JOURNEY_MISSING:'+f['id'])
  if f['live_services']!='NOT_CHECKED' or f['handset_acceptance']!='NOT_RUN_IN_THIS_PASS':errors.append('FALSE_RUNTIME_CLAIM:'+f['id'])
 for x in inv['contexts']:
  if x['test_id'] not in tests:errors.append('CONTEXT_TEST:'+x['id'])
 if any(t['execution_state']!='NOT_RUN' for t in inv['tests']):errors.append('CHANGED_TEST_STATE')
 return sorted(set(errors))
def main():
 inv=read('INVENTORY.json');f=read('FINDINGS.json')['findings'];d=read('DOMAIN_REVIEW.json')['families'];s=read('STRUCTURAL_FINDINGS.json');errors=validate(inv,f,d)
 for path,meta in s['input_hashes'].items():
  q=P/path
  if not q.is_file() or hashlib.sha256(q.read_bytes()).hexdigest()!=meta['sha256']:errors.append('INPUT_CHANGED:'+path)
 cases=[]
 mutant=copy.deepcopy(inv);mutant['contexts'].pop();cases.append(('omitted context rejected','COUNT_OR_ID:contexts' in validate(mutant,f,d)))
 mutant=copy.deepcopy(d)
 for row in mutant:row['backend_units']=[u for u in row['backend_units'] if u!='BE-034']
 cases.append(('omitted Studio service rejected','BACKEND_COVERAGE' in validate(inv,f,mutant)))
 mutant=copy.deepcopy(f);mutant[0]['owners']=['FE-999'];cases.append(('invented closure owner rejected',any(e.startswith('FINDING_OWNER:') for e in validate(inv,mutant,d))))
 mutant=copy.deepcopy(d);mutant[0]['handset_acceptance']='PASSED';cases.append(('unsupported handset claim rejected',any(e.startswith('FALSE_RUNTIME_CLAIM:') for e in validate(inv,f,mutant))))
 result={'scope':'AUDIT_STRUCTURE_AND_INPUT_HASH_CHECKS_ONLY','passed':not errors and all(ok for name,ok in cases),'findings':errors,'negative_controls':[{'name':name,'passed':ok} for name,ok in cases],'backend_units_covered':len({u for x in d for u in x['backend_units']}),'review_families':len(d),'source_input_hashes_verified':len(s['input_hashes']),'application_tests_executed':0,'semantic_judgments_independently_certified':False}
 print(json.dumps(result,indent=2));return int(not result['passed'])
if __name__=='__main__':raise SystemExit(main())
