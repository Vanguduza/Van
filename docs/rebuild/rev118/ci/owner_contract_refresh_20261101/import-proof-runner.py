"""External observation only: preserve actual imported product module origins."""
import sys,runpy,json,hashlib
from pathlib import Path
proof=Path(sys.argv.pop(1));root=Path.cwd().resolve()
try:
 runpy.run_path(str(root/'tools/rebuild/source_storage_audit.py'),run_name='__main__')
finally:
 modules={}
 for name,module in tuple(sys.modules.items()):
  if name=='vati' or name.startswith('vati.'):
   file=getattr(module,'__file__',None)
   if file:
    p=Path(file).resolve();assert p.is_relative_to(root/'trading'/'vati'),(name,str(p))
    modules[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 assert modules
 proof.write_text(json.dumps({'source_root':str(root),'all_observed_product_imports_inside_exact_worktree':True,'modules':modules},indent=2)+'\n')
