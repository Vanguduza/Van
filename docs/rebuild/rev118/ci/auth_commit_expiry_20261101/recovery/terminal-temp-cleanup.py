from pathlib import Path
import json,hashlib,os,shutil,datetime
W=Path('/workspace');recovery=W/'van-storage-exhaustion-recovery-20261101.json';d=json.loads(recovery.read_text())
owned=[('pytest-36','van-auth-corrected-affected-20261101',171858,171854),('pytest-39','van-auth-corrected-remainder-20261101',260479,260461),('pytest-38','van-successor-regression-pg-r2-20261101',237656,235682)]
for name,stem,pid,controller in owned:
 root=Path('/tmp/pytest-of-agent')/name;assert root.is_dir() and not root.is_symlink();assert not Path('/proc',str(pid)).exists() and not Path('/proc',str(controller)).exists()
 if stem.startswith('van-successor'):
  terminal=W/stem/'receipt.json';xml=W/stem/'full-trading.xml';t=json.load(open(terminal));assert t['completed'] and t['cleaned'] and t['owned_fixture_independently_absent']
 else:
  terminal=W/(stem+'.json');xml=W/(stem+'.xml');t=json.load(open(terminal));assert t['state']=='COMPLETED' and t['command_pid']==pid
 assert str(root) in xml.read_text(),('Original raw failure does not attribute temp tree',name)
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  for candidate in [proc/'cwd',*(proc/'fd').glob('*')]:
   try:target=os.readlink(candidate)
   except OSError:continue
   assert not (target==str(root) or target.startswith(str(root)+'/')),('Active handle',proc.name,target)
 entries=[{'path':str(f.relative_to(root)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in root.rglob('*') if f.is_file() and not f.is_symlink()]
 manifest=W/('van-owned-'+name+'-temp-inventory-20261101.json');assert not manifest.exists();manifest.write_text(json.dumps({'directory':str(root),'owner_command_pid':pid,'terminal_receipt':str(terminal),'terminal_sha256':hashlib.sha256(terminal.read_bytes()).hexdigest(),'original_failure_xml':str(xml),'original_failure_xml_sha256':hashlib.sha256(xml.read_bytes()).hexdigest(),'files':entries},indent=2)+'\n')
 before=shutil.disk_usage('/tmp');shutil.rmtree(root);after=shutil.disk_usage('/tmp');d['cleanup'].append({'directory':str(root),'inventory':str(manifest),'inventory_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'files':len(entries),'free_bytes_before':before.free,'free_bytes_after':after.free,'removed':True});recovery.write_text(json.dumps(d,indent=2)+'\n');print(name,len(entries),before.free,after.free,flush=True)
