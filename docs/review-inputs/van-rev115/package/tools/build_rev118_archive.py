#!/usr/bin/env python3
"""Build and independently extract the already-sealed Rev1.18 document package."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,zipfile
P=Path(__file__).resolve().parents[1];B=P.parent
name='VAN_NEXT_WHOLE_PRODUCT_BLUEPRINT_PACK_REV1_18_20261021.zip';prefix='VAN_NEXT_WHOLE_PRODUCT_REV1_18_20261021/';archive=B/name
subprocess.run(['python3','-B','verification/verify_rev117.py','--check-package','--json'],cwd=P,check=True,capture_output=True)
files=[f for f in sorted(P.rglob('*')) if f.is_file()]
assert not any('__pycache__' in f.parts for f in files)
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for f in files:
  info=zipfile.ZipInfo(prefix+f.relative_to(P).as_posix(),(2026,10,21,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,f.read_bytes(),compresslevel=9)
r={'revision':'1.18','scope':'ARCHIVE_IDENTITY_AND_FRESH_EXTRACTION_DOCUMENT_CHECKS_ONLY','parent_commit':'673a1cc6fa2549a747bd0e2097202ebeceffb5d1','archive':name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'application_tests_executed':0,'native_or_economic_qualification_issued':False,'checks':[]}
with tempfile.TemporaryDirectory(prefix='van-rev118-',dir='/tmp') as td:
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  assert len(z.namelist())==len(files)
  assert {n.removeprefix(prefix) for n in z.namelist()}=={f.relative_to(P).as_posix() for f in files}
  assert all(z.read(n)==(P/n.removeprefix(prefix)).read_bytes() for n in z.namelist())
  r.update(crc_all_members_ok=True,archive_members=len(files),archive_matches_unpacked_package=True);z.extractall(td)
 for args in [['plan/compile_rev118.py','--check'],['plan/render_plan.py','--check'],['verification/verify_whole_product.py'],['verification/verify_rev117.py','--json'],['verification/verify_review_contracts.py'],['verification/verify_experience_learning.py'],['verification/verify_model_hardening.py'],['verification/verify_theme_readability.py'],['verification/verify_rev117.py','--check-package','--json']]:
  cmd=['python3','-B',*args];out=subprocess.run(cmd,cwd=Path(td)/prefix,capture_output=True,text=True);r['checks'].append({'command':cmd,'exit_code':out.returncode,'stdout':out.stdout,'stderr':out.stderr});print(args[0],out.returncode,flush=True);assert out.returncode==0,out.stdout+out.stderr
r['passed']=True;(B/'REV1_18_FINAL_PACKAGE_RECEIPT.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='checks'},indent=2))
