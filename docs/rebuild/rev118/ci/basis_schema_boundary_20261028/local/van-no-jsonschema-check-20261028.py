import importlib.abc,runpy,sys
class DocumentaryDependencyUnavailable(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='jsonschema' or fullname.startswith('jsonschema.'):
   raise ModuleNotFoundError('intentionally unavailable documentary-only jsonschema',name=fullname)
sys.meta_path.insert(0,DocumentaryDependencyUnavailable())
sys.argv=['tools/rebuild/source_storage_audit.py','--report','/workspace/van-no-jsonschema-check-20261028-audit.json','trading/tests/test_physical_baselines.py','trading/tests/test_physical_native_controls.py','trading/tests/test_physical_risk_runtime.py','trading/tests/test_physical_snapshot_producers.py','--junitxml=/workspace/van-no-jsonschema-check-20261028.xml','-q']
runpy.run_path('tools/rebuild/source_storage_audit.py',run_name='__main__')
