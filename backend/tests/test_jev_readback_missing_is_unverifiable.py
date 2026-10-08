"""Reviewer I M-6 — a Jev read-back that reports nothing is UNVERIFIABLE, never VERIFIED.

Probe review-i/probes/jevreadback.py: with ``status() == {}`` the observation defaulted
``projects[project_id]`` and ``owner_active`` to True and ``bypassed`` to False, so an
"enable" command was VERIFIED by a Jev that said nothing.
"""

from __future__ import annotations

import pytest

from van_gateway.command.success_contracts import JEV_READBACK, SuccessContract
from van_gateway.mission.verifiers import ObservationVerifier
from van_gateway.verification.production import _jev_readback_observation


class _Jev:
    def __init__(self, status=None, module=None):
        self._status = {} if status is None else status
        self._module = {} if module is None else module

    async def status(self):
        return self._status

    async def module(self, module_id):
        return self._module


async def _verify(jev, postconditions):
    verifier = ObservationVerifier(
        _jev_readback_observation(jev), verifier_version="jev-readback/1", evidence_prefix="jev://",
    )
    record = await verifier.verify(
        SuccessContract(verifier_class=JEV_READBACK, postconditions=postconditions, evidence_required=True),
        {"now_ms": 1},
    )
    return record.status.value


ENABLE = {"kind": "global", "project_id": None, "owner_active": True, "bypassed": False}
PROJECT = {"kind": "global", "project_id": "proj-x", "project_enabled": True}
DISABLE = {"kind": "global", "project_id": None, "owner_active": False}
MODULE = {"kind": "module", "module_id": "m1", "status": "ACTIVE"}


@pytest.mark.parametrize("status", [
    {},
    {"global": {}},
    {"global": None},
    {"global": {"owner_active": True}},             # bypassed unreported
    {"global": {"bypassed": False}},                # owner_active unreported
    {"global": {"owner_active": "true", "bypassed": False}},  # not a bool
])
async def test_global_enable_unreported_is_unverifiable(status):
    assert await _verify(_Jev(status), ENABLE) == "UNVERIFIABLE"


@pytest.mark.parametrize("status", [
    {}, {"global": {}}, {"global": {"projects": {}}}, {"global": {"projects": {"other": True}}},
    {"global": {"projects": {"proj-x": 1}}},
])
async def test_project_enable_unreported_is_unverifiable(status):
    assert await _verify(_Jev(status), PROJECT) == "UNVERIFIABLE"


async def test_global_disable_unreported_is_unverifiable():
    assert await _verify(_Jev({}), DISABLE) == "UNVERIFIABLE"


@pytest.mark.parametrize("module", [{}, {"status": None}, {"status": ""}])
async def test_module_status_unreported_is_unverifiable(module):
    assert await _verify(_Jev(module=module), MODULE) == "UNVERIFIABLE"


@pytest.mark.parametrize(("status", "postconditions", "outcome"), [
    ({"global": {"owner_active": True, "bypassed": False}}, ENABLE, "VERIFIED"),
    ({"global": {"owner_active": True, "bypassed": True}}, ENABLE, "FAILED"),
    ({"global": {"owner_active": False}}, DISABLE, "VERIFIED"),
    ({"global": {"owner_active": True}}, DISABLE, "FAILED"),
    ({"global": {"projects": {"proj-x": True}}}, PROJECT, "VERIFIED"),
    ({"global": {"projects": {"proj-x": False}}}, PROJECT, "FAILED"),
])
async def test_reported_state_is_still_judged(status, postconditions, outcome):
    assert await _verify(_Jev(status), postconditions) == outcome


async def test_reported_module_status_is_still_judged():
    assert await _verify(_Jev(module={"status": "ACTIVE"}), MODULE) == "VERIFIED"
    assert await _verify(_Jev(module={"status": "SHADOW"}), MODULE) == "FAILED"
