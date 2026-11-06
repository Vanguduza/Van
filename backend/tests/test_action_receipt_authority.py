"""Verification receipts require submitted work and independent observations."""
import pytest
from test_owner_runtime import runtime
from van_gateway.action.models import ActionDefinition,ExecutionStatus,VerificationObservation,VerifierType
from van_gateway.action.service import ActionPolicyError
from van_gateway.models import ActionClass,PrincipalType

async def _begin(actions, *, action_class=ActionClass.A3, owner_approved=False):
    await actions.register(ActionDefinition(action_id='test.readback',action_class=action_class,
                                            mutates_state=True,verifier_type=VerifierType.READ_BACK))
    return await actions.begin(execution_id='exec-probe',command_id='cmd-probe',turn_id=None,
                               action_id='test.readback',principal_type=PrincipalType.OWNER_DEVICE,
                               requested_by='device:test',idempotency_key='idem-probe',parameters={},
                               snapshot_id=None,owner_approved=owner_approved)

def _observation(**changes):
    return VerificationObservation(execution_id='exec-probe',success=changes.get('success',True),
                                    correlation=changes.get('correlation',{'object_id':'verified-object'}),
                                    observed_postcondition=changes.get('postcondition',{'exists':True}),
                                    evidence_pointer=changes.get('evidence','readback://test-object'))

@pytest.mark.asyncio
async def test_worker_supplied_matching_correlation_cannot_mint_verified_success(runtime):
    store,_context,actions=runtime
    execution=await _begin(actions)
    await actions.mark_submitted(execution.execution_id,correlation={'object_id':'verified-object'})
    receipt=await actions.verify(_observation())
    assert receipt.status is ExecutionStatus.UNVERIFIABLE
    assert (await actions.get_execution(execution.execution_id)).status is ExecutionStatus.UNVERIFIABLE

@pytest.mark.asyncio
@pytest.mark.parametrize('missing',['postcondition','evidence'])
async def test_mutating_success_requires_postcondition_and_evidence(runtime,missing):
    _store,_context,actions=runtime
    execution=await _begin(actions)
    await actions.mark_submitted(execution.execution_id,correlation={'object_id':'verified-object'})
    changes={'postcondition':{}} if missing=='postcondition' else {'evidence':None}
    receipt=await actions.verify(_observation(**changes),independent_observer=True)
    assert receipt.status is ExecutionStatus.UNVERIFIABLE

@pytest.mark.asyncio
async def test_authorized_work_cannot_be_verified_before_submission(runtime):
    _store,_context,actions=runtime
    await _begin(actions)
    with pytest.raises(ActionPolicyError,match='execution_not_submitted'):
        await actions.verify(_observation(),independent_observer=True)

@pytest.mark.asyncio
async def test_owner_approval_required_cannot_be_overwritten_by_verification(runtime):
    _store,_context,actions=runtime
    execution=await _begin(actions,action_class=ActionClass.A4)
    assert execution.status is ExecutionStatus.AUTHORIZATION_REQUIRED
    with pytest.raises(ActionPolicyError,match='execution_terminal'):
        await actions.verify(_observation(),independent_observer=True)
    assert (await actions.get_execution(execution.execution_id)).status is ExecutionStatus.AUTHORIZATION_REQUIRED

@pytest.mark.asyncio
async def test_verified_terminal_receipt_is_immutable_and_duplicate_is_idempotent(runtime):
    store,_context,actions=runtime
    execution=await _begin(actions)
    await actions.mark_submitted(execution.execution_id,correlation={'object_id':'verified-object'})
    receipt=await actions.verify(_observation(),independent_observer=True)
    assert receipt.status is ExecutionStatus.VERIFIED_SUCCESS
    assert await actions.verify(_observation(),independent_observer=True)==receipt
    with pytest.raises(ActionPolicyError,match='terminal_verification_conflict'):
        await actions.verify(_observation(success=False),independent_observer=True)
    assert (await actions.get_execution(execution.execution_id)).status is ExecutionStatus.VERIFIED_SUCCESS
    assert len(await store.fetchall('SELECT receipt_id FROM action_receipts'))==1
