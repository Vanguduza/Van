#!/usr/bin/env python3
"""Reproduce the pinned blueprint inventory and structural audit; no application testing."""
import json,hashlib,collections
from pathlib import Path
HERE=Path(__file__).resolve().parent
P=HERE.parent/'package'
BASE='172d2143d3e6d2ec4b401376f5ef5a4cf94c7429'
SOURCES={'features':('traceability/REV2_93_FEATURE_CROSSWALK.json','features'),'requirements':('traceability/REQUIREMENTS_AND_DU_MAPPING.json','requirements'),'contexts':('design/ALL_SURFACE_CONTRACTS.json','surfaces'),'actions':('traceability/LEGACY_349_ACTIONS.json','actions'),'services':('contracts/BACKEND_SERVICE_CATALOG.json','services'),'tests':('verification/TEST_CONTRACTS.json','tests'),'units':('plan/DEVELOPMENT_PLAN.json','units'),'source_atoms':('traceability/REV2_171_ATOM_CROSSWALK.json','requirements'),'product_truth':('traceability/PRODUCT_TRUTH.json','truth_atoms'),'external_qualification':('verification/RUNTIME_EXTERNAL_QUALIFICATION_MATRIX.json','capabilities')}
def write(name,x):
 if name=='INVENTORY.json':
  # One row per record keeps the complete snapshot reviewable without 70k pretty-print lines.
  blocks=[]
  for k,v in x.items():
   value=('[\n'+',\n'.join(json.dumps(row,sort_keys=True,separators=(',',':')) for row in v)+'\n]') if isinstance(v,list) else json.dumps(v,sort_keys=True)
   blocks.append(json.dumps(k)+': '+value)
  (HERE/name).write_text('{\n'+',\n'.join(blocks)+'\n}\n')
 else:(HERE/name).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def main():
 d={k:json.loads((P/f).read_text())[field] for k,(f,field) in SOURCES.items()}
 by={k:{x['id']:x for x in rows} for k,rows in d.items()};issues=[]
 for k,rows in d.items():
  if len(rows)!=len(by[k]):issues.append({'type':'DUPLICATE_ID','inventory':k})
 for kind in ['features','requirements','contexts','actions','services','source_atoms']:
  for x in d[kind]:
   for field,target in [('backend_units','units'),('frontend_units','units'),('other_units','units'),('test_ids','tests'),('van_requirements','requirements'),('feature_ids','features'),('context_ids','contexts')]:
    for val in x.get(field,[]):
     if val not in by[target]:issues.append({'type':'UNRESOLVED_REFERENCE','inventory':kind,'id':x['id'],'field':field,'value':val})
   for field,target in [('test_id','tests'),('primary_surface_id','contexts'),('surface_id','contexts')]:
    if field in x and x[field] not in by[target]:issues.append({'type':'UNRESOLVED_REFERENCE','inventory':kind,'id':x['id'],'field':field,'value':x[field]})
 for t in d['tests']:
  for uid in [t['unit'],*t.get('additional_units',[])]:
   if uid not in by['units']:issues.append({'type':'UNKNOWN_TEST_UNIT','id':t['id'],'unit':uid})
 mismatch=[];features=[]
 for f in d['features']:
  testids=f.get('test_ids',[]);owners=sorted({u for tid in testids for u in [by['tests'][tid]['unit'],*by['tests'][tid].get('additional_units',[])]})
  missing=f['primary_frontend_unit'] not in owners
  if missing:mismatch.append({'id':f['id'],'title':f['title'],'primary_frontend_unit':f['primary_frontend_unit'],'test_units':owners,'test_ids':testids,'interpretation':'Primary owner absent from directly linked feature-test ownership; review delegation/additional-unit binding, not proof feature is missing.'})
  features.append({'id':f['id'],'domain':f['domain'],'title':f['title'],'requirement_ids':f.get('van_requirements',[]),'source_atom_ids':f.get('requirement_ids',[]),'context_ids':f['context_ids'],'backend_units':f['backend_units'],'frontend_units':f['frontend_units'],'primary_frontend_unit':f['primary_frontend_unit'],'test_ids':testids,'test_units':owners,'primary_owner_in_direct_test_binding':not missing,'contract_assessment':'NAMED_SCOPE_PRESENT_IMPLEMENTATION_CONTRACT_DEPTH_REQUIRES_DOMAIN_REVIEW','application_evidence':'NOT_RUN_IN_PACKAGE'})
 contexts=[]
 for s in d['contexts']:
  contexts.append({'id':s['id'],'title':s.get('title',s.get('display_title')),'domain':s['domain'],'source_class':s.get('source','UNSPECIFIED_IN_ROW'),'route_candidate':s.get('route_candidate'),'backend_units':s['backend_units'],'frontend_units':s['frontend_units'],'test_id':s.get('test_id'),'states':s.get('states',[]),'feature_ids':s.get('feature_ids',[]),'legacy_action_ids':[a['id'] for a in d['actions'] if a['surface_id']==s['id']],'endpoint_references':s.get('endpoints',[]),'endpoint_interpretation':'HISTORICAL_REFERENCE_NOT_CURRENT_ROUTE_QUALIFICATION' if s.get('endpoints') else 'NO_INLINE_ENDPOINT_REFERENCE; resolve through service/extension contracts; absence alone does not mean no backend','evidence':'NATIVE_NOT_RUN'})
 inv={'schema':'van.whole.product.audit.inventory/1.0','audited_commit':BASE,'date':'2026-10-21','scope':'Blueprint structural inventory and domain contract review, not application/source/live acceptance','features':features,'contexts':contexts,'requirements':d['requirements'],'actions':d['actions'],'services':d['services'],'tests':d['tests'],'units':d['units'],'source_atoms':d['source_atoms'],'product_truth':d['product_truth'],'external_qualification':d['external_qualification']}
 write('INVENTORY.json',inv)
 inputs={f:{'sha256':hashlib.sha256((P/f).read_bytes()).hexdigest(),'bytes':(P/f).stat().st_size} for f,field in SOURCES.values()}
 # Seal all package inputs as audit scope, not just the ten primary registries.
 for f in ['CANONICAL_AUTHORITY.json','MANIFEST.json','VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md','contracts/BACKEND_TO_FRONTEND_CONSUMPTION_CONTRACT.md','design/DARK_THEME_READABILITY_AMENDMENT_20261021.md']:
  inputs[f]={'sha256':hashlib.sha256((P/f).read_bytes()).hexdigest(),'bytes':(P/f).stat().st_size}
 summary={'audited_commit':BASE,'date':'2026-10-21','counts':{k:len(v) for k,v in d.items()},'domain_context_counts':dict(collections.Counter(x['domain'] for x in d['contexts'])),'structural_reference_findings':issues,'feature_primary_test_owner_mismatches':mismatch,'contexts_with_inline_endpoint_references':sum(bool(s.get('endpoints')) for s in d['contexts']),'unique_inline_method_path_pairs':len({(e.get('method'),e.get('path')) for s in d['contexts'] for e in s.get('endpoints',[])}),'legacy_action_test_expectation_equals_action_title':sum(by['tests'][a['test_id']].get('expectation')==a['text'] for a in d['actions']),'services_with_structured_operation_objects':sum(any(isinstance(op,dict) for op in s['operations']) for s in d['services']),'test_execution_states':dict(collections.Counter(t['execution_state'] for t in d['tests'])),'repeated_test_expectations':[{'expectation':a,'count':b} for a,b in collections.Counter(t.get('expectation') for t in d['tests'] if t.get('expectation')).most_common(8)],'input_hashes':inputs,'application_tests_executed_by_audit':0,'live_services_checked':False,'source_implementation_reassessed':False,'verdict':'SCOPE_BROADLY_ENUMERATED; NOT_WHOLE_PRODUCT_IMPLEMENTATION_OR_RELEASE_READY'}
 write('STRUCTURAL_FINDINGS.json',summary)
 def cell(x):return str(x).replace('|','\\|').replace('\n',' ')
 lines=['# Complete feature and screen review index','',f'Audited blueprint commit: `{BASE}`. Every row is specification coverage, not a runtime pass. Full requirement/action/service/test/atom/truth inventories and original fields are in `INVENTORY.json`.','', '## All 93 named features','', '| Feature | Purpose | Primary FE | Test owners | Binding review |','|---|---|---|---|---|']
 for f in features:lines.append('| '+' | '.join(map(cell,[f['id'],f['title'],f['primary_frontend_unit'],', '.join(f['test_units']),'REVIEW: primary absent' if not f['primary_owner_in_direct_test_binding'] else 'Primary included']))+' |')
 lines+=['','## All 234 contexts','', '| Context | Purpose / domain | Backend units | Test | Legacy endpoint references |','|---|---|---|---|---|']
 for s in contexts:lines.append('| '+' | '.join(map(cell,[s['id'],str(s['title'])+' / '+s['domain'],', '.join(s['backend_units']),s['test_id'],len(s['endpoint_references'])]))+' |')
 lines+=['','## All 82 backend capability boundaries','', '| Unit | Purpose | Package status |','|---|---|---|']
 for s in d['services']:lines.append('| '+' | '.join(map(cell,[s['id'],s['title'],s.get('implementation_status',s.get('status'))]))+' |')
 (HERE/'FEATURE_SCREEN_SERVICE_INDEX.md').write_text('\n'.join(lines)+'\n')
 assert not issues,issues
 assert set(by['services'])=={u['id'] for u in d['units'] if u['kind']=='BACKEND'}
 assert set(by['external_qualification'])==set(by['services'])
 print(json.dumps({'counts':summary['counts'],'unresolved_references':len(issues),'primary_test_owner_mismatches':len(mismatch),'application_tests_executed':0},indent=2))
if __name__=='__main__':main()
