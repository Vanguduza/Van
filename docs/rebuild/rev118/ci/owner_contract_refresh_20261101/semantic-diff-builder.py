from pathlib import Path
import subprocess,json,hashlib,datetime,re
root=Path('/workspace/van-lanes-20261101/d43-endpoint-ci-fix')
paths=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()
allowed={'registries/owner_endpoints.json','registries/owner_features.json','registries/owner_screens.json','docs/rebuild/rev118/backend/OWNER_REGISTRY_GENERATION.json'}
assert set(paths)==allowed|{'docs/rebuild/rev118/backend/OWNER_FRONTEND_SCREEN_REGISTRY.md'},paths
changes=[]
def compare(a,b,path):
 assert type(a)==type(b),(path,type(a),type(b))
 if isinstance(a,dict):
  assert a.keys()==b.keys(),path
  for k in a:compare(a[k],b[k],path+[k])
 elif isinstance(a,list):
  assert len(a)==len(b),path
  for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+[i])
 elif a!=b:changes.append({'path':path,'before':a,'after':b})
for rel in sorted(allowed):
 old=json.loads(subprocess.check_output(['git','show','HEAD:'+rel],cwd=root));new=json.loads((root/rel).read_text());compare(old,new,[rel])
for c in changes:
 p=c['path']
 if p[0].startswith('registries/'):
  assert p[-1] in {'source','source_ref'},c
  assert re.fullmatch(r'backend/van_gateway/app.py:\d+',c['before']) and re.fullmatch(r'backend/van_gateway/app.py:\d+',c['after']),c
  assert int(c['after'].split(':')[-1])-int(c['before'].split(':')[-1])==50,c
 else:assert p[1]=='outputs' and p[2] in allowed,c
features=json.loads((root/'registries/owner_features.json').read_text())['features'];screens=json.loads((root/'registries/owner_screens.json').read_text())['screens'];endpoints=json.loads((root/'registries/owner_endpoints.json').read_text())['endpoints'];schemas=json.loads((root/'registries/owner_endpoint_schemas.json').read_text())['components']['schemas'];funcs=[f for r in features for f in r.get('current_implementation',{}).get('functions',[])]
assert (len(endpoints),len(schemas),len(features),len(funcs),len(screens))==(484,378,42,105,78)
r={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_parent':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'source_change':'f8758db746582439819c1c1129ca64a8cf9fca7d inserted50 app.py lines before cited route declarations','only_derived_source_line_citations_and_generation_hashes_changed':True,'changes':changes,'counts':{'endpoints':484,'schemas':378,'groups':42,'functions':105,'surfaces':78},'earlier_instruction_inventory_counts':{'endpoints':479,'schemas':369,'disposition':'Historical counts; actual committed d43 inventory484/378 is preserved, no removals to force older figures'},'routes_schemas_authentication_roles_actions_changed':False,'guard_gap':'Previous packet omitted canonical owner/frontend registry --check after app.py source-location input changed. Exact hosted and local original failure retained.','after_pins':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(allowed)}}
Path('/workspace/van-d43-owner-contract-semantic-diff-20261101.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'changed_values':len(changes),'count_preservation':r['counts'],'semantic_behavior_changed':False}))
