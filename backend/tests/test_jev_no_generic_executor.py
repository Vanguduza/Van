"""Programme B — Jev may rank/annotate typed fabric operations; it is never an executor.

The ComputerInteractionFabric has no EXECUTE primitive (§38). These tests fail if one becomes
reachable from Jev output: through the Jev client surface, through the interaction router,
or through fabric ranking.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from van_gateway.browser.interaction_router import (
    B1ValidationError, InteractionStep, validate_b1_payload, validate_jev_proposal,
)
from van_gateway.computer_use.annotations import FabricAnnotation, annotate_fabric_operations

JEV_CLOSED_OPERATIONS = frozenset(InteractionStep.__dataclass_fields__["closed_operation_set"].default)
from van_gateway.computer_use.fabric import OperationType
from van_gateway.jev.advisor import JevVanAdvisor
from van_gateway.jev.client import JevProjectionClient

JEV_PKG = Path(__file__).resolve().parents[2] / "backend" / "van_gateway" / "jev"
EXECUTOR_VERBS = ("execute", "run", "act", "actuate", "click", "navigate", "eval", "begin", "dispatch")
EXECUTOR_MODULES = (
    "van_gateway.computer_use", "van_gateway.browser", "van_gateway.command",
    "van_gateway.automation", "vati", "van_gateway.trading",
)


def test_jev_package_imports_no_executor_module():
    for path in JEV_PKG.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(EXECUTOR_MODULES), (path.name, node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(EXECUTOR_MODULES), (path.name, alias.name)


@pytest.mark.parametrize("cls", [JevVanAdvisor, JevProjectionClient])
def test_jev_clients_expose_no_execution_primitive(cls):
    public = [name for name, _ in inspect.getmembers(cls) if not name.startswith("_")]
    assert not [n for n in public if n.split("_")[0] in EXECUTOR_VERBS], public


def test_the_fabric_itself_still_has_no_generic_primitive():
    assert not {"EXECUTE", "RUN_ARBITRARY", "EVAL", "SHELL"} & {op.value for op in OperationType}


REQUEST = validate_b1_payload(
    {
        "payload_schema": "van.browser.action_payload.v1",
        "effect_direction": "PROPOSE_ACTION",
        "closed_operation_set": sorted(JEV_CLOSED_OPERATIONS),
        "origin_class": "PUBLIC_ALLOWLISTED",
        "targets": [{"target_id": "t_00000000000000a1", "role": "button", "label": "Go"}],
        "action_class_ceiling": "A3",
        "observation_epoch": "ep",
    },
    ceiling="A3", closed_operation_set=tuple(JEV_CLOSED_OPERATIONS),
)

@pytest.mark.parametrize(
    "operation",
    sorted({op.value for op in OperationType} | {op.value.lower() for op in OperationType}
           | {"execute", "eval", "run", "shell", "EXECUTE", "RUN_ARBITRARY"}),
)
def test_no_fabric_or_generic_operation_survives_the_b1_validator(operation):
    if operation in JEV_CLOSED_OPERATIONS:
        pytest.skip("member of the B1 closed set by definition")
    with pytest.raises(B1ValidationError, match="OPERATION_NOT_IN_CLOSED_SET"):
        validate_jev_proposal(
            proposal={"operation": operation, "target_id": "t_00000000000000a1", "value_ref": None},
            request=REQUEST, current_epoch="ep",
            classify=lambda *_: pytest.fail("off-contract operation reached classification"),
        )


def test_fabric_ranking_is_data_over_caller_candidates_only():
    ranked = annotate_fabric_operations(
        ["op_read", "op_click"],
        {"ranking": [{"candidate_id": "op_click", "note": "likely next"}, {"candidate_id": "op_read"}]},
    )
    assert [a.candidate_id for a in ranked] == ["op_click", "op_read"]
    assert {f.name for f in dataclasses.fields(FabricAnnotation)} == {"candidate_id", "rank", "note"}
    assert not any(callable(getattr(a, name, None)) for a in ranked for name in EXECUTOR_VERBS)


@pytest.mark.parametrize("response", [
    {"ranking": [{"candidate_id": "op_new", "operation_type": "EXECUTE"}]},
    {"ranking": [{"candidate_id": "op_x"}]},
    {"ranking": [{"candidate_id": "op_read", "operation_type": "RUN_PYTHON_FILE"}]},
    {"ranking": [{"candidate_id": "op_read"}], "execute": {"command": "rm -rf /"}},
    {"ranking": "op_click"},
    {"ranking": [{"candidate_id": {"not": "an identifier"}}]},
    {"ranking": [{"candidate_id": ["op_read"]}]},
    {"ranking": [{"candidate_id": "op_read"}, {"candidate_id": "op_read"}]},
    None,
])
def test_off_contract_ranking_cannot_add_or_execute_and_leaves_caller_order(response):
    ranked = annotate_fabric_operations(["op_read", "op_click"], response)
    assert [(a.candidate_id, a.note) for a in ranked] == [("op_read", None), ("op_click", None)]
