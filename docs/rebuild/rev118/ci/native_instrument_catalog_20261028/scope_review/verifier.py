from pathlib import Path
import subprocess,json,hashlib
root=Path('/workspace/van-review-2026-10-18/publish')
def original(p):return subprocess.check_output(['git','show','HEAD:'+p],cwd=root)
old=json.loads(Path('/workspace/van-native-instrument-catalog-workmap-preimage-20261028.json').read_text())
new=json.loads((root/'docs/rebuild/rev118/SOURCE_WORKMAP.json').read_text())
for key in ['counts','units','canonical_package_tree']:assert old[key]==new[key]
for k,v in old['identity_contract_hashes'].items():
 assert v.keys()==new['identity_contract_hashes'][k].keys()
 if k not in ['source_features','source_surfaces']:assert v==new['identity_contract_hashes'][k]
results={}
for name,key in [('owner_features','features'),('owner_screens','screens')]:
 a=json.loads(original('registries/'+name+'.json'));b=json.loads((root/'registries'/str(name+'.json')).read_text());diffs=[]
 def walk(x,y,path=''):
  if x==y:return
  if isinstance(x,dict) and isinstance(y,dict):
   assert x.keys()==y.keys(),path
   for k in x:walk(x[k],y[k],path+'/'+k)
  elif isinstance(x,list) and isinstance(y,list):
   assert len(y)>=len(x),path
   identity=next((k for k in ['id','endpoint_id'] if x and all(isinstance(r,dict) and k in r for r in x+y) and len({r[k] for r in x})==len(x) and len({r[k] for r in y})==len(y)),None)
   if identity:
    ym={r[identity]:r for r in y};ids={r[identity] for r in x};assert ids<=ym.keys()
    assert [r[identity] for r in y if r[identity] in ids]==[r[identity] for r in x]
    for r in x:walk(r,ym[r[identity]],path+'/'+str(r[identity]))
    for r in y:
     if r[identity] not in ids:
      assert r.get('path')=='/v1/trading/market/instruments' and path.endswith('/backend_contract_extensions')
      diffs.append({'path':path+'/'+str(r[identity]),'change':'ADDED_CATALOG_EXTENSION'})
   else:
    assert len(x)==len(y),path
    for i in range(len(x)):walk(x[i],y[i],path+'/'+str(i))
  else:
   if path.endswith('/source_ref'):
    xp,xl=x.rsplit(':',1);yp,yl=y.rsplit(':',1);assert xp==yp
    assert original(xp).decode().splitlines()[int(xl)-1]==(root/yp).read_text().splitlines()[int(yl)-1]
   else:assert path.endswith(('/source_ref/line','/source_ref/sha256')),path
   diffs.append({'path':path,'change':'SOURCE_CITATION_REFRESH'})
 walk(a[key],b[key]);assert sum(d['change']=='ADDED_CATALOG_EXTENSION' for d in diffs)==1
 results[name]={'all_original_ids_rows_values_and_order_preserved_except_source_citations':True,'changes':diffs}
results.update(frozen_unit_contracts_and_dependencies_preserved=True,all_identity_sets_and105_source_function_contract_hashes_preserved=True,
 changed_source_row_hashes={k:sum(v[i]!=new['identity_contract_hashes'][k][i] for i in v) for k,v in old['identity_contract_hashes'].items() if v!=new['identity_contract_hashes'][k]})
Path('/workspace/van-native-instrument-catalog-scope-review-20261028.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({k:v for k,v in results.items() if k not in ['owner_features','owner_screens']}))
