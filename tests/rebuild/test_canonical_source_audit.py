"""Synthetic instrument/source fixtures; no application or hosted qualification."""
import argparse
import copy
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from tools.rebuild import canonical_source_audit as audit


_SUPERVISION_DRIVER = r'''
import json, os, signal, subprocess, sys
from pathlib import Path
sys.path.insert(0,sys.argv.pop(1))
from tools.rebuild.canonical_source_audit import OwnedProcessSupervisor
mode, log_path = sys.argv[1:]
supervisor = OwnedProcessSupervisor()
if mode == 'unsupported':
    from unittest.mock import patch
    with patch('os.pidfd_open', side_effect=OSError('unsupported')), patch('subprocess.Popen') as spawn:
        try: supervisor.preflight()
        except BaseException as exc:
            print(json.dumps({'result':{'kind':'exception','value':type(exc).__name__},'spawned':spawn.called}))
        else: print(json.dumps({'result':{'kind':'return'},'spawned':spawn.called}))
    sys.exit(0)
supervisor.preflight()
children = {
    'normal': "pass",
    'adopted_terminal': "import os,time\np=os.fork()\nif p==0: os._exit(0)\ntime.sleep(.15)\nos._exit(0)",
    'detached_live': "import os,time\nr,w=os.pipe()\np=os.fork()\nif p==0:\n os.close(r)\n os.setsid()\n q=os.fork()\n if q==0:\n  os.setsid()\n  os.write(w,b'x')\n  time.sleep(30)\n os._exit(0)\nos.close(w)\nassert os.read(r,1)==b'x'\nos._exit(0)",
    'timeout': "import time; time.sleep(30)",
    'interrupt': "import time; time.sleep(30)",
    'controller_fault': "import time; time.sleep(30)",
    'bind_fault': "import time; time.sleep(30)",
    'bind_permanent': "pass", 'early_interrupt': "pass", 'missing_ack': "pass",
}
if mode == 'controller_fault':
    def broken_wait(child, timeout_seconds): raise RuntimeError('controlled owner failure')
    supervisor._wait_leader = broken_wait
if mode == 'bind_fault':
    original_bind=supervisor._bind
    def fail_once(pid):
        if not getattr(fail_once,'attempted',False):
            fail_once.attempted=True
            raise OSError('controlled first ownership bind failure')
        return original_bind(pid)
    supervisor._bind=fail_once
if mode in {'bind_fault','bind_permanent','early_interrupt','missing_ack'}:
    children[mode]="from pathlib import Path; Path("+repr(log_path+'.effect')+").write_text('executed')"
if mode == 'bind_permanent':
    def unavailable(pid):raise OSError('controlled permanent post-spawn pidfd failure')
    supervisor._bind=unavailable
if mode == 'early_interrupt':
    def terminated(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,terminated)
    def before_binding(pid):signal.raise_signal(signal.SIGTERM)
    supervisor._bind=before_binding
if mode == 'missing_ack':supervisor._release_gate=lambda descriptor:0
if mode == 'interrupt':
    def interrupted(signum, frame): raise KeyboardInterrupt()
    signal.signal(signal.SIGALRM, interrupted)
    signal.setitimer(signal.ITIMER_REAL, .35)
result = None
try:
    with Path(log_path).open('wb') as log:
        command=(['git','-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-qm','fixture']
                 if mode=='git' else [sys.executable,'-c',children[mode]])
        code = supervisor.run(command, cwd=os.getcwd(), env=os.environ.copy(), log=log,
                              timeout_seconds=.35 if mode=='timeout' else 5)
    result = {'kind':'return','value':code}
except BaseException as exc:
    result = {'kind':'exception','value':type(exc).__name__}
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
print(json.dumps({'result':result,'evidence':supervisor.evidence,'effect_exists':Path(log_path+'.effect').exists()},sort_keys=True))
'''


def _supervision_process(tmp_path, mode, *, cwd=None, env=None):
    """Separate interpreter keeps process-global subreaper state out of pytest."""
    run=subprocess.run([sys.executable,'-c',_SUPERVISION_DRIVER,str(Path(__file__).resolve().parents[2]),mode,str(tmp_path/(mode+'.log'))],
                       cwd=cwd or Path(__file__).resolve().parents[2],env=env or os.environ.copy(),capture_output=True,text=True,timeout=15)
    assert run.returncode==0,(run.stdout,run.stderr)
    return json.loads(run.stdout)


def _assert_supervision_cleanup(evidence):
    assert evidence['schema']=='van.kernel-owned-child-supervision/1'
    assert evidence['capabilities']=={'pidfd':True,'subreaper':True,'proc_identity':True}
    for key in ('supervisor_identity','leader_identity'):
        assert set(evidence[key])=={'pid','ppid','start_ticks'}
        assert all(type(value) is int and value>=0 for value in evidence[key].values())
    assert evidence['leader_identity']['ppid']==evidence['supervisor_identity']['pid']
    assert evidence['leader_pidfd_bound'] is True and evidence['leader_waited'] is True
    assert evidence['owned_children_absent'] is True and evidence['waitpid_echild'] is True
    assert evidence['remaining_owned']==[] and evidence['cleanup_error'] is None
    for row in evidence['adopted']:
        assert row['pidfd_bound'] is True and row['reaped'] is True and type(row['wait_status']) is int
        assert set(row['identity'])=={'pid','ppid','start_ticks'}


@pytest.mark.parametrize('mode',['normal','adopted_terminal'])
def test_owned_supervisor_reaps_terminal_processes_in_isolated_interpreter(tmp_path,mode):
    result=_supervision_process(tmp_path,mode)
    assert result['result']=={'kind':'return','value':0}
    _assert_supervision_cleanup(result['evidence'])
    assert result['evidence']['unexpected_live_descendants'] is False
    assert result['evidence']['leader_exit']==0 and result['evidence']['leader_forced_cleanup'] is False
    if mode=='adopted_terminal':assert result['evidence']['adopted']


def test_owned_supervisor_reaps_but_blocks_live_detached_descendants(tmp_path):
    result=_supervision_process(tmp_path,'detached_live')
    assert result['result']=={'kind':'exception','value':'ProcessSupervisionBlocked'}
    _assert_supervision_cleanup(result['evidence'])
    assert result['evidence']['unexpected_live_descendants'] is True
    assert len({row['identity']['pid'] for row in result['evidence']['adopted']})>=2


@pytest.mark.parametrize('mode,error',[('timeout','TimeoutExpired'),('interrupt','KeyboardInterrupt'),('controller_fault','RuntimeError')])
def test_owned_supervisor_cleans_before_propagating_timeout_or_interrupt(tmp_path,mode,error):
    result=_supervision_process(tmp_path,mode)
    assert result['result']=={'kind':'exception','value':error}
    _assert_supervision_cleanup(result['evidence'])
    assert result['evidence']['leader_forced_cleanup'] is True


@pytest.mark.parametrize('mode,error',[
    ('bind_fault','OSError'),('bind_permanent','OSError'),
    ('early_interrupt','KeyboardInterrupt'),('missing_ack','ProcessSupervisionBlocked')])
def test_owned_supervisor_never_executes_unbound_or_unacknowledged_command(tmp_path,mode,error):
    result=_supervision_process(tmp_path,mode)
    assert result['result']=={'kind':'exception','value':error}
    assert result['effect_exists'] is False
    evidence=result['evidence']
    assert evidence['capabilities']=={'pidfd':True,'subreaper':True,'proc_identity':True}
    assert evidence['leader_waited'] is True and evidence['leader_exit']==125
    assert evidence['owned_children_absent'] is True and evidence['waitpid_echild'] is True
    assert evidence['remaining_owned']==[] and evidence['cleanup_error'] is None
    assert evidence['launch_gate']['released'] is False and evidence['launch_gate']['closed'] is True
    assert evidence['launch_gate']['aborted_before_exec'] is True
    if mode in {'bind_fault','bind_permanent','early_interrupt'}:
        assert evidence['leader_pidfd_bound'] is False and evidence['leader_identity'] is None
    else:assert evidence['leader_pidfd_bound'] is True


def test_owned_supervisor_leaves_unrelated_peer_alive(tmp_path):
    peer=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
    try:
        result=_supervision_process(tmp_path,'detached_live')
        assert result['result']=={'kind':'exception','value':'ProcessSupervisionBlocked'}
        _assert_supervision_cleanup(result['evidence'])
        assert peer.poll() is None
    finally:
        peer.terminate()
        peer.wait(timeout=5)


def test_owned_supervisor_refuses_unsupported_platform_before_spawn(tmp_path):
    result=_supervision_process(tmp_path,'unsupported')
    assert result=={'result':{'kind':'exception','value':'ProcessSupervisionBlocked'},'spawned':False}


def test_owned_supervisor_keeps_git_hooks_and_existing_injected_configuration(tmp_path,monkeypatch):
    monkeypatch.delenv('PYTHONPATH',raising=False)
    repo=tmp_path/'repo';repo.mkdir()
    subprocess.run(['git','init','-q'],cwd=repo,check=True)
    (repo/'content').write_text('fixture\n')
    subprocess.run(['git','add','content'],cwd=repo,check=True)
    hook=repo/'.git/hooks/pre-commit'
    hook.write_text('#!/bin/sh\ngit config --get gc.autoDetach > ../hook-sentinel\ngit config --get maintenance.autoDetach >> ../hook-sentinel\ngit config --get advice.detachedHead >> ../hook-sentinel\n')
    hook.chmod(0o755)
    env={**os.environ,'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'advice.detachedHead','GIT_CONFIG_VALUE_0':'false',
         'GIT_TRACE2_EVENT':str(tmp_path/'git-trace.json')}
    result=_supervision_process(tmp_path,'git',cwd=repo,env=env)
    assert result['result']=={'kind':'return','value':0}
    _assert_supervision_cleanup(result['evidence'])
    assert (tmp_path/'hook-sentinel').read_text().splitlines()==['false','false','false']
    assert any('maintenance' in line for line in (tmp_path/'git-trace.json').read_text().splitlines())


def test_auditor_receipt_scope_preserves_legacy_as_history_only():
    assert audit.profile_evidence_scope({'schema':'van.canonical-cwd-audit/1'})=='HISTORICAL_GROUP_ONLY'
    assert audit.profile_evidence_scope({'schema':'van.canonical-cwd-audit/2'})=='OWNED_DESCENDANTS_REQUIRED'
    with pytest.raises(ValueError):audit.profile_evidence_scope({'schema':'van.canonical-cwd-audit/unknown'})


_PROBE_DRIVER = r'''
import json, os, subprocess, sys
from tools.rebuild import canonical_source_audit as audit
mode=sys.argv[1]; records=[]; real_run=subprocess.run
source={'capture':"import sys; print('probe-out'); print('probe-err',file=sys.stderr)",
        'inherited':"import sys; print('probe-out'); print('probe-err',file=sys.stderr)",
        'error':"import sys; print('probe-error',file=sys.stderr); sys.exit(7)",
        'timeout':"import time; time.sleep(30)",
        'oversized':"import sys; sys.stdout.buffer.write(b'x'*16384); sys.stdout.flush()"}[mode]
if mode=='oversized':audit.PROBE_OUTPUT_CAP=4096
try:
    with audit.supervised_probes(records,2):
        assert subprocess.run is real_run
        options={'capture_output':True,'text':True,'check':mode=='error'}
        if mode!='inherited':options['timeout']=.2 if mode=='timeout' else 2
        if mode=='oversized':options['env']={**os.environ,'VAN_FIXTURE_PADDING':'x'*5000}
        value=audit.subprocess.run([sys.executable,'-c',source],**options)
    result={'kind':'return','code':value.returncode,'stdout':value.stdout,'stderr':value.stderr}
except BaseException as error:
    result={'kind':'exception','type':type(error).__name__,
            'returncode':getattr(error,'returncode',None),'stderr':getattr(error,'stderr',None)}
print(json.dumps({'result':result,'records':records},sort_keys=True))
'''


