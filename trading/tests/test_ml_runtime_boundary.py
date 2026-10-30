"""The actual T0 serve entrypoint must not load model frameworks."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('module',['qlib','lightgbm','neuralforecast','xgboost','optuna','feast','mlflow','torch','pyarrow'])
def test_actual_serve_entrypoint_refuses_model_import_before_model_code_executes(tmp_path,module):
    marker=tmp_path/'model-executed'
    fake=tmp_path/'packages';package=fake/module;package.mkdir(parents=True)
    (package/'__init__.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\n')
    code='''
from argparse import Namespace
import importlib,json,sys
from vati.__main__ import cmd_serve
try:cmd_serve(Namespace(config=sys.argv[1],once=True))
except FileNotFoundError:pass
try:
 importlib.import_module(sys.argv[2]);blocked=False
except ImportError:blocked=True
print(json.dumps({'blocked':blocked}))
'''
    env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(fake),str(Path(__file__).resolve().parents[1])]))
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path/'absent-profile.json'),module],
        env=env,capture_output=True,text=True,timeout=30)
    assert child.returncode==0,child.stderr
    assert json.loads(child.stdout.splitlines()[-1])['blocked'] is True
    assert not marker.exists(),'model module code executed inside the actual T0 serve process'


def test_serve_refuses_a_preloaded_model_before_loading_account_configuration(tmp_path):
    code='''
from argparse import Namespace
import json,sys,types
sys.modules['torch']=types.ModuleType('torch')
from vati.__main__ import cmd_serve
try:result=cmd_serve(Namespace(config=sys.argv[1],once=True))
except FileNotFoundError:result='CONFIGURATION_WAS_READ'
print(json.dumps({'result':result}))
'''
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path/'absent-profile.json')],
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,text=True,timeout=30)
    assert child.returncode==0,child.stderr
    assert json.loads(child.stdout.splitlines()[-1])['result']==2
    assert 'T0_MODEL_BOUNDARY_UNAVAILABLE' in child.stdout
