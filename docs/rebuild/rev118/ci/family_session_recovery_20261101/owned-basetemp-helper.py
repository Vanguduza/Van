from pathlib import Path
import shutil,os,json,hashlib,datetime

def preflight(path):
 p=Path(path);assert p.parent==Path('/tmp') and p.name.startswith('van-recovery-') and not p.exists()
 use=shutil.disk_usage('/tmp');stat=os.statvfs('/tmp');assert use.free>=4*1024**3 and stat.f_favail>=100000
 return {'path':str(p),'free_bytes_before':use.free,'free_inodes_before':stat.f_favail,'minimum_free_bytes':4*1024**3,'no_preexisting_directory':True}
def cleanup(path,out):
 p=Path(path);out=Path(out);assert p.parent==Path('/tmp') and p.name.startswith('van-recovery-') and not p.is_symlink()
 if not p.exists():return {'path':str(p),'created':False,'independently_absent':True}
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  for c in [proc/'cwd',*(proc/'fd').glob('*')]:
   try:target=os.readlink(c)
   except OSError:continue
   assert not(target==str(p) or target.startswith(str(p)+'/')),('Active owned-temp handle',proc.name,target)
 entries=[{'path':str(f.relative_to(p)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in p.rglob('*') if f.is_file() and not f.is_symlink()]
 inventory=out/'owned-temp-inventory.json';assert not inventory.exists();inventory.write_text(json.dumps({'directory':str(p),'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':entries},indent=2)+'\n');before=shutil.disk_usage('/tmp');shutil.rmtree(p);after=shutil.disk_usage('/tmp');assert not p.exists();return {'path':str(p),'files':len(entries),'inventory':str(inventory),'inventory_sha256':hashlib.sha256(inventory.read_bytes()).hexdigest(),'free_bytes_before_cleanup':before.free,'free_bytes_after_cleanup':after.free,'free_inodes_after':os.statvfs('/tmp').f_favail,'independently_absent':True}
