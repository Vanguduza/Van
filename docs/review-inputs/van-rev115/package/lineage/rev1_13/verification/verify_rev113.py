#!/usr/bin/env python3
"""Deterministic structural audit of Rev1.13 documentary pack. Never issues F15/BG or touches live services."""
import json,hashlib,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text())
def fail(cond,msg):
 if not cond:raise AssertionError(msg)
plan=read('plan/DEVELOPMENT_PLAN.json');units=plan['units'];d={u['id']:u for u in units}
assert len(d)==len(units)==131
assert set(plan['required_backend_ids'])=={u['id'] for u in units if u['kind']=='BACKEND'}
assert set(plan['required_backend_verification_ids'])=={u['id'] for u in units if u['kind']=='BACKEND_VERIFICATION'}
ss=read('design/ALL_SURFACE_CONTRACTS.json');req=read('traceability/REQUIREMENTS_AND_DU_MAPPING.json');tests=read('verification/TEST_CONTRACTS.json')
assert len(req['requirements'])==237 and len(ss['surfaces'])==234
assert len(tests['tests'])==tests['count'] and len(tests['tests'])==1328
assert len(set(x['id'] for x in tests['tests']))==len(tests['tests'])
assert all(x['execution_state']=='NOT_RUN' for x in tests['tests'])
for unit in units:
 assert unit['id'] not in unit.get('dependencies',[])
 for dep in unit.get('dependencies',[]):assert dep in d,(unit['id'],dep)
seen={}
def ancestor(k):
 if k in seen:return seen[k]
 a=set(d[k]['dependencies'])
 for x in d[k]['dependencies']:a.update(ancestor(x))
 seen[k]=a;return a
for b in plan['required_backend_ids']+plan['required_backend_verification_ids']:
 assert b in ancestor('BG-001'),b
for u in units:
 if u['kind'] not in ['PREDEVELOPMENT','PREDEVELOPMENT_GATE','BACKEND','BACKEND_VERIFICATION','BACKEND_GATE']:
  assert 'BG-001' in ancestor(u['id']),(u['id'],'UI before BG')
 if u['kind'] in ['BACKEND','BACKEND_VERIFICATION','BACKEND_GATE']:
  assert 'PRE-003' in ancestor(u['id']),(u['id'],'code before F15')
for x in ss['surfaces']:
 assert x.get('style_goldens')=='FUTURE_NATIVE_OWNER_SIGNOFF_AFTER_BG_001',x['id']
 assert x.get('style_modes')==['DARK_GRAPHITE','LIGHT_PORCELAIN','REDUCED_MOTION','ACCESSIBILITY_LARGE_TEXT','OFFLINE_STALE','LOADING','ERROR'],x['id']
 assert x.get('style_primary_component') and x.get('style_secondary_component'),x['id']
 for uid in x['frontend_units']: assert uid in d and d[uid]['kind']=='FRONTEND',(x['id'],uid)
recipes=read('design/COMPONENT_RECIPES_REV2.json');names={r['id'] for r in recipes['recipes']}
assert len(recipes['recipes'])==30 and len(names)==30
for x in ss['surfaces']:assert x['style_primary_component'] in names and x['style_secondary_component'] in names
styles=read('design/VAN_MATERIAL_TOKENS_REV2.json')
assert set(styles['color']['dark'])==set(styles['color']['light'])
assert len(styles['color']['dark'])>=28
def srgb_lumin(hexcode):
 parts=[int(hexcode[1+i:3+i],16)/255 for i in (0,2,4)]
 parts=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in parts]
 return sum(a*b for a,b in zip(parts,[.2126,.7152,.0722]))
def contrast(a,b):
 lo,hi=sorted((srgb_lumin(a),srgb_lumin(b)));return (hi+.05)/(lo+.05)
for theme in ('dark','light'):
 colors=styles['color'][theme]
 for key in ('text_primary','text_secondary','text_muted','accent','focus','positive','negative','warning'):
  for surface in ('canvas','surface','surface_raised'):
   assert contrast(colors[key],colors[surface])>=4.5,(theme,key,surface,contrast(colors[key],colors[surface]))

assert not read('verification/F15_CERTIFICATE.json').get('ready',False)
assert not read('verification/BACKEND_COMPLETE_CERTIFICATE.json').get('ready',False)
assert plan['backend_gate']=='BG-001' and plan['frontend_start']=='UX-001'
assert read('CANONICAL_AUTHORITY.json')['signed_authority'] is False
print(json.dumps({'schema':'van.document.rev113/1.0','finding_count':0,'packets':131,'backend':82,'bq':12,'scope':len(req['requirements']),'surfaces':234,'styles':len(styles['color']['dark']),'recipes':len(names),'tests_not_run':len(tests['tests']),'F15':'NOT_ISSUED','BG':'NOT_ISSUED'},sort_keys=True))