@pytest.mark.parametrize('mode',['capture','inherited','error','timeout','oversized'])
def test_supervised_prerequisite_preserves_capture_error_and_timeout(tmp_path,mode):
    import hashlib
    proc=subprocess.run([sys.executable,'-c',_PROBE_DRIVER,mode],cwd=Path(__file__).resolve().parents[2],
                        env=os.environ.copy(),capture_output=True,text=True,timeout=15)
    assert proc.returncode==0,(proc.stdout,proc.stderr)
    value=json.loads(proc.stdout);assert len(value['records'])==1
    record=value['records'][0];assert record['timeout_policy']=='EXPLICIT_OR_EXISTING_PROFILE_BOUND'
    assert record['timeout_seconds']==(.2 if mode=='timeout' else 2)
    _assert_supervision_cleanup(record['process_supervision'])
    assert record['capture_threads_joined'] is True
    assert record['output_limit_exceeded'] is (mode=='oversized')
    if mode=='oversized':
        assert record['process_supervision']['launch_gate']['released'] is True
        assert record['process_supervision']['launch_gate']['exec_environment']['bytes']>4096
    assert record['stdout_bytes']<=(4096 if mode=='oversized' else 8*1024**2)
    if mode in {'capture','inherited'}:
        assert value['result']=={'kind':'return','code':0,'stdout':'probe-out\n','stderr':'probe-err\n'}
        assert record['stdout_sha256']==hashlib.sha256(b'probe-out\n').hexdigest()
        assert record['stderr_sha256']==hashlib.sha256(b'probe-err\n').hexdigest()
    elif mode=='error':
        assert value['result']['type']=='CalledProcessError' and value['result']['returncode']==7
        assert value['result']['stderr']=='probe-error\n'
    elif mode=='timeout':assert value['result']['type']=='TimeoutExpired'
    else:assert value['result']['type']=='ProcessSupervisionBlocked'


def git(root,*args):
    return subprocess.check_output(['git',*args],cwd=root,text=True).strip()


@pytest.fixture
def canonical_fixture(tmp_path):
    root=tmp_path/'canonical-source';root.mkdir()
    actual=Path(__file__).resolve().parents[2]
    for relative in ('tools/rebuild/canonical_source_audit.py','tools/rebuild/backend_public_source.py',
                     'tools/rebuild/public_source_shards.py','tools/rebuild/source_storage_audit.py'):
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(actual/relative,path)
    files=['backend/tests/test_fixture.py','tests/rebuild/test_fixture.py','services/test_fixture.py',
        'hermes/policy/tests/test_fixture.py','trading/tests/test_fixture.py',*audit.public.PRIVATE,audit.public.FIREWALL]
    for relative in files:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('def test_current_cwd(tmp_path):\n    import os\n    from pathlib import Path\n    assert Path.cwd().resolve() in (Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[2]/"backend")\n' if relative.startswith('tests/rebuild/') else 'def test_fixture():\n    assert True\n')
    (root/'pytest.ini').write_text('[pytest]\ntestpaths = '+' '.join(audit.ROOTS)+'\n')
    (root/'.gitignore').write_text('__pycache__/\n.pytest_cache/\n')
    # A pinned synthetic instrument runtime, not the application documentary lock.
    (root/'tools/rebuild/requirements.lock').write_text('pytest=='+importlib.metadata.version('pytest')+'\n')
    git(root,'init','-q');git(root,'add','.')
    git(root,'-c','user.name=Canonical audit source fixture','-c','user.email=source@example.test','commit','-qm','Synthetic full-root collector inputs')
    return root,git(root,'rev-parse','HEAD')


def test_inventory_includes_the_entire_original_five_roots_and_blocks_unowned_files(canonical_fixture):
    root,_=canonical_fixture;manifest=audit.inventory(root)
    assert manifest['roots']==list(audit.ROOTS) and not manifest['blocked']
    assert {row['owner'] for row in manifest['files']} >= {'gateway','media','documentary','trading_pg','namespace','private_dds'}
    extra=root/'tests/test_new_unowned.py';extra.write_text('def test_extra(): assert True\n');git(root,'add',str(extra))
    manifest=audit.inventory(root)
    assert manifest['blocked']==['tests/test_new_unowned.py']
    row=next(row for row in manifest['files'] if row['path']=='tests/test_new_unowned.py')
    assert row['profiles']==[] and row['owner'] is None


@pytest.mark.parametrize('damage',['extra-root','drop-tests-root','wrong-pattern'])
def test_original_pytest_root_and_pattern_controls_are_not_silent_overrides(canonical_fixture,damage):
    root,_=canonical_fixture
    if damage=='wrong-pattern':
        (root/'pytest.ini').write_text('[pytest]\ntestpaths = '+' '.join(audit.ROOTS)+'\npython_files = *_uncollected.py\n')
    else:
        roots=list(audit.ROOTS)
        if damage=='extra-root':roots.append('docs')
        else:roots.remove('tests')
        (root/'pytest.ini').write_text('[pytest]\ntestpaths = '+' '.join(roots)+'\n')
    with pytest.raises(ValueError):audit.inventory(root)


def test_listener_uid_node_has_one_explicit_runtime_owner(canonical_fixture):
    root,_=canonical_fixture;path=root/audit.UID_NODE.split('::')[0]
    path.write_text('def test_only_the_configured_client_uid_may_use_a_listener(): assert True\ndef test_ordinary(): assert True\n');git(root,'add',str(path))
    manifest=audit.inventory(root)
    assert audit.node_owner(audit.UID_NODE,manifest)=='browser_uid'
    assert audit.node_owner(path.relative_to(root).as_posix()+'::test_ordinary',manifest)=='browser'
    with pytest.raises(ValueError,match='foreign'):audit.node_owner('docs/test_archive.py::test_case',manifest)


@pytest.mark.parametrize('cwd',['checkout','backend'])
def test_actual_cli_collection_execution_and_independent_readback_bind_cwd(canonical_fixture,tmp_path,monkeypatch,cwd):
    root,head=canonical_fixture;output=tmp_path/('proof-'+cwd)
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(root/p) for p in audit.proof.CANONICAL_PYTHONPATH),
        'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
        'GITHUB_RUN_ID':'SYNTHETIC-COLLECTOR-RUN','GITHUB_RUN_ATTEMPT':'1'}
    for mode in ('collect','execute'):
        command=[sys.executable,'-B','-s',str(root/'tools/rebuild/canonical_source_audit.py'),'run',
            '--profile','documentary','--cwd',cwd,'--expected-commit',head,'--output',str(output/mode),'--timeout-seconds','30']
        if mode=='collect':command.append('--collect-only')
        result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=40)
        assert result.returncode==0, (result.stdout,result.stderr,(output/mode/'receipt.json').read_text(),(output/mode/'pytest.log').read_text() if (output/mode/'pytest.log').exists() else '')
    for key in ('PYTHONPATH','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):monkeypatch.setenv(key,env[key])
    original_output=output
    output=tmp_path/('downloaded-profile-'+cwd)
    shutil.move(str(original_output),output)
    assert not original_output.exists()
    manifest=audit.inventory(root)
    collected,empty,_=audit.verify_profile(output/'collect',manifest,'documentary',cwd,head,root)
    assert collected['collect_only'] is True and empty=={}
    state,outcomes,_=audit.verify_profile(output/'execute',manifest,'documentary',cwd,head,root)
    assert state['output']==str(original_output/'execute')
    assert state['actual_cwd']==str(root if cwd=='checkout' else root/'backend')
    receipt=audit.load(output/'execute'/'receipt.json')
    _assert_supervision_cleanup(receipt['process_supervision'])
    assert receipt['schema']=='van.canonical-cwd-audit/2'
    assert receipt['supervisor_identity']==receipt['process_supervision']['supervisor_identity']
    assert state['child_process_identity']==receipt['process_supervision']['leader_identity']
    assert state['actual_basetemp']==receipt['basetemp']['path']
    assert 'pytest-' in state['actual_basetemp']
    assert receipt['basetemp_cleanup']['state']=='REMOVED_OWNED_TERMINAL'
    assert not Path(receipt['basetemp']['parent']).exists()
    assert list(outcomes)==['tests/rebuild/test_fixture.py::test_current_cwd']
    assert outcomes['tests/rebuild/test_fixture.py::test_current_cwd']=={'setup':'passed','call':'passed','teardown':'passed'}
    assert state['protected_before']==state['child_protected_after']==audit.protected(root)
    other='backend' if cwd=='checkout' else 'checkout'
    with pytest.raises(ValueError,match='profile/cwd/commit'):audit.verify_profile(output/'execute',manifest,'documentary',other,head,root)


def test_runtime_missing_lock_or_fixture_is_a_refusal_without_fake_profile(canonical_fixture,monkeypatch):
    root,_=canonical_fixture
    with pytest.raises(ValueError,match='lock missing'):audit.environment('private_dds',root)
    with pytest.raises(ValueError,match='unknown runtime'):audit.selectors(audit.inventory(root),'invented',root)


def test_protected_directory_fingerprint_detects_content_entries_and_symlinks(canonical_fixture,tmp_path):
    root,_=canonical_fixture;before=audit.protected(root)
    (root/'backend/data').mkdir();(root/'backend/data/original').write_bytes(b'SOURCE immutable snapshot')
    original=audit.protected(root);assert before!=original
    (root/'backend/data/original').write_bytes(b'altered');assert audit.protected(root)!=original
    (root/'data').symlink_to(tmp_path,target_is_directory=True)
    # A link is recorded as a link, not recursively followed as owned content.
    assert audit.protected(root)['data']['exists']


@pytest.fixture(scope='module')
def actual_phase_receipt(tmp_path_factory):
    # Reuse the same actual synthetic producer once; each rejection mutates and
    # restores only its owned evidence bytes, with no application/native claim.
    temporary=tmp_path_factory.mktemp('actual-canonical-phase-controls')
    root,head=canonical_fixture.__wrapped__(temporary)
    output=temporary/'actual-execute'
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(root/p) for p in audit.proof.CANONICAL_PYTHONPATH),
        'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
        'GITHUB_RUN_ID':'SYNTHETIC-PHASE-RUN','GITHUB_RUN_ATTEMPT':'1'}
    command=[sys.executable,'-B','-s',str(root/'tools/rebuild/canonical_source_audit.py'),'run','--profile','documentary',
        '--cwd','backend','--expected-commit',head,'--output',str(output),'--timeout-seconds','30']
    result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=40)
    assert result.returncode==0,(result.stdout,result.stderr,(output/'receipt.json').read_text())
    return root,head,output,env


@pytest.mark.parametrize('damage',['wrong-cwd','wrong-actual-cwd','source','protected','lock','missing-call',
    'duplicate-phase','foreign-phase','failed-setup','missing-junit','lost-file','storage-cwd','storage-write',
    'collect-only','foreign-artifact','aborted','selector-override','foreign-plugin','wrong-config-cut',
    'temp-execution','temp-actual','temp-cleanup','temp-path',
    'output-state','output-input','output-collection','output-relative','output-dotdot',
    'output-checkout','output-root','wrapper-report','state-path','junit-path',
    'supervision-missing','supervision-echild','supervision-leader','supervision-live','supervision-schema','legacy-receipt',
    'parent-probe-missing','child-probe-missing','parent-probe-owner','child-probe-owner',
    'parent-probe-unjoined','child-probe-overflow','parent-probe-command','child-probe-cwd',
    'parent-probe-drop','child-probe-reorder','parent-probe-timeout','launch-gate-missing','launch-gate-unreleased'])
