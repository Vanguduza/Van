"""Reviewer I2 issue (a) — a run is owner success only with BOTH verdicts.

review-i2/probes/dispatch_corr.py showed two defects in ``AutomationDispatcher.dispatch``:

1. The run status came from ``verification.outcome`` alone while the Action Runtime judged
   correlation separately, so ``owner_success=True`` sat beside an execution recorded
   ``VERIFICATION_FAILED``.
2. On the field/expected path the verifier returned no correlation, the dispatcher merged in
   the engine's own ``{"n8n_execution_id": ...}``, and the Action Runtime compared the engine's
   id with itself.

Now the run is ``VERIFIED_SUCCESS`` only when the verifier says VERIFIED *and* the action
receipt says VERIFIED_SUCCESS, and the engine correlation is matched only against a value
the independent observer reported.
"""

from __future__ import annotations

import pytest

from test_automation_dispatch import ACTION_ID, _build, _Observer
from van_gateway.action.models import ExecutionStatus, PrincipalType
from van_gateway.automation.models import RunStatus
from van_gateway.automation.verifier import PostconditionSpec, VerificationOutcome

ENGINE_ID = "n8n-exec-9"  # what the fake n8n webhook returns as executionId


async def _dispatch(tmp_path, observed: dict, spec: PostconditionSpec):
    store, dispatcher = await _build(tmp_path, observer=_Observer(observed))
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={"broker_alias": "primary_mt5"},
        postcondition=spec,
    )
    receipt = await store.fetchone(
        "SELECT status, correlation_json FROM action_receipts WHERE execution_id = ?",
        (result.execution.execution_id,),
    )
    run = await store.fetchone("SELECT status FROM automation_runs WHERE run_id = ?", (result.run_id,))
    return result, receipt, run


FIELD = PostconditionSpec(kind="READ_BACK", field="state", expected="DELIVERED")


async def test_engine_id_is_never_compared_with_itself(tmp_path):
    """Probe row 2: field/expected passes, the observer says nothing about the engine run."""
    result, receipt, run = await _dispatch(tmp_path, {"exists": True, "state": "DELIVERED"}, FIELD)
    assert result.verification_outcome is VerificationOutcome.VERIFIED
    assert result.owner_success is False
    assert result.status is RunStatus.PARTIAL_SUCCESS
    assert run["status"] == RunStatus.PARTIAL_SUCCESS.value
    assert receipt["status"] == ExecutionStatus.PARTIAL_SUCCESS.value
    # Nothing the engine said was written into the receipt as if it had been observed.
    assert ENGINE_ID not in (receipt["correlation_json"] or "")
    assert result.detail["verifier_detail"] == "ENGINE_CORRELATION_UNOBSERVED:n8n_execution_id"


async def test_an_observed_foreign_engine_id_fails_the_run(tmp_path):
    """Probe row 3: the observed effect belongs to another execution."""
    result, receipt, _run = await _dispatch(
        tmp_path, {"exists": True, "state": "DELIVERED", "n8n_execution_id": "WRONG"}, FIELD,
    )
    assert result.verification_outcome is VerificationOutcome.VERIFIED
    assert receipt["status"] == ExecutionStatus.VERIFICATION_FAILED.value
    assert result.status is RunStatus.FAILED
    assert result.owner_success is False
    assert result.execution.status is ExecutionStatus.VERIFICATION_FAILED
    assert result.detail["verifier_detail"] == "ENGINE_CORRELATION_MISMATCH"


async def test_caller_correlation_verified_but_engine_unobserved_is_not_success(tmp_path):
    """Probe row 1 (with the N-1 declared value): VERIFIED alone is not owner success."""
    spec = PostconditionSpec(
        kind="READ_BACK", correlation_keys=["evidence_pointer"],
        expected_correlation={"evidence_pointer": "gateway://evidence/1"},
    )
    result, receipt, _run = await _dispatch(
        tmp_path, {"exists": True, "evidence_pointer": "gateway://evidence/1"}, spec,
    )
    assert result.verification_outcome is VerificationOutcome.VERIFIED
    assert result.owner_success is False
    assert result.status is not RunStatus.VERIFIED_SUCCESS
    assert receipt["status"] != ExecutionStatus.VERIFIED_SUCCESS.value


@pytest.mark.parametrize("spec", [
    FIELD,
    PostconditionSpec(kind="READ_BACK", correlation_keys=["evidence_pointer"],
                      expected_correlation={"evidence_pointer": "gateway://evidence/1"}),
], ids=["field", "correlation"])
async def test_both_verdicts_agree_on_success(tmp_path, spec):
    result, receipt, run = await _dispatch(tmp_path, {
        "exists": True, "state": "DELIVERED", "evidence_pointer": "gateway://evidence/1",
        "n8n_execution_id": ENGINE_ID,
    }, spec)
    assert result.status is RunStatus.VERIFIED_SUCCESS
    assert result.owner_success is True
    assert receipt["status"] == ExecutionStatus.VERIFIED_SUCCESS.value
    assert run["status"] == RunStatus.VERIFIED_SUCCESS.value
    assert result.execution.status is ExecutionStatus.VERIFIED_SUCCESS


async def test_owner_success_never_sits_beside_a_failed_execution(tmp_path):
    """The invariant, over every probe observation."""
    cases = [
        ({"exists": True, "state": "DELIVERED"}, FIELD),
        ({"exists": True, "state": "DELIVERED", "n8n_execution_id": "WRONG"}, FIELD),
        ({"exists": True, "evidence_pointer": "gateway://evidence/1"},
         PostconditionSpec(kind="READ_BACK", correlation_keys=["evidence_pointer"],
                           expected_correlation={"evidence_pointer": "gateway://evidence/1"})),
        ({"exists": True, "state": "DELIVERED", "n8n_execution_id": ENGINE_ID}, FIELD),
    ]
    for index, (observed, spec) in enumerate(cases):
        run_dir = tmp_path / f"c{index}"
        run_dir.mkdir()
        result, receipt, _run = await _dispatch(run_dir, observed, spec)
        assert result.owner_success == (receipt["status"] == ExecutionStatus.VERIFIED_SUCCESS.value), index
        assert result.owner_success == (result.execution.status is ExecutionStatus.VERIFIED_SUCCESS), index
