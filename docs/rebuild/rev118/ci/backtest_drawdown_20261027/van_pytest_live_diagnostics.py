"""External source-run evidence only; no collection, assertions or outcomes changed."""
import json,os
from pathlib import Path

def pytest_runtest_logreport(report):
    path=os.environ.get('VAN_TEST_EVENT_LOG')
    if not path:return
    row={'nodeid':report.nodeid,'phase':report.when,'outcome':report.outcome,'duration':report.duration}
    if report.failed:row['original_longrepr']=str(report.longrepr)
    if report.skipped:row['skip_reason']=str(report.longrepr)
    with Path(path).open('a') as stream:
        stream.write(json.dumps(row,sort_keys=True)+'\n');stream.flush()
        if report.failed:os.fsync(stream.fileno())
