#!/usr/bin/env python3
"""Independent document-level preservation and integration crosswalk checks.
Unsigned file hashes are integrity checks, not owner signatures or app acceptance.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(root,path):return json.loads((root/path).read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def by(rows):return {x['id']:x for x in rows}
def load(root):
 manifest=read(root,'lineage/REV111_PRESERVATION_MANIFEST.json');locations={x['original_path']:x['preserved_at'] for x in manifest['files']}
 paths={'requirements':('traceability/REQUIREMENTS_AND_DU_MAPPING.json','requirements'),'tests':('verification/TEST_CONTRACTS.json','tests'),'surfaces':('design/ALL_SURFACE_CONTRACTS.json','surfaces'),'units':('plan/DEVELOPMENT_PLAN.json','units'),'services':('contracts/BACKEND_SERVICE_CATALOG.json','services')}
 out={'root':str(root),'manifest':manifest,'old':{},'new':{},'findings':read(root,'traceability/REVIEW_FINDINGS_DISPOSITION.json')['findings'],'adoptions':read(root,'traceability/HIGH_VALUE_ADOPTION_CROSSWALK.json')['adoptions'],'packet_map':read(root,'traceability/REV111_PACKET_CROSSWALK.json')['mappings']}
 for k,(p,key) in paths.items():out['old'][k]=read(root,locations[p])[key];out['new'][k]=read(root,p)[key]
 return out

def validate(b,check_bytes=True):
 errors=[];groups=[]
 def bad(code,d):errors.append({'code':code,'detail':str(d)})
 def group(s):groups.append(s)
 root=Path(b['root'])
 if check_bytes:
  for row in b['manifest']['files']:
   p=root/row['preserved_at']
   if not p.exists() or sha(p.read_bytes())!=row['sha256']:bad('ORIGINAL_BYTES_CHANGED',row['original_path'])
  group('173 original parent files reconstructable from byte-preserving locations')
 for k,count in [('requirements',205),('tests',1185),('surfaces',228)]:
  old=by(b['old'][k]);new=by(b['new'][k])
  if len(old)!=count:bad('PARENT_COUNT',k)
  for i,v in old.items():
   if new.get(i)!=v:bad('INHERITED_OBJECT_CHANGED',k+':'+i)
  group(k+' inherited objects exact')
 new=by(b['new']['units']);old=by(b['old']['units'])
 for i,u in old.items():
  if i not in new:bad('OLD_UNIT_REMOVED',i);continue
  v=new[i]
  for k in ['id','kind','stage','title','exit_contract','completion','status','implementation_evidence','merged_obligations']:
   if v.get(k)!=u.get(k):bad('OLD_UNIT_OBLIGATION_CHANGED',i+':'+k)
  if not set(u['dependencies'])<=set(v['dependencies']):bad('OLD_DEPENDENCY_REMOVED',i)
  if v.get('full_deliverables',[])[:len(u.get('full_deliverables',[]))]!=u.get('full_deliverables',[]):bad('OLD_DELIVERABLE_REMOVED',i)
 group('121 stable units, original dependencies, exit contracts and deliverables retained')
 expected={f'BE-{i:03}' for i in range(37,45)}|{'BQ-008','BQ-009'}
 if set(new)-set(old)!=expected:bad('NEW_UNIT_SCOPE',set(new)-set(old))
 group('eight new backend units and two verifiers only')
 req=by(b['new']['requirements']);test=by(b['new']['tests'])
 hva={f'VAN-HVA-{i:03}' for i in range(1,33)}
 if set(req)-set(by(b['old']['requirements']))!=hva:bad('HVA_REQUIREMENT_SCOPE','32 exact IDs')
 for i in range(1,33):
  r=req.get(f'VAN-HVA-{i:03}',{})
  for suffix,k in [('POS','positive'),('NEG','adversarial'),('REC','recovery')]:
   t=test.get(f'T-HVA-{i:03}-{suffix}',{})
   if t.get('expectation')!=r.get('acceptance',{}).get(k) or not t:bad('HVA_TEST_BINDING',str(i)+':'+suffix)
   if t.get('execution_state')!='NOT_RUN':bad('FALSE_APPLICATION_PASS',str(i)+':'+suffix)
 group('32 requirements bound to 96 actual positive/adversarial/recovery contracts')
 ids=[x['id'] for x in b['findings']]
 if set(ids)!={f'R{i:02}' for i in range(1,13)} or len(ids)!=12:bad('REVIEW_SCOPE','R01–R12 required')
 for f in b['findings']:
  if not f['requirements'] or not f['units'] or not f['acceptance_contracts']:bad('UNRESOLVED_REVIEW_MAPPING',f['id'])
  if not set(f['requirements'])<=set(req) or not set(f['acceptance_contracts'])<=set(test):bad('UNKNOWN_REVIEW_BINDING',f['id'])
 group('all 12 review findings mapped to real requirements and test IDs')
 if {x['adoption_id'] for x in b['adoptions']}!={f'VAN-A{i:02}' for i in range(1,9)}:bad('ADOPTION_SCOPE','A01–A08')
 for a in b['adoptions']:
  if not a['requirement_ids'] or not a['units'] or not a['test_contract_ids']:bad('ADOPTION_EMPTY',a['adoption_id'])
  if not set(a['requirement_ids'])<=set(req) or not set(a['units'])<=set(new):bad('ADOPTION_UNKNOWN',a['adoption_id'])
 group('all eight source adoptions integrated without new authority')
 svc=by(b['new']['services'])
 if {x['id'] for x in b['new']['units'] if x['kind']=='BACKEND'}!=set(svc):bad('SERVICE_SET','all backend services')
 for i,s in svc.items():
  if s.get('dependencies')!=new.get(i,{}).get('dependencies'):bad('SERVICE_DEPENDENCY_DRIFT',i)
 group('service and executable-plan dependencies agree')
 for m in b['packet_map']:
  i=m['unit_id']
  if i not in new or i not in old or m['source_packet_id']!=old[i]['packet_id'] or m['target_packet_id']!=new[i]['packet_id']:bad('PACKET_ALIAS_MISMATCH',i)
 if len(b['packet_map'])!=121:bad('PACKET_MAP_COUNT','121')
 group('revision-qualified packet-number crosswalk complete')
 def anc(i):
  q=list(new[i]['dependencies']);seen=set()
  while q:
   j=q.pop()
   if j not in seen:seen.add(j);q+=new.get(j,{}).get('dependencies',[])
  return seen
 for consumer,producer in [('BE-032','BE-044'),('VAN-ML-PKT-030','BE-044'),('BQ-006','BQ-008'),('BQ-006','BQ-009')]:
  if producer not in anc(consumer):bad('HVA_PRODUCER_ORDER',consumer+'<-'+producer)
 group('domain integration feeds catalogue, scientific evaluation and independent review')
 for i in ['VAN-ML-PKT-011','VAN-ML-PKT-016']:
  if anc(i)&{f'BE-{j:03}' for j in range(37,45)}:bad('GENERIC_RESEARCH_BLOCKED_BY_CRYPTO',i)
 group('generic Qlib/neural research not blocked by crypto providers')
 return {'findings':errors,'check_groups':groups,'scope':'Specification byte/object preservation and integration mappings only; not independent F15 or application qualification'}

def selftest(b):
 cases=[]
 def add(title,code,fn):cases.append((title,code,fn))
 add('old requirement weakened','INHERITED_OBJECT_CHANGED',lambda x:x['new']['requirements'][0].__setitem__('text','omitted'))
 add('old test removed','INHERITED_OBJECT_CHANGED',lambda x:x['new']['tests'].pop(0))
 add('old theme context removed','INHERITED_OBJECT_CHANGED',lambda x:x['new']['surfaces'].pop(0))
 add('stable unit removed','OLD_UNIT_REMOVED',lambda x:x['new']['units'].pop(0))
 add('old exit weakened','OLD_UNIT_OBLIGATION_CHANGED',lambda x:x['new']['units'][0].__setitem__('exit_contract','waived'))
 add('new unit removed','NEW_UNIT_SCOPE',lambda x:x['new']['units'].__setitem__(slice(None),[r for r in x['new']['units'] if r['id']!='BQ-008']))
 add('new requirement removed','HVA_REQUIREMENT_SCOPE',lambda x:x['new']['requirements'].pop())
 add('test no longer tests requirement','HVA_TEST_BINDING',lambda x:next(r for r in x['new']['tests'] if r['id']=='T-HVA-001-POS').__setitem__('expectation','placeholder'))
 add('application claimed passed','FALSE_APPLICATION_PASS',lambda x:next(r for r in x['new']['tests'] if r['id']=='T-HVA-001-POS').__setitem__('execution_state','PASS'))
 add('review row omitted','REVIEW_SCOPE',lambda x:x['findings'].pop())
 add('review row unmapped','UNRESOLVED_REVIEW_MAPPING',lambda x:x['findings'][0].__setitem__('requirements',[]))
 add('review fake test','UNKNOWN_REVIEW_BINDING',lambda x:x['findings'][0]['acceptance_contracts'].append('FAKE_TEST'))
 add('adoption omitted','ADOPTION_SCOPE',lambda x:x['adoptions'].pop())
 add('adoption empty','ADOPTION_EMPTY',lambda x:x['adoptions'][0].__setitem__('units',[]))
 add('service dependency stale','SERVICE_DEPENDENCY_DRIFT',lambda x:x['new']['services'][0].__setitem__('dependencies',[]))
 add('packet old/new confused','PACKET_ALIAS_MISMATCH',lambda x:x['packet_map'][0].__setitem__('target_packet_id','VAN-PKT-999'))
 add('domain omitted from final catalogue','HVA_PRODUCER_ORDER',lambda x:next(r for r in x['new']['units'] if r['id']=='BE-032').__setitem__('dependencies',['BE-001']))
 out=[]
 for title,code,fn in cases:
  x=copy.deepcopy(b);fn(x)
  if x==b:raise ValueError('NOOP_MUTATION:'+title)
  codes={e['code'] for e in validate(x,False)['findings']};out.append({'case':title,'expected':code,'caught':code in codes})
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');a=p.parse_args();b=load(ROOT);o=validate(b)
 if a.selftest:o['negative_cases']=selftest(b);o['negative_cases_caught']=sum(x['caught'] for x in o['negative_cases'])
 print(json.dumps(o,indent=2));sys.exit(bool(o['findings']) or any(not x['caught'] for x in o.get('negative_cases',[])))
