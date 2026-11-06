"""Admitted worker effects must satisfy the exact typed owner and step predicates.

The dispatch verifier observes run correlation. Its strict comparison cannot repair
an IR predicate that WorkerWorkflowObserver already accepted using Python's numeric
coercion, so exercise the real callback/effect/readback path for both IR locations.
"""
import pytest

from test_automation_worker_runtime import admitted, build, monitor_steps, step, verified_result
from van_gateway.automation.models import Primitive
from van_gateway.automation.verifier import VerificationOutcome


@pytest.mark.parametrize("predicate_scope", ["owner", "step"])
@pytest.mark.parametrize("effect,expected,matches", [
    pytest.param("event", 1, False, id="boolean-is-not-integer"),
    pytest.param("event", True, True, id="exact-boolean"),
    pytest.param("wait", True, False, id="integer-is-not-boolean"),
    pytest.param("wait", 1.0, False, id="integer-is-not-float"),
    pytest.param("wait", 1, True, id="exact-integer"),
    pytest.param("merge", {"items": [{"count": True}]}, False, id="nested-boolean-is-not-integer"),
    pytest.param("merge", {"items": [{"count": 1.0}]}, False, id="nested-integer-is-not-float"),
    pytest.param("merge", {"items": [{"count": 1}]}, True, id="exact-nested-integer"),
])
async def test_real_worker_effect_respects_typed_declared_predicate(tmp_path, predicate_scope, effect, expected, matches):
    if effect == "event":
        steps, inputs, field = monitor_steps(), {"document": {"version": "A"}}, "emitted"
    elif effect == "wait":
        steps, inputs, field = [step("wait", Primitive.WAIT, "bounded_wait", {"delay_ms": 1})], {}, "waited_ms"
    else:
        steps = [step("merge", Primitive.MERGE, "merge_objects", {"sources": [{"items": [{"count": 1}]}]})]
        inputs, field = {}, "payload"
    predicate = {"kind": "READ_BACK", "field": field, "expected": expected}
    if predicate_scope == "step":
        steps[-1].postcondition = predicate
    worker, store, body = await build(tmp_path, steps=steps, inputs=inputs,
        declared_verifier=predicate if predicate_scope == "owner" else {"kind": "READ_BACK"})
    await admitted(worker, body)
    if effect == "event":
        staged = await worker.execute(await body("detect", {"payload": inputs["document"]}))
        receipt = await worker.execute(await body("emit", {"payload": staged["result"], "event_type": "source.changed"}))
        events = await store.fetchall("SELECT * FROM events WHERE event_type='automation.external_event'")
        assert len(events) == 1 and receipt["result"][field] is True
    elif effect == "wait":
        receipt = await worker.execute(await body("wait", {"delay_ms": 1}))
        assert type(receipt["result"][field]) is int and receipt["result"][field] == 1
    else:
        receipt = await worker.execute(await body("merge", {"sources": [{"items": [{"count": 1}]}]}))
        assert type(receipt["result"][field]["items"][0]["count"]) is int
    observed = await verified_result(worker, inputs)
    assert observed.outcome is (VerificationOutcome.VERIFIED if matches else VerificationOutcome.FAILED)
    if not matches:
        assert observed.observed["reason"] == (
            "OWNER_POSTCONDITION_MISMATCH" if predicate_scope == "owner" else "DECLARED_FIELD_MISMATCH")
