import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/workspace/van-review-2026-10-18/publish');source=root/'trading/vati/execution/ctrader/transport.py';original=source.read_text()
out=pathlib.Path('/workspace/van-read-capacity-mutations-20261025');out.mkdir(exist_ok=True)
variants={
 'omit-frame-header-accounting':('                self._admit_frame_header(ln)','                pass  # supplemental fault omits header accounting'),
 'omit-encoded-byte-limit':('                    or length>self.max_read_bytes-self._reserved_encoded_bytes','                    or False'),
 'refund-on-reconnect':('            self.check_budget()  # Includes elapsed connector work, even before auth.','            self._admitted_frame_headers=self._reserved_encoded_bytes=0\n            self.check_budget()  # supplemental fault refunds frames on reconnect'),
}
receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(old,new) in variants.items():
  assert original.count(old)==1,(name,original.count(old))
  mutated=original.replace(old,new);source.write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_ctrader_read_capacity.py','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
  receipts.append({'case':name,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});source.write_text(original)
finally:
 source.write_text(original)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','control_sha256':hashlib.sha256(original.encode()).hexdigest(),'source_restored':source.read_text()==original,'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
print(json.dumps(receipts));assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
