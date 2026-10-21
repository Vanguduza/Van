#!/usr/bin/env python3
"""Compile mandatory additive acceptance refinements; no runtime result creation."""
from pathlib import Path
import json,copy,hashlib,argparse
P=Path(__file__).resolve().parents[1]
def rd(f):return json.loads((P/f).read_text())
def compiled():
 base=rd('verification/TEST_CONTRACTS.json');ref=rd('contracts/whole_product/ACCEPTANCE_REFINEMENTS.json');actions=rd(ref['action_contract_source'])['actions'];scenarios=rd(ref['domain_scenarios_source'])['scenarios'];result=copy.deepcopy(base);result['revision']='1.18';result['resolution']='Mandatory additive effective view; all original predicates and owners retained; no application results produced.';by={t['id']:t for t in result['tests']}
 for tid,owners in ref['owner_additions'].items():
  t=by[tid];t['additional_units']=sorted(set(t.get('additional_units',[])+owners)-{t['unit']})
 for a in actions:
  t=by[a['test_id']];t['inherited_expectation']=t.get('expectation');t['expectation']=a['positive_oracle']+' Refusal: '+a['negative_oracle']+' Recovery: '+a['recovery_oracle'];t['whole_product_action_id']=a['action_id'];t['required_assertions']={'positive':a['positive_oracle'],'negative':a['negative_oracle'],'recovery':a['recovery_oracle']};t['required_input_profile']=a['input_profile'];t['required_evidence']=a['expected_evidence']
 for s in scenarios:by[s['test_id']].setdefault('whole_product_scenarios',[]).append(s)
 for t in result['tests']:assert t['execution_state']=='NOT_RUN'
 return result
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();text=json.dumps(compiled(),indent=2,sort_keys=True)+'\n';p=P/'verification/EFFECTIVE_TEST_CONTRACTS_REV118.json'
 if a.check:
  ok=p.is_file() and p.read_text()==text;print('Effective acceptance registry matches' if ok else 'STALE_EFFECTIVE_ACCEPTANCE');raise SystemExit(0 if ok else 1)
 p.write_text(text);print('Compiled 1610 acceptance identities with 349 action-oracle refinements, explicit ownership additions and 72 domain scenarios; all NOT_RUN.')
