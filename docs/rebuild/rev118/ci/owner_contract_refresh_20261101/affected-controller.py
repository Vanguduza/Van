from pathlib import Path
import sys,subprocess,json,datetime,hashlib,os
sys.path.insert(0,'/workspace')
from van_owned_basetemp_20261101 import preflight,cleanup
root=Path('/workspace/van-lanes-20261101/d43-endpoint-ci-fix')
out=Path('/workspace/van-d43-endpoint-registry-affected-r3-20261101');out.mkdir(exist_ok=False)
temp='/tmp/van-recovery-d43-endpoint-registry-affected-r3-20261101'
receipt={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_parent':'d43bd396765204a4843cdb7485535e9fcd7af3ce','owned_temp_preflight':preflight(temp)}
targets=['tests/contracts/test_owner_endpoint_registry.py','tests/contracts/test_owner_redesign_registry.py','tests/rebuild/test_owner_registry_refresh.py']
receipt['source_pins']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'backend/van_gateway/app.py',root/'registries/owner_endpoints.json',root/'registries/owner_endpoint_schemas.json',root/'tools/audit/export_owner_endpoints.py',root/'pytest.ini',*[root/t.split('::')[0] for t in targets]]}
cmd=['/workspace/van-backend-venv-20261025/bin/python','/workspace/van-source-import-proof-runner-20261101.py',str(out/'actual-imports.json'),'--report',str(out/'storage-audit.json'),*targets,'--basetemp='+temp,'--junitxml='+str(out/'tests.xml'),'-q'];receipt['command']=cmd
with (out/'tests.log').open('w') as log:
 try:receipt['exit']=subprocess.run(cmd,cwd=root,env={**os.environ,"PYTHONPATH":str(root/"trading")},stdout=log,stderr=subprocess.STDOUT,timeout=900).returncode
 except subprocess.TimeoutExpired:receipt['state']='TIMEOUT';raise
 finally:
  receipt['owned_temp_cleanup']=cleanup(temp,out);receipt['completed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'exit':receipt['exit'],'receipt':str(out/'receipt.json')}))
