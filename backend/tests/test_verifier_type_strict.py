"""Review I3 MINOR-5 — verifier comparisons were not type-strict.

review-i3/probes/corr_types.py: expected ``True`` vs observed ``1``, expected ``1`` vs observed
``1.0``, and expected ``""`` on a blank page all came back VERIFIED.
"""

from __future__ import annotations

import pytest

from van_gateway.action.models import VerifierType
from van_gateway.automation.verifier import (
    PostconditionSpec,
    VerificationOutcome,
    WorkflowVerifier,
    strictly_equal,
)

OBS = {"exists": True, "url": "https://docs.example.com/x", "title": "Report", "visible_text": "",
       "flag": 1, "n": 1.0, "count": 3, "ok": True, "items": [1, 2], "meta": {"a": 1}}


class _Observer:
    async def observe(self, spec, ctx):
        return dict(OBS)


async def _verify(**kw):
    spec = PostconditionSpec(kind="READ_BACK", **kw)
    return await WorkflowVerifier({"READ_BACK": _Observer()}).verify(
        spec=spec, verifier_type=VerifierType.READ_BACK, engine_reported_success=True)


TYPE_CONFUSIONS = [
    pytest.param("flag", True, id="bool-vs-int"),
    pytest.param("n", 1, id="int-vs-float"),
    pytest.param("count", 3.0, id="float-vs-int"),
    pytest.param("ok", 1, id="int-vs-bool"),
    pytest.param("count", "3", id="str-vs-int"),
    pytest.param("items", [True, 2], id="bool-inside-list"),
    pytest.param("meta", {"a": 1.0}, id="float-inside-dict"),
]


@pytest.mark.parametrize("key,expected", TYPE_CONFUSIONS)
async def test_correlation_is_type_strict(key, expected):
    result = await _verify(expected_correlation={key: expected})
    assert result.outcome is VerificationOutcome.FAILED
    assert result.detail == f"correlation mismatch: ['{key}']"


@pytest.mark.parametrize("key,expected", TYPE_CONFUSIONS)
async def test_field_expected_is_type_strict(key, expected):
    result = await _verify(field=key, expected=expected)
    assert result.outcome is VerificationOutcome.FAILED
    assert result.detail == f"{key} mismatch"


@pytest.mark.parametrize("key,expected", [("ok", True), ("count", 3), ("n", 1.0), ("items", [1, 2]),
                                          ("meta", {"a": 1}), ("title", "Report")])
async def test_same_type_same_value_still_verifies(key, expected):
    assert (await _verify(expected_correlation={key: expected})).outcome is VerificationOutcome.VERIFIED
    assert (await _verify(field=key, expected=expected)).outcome is VerificationOutcome.VERIFIED


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
async def test_blank_expected_string_is_refused_not_verified(blank):
    for kw in ({"expected_correlation": {"visible_text": blank}}, {"field": "visible_text", "expected": blank}):
        result = await _verify(**kw)
        assert result.outcome is VerificationOutcome.UNVERIFIABLE, kw
        assert "declares no predicate" in (result.detail or "")


async def test_a_blank_expected_cannot_ride_along_with_a_real_predicate():
    result = await _verify(field="visible_text", expected="", expected_correlation={"title": "Report"})
    assert result.outcome is VerificationOutcome.UNVERIFIABLE


def test_strictly_equal_rejects_numeric_tower_aliases():
    assert not strictly_equal(True, 1) and not strictly_equal(1, 1.0) and not strictly_equal(0, False)
    assert strictly_equal("a", "a") and strictly_equal([1, {"b": True}], [1, {"b": True}])