def test_resealed_actual_phase_receipts_fail_closed(actual_phase_receipt,monkeypatch,damage):
    root,head,out,env=actual_phase_receipt
    for key in ('PYTHONPATH','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):monkeypatch.setenv(key,env[key])
    originals={p:p.read_bytes() for p in out.iterdir() if p.is_file()}
    state=json.loads((out/'terminal.json').read_text());receipt=json.loads((out/'receipt.json').read_text())
    phases=[json.loads(x) for x in (out/'phases.jsonl').read_text().splitlines()]
    try:
        if damage=='wrong-cwd':state['cwd']=receipt['cwd']='checkout'
        elif damage=='supervision-missing':receipt.pop('process_supervision')
        elif damage=='supervision-echild':receipt['process_supervision']['waitpid_echild']=False
        elif damage=='supervision-leader':receipt['process_supervision']['leader_identity']['start_ticks']+=1
        elif damage=='supervision-live':receipt['process_supervision']['unexpected_live_descendants']=True
        elif damage=='supervision-schema':receipt['process_supervision']['schema']='foreign'
        elif damage=='launch-gate-missing':receipt['process_supervision'].pop('launch_gate')
        elif damage=='launch-gate-unreleased':receipt['process_supervision']['launch_gate']['released']=False
        elif damage=='legacy-receipt':receipt['schema']='van.canonical-cwd-audit/1'
        elif damage=='parent-probe-missing':receipt['probe_supervision']=[]
        elif damage=='child-probe-missing':state['probe_supervision']=[]
        elif damage=='parent-probe-owner':receipt['probe_supervision'][0]['process_supervision']['supervisor_identity']['pid']+=1
        elif damage=='child-probe-owner':state['probe_supervision'][0]['process_supervision']['supervisor_identity']['pid']+=1
        elif damage=='parent-probe-unjoined':receipt['probe_supervision'][0]['capture_threads_joined']=False
        elif damage=='child-probe-overflow':state['probe_supervision'][0]['output_limit_exceeded']=True
        elif damage=='parent-probe-command':
            import hashlib
            record=receipt['probe_supervision'][0];record['argv']=['git','status','--porcelain']
            record['command_sha256']=hashlib.sha256(json.dumps(record['argv'],separators=(',',':')).encode()).hexdigest()
        elif damage=='child-probe-cwd':state['probe_supervision'][0]['cwd']=str(root/'backend')
        elif damage=='parent-probe-drop':receipt['probe_supervision'].pop()
        elif damage=='child-probe-reorder':state['probe_supervision'][1:3]=reversed(state['probe_supervision'][1:3])
        elif damage=='parent-probe-timeout':receipt['probe_supervision'][0]['timeout_seconds']+=1
        elif damage=='wrong-actual-cwd':state['actual_cwd']=receipt['actual_cwd']=str(root)
        elif damage=='source':receipt['source_after']={'commit':'foreign'}
        elif damage=='protected':receipt['protected_after']={}
        elif damage=='lock':
            for value in (receipt['environment_before'],receipt['environment_after'],state['child_environment_before'],state['child_environment_after']):value['locks']={}
        elif damage=='missing-call':phases=[p for p in phases if p['when']!='call']
        elif damage=='duplicate-phase':phases.append(phases[0])
        elif damage=='foreign-phase':phases[0]['nodeid']='backend/tests/test_fixture.py::test_fixture'
        elif damage=='failed-setup':phases[0]['outcome']='failed'
        elif damage=='missing-junit':(out/'report.xml').write_text('<testsuite/>')
        elif damage=='lost-file':state['collected']=state['assigned']=[]
        elif damage.startswith('storage'):
            storage=json.loads((out/'storage-audit.json').read_text())
            if damage=='storage-cwd':storage['invocation_cwd']=str(root)
            else:storage['forbidden_events']=[{'event':'open','path':'data/source.sqlite'}]
            audit.dump(out/'storage-audit.json',storage)
        elif damage=='collect-only':state['collect_only']=True
        elif damage=='foreign-artifact':receipt['artifacts']['unexpected.json']='f'*64
        elif damage=='aborted':receipt['terminal']=False
        elif damage=='temp-execution':
            state['basetemp']['execution_id']=receipt['basetemp']['execution_id']='foreign'
        elif damage=='temp-actual':state['actual_basetemp']=str(root/'unowned')
        elif damage=='temp-cleanup':receipt['basetemp_cleanup']['state']='RETAINED_UNVERIFIED_CHILD_TERMINATION'
        elif damage=='temp-path':
            state['basetemp']['path']=receipt['basetemp']['path']=str(root/'basetemp')
        elif damage in {'output-state','output-input','output-collection'}:
            if damage=='output-state':state['output']=str(out.parent/'foreign-output')
            else:
                path=out/('input.json' if damage=='output-input' else 'collection.json')
                value=audit.load(path);value['output']=str(out.parent/'foreign-output');audit.dump(path,value)
        elif damage in {'output-relative','output-dotdot','output-checkout','output-root'}:
            value={'output-relative':'relative-output','output-dotdot':str(out.parent)+'/../foreign',
                'output-checkout':str(root/'evidence'),'output-root':'/'}[damage]
            receipt['output']=state['output']=value
            for name in ('input.json','collection.json'):
                original=audit.load(out/name);original['output']=value;audit.dump(out/name,original)
        elif damage=='wrapper-report':receipt['command'][7]=str(out.parent/'foreign-storage-audit.json')
        elif damage in {'state-path','junit-path'}:
            option='--van-canonical-state=' if damage=='state-path' else '--junitxml='
            arguments=state['pytest_arguments']
            index=next(i for i,arg in enumerate(arguments) if arg.startswith(option))
            arguments[index]=option+str(out.parent/'foreign.json')
            receipt['command']=receipt['command'][:8]+arguments
        elif damage in {'selector-override','foreign-plugin','wrong-config-cut'}:
            arguments=state['pytest_arguments']
            if damage=='selector-override':arguments.extend(['-k','narrow'])
            elif damage=='foreign-plugin':arguments.extend(['-p','unapproved_plugin'])
            else:arguments[arguments.index('--confcutdir='+str(root))]='--confcutdir='+str(root/'tests')
            receipt['command']=receipt['command'][:8]+arguments
        audit.dump(out/'terminal.json',state)
        (out/'phases.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in phases))
        for name in receipt['artifacts']:
            if (out/name).is_file():receipt['artifacts'][name]=audit.sha(out/name)
        audit.dump(out/'receipt.json',receipt)
        with pytest.raises((ValueError,FileNotFoundError)):
            audit.verify_profile(out,audit.inventory(root),'documentary','backend',head,root)
    finally:
        for path,data in originals.items():path.write_bytes(data)
    audit.verify_profile(out,audit.inventory(root),'documentary','backend',head,root)


def test_legacy_profile_remains_historical_and_does_not_qualify(actual_phase_receipt,monkeypatch):
    root,head,out,env=actual_phase_receipt
    for key in ('PYTHONPATH','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):monkeypatch.setenv(key,env[key])
    path=out/'receipt.json';original=path.read_bytes();receipt=json.loads(original)
    try:
        receipt['schema']='van.canonical-cwd-audit/1';audit.dump(path,receipt)
        assert audit.profile_evidence_scope(receipt)=='HISTORICAL_GROUP_ONLY'
        with pytest.raises(ValueError,match='HISTORICAL_GROUP_ONLY'):
            audit.verify_profile(out,audit.inventory(root),'documentary','backend',head,root)
    finally:path.write_bytes(original)


def test_default_public_verifier_refuses_backend_cwd_even_with_resealed_hashes(monkeypatch,tmp_path):
    # The root contract cannot consume a label-only backend artifact.
    folder=tmp_path/'worker';folder.mkdir()
    audit.dump(folder/'terminal.json',{'schema':audit.proof.SCHEMA,'execution_cwd':'backend','invocation_cwd':str(tmp_path/'backend')})
    audit.dump(folder/'run.json',{'execution_cwd':'backend','invocation_cwd':str(tmp_path/'backend')})
    monkeypatch.setattr(audit.public,'execution_directory',lambda root,cwd:Path(root) if cwd=='checkout' else Path(root)/'backend')
    with pytest.raises(ValueError,match='cwd'):
        audit.proof.verify_snapshot(folder,{},'gateway','a'*40,{},tmp_path,collection=True)


def test_workflow_preserves_original_gate_and_adds_distinct_fixture_owned_matrix():
    root=Path(__file__).resolve().parents[2];text=(root/'.github/workflows/van-ci.yml').read_text()
    assert (root/'tools/ci/github-actions-ci.yml').read_text()==text
    def block(name):
        import re
        match=re.search(r'^  '+re.escape(name)+r':\n(.*?)(?=^  [\w-]+:\n|\Z)',text,re.S|re.M)
        assert match,name
        return match.group(1)
    old=block('backend-public-source');assert 'needs.backend-public-source-gateway.result' in old
    assert '--execution-cwd backend' not in old
    added=block('obl004-backend-public-source')
    assert '--execution-cwd backend' in added and 'needs.obl004-backend-gateway.result' in added
    assert 'van-obl004-backend-gateway-*' in added
    for job in ('obl004-documentary','obl004-trading-pg','obl004-browser-namespace','obl004-scenarios','obl004-private-dds','obl004-forecast-source'):
        b=block(job);assert '- checkout\n' in b and '- backend\n' in b
        assert '--expected-commit' in b and '--collect-only' in b and '--cwd' in b
    gate=block('obl004-canonical-matrix');assert 'canonical_source_audit.py join' in gate and 'if: always()' in gate
    assert '--public-root-result' in gate and '--public-backend-result' in gate


@pytest.mark.parametrize('damage',[None,'missing-profile','duplicate-execution','cwd-collection-change','unassigned-file','failed-public'])
def test_matrix_join_exact_union_after_independent_profile_validation(canonical_fixture,tmp_path,monkeypatch,damage):
    """Synthetic already-verified profile seams isolate the matrix join algebra.

    Actual collector/phase/JUnit verification is exercised above; this is not a
    fabricated application/native execution or an alternate qualification path.
    """
    root,head=canonical_fixture
    extra=[audit.UID_NODE.split('::')[0],*audit.FORECAST,'tests/scenarios/test_acceptance_scenarios.py']
    if damage=='unassigned-file':extra.append('tests/test_unknown_owner.py')
    for relative in extra:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('def test_fixture(): assert True\n'+('def test_only_the_configured_client_uid_may_use_a_listener(): assert True\n' if relative==audit.UID_NODE.split('::')[0] else ''));git(root,'add',str(path))
    manifest=audit.inventory(root)
    nodes={}
    for row in manifest['files']:
        if row['owner'] is not None:nodes[row['path']]=row['path']+'::test_fixture'
    all_nodes=[*nodes.values(),audit.UID_NODE]
    public_nodes={profile:[node for node in all_nodes if audit.node_owner(node,manifest)==profile] for profile in ('gateway','media')}
    for cwd in ('checkout','backend'):
        folder=tmp_path/('public-'+cwd)
        for profile,control in [('gateway','gateway-control'),('media','media-control')]:
            (folder/control).mkdir(parents=True)
            audit.dump(folder/control/'terminal.json',{'full_collection':public_nodes[profile]})
    def public_verified(folder,commit,result,*,root,execution_cwd):
        assert commit==head
        if result!='success':raise ValueError('actual public prerequisite failed')
        return {'tests':sum(map(len,public_nodes.values())),'declared_unexecuted':[]}
    def profile_verified(folder,actual_manifest,profile,cwd,commit,source):
        assert actual_manifest==manifest and commit==head and source==root
        if damage=='missing-profile' and profile=='scenarios':raise FileNotFoundError('synthetic missing profile report')
        selected=[node for node in all_nodes if audit.node_owner(node,manifest)==profile]
        if damage=='cwd-collection-change' and profile=='trading_pg' and cwd=='backend':selected=[n+'[backend-only]' for n in selected]
        outcomes={node:{'setup':'passed','call':'passed','teardown':'passed'} for node in selected}
        if damage=='duplicate-execution' and profile=='trading_pg':outcomes[public_nodes['gateway'][0]]={'setup':'passed','call':'passed','teardown':'passed'}
        state={'collect_only':folder.name=='collect','collected':sorted([*selected,audit.UID_NODE]) if profile=='browser' else selected,'assigned':selected,
            'pytest_inputs':{'synthetic':'instrument-only'},'child_environment_before':{'synthetic':'instrument-only'}}
        return state,outcomes,[]
    monkeypatch.setattr(audit,'ROOT',root);monkeypatch.setattr(audit.proof,'verify_shards',public_verified)
    monkeypatch.setattr(audit,'verify_profile',profile_verified)
    args=argparse.Namespace(expected_commit=head,reports=tmp_path/'profiles',public_root=tmp_path/'public-checkout',
        public_backend=tmp_path/'public-backend',public_root_result='failure' if damage=='failed-public' else 'success',
        public_backend_result='success',output=tmp_path/'matrix.json')
    exitcode=audit.join(args);result=json.loads(args.output.read_text())
    assert result['certificates_issued']==[]
    if damage is None:
        assert exitcode==0 and result['state']=='FULL_SOURCE_CWD_QUALIFIED'
        assert result['node_collections']['checkout']==result['node_collections']['backend']==sorted(all_nodes)
    else:assert exitcode==1 and result['state']=='BLOCKED_INCOMPLETE_QUALIFICATION' and result['blocked_cells']


@pytest.mark.parametrize('damage',[None,'arbitrary-extra','original-object','concurrency'])
def test_actual_closed_jobset_guard_allows_only_the_nine_bound_additions(damage):
    """Run the existing guard body with controlled job dictionaries; no YAML dependency added to documentary runtime."""
    import ast
    root=Path(__file__).resolve().parents[2]
    tree=ast.parse((root/'tests/contracts/test_ci_public_source_shards.py').read_text())
    declaration=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OBL004_JOBS' for t in n.targets))
    added=ast.literal_eval(declaration.value)
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='test_every_other_job_trigger_and_concurrency_boundary_is_unchanged')
    before={'on':{'push':{'branches':['source']}},'concurrency':{'group':'original','cancel-in-progress':True},
        'jobs':{'backend':{'original':True},'backend-public-source':{'original':True}}}
    after=copy.deepcopy(before);after['jobs'].update({name:{'additive':True} for name in added|{'backend-public-source-gateway'}})
    if damage=='arbitrary-extra':after['jobs']['unreviewed-new-job']={}
    elif damage=='original-object':after['jobs']['backend']['original']=False
    elif damage=='concurrency':after['concurrency']['group']='changed'
    namespace={'workflows':lambda:(before,after),'OBL004_JOBS':added}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<actual unchanged compatibility guard body>','exec'),namespace)
    if damage is None:namespace[function.name]()
    else:
        with pytest.raises(AssertionError):namespace[function.name]()


def test_actual_source_drift_blocks_and_preserves_original_child_exit(canonical_fixture,tmp_path):
    root,_=canonical_fixture
    source=root/'tests/rebuild/test_fixture.py'
    source.write_text('def test_source_drift():\n    from pathlib import Path\n    path=Path(__file__)\n    path.write_text(path.read_text()+"\\n# SOURCE deliberate tracked drift\\n")\n')
    git(root,'add',str(source));git(root,'-c','user.name=Source drift fixture','-c','user.email=source@example.test','commit','-qm','Controlled adversarial source mutation')
    head=git(root,'rev-parse','HEAD');out=tmp_path/'source-drift-proof'
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(root/p) for p in audit.proof.CANONICAL_PYTHONPATH),
        'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','GITHUB_RUN_ID':'SYNTHETIC-DRIFT','GITHUB_RUN_ATTEMPT':'1'}
    result=subprocess.run([sys.executable,'-B','-s',str(root/'tools/rebuild/canonical_source_audit.py'),'run',
        '--profile','documentary','--cwd','backend','--expected-commit',head,'--output',str(out),'--timeout-seconds','30'],
        cwd=root,env=env,capture_output=True,text=True,timeout=40)
    receipt=json.loads((out/'receipt.json').read_text())
    assert result.returncode==1 and receipt['state']=='BLOCKED'
    assert type(receipt['exit']) is int and receipt['exit']!=0
    assert 'tracked source differs' in (out/'pytest.log').read_text()
    assert '# SOURCE deliberate tracked drift' in source.read_text()


