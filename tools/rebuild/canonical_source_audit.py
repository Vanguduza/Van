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
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import select
import signal
import shutil
import stat
import tempfile
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rebuild import public_source_shards as proof
from tools.rebuild import backend_public_source as public
from tools.rebuild.source_storage_audit import checkout_root

LEGACY_SCHEMA = 'van.canonical-cwd-audit/1'
SCHEMA = 'van.canonical-cwd-audit/2'
PROBE_OUTPUT_CAP = 8 * 1024**2
EXEC_ENVIRONMENT_CAP = 8 * 1024**2
LAUNCH_GATE_SECONDS = 5
LAUNCH_ENVIRONMENT_POLICY = 'van.trusted-bootstrap-private-exec-environment/2'
# Linux UAPI values: some supported Python builds omit the fcntl names.
# Support is established by actual add/get-seal syscalls, never by these names.
LINUX_F_ADD_SEALS=1033
LINUX_F_GET_SEALS=1034
LINUX_ENVIRONMENT_SEALS=0x0001|0x0002|0x0004|0x0008
# Isolated Python starts this trusted gate, then execs the original argv in the
# same PID only after the parent has bound pidfd + PID/start/PPID. Neither the
# original program nor its startup hooks can run while ownership is unbound.
LAUNCH_GATE = '''import os,select,sys
descriptor=int(sys.argv[1])
environment_descriptor=int(sys.argv[2])
environment_size=int(sys.argv[3])
ready,_,_=select.select([descriptor],[],[],5)
allowed=os.read(descriptor,1) if ready else b''
os.close(descriptor)
if allowed!=b'X':
    os.close(environment_descriptor)
    os._exit(125)
try:
    chunks=[];remaining=environment_size
    while remaining:
        chunk=os.read(environment_descriptor,min(65536,remaining))
        if not chunk:raise ValueError()
        chunks.append(chunk);remaining-=len(chunk)
    if os.read(environment_descriptor,1):raise ValueError()
    os.close(environment_descriptor);environment_descriptor=None
    payload=b''.join(chunks)
    if payload and not payload.endswith(b'\\0'):raise ValueError()
    environment={}
    for entry in payload[:-1].split(b'\\0') if payload else []:
        key,separator,value=entry.partition(b'=')
        if not separator or key in environment:raise ValueError()
        environment[key]=value
    os.execvpe(sys.argv[4],sys.argv[4:],environment)
except BaseException:
    if environment_descriptor is not None:os.close(environment_descriptor)
    os._exit(126)
'''
ROOTS = ('backend/tests', 'tests', 'services', 'hermes/policy/tests', 'trading/tests')
UID_NODE = 'backend/tests/test_browser_egress_proxy_i8.py::test_only_the_configured_client_uid_may_use_a_listener'
FORECAST = {'trading/tests/test_forecast_source_partitions.py', 'trading/tests/test_ml_runtime_boundary.py'}
VTIL_RESOLVER_NODE = 'trading/tests/test_vtil_borrow.py::test_dial_resolver_selects_trading_knowledge_from_van_registry'
DDS_COMMIT = '64d6b7158c723b7700e5b53175ea8048d4e92d00'
DDS_NODE_VERSION = 'v24.19.0'
DDS_NODE_INPUT_POLICY = 'van.vtil-node-inputs/1'
DDS_NODE_INPUT_KEYS = ('NODE_OPTIONS','NODE_PATH','NODE_COMPILE_CACHE','NODE_DISABLE_COMPILE_CACHE')
DDS_RESOLVER_SOURCES = {'agent-system/orchestration/engineering-resource-resolver.mjs': '6d20c98daf2f3390de99bb6200b4eacf2a8493b7e85992cf80cde7f4a103e36e', 'agent-system/orchestration/engineering-resource-registry.mjs': 'fd89fe548a1e072edb85ce260a7495224304eed1cf592280b7488e3a8b8a5d72', 'agent-system/orchestration/skill-resolver.mjs': '020f0270249d0b8197c9c22817c00743f2aaf2b8af45944c975bee5904b4fdce', 'agent-system/orchestration/skill-registry.mjs': '0608f6944bac4257318e9060633fd3a4fb2f87199232668520b59129bd5a8da0', 'agent-system/orchestration/state-store.mjs': '73f972e1749c30905d0c9c707ada5055bda3bd0ec960bf341df60f88d0741f18'}
SPECIAL_NODES = {
    VTIL_RESOLVER_NODE: ('private_dds', 'dial-new checkout not available (set DIAL_REPO)'),
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
    # This additive audit runtime uses BACKEND_LOCK, including PyYAML6.0.3.
    # The unchanged original Android owner's separate6.0.2 overlay stays intact.
    'android_guards': {'owner':'android-and-visual-evidence actual AGP refusal controls', 'locks':BACKEND_LOCK, 'agp':True, 'pyyaml':'6.0.3'},
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

def validate_basetemp(value, root, execution_id, *, live=False, producer_uid=None):
    """Bind a short owned parent; pytest may recreate only its child directory."""
    parent=Path(value['parent']);path=Path(value['path'])
    require(parent.parent==Path('/tmp') and re.fullmatch(r'pytest-vca-[a-z0-9_]{8}',parent.name)
        and path==parent/'b' and not path.is_relative_to(Path(root).resolve())
        and len(os.fsencode(path))<=32,'invalid owned short pytest basetemp')
    require(value['execution_id']==execution_id and value['root']==str(Path(root).resolve())
        and type(value['uid']) is int and 0<=value['uid']<2**32-1
        and type(value['device']) is int and value['device']>=0
        and type(value['inode']) is int and value['inode']>0,'foreign basetemp execution/owner')
    if live:
        require(value['uid']==os.getuid(),'foreign live basetemp process owner')
    else:
        require(type(producer_uid) is int and 0<=producer_uid<2**32-1
            and value['uid']==producer_uid,'basetemp differs from original producer owner')
    if live:
        info=parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o700
            and info.st_uid==value['uid'] and info.st_dev==value['device'] and info.st_ino==value['inode'],
            'owned basetemp parent changed')
        marker=parent/'owner.json'
        require(not marker.is_symlink() and load(marker)==value,'owned basetemp marker changed')
    return path


def create_basetemp(root, execution_id):
    parent=Path(tempfile.mkdtemp(prefix='pytest-vca-',dir='/tmp'))
    info=parent.stat()
    value={'parent':str(parent),'path':str(parent/'b'),'execution_id':execution_id,
        'root':str(Path(root).resolve()),'uid':info.st_uid,'device':info.st_dev,'inode':info.st_ino}
    dump(parent/'owner.json',value)
    validate_basetemp(value,root,execution_id,live=True)
    return value


def cleanup_basetemp(value, root, execution_id, *, child_started, child_terminal, children_remaining):
    result={'path':value['path'],'execution_id':execution_id,
        'identity_sha256':hashlib.sha256(_JSON_DUMPS(value,sort_keys=True).encode()).hexdigest()}
    if (child_started and not child_terminal) or children_remaining!=[]:
        return {**result,'state':'RETAINED_UNVERIFIED_CHILD_TERMINATION'}
    validate_basetemp(value,root,execution_id,live=True)
    shutil.rmtree(value['parent'])
    return {**result,'state':'REMOVED_OWNED_TERMINAL'}


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

