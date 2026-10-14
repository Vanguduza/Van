from __future__ import annotations
import pytest
from conftest_automation import make_store
from van_gateway.computer_use.fabric import ComputerInteractionFabric,ComputerUseError,OperationRequest,OperationState,OperationType,Surface
from van_gateway.computer_use.worker import ComputerWorkerResult,ComputerWorkerError
from van_gateway.models import ActionClass
from van_gateway.automation.health import AutomationHealthApi
from van_gateway.config import Settings
from van_gateway.degraded.registry import DegradedRegistry

def request():
 return OperationRequest(mission_id='m1',surface=Surface.TERMINAL,target_application='owner-workspace',operation_type=OperationType.WRITE_TEXT,action_class=ActionClass.A3,verifier_type='READ_BACK')
class Worker:
 async def status(self):return {'ready':True,'state':'READY'}
 async def execute(self,operation_id,request,lease):
  return ComputerWorkerResult(result={'operation_id':operation_id,'stdout':'output'},output_sha256='a'*64,exit_code=0)

@pytest.mark.asyncio
async def test_arbitrary_receipt_string_never_qualifies_completion(tmp_path):
 store=await make_store(tmp_path);f=ComputerInteractionFabric(store,workers=frozenset({Surface.TERMINAL}));op=await f.begin(request())
 with pytest.raises(ComputerUseError,match='OPERATION_NATIVE_RECEIPT_REQUIRED'):await f.complete(op,state=OperationState.COMPLETED,evidence_ref='computer-receipt://not-a-native-receipt')
 assert (await f.for_mission('m1'))[0]['state']=='PENDING'

@pytest.mark.asyncio
async def test_well_formed_but_nonexistent_receipt_refuses(tmp_path):
 store=await make_store(tmp_path);f=ComputerInteractionFabric(store,workers=frozenset({Surface.TERMINAL}));op=await f.begin(request())
 with pytest.raises(ComputerUseError,match='OPERATION_NATIVE_RECEIPT_UNVERIFIED'):await f.complete(op,state=OperationState.COMPLETED,evidence_ref='computer-receipt://cwr_'+'0'*32)

@pytest.mark.asyncio
async def test_receipt_from_another_operation_does_not_complete_current_work(tmp_path):
 store=await make_store(tmp_path);f=ComputerInteractionFabric(store,worker_impls={Surface.TERMINAL:Worker()});first=await f.execute_operation(request());other=await f.begin(request())
 with pytest.raises(ComputerUseError,match='OPERATION_NATIVE_RECEIPT_UNVERIFIED'):await f.complete(other,state=OperationState.COMPLETED,evidence_ref=first['evidence_ref'])
 assert (await f.for_mission('m1'))[1]['state']=='PENDING'

@pytest.mark.asyncio
async def test_invalid_worker_output_receipt_retains_unknown_mutation(tmp_path):
 class InvalidWorker(Worker):
  async def execute(self,operation_id,request,lease):return ComputerWorkerResult(result={'partial':True},output_sha256='not-a-digest',exit_code=0)
 store=await make_store(tmp_path);f=ComputerInteractionFabric(store,worker_impls={Surface.TERMINAL:InvalidWorker()})
 with pytest.raises(ComputerUseError,match='OPERATION_WORKER_FAILED'):await f.execute_operation(request())
 assert (await f.for_mission('m1'))[0]['state']=='OUTCOME_UNKNOWN'

@pytest.mark.asyncio
async def test_post_effect_worker_failure_is_unknown(tmp_path):
 class FailedWorker(Worker):
  async def execute(self,*args):raise ComputerWorkerError('COMPUTER_OPERATION_FAILED')
 store=await make_store(tmp_path);f=ComputerInteractionFabric(store,worker_impls={Surface.TERMINAL:FailedWorker()})
 with pytest.raises(ComputerUseError,match='COMPUTER_OPERATION_FAILED'):await f.execute_operation(request())
 assert (await f.for_mission('m1'))[0]['state']=='OUTCOME_UNKNOWN'

@pytest.mark.asyncio
async def test_health_uses_the_actual_injected_worker_readiness(tmp_path):
 class ColdWorker(Worker):
  async def status(self):return {'ready':False,'state':'UNQUALIFIED'}
 store=await make_store(tmp_path);fabric=ComputerInteractionFabric(store,worker_impls={Surface.TERMINAL:ColdWorker()})
 health=AutomationHealthApi(store,Settings(),degraded=DegradedRegistry(),computer_use=fabric)
 report=await health.computer_use_health()
 assert report['registered_surfaces']['TERMINAL'] is True
 assert report['surfaces']['TERMINAL'] is False
 assert report['worker_status']['TERMINAL']['state']=='UNQUALIFIED'
 assert health.computer_use is fabric


@pytest.mark.asyncio
async def test_loaded_code_identity_is_separate_from_checkout_and_source_bytes(tmp_path):
 store=await make_store(tmp_path);fabric=ComputerInteractionFabric(store)
 health=AutomationHealthApi(store,Settings(),degraded=DegradedRegistry(),computer_use=fabric)
 first=health.computer_source_identity()
 assert first['checked_out']['state']=='OBSERVED'
 assert first['checked_out']['dirty'] is True
 assert first['qualified_source'] is None
 async def replacement(request):return {}
 fabric.execute_operation=replacement
 second=health.computer_source_identity()
 assert first['loaded_methods']['fabric.execute_operation']['loaded_code_sha256']!=second['loaded_methods']['fabric.execute_operation']['loaded_code_sha256']
 assert first['checked_out']['commit']==second['checked_out']['commit']
 assert second['qualified_source'] is None
