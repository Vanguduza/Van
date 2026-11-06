#!/usr/bin/env python3
"""Reproduce the compact graph checks run through Global DIAL on van-trading-core.
This checks the exported graph, not runtime services or F15/BG authorization.
"""
from __future__ import annotations
import json,copy,argparse,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def validate(x):
 rows=x['nodes'];names=[r[0] for r in rows];u={r[0]:r for r in rows};errors=[]
 if len(names)!=len(u):errors.append('DUPLICATE_UNIT')
 b={r[0] for r in rows if r[1]=='BACKEND'};v={r[0] for r in rows if r[1]=='BACKEND_VERIFICATION'};ui={r[0] for r in rows if r[1] in ['FRONTEND','FRONTEND_DESIGN']}
 if b!=set(x['required_backend_ids']) or v!=set(x['required_backend_verification_ids']):errors.append('SCOPE_MISMATCH')
 if set(u['BG-001'][3])!=b|v:errors.append('BG_SCOPE')
 def anc(i):
  q=list(u.get(i,[None,None,None,[]])[3]);seen=set()
  while q:
   z=q.pop()
   if z not in seen:seen.add(z);q.extend(u.get(z,[None,None,None,[]])[3])
  return seen
 for i,k,s,deps in rows:
  aa=anc(i)
  if any(d not in u for d in deps):errors.append('MISSING_DEPENDENCY')
  if len(deps)!=len(set(deps)):errors.append('DUPLICATE_DEPENDENCY')
  if i in aa:errors.append('CYCLE')
  if any(u[d][2]>s for d in deps if d in u):errors.append('PHASE_INVERSION')
  if k not in ['PREDEVELOPMENT','PREDEVELOPMENT_GATE'] and 'PRE-003' not in aa:errors.append('NO_F15')
  if i in ui and 'BG-001' not in aa:errors.append('UI_BEFORE_BG')
  if i in b|v and ui&aa:errors.append('BACKEND_AFTER_UI')
  if i in b|v and i not in anc('BG-001'):errors.append('BACKEND_NOT_COVERED')
  if k=='BACKEND' and i!='BE-001' and 'BE-001' not in aa:errors.append('NO_PARITY')
 for consumer,producer in [('BE-036','BE-035'),('BE-032','BE-036'),('VAN-ML-PKT-008','BE-035'),('VAN-ML-PKT-009','BE-035'),('BG-001','BQ-007')]:
  if producer not in anc(consumer):errors.append('PRODUCER_ORDER')
 return sorted(set(errors))
def selftest(g):
 def node(x,i):return next(r for r in x['nodes'] if r[0]==i)
 cases=[('duplicate','DUPLICATE_UNIT',lambda x:x['nodes'].append(copy.deepcopy(x['nodes'][0]))),('cycle','CYCLE',lambda x:node(x,'PRE-001')[3].append('BE-001')),('unknown','MISSING_DEPENDENCY',lambda x:node(x,'BE-004')[3].append('MISSING')),('missing bg member','BG_SCOPE',lambda x:node(x,'BG-001')[3].remove('BE-035')),('wrong scope','SCOPE_MISMATCH',lambda x:x['required_backend_ids'].pop()),('ux shortcut','UI_BEFORE_BG',lambda x:node(x,'UX-001').__setitem__(3,['PRE-003'])),('frontend shortcut','UI_BEFORE_BG',lambda x:node(x,'FE-004').__setitem__(3,['PRE-003'])),('code before f15','NO_F15',lambda x:node(x,'BE-001').__setitem__(3,['PRE-001'])),('evaluator missing','PRODUCER_ORDER',lambda x:node(x,'BE-036').__setitem__(3,['PRE-003','BE-001'])),('catalog missing','PRODUCER_ORDER',lambda x:node(x,'BE-032').__setitem__(3,['PRE-003','BE-001'])),('backward ui','BACKEND_AFTER_UI',lambda x:node(x,'BE-004')[3].append('FE-004')),('duplicate dependency','DUPLICATE_DEPENDENCY',lambda x:node(x,'BE-035')[3].append(node(x,'BE-035')[3][0])),('parity skipped','NO_PARITY',lambda x:node(x,'BE-004').__setitem__(3,['PRE-003'])),('training shortcut','PRODUCER_ORDER',lambda x:node(x,'VAN-ML-PKT-008').__setitem__(3,['PRE-003','BE-001']))]
 out=[]
 for name,code,mut in cases:
  t=copy.deepcopy(g);mut(t)
  if t==g:raise ValueError('NOOP_MUTATION:'+name)
  out.append({'case':name,'expected':code,'caught':code in validate(t)})
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');a=p.parse_args();raw=(ROOT/'evidence/GRAPH_EXPORT.json').read_bytes().rstrip(b'\n');g=json.loads(raw)
 if g['plan_sha256']!=hashlib.sha256((ROOT/'plan/DEVELOPMENT_PLAN.json').read_bytes()).hexdigest():raise SystemExit('STALE_GRAPH_EXPORT')
 errors=validate(g);out={'findings':errors,'graph_sha256':hashlib.sha256(raw).hexdigest(),'plan_sha256':g['plan_sha256'],'scope':'Compact document graph only'}
 if a.selftest:
  out['negative_cases']=selftest(g)
  if not all(x['caught'] for x in out['negative_cases']):errors.append('MISSED_MUTATION')
 print(json.dumps(out,indent=2));raise SystemExit(1 if errors else 0)
