import pathlib,json,subprocess,hashlib,datetime,os
W=pathlib.Path('/workspace');R=W/'van-lanes-20261101/auth-final';out=W/'van-auth-shared-shard-environment-20261101.json';assert not out.exists()
selected=json.load(open(W/'van-auth-corrected-affected-20261101.json'));remainder=json.load(open(W/'van-auth-corrected-remainder-20261101.json'));start=datetime.datetime.fromisoformat(selected['started_at_utc']).timestamp()
selectors={};expectedpython='/workspace/van-backend-venv-20261025/bin/python'
for label,d in [('selected',selected),('remainder',remainder)]:
 assert d['command'][0]==expectedpython and d['cwd']==str(R)
 entries=dict(x.split(b'=',1) for x in (pathlib.Path('/proc')/str(d['command_pid'])/'environ').read_bytes().split(b'\0') if b'=' in x)
 selectors[label]={k:entries.get(k.encode(),b'').decode() for k in ['PYTHONPATH','DIAL_REPO','PYTEST_ADDOPTS','PYTEST_PLUGINS','VATI_TEST_PG_ISOLATED_FIXTURE']}
 selectors[label]['VATI_TEST_PG_DSN_present']=b'VATI_TEST_PG_DSN' in entries
assert selectors['selected']==selectors['remainder'],selectors
freeze=subprocess.check_output([expectedpython,'-m','pip','freeze'],text=True)
launch=json.load(open(W/'van-auth-corrected-remainder-environment-20261101.json'));assert hashlib.sha256(freeze.encode()).hexdigest()==launch['package_freeze_sha256']
lib=W/'van-backend-venv-20261025/lib/python3.12/site-packages';files=[p for p in lib.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'];newer=[str(p.relative_to(lib)) for p in files if max(p.stat().st_mtime,p.stat().st_ctime)>start]
# Existing interpreter/venv shared by both processes; no installer run during either shard.
paths=subprocess.check_output(['git','ls-files'],cwd=R,text=True).splitlines();inputs={};newinputs=[]
for rel in paths:
 p=R/rel
 if p.is_file() and (rel.startswith(('backend/','trading/tests/fixtures/','tests/fixtures/','registries/','schemas/')) or p.name.startswith('conftest') or p.name in ['pytest.ini','pyproject.toml','setup.cfg']):
  inputs[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
  if p.stat().st_mtime>start:newinputs.append(rel)
assert not newer,('package files changed since selected start',newer[:10]);assert not newinputs,('fixture/config files changed since selected start',newinputs)
receipt={'schema':'van.auth-shared-shard-environment/1','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selected_started_at_utc':selected['started_at_utc'],'same_worktree':str(R),'same_python':expectedpython,'same_environment_selectors':selectors,'package_freeze_sha256':hashlib.sha256(freeze.encode()).hexdigest(),'installed_package_file_count':len(files),'package_files_modified_or_metadata_changed_since_selected_start':newer,'source_config_fixture_files':inputs,'source_config_fixture_files_modified_since_selected_start':newinputs,'limitations':'Shared live interpreter/package environment observed during both runs; filesystem timestamps and package metadata are corroboration, not a historical OS write audit. No package install or source/fixture mutation performed by this worker during either run.'}
out.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['source_config_fixture_files','same_environment_selectors']}),flush=True)
