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
    'output-checkout','output-root','wrapper-report','state-path','junit-path'])
def test_resealed_actual_phase_receipts_fail_closed(actual_phase_receipt,monkeypatch,damage):
    root,head,out,env=actual_phase_receipt
    for key in ('PYTHONPATH','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):monkeypatch.setenv(key,env[key])
    originals={p:p.read_bytes() for p in out.iterdir() if p.is_file()}
    state=json.loads((out/'terminal.json').read_text());receipt=json.loads((out/'receipt.json').read_text())
    phases=[json.loads(x) for x in (out/'phases.jsonl').read_text().splitlines()]
    try:
        if damage=='wrong-cwd':state['cwd']=receipt['cwd']='checkout'
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
