#!/usr/bin/env python3
"""Verify all distributed files against the package manifest, without network calls."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);a=ap.parse_args();r=a.root.resolve();m=json.loads((r/'MANIFEST.json').read_text());errors=[];listed=set()
 for f in m['files']:
  rel=f['path'];p=(r/rel).resolve()
  if r not in p.parents:errors.append('UNSAFE_PATH:'+rel);continue
  if rel in listed:errors.append('DUPLICATE_MEMBER:'+rel)
  listed.add(rel)
  if not p.is_file() or p.is_symlink():errors.append('MISSING_OR_LINK:'+rel);continue
  if len(p.read_bytes())!=f['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:errors.append('MEMBER_MISMATCH:'+rel)
 actual={str(p.relative_to(r)) for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.json'}
 for x in sorted(actual-listed):errors.append('UNLISTED_MEMBER:'+x)
 print(json.dumps({'scope':'Package identity only, not signature or implementation qualification','members':len(listed),'findings':errors},indent=2));return 1 if errors else 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:print(str(e),file=sys.stderr);raise SystemExit(2)