def test_exact_native_prerequisite_nodes_have_real_existing_owner_selectors(canonical_fixture):
    root,_=canonical_fixture
    for node in audit.SPECIAL_NODES:
        path=root/node.split('::')[0];path.parent.mkdir(parents=True,exist_ok=True);path.write_text('def test_fixture(): assert True\n');git(root,'add',str(path))
    manifest=audit.inventory(root)
    for node,(owner,_) in audit.SPECIAL_NODES.items():
        assert audit.node_owner(node,manifest)==owner
        assert str(root/node) in audit.selectors(manifest,owner,root)
        assert owner in next(row for row in manifest['files'] if row['path']==node.split('::')[0])['profiles']
    text=(Path(__file__).resolve().parents[2]/'.github/workflows/van-ci.yml').read_text()
    assert '--profile android_guards' in text and 'java-version: \'17\'' in text

@pytest.mark.parametrize('damage',[None,'wrong-reason','nonowner-executed','unrelated-skip','producer-drift'])
def test_public_nonowning_skips_and_exact_b1_na_are_never_native_passes(tmp_path,damage):
    actual=Path(__file__).resolve().parents[2]
    for relative in audit.B1_NA_PRODUCERS:
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((actual/relative).read_bytes())
    native=next(iter(audit.SPECIAL_NODES));na=next(iter(audit.B1_NA_NODES))
    normal='backend/tests/test_fixture.py::test_fixture'
    nodes={native,na,normal}
    manifest={'files':[{'path':n.split('::')[0],'owner':'gateway'} for n in nodes]}
    skips={native:audit.SPECIAL_NODES[native][1],na:audit.B1_NA_REASON}
    if damage=='wrong-reason':skips[native]='unavailable runtime'
    elif damage=='nonowner-executed':del skips[native]
    elif damage=='unrelated-skip':skips[normal]=audit.B1_NA_REASON
    elif damage=='producer-drift':(tmp_path/next(iter(audit.B1_NA_PRODUCERS))).write_text('# changed producer\n')
    if damage:
        with pytest.raises(ValueError):audit.public_owned_execution(nodes,'gateway',skips,manifest,tmp_path)
    else:
        executed,disclosed=audit.public_owned_execution(nodes,'gateway',skips,manifest,tmp_path)
        assert executed=={normal} and len(disclosed)==1 and disclosed[0]['id']==na
        assert disclosed[0]['source_sha256']==audit.B1_NA_PRODUCERS


def test_added_profile_install_overlays_preserve_their_declared_lock_versions():
    """A setup overlay must not make the owning profile refuse before collection."""
    import re
    import yaml
    root = Path(__file__).resolve().parents[2]
    original = yaml.safe_load(subprocess.check_output([
        'git', 'show', '53c3457c417a8545380ab8c4e538c727c862dfba:.github/workflows/van-ci.yml'
    ], cwd=root))
    current = yaml.safe_load((root/'.github/workflows/van-ci.yml').read_text())
    for identity in sorted(set(current['jobs']) - set(original['jobs'])):
        commands = [step['run'] for step in current['jobs'][identity].get('steps', []) if 'run' in step]
        profiles = {name for command in commands for name in re.findall(r'--profile\s+(\w+)', command)}
        overlays = {name.lower().replace('_', '-'): version
            for command in commands if re.search(r'\bpip\s+install\b', command)
            for name, version in re.findall(r'([\w.-]+)==([^\s\"\';]+)', command)}
        # Public gateway/media and the join keep their separate existing owners;
        # only actual canonical profile commands assert these declared locks.
        for profile in profiles:
            assert profile in audit.PROFILES, (identity, profile)
            for lock in audit.PROFILES[profile]['locks']:
                for name, version in re.findall(r'^([\w.-]+)==([^\s;\\]+)', (root/lock).read_text(), re.M):
                    normalized = name.lower().replace('_', '-')
                    if normalized in overlays:
                        assert overlays[normalized] == version, (identity, profile, name, version, overlays[normalized])


@pytest.fixture
def modeled_backend_locked_agp_runtime(tmp_path, monkeypatch):
    """Production callables on SOURCE modeled metadata/Java; no AGP qualification."""
    import re
    from types import SimpleNamespace
    root = tmp_path/'modeled-backend-locked-agp'
    (root/'backend').mkdir(parents=True)
    actual = Path(__file__).resolve().parents[2]
    (root/'backend/requirements.lock').write_bytes((actual/'backend/requirements.lock').read_bytes())
    (root/'android').mkdir()
    wrapper = root/'android/gradlew'
    wrapper.write_text('SOURCE wrapper identity fixture; never executed\n')
    versions = {name.lower().replace('_', '-'): version for name, version in re.findall(
        r'^([\w.-]+)==([^\s;\\]+)', (root/'backend/requirements.lock').read_text(), re.M)}
    assert versions['pyyaml'] == '6.0.3'
    monkeypatch.setattr(audit.importlib.metadata, 'distributions', lambda: [
        SimpleNamespace(metadata={'Name': name}, version=version) for name, version in versions.items()])
    monkeypatch.setattr(audit.importlib.metadata, 'entry_points', lambda **kwargs: [])
    monkeypatch.setenv('PYTHONPATH', os.pathsep.join(str(root/path) for path in audit.proof.CANONICAL_PYTHONPATH))
    monkeypatch.setenv('VAN_ANDROID_GRADLE_BIN', str(wrapper))
    java = {'returncode': 0, 'stderr': 'openjdk version "17.0.99"\nSOURCE modeled Java17, not executed'}
    def modeled_java(command, **kwargs):
        assert command == ['java', '-version']
        assert kwargs.get('timeout') == 10
        return subprocess.CompletedProcess(command, java['returncode'], stdout='', stderr=java['stderr'])
    monkeypatch.setattr(audit.subprocess, 'run', modeled_java)
    return root, versions, java


def test_additive_agp_producer_and_verifier_accept_the_same_declared_closure(modeled_backend_locked_agp_runtime):
    root, _, _ = modeled_backend_locked_agp_runtime
    value = audit.environment('android_guards', root)
    assert value['pyyaml'] == dict(value['packages'])['pyyaml'] == '6.0.3'
    assert value['agp_wrapper_sha256'] == audit.sha(root/'android/gradlew')
    audit.verify_environment('android_guards', value, root)


@pytest.mark.parametrize('damage', ['version', 'lock', 'java', 'java-exit', 'wrapper'])
def test_additive_agp_producer_refuses_wrong_modeled_installed_closure(modeled_backend_locked_agp_runtime, monkeypatch, damage):
    root, versions, java = modeled_backend_locked_agp_runtime
    if damage == 'version': versions['pyyaml'] = '6.0.2'
    elif damage == 'lock': (root/'backend/requirements.lock').unlink()
    elif damage == 'java': java['stderr'] = 'openjdk version "21.0.9"'
    elif damage == 'java-exit': java['returncode'] = 1
    else: monkeypatch.setenv('VAN_ANDROID_GRADLE_BIN', str(root/'foreign-gradlew'))
    with pytest.raises(ValueError): audit.environment('android_guards', root)


@pytest.mark.parametrize('damage', ['package-version', 'agp-version', 'lock', 'java', 'wrapper', 'wrapper-source'])
def test_additive_agp_verifier_refuses_modeled_receipt_tampering(modeled_backend_locked_agp_runtime, damage):
    root, _, _ = modeled_backend_locked_agp_runtime
    value = audit.environment('android_guards', root)
    if damage == 'package-version': value['packages'] = [(name, '6.0.2' if name == 'pyyaml' else version) for name, version in value['packages']]
    elif damage == 'agp-version': value['pyyaml'] = '6.0.2'
    elif damage == 'lock': value['locks']['backend/requirements.lock'] = '0'*64
    elif damage == 'java': value['java_version'] = 'openjdk version "21.0.9"'
    elif damage == 'wrapper': value['agp_wrapper_sha256'] = '0'*64
    else: (root/'android/gradlew').write_text('SOURCE deliberately changed wrapper')
    with pytest.raises(ValueError): audit.verify_environment('android_guards', value, root)


def test_short_owned_basetemp_supports_real_unix_socket_and_original_key_guard(tmp_path):
    import socket
    root=tmp_path/'checkout';root.mkdir()
    first=audit.create_basetemp(root,'first-execution')
    second=audit.create_basetemp(root,'second-execution')
    try:
        assert first['path']!=second['path']
        base=audit.validate_basetemp(first,root,'first-execution',live=True)
        assert not base.is_relative_to(root)
        # Exact original test-key guard; registry content is an owned fixture.
        key_path=base/'owner-authority0'/'owner_authority_keys.json'
        assert 'pytest-' in str(key_path)
        key_path.parent.mkdir(parents=True);key_path.write_text('{}')
        # Actual failing browser relative path, on the same AF_UNIX boundary.
        path=base/'test_a_bare_lf_smuggled_reques0'/'egress.sock'
        path.parent.mkdir(parents=True)
        assert len(os.fsencode(path))<=107
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:server.bind(str(path))
    finally:
        for value,identity in ((first,'first-execution'),(second,'second-execution')):
            result=audit.cleanup_basetemp(value,root,identity,child_started=True,child_terminal=True,children_remaining=[])
            assert result['state']=='REMOVED_OWNED_TERMINAL' and not Path(value['parent']).exists()


