from pathlib import Path, PurePosixPath
import json,urllib.request,hashlib,zipfile,stat,xml.etree.ElementTree as E
meta=json.loads(Path('/workspace/van-37327981-selected-hosted-download-20261028.json').read_text())
out=Path('/workspace/van-37327981-selected-hosted-20261028');out.mkdir(exist_ok=True)
assert meta['workflow_run']['head_sha']=='3732798104c476680cac8e22f833f2ed764d77e2'
with urllib.request.urlopen(meta['url'],timeout=60) as r: data=r.read(8*1024*1024+1)
assert len(data)==meta['size_in_bytes']<8*1024*1024
digest=hashlib.sha256(data).hexdigest();assert meta['digest']=='sha256:'+digest
p=out/'original-12818970544.zip';p.write_bytes(data)
files={}
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 names=z.namelist();assert len(names)==len(set(names))
 for info in z.infolist():
  rel=PurePosixPath(info.filename)
  assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in info.filename
  assert not stat.S_ISLNK(info.external_attr>>16)
  if info.is_dir():continue
  content=z.read(info);target=out/'extracted'/info.filename
  target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
  assert target.read_bytes()==content
  files[info.filename]=hashlib.sha256(content).hexdigest()
summaries={}
for name in files:
 if name.endswith('.xml'):
  root=E.parse(out/'extracted'/name).getroot();cases=list(root.iter('testcase'))
  summaries[name]={'cases':len(cases),'passed':sum(not any(c.tag in ('skipped','failure','error') for c in t) for t in cases),'skipped':sum(len(t.findall('skipped')) for t in cases),'failed':sum(len(t.findall('failure')) for t in cases),'errors':sum(len(t.findall('error')) for t in cases),'skip_reasons':[c.get('message') for t in cases for c in t.findall('skipped')]}
v={'head':meta['workflow_run']['head_sha'],'run_id':40692934675,'artifact_id':meta['id'],'size':len(data),'sha256':digest,'github_digest_verified':True,'zip_crc_paths_duplicates_symlinks_checked':True,'extracted_file_sha256':files,'junit':summaries,'source_evidence_only':True}
(out/'verified-evidence.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({k:v[k] for k in ['head','artifact_id','size','sha256','junit']}))
