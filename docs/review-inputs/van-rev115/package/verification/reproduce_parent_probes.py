"""Replay the exact reviewed document-only probes against the exact parent archive."""
import hashlib,json,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path,PurePosixPath
P=Path(__file__).resolve().parents[1]
archive=P/'lineage/REV1_14_EXACT_PARENT.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='f12020bd852d2c3a6f8f8ee237f4cf7a3dba7665762d05f984f0eae271f4dc37'
with tempfile.TemporaryDirectory(prefix='van-document-review-') as tmp:
 root=Path(tmp);dest=root/'input';dest.mkdir()
 with zipfile.ZipFile(archive) as z:
  names=set()
  for info in z.infolist():
   n=PurePosixPath(info.filename)
   if n.is_absolute() or '..' in n.parts or info.filename in names or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('UNSAFE_PARENT_ARCHIVE')
   names.add(info.filename)
  z.extractall(dest)
 shutil.copy2(P/'evidence/rev115/review_probes.py',root/'review_probes.py')
 r=subprocess.run([sys.executable,'-B',str(root/'review_probes.py')],cwd=root,capture_output=True,text=True,timeout=30)
 if r.returncode:print(r.stderr,file=sys.stderr);raise SystemExit(r.returncode)
 actual=json.loads((root/'independent_probe_results.json').read_text());expected=json.loads((P/'evidence/rev115/independent_probe_results.json').read_text())
 equal=actual==expected
 print(json.dumps({'scope':'EXACT_PARENT_DOCUMENT_PROBE_REPLAY_ONLY','equal':equal,'probes':len(actual['probes']),'application_tests_executed':0},indent=2))
 raise SystemExit(0 if equal else 1)
