#!/usr/bin/env python3
"""Collect exact source evidence from an authorized existing Git checkout.
No fetch, checkout, build, broker call, secret read or tracked-file modification.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
SOURCE='a39f241b0135cf92cc5a6b9a28af226aa294603d';BASE='8eb1889822fc8a83f219977c15340172e16acd91'
def git(repo,*args):
 p=subprocess.run(['git','-C',str(repo),*args],capture_output=True,timeout=60)
 if p.returncode:raise ValueError(f'Git {args[0]} failed: '+p.stderr.decode(errors='replace')[:250])
 return p.stdout

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args();r=a.repo.resolve();out=a.output.resolve()
 if out==r or r in out.parents:raise ValueError('Evidence output must be outside the source worktree')
 head=git(r,'rev-parse','HEAD').decode().strip()
 if head!=SOURCE:raise ValueError('Unexpected source HEAD '+head)
 if git(r,'status','--porcelain=v1','-uno').strip():raise ValueError('Tracked source is dirty; do not certify it')
 changes=git(r,'diff','--name-status','-z',BASE,SOURCE).split(b'\0');entries=[];i=0
 while i<len(changes) and changes[i]:
  state=changes[i].decode();i+=1
  if state.startswith(('R','C')):old=changes[i].decode();new=changes[i+1].decode();i+=2
  else:new=changes[i].decode();old=new;i+=1
  row={'path':new,'base_path':old,'change':state}
  for label,sha,path in [('source',SOURCE,new),('base',BASE,old)]:
   p=subprocess.run(['git','-C',str(r),'show',sha+':'+path],capture_output=True,timeout=40)
   if p.returncode:row[label+'_sha256']=None;continue
   row[label+'_sha256']=hashlib.sha256(p.stdout).hexdigest();row[label+'_bytes']=len(p.stdout)
  entries.append(row)
 data={'schema':'van.pinned.source.manifest/1.0','repository':'Vanguduza/Van','source_sha':SOURCE,'base_sha':BASE,'scope':'All changed Git blobs; hashes not semantic or runtime proof','files':entries}
 out.mkdir(parents=True,exist_ok=True);(out/'SOURCE_BLOB_MANIFEST.json').write_text(json.dumps(data,indent=2)+'\n')
 for path in ['docs/design/van-next/VAN_NEXT_OWNER_DECISIONS_REV1.md','docs/design/van-next/VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9B_20261016.md','docs/design/van-next/plan/generate_plan.py','docs/design/van-next/plan/REQUIREMENT_LOCK_REV1_9B.json','docs/design/van-next/contracts/check_state_machines.py','docs/design/van-next/contracts/VAN_TRANSITION_GUARDS_REV1_9B.json','docs/design/van-next/contracts/VAN_STATE_MACHINES_REV1_9.json']:
  b=git(r,'show',SOURCE+':'+path);p=out/'source_documents'/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 print(json.dumps({'source_sha':SOURCE,'changed_paths':len(entries),'output':str(out),'scope':'Read-only exact blob collection; no code changes or qualification issuance'}));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,OSError,subprocess.SubprocessError) as e:print(str(e),file=sys.stderr);raise SystemExit(2)
