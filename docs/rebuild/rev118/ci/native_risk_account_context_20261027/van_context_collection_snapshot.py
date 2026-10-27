import json,os
from pathlib import Path
def pytest_collection_finish(session):
    path=os.environ.get('VAN_COLLECTION_SNAPSHOT')
    if path:
        Path(path).write_text(json.dumps({'nodeids':[item.nodeid for item in session.items], 'tests_executed':False},indent=2)+'\n')
