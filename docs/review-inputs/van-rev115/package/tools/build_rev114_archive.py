#!/usr/bin/env python3
"""Build a deterministic documentation ZIP; never signs or issues readiness."""
from pathlib import Path
import argparse,hashlib,json,zipfile,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 output=args.output.resolve()
 if ROOT==output or ROOT in output.parents:raise ValueError('Archive output must be outside the source root')
 files=sorted([p for p in ROOT.rglob('*') if p.is_file() and p.name!='MANIFEST.json' and '__pycache__' not in p.parts],key=lambda p:p.relative_to(ROOT).as_posix())
 records={}
 for p in files:
  if p.is_symlink():raise ValueError('Symlink not allowed: '+str(p))
  if p.suffix.lower() in ('.ttf','.otf','.woff','.woff2'):raise ValueError('Font binary not redistributed: '+str(p))
  name=p.relative_to(ROOT).as_posix();records[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
 manifest={'schema':'van.documentation-archive-manifest/1.14','revision':'1.14','authority':'PREPARED_IDENTITY_ONLY_NOT_A_SIGNATURE_OR_RUNTIME_QUALIFICATION','file_count_excluding_manifest':len(records),'files':records}
 (ROOT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
 files=sorted([*files,ROOT/'MANIFEST.json'],key=lambda p:p.relative_to(ROOT).as_posix());output.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in files:
   info=zipfile.ZipInfo(ROOT.name+'/'+p.relative_to(ROOT).as_posix(),date_time=(2026,10,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.external_attr=(0o100644<<16)
   z.writestr(info,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
 with zipfile.ZipFile(output) as z:
  bad=z.testzip()
  if bad:raise ValueError('ZIP CRC failure:'+bad)
 print(json.dumps({'archive':str(output),'bytes':output.stat().st_size,'files':len(files),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'scope':'document identity; no application result'},sort_keys=True));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as ex:print(str(ex),file=sys.stderr);raise SystemExit(2)
