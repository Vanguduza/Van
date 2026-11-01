#!/usr/bin/env python3
"""OBL004 canonical inventory/phase collector/join; no native admission authority.

Existing public workers remain their four-worker owner. Other profiles use the
same original fixtures/locks, with explicit file/node ownership and no fallback.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import configparser
import fnmatch
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rebuild import public_source_shards as proof
from tools.rebuild import backend_public_source as public
from tools.rebuild.source_storage_audit import checkout_root

SCHEMA = 'van.canonical-cwd-audit/1'
ROOTS = ('backend/tests', 'tests', 'services', 'hermes/policy/tests', 'trading/tests')
UID_NODE = 'backend/tests/test_browser_egress_proxy_i8.py::test_only_the_configured_client_uid_may_use_a_listener'
FORECAST = {'trading/tests/test_forecast_source_partitions.py', 'trading/tests/test_ml_runtime_boundary.py'}
SPECIAL_NODES = {
    'backend/tests/test_jev_browser_eligibility.py::test_vendored_dds_files_are_the_audited_blobs': ('private_dds', 'DDS checkout not present; blob hashes pinned above'),
    'tests/contracts/test_ci_dds_contract_pin.py::test_recorded_blobs_are_the_pinned_dds_blobs_when_dds_is_present': ('private_dds', 'no DDS git clone beside this checkout; the CI step verifies the same table itself'),
    'tests/contracts/test_android_instrumentation_abi.py::test_actual_agp_direct_package_release_refuses_missing_core_deployment_profile': ('android_guards', 'opt-in actual AGP release guard check'),
    'tests/contracts/test_android_production_target.py::test_actual_agp_valid_target_still_refuses_missing_production_signing': ('android_guards', 'opt-in actual AGP signing guard check'),
}
B1_NA_NODES = frozenset({'backend/tests/test_jev_no_generic_executor.py::test_no_fabric_or_generic_operation_survives_the_b1_validator[click]', 'backend/tests/test_jev_no_generic_executor.py::test_no_fabric_or_generic_operation_survives_the_b1_validator[scroll]', 'backend/tests/test_jev_no_generic_executor.py::test_no_fabric_or_generic_operation_survives_the_b1_validator[select]'})
B1_NA_REASON = 'member of the B1 closed set by definition'
B1_NA_PRODUCERS = {'backend/tests/test_jev_no_generic_executor.py': '1c068cbd999812350fb61139b2523e27ef19df72b1fe8c58dd5a38d98f239081', 'backend/van_gateway/browser/interaction_router.py': '778ebf6ad5dcb1d068f71fb16fa259df506d9864a917c7ee1c1f7a2cb87d53ca', 'backend/van_gateway/computer_use/fabric.py': 'acb3761bdaaaae24a403f535204513180920f4fe39f6c584c6c32deafe39b644'}
BACKEND_LOCK = ('backend/requirements.lock',)
PROFILES = {
    'gateway': {'owner':'backend-public-source-gateway', 'locks':BACKEND_LOCK},
    'media': {'owner':'backend-public-source isolated media', 'locks':('deploy/van-browser-stream/requirements.lock',)},
    'documentary': {'owner':'rebuild-documentary', 'locks':('tools/rebuild/requirements.lock',)},
    'trading_pg': {'owner':'postgres-ledger', 'locks':BACKEND_LOCK, 'pg':True},
    'browser': {'owner':'browser-guard-source full browser', 'locks':BACKEND_LOCK, 'chromium':True},
    'browser_uid': {'owner':'browser-guard-source listener UID', 'locks':BACKEND_LOCK, 'chromium':True, 'root':True},
    'namespace': {'owner':'browser-guard-source namespace firewall', 'locks':BACKEND_LOCK, 'root':True, 'nft':True},
    'private_dds': {'owner':'backend pinned private DDS contract', 'locks':BACKEND_LOCK, 'dds':True},
    'android_guards': {'owner':'android-and-visual-evidence actual AGP refusal controls', 'locks':BACKEND_LOCK, 'agp':True},
    'scenarios': {'owner':'backend lock, existing tests/scenarios ASGI owner fixtures', 'locks':BACKEND_LOCK},
    'forecast': {'owner':'van-forecast-runtime-source', 'locks':('backend/requirements.lock','tools/rebuild/requirements.lock',
          'trading/vati_forecast_worker/locks/research-cp312-linux-x86_64.wheel.lock'), 'pg':True, 'arrow':True},
}
_STATE = None
_JSON_DUMPS = json.dumps

def require(ok, message):
    if not ok: raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path, value):
    Path(path).write_text(_JSON_DUMPS(value, indent=2, sort_keys=True)+'\n')

def load(path):
    return json.loads(Path(path).read_text())

def protected(root):
    return proof.protected_identity(root)

def inventory(root):
    """Enumerate tracked pytest files in every original root; no archive walk."""
    root = Path(root).resolve()
    parser=configparser.ConfigParser();parser.read(root/'pytest.ini')
    roots=tuple(parser['pytest']['testpaths'].split())
    require(roots==ROOTS, 'canonical pytest roots changed; explicit owner review required')
    patterns=parser['pytest'].get('python_files','test_*.py *_test.py').split()
    paths=subprocess.check_output(['git','ls-files','-z','--',*roots],cwd=root).decode().split('\0')
    files=sorted(p for p in paths if p and any(fnmatch.fnmatch(Path(p).name, pattern) for pattern in patterns))
    require(files and all(any(p.startswith(x+'/') for p in files) for x in roots),'missing canonical suite root')
    selection=public.plan(root)
    selected={r['path']:public.runtime(r['path']) for r in selection['selected']}
    separated={r['path']:r['reason'] for r in selection['separate']}
    result=[]
    for path in files:
        owner=None
        if path in FORECAST: owner='forecast'
        elif path.startswith('trading/tests/'): owner='trading_pg'
        elif path.startswith('tests/rebuild/'): owner='documentary'
        elif path=='tests/scenarios/test_acceptance_scenarios.py': owner='scenarios'
        elif path in selected: owner=selected[path]
        elif path in public.PRIVATE: owner='private_dds'
        elif path==public.FIREWALL: owner='namespace'
        elif separated.get(path)=='SEPARATE_COMPLETE_BROWSER_SOURCE_JOB': owner='browser'
        profiles=[owner] if owner else []
        if path==UID_NODE.split('::')[0]: profiles.append('browser_uid')
        profiles.extend(sorted({owner for node,(owner,_) in SPECIAL_NODES.items() if node.split('::')[0]==path}))
        result.append({'path':path,'sha256':sha(root/path),'profiles':profiles,
            'owner':owner,'state':'ASSIGNED' if owner else 'BLOCKED_NO_EXISTING_RUNTIME_OWNER'})
    return {'schema':SCHEMA,'roots':list(roots),'patterns':patterns,'files':result,
        'pytest_ini_sha256':sha(root/'pytest.ini'), 'profiles':{k:{**v,'locks':list(v['locks'])} for k,v in PROFILES.items()},
        'blocked':[r['path'] for r in result if r['owner'] is None],
        'public_selection_sha256':proof.fingerprint(selection)}

def node_owner(node, manifest):
    if node==UID_NODE:return 'browser_uid'
    if node in SPECIAL_NODES:return SPECIAL_NODES[node][0]
    path=node.split('::',1)[0]
    rows=[r for r in manifest['files'] if r['path']==path]
    require(len(rows)==1 and '::' in node,'foreign/noncanonical node')
    return rows[0]['owner']

def selectors(manifest, profile, root):
    require(profile in PROFILES,'unknown runtime profile')
    if profile=='browser_uid':return [str(Path(root)/UID_NODE.split('::')[0])+'::'+UID_NODE.split('::',1)[1]]
    files=[str(Path(root)/r['path']) for r in manifest['files'] if r['owner']==profile]
    return files+[str(Path(root)/node) for node,(owner,_) in SPECIAL_NODES.items() if owner==profile]

def environment(profile, root):
    """Bind the actual fixture owner, versions/locks/plugins; never record DSNs."""
    spec=PROFILES[profile];versions={d.metadata['Name'].lower().replace('_','-'):d.version for d in importlib.metadata.distributions()}
    for lock in spec['locks']:
        require((Path(root)/lock).is_file(),'declared runtime lock missing')
        # The forecast wheel closure contains many unrelated optional packages;
        # only its exact Arrow wheel is required by this existing source profile.
        for name,version in re.findall(r'^([\w.-]+)==([^\s;\\]+)',(Path(root)/lock).read_text(),re.M):
            if lock.endswith('wheel.lock') and name.lower()!='pyarrow':continue
            require(versions.get(name.lower().replace('_','-'))==version,'original runtime lock version mismatch: '+name)
    result={'profile':profile,'owner':spec['owner'],'locks':{p:sha(Path(root)/p) for p in spec['locks']},
        'python':platform.python_version(),'executable_sha256':sha(Path(sys.executable).resolve()),
        'packages':sorted(versions.items()),'plugins':sorted(e.value for e in importlib.metadata.entry_points(group='pytest11')),
        'pythonpath':proof.import_path_identity(Path(root)), 'uid':os.geteuid(),
        'image_os':os.environ.get('ImageOS'),'image_version':os.environ.get('ImageVersion')}
    if spec.get('pg'):
        require(os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')=='1' and os.environ.get('VATI_TEST_PG_DSN'),'isolated PostgreSQL prerequisite unavailable')
        import psycopg
        require(psycopg.__version__=='3.2.9','wrong existing PostgreSQL client')
        with psycopg.connect(os.environ['VATI_TEST_PG_DSN']) as connection:
            result['postgres_version']=connection.info.server_version
        require(result['postgres_version']==170011,'wrong existing PostgreSQL server')
    if spec.get('chromium'):
        chromium=os.environ.get('VAN_TEST_CHROMIUM');require(chromium and Path(chromium).is_file(),'original Chromium prerequisite unavailable')
        result['chromium_sha256']=sha(chromium)
    if spec.get('root'):require(os.geteuid()==0,'original root fixture required')
    if spec.get('nft'):
        nft=subprocess.run(['nft','--version'],capture_output=True,text=True)
        require(nft.returncode==0,'original nftables namespace prerequisite unavailable');result['nft_version']=nft.stdout.strip()
    if spec.get('agp'):
        wrapper=os.environ.get('VAN_ANDROID_GRADLE_BIN')
        require(wrapper and Path(wrapper).resolve()==(Path(root)/'android/gradlew').resolve() and Path(wrapper).is_file(),'original AGP wrapper prerequisite unavailable')
        result['agp_wrapper_sha256']=sha(wrapper)
        java=subprocess.run(['java','-version'],capture_output=True,text=True,timeout=10)
        require(java.returncode==0 and re.search(r'version \"17[.\"]',java.stderr),'original Java17 prerequisite unavailable')
        result['java_version']=java.stderr.strip();result['pyyaml']=versions.get('pyyaml')
        require(result['pyyaml']=='6.0.2','original AGP Python overlay mismatch')
    if spec.get('dds'):
        sibling=Path(root).parent/'dial-development-system'
        require(sibling.is_dir(),'pinned private DDS prerequisite unavailable')
        result['dds_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=sibling,text=True).strip()
        require(result['dds_commit']=='64d6b7158c723b7700e5b53175ea8048d4e92d00','wrong private DDS pin')
    return result

def verify_environment(profile, value, root):
    spec=PROFILES[profile]
    require(value.get('profile')==profile and value.get('owner')==spec['owner'], 'foreign runtime owner')
    require(value.get('locks')=={p:sha(Path(root)/p) for p in spec['locks']}, 'wrong runtime lock inputs')
    require(value.get('python','').startswith('3.12.') and len(value.get('executable_sha256',''))==64
        and value.get('pythonpath')==proof.CANONICAL_PYTHONPATH, 'wrong Python executable/import runtime')
    versions=dict(value.get('packages',[]))
    for lock in spec['locks']:
        for name,version in re.findall(r'^([\w.-]+)==([^\s;\\]+)',(Path(root)/lock).read_text(),re.M):
            if lock.endswith('wheel.lock') and name.lower()!='pyarrow':continue
            require(versions.get(name.lower().replace('_','-'))==version,'locked package mismatch')
    if spec.get('pg'):require(value.get('postgres_version')==170011 and versions.get('psycopg')=='3.2.9','wrong isolated PG profile')
    if spec.get('chromium'):require(len(value.get('chromium_sha256',''))==64,'missing actual Chromium identity')
    if spec.get('root'):require(value.get('uid')==0,'missing original root fixture')
    if spec.get('nft'):require(value.get('nft_version'),'missing actual namespace fixture')
    if spec.get('agp'):
        require(value.get('agp_wrapper_sha256')==sha(Path(root)/'android/gradlew') and re.search(r'version \"17[.\"]',value.get('java_version','')) and value.get('pyyaml')=='6.0.2','missing original AGP runtime')
    if spec.get('dds'):require(value.get('dds_commit')=='64d6b7158c723b7700e5b53175ea8048d4e92d00','missing exact private DDS prerequisite')


def pytest_addoption(parser):
    group=parser.getgroup('van-canonical-cwd-audit')
    group.addoption('--van-canonical-state')

def pytest_configure(config):
    global _STATE
    state_path=config.getoption('--van-canonical-state')
    if not state_path:return
    state=load(state_path);root=Path(state['root'])
    require(Path.cwd().resolve()==public.execution_directory(root,state['cwd']),'wrong actual invocation cwd')
    require(not config.option.keyword and not config.option.markexpr and not config.option.deselect
        and not getattr(config.option,'lf',False) and getattr(config.option,'numprocesses',None) in (None,0),'noncanonical selection/parallelism override')
    require(Path(config.rootpath).resolve()==root and Path(config.inipath).resolve()==root/'pytest.ini','wrong pytest root/config')
    require(Path(config.getoption('confcutdir')).resolve()==root,'wrong conftest cut')
    require(os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD')=='1','ambient pytest plugins not canonical')
    state['pytest_inputs']=proof.effective_pytest_inputs(config,root,'gateway')
    state['pytest_arguments']=list(config.invocation_params.args)
    state['child_environment_before']=environment(state['profile'],root)
    state['child_source_before']=proof.source_identity(root,state['commit'])
    state['protected_before']=protected(root)
    state['collection_errors']=[];state['internal_errors']=[]
    _STATE=state;config._van_canonical_state=state

def pytest_collection_modifyitems(config, items):
    state=getattr(config,'_van_canonical_state',None)
    if state is None:return
    full=sorted(item.nodeid for item in items);require(len(full)==len(set(full)) and full,'empty/duplicate collection')
    expected={r['path'] for r in state['manifest']['files'] if state['profile'] in r['profiles']}
    require({n.split('::')[0] for n in full}==expected,'profile collection lost/added files')
    state['collected']=full;state['assigned']=[n for n in full if node_owner(n,state['manifest'])==state['profile']]
    retained=[];dropped=[]
    for item in items:
        item.user_properties.append(('van_source_nodeid',item.nodeid))
        (retained if item.nodeid in state['assigned'] else dropped).append(item)
    if not state['collect_only']:
        items[:]=retained
        if dropped:config.hook.pytest_deselected(items=dropped)
    dump(Path(state['output'])/'collection.json',state)

def pytest_collectreport(report):
    if _STATE is not None and report.failed:_STATE['collection_errors'].append(str(report.nodeid))

def pytest_internalerror(excrepr,excinfo):
    if _STATE is not None:_STATE['internal_errors'].append(type(excinfo.value).__name__)

def pytest_runtest_logreport(report):
    if _STATE is None:return
    row={'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome,
        'skip_reason':str(report.longrepr[2]) if report.skipped and isinstance(report.longrepr,tuple) else None}
    with (Path(_STATE['output'])/'phases.jsonl').open('a') as stream:stream.write(_JSON_DUMPS(row,sort_keys=True)+'\n')

def pytest_sessionfinish(session,exitstatus):
    if _STATE is None:return
    _STATE['pytest_exit']=int(exitstatus)
    after,candidates=proof._source_observation(_STATE['root'],_STATE['commit'],after_run=True)
    _STATE.update(child_source_after=after,generated_cache_candidates=candidates,
        child_environment_after=environment(_STATE['profile'],Path(_STATE['root'])),
        child_protected_after=protected(Path(_STATE['root'])))
    dump(Path(_STATE['output'])/'terminal.json',_STATE)

def build_pytest_arguments(root, output, profile, manifest, collect_only):
    root,output=Path(root),Path(output)
    arguments=[*selectors(manifest,profile,root),'-c',str(root/'pytest.ini'),
        '--rootdir='+str(root),'--confcutdir='+str(root),'-p','pytest_asyncio.plugin',
        '-p','anyio.pytest_plugin','-p','tools.rebuild.canonical_source_audit',
        '--van-canonical-state='+str(output/'input.json'),'--basetemp='+str(output/'basetemp'),'-q']
    return arguments+(['--collect-only'] if collect_only else ['--junitxml='+str(output/'report.xml')])


def run(args):
    root=ROOT;output=args.output.resolve();require(not output.exists(),'fresh owned evidence directory required')
    require(not output.is_relative_to(root),'canonical audit outputs/basetemps must be outside checkout')
    require(args.profile not in {'gateway','media'},'original public four-worker/media owner must be used')
    output.mkdir(parents=True)
    baseline={'schema':SCHEMA,'profile':args.profile,'cwd':args.cwd,'commit':args.expected_commit,
        'root':str(root),'output':str(output),'execution_id':str(uuid.uuid4()),
        'workflow':{'id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT')},
        'collect_only':args.collect_only,'terminal':False}
    try:
        require(baseline['workflow']['id'] and baseline['workflow']['attempt'],'explicit current workflow identity required')
        require(not any(os.environ.get(k) for k in ('PYTEST_ADDOPTS','PYTEST_PLUGINS','PYTHONHOME','PYTHONUSERBASE','PYTHONSTARTUP','PYTHONINSPECT','PYTHONOPTIMIZE')),'ambient selection/import override')
        baseline['manifest']=inventory(root)
        baseline['source_before']=proof.source_identity(root,args.expected_commit)
        baseline['environment_before']=environment(args.profile,root)
        baseline['protected_before']=protected(root)
        cwd=public.execution_directory(root,args.cwd)
        chosen=selectors(baseline['manifest'],args.profile,root);require(chosen,'profile has no selectors')
        baseline['actual_cwd']=str(cwd)
        state=output/'input.json';dump(state,baseline)
        (output/'phases.jsonl').write_text('')
        command=[sys.executable,'-B','-s',str(root/'tools/rebuild/source_storage_audit.py'),
            '--checkout-root',str(root),'--report',str(output/'storage-audit.json'),
            *build_pytest_arguments(root,output,args.profile,baseline['manifest'],args.collect_only)]
        env={**os.environ,'PYTHONPATH':os.pathsep.join(str(root/p) for p in proof.CANONICAL_PYTHONPATH),
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
        with (output/'pytest.log').open('w') as log:
            child=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:exitcode=child.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL);exitcode=child.wait();baseline['timed_out']=True
        remaining=[line for line in subprocess.check_output(['ps','-eo','pid=,pgid=,stat='],text=True).splitlines() if len(line.split())==3 and line.split()[1]==str(child.pid) and not line.split()[2].startswith('Z')]
        baseline.update(child_pid=child.pid,exit=exitcode,command=command,children_remaining=remaining)
        if remaining:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            raise ValueError('owned child processes survived terminal')
        baseline['generated_cache_outputs']=proof.archive_generated_bytecode(root,args.expected_commit,baseline['source_before'],output)
        child_state=load(output/'terminal.json')
        require(child_state.get('generated_cache_candidates')==baseline['generated_cache_outputs'],'child/parent generated-cache observation differs')
        baseline.update(source_after=proof.source_identity(root,args.expected_commit),
            environment_after=environment(args.profile,root),protected_after=protected(root))
        baseline['state']='TERMINAL' if exitcode==0 else 'FAILED'
    except Exception as exc:
        baseline.update(state='BLOCKED',reason_type=type(exc).__name__,reason=str(exc))
        baseline.setdefault('exit',None)
    baseline['terminal']=True
    baseline['artifacts']={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='receipt.json'}
    dump(output/'receipt.json',baseline)
    return 0 if baseline['state']=='TERMINAL' else 1

def verify_profile(folder,manifest,profile,cwd,commit,root):
    folder=Path(folder);receipt=load(folder/'receipt.json');state=load(folder/'terminal.json')
    require(receipt['workflow'].get('id') and receipt['workflow'].get('attempt'),'missing current workflow identity')
    require(receipt['state']=='TERMINAL' and receipt['terminal'] and receipt['exit']==0 and receipt.get('children_remaining')==[] and state['pytest_exit']==0,'blocked/aborted/failed runtime')
    require(receipt['schema']==state['schema']==SCHEMA and receipt['manifest']==state['manifest']==manifest,'source/profile inventory mismatch')
    require(receipt['profile']==state['profile']==profile and receipt['cwd']==state['cwd']==cwd and receipt['commit']==state['commit']==commit,'foreign profile/cwd/commit')
    require(receipt['actual_cwd']==state['actual_cwd']==str(public.execution_directory(root,cwd)),'wrong actual parent cwd')
    require(isinstance(receipt.get('execution_id'),str) and receipt['execution_id'] and receipt['execution_id']==state['execution_id'] and receipt['workflow']==state['workflow']==
        {'id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT')},'foreign execution/workflow')
    expected=proof.source_identity(root,commit)
    require(receipt['source_before']==receipt['source_after']==state['child_source_before']==state['child_source_after']==expected,'source drift')
    require(receipt['environment_before']==receipt['environment_after']==state['child_environment_before']==state['child_environment_after'],'environment/profile drift')
    verify_environment(profile,receipt['environment_before'],root)
    require(receipt['protected_before']==receipt['protected_after']==state['protected_before']==state['child_protected_after']==protected(root),'protected-directory snapshot drift')
    require(not state['collection_errors'] and not state['internal_errors'],'collection/internal failure')
    require(state['pytest_inputs']['config_sha256']==sha(Path(root)/'pytest.ini') and state['pytest_inputs']['autoload'] is False,'wrong config/plugins')
    mandatory={'input.json','collection.json','terminal.json','phases.jsonl','storage-audit.json','generated-bytecode.json','pytest.log'} | (set() if state['collect_only'] else {'report.xml'})
    require(set(receipt['artifacts'])==mandatory,'missing or foreign runtime artifact')
    for name,digest in receipt['artifacts'].items():require(sha(folder/name)==digest,'artifact content drift')
    proof.verify_generated_bytecode(folder,root,commit,state,receipt)
    audit=load(folder/'storage-audit.json')
    require(audit['root']==str(root) and audit['invocation_cwd']==receipt['actual_cwd'] and audit['forbidden_events']==[]
        and audit['source_sha256']==sha(Path(root)/'tools/rebuild/source_storage_audit.py'),'wrong/violating storage audit')
    full=state['collected'];require(len(full)==len(set(full)) and full,'empty/duplicate full collection')
    expected_files={r['path'] for r in manifest['files'] if profile in r['profiles']}
    require({n.split('::')[0] for n in full}==expected_files,'missing or foreign collected profile file')
    command=receipt['command']
    prefix=['-B','-s',str(Path(root)/'tools/rebuild/source_storage_audit.py'),'--checkout-root',str(root),'--report',str(folder/'storage-audit.json')]
    require(type(state.get('collect_only')) is bool and receipt.get('collect_only')==state['collect_only'],'phase identity differs')
    expected_arguments=build_pytest_arguments(root,folder,profile,manifest,state['collect_only'])
    require(command[1:8]==prefix and command[8:]==state['pytest_arguments']==expected_arguments,'recorded actual pytest invocation differs')
    chosen=selectors(manifest,profile,root)
    require(command[8:8+len(chosen)]==chosen,'absolute original selectors differ')
    require(all(p in state['pytest_inputs']['plugins'] for p in proof.EXPLICIT_PLUGINS['gateway']),'required original plugins missing')
    require(state['assigned']==[n for n in full if node_owner(n,manifest)==profile],'wrong exact assignment')
    phases=[json.loads(line) for line in (folder/'phases.jsonl').read_text().splitlines() if line]
    if state['collect_only']:
        require(not phases and not (folder/'report.xml').exists(),'collection-only executed phases')
        return state,{},[]
    outcomes=defaultdict(dict)
    for row in phases:
        require(row['nodeid'] in state['assigned'] and row['when'] in {'setup','call','teardown'} and row['when'] not in outcomes[row['nodeid']],'foreign/duplicate phase')
        outcomes[row['nodeid']][row['when']]=row['outcome']
    require(set(outcomes)==set(state['assigned']),'missing execution')
    for value in outcomes.values():require(value=={'setup':'passed','call':'passed','teardown':'passed'},'failed/skipped/unexecuted phase blocks full qualification')
    xml=list(ET.parse(folder/'report.xml').getroot().iter('testcase'));nodes=[]
    for case in xml:
        props=[p.get('value') for p in case.findall('./properties/property') if p.get('name')=='van_source_nodeid']
        require(len(props)==1 and not any(case.find(k) is not None for k in ('failure','error','skipped')),'invalid JUnit outcome/node identity')
        nodes+=props
    require(Counter(nodes)==Counter(state['assigned']),'JUnit/phase exact union mismatch')
    return state,dict(outcomes),[]

def public_owned_execution(nodes,runtime,skips,manifest,root):
    """Keep original non-owner skips; require separate actual owner execution."""
    foreign={n for n in nodes if node_owner(n,manifest)!=runtime}
    require(all(n in SPECIAL_NODES and skips.get(n)==SPECIAL_NODES[n][1] for n in foreign),
        'unexpected non-owning public execution/failure or prerequisite skip')
    owned=nodes-foreign;not_applicable=[]
    for node in sorted(owned & skips.keys()):
        require(node in B1_NA_NODES and skips[node]==B1_NA_REASON and
            all(sha(Path(root)/path)==digest for path,digest in B1_NA_PRODUCERS.items()),
            'owning public skip lacks exact pinned applicability predicate')
        not_applicable.append({'id':node,'reason':B1_NA_REASON,'source_sha256':B1_NA_PRODUCERS,
            'predicate':'operation in the pinned InteractionStep.closed_operation_set; this negative rejection probe is inapplicable'})
    return owned-{row['id'] for row in not_applicable},not_applicable

def join(args):
    root=ROOT;manifest=inventory(root);reports={};failures=[];all_collections={cwd:set() for cwd in ('checkout','backend')};executions={cwd:Counter() for cwd in all_collections};not_applicable={cwd:[] for cwd in all_collections}
    if manifest['blocked']:
        failures.extend({'cell':path,'reason':'BLOCKED_NO_EXISTING_RUNTIME_OWNER'} for path in manifest['blocked'])
    for cwd in all_collections:
        public_folder=args.public_root if cwd=='checkout' else args.public_backend
        public_result=args.public_root_result if cwd=='checkout' else args.public_backend_result
        try:
            summary=proof.verify_shards(public_folder,args.expected_commit,public_result,root=root,execution_cwd=cwd)
            for runtime,control in [('gateway','gateway-control'),('media','media-control')]:
                state=load(public_folder/control/'terminal.json');nodes=set(state['full_collection'])
                skips={row['id']:row['reason'] for row in summary['declared_unexecuted']}
                owned,disclosed=public_owned_execution(nodes,runtime,skips,manifest,root)
                not_applicable[cwd].extend(disclosed)
                all_collections[cwd]|=nodes;executions[cwd].update(owned)
            reports[cwd+'/public']={'state':'VERIFIED','tests':summary['tests']}
        except Exception as exc:failures.append({'cell':cwd+'/public','reason_type':type(exc).__name__,'reason':str(exc)})
        for profile in PROFILES:
            if profile in {'gateway','media'}:continue
            key=cwd+'/'+profile;folder=args.reports/f'{profile}-{cwd}'
            try:
                control,_,_=verify_profile(folder/'collect',manifest,profile,cwd,args.expected_commit,root)
                state,outcomes,_=verify_profile(folder/'execute',manifest,profile,cwd,args.expected_commit,root)
                require(control['collect_only'] and not state['collect_only'] and control['collected']==state['collected']
                    and control['assigned']==state['assigned'] and control['pytest_inputs']==state['pytest_inputs']
                    and control['child_environment_before']==state['child_environment_before'],'collection/execution profile mismatch')
                all_collections[cwd].update(state['collected']);executions[cwd].update(outcomes.keys())
                reports[key]={'state':'VERIFIED','tests':len(outcomes)}
            except Exception as exc:failures.append({'cell':key,'reason_type':type(exc).__name__,'reason':str(exc)})
        if Counter(all_collections[cwd])!=executions[cwd]+Counter(row['id'] for row in not_applicable[cwd]):failures.append({'cell':cwd,'reason':'missing/duplicate exact canonical node execution union'})
    if all_collections['checkout']!=all_collections['backend']:failures.append({'cell':'matrix','reason':'canonical node collection differs across cwd'})
    result={'schema':SCHEMA,'commit':args.expected_commit,'state':'FULL_SOURCE_CWD_QUALIFIED' if not failures else 'BLOCKED_INCOMPLETE_QUALIFICATION',
        'manifest':manifest,'verified_profiles':reports,'blocked_cells':failures,
        'node_collections':{k:sorted(v) for k,v in all_collections.items()},
        'not_applicable':not_applicable,'executed_counts':{cwd:sum(rows.values()) for cwd,rows in executions.items()},
        'not_applicable_counts':{cwd:len(rows) for cwd,rows in not_applicable.items()},'certificates_issued':[],
        'limits':'SOURCE only; native/unit/admission gates and historical WAL/SHM disposition remain separate'}
    dump(args.output,result);return 0 if not failures else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('plan','run','join'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--expected-commit',required=True)
    parser.add_argument('--profile',choices=tuple(PROFILES));parser.add_argument('--cwd',choices=('checkout','backend'),default='checkout')
    parser.add_argument('--collect-only',action='store_true');parser.add_argument('--timeout-seconds',type=int,default=1800)
    parser.add_argument('--reports',type=Path);parser.add_argument('--public-root',type=Path);parser.add_argument('--public-backend',type=Path)
    parser.add_argument('--public-root-result',choices=('success','failure','cancelled','skipped'));parser.add_argument('--public-backend-result',choices=('success','failure','cancelled','skipped'))
    args=parser.parse_args();require(1<=args.timeout_seconds<=3600,'invalid child time cap')
    checkout_root(Path.cwd(),ROOT)
    if args.command=='plan':dump(args.output,inventory(ROOT));return 0
    if args.command=='run':require(args.profile is not None,'explicit original runtime profile required');return run(args)
    require(all(getattr(args,k) is not None for k in ('reports','public_root','public_backend','public_root_result','public_backend_result')),'complete matrix inputs required')
    return join(args)

if __name__=='__main__':raise SystemExit(main())
