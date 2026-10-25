import hashlib,json,pathlib,subprocess,tempfile,types,shutil
from test_native_market_archive import contract,observation
from vati.market_data.native_archive import NativeMarketArchive
base='ad1d3941d6a0257ee9966fd66f02eddb76af04de'
path='trading/vati/market_data/native_archive.py'
old=subprocess.check_output(['git','show',base+':'+path],text=True)
module=types.ModuleType('baseline_native_archive');module.__file__=path
exec(compile(old,path,'exec'),module.__dict__)
out=pathlib.Path('/workspace/van-native-quote-bar-compatibility-20261025');out.mkdir(exist_ok=True)
c=contract();obs=observation(c)
with tempfile.TemporaryDirectory(prefix='van-native-quote-bar-compat-') as temporary:
 root=pathlib.Path(temporary)/'native';original=module.NativeMarketArchive(root,clock=lambda:400000)
 before=original.record('captured-before-quote-refactor',c,obs)
 bytes_before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json')}
 current=NativeMarketArchive(root,clock=lambda:500000)
 after=current.lookup(c.native_scope,'M1','captured-before-quote-refactor')
 assert before==after
 assert current.record('captured-before-quote-refactor',c,obs)==before
 bytes_after={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json')}
 assert bytes_before==bytes_after
 shutil.copytree(root,out/'baseline_archive',dirs_exist_ok=True)
 receipt={'schema':'van.native-bar-archive-compatibility/1','baseline_commit':base,'baseline_source_sha256':hashlib.sha256(old.encode()).hexdigest(),'current_source_sha256':hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest(),'receipt_unchanged':before==after,'original_json_bytes_unchanged':bytes_before==bytes_after,'file_sha256':{p:hashlib.sha256(blob).hexdigest() for p,blob in bytes_before.items()},'original_receipt':before,'scope':'Generated actual baseline implementation capture replayed by current implementation; unqualified source fixture, not live provider evidence'}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt))
