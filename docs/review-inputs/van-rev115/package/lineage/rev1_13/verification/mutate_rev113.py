#!/usr/bin/env python3
"""Mutation probes against the ACTUAL Rev1.13 documentary verifier; never touches app or service."""
import copy, json, pathlib, subprocess, sys, tempfile, shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
FILES=['plan/DEVELOPMENT_PLAN.json','design/ALL_SURFACE_CONTRACTS.json','traceability/REQUIREMENTS_AND_DU_MAPPING.json','verification/TEST_CONTRACTS.json','design/COMPONENT_RECIPES_REV2.json','design/VAN_MATERIAL_TOKENS_REV2.json','verification/F15_CERTIFICATE.json','verification/BACKEND_COMPLETE_CERTIFICATE.json','CANONICAL_AUTHORITY.json']
CASES={
'BG_MISSING_REQUIRED_BACKEND':lambda d:d['plan/DEVELOPMENT_PLAN.json']['required_backend_ids'].remove('BE-035'),
'FRONTEND_BEFORE_BG':lambda d:d['plan/DEVELOPMENT_PLAN.json']['units'][next(i for i,x in enumerate(d['plan/DEVELOPMENT_PLAN.json']['units']) if x['id']=='UX-001')].update(dependencies=[]),
'BACKEND_BEFORE_F15':lambda d:d['plan/DEVELOPMENT_PLAN.json']['units'][next(i for i,x in enumerate(d['plan/DEVELOPMENT_PLAN.json']['units']) if x['id']=='BE-001')].update(dependencies=[]),
'DUPLICATE_PACKET':lambda d:d['plan/DEVELOPMENT_PLAN.json']['units'].append(copy.deepcopy(d['plan/DEVELOPMENT_PLAN.json']['units'][3])),
'DROPPED_CONTEXT':lambda d:d['design/ALL_SURFACE_CONTRACTS.json']['surfaces'].pop(),
'MISSING_LIGHT_ROLE':lambda d:d['design/VAN_MATERIAL_TOKENS_REV2.json']['color']['light'].pop('accent'),
'DUPLICATE_COMPONENT':lambda d:d['design/COMPONENT_RECIPES_REV2.json']['recipes'].append(copy.deepcopy(d['design/COMPONENT_RECIPES_REV2.json']['recipes'][0])),
'FAKE_LIGHT_CONTRAST':lambda d:d['design/VAN_MATERIAL_TOKENS_REV2.json']['color']['light'].update(text_muted='#E5E5E5'),
'FAKE_F15_READY':lambda d:d['verification/F15_CERTIFICATE.json'].update(ready=True),
'MISROUTED_SCREEN':lambda d:d['design/ALL_SURFACE_CONTRACTS.json']['surfaces'][0].update(frontend_units=['BE-010']),
'DROPPED_TEST':lambda d:d['verification/TEST_CONTRACTS.json']['tests'].pop(),
'FORGED_OWNER_SIGNATURE':lambda d:d['CANONICAL_AUTHORITY.json'].update(signed_authority=True),
}
outputs=[]
for name,mutation in CASES.items():
 data={f:json.loads((ROOT/f).read_text()) for f in FILES}
 mutation(data)
 with tempfile.TemporaryDirectory(prefix='van-rev113-mutate-') as tmp:
  tmp=pathlib.Path(tmp)
  for f,record in data.items():
   dest=tmp/f;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(record))
  (tmp/'verification/verify_rev113.py').write_text((ROOT/'verification/verify_rev113.py').read_text())
  p=subprocess.run([sys.executable,str(tmp/'verification/verify_rev113.py')],capture_output=True,text=True,timeout=20)
  outputs.append({'mutation':name,'caught':p.returncode!=0,'exit_code':p.returncode,'diagnostic':p.stderr.strip().splitlines()[-1][-180:] if p.stderr else p.stdout[:80]})
failed=[x for x in outputs if not x['caught']]
record={'schema':'van.document.rev113.mutations/1.0','count':len(outputs),'caught':len(outputs)-len(failed),'false_negatives':failed,'cases':outputs,'scope':'Document structural/role checks, not live risk test or independent F15'}
print(json.dumps(record,sort_keys=True))
raise SystemExit(1 if failed else 0)
