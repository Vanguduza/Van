"""Worker environments cannot inherit credentials or claim unenforced budgets."""
import json

import pytest

from vati_forecast_worker.policy import (
    WorkerBoundaryError,WorkerBudget,fixture_environment,require_fixture_environment,require_kernel_limits,
)


def test_fixed_worker_environment_excludes_all_host_variables(monkeypatch):
    monkeypatch.setenv('CUSTOM_OWNER_CREDENTIAL','fixture-secret-never-forward')
    monkeypatch.setenv('CTRADER_ACCESS_TOKEN','fixture-native-token')
    env=fixture_environment('RESEARCH_FIXTURE_SMOKE')
    assert 'CUSTOM_OWNER_CREDENTIAL' not in env and 'CTRADER_ACCESS_TOKEN' not in env
    assert 'fixture-secret-never-forward' not in json.dumps(env)
    assert all(env[name]=='' for name in ('HTTP_PROXY','HTTPS_PROXY','GPG_KEY'))


@pytest.mark.parametrize('name',['CUSTOM_OWNER_CREDENTIAL','CTRADER_ACCESS_TOKEN','GITHUB_TOKEN','AWS_SECRET_ACCESS_KEY'])
def test_unexpected_environment_refuses_without_echoing_credentials(name):
    env=fixture_environment('RESEARCH_FIXTURE_SMOKE') | {name:'fixture-secret-never-echo'}
    with pytest.raises(WorkerBoundaryError) as error:require_fixture_environment(env)
    assert 'fixture-secret-never-echo' not in str(error.value)


def test_worker_role_is_only_a_fixture_label_not_execution_authority():
    env=fixture_environment('INFERENCE_FIXTURE_SMOKE')
    result=require_fixture_environment(env)
    assert result['data_environment']=='FIXTURE' and result['execution_authority'] is False
    with pytest.raises(WorkerBoundaryError):fixture_environment('LIVE_TRADER')
    with pytest.raises(TypeError):WorkerBudget(execution_authority=True)


@pytest.mark.parametrize('value',[True,0,-1,2**63])
def test_worker_budget_requires_bounded_integer_values(value):
    with pytest.raises(WorkerBoundaryError):WorkerBudget(pids=value)


@pytest.mark.parametrize('change',[{'cpu.max':'max 100000'},{'cpu.max':'300000 100000'},
    {'memory.max':'max'},{'memory.max':str(7*1024**3)},{'pids.max':'max'},{'pids.max':'257'},
    {'cpu.max':'0 100000'},{'cpu.max':'200000 0'}])
def test_worker_cannot_claim_isolation_from_configuration_strings_alone(change):
    observed={'cpu.max':'200000 100000','memory.max':str(6*1024**3),'pids.max':'256'} | change
    with pytest.raises(WorkerBoundaryError):require_kernel_limits(WorkerBudget(),observed)


def test_actual_observed_budget_snapshot_is_returned_independently():
    observed={'cpu.max':'200000 100000','memory.max':str(6*1024**3),'pids.max':'256'}
    result=require_kernel_limits(WorkerBudget(),observed);result['pids.max']='max'
    assert observed['pids.max']=='256'


@pytest.mark.parametrize('identity',[('machine','aarch64'),('system','Darwin'),
    ('python_version','3.11.1'),('python_implementation','PyPy')])
def test_unsupported_interpreter_or_architecture_refuses_before_model_imports(monkeypatch,identity):
    from vati_forecast_worker import policy
    # These are refusal controls, not evidence of an executed ARM/macOS worker.
    for name,value in {'machine':'x86_64','system':'Linux','python_version':'3.12.15',
            'python_implementation':'CPython'}.items():
        monkeypatch.setattr(policy.platform,name,lambda value=value:value)
    monkeypatch.setattr(policy.platform,identity[0],lambda:identity[1])
    with pytest.raises(WorkerBoundaryError,match='INTERPRETER_OR_ARCHITECTURE_INCOMPATIBLE'):
        policy.require_locked_environment()