@pytest.mark.parametrize('terminal,remaining',[(False,[]),(True,None),(True,['owned-live-child'])])
def test_unknown_or_live_child_retains_owned_basetemp(tmp_path,terminal,remaining):
    value=audit.create_basetemp(tmp_path,'owned-execution')
    original=(Path(value['parent'])/'owner.json').read_bytes()
    try:
        result=audit.cleanup_basetemp(value,tmp_path,'owned-execution',child_started=True,
            child_terminal=terminal,children_remaining=remaining)
        assert result['state']=='RETAINED_UNVERIFIED_CHILD_TERMINATION'
        assert (Path(value['parent'])/'owner.json').read_bytes()==original
    finally:
        audit.cleanup_basetemp(value,tmp_path,'owned-execution',child_started=True,child_terminal=True,children_remaining=[])


@pytest.mark.parametrize('damage',['execution','root','path','marker','mode'])
def test_owned_basetemp_identity_refuses_foreign_cleanup(tmp_path,damage):
    value=audit.create_basetemp(tmp_path,'original-execution');original=copy.deepcopy(value)
    marker=Path(value['parent'])/'owner.json'
    try:
        if damage=='execution':value['execution_id']='foreign'
        elif damage=='root':value['root']=str(tmp_path/'other')
        elif damage=='path':value['path']=str(tmp_path/'unowned')
        elif damage=='marker':marker.write_text('{}')
        else:Path(value['parent']).chmod(0o755)
        with pytest.raises(ValueError):
            audit.cleanup_basetemp(value,tmp_path,'original-execution',child_started=True,child_terminal=True,children_remaining=[])
        assert Path(original['parent']).exists()
    finally:
        Path(original['parent']).chmod(0o700);audit.dump(marker,original)
        audit.cleanup_basetemp(original,tmp_path,'original-execution',child_started=True,child_terminal=True,children_remaining=[])


