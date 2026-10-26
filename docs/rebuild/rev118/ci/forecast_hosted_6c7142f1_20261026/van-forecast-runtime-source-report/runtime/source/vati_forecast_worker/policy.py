"""Fixed-fixture worker policy, checked before any framework import or file write.

These limits are source-test policy, not a research grant, native admission or
permission to consume owner data. General training/inference jobs remain gated
by the canonical programme and its actual referenced authorities.
"""
from dataclasses import dataclass
from fractions import Fraction
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re


class WorkerBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class WorkerBudget:
    cpu_millis: int=2000
    memory_bytes: int=6*1024**3
    pids: int=256
    runtime_seconds: int=300
    log_bytes: int=4*1024**2
    artifact_bytes: int=64*1024**2

    def __post_init__(self):
        for name,lower,upper in (
            ('cpu_millis',250,2000),('memory_bytes',256*1024**2,6*1024**3),
            ('pids',16,256),('runtime_seconds',1,600),
            ('log_bytes',1024,4*1024**2),('artifact_bytes',1024,64*1024**2),
        ):
            value=getattr(self,name)
            if type(value) is not int or not lower<=value<=upper:
                raise WorkerBoundaryError('WORKER_RESOURCE_POLICY_INVALID:'+name)

    def body(self):
        return {**self.__dict__,'execution_authority':False,'economic_admission':False}


_PROXIES=('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy')
_THREADS=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','ARROW_NUM_THREADS')
_ROLES=frozenset({'RESEARCH_FIXTURE_SMOKE','INFERENCE_FIXTURE_SMOKE'})


def fixture_environment(role):
    """Never copy the host environment into a model worker."""
    if not isinstance(role,str) or role not in _ROLES:raise WorkerBoundaryError('UNADMITTED_WORKER_ROLE')
    return {**{name:'' for name in _PROXIES},**{name:'1' for name in _THREADS},
        'VAN_MODEL_WORKER_ROLE':role,'HOME':'/tmp/van-model-worker','MPLCONFIGDIR':'/tmp/matplotlib',
        'PYTHONPATH':'/opt/van','PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0',
        'CUDA_VISIBLE_DEVICES':'','GPG_KEY':'','HF_HUB_OFFLINE':'1',
        'DO_NOT_TRACK':'1','MLFLOW_DISABLE_TELEMETRY':'true','FEAST_USAGE':'False',
        'RAY_USAGE_STATS_ENABLED':'0'}


def require_fixture_environment(environment=None):
    values=os.environ if environment is None else environment
    role=values.get('VAN_MODEL_WORKER_ROLE');expected=fixture_environment(role)
    # Public interpreter metadata is supplied by the pinned base image. All
    # additional application, cloud, broker and owner variables refuse before
    # models load; no incoming variable value is included in the error.
    allowed=set(expected)|{'PATH','HOSTNAME','LANG','PYTHON_VERSION','PYTHON_SHA256'}
    if set(values)-allowed or any(values.get(name)!=value for name,value in expected.items()):
        raise WorkerBoundaryError('WORKER_ENVIRONMENT_NOT_MINIMAL')
    return {'role':role,'environment_keys':sorted(values),'broker_credentials_forwarded':False,
            'execution_authority':False,'data_environment':'FIXTURE'}


def require_kernel_limits(budget,observed):
    try:
        if not isinstance(observed,dict) or any(not isinstance(observed.get(name),str)
                for name in ('cpu.max','memory.max','pids.max')):raise ValueError()
        quota,period=observed['cpu.max'].split()
        if quota=='max' or int(quota)<=0 or int(period)<=0:raise ValueError()
        if Fraction(int(quota),int(period))>Fraction(budget.cpu_millis,1000):raise ValueError()
        for name,maximum in (('memory.max',budget.memory_bytes),('pids.max',budget.pids)):
            if observed[name]=='max' or not 0<int(observed[name])<=maximum:raise ValueError()
    except (KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
        raise WorkerBoundaryError('WORKER_KERNEL_LIMITS_UNAVAILABLE_OR_EXCEED_POLICY') from exc
    return dict(observed)


def require_worker_boundary(budget=None):
    budget=budget or WorkerBudget();environment=require_fixture_environment()
    observed={name:(Path('/sys/fs/cgroup')/name).read_text().strip()
              for name in ('cpu.max','memory.max','pids.max')}
    require_kernel_limits(budget,observed)
    root_flags=next(line.split()[3].split(',') for line in Path('/proc/mounts').read_text().splitlines()
                    if line.split()[1]=='/')
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if 'ro' not in root_flags or os.getuid()==0 or status['NoNewPrivs'].strip()!='1' or int(status['CapEff'].strip(),16)!=0:
        raise WorkerBoundaryError('WORKER_PROCESS_BOUNDARY_UNAVAILABLE')
    # Default routes must be absent in this offline fixture worker. This is
    # observed process policy, not native host or production qualification.
    routes=Path('/proc/net/route').read_text().splitlines()[1:]
    interfaces={path.name for path in Path('/sys/class/net').iterdir()}
    if interfaces!={'lo'} or any(line.split()[1]=='00000000' for line in routes):
        raise WorkerBoundaryError('WORKER_NETWORK_NOT_OFFLINE')
    return {**environment,'budget':budget.body(),'observed_cgroup':observed,
            'root_read_only':True,'no_new_privileges':True,'effective_capabilities':0}


def require_locked_environment():
    root=Path(__file__).parent
    expected=json.loads((root/'environment.json').read_text())
    if (platform.python_implementation()!=expected['implementation']
            or platform.python_version()!=expected['python']
            or platform.system()!=expected['platform'] or platform.machine()!=expected['architecture']):
        raise WorkerBoundaryError('WORKER_INTERPRETER_OR_ARCHITECTURE_INCOMPATIBLE')
    manifest=json.loads((root/'locks/wheel-manifest-cp312-linux-x86_64.json').read_text())
    versions={}
    for row in manifest['wheels']:
        try:actual=importlib.metadata.version(row['name'])
        except importlib.metadata.PackageNotFoundError as exc:
            raise WorkerBoundaryError('WORKER_LOCKED_DISTRIBUTION_UNAVAILABLE') from exc
        if actual!=row['version']:raise WorkerBoundaryError('WORKER_LOCKED_VERSION_INCOMPATIBLE:'+row['name'])
        versions[row['name']]=actual
    normalize=lambda name:re.sub(r'[-_.]+','-',name).lower()
    installed={normalize(dist.metadata['Name']) for dist in importlib.metadata.distributions()}
    if installed-set(versions)-{'pip','setuptools','wheel','packaging'}:
        raise WorkerBoundaryError('WORKER_UNLOCKED_DISTRIBUTIONS_PRESENT')
    for name,version in expected['required_versions'].items():
        if versions.get(name)!=version:raise WorkerBoundaryError('WORKER_REQUIRED_FRAMEWORK_INCOMPATIBLE')
    return {'interpreter':platform.python_version(),'architecture':platform.machine(),
            'locked_distribution_count':len(versions),'required_versions':expected['required_versions']}
