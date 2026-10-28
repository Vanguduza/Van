"""Retain actual immutable bodies from the exact parent-runtime counterexample."""
import hashlib,json
from pathlib import Path

def pytest_runtest_makereport(item,call):
    if call.when!='call' or call.excinfo is None:return
    for frame in call.excinfo.traceback:
        values=frame.frame.f_locals
        if 'facts' not in values or 'result' not in values:continue
        from vati.risk import authority,pending
        from vati.risk.serde import snapshot_to_dict
        expected=Path('/workspace/van-pending-current-contract-parent-runtime-20261028/trading/vati')
        assert Path(authority.__file__).is_relative_to(expected)
        assert Path(pending.__file__).is_relative_to(expected)
        body=snapshot_to_dict(values['facts']);result=values['result'].to_dict()
        assert result['decision']=='APPROVED'
        assert all('valuation_contract' not in p for p in body['pending_risk_commitments'])
        record={'nodeid':item.nodeid,'source_commit':'eac4761f34c2c966ccc57578d7a8865695b40cf7',
            'snapshot':body,'decision':result,'source_module_hashes':{
                str(Path(m.__file__).relative_to(expected)):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
                for m in (authority,pending)}}
        with Path('/workspace/van-pending-current-contract-parent-bodies-20261028.jsonl').open('a') as f:
            f.write(json.dumps(record)+'\n')
        break