@pytest.mark.parametrize('producer_uid',[0,1000])
def test_archived_profile_binds_joined_producer_not_current_reader(actual_phase_receipt,monkeypatch,producer_uid):
    """Actual production readback, modeled producer UID; no root execution claim."""
    root,head,out,env=actual_phase_receipt
    for key in ('PYTHONPATH','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):monkeypatch.setenv(key,env[key])
    originals={p:p.read_bytes() for p in out.iterdir() if p.is_file()}
    state=audit.load(out/'terminal.json');receipt=audit.load(out/'receipt.json')
    try:
        for value in (receipt['environment_before'],receipt['environment_after'],state['child_environment_before'],state['child_environment_after']):value['uid']=producer_uid
        state['basetemp']['uid']=receipt['basetemp']['uid']=producer_uid
        receipt['basetemp_cleanup']['identity_sha256']=audit.hashlib.sha256(audit._JSON_DUMPS(receipt['basetemp'],sort_keys=True).encode()).hexdigest()
        audit.dump(out/'terminal.json',state)
        receipt['artifacts']['terminal.json']=audit.sha(out/'terminal.json');audit.dump(out/'receipt.json',receipt)
        # Read with the actual current process and then the modeled inverse UID.
        audit.verify_profile(out,audit.inventory(root),'documentary','backend',head,root)
        monkeypatch.setattr(audit.os,'getuid',lambda:1000 if producer_uid==0 else 0)
        audit.verify_profile(out,audit.inventory(root),'documentary','backend',head,root)
        receipt['environment_before']['uid']=producer_uid+1
        audit.dump(out/'receipt.json',receipt)
        with pytest.raises(ValueError,match='environment/profile drift'):
            audit.verify_profile(out,audit.inventory(root),'documentary','backend',head,root)
    finally:
        for path,data in originals.items():path.write_bytes(data)


@pytest.mark.parametrize('uid',[None,True,-1,2**32-1,'0',1.5,'mismatched-integer'])
def test_archived_temp_refuses_malformed_or_mismatched_producer_uid(tmp_path,uid):
    if uid=='mismatched-integer':uid=os.getuid()+1
    value=audit.create_basetemp(tmp_path,'execution')
    try:
        with pytest.raises(ValueError,match='producer owner'):
            audit.validate_basetemp(value,tmp_path,'execution',producer_uid=uid)
        altered={**value,'uid':uid}
        with pytest.raises(ValueError):
            audit.validate_basetemp(altered,tmp_path,'execution',producer_uid=os.getuid())
    finally:
        audit.cleanup_basetemp(value,tmp_path,'execution',child_started=False,child_terminal=False,children_remaining=[])


def test_live_foreign_uid_still_refuses_and_root_profile_still_requires_zero(canonical_fixture,monkeypatch):
    root,_=canonical_fixture
    value=audit.create_basetemp(root,'execution')
    try:
        foreign={**value,'uid':0 if os.getuid()!=0 else 1000}
        with pytest.raises(ValueError,match='live basetemp process owner'):
            audit.validate_basetemp(foreign,root,'execution',live=True)
        (root/'backend/requirements.lock').write_text((root/'tools/rebuild/requirements.lock').read_text())
        monkeypatch.setenv('PYTHONPATH',os.pathsep.join(str(root/p) for p in audit.proof.CANONICAL_PYTHONPATH))
        record=audit.environment('documentary',root)
        record.update(profile='browser_uid',owner=audit.PROFILES['browser_uid']['owner'],
            locks={'backend/requirements.lock':audit.sha(root/'backend/requirements.lock')},chromium_sha256='a'*64,uid=0)
        audit.verify_environment('browser_uid',record,root)
        audit.validate_basetemp(foreign if foreign['uid']==0 else value,root,'execution',producer_uid=0)
        record['uid']=1000
        with pytest.raises(ValueError,match='root fixture'):audit.verify_environment('browser_uid',record,root)
    finally:
        audit.cleanup_basetemp(value,root,'execution',child_started=False,child_terminal=False,children_remaining=[])


@pytest.mark.parametrize('filename,function_name,refusal,has_profile',[
    ('test_android_instrumentation_abi.py','test_actual_agp_direct_package_release_refuses_missing_core_deployment_profile',
     'Release deployment target refused: VAN_DEPLOYMENT_PROFILE_FILE is required for van-trading-core releases',False),
    ('test_android_production_target.py','test_actual_agp_valid_target_still_refuses_missing_production_signing',
     'Release signing refused: android/keystore.properties missing.',True),
])
def test_original_agp_invocations_route_only_project_cache_to_owned_external_fixture(tmp_path,filename,function_name,refusal,has_profile):
    """Execute original invocation bodies with a controlled recorder, not actual AGP.

    The immutable before AST proves all original guard assertions, wrapper/cwd,
    task/signing/profile flags, timeout and skip policy survive only the exact
    owned init setup and the project-cache/init-script argument pairs.
    """
    import ast
    from types import SimpleNamespace
    root=Path(__file__).resolve().parents[2];relative='tests/contracts/'+filename
    original=subprocess.check_output(['git','show','ba817c4a6aeaf9a8272d81270f6d0abaf7c18feb:'+relative],cwd=root,text=True)
    old=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name==function_name)
    current=next(n for n in ast.parse((root/relative).read_text()).body if isinstance(n,ast.FunctionDef) and n.name==function_name)
    without_cache=copy.deepcopy(current)
    expected_setup=ast.parse('output_root = tmp_path / "gradle-build-outputs"\ninit_script = tmp_path / "owned-build-dir.init.gradle"\ninit_script.write_text(\n    "gradle.beforeProject { project ->\\n"\n    "    project.layout.buildDirectory.set(new File(new File(new java.net.URI("\n    + json.dumps(output_root.as_uri())\n    + ")), project.rootProject.name + project.path.replace(\':\', \'_\')))\\n}\\n",\n    encoding="utf-8",\n)\n').body
    setup_at=next(i for i,n in enumerate(without_cache.body) if isinstance(n,ast.Assign)
        and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='output_root')
    assert [ast.dump(n,include_attributes=False) for n in without_cache.body[setup_at:setup_at+len(expected_setup)]]==[
        ast.dump(n,include_attributes=False) for n in expected_setup]
    del without_cache.body[setup_at:setup_at+len(expected_setup)]
    invocation=next(n for n in ast.walk(without_cache) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='run' and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess')
    args=invocation.args[0].elts
    for option in ('--project-cache-dir','--init-script'):
        offsets=[i for i,n in enumerate(args) if isinstance(n,ast.Constant) and n.value==option]
        assert len(offsets)==1
        del args[offsets[0]:offsets[0]+2]
    assert ast.dump(without_cache,include_attributes=False)==ast.dump(old,include_attributes=False)
    fixture_root=tmp_path/'controlled-checkout';(fixture_root/'android').mkdir(parents=True)
    wrapper=str(fixture_root/'android/gradlew');calls=[]
    def record(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=1,stdout=refusal,stderr='')
    # Only this extracted test function is executed: no module imports, Java,
    # Gradle, cryptography, signing material or production effect is substituted.
    runnable=copy.deepcopy(current);runnable.decorator_list=[]
    namespace={'ROOT':fixture_root,'os':SimpleNamespace(environ={'VAN_ANDROID_GRADLE_BIN':wrapper}),
        'subprocess':SimpleNamespace(run=record),'pytest':pytest,'json':json}
    exec(compile(ast.Module(body=[runnable],type_ignores=[]),str(root/relative),'exec'),namespace)
    owned=[]
    for index in range(2):
        temporary=tmp_path/('owned-case-'+str(index)+" quoted $ '\"");temporary.mkdir()
        profile=temporary/'deployment-profile.json';profile.write_text('{}')
        kwargs={'tmp_path':temporary}
        if has_profile:kwargs['profile']=lambda:profile
        namespace[function_name](**kwargs)
        command,options=calls[-1]
        assert command[0]==wrapper and options=={'cwd':fixture_root/'android','capture_output':True,'text':True,'timeout':180}
        assert command.count('--init-script')==1
        init=Path(command[command.index('--init-script')+1])
        assert init==temporary/'owned-build-dir.init.gradle' and init.is_file()
        generated=init.read_text()
        output=temporary/'gradle-build-outputs'
        assert 'gradle.beforeProject { project ->' in generated
        assert 'project.layout.buildDirectory.set(new File(new File(new java.net.URI('+json.dumps(output.as_uri())+'))' in generated
        assert "project.rootProject.name + project.path.replace(':', '_')" in generated
        # The real Gradle hook is source-proven by earlier retained compiler
        # output; these label/path controls are not new AGP execution evidence.
        destinations=[output/(name+path.replace(':','_')) for name,path in [('Van',':'),('buildSrc',':'),('Van',':app')]]
        assert len(set(destinations))==3 and all(v.is_relative_to(temporary) and not v.is_relative_to(root) for v in destinations)
        assert command.count('--project-cache-dir')==1
        cache=Path(command[command.index('--project-cache-dir')+1])
        assert cache==temporary/'gradle-project-cache' and cache.parent==temporary
        assert cache.is_absolute() and not cache.is_relative_to(root) and not cache.is_relative_to(fixture_root)
        assert ':app:packageRelease' in command and '--dry-run' in command
        owned.append(cache)
    assert owned[0]!=owned[1] and len(calls)==2


def test_vtil_resolver_alone_uses_private_owner_and_join_assignment(canonical_fixture):
    root,_=canonical_fixture
    node=audit.VTIL_RESOLVER_NODE;path=root/node.split('::')[0]
    path.write_text('def test_registry_files_present_in_dial_vekl_layout(): assert True\ndef test_dial_resolver_selects_trading_knowledge_from_van_registry(): assert True\n')
    git(root,'add',str(path));manifest=audit.inventory(root)
    static=node.split('::')[0]+'::test_registry_files_present_in_dial_vekl_layout'
    assert audit.node_owner(node,manifest)=='private_dds'
    assert audit.node_owner(static,manifest)=='trading_pg'
    assert str(path) in audit.selectors(manifest,'trading_pg',root)
    assert str(root/node) in audit.selectors(manifest,'private_dds',root)
    assert next(row for row in manifest['files'] if row['path']==str(path.relative_to(root)))['profiles']==['trading_pg','private_dds']
    nodes={node,static};owned={profile:{n for n in nodes if audit.node_owner(n,manifest)==profile} for profile in ('trading_pg','private_dds')}
    assert owned=={'trading_pg':{static},'private_dds':{node}} and set.union(*owned.values())==nodes
    assert all(value[0] in {'private_dds','android_guards'} for value in audit.SPECIAL_NODES.values())
    assert len(audit.SPECIAL_NODES)==5
    import ast
    prior=ast.parse(subprocess.check_output(['git','show','ba817c4a6aeaf9a8272d81270f6d0abaf7c18feb:tools/rebuild/canonical_source_audit.py'],text=True,cwd=Path(__file__).resolve().parents[2]))
    original=next(n.value for n in prior.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SPECIAL_NODES' for t in n.targets))
    assert {n:v for n,v in audit.SPECIAL_NODES.items() if n!=node}==ast.literal_eval(original)


@pytest.fixture
def modeled_private_dds_runtime(tmp_path,monkeypatch):
    """Real tiny Git/source fixture, modeled Node+Python closure; no private credential/native qualification."""
    import re
    from types import SimpleNamespace
    root=tmp_path/'van';(root/'backend').mkdir(parents=True)
    actual=Path(__file__).resolve().parents[2]
    (root/'backend/requirements.lock').write_bytes((actual/'backend/requirements.lock').read_bytes())
    versions={name.lower().replace('_','-'):version for name,version in re.findall(r'^([\w.-]+)==([^\s;\\]+)',(root/'backend/requirements.lock').read_text(),re.M)}
    monkeypatch.setattr(audit.importlib.metadata,'distributions',lambda:[SimpleNamespace(metadata={'Name':name},version=version) for name,version in versions.items()])
    monkeypatch.setattr(audit.importlib.metadata,'entry_points',lambda **kwargs:[])
    monkeypatch.setenv('PYTHONPATH',os.pathsep.join(str(root/p) for p in audit.proof.CANONICAL_PYTHONPATH))
    sibling=tmp_path/'dial-development-system';sibling.mkdir()
    sources={}
    for relative in audit.DDS_RESOLVER_SOURCES:
        path=sibling/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('// SOURCE modeled resolver import: '+relative+'\n');sources[relative]=audit.sha(path)
    git(sibling,'init','-q');git(sibling,'add','.')
    git(sibling,'-c','user.name=Source fixture','-c','user.email=fixture@example.test','commit','-qm','SOURCE fixture, no authority')
    monkeypatch.setattr(audit,'DDS_COMMIT',git(sibling,'rev-parse','HEAD'))
    monkeypatch.setattr(audit,'DDS_RESOLVER_SOURCES',sources)
    monkeypatch.setenv('DIAL_REPO',str(sibling))
    for key in audit.DDS_NODE_INPUT_KEYS[:-1]:monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('NODE_DISABLE_COMPILE_CACHE','1')
    node=tmp_path/'modeled-node';node.write_text('SOURCE modeled executable identity, never executed\n')
    monkeypatch.setattr(audit.shutil,'which',lambda name:str(node) if name=='node' else None)
    original_run=audit.subprocess.run;observed={'version':audit.DDS_NODE_VERSION}
    def run(command,**kwargs):
        if command==[str(node),'--version']:
            assert kwargs['timeout']==10
            return subprocess.CompletedProcess(command,0,stdout=observed['version']+'\n',stderr='')
        return original_run(command,**kwargs)
    monkeypatch.setattr(audit.subprocess,'run',run)
    return root,sibling,node,observed


def test_private_dds_producer_and_archived_readback_share_exact_source_runtime(modeled_private_dds_runtime):
    root,sibling,node,_=modeled_private_dds_runtime
    value=audit.environment('private_dds',root)
    assert value['dial_repo']==str(sibling.resolve()) and value['dds_resolver_sources']==audit.DDS_RESOLVER_SOURCES
    assert value['node']=={'version':audit.DDS_NODE_VERSION,'executable':str(node.resolve()),'sha256':audit.sha(node),
        'input_policy':audit.DDS_NODE_INPUT_POLICY,'inputs':{'NODE_OPTIONS':None,'NODE_PATH':None,'NODE_COMPILE_CACHE':None,'NODE_DISABLE_COMPILE_CACHE':'1'}}
    audit.verify_environment('private_dds',value,root)


@pytest.mark.parametrize('damage',['missing-checkout','wrong-pin','missing-config','foreign-config','source-drift','pinned-blob-drift','missing-source','missing-node','wrong-node'])
def test_private_dds_producer_refuses_missing_or_wrong_original_prerequisite(modeled_private_dds_runtime,monkeypatch,damage):
    root,sibling,node,observed=modeled_private_dds_runtime
    if damage=='missing-checkout':sibling.rename(sibling.with_name('absent'))
    elif damage=='wrong-pin':monkeypatch.setattr(audit,'DDS_COMMIT','0'*40)
    elif damage=='missing-config':monkeypatch.delenv('DIAL_REPO')
    elif damage=='foreign-config':monkeypatch.setenv('DIAL_REPO',str(root))
    elif damage=='source-drift':(sibling/next(iter(audit.DDS_RESOLVER_SOURCES))).write_text('// changed\n')
    elif damage=='pinned-blob-drift':monkeypatch.setattr(audit,'DDS_RESOLVER_SOURCES',{p:'0'*64 for p in audit.DDS_RESOLVER_SOURCES})
    elif damage=='missing-source':(sibling/next(iter(audit.DDS_RESOLVER_SOURCES))).unlink()
    elif damage=='missing-node':monkeypatch.setattr(audit.shutil,'which',lambda _:None)
    else:observed['version']='v22.0.0'
    with pytest.raises((ValueError,FileNotFoundError)):audit.environment('private_dds',root)


@pytest.mark.parametrize('damage',['pin','repo','sources','node-version','node-executable','node-hash','missing-node'])
def test_private_dds_readback_refuses_retargeted_or_incomplete_receipt(modeled_private_dds_runtime,damage):
    root,_,_,_=modeled_private_dds_runtime;value=audit.environment('private_dds',root)
    if damage=='pin':value['dds_commit']='0'*40
    elif damage=='repo':value['dial_repo']=str(root)
    elif damage=='sources':value['dds_resolver_sources']={}
    elif damage=='node-version':value['node']['version']='v22.0.0'
    elif damage=='node-executable':value['node']['executable']='node'
    elif damage=='node-hash':value['node']['sha256']='not-a-digest'
    else:del value['node']
    with pytest.raises(ValueError):audit.verify_environment('private_dds',value,root)


def test_vtil_workflow_declares_only_pinned_private_sibling_and_preserves_existing_jobs():
    import subprocess
    root=Path(__file__).resolve().parents[2]
    # No new YAML dependency in the documentary profile: the exact text delta is
    # one job-scoped fact, with the original complete workflow bytes retained.
    current=(root/'.github/workflows/van-ci.yml').read_text()
    original=subprocess.check_output(['git','show','ba817c4a6aeaf9a8272d81270f6d0abaf7c18feb:.github/workflows/van-ci.yml'],cwd=root,text=True)
    addition='      DIAL_REPO: ${{ github.workspace }}/../dial-development-system\n'
    a,b=current.split('  obl004-private-dds:\n',1);block,tail=b.split('  obl004-forecast-source:\n',1)
    disabled="      NODE_DISABLE_COMPILE_CACHE: '1'\n"
    assert block.count(addition)==1 and block.count(disabled)==1
    assert a+'  obl004-private-dds:\n'+block.replace(addition,'').replace(disabled,'')+'  obl004-forecast-source:\n'+tail==original
    assert 'node-version: '+audit.DDS_NODE_VERSION.removeprefix('v') in block
    assert 'ref: '+audit.DDS_COMMIT in block
    assert (root/'tools/ci/github-actions-ci.yml').read_text()==current


@pytest.mark.parametrize('key,value',[
    ('NODE_OPTIONS','--import=data:text/javascript,process.exit(0)'),
    ('NODE_PATH','/unqualified/module/search'),('NODE_COMPILE_CACHE','/unqualified/shared-cache'),
    ('NODE_DISABLE_COMPILE_CACHE',None),('NODE_DISABLE_COMPILE_CACHE','0'),
    ('NODE_DISABLE_COMPILE_CACHE','true'),
])
def test_private_node_inputs_refuse_before_any_node_invocation(modeled_private_dds_runtime,monkeypatch,key,value):
    root,_,node,_=modeled_private_dds_runtime
    if value is None:monkeypatch.delenv(key)
    else:monkeypatch.setenv(key,value)
    original=audit.subprocess.run;node_calls=[]
    def observed(command,**kwargs):
        if command[0]==str(node):node_calls.append(command)
        return original(command,**kwargs)
    monkeypatch.setattr(audit.subprocess,'run',observed)
    with pytest.raises(ValueError,match='unqualified Node'):audit.environment('private_dds',root)
    assert node_calls==[]
    assert os.environ.get(key)==value  # refusal never sanitizes inherited controls


@pytest.mark.parametrize('empty',['',None])
def test_empty_node_overrides_are_recorded_exactly_with_explicit_disabled_cache(modeled_private_dds_runtime,monkeypatch,empty):
    root,_,_,_=modeled_private_dds_runtime
    for key in audit.DDS_NODE_INPUT_KEYS[:-1]:
        if empty is None:monkeypatch.delenv(key,raising=False)
        else:monkeypatch.setenv(key,empty)
    record=audit.environment('private_dds',root)
    assert record['node']['inputs']=={**{k:empty for k in audit.DDS_NODE_INPUT_KEYS[:-1]},'NODE_DISABLE_COMPILE_CACHE':'1'}
    audit.verify_environment('private_dds',record,root)


@pytest.mark.parametrize('damage',['missing-policy','wrong-policy','missing-inputs','nonobject','missing-key','extra-key',
    'options','path','cache','enabled-cache','malformed-empty'])
def test_archived_node_input_policy_refuses_missing_malformed_and_executable_values(modeled_private_dds_runtime,damage):
    root,_,_,_=modeled_private_dds_runtime;record=audit.environment('private_dds',root);node=record['node']
    if damage=='missing-policy':del node['input_policy']
    elif damage=='wrong-policy':node['input_policy']='unqualified/0'
    elif damage=='missing-inputs':del node['inputs']
    elif damage=='nonobject':node['inputs']=[]
    elif damage=='missing-key':del node['inputs']['NODE_OPTIONS']
    elif damage=='extra-key':node['inputs']['unqualified']=''
    elif damage=='options':node['inputs']['NODE_OPTIONS']='--require=/unqualified/preload'
    elif damage=='path':node['inputs']['NODE_PATH']='/unqualified/search'
    elif damage=='cache':node['inputs']['NODE_COMPILE_CACHE']='/unqualified/cache'
    elif damage=='enabled-cache':node['inputs']['NODE_DISABLE_COMPILE_CACHE']='0'
    else:node['inputs']['NODE_OPTIONS']=[]
    with pytest.raises(ValueError):audit.verify_environment('private_dds',record,root)


def test_archived_node_policy_uses_producer_not_aggregate_reader_environment(modeled_private_dds_runtime,monkeypatch):
    root,_,_,_=modeled_private_dds_runtime;record=audit.environment('private_dds',root);original=copy.deepcopy(record)
    monkeypatch.setenv('NODE_OPTIONS','--import=data:text/javascript,process.exit(0)')
    monkeypatch.setenv('NODE_PATH','/reader-only/search');monkeypatch.setenv('NODE_COMPILE_CACHE','/reader-only/cache')
    monkeypatch.setenv('NODE_DISABLE_COMPILE_CACHE','0')
    monkeypatch.setattr(audit.subprocess,'run',lambda *a,**k:pytest.fail('archived readback must not execute reader Node'))
    audit.verify_environment('private_dds',record,root)
    assert record==original and os.environ['NODE_DISABLE_COMPILE_CACHE']=='0'


@pytest.mark.parametrize('command',['plan','join'])
def test_actual_auxiliary_cli_supervises_all_git_probes(canonical_fixture,tmp_path,command):
    root,head=canonical_fixture;output=tmp_path/(command+'.json')
    args=[sys.executable,'-B','-s',str(root/'tools/rebuild/canonical_source_audit.py'),command,
        '--expected-commit',head,'--output',str(output),'--timeout-seconds','10']
    if command=='join':
        args+=['--reports',str(tmp_path/'missing-reports'),'--public-root',str(tmp_path/'missing-public'),
            '--public-backend',str(tmp_path/'missing-backend'),'--public-root-result','failure',
            '--public-backend-result','failure']
    result=subprocess.run(args,cwd=root,env=os.environ.copy(),capture_output=True,text=True,timeout=20)
    assert result.returncode==(0 if command=='plan' else 1),(result.stdout,result.stderr)
    record=audit.load(output.with_name(output.name+'.supervision.json'))
    assert record['state']=='TERMINAL' and record['command']==command
    assert record['process_supervision']['waitpid_echild'] is True
    assert record['process_supervision']['owned_children_absent'] is True
    assert record['probe_supervision']
    audit._verify_probe_supervision(record['probe_supervision'],record['process_supervision']['supervisor_identity'])
    assert record['probe_supervision'][0]['argv']==['git','ls-files','-z','--',*audit.ROOTS]


def test_actual_cli_sigterm_persists_blocked_receipt_after_owned_cleanup(canonical_fixture,tmp_path):
    import signal,time
    root,_=canonical_fixture;marker=tmp_path/'child-entered';output=tmp_path/'terminated-profile'
    fixture=root/'tests/rebuild/test_fixture.py'
    fixture.write_text('def test_blocking_source_fixture():\n    import os,time\n    from pathlib import Path\n    Path(os.environ["VAN_TEST_CHILD_MARKER"]).write_text("entered")\n    time.sleep(30)\n')
    git(root,'add',str(fixture));git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-qm','blocking signal fixture')
    head=git(root,'rev-parse','HEAD')
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(root/p) for p in audit.proof.CANONICAL_PYTHONPATH),
        'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','VAN_TEST_CHILD_MARKER':str(marker),
        'GITHUB_RUN_ID':'SYNTHETIC-SIGTERM','GITHUB_RUN_ATTEMPT':'1'}
    args=[sys.executable,'-B','-s',str(root/'tools/rebuild/canonical_source_audit.py'),'run','--profile','documentary',
        '--cwd','checkout','--expected-commit',head,'--output',str(output),'--timeout-seconds','30']
    child=subprocess.Popen(args,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    descriptor=os.pidfd_open(child.pid,0)
    try:
        deadline=time.monotonic()+12
        while not marker.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
        assert marker.exists(),'actual fixture did not enter'
        signal.pidfd_send_signal(descriptor,signal.SIGTERM)
        stdout,stderr=child.communicate(timeout=10)
        assert child.returncode==128+signal.SIGTERM,(stdout,stderr)
        receipt=audit.load(output/'receipt.json')
        assert receipt['state']=='BLOCKED' and receipt['reason_type']=='SystemExit'
        _assert_supervision_cleanup(receipt['process_supervision'])
        assert receipt['process_supervision']['leader_forced_cleanup'] is True
        assert receipt['process_supervision']['interrupted']=='SystemExit'
    finally:
        if child.poll() is None:signal.pidfd_send_signal(descriptor,signal.SIGKILL)
        child.wait(timeout=5);os.close(descriptor)


@pytest.fixture(scope='module')
def actual_loader_constructor(tmp_path_factory):
    """Compile a source-only loader fixture; never load it in the test parent."""
    temporary=tmp_path_factory.mktemp('loader-constructor')
    compiler=shutil.which('cc')
    assert compiler, 'actual compiler required for the auditor loader-boundary source probe'
    source=temporary/'constructor.c';library=temporary/'constructor.so'
    source.write_text(r'''#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
__attribute__((constructor)) static void before_main(void) {
    const char *marker=getenv("VAN_TEST_LOADER_MARKER");
    if (!marker) return;
    int fd=open(marker,O_WRONLY|O_CREAT|O_EXCL,0600);
    if (fd>=0) {
        const char *bound=getenv("VAN_TEST_BOUND_MARKER");
        const char *value=bound ? (access(bound,F_OK)==0 ? "after-bind" : "before-bind") : "constructor";
        write(fd,value,strlen(value)); close(fd);
    }
    const char *child=getenv("VAN_TEST_LOADER_CHILD");
    if (child && strcmp(child,"1")==0 && fork()==0) { sleep(30); _exit(0); }
}
''')
    built=subprocess.run([compiler,'-shared','-fPIC',str(source),'-o',str(library)],
        capture_output=True,text=True,timeout=15)
    assert built.returncode==0,(built.stdout,built.stderr)
    # A child-only positive control proves the compiled constructor runs. It
    # does not fork, and the parent never inherits LD_PRELOAD.
    marker=temporary/'positive-marker'
    result=subprocess.run(['/bin/true'],env={**os.environ,'LD_PRELOAD':str(library),
        'VAN_TEST_LOADER_MARKER':str(marker),'VAN_TEST_LOADER_CHILD':'0'},capture_output=True,timeout=5)
    assert result.returncode==0 and marker.read_text()=='constructor'
    return library


_LOADER_HANDOFF_DRIVER = r'''
import hashlib,json,os,subprocess,sys
from pathlib import Path
from tools.rebuild.canonical_source_audit import OwnedProcessSupervisor,foreground_git_environment
library,marker,key,location,mode=sys.argv[1:]
owner=OwnedProcessSupervisor();bound=marker+'.bound'
env=os.environ.copy();value=library if key=='LD_PRELOAD' else '' if key=='LD_AUDIT' else 'glibc.malloc.trim_threshold=131072' if key=='GLIBC_TUNABLES' else 'fixture-loader-value'
if location=='inherited':
    os.environ[key]=value;env=os.environ.copy()
else:env[key]=value
env.update(VAN_TEST_LOADER_MARKER=marker,VAN_TEST_LOADER_CHILD='0',VAN_TEST_BOUND_MARKER=bound)
original_bind=owner._bind
def bind(pid):
    assert not Path(marker).exists()
    if mode=='bind_failure':raise OSError('controlled permanent binding failure')
    if mode=='early_interrupt':raise KeyboardInterrupt()
    result=original_bind(pid);Path(bound).write_text('bound');return result
owner._bind=bind
if mode=='missing_ack':owner._release_gate=lambda descriptor:0
expected=foreground_git_environment(env)
def digest(environment):
    return hashlib.sha256(repr(sorted((os.fsencode(k),os.fsencode(v)) for k,v in environment.items())).encode()).hexdigest()
code="import os,hashlib;print(hashlib.sha256(repr(sorted(os.environb.items())).encode()).hexdigest())"
log_path=marker+'.log';before=len(list(Path('/proc/self/fd').iterdir()))
try:
    with open(log_path,'wb') as log:owner.run([sys.executable,'-c',code],cwd=os.getcwd(),env=env,log=log,timeout_seconds=3)
except BaseException as error:result={'type':type(error).__name__}
else:result={'type':'success','environment_exact':Path(log_path).read_text().strip()==digest(expected)}
result.update(effect=Path(marker).read_text() if Path(marker).exists() else None,
    fd_count_restored=len(list(Path('/proc/self/fd').iterdir()))==before,evidence=owner.evidence)
print(json.dumps(result,sort_keys=True))
'''


@pytest.mark.parametrize('key',['LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH','GCONV_PATH','GLIBC_TUNABLES'])
@pytest.mark.parametrize('location',['explicit','inherited'])
def test_loader_environment_is_restored_exactly_only_after_owned_bootstrap(actual_loader_constructor,tmp_path,key,location):
    marker=tmp_path/'constructor-marker'
    result=subprocess.run([sys.executable,'-c',_LOADER_HANDOFF_DRIVER,str(actual_loader_constructor),str(marker),key,location,'success'],
        cwd=Path(__file__).resolve().parents[2],env=os.environ.copy(),capture_output=True,text=True,timeout=15)
    assert result.returncode==0,(result.stdout,result.stderr)
    observed=json.loads(result.stdout)
    assert observed['type']=='success' and observed['environment_exact'] is True
    assert observed['effect']==('after-bind' if key=='LD_PRELOAD' else None)
    assert observed['fd_count_restored'] is True
    _assert_supervision_cleanup(observed['evidence'])
    assert observed['evidence']['launch_gate']['exec_environment']['sealed'] is True
    assert observed['evidence']['launch_gate']['exec_environment']['parent_closed'] is True


@pytest.mark.parametrize('mode',['bind_failure','early_interrupt','missing_ack'])
def test_original_preload_cannot_execute_when_binding_or_ack_fails(actual_loader_constructor,tmp_path,mode):
    marker=tmp_path/'unbound-constructor-marker'
    result=subprocess.run([sys.executable,'-c',_LOADER_HANDOFF_DRIVER,str(actual_loader_constructor),str(marker),'LD_PRELOAD','explicit',mode],
        cwd=Path(__file__).resolve().parents[2],env=os.environ.copy(),capture_output=True,text=True,timeout=15)
    assert result.returncode==0,(result.stdout,result.stderr)
    observed=json.loads(result.stdout)
    assert observed['type'] in {'OSError','KeyboardInterrupt','ProcessSupervisionBlocked'}
    assert observed['effect'] is None and observed['fd_count_restored'] is True
    assert observed['evidence']['leader_waited'] is True and observed['evidence']['leader_exit']==125
    assert observed['evidence']['waitpid_echild'] is True and observed['evidence']['owned_children_absent'] is True
    assert observed['evidence']['launch_gate']['aborted_before_exec'] is True


def test_exec_environment_memfd_is_byte_exact_and_kernel_sealed():
    import fcntl
    values={'EMPTY':'', 'NONASCII':'snowman-\u2603', 'RAW':'\udcff', 'EQUALS':'a=b'}
    fd,evidence=audit._sealed_exec_environment(values)
    try:
        expected=b''.join(os.fsencode(k)+b'='+os.fsencode(v)+b'\0' for k,v in values.items())
        assert os.read(fd,len(expected)+1)==expected
        assert evidence['bytes']==len(expected) and evidence['entries']==len(values)
        assert fcntl.fcntl(fd,1034)==0x000f
        for action in (lambda:os.pwrite(fd,b'x',0),lambda:os.ftruncate(fd,len(expected)+1),lambda:os.ftruncate(fd,len(expected)-1)):
            with pytest.raises(OSError):action()
    finally:os.close(fd)


def test_exec_environment_capacity_refuses_before_fd_creation(monkeypatch):
    created=[]
    monkeypatch.setattr(os,'memfd_create',lambda *a,**k:created.append(True))
    with pytest.raises(audit.ProcessSupervisionBlocked,match='ORIGINAL_EXEC_ENVIRONMENT_CAPACITY'):
        audit._sealed_exec_environment({'TOO_LARGE':'x'*audit.EXEC_ENVIRONMENT_CAP})
    assert created==[]


def test_exec_environment_seal_failure_closes_fd(monkeypatch):
    import fcntl
    descriptors=[];real_create=os.memfd_create;real_fcntl=fcntl.fcntl
    def create(*args,**kwargs):
        descriptor=real_create(*args,**kwargs);descriptors.append(descriptor);return descriptor
    def fail_seal(fd,operation,*args):
        if operation==1033:raise OSError('controlled seal failure')
        return real_fcntl(fd,operation,*args)
    monkeypatch.setattr(os,'memfd_create',create);monkeypatch.setattr(fcntl,'fcntl',fail_seal)
    with pytest.raises(OSError,match='controlled seal failure'):
        audit._sealed_exec_environment({'PRIVATE':'value'})
    assert len(descriptors)==1
    with pytest.raises(OSError):os.fstat(descriptors[0])


def test_actual_bootstrap_uses_active_runtime_not_sysconfig(monkeypatch):
    import ctypes,hashlib,sysconfig
    monkeypatch.setattr(sysconfig,'get_config_var',lambda key:'/fixture/stale/libdir')
    env,evidence=audit._trusted_bootstrap_environment({'PATH':'/usr/bin','LD_PRELOAD':'untrusted','GLIBC_TUNABLES':'untrusted'})
    assert 'LD_PRELOAD' not in env and 'GLIBC_TUNABLES' not in env
    executable=Path('/proc/self/exe').resolve()
    assert evidence['executable']==str(executable)
    assert evidence['executable_sha256']==hashlib.sha256(executable.read_bytes()).hexdigest()
    address=ctypes.cast(ctypes.pythonapi.Py_GetVersion,ctypes.c_void_p).value
    mapping=next(line for line in Path('/proc/self/maps').read_text().splitlines()
        if int(line.split()[0].split('-')[0],16)<=address<int(line.split()[0].split('-')[1],16))
    fields=mapping.split(None,5);assert len(fields)==6
    active=Path(fields[5]).resolve()
    if active==executable:
        assert evidence['library_mode']=='STANDALONE_NO_MAPPED_LIBPYTHON' and evidence['library'] is None
        assert 'LD_LIBRARY_PATH' not in env
    else:
        assert evidence['library_mode']=='ACTIVE_MAPPED_LIBPYTHON'
        assert evidence['library']['path']==str(active)
        assert evidence['library']['sha256']==hashlib.sha256(active.read_bytes()).hexdigest()
        assert env['LD_LIBRARY_PATH']==str(active.parent)


def test_runtime_permission_metadata_is_provenance_with_actual_identity(monkeypatch):
    """Simulated permission metadata; actual runtime files are never chmodded."""
    real_stat=Path.stat;executable=Path('/proc/self/exe').resolve()
    def metadata(path,*args,**kwargs):
        import stat
        value=real_stat(path,*args,**kwargs);fields=list(value)
        fields[0]=stat.S_IFMT(value.st_mode)|(0o777 if path==executable or stat.S_ISDIR(value.st_mode) else 0o666)
        return os.stat_result(fields)
    monkeypatch.setattr(Path,'stat',metadata)
    env,record=audit._trusted_bootstrap_environment({'LD_PRELOAD':'caller-only'})
    assert 'LD_PRELOAD' not in env
    assert record['executable_mode']==0o777
    assert record['executable_device']==real_stat(executable).st_dev
    assert record['executable_inode']==real_stat(executable).st_ino
    if record['library'] is not None:
        assert record['library']['mode']==0o666 and record['library']['directory_mode']==0o777


def test_changed_executable_identity_has_distinct_failure_before_spawn(monkeypatch):
    real_stat=Path.stat
    def replaced(path,*args,**kwargs):
        value=real_stat(path,*args,**kwargs)
        if path==Path('/proc/self/exe'):
            fields=list(value);fields[1]+=1;return os.stat_result(fields)
        return value
    monkeypatch.setattr(Path,'stat',replaced)
    with pytest.raises(audit.ProcessSupervisionBlocked,match='REPLACED_BOOTSTRAP_EXECUTABLE_IDENTITY'):
        audit._trusted_bootstrap_environment({})


@pytest.mark.parametrize('damage,reason',[
    ('deleted','DELETED_BOOTSTRAP_LIBRARY'),
    ('replaced','REPLACED_BOOTSTRAP_LIBRARY_IDENTITY'),
    ('ambiguous','AMBIGUOUS_BOOTSTRAP_LIBRARY'),
    ('api-replaced','REPLACED_BOOTSTRAP_'),
])
def test_simulated_mapping_identity_damage_still_refuses(monkeypatch,tmp_path,damage,reason):
    """Controlled /proc metadata damage, not an actual replaced loaded SDK."""
    import ctypes
    address=ctypes.cast(ctypes.pythonapi.Py_GetVersion,ctypes.c_void_p).value
    real_read=Path.read_text;maps=Path('/proc/self/maps');original=real_read(maps)
    libraries=[]
    for suffix in ('a','b'):
        path=tmp_path/('libpython-identity-'+suffix+'.so.1.0');path.write_bytes(b'metadata-only')
        info=path.stat();libraries.append((path,info))
    def line(path,info,*,inode=None,deleted=False):
        return f'1-2 r-xp 00000000 {os.major(info.st_dev):x}:{os.minor(info.st_dev):x} {info.st_ino if inode is None else inode} {path}'+(' (deleted)' if deleted else '')
    path,info=libraries[0]
    if damage=='deleted':altered=original+'\n'+line(path,info,deleted=True)
    elif damage=='replaced':altered=original+'\n'+line(path,info,inode=info.st_ino+1)
    elif damage=='ambiguous':
        altered='\n'.join(row for row in original.splitlines() if '/libpython' not in row)
        altered+='\n'+'\n'.join(line(p,s) for p,s in libraries)
    else:
        rows=[]
        for row in original.splitlines():
            fields=row.split(None,5)
            if len(fields)==6 and int(fields[0].split('-')[0],16)<=address<int(fields[0].split('-')[1],16):
                fields[4]=str(int(fields[4])+1);row=' '.join(fields)
            rows.append(row)
        altered='\n'.join(rows)
    monkeypatch.setattr(Path,'read_text',lambda path,*a,**k:altered if path==maps else real_read(path,*a,**k))
    with pytest.raises(audit.ProcessSupervisionBlocked,match=reason):
        audit._trusted_bootstrap_environment({})


_EXEC_HANDOFF_FAILURE_DRIVER = r'''
import json,os,subprocess,sys
from unittest.mock import patch
from tools.rebuild import canonical_source_audit as audit
mode,log_path,marker=sys.argv[1:];fds=[];created=os.memfd_create
def create(*args,**kwargs):
    fd=created(*args,**kwargs);fds.append(fd);return fd
owner=audit.OwnedProcessSupervisor()
with open(log_path,'wb') as log, patch('os.memfd_create',side_effect=create), patch('subprocess.Popen',side_effect=OSError('controlled spawn failure')) as spawn:
    try:owner.run([sys.executable,'-c','open('+repr(marker)+',"w").write("executed")'],cwd=os.getcwd(),env=os.environ.copy(),log=log,timeout_seconds=3)
    except BaseException as error:kind=type(error).__name__
    else:kind='unexpected success'
closed=[]
for fd in fds:
    try:os.fstat(fd);closed.append(False)
    except OSError:closed.append(True)
print(json.dumps({'kind':kind,'spawn_count':spawn.call_count,'closed':closed,'effect':os.path.exists(marker),'evidence':owner.evidence}))
'''


def test_spawn_failure_closes_sealed_environment_and_starts_no_child(tmp_path):
    log=tmp_path/'spawn.log';marker=tmp_path/'spawn.effect'
    result=subprocess.run([sys.executable,'-c',_EXEC_HANDOFF_FAILURE_DRIVER,'spawn',str(log),str(marker)],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,(result.stdout,result.stderr)
    value=json.loads(result.stdout)
    assert value['kind']=='OSError' and value['spawn_count']==1 and value['closed']==[True]
    assert value['effect'] is False
    assert value['evidence']['leader_identity'] is None and value['evidence']['waitpid_echild'] is True
    assert value['evidence']['owned_children_absent'] is True


_DYNAMIC_BOOTSTRAP_DRIVER = r'''
import json,os,sys,types
from pathlib import Path
# The source module's hook decorator is registered only when pytest runs;
# this isolated embedded interpreter exercises just the process supervisor.
pytest=types.ModuleType('pytest')
pytest.hookimpl=lambda **kwargs:lambda function:function
sys.modules['pytest']=pytest
from tools.rebuild import canonical_source_audit as audit
private=sys.argv[1];log=Path(sys.argv[2]);expected=os.environ['LD_LIBRARY_PATH']
bootstrap,evidence=audit._trusted_bootstrap_environment(os.environ.copy())
owner=audit.OwnedProcessSupervisor()
with log.open('wb') as output,log.with_suffix('.stderr').open('wb') as diagnostics:
    code=owner.run([sys.executable,'-c','import os;print(os.environ["LD_LIBRARY_PATH"])'],
        cwd=os.getcwd(),env=os.environ.copy(),log=output,stderr=diagnostics,timeout_seconds=5)
print(json.dumps({'evidence':evidence,'bootstrap_path':bootstrap.get('LD_LIBRARY_PATH'),
    'expected':expected,'original_env':log.read_text().strip(),'code':code,'owner':owner.evidence}))
'''


@pytest.mark.parametrize('runtime_mode',[0o755,0o777])
def test_real_dynamic_python_gate_uses_mapped_private_library_and_restores_environment(tmp_path,runtime_mode):
    import ctypes,hashlib
    compiler=shutil.which('cc')
    assert compiler, 'dynamic interpreter fixture requires cc'
    address=ctypes.cast(ctypes.pythonapi.Py_GetVersion,ctypes.c_void_p).value
    mapping=next(line for line in Path('/proc/self/maps').read_text().splitlines()
        if int(line.split()[0].split('-')[0],16)<=address<int(line.split()[0].split('-')[1],16))
    active=Path(mapping.split(None,5)[5]).resolve()
    candidates=[]
    if active.name.startswith('libpython') and '.so' in active.name:candidates.append(active)
    for directory in [Path(sys.base_prefix)/'lib',Path('/usr/lib'),*sorted(Path('/usr/lib').glob('*-linux-gnu'))]:
        candidates.extend(sorted(directory.glob('libpython*.so.1.0')))
    candidates=list(dict.fromkeys(path.resolve() for path in candidates if path.is_file()))
    assert candidates, 'dynamic interpreter fixture requires an installed shared libpython'
    private=tmp_path/'trusted';private.mkdir(mode=0o700)
    source=tmp_path/'embed.c';binary=private/'python-embedded'
    source.write_text('extern int Py_BytesMain(int, char **);\nint main(int argc, char **argv) { return Py_BytesMain(argc, argv); }\n')
    proof='import ctypes,os; a=ctypes.cast(ctypes.pythonapi.Py_GetVersion,ctypes.c_void_p).value; print(next(l.split(None,5)[5].strip() for l in open("/proc/self/maps") if len(l.split(None,5))==6 and int(l.split()[0].split("-")[0],16)<=a<int(l.split()[0].split("-")[1],16)))'
    failures=[];library=None
    for candidate in candidates:
        build=subprocess.run([compiler,str(source),str(candidate),'-o',str(binary)],capture_output=True,text=True,timeout=20)
        if build.returncode:
            failures.append((str(candidate),'link failed'));continue
        probe_env={k:v for k,v in os.environ.items() if not k.startswith('LD_') and k not in {'GCONV_PATH','GLIBC_TUNABLES'}}
        probe_env['LD_LIBRARY_PATH']=str(candidate.parent)
        probe=subprocess.run([str(binary),'-c',proof],env=probe_env,capture_output=True,text=True,timeout=20)
        if probe.returncode==0 and Path(probe.stdout.strip()).resolve()==candidate:
            library=candidate;break
        failures.append((str(candidate),'embedded interpreter or active mapping failed'))
    assert library is not None, f'no usable installed shared Python interpreter: {failures}'
    # Only our tiny ELF and fixture directory change mode, never an SDK file.
    assert binary.stat().st_size<=8*1024*1024
    binary.chmod(runtime_mode);private.chmod(runtime_mode)
    if library.stat().st_size<=8*1024*1024:
        mapped=private/library.name;shutil.copyfile(library,mapped);mapped.chmod(0o666 if runtime_mode==0o777 else 0o644)
        assert hashlib.sha256(mapped.read_bytes()).digest()==hashlib.sha256(library.read_bytes()).digest()
        original_path=str(private)
    else:
        mapped=library
        original_path=str(private)+':'+str(library.parent)
    env={**os.environ,'LD_LIBRARY_PATH':original_path}
    result=subprocess.run([str(binary),'-c',_DYNAMIC_BOOTSTRAP_DRIVER,str(private),str(tmp_path/'original.log')],
        cwd=Path(__file__).resolve().parents[2],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,(result.stdout,result.stderr)
    observed=json.loads(result.stdout);evidence=observed['evidence']
    assert evidence['schema']=='van.active-python-bootstrap/2'
    assert evidence['runtime_trust']=='ALREADY_LOADED_INSTALLED_EXECUTOR'
    assert evidence['executable_mode']==runtime_mode
    assert evidence['executable_inode']==binary.stat().st_ino
    assert evidence['library_mode']=='ACTIVE_MAPPED_LIBPYTHON'
    assert evidence['library']['path']==str(mapped.resolve())
    assert evidence['library']['sha256']==hashlib.sha256(mapped.read_bytes()).hexdigest()
    assert observed['bootstrap_path']==str(mapped.parent)
    assert observed['expected']==observed['original_env']==original_path
    assert observed['code']==0
    _assert_supervision_cleanup(observed['owner'])