def qualified_node_inputs(value):
    # This policy covers only the exact ESM resolver fixture's executable
    # overrides/search/compile-cache inputs. Refuse, never sanitize, incoming
    # values. Archived callers supply the producer record, not their own env.
    require(isinstance(value,dict) and set(value)==set(DDS_NODE_INPUT_KEYS),'missing or malformed original Node inputs')
    require(all(value[k] is None or value[k]=='' for k in DDS_NODE_INPUT_KEYS[:-1])
        and value['NODE_DISABLE_COMPILE_CACHE']=='1','unqualified Node executable/search/cache inputs')
    return dict(value)


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
        require(result['pyyaml']==spec['pyyaml'],'additive backend-locked AGP Python overlay mismatch')
    if spec.get('dds'):
        node_inputs=qualified_node_inputs({k:os.environ.get(k) for k in DDS_NODE_INPUT_KEYS})
        sibling=Path(root).parent/'dial-development-system'
        require(sibling.is_dir(),'pinned private DDS prerequisite unavailable')
        result['dds_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=sibling,text=True).strip()
        require(result['dds_commit']==DDS_COMMIT,'wrong private DDS pin')
        configured=os.environ.get('DIAL_REPO')
        require(configured and Path(configured).resolve()==sibling.resolve(),'explicit pinned sibling DIAL_REPO prerequisite unavailable')
        result['dial_repo']=str(sibling.resolve())
        result['dds_resolver_sources']={}
        for path,expected in DDS_RESOLVER_SOURCES.items():
            pinned=subprocess.check_output(['git','show',DDS_COMMIT+':'+path],cwd=sibling)
            require(hashlib.sha256(pinned).hexdigest()==expected,'pinned DDS resolver blob identity mismatch')
            result['dds_resolver_sources'][path]=sha(sibling/path)
        require(result['dds_resolver_sources']==DDS_RESOLVER_SOURCES,'private DDS resolver source drift')
        node=shutil.which('node');require(node,'private DDS Node prerequisite unavailable')
        observed=subprocess.run([node,'--version'],capture_output=True,text=True,timeout=10)
        require(observed.returncode==0 and observed.stdout.strip()==DDS_NODE_VERSION,'wrong private DDS Node runtime')
        result['node']={'version':observed.stdout.strip(),'executable':str(Path(node).resolve()),'sha256':sha(Path(node).resolve()),
            'input_policy':DDS_NODE_INPUT_POLICY,'inputs':node_inputs}
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
        require(value.get('agp_wrapper_sha256')==sha(Path(root)/'android/gradlew') and re.search(r'version \"17[.\"]',value.get('java_version','')) and value.get('pyyaml')==spec['pyyaml'],'missing additive backend-locked AGP runtime')
    if spec.get('dds'):
        require(value.get('dds_commit')==DDS_COMMIT,'missing exact private DDS prerequisite')
        require(value.get('dial_repo')==str((Path(root).parent/'dial-development-system').resolve())
            and value.get('dds_resolver_sources')==DDS_RESOLVER_SOURCES,'missing original pinned resolver source binding')
        node=value.get('node',{})
        require(isinstance(node,dict) and node.get('input_policy')==DDS_NODE_INPUT_POLICY,'missing original Node input policy')
        qualified_node_inputs(node.get('inputs'))
        require(node.get('version')==DDS_NODE_VERSION and Path(node.get('executable','')).is_absolute()
            and isinstance(node.get('sha256'),str) and re.fullmatch(r'[0-9a-f]{64}',node['sha256']),
            'missing original pinned Node runtime identity')


def pytest_addoption(parser):
    group=parser.getgroup('van-canonical-cwd-audit')
    group.addoption('--van-canonical-state')

def pytest_configure(config):
    global _STATE
    state_path=config.getoption('--van-canonical-state')
    if not state_path:return
    state=load(state_path);root=Path(state['root'])
    require(state.get('schema')==SCHEMA,'current owned-descendant collector schema required')
    require(state.get('supervisor_identity',{}).get('pid')==os.getppid(),'foreign actual supervisor identity')
    require(Path.cwd().resolve()==public.execution_directory(root,state['cwd']),'wrong actual invocation cwd')
    require(not config.option.keyword and not config.option.markexpr and not config.option.deselect
        and not getattr(config.option,'lf',False) and getattr(config.option,'numprocesses',None) in (None,0),'noncanonical selection/parallelism override')
    require(Path(config.rootpath).resolve()==root and Path(config.inipath).resolve()==root/'pytest.ini','wrong pytest root/config')
    require(Path(config.getoption('confcutdir')).resolve()==root,'wrong conftest cut')
    require(os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD')=='1','ambient pytest plugins not canonical')
    state['probe_supervision']=[]
    with supervised_probes(state['probe_supervision'],state['probe_timeout_seconds']):
        state['pytest_inputs']=proof.effective_pytest_inputs(config,root,'gateway')
        state['pytest_arguments']=list(config.invocation_params.args)
        state['child_environment_before']=environment(state['profile'],root)
        state['child_source_before']=proof.source_identity(root,state['commit'])
        state['protected_before']=protected(root)
        state['collection_errors']=[];state['internal_errors']=[]
        state['child_process_identity']=_identity_binding(_process_identity(os.getpid()))
    _STATE=state;config._van_canonical_state=state

def pytest_sessionstart(session):
    state=getattr(session.config,'_van_canonical_state',None)
    if state is None:return
    expected=validate_basetemp(state['basetemp'],state['root'],state['execution_id'],live=True)
    actual=session.config._tmp_path_factory.getbasetemp().resolve()
    require(actual==expected,'wrong actual pytest basetemp')
    state['actual_basetemp']=str(actual)


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
    with supervised_probes(_STATE['probe_supervision'],_STATE['probe_timeout_seconds']):
        after,candidates=proof._source_observation(_STATE['root'],_STATE['commit'],after_run=True)
        _STATE.update(child_source_after=after,generated_cache_candidates=candidates,
            child_environment_after=environment(_STATE['profile'],Path(_STATE['root'])),
            child_protected_after=protected(Path(_STATE['root'])))
    dump(Path(_STATE['output'])/'terminal.json',_STATE)

def build_pytest_arguments(root, output, profile, manifest, collect_only, basetemp):
    root,output=Path(root),Path(output)
    arguments=[*selectors(manifest,profile,root),'-c',str(root/'pytest.ini'),
        '--rootdir='+str(root),'--confcutdir='+str(root),'-p','pytest_asyncio.plugin',
        '-p','anyio.pytest_plugin','-p','tools.rebuild.canonical_source_audit',
        '--van-canonical-state='+str(output/'input.json'),'--basetemp='+str(basetemp),'-q']
    return arguments+(['--collect-only'] if collect_only else ['--junitxml='+str(output/'report.xml')])


class ProcessSupervisionBlocked(ValueError):
    """No current qualification without actual kernel ownership evidence."""


def _process_identity(pid):
    try:raw=Path('/proc',str(pid),'stat').read_text()
    except (FileNotFoundError,NotADirectoryError,ProcessLookupError):return None
    values=raw[raw.rfind(')')+2:].split()
    return {'pid':pid,'ppid':int(values[1]),'start_ticks':int(values[19]),'state':values[0]}


def _identity_binding(value):
    return {key:value[key] for key in ('pid','ppid','start_ticks')}


def _owned_children():
    children={}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        value=_process_identity(int(entry.name))
        if value is not None and value['ppid']==os.getpid():children[value['pid']]=value
    return children


def foreground_git_environment(environment):
    environment=dict(environment)
    try:count=int(environment.get('GIT_CONFIG_COUNT','0'))
    except (TypeError,ValueError):raise ProcessSupervisionBlocked('invalid existing Git configuration injection') from None
    if not 0<=count<=128:raise ProcessSupervisionBlocked('invalid existing Git configuration injection')
    for offset,key in enumerate(('gc.autoDetach','maintenance.autoDetach')):
        environment['GIT_CONFIG_KEY_'+str(count+offset)]=key
        environment['GIT_CONFIG_VALUE_'+str(count+offset)]='false'
    environment['GIT_CONFIG_COUNT']=str(count+2)
    return environment


def _trusted_bootstrap_environment(effective):
    """Use the already trusted active Python runtime, never caller loader knobs.

    The already loaded installed runtime is a trusted executor prerequisite.
    File modes are provenance, not proof against a hostile runtime owner or
    same-user filesystem mutation. Caller loader inputs remain excluded here.
    sysconfig LIBDIR may describe a build machine, so it is not a source here.
    """
    import ctypes
    try:
        executable=Path(sys.executable).resolve(strict=True)
        active=Path('/proc/self/exe').stat();actual=executable.stat()
    except FileNotFoundError:
        raise ProcessSupervisionBlocked('DELETED_BOOTSTRAP_EXECUTABLE') from None
    if not stat.S_ISREG(actual.st_mode):
        raise ProcessSupervisionBlocked('UNQUALIFIED_BOOTSTRAP_EXECUTABLE_TYPE')
    if (active.st_dev,active.st_ino)!=(actual.st_dev,actual.st_ino):
        raise ProcessSupervisionBlocked('REPLACED_BOOTSTRAP_EXECUTABLE_IDENTITY')
    libraries={};api_mapping=None
    api_address=ctypes.cast(ctypes.pythonapi.Py_GetVersion,ctypes.c_void_p).value
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields=line.split(None,5)
        if len(fields)!=6:continue
        low,high=(int(value,16) for value in fields[0].split('-'))
        if api_address is not None and low<=api_address<high:
            if api_mapping is not None or 'x' not in fields[1]:
                raise ProcessSupervisionBlocked('AMBIGUOUS_BOOTSTRAP_PYTHON_API')
            api_mapping=fields
        if not re.search(r'/libpython[^/]*\.so(?:\.[0-9]+)*(?: \(deleted\))?$',fields[5]):continue
        name=fields[5]
        if name.endswith(' (deleted)'):raise ProcessSupervisionBlocked('DELETED_BOOTSTRAP_LIBRARY')
        library=Path(name).resolve(strict=True);info=library.stat()
        major,minor=(int(value,16) for value in fields[3].split(':'))
        if not stat.S_ISREG(info.st_mode):
            raise ProcessSupervisionBlocked('UNQUALIFIED_BOOTSTRAP_LIBRARY_TYPE')
        if (os.major(info.st_dev),os.minor(info.st_dev),info.st_ino)!=(major,minor,int(fields[4])):
            raise ProcessSupervisionBlocked('REPLACED_BOOTSTRAP_LIBRARY_IDENTITY')
        libraries[str(library)]=library
    if len(libraries)>1:raise ProcessSupervisionBlocked('AMBIGUOUS_BOOTSTRAP_LIBRARY')
    if api_mapping is None or api_mapping[5].endswith(' (deleted)'):
        raise ProcessSupervisionBlocked('UNQUALIFIED_BOOTSTRAP_PYTHON_API')
    api_file=Path(api_mapping[5]).resolve(strict=True);api_info=api_file.stat()
    major,minor=(int(value,16) for value in api_mapping[3].split(':'))
    if (os.major(api_info.st_dev),os.minor(api_info.st_dev),api_info.st_ino)!=(major,minor,int(api_mapping[4])):
        raise ProcessSupervisionBlocked('REPLACED_BOOTSTRAP_PYTHON_API')
    if libraries:
        if api_file!=next(iter(libraries.values())):
            raise ProcessSupervisionBlocked('UNRELATED_MAPPED_BOOTSTRAP_LIBRARY')
    elif api_file!=executable:
        raise ProcessSupervisionBlocked('UNQUALIFIED_STANDALONE_PYTHON_API')
    bootstrap={key:value for key,value in effective.items()
        if not os.fsdecode(key).startswith('LD_') and os.fsdecode(key) not in {'GCONV_PATH','GLIBC_TUNABLES'}}
    evidence={'schema':'van.active-python-bootstrap/2','executable':str(executable),
        'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
        'executable_device':actual.st_dev,'executable_inode':actual.st_ino,
        'executable_mode':stat.S_IMODE(actual.st_mode),'runtime_trust':'ALREADY_LOADED_INSTALLED_EXECUTOR',
        'library_mode':'STANDALONE_NO_MAPPED_LIBPYTHON','library':None}
    if libraries:
        library=next(iter(libraries.values()));directory=library.parent;info=directory.stat()
        if (not stat.S_ISDIR(info.st_mode)
            or any(char in str(directory) for char in (':','\n','\r'))):
            raise ProcessSupervisionBlocked('UNQUALIFIED_BOOTSTRAP_LIBRARY_DIRECTORY')
        bootstrap['LD_LIBRARY_PATH']=str(directory)
        evidence.update(library_mode='ACTIVE_MAPPED_LIBPYTHON',library={
            'path':str(library),'sha256':hashlib.sha256(library.read_bytes()).hexdigest(),
            'device':library.stat().st_dev,'inode':library.stat().st_ino,'mode':stat.S_IMODE(library.stat().st_mode),
            'directory_device':info.st_dev,'directory_inode':info.st_ino,'directory_mode':stat.S_IMODE(info.st_mode)})
    return bootstrap,evidence


def _sealed_exec_environment(environment):
    """No payload value is returned in evidence, argv, a pathname or a log."""
    descriptor=None
    try:
        entries=[];names=set();size=0
        for key,value in environment.items():
            key=os.fsencode(key);value=os.fsencode(value)
            if b'=' in key or b'\0' in key or b'\0' in value or key in names:
                raise ProcessSupervisionBlocked('INVALID_ORIGINAL_EXEC_ENVIRONMENT')
            names.add(key);entry=key+b'='+value+b'\0';size+=len(entry)
            if size>EXEC_ENVIRONMENT_CAP:raise ProcessSupervisionBlocked('ORIGINAL_EXEC_ENVIRONMENT_CAPACITY')
            entries.append(entry)
        descriptor=os.memfd_create('van-owned-exec-environment',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        for entry in entries:
            pending=memoryview(entry)
            while pending:
                written=os.write(descriptor,pending)
                if written<=0:raise ProcessSupervisionBlocked('ORIGINAL_EXEC_ENVIRONMENT_WRITE_FAILED')
                pending=pending[written:]
        seals=LINUX_ENVIRONMENT_SEALS
        fcntl.fcntl(descriptor,LINUX_F_ADD_SEALS,seals)
        if fcntl.fcntl(descriptor,LINUX_F_GET_SEALS)!=seals or os.fstat(descriptor).st_size!=size:
            raise ProcessSupervisionBlocked('ORIGINAL_EXEC_ENVIRONMENT_NOT_SEALED')
        os.lseek(descriptor,0,os.SEEK_SET)
        return descriptor,{'schema':'van.sealed-exec-environment/1','bytes':size,'entries':len(entries),
            'sealed':True,'parent_closed':False,'read_after_ownership_ack':True,'closed_before_original_exec':True}
    except BaseException:
        if descriptor is not None:os.close(descriptor)
        raise


class OwnedProcessSupervisor:
    """Process-local Linux ownership, deliberately ported from the qualified runner.

    Evidence is DATA from this producer, not a new signer or platform authority.
    Only kernel-owned children with bound PID/start/PPID identities are signalled.
    """
    def __init__(self):
        self.prepared=False;self.child_started=False;self.child_pid=None
        self.evidence={'schema':'van.kernel-owned-child-supervision/1',
            'capabilities':{'pidfd':False,'subreaper':False,'proc_identity':False},
            'supervisor_identity':None,'leader_identity':None,'leader_pidfd_bound':False,
            'leader_waited':False,'leader_exit':None,'leader_forced_cleanup':False,
            'launch_gate':{'schema':'van.bound-exec-gate/1','source_sha256':hashlib.sha256(LAUNCH_GATE.encode()).hexdigest(),
                'timeout_seconds':LAUNCH_GATE_SECONDS,'environment_policy':LAUNCH_ENVIRONMENT_POLICY,
                'bootstrap':None,'exec_environment':None,
                'released':False,'closed':False,'aborted_before_exec':False},
            'adopted':[],'owned_children_absent':False,'waitpid_echild':False,
            'unexpected_live_descendants':False,'cleanup_error':None,'interrupted':None,'remaining_owned':[]}

    def preflight(self):
        if self.prepared:return
        descriptor=None
        try:
            if (sys.platform!='linux' or not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal')
                    or not hasattr(os,'waitid') or not hasattr(os,'WNOWAIT')):
                raise ProcessSupervisionBlocked('OWNED_CHILD_SUPERVISION_UNAVAILABLE')
            identity=_process_identity(os.getpid())
            if identity is None or _owned_children():raise ProcessSupervisionBlocked('OWNED_CHILD_BASELINE_UNPROVEN')
            self.evidence['supervisor_identity']=_identity_binding(identity)
            self.evidence['capabilities']['proc_identity']=True
            descriptor=os.pidfd_open(os.getpid(),0);signal.pidfd_send_signal(descriptor,0)
            self.evidence['capabilities']['pidfd']=True
            import ctypes
            libc=ctypes.CDLL(None,use_errno=True);value=ctypes.c_int()
            if libc.prctl(36,1,0,0,0)!=0 or libc.prctl(37,ctypes.byref(value),0,0,0)!=0 or value.value!=1:
                raise ProcessSupervisionBlocked('OWNED_CHILD_SUBREAPER_UNAVAILABLE')
            self.evidence['capabilities']['subreaper']=True;self.prepared=True
        except ProcessSupervisionBlocked:raise
        except Exception as error:
            raise ProcessSupervisionBlocked('OWNED_CHILD_SUPERVISION_UNAVAILABLE:'+type(error).__name__) from None
        finally:
            if descriptor is not None:os.close(descriptor)

    @staticmethod
    def _bind(pid):
        descriptor=os.pidfd_open(pid,0)
        try:
            identity=_process_identity(pid)
            if identity is None or identity['ppid']!=os.getpid():raise ProcessSupervisionBlocked('OWNED_CHILD_IDENTITY_UNPROVEN')
            return descriptor,identity
        except BaseException:
            os.close(descriptor);raise

    @staticmethod
    def _signal(descriptor,identity,number):
        current=_process_identity(identity['pid'])
        if current is None:return False
        if current['ppid']!=os.getpid() or current['start_ticks']!=identity['start_ticks']:
            raise ProcessSupervisionBlocked('OWNED_CHILD_IDENTITY_CHANGED')
        try:signal.pidfd_send_signal(descriptor,number)
        except ProcessLookupError:return False
        return True

    def _wait_leader(self,child,timeout_seconds):
        deadline=time.monotonic()+timeout_seconds
        while True:
            if getattr(self,'capture',None) is not None and self.capture.failed.is_set():
                raise ProcessSupervisionBlocked('PREREQUISITE_CAPTURE_FAILED')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise subprocess.TimeoutExpired(child.args,timeout_seconds)
            try:return child.wait(timeout=min(.05,remaining))
            except subprocess.TimeoutExpired:continue

    def _release_gate(self,descriptor):return os.write(descriptor,b'X')

    def _drain(self):
        self.evidence['waitpid_echild']=False;self.evidence['owned_children_absent']=False
        deadline=time.monotonic()+5;started=time.monotonic();bound={};sent=set()
        try:
            while time.monotonic()<deadline:
                current=_owned_children()
                for pid,identity in current.items():
                    key=(pid,identity['start_ticks'])
                    if key not in bound:
                        descriptor,fresh=self._bind(pid)
                        if fresh['start_ticks']!=identity['start_ticks']:
                            os.close(descriptor);raise ProcessSupervisionBlocked('OWNED_CHILD_IDENTITY_CHANGED')
                        bound[key]={'fd':descriptor,'identity':fresh,'signals':[]}
                while True:
                    try:pending=os.waitid(os.P_ALL,0,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                    except ChildProcessError:
                        try:unexpected=os.waitpid(-1,os.WNOHANG)
                        except ChildProcessError:self.evidence['waitpid_echild']=True;break
                        raise ProcessSupervisionBlocked('OWNED_CHILD_SET_CHANGED_BEFORE_ECHILD')
                    if pending is None:break
                    pid=pending.si_pid
                    matches=[(key,row) for key,row in bound.items() if key[0]==pid]
                    if not matches:
                        descriptor,fresh=self._bind(pid);key=(pid,fresh['start_ticks'])
                        bound[key]={'fd':descriptor,'identity':fresh,'signals':[]};matches=[(key,bound[key])]
                    if len(matches)!=1:raise ProcessSupervisionBlocked('REAPED_CHILD_IDENTITY_UNPROVEN')
                    key,row=matches[0]
                    actual,status=os.waitpid(pid,os.WNOHANG)
                    if actual!=pid:raise ProcessSupervisionBlocked('OWNED_CHILD_REAP_CHANGED')
                    self.evidence['adopted'].append({'identity':_identity_binding(row['identity']),
                        'pidfd_bound':True,'wait_status':status,'signals':row['signals'],'reaped':True})
                    os.close(row['fd']);del bound[key]
                if self.evidence['waitpid_echild']:break
                for pid,identity in current.items():
                    fresh=_process_identity(pid)
                    if fresh is None:continue
                    if fresh['ppid']!=os.getpid() or fresh['start_ticks']!=identity['start_ticks']:
                        raise ProcessSupervisionBlocked('OWNED_CHILD_IDENTITY_CHANGED')
                    if fresh['state']=='Z':continue
                    self.evidence['unexpected_live_descendants']=True
                    number=signal.SIGKILL if time.monotonic()-started>=1 else signal.SIGTERM
                    key=(pid,fresh['start_ticks']);marker=(*key,int(number));row=bound[key]
                    if marker not in sent and self._signal(row['fd'],fresh,number):
                        sent.add(marker);row['signals'].append(int(number))
                time.sleep(.02)
            remaining=_owned_children();self.evidence['remaining_owned']=[_identity_binding(v) for v in remaining.values()]
            self.evidence['owned_children_absent']=self.evidence['waitpid_echild'] and not remaining
            if not self.evidence['owned_children_absent']:raise ProcessSupervisionBlocked('OWNED_CHILD_CLEANUP_INCOMPLETE')
        finally:
            for row in bound.values():os.close(row['fd'])
            if not self.evidence['owned_children_absent']:
                # Cleanup failure is not an empty child set. Retain observed
                # identities, or explicit unknown when /proc cannot be read.
                try:self.evidence['remaining_owned']=[_identity_binding(v) for v in _owned_children().values()]
                except BaseException:self.evidence['remaining_owned']=None

    def run(self,command,*,cwd,env,log,timeout_seconds,stderr=subprocess.STDOUT,capture=None):
        child=None;descriptor=None;identity=None;primary=None
        gate_read=None;gate_write=None;environment_descriptor=None
        self.capture=capture
        try:
            self.preflight()
            if _owned_children():raise ProcessSupervisionBlocked('OWNED_CHILD_BASELINE_CHANGED')
            launch_env=foreground_git_environment(env)
            try:
                bootstrap_env,bootstrap=_trusted_bootstrap_environment(launch_env)
                environment_descriptor,environment=_sealed_exec_environment(launch_env)
            except (OSError,AttributeError):
                raise ProcessSupervisionBlocked('TRUSTED_BOOTSTRAP_RUNTIME_UNAVAILABLE') from None
            self.evidence['launch_gate'].update(bootstrap=bootstrap,exec_environment=environment)
            gate_read,gate_write=os.pipe()
            launcher=[sys.executable,'-I','-S','-B','-c',LAUNCH_GATE,str(gate_read),
                str(environment_descriptor),str(environment['bytes']),*[os.fspath(v) for v in command]]
            child=subprocess.Popen(launcher,cwd=cwd,env=bootstrap_env,stdout=log,stderr=stderr,
                start_new_session=True,pass_fds=(gate_read,environment_descriptor))
            self.child_started=True;self.child_pid=child.pid
            os.close(environment_descriptor);environment_descriptor=None
            self.evidence['launch_gate']['exec_environment']['parent_closed']=True
            os.close(gate_read);gate_read=None
            if capture is not None:capture.start(child)
            descriptor,identity=self._bind(child.pid)
            self.evidence['leader_identity']=_identity_binding(identity);self.evidence['leader_pidfd_bound']=True
            if self._release_gate(gate_write)!=1:raise ProcessSupervisionBlocked('OWNED_CHILD_LAUNCH_NOT_ACKNOWLEDGED')
            self.evidence['launch_gate']['released']=True
            os.close(gate_write);gate_write=None;self.evidence['launch_gate']['closed']=True
            self._wait_leader(child,timeout_seconds)
        except BaseException as error:
            primary=error;self.evidence['interrupted']=type(error).__name__
        finally:
            # Every exit path closes the sole parent gate writer before any
            # ownership retry. EOF cannot authorize execution and is bounded.
            for gate in (gate_read,gate_write,environment_descriptor):
                if gate is not None:os.close(gate)
            if self.evidence['launch_gate']['exec_environment'] is not None:
                self.evidence['launch_gate']['exec_environment']['parent_closed']=True
            self.evidence['launch_gate']['closed']=True
            try:
                if child is not None:
                    if not self.evidence['launch_gate']['released']:
                        self.evidence['launch_gate']['aborted_before_exec']=True
                        # Exact Popen wait is kernel ownership, not a numeric
                        # signal fallback. This also works when pidfd binding
                        # is permanently unavailable after a successful spawn.
                        child.wait(timeout=LAUNCH_GATE_SECONDS+1)
                        self.evidence['leader_waited']=True;self.evidence['leader_exit']=child.returncode
                    else:
                        self._finish_released_child(child,descriptor,identity)
                        self.evidence['leader_waited']=child.returncode is not None;self.evidence['leader_exit']=child.returncode
            except BaseException as error:self.evidence['cleanup_error']=type(error).__name__+': '+str(error)
            finally:
                # Independently attempt the kernel-owned drain even when the
                # leader's initial/retry binding or wait failed.
                try:
                    if self.prepared:self._drain()
                except BaseException as error:
                    prior=self.evidence['cleanup_error']
                    self.evidence['cleanup_error']=(prior+'; ' if prior else '')+type(error).__name__+': '+str(error)
                finally:
                    if descriptor is not None:os.close(descriptor)
                    if capture is not None:
                        try:capture.finish()
                        except BaseException as error:
                            prior=self.evidence['cleanup_error']
                            self.evidence['cleanup_error']=(prior+'; ' if prior else '')+type(error).__name__+': '+str(error)
        if primary is not None:raise primary
        if self.evidence['cleanup_error'] is not None or not self.evidence['owned_children_absent']:
            raise ProcessSupervisionBlocked('OWNED_CHILD_CLEANUP_INCOMPLETE')
        if self.evidence['unexpected_live_descendants']:
            raise ProcessSupervisionBlocked('UNEXPECTED_LIVE_DESCENDANTS_REAPED_NOT_QUALIFIED')
        return self.evidence['leader_exit']

    def _finish_released_child(self,child,descriptor,identity):
        if descriptor is None or identity is None:raise ProcessSupervisionBlocked('RELEASED_CHILD_WITHOUT_BOUND_OWNERSHIP')
        if child.poll() is None:
            self.evidence['leader_forced_cleanup']=True
            self._signal(descriptor,identity,signal.SIGTERM)
            try:child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._signal(descriptor,identity,signal.SIGKILL);child.wait(timeout=3)


class _BoundedCapture:
    """Drain pipes without allocating unbounded disk or memory, including on failure."""
    def __init__(self):
        self.failed=threading.Event();self.stop=threading.Event();self.threads=[]
        self.buffers={'stdout':bytearray(),'stderr':bytearray()}
        self.output_limit_exceeded=False;self.errors=[];self.joined=False

    def start(self,child):
        self.pipes=[child.stdout,child.stderr]
        for name,pipe in zip(('stdout','stderr'),self.pipes):
            worker=threading.Thread(target=self._drain,args=(name,pipe),name='canonical-probe-'+name)
            worker.start();self.threads.append(worker)

    def _drain(self,name,pipe):
        try:
            while True:
                ready,_,_=select.select([pipe.fileno()],[],[],.05)
                if not ready:
                    if self.stop.is_set():break
                    continue
                data=os.read(pipe.fileno(),16384)
                if not data:break
                remaining=max(0,PROBE_OUTPUT_CAP-len(self.buffers[name]))
                self.buffers[name].extend(data[:remaining])
                if len(data)>remaining:
                    self.output_limit_exceeded=True;self.failed.set()
                # Continue draining/discarding after the cap while the owner
                # kills and reaps its exact kernel children.
        except BaseException as error:
            self.errors.append(type(error).__name__);self.failed.set()
        finally:pipe.close()

    def finish(self):
        self.stop.set()
        for worker in self.threads:worker.join(timeout=5)
        self.joined=all(not worker.is_alive() for worker in self.threads)
        # A reader that failed to start must not leave its pipe open.
        for pipe in getattr(self,'pipes',[])[len(self.threads):]:pipe.close()
        if not self.joined:raise ProcessSupervisionBlocked('PREREQUISITE_READER_NOT_JOINED')


def profile_evidence_scope(receipt):
    if receipt.get('schema')==LEGACY_SCHEMA:return 'HISTORICAL_GROUP_ONLY'
    require(receipt.get('schema')==SCHEMA,'unsupported canonical profile schema')
    return 'OWNED_DESCENDANTS_REQUIRED'


def _verify_process_supervision(receipt,state):
    evidence=receipt.get('process_supervision')
    keys={'schema','capabilities','supervisor_identity','leader_identity','leader_pidfd_bound','leader_waited','leader_exit',
        'leader_forced_cleanup','adopted','owned_children_absent','waitpid_echild','unexpected_live_descendants',
        'cleanup_error','interrupted','remaining_owned','launch_gate'}
    require(isinstance(evidence,dict) and set(evidence)==keys and evidence['schema']=='van.kernel-owned-child-supervision/1',
        'missing or foreign owned-child supervision')
    require(evidence['capabilities']=={'pidfd':True,'subreaper':True,'proc_identity':True},'unproven process supervision capabilities')
    gate=evidence['launch_gate']
    require(isinstance(gate,dict) and set(gate)=={'schema','source_sha256','timeout_seconds','environment_policy',
        'released','closed','aborted_before_exec','bootstrap','exec_environment'},'missing exact bound-exec launch gate')
    require({key:value for key,value in gate.items() if key not in {'bootstrap','exec_environment'}}=={'schema':'van.bound-exec-gate/1',
        'source_sha256':hashlib.sha256(LAUNCH_GATE.encode()).hexdigest(),'timeout_seconds':LAUNCH_GATE_SECONDS,
        'environment_policy':LAUNCH_ENVIRONMENT_POLICY,
        'released':True,'closed':True,'aborted_before_exec':False},'missing exact bound-exec launch gate')
    bootstrap=gate['bootstrap'];environment=gate['exec_environment']
    digest=lambda value:isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None
    modern=isinstance(bootstrap,dict) and bootstrap.get('schema')=='van.active-python-bootstrap/2'
    bootstrap_keys={'schema','executable','executable_sha256','library_mode','library'}
    if modern:bootstrap_keys|={'executable_device','executable_inode','executable_mode','runtime_trust'}
    require(isinstance(bootstrap,dict) and set(bootstrap)==bootstrap_keys
        and bootstrap['schema'] in {'van.active-python-bootstrap/1','van.active-python-bootstrap/2'} and isinstance(bootstrap['executable'],str)
        and Path(bootstrap['executable']).is_absolute() and digest(bootstrap['executable_sha256']),
        'unproven trusted bootstrap executable')
    if modern:
        require(bootstrap['runtime_trust']=='ALREADY_LOADED_INSTALLED_EXECUTOR'
            and type(bootstrap['executable_device']) is int and bootstrap['executable_device']>=0
            and type(bootstrap['executable_inode']) is int and bootstrap['executable_inode']>0
            and type(bootstrap['executable_mode']) is int and 0<=bootstrap['executable_mode']<=0o7777,
            'unproven installed bootstrap runtime provenance')
    library=bootstrap['library']
    if bootstrap['library_mode']=='STANDALONE_NO_MAPPED_LIBPYTHON':
        require(library is None,'foreign standalone bootstrap library')
    else:
        require(bootstrap['library_mode']=='ACTIVE_MAPPED_LIBPYTHON' and isinstance(library,dict)
            and set(library)==({'path','sha256','device','inode','directory_device','directory_inode','directory_mode'}|({'mode'} if modern else set()))
            and isinstance(library['path'],str) and Path(library['path']).is_absolute() and digest(library['sha256'])
            and all(type(library[key]) is int and library[key]>=0 for key in ('device','inode','directory_device','directory_inode','directory_mode'))
            and library['inode']>0 and library['directory_inode']>0 and library['directory_mode']<=0o7777
            and (modern or not library['directory_mode'] & 0o022),
            'unproven active mapped bootstrap library')
        if modern:require(type(library['mode']) is int and 0<=library['mode']<=0o7777,'invalid mapped runtime mode provenance')
    require(isinstance(environment,dict) and set(environment)=={'schema','bytes','entries','sealed','parent_closed',
        'read_after_ownership_ack','closed_before_original_exec'}
        and environment['schema']=='van.sealed-exec-environment/1'
        and type(environment['bytes']) is int and 0<=environment['bytes']<=EXEC_ENVIRONMENT_CAP
        and type(environment['entries']) is int and 0<=environment['entries']<=environment['bytes']
        and all(environment[key] is True for key in ('sealed','parent_closed','read_after_ownership_ack','closed_before_original_exec')),
        'unproven original exec environment handoff')
    def identity(value):
        return (isinstance(value,dict) and set(value)=={'pid','ppid','start_ticks'} and
            all(type(value[k]) is int for k in value) and value['pid']>0 and value['ppid']>=0 and value['start_ticks']>0)
    parent=evidence['supervisor_identity'];leader=evidence['leader_identity']
    require(identity(parent) and identity(leader) and parent==receipt.get('supervisor_identity')
        and parent==state.get('supervisor_identity') and leader==state.get('child_process_identity') and leader['ppid']==parent['pid']
        and receipt.get('child_pid')==leader['pid'] and leader['pid']!=parent['pid'],'foreign supervisor/collector identity')
    require(evidence['leader_pidfd_bound'] is True and evidence['leader_waited'] is True and type(evidence['leader_exit']) is int
        and evidence['leader_exit']==receipt['exit']==0 and evidence['leader_forced_cleanup'] is False
        and evidence['owned_children_absent'] is True and evidence['waitpid_echild'] is True
        and evidence['unexpected_live_descendants'] is False and evidence['cleanup_error'] is None
        and evidence['interrupted'] is None and evidence['remaining_owned']==[],'incomplete or forced owned-child cleanup')
    require(isinstance(evidence['adopted'],list),'invalid adopted-child evidence');seen=set()
    for row in evidence['adopted']:
        require(isinstance(row,dict) and set(row)=={'identity','pidfd_bound','wait_status','signals','reaped'}
            and identity(row['identity']) and row['identity']['ppid']==parent['pid']
            and row['identity']['pid'] not in {parent['pid'],leader['pid']} and row['identity']['pid'] not in seen
            and row['pidfd_bound'] is True and type(row['wait_status']) is int and row['wait_status']>=0
            and row['signals']==[] and row['reaped'] is True,'unproven or forced adopted-child reaping')
        seen.add(row['identity']['pid'])


class _ProbeSubprocess:
    """Scoped module facade: exact existing argv/timeouts, supervised ownership."""
    def __init__(self,original,records,timeout_seconds):
        self.original,self.records,self.timeout_seconds=original,records,timeout_seconds
    def __getattr__(self,name):return getattr(self.original,name)
    def run(self,command,**kwargs):
        allowed={'cwd','env','timeout','capture_output','text','check'}
        if set(kwargs)-allowed or not kwargs.get('capture_output'):
            raise ProcessSupervisionBlocked('unsupported prerequisite subprocess shape')
        timeout=kwargs.get('timeout',self.timeout_seconds)
        if timeout is None:timeout=self.timeout_seconds
        argv=[os.fspath(v) for v in command]
        owner=OwnedProcessSupervisor();record={'argv':argv,'cwd':str(Path(kwargs.get('cwd') or Path.cwd()).resolve()),
            'command_sha256':hashlib.sha256(_JSON_DUMPS(argv,separators=(',',':')).encode()).hexdigest(),
            'timeout_seconds':timeout,'timeout_policy':'EXPLICIT_OR_EXISTING_PROFILE_BOUND','process_supervision':None}
        capture=_BoundedCapture()
        try:
            code=owner.run(command,cwd=kwargs.get('cwd'),env=kwargs.get('env',os.environ),log=subprocess.PIPE,
                stderr=subprocess.PIPE,timeout_seconds=timeout,capture=capture)
        finally:
            stdout,stderr=bytes(capture.buffers['stdout']),bytes(capture.buffers['stderr'])
            record.update(process_supervision=owner.evidence,stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                stderr_sha256=hashlib.sha256(stderr).hexdigest(),stdout_bytes=len(stdout),stderr_bytes=len(stderr),
                capture_threads_joined=capture.joined,output_limit_exceeded=capture.output_limit_exceeded,
                capture_errors=capture.errors)
            self.records.append(record)
        if capture.failed.is_set():raise ProcessSupervisionBlocked('PREREQUISITE_CAPTURE_FAILED')
        if kwargs.get('text'):stdout=stdout.decode();stderr=stderr.decode()
        result=self.original.CompletedProcess(command,code,stdout,stderr)
        if kwargs.get('check') and code:raise self.original.CalledProcessError(code,command,output=stdout,stderr=stderr)
        return result
    def check_output(self,command,**kwargs):
        result=self.run(command,capture_output=True,**kwargs)
        if result.returncode:raise self.original.CalledProcessError(result.returncode,command,output=result.stdout,stderr=result.stderr)
        return result.stdout


from contextlib import contextmanager
@contextmanager
def supervised_probes(records,timeout_seconds):
    """Only this synchronous owner's modules are rebound, never global stdlib."""
    modules=(sys.modules[__name__],proof,public)
    previous=[(module,module.subprocess) for module in modules]
    facade=_ProbeSubprocess(subprocess,records,timeout_seconds)
    try:
        for module,_ in previous:module.subprocess=facade
        yield
    finally:
        for module,original in reversed(previous):module.subprocess=original


def _verify_probe_supervision(records,parent):
    require(isinstance(records,list) and records,'missing prerequisite subprocess proof')
    for row in records:
        require(isinstance(row,dict) and set(row)=={'argv','cwd','command_sha256','timeout_seconds','timeout_policy','process_supervision',
            'stdout_sha256','stderr_sha256','stdout_bytes','stderr_bytes','capture_threads_joined','output_limit_exceeded','capture_errors'}
            and isinstance(row['argv'],list) and row['argv'] and all(isinstance(v,str) and '\x00' not in v for v in row['argv'])
            and isinstance(row['cwd'],str) and Path(row['cwd']).is_absolute()
            and row['command_sha256']==hashlib.sha256(_JSON_DUMPS(row['argv'],separators=(',',':')).encode()).hexdigest()
            and row['timeout_policy']=='EXPLICIT_OR_EXISTING_PROFILE_BOUND'
            and type(row['timeout_seconds']) in (int,float) and 0<row['timeout_seconds']<=3600
            and all(isinstance(row[k],str) and re.fullmatch('[0-9a-f]{64}',row[k]) for k in ('command_sha256','stdout_sha256','stderr_sha256'))
            and all(type(row[k]) is int and 0<=row[k]<=PROBE_OUTPUT_CAP for k in ('stdout_bytes','stderr_bytes'))
            and row['capture_threads_joined'] is True and row['output_limit_exceeded'] is False and row['capture_errors']==[],
            'invalid prerequisite subprocess proof')
        evidence=row['process_supervision']
        require(isinstance(evidence,dict) and evidence.get('supervisor_identity')==parent,'foreign prerequisite subprocess owner')
        _verify_process_supervision({'process_supervision':evidence,'supervisor_identity':parent,
            'child_pid':(evidence.get('leader_identity') or {}).get('pid'),'exit':evidence.get('leader_exit')},
            {'supervisor_identity':parent,'child_process_identity':evidence.get('leader_identity')})


def _source_probe_commands():
    return [['git','rev-parse','HEAD'],['git','diff','--no-ext-diff','--name-only','HEAD','--'],
        ['git','ls-files','-z','--others','--exclude-standard'],
        ['git','ls-files','-z','--others','--ignored','--exclude-standard'],
        ['git','ls-files','--','pytest.ini'],['git','rev-parse','HEAD^{tree}']]


def _verify_probe_transcript(records,receipt,state,root,*,collector):
    """Reconstruct the actual helper call sequence; a hash-shaped value is no proof.

    This validates original recorded argv/cwd/time bounds, without executing any
    reader Java/Node or adopting a reader prerequisite as the producer's runtime.
    """
    root=Path(root);timeout=receipt.get('probe_timeout_seconds')
    require(type(timeout) is int and 1<=timeout<=3600,'invalid original probe time bound')
    parent_cwd=receipt.get('preflight_cwd')
    require(parent_cwd in {str(root),str(root/'backend')},'foreign original preflight cwd')
    default_cwd=state['actual_cwd'] if collector else parent_cwd
    environment=receipt['environment_before'];profile=receipt['profile'];expected=[]
    def append(argv,cwd=root,bound=timeout):expected.append((argv,str(cwd),bound))
    def source():
        for argv in _source_probe_commands():append(argv)
    def runtime():
        spec=PROFILES[profile]
        if spec.get('nft'):append(['nft','--version'],default_cwd)
        if spec.get('agp'):append(['java','-version'],default_cwd,10)
        if spec.get('dds'):
            sibling=root.parent/'dial-development-system'
            append(['git','rev-parse','HEAD'],sibling)
            for path in DDS_RESOLVER_SOURCES:append(['git','show',DDS_COMMIT+':'+path],sibling)
            append([environment['node']['executable'],'--version'],default_cwd,10)
    if collector:
        # Plugin manager iteration order is not promised. Bind its exact local
        # plugin set, one check each, before the deterministic helper sequence.
        local={key for key in state['pytest_inputs']['plugins'] if key.endswith('.py')}
        prefix=records[:len(local)]
        require(len(prefix)==len(local) and {tuple(row['argv']) for row in prefix}==
            {('git','ls-files','--',key) for key in local}
            and all(row['cwd']==str(root) and row['timeout_seconds']==timeout for row in prefix),
            'original collector plugin probe transcript differs')
        records=records[len(local):]
        runtime();source();source();runtime()
    else:
        append(['git','ls-files','-z','--',*ROOTS]);source();runtime();source()
        for relative in receipt['generated_cache_outputs']:
            path=Path(relative)
            source_path=path.parent.parent/(path.name.split('.'+sys.implementation.cache_tag,1)[0]+'.py')
            append(['git','show',receipt['commit']+':'+source_path.as_posix()])
            append(['git','ls-tree',receipt['commit'],'--',source_path.as_posix()])
            append(['git','show',receipt['commit']+':'+source_path.as_posix()])
        source();source();runtime()
    require([(row['argv'],row['cwd'],row['timeout_seconds']) for row in records]==expected,
        'original prerequisite probe transcript differs')


def run(args):
    root=ROOT;output=args.output.resolve();require(not output.exists(),'fresh owned evidence directory required')
    require(not output.is_relative_to(root),'canonical audit outputs/basetemps must be outside checkout')
    require(args.profile not in {'gateway','media'},'original public four-worker/media owner must be used')
    output.mkdir(parents=True)
    baseline={'schema':SCHEMA,'profile':args.profile,'cwd':args.cwd,'commit':args.expected_commit,
        'root':str(root),'output':str(output),'execution_id':str(uuid.uuid4()),
        'workflow':{'id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT')},
        'collect_only':args.collect_only,'terminal':False,'preflight_cwd':str(Path.cwd().resolve())}
    child_started=False;child_terminal=False;remaining=[];owner=OwnedProcessSupervisor();interruption=None;probe_context=None
    baseline['probe_supervision']=[];baseline['probe_timeout_seconds']=args.timeout_seconds
    try:
        owner.preflight();baseline['supervisor_identity']=owner.evidence['supervisor_identity']
        probe_context=supervised_probes(baseline['probe_supervision'],args.timeout_seconds);probe_context.__enter__()
        require(baseline['workflow']['id'] and baseline['workflow']['attempt'],'explicit current workflow identity required')
        require(not any(os.environ.get(k) for k in ('PYTEST_ADDOPTS','PYTEST_PLUGINS','PYTHONHOME','PYTHONUSERBASE','PYTHONSTARTUP','PYTHONINSPECT','PYTHONOPTIMIZE')),'ambient selection/import override')
        baseline['manifest']=inventory(root)
        baseline['source_before']=proof.source_identity(root,args.expected_commit)
        baseline['environment_before']=environment(args.profile,root)
        baseline['protected_before']=protected(root)
        cwd=public.execution_directory(root,args.cwd)
        chosen=selectors(baseline['manifest'],args.profile,root);require(chosen,'profile has no selectors')
        baseline['actual_cwd']=str(cwd)
        baseline['basetemp']=create_basetemp(root,baseline['execution_id'])
        state=output/'input.json';dump(state,baseline)
        (output/'phases.jsonl').write_text('')
        command=[sys.executable,'-B','-s',str(root/'tools/rebuild/source_storage_audit.py'),
            '--checkout-root',str(root),'--report',str(output/'storage-audit.json'),
            *build_pytest_arguments(root,output,args.profile,baseline['manifest'],args.collect_only,baseline['basetemp']['path'])]
        env={**os.environ,'PYTHONPATH':os.pathsep.join(str(root/p) for p in proof.CANONICAL_PYTHONPATH),
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
        baseline['command']=command
        with (output/'pytest.log').open('w') as log:
            exitcode=owner.run(command,cwd=cwd,env=env,log=log,timeout_seconds=args.timeout_seconds)
        evidence=owner.evidence
        child_started=owner.child_started
        child_terminal=evidence['leader_waited'] and evidence['owned_children_absent'] and evidence['waitpid_echild']
        remaining=evidence['remaining_owned']
        baseline.update(child_pid=evidence['leader_identity']['pid'],exit=exitcode,children_remaining=remaining)
        baseline['generated_cache_outputs']=proof.archive_generated_bytecode(root,args.expected_commit,baseline['source_before'],output)
        child_state=load(output/'terminal.json')
        require(child_state.get('generated_cache_candidates')==baseline['generated_cache_outputs'],'child/parent generated-cache observation differs')
        baseline.update(source_after=proof.source_identity(root,args.expected_commit),
            environment_after=environment(args.profile,root),protected_after=protected(root))
        baseline['state']='TERMINAL' if exitcode==0 else 'FAILED'
    except BaseException as exc:
        baseline.update(state='BLOCKED',reason_type=type(exc).__name__,reason=str(exc))
        baseline.setdefault('exit',owner.evidence['leader_exit'])
        if isinstance(exc,subprocess.TimeoutExpired):baseline['timed_out']=True
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):interruption=exc
    finally:
        if owner.prepared:
            try:owner._drain()
            except BaseException as error:owner.evidence['cleanup_error']=type(error).__name__+': '+str(error)
        if probe_context is not None:probe_context.__exit__(None,None,None)
        baseline['process_supervision']=owner.evidence
        if owner.evidence['cleanup_error'] is not None or owner.evidence['unexpected_live_descendants']:
            baseline.update(state='BLOCKED',cleanup_error=owner.evidence['cleanup_error'] or 'UNEXPECTED_LIVE_DESCENDANTS')
        child_started=owner.child_started
        child_terminal=(owner.evidence['leader_waited'] and owner.evidence['owned_children_absent']
            and owner.evidence['waitpid_echild'] and owner.evidence['cleanup_error'] is None
            and owner.evidence['interrupted'] is None and not owner.evidence['unexpected_live_descendants'])
        remaining=owner.evidence['remaining_owned'] if child_terminal else None
        baseline['children_remaining']=remaining
        if child_started:baseline['child_pid']=owner.child_pid
    if 'basetemp' in baseline:
        try:
            baseline['basetemp_cleanup']=cleanup_basetemp(baseline['basetemp'],root,baseline['execution_id'],
                child_started=child_started,child_terminal=child_terminal,children_remaining=remaining)
        except Exception as exc:
            baseline.update(state='BLOCKED',cleanup_error=type(exc).__name__+': '+str(exc))
    baseline['terminal']=True
    baseline['artifacts']={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='receipt.json'}
    dump(output/'receipt.json',baseline)
    if interruption is not None:raise interruption
    return 0 if baseline['state']=='TERMINAL' else 1

def producer_output(folder, receipt, state, root):
    """Bind the original invocation path; downloaded artifacts may be relocated."""
    original=receipt.get('output')
    require(isinstance(original,str) and bool(original) and '\x00' not in original,
        'invalid original producer output')
    output=Path(original)
    require(output.is_absolute() and str(output)==original and '..' not in output.parts
        and output!=Path('/') and not output.is_relative_to(Path(root)),
        'invalid original producer output')
    # These are original producer observations, not paths inferred from the
    # consumer's extraction directory. Keep every original argument exact.
    identities=('schema','profile','cwd','commit','root','output','execution_id',
        'workflow','collect_only','manifest','actual_cwd')
    if receipt.get('schema')==SCHEMA:identities+=('supervisor_identity','preflight_cwd','probe_timeout_seconds')
    for observed in (state,load(Path(folder)/'input.json'),load(Path(folder)/'collection.json')):
        require(isinstance(observed,dict) and all(key in receipt and key in observed and receipt[key]==observed[key]
            for key in identities),'original producer identity differs')
    require(receipt['root']==str(root),'foreign original producer root')
    return output


def verify_profile(folder,manifest,profile,cwd,commit,root):
    folder=Path(folder);receipt=load(folder/'receipt.json');state=load(folder/'terminal.json')
    require(profile_evidence_scope(receipt)!='HISTORICAL_GROUP_ONLY','HISTORICAL_GROUP_ONLY: legacy profile needs a fresh current owned-descendant run')
    require(receipt['workflow'].get('id') and receipt['workflow'].get('attempt'),'missing current workflow identity')
    _verify_process_supervision(receipt,state)
    _verify_probe_supervision(receipt.get('probe_supervision'),receipt.get('supervisor_identity'))
    _verify_probe_supervision(state.get('probe_supervision'),state.get('child_process_identity'))
    _verify_probe_transcript(receipt['probe_supervision'],receipt,state,root,collector=False)
    _verify_probe_transcript(state['probe_supervision'],receipt,state,root,collector=True)
    require(receipt['state']=='TERMINAL' and receipt['terminal'] and receipt['exit']==0 and receipt.get('children_remaining')==[] and state['pytest_exit']==0,'blocked/aborted/failed runtime')
    require(receipt['schema']==state['schema']==SCHEMA and receipt['manifest']==state['manifest']==manifest,'source/profile inventory mismatch')
    require(receipt['profile']==state['profile']==profile and receipt['cwd']==state['cwd']==cwd and receipt['commit']==state['commit']==commit,'foreign profile/cwd/commit')
    require(receipt['actual_cwd']==state['actual_cwd']==str(public.execution_directory(root,cwd)),'wrong actual parent cwd')
    require(isinstance(receipt.get('execution_id'),str) and receipt['execution_id'] and receipt['execution_id']==state['execution_id'] and receipt['workflow']==state['workflow']==
        {'id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT')},'foreign execution/workflow')
    require(receipt['environment_before']==receipt['environment_after']==state['child_environment_before']==state['child_environment_after'],'environment/profile drift')
    verify_environment(profile,receipt['environment_before'],root)
    require(receipt['basetemp']==state['basetemp'],'foreign basetemp identity')
    basetemp=validate_basetemp(receipt['basetemp'],root,receipt['execution_id'],
        producer_uid=receipt['environment_before'].get('uid'))
    cleanup=receipt.get('basetemp_cleanup',{})
    require(state.get('actual_basetemp')==str(basetemp) and cleanup=={
        'path':str(basetemp),'execution_id':receipt['execution_id'],'state':'REMOVED_OWNED_TERMINAL',
        'identity_sha256':hashlib.sha256(_JSON_DUMPS(receipt['basetemp'],sort_keys=True).encode()).hexdigest()},
        'missing or foreign terminal basetemp cleanup')
    expected=proof.source_identity(root,commit)
    require(receipt['source_before']==receipt['source_after']==state['child_source_before']==state['child_source_after']==expected,'source drift')
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
    output=producer_output(folder,receipt,state,root)
    prefix=['-B','-s',str(Path(root)/'tools/rebuild/source_storage_audit.py'),'--checkout-root',str(root),'--report',str(output/'storage-audit.json')]
    require(type(state.get('collect_only')) is bool and receipt.get('collect_only')==state['collect_only'],'phase identity differs')
    expected_arguments=build_pytest_arguments(root,output,profile,manifest,state['collect_only'],basetemp)
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

@contextmanager
def termination_handlers():
    """Turn actual CLI termination into an exception that runs ownership finally blocks."""
    previous={number:signal.getsignal(number) for number in (signal.SIGINT,signal.SIGTERM)}
    def interrupted(number,frame):raise SystemExit(128+number)
    try:
        for number in previous:signal.signal(number,interrupted)
        yield
    finally:
        for number,handler in previous.items():signal.signal(number,handler)


def _auxiliary_cli(args):
    owner=OwnedProcessSupervisor();records=[];primary=None;code=1
    try:
        owner.preflight()
        with supervised_probes(records,args.timeout_seconds):
            if args.command=='plan':dump(args.output,inventory(ROOT));code=0
            else:code=join(args)
    except BaseException as error:primary=error
    finally:
        if owner.prepared:
            try:owner._drain()
            except BaseException as error:
                owner.evidence['cleanup_error']=type(error).__name__+': '+str(error)
                if primary is None:primary=error
        record={'schema':SCHEMA,'command':args.command,'process_supervision':owner.evidence,
            'probe_supervision':records,'state':'TERMINAL' if primary is None else 'BLOCKED'}
        if primary is not None:
            record.update(reason_type=type(primary).__name__,reason=str(primary))
            dump(args.output,record)
        dump(args.output.with_name(args.output.name+'.supervision.json'),record)
    if primary is not None:
        if isinstance(primary,(KeyboardInterrupt,SystemExit)):raise primary
        return 1
    return code


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('plan','run','join'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--expected-commit',required=True)
    parser.add_argument('--profile',choices=tuple(PROFILES));parser.add_argument('--cwd',choices=('checkout','backend'),default='checkout')
    parser.add_argument('--collect-only',action='store_true');parser.add_argument('--timeout-seconds',type=int,default=1800)
    parser.add_argument('--reports',type=Path);parser.add_argument('--public-root',type=Path);parser.add_argument('--public-backend',type=Path)
    parser.add_argument('--public-root-result',choices=('success','failure','cancelled','skipped'));parser.add_argument('--public-backend-result',choices=('success','failure','cancelled','skipped'))
    args=parser.parse_args();require(1<=args.timeout_seconds<=3600,'invalid child time cap')
    checkout_root(Path.cwd(),ROOT)
    with termination_handlers():
        if args.command=='run':require(args.profile is not None,'explicit original runtime profile required');return run(args)
        if args.command=='join':
            require(all(getattr(args,k) is not None for k in ('reports','public_root','public_backend','public_root_result','public_backend_result')),'complete matrix inputs required')
        return _auxiliary_cli(args)

if __name__=='__main__':raise SystemExit(main())
