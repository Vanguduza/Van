import os,json,sys
from pathlib import Path
from tools.rebuild.source_storage_audit import StorageAudit
_audit=None
def pytest_sessionstart(session):
 global _audit
 _audit=StorageAudit(Path(os.environ['VAN_MUTATION_SOURCE_ROOT']));sys.addaudithook(_audit)
def pytest_sessionfinish(session,exitstatus):
 Path(os.environ['VAN_MUTATION_STORAGE_REPORT']).write_text(json.dumps({'root':str(_audit.root),'forbidden_events':_audit.violations,'pytest_exit':int(exitstatus)},indent=2)+'\n')
