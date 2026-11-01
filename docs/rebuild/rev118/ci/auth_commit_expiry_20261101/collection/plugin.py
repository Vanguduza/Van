"""Read-only test collection identity evidence; no test execution."""
import os,json,pathlib,hashlib,platform,sys

def pytest_collection_finish(session):
    raw_ids=[item.nodeid for item in session.items]
    ids=[str(item.path.relative_to(pathlib.Path.cwd()))+'::'+item.nodeid.split('::',1)[1] for item in session.items]
    p=pathlib.Path(os.environ['VAN_COLLECTION_MANIFEST'])
    assert not p.exists()
    data={'rootpath':str(session.config.rootpath),'raw_nodeids':raw_ids,'nodeids':ids,'unique_nodeids':len(set(ids)),'total':len(ids),'python':sys.executable,'python_version':platform.python_version(),'collection_args':list(session.config.invocation_params.args),'environment_selectors':{k:os.environ.get(k) for k in ['PYTHONPATH','DIAL_REPO']},'fixture_selectors_present':{k:bool(os.environ.get(k)) for k in ['VATI_TEST_PG_DSN','VATI_TEST_PG_ISOLATED_FIXTURE']}}
    assert len(ids)==len(set(ids))
    data['nodeids_sha256']=hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
    p.write_text(json.dumps(data,indent=2)+'\n')
