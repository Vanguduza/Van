from pathlib import Path
import subprocess,hashlib,json,tempfile,importlib.util,sys
root=Path('/workspace/van-review-2026-10-18/publish');source='deploy/van-trading-core/mql5/VanBridgeEA.mq5'
base='bf41e16b0213431eeaeb33da96676cfb7dc47477'
old=subprocess.check_output(['git','show',base+':'+source],cwd=root,text=True)
current=(root/source).read_text()
def entry(text):
 start=text.index('void ExecOrderSend(');at=text.index('{',start)+1;depth=1;quoted=False;escaped=False
 while depth:
  c=text[at];at+=1
  if escaped:escaped=False
  elif quoted and c=='\\':escaped=True
  elif c=='"':quoted=not quoted
  elif not quoted:
   if c=='{':depth+=1
   elif c=='}':depth-=1
 return start,at
start,end=entry(old);old_body=old[start:end]
a,b=entry(current);mixed=current[:a]+old_body+current[b:]
sys.path[:0]=[str(root/'trading'),str(root/'trading/tests')]
spec=importlib.util.spec_from_file_location('original_ea_cash_source_before',root/'trading/tests/test_mql_native_function_bodies.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='van-owned-original-ea-cash-') as folder:
 path=Path(folder);candidate=path/'original-entry-body.mq5';candidate.write_text(mixed);module.EA=candidate
 class Factory:
  def mktemp(self,name):
   p=path/name;p.mkdir();return p
 run=module.ea.__wrapped__(Factory());results={name:run(name) for name in ['entry-cash-credit','entry-cash-used','entry-good']}
 assert all(results[n]['entry_calls']==1 and results[n]['margin_calls']==0 and results[n]['results'][0]['status']=='FILLED' for n in results)
receipt={'schema':'van.original-ea-entry-body-cash-counterexample/1','original_source_commit':base,
 'original_entry_body_sha256':hashlib.sha256(old_body.encode()).hexdigest(),
 'fixture_sha256':hashlib.sha256((root/'trading/tests/mql_terminal_fixture.cpp').read_bytes()).hexdigest(),
 'method':'Exact original published ExecOrderSend body; current supplemental helper declarations unused by that body; controlled C++ terminal API fixture. Not MetaTrader runtime or connected broker evidence.',
 'numeric_values_encoding':'Parsed Decimal values preserved as exact text in this source artifact only',
 'results':results,'actual_verifier_exit':0,'formal_native_financial_acceptance':'NOT_ISSUED'}
Path('/workspace/van-mt5-final-cash-margin-ea-before-20261028.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n')
print(json.dumps({'original_entry_body_sha256':receipt['original_entry_body_sha256'],'cases':{n:{'entry_calls':r['entry_calls'],'margin_calls':r['margin_calls'],'status':r['results'][0]['status']} for n,r in results.items()},'not_MetaTrader_runtime':True}))
