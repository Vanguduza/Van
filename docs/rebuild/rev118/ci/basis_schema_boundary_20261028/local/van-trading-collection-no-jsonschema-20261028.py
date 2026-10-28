import importlib.abc,runpy,sys
class DocumentaryDependencyUnavailable(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='jsonschema' or fullname.startswith('jsonschema.'):
   raise ModuleNotFoundError('intentionally unavailable documentary-only jsonschema',name=fullname)
sys.meta_path.insert(0,DocumentaryDependencyUnavailable())
sys.argv=['tools/rebuild/source_storage_audit.py','--report','/workspace/van-trading-collection-no-jsonschema-20261028-audit.json','trading/tests','--ignore=trading/tests/test_original_native_collateral.py','--collect-only','-q']
runpy.run_path('tools/rebuild/source_storage_audit.py',run_name='__main__')
