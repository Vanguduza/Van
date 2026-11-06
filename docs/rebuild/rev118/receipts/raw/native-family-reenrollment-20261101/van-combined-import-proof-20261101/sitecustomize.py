import builtins,sys,os,json,hashlib
from pathlib import Path
_dir=Path(__file__).parent
_config=json.loads((_dir/'config.json').read_text())
_seen=set()
_original=builtins.__import__
def _recorded_import(*args,**kwargs):
    result=_original(*args,**kwargs)
    for name,binding in _config['modules'].items():
        module=sys.modules.get(name)
        if name not in _seen and module is not None and getattr(module,'__file__',None):
            path=Path(module.__file__).resolve()
            expected=Path(_config['root'])/binding['path']
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            if path!=expected or actual!=binding['sha256']:raise ImportError('combined SOURCE import identity differs: '+name)
            _seen.add(name)
            with (_dir/('imports-'+str(os.getpid())+'.jsonl')).open('a') as stream:
                stream.write(json.dumps(dict(pid=os.getpid(),ppid=os.getppid(),module=name,path=str(path),sha256=actual))+'\n')
    return result
builtins.__import__=_recorded_import
