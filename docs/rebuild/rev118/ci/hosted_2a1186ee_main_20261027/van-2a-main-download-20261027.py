from pathlib import Path,PurePosixPath
import json,hashlib,urllib.request,zipfile,stat
transfer=Path('/workspace/van-2a-main-private-transfer-20261027.json')
out=Path('/workspace/van-2a1186ee-main-hosted');out.mkdir(exist_ok=True)
data=json.loads(transfer.read_text());receipts=[]
def sha(b):return hashlib.sha256(b).hexdigest()
try:
 for item in data['downloads']:
  a=item['artifact'];dest=out/(a['name']+'.zip')
  if not dest.exists():
   with urllib.request.urlopen(item['download']['download_url'],timeout=60) as response:raw=response.read()
   assert len(raw)==a['size_in_bytes'],a['name']
   if a.get('digest'):assert a['digest']=='sha256:'+sha(raw)
   dest.write_bytes(raw)
  raw=dest.read_bytes();assert len(raw)==a['size_in_bytes']
  if a.get('digest'):assert a['digest']=='sha256:'+sha(raw)
  root=out/a['name'];root.mkdir(exist_ok=True)
  with zipfile.ZipFile(dest) as archive:
   assert archive.testzip() is None
   for info in archive.infolist():
    name=PurePosixPath(info.filename);assert not name.is_absolute() and '..' not in name.parts and '\\' not in info.filename
    assert not stat.S_ISLNK(info.external_attr>>16)
   archive.extractall(root)
  receipts.append({'artifact_id':a['id'],'name':a['name'],'bytes':len(raw),'sha256':sha(raw),'github_digest':a.get('digest'),'crc_path_symlink_verified':True})
 (out/'download-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
 (out/'run-and-jobs-metadata.json').write_text(json.dumps({k:data[k] for k in ['runs','jobs','artifacts']},indent=2)+'\n')
 for name,value in data['logs'].items():
  text=value if isinstance(value,str) else value.get('content',value.get('logs'))
  assert isinstance(text,str)
  (out/(name+'-job.log')).write_bytes(text.encode('utf-8'))
 print(json.dumps({'archives':len(receipts),'bytes':sum(x['bytes'] for x in receipts),'out':str(out)}))
finally:transfer.unlink(missing_ok=True)
