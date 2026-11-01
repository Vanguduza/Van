"""Exact selected family-action semantics; no policy admission or native effects."""
from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from vati.lifecycle.family_actions import (
    EXPLICIT_LEGS_V1, FamilyActionError, FamilyLeg, FamilyPolicy, FamilySnapshot,
    NativeCloseRules, plan_reduction,
)

D = Decimal
BINDING = dict(original_mandate_ref="original-policy-event", current_mandate_ref="current-policy-event",
               grant_ref="current-grant", lease_ref="account-lease", fence_ref="account-fence")


def snapshot(*, root=".06", child=".05", root_rules=None, child_rules=None):
    rules = NativeCloseRules("native-close-grid", "native-contract", D(".01"), True, True)
    return FamilySnapshot("family", "original-family-revision", "account", "paper", "EURUSD", "LONG", (
        FamilyLeg("root-position", "root-intent", None if root is None else D(root), D(10), D(9), True,
                  ("root-command", "root-fill"), root_rules or rules),
        FamilyLeg("child-position", "child-intent", D(child), D(8), D(7), True,
                  ("child-command", "child-fill", "original-parent-ancestry"), child_rules or rules),
    ), ("original-family-membership",))


def quantities(plan):
    return {target.position_id: target.quantity for target in plan.targets}


def test_proportional_floor_retains_the_unmet_quantity_without_redistribution():
    with localcontext() as context:
        context.prec = 2
        plan = plan_reduction(snapshot(), policy=FamilyPolicy(), action="PARTIAL_CLOSE",
                              requested_quantity=D(".04"), authority_refs=BINDING)
    assert quantities(plan) == {"root-position": D(".02"), "child-position": D(".01")}
    assert plan.residual_quantity == D(".01")
    assert plan.reason == "UNALLOCATED_NATIVE_RESIDUAL"
    assert plan.policy.mode == "SHADOW" and plan.policy.qualification_ref is None


def test_each_native_grid_is_used_without_giving_another_leg_the_rounding_remainder():
    child = NativeCloseRules("child-native-grid", "child-contract", D(".001"), True, True)
    plan = plan_reduction(snapshot(child_rules=child), policy=FamilyPolicy(), action="PARTIAL_CLOSE",
                          requested_quantity=D(".009"), authority_refs=BINDING)
    assert quantities(plan) == {"root-position": D(0), "child-position": D(".004")}
    assert plan.residual_quantity == D(".005")


def test_full_close_keeps_original_odd_lots_instead_of_reusing_entry_minimums():
    rules = NativeCloseRules("native-full-close", "entry-minimum-is-not-close-minimum", D(".01"),
                             False, True, partial_min=D(".05"), full_close_odd_lot=True)
    plan = plan_reduction(snapshot(root=".035", child=".007", root_rules=rules, child_rules=rules),
                          policy=FamilyPolicy(version=EXPLICIT_LEGS_V1), action="FULL_CLOSE", authority_refs=BINDING)
    assert quantities(plan) == {"root-position": D(".035"), "child-position": D(".007")}
    assert plan.requested_quantity == D(".042") and plan.residual_quantity == 0


def test_native_remainder_constraint_reduces_the_target_never_rounds_to_full_close():
    rules = NativeCloseRules("native-close-constraint", "contract", D(".01"), True, True,
                             minimum_remaining=D(".02"))
    original = snapshot(root=".06", child="0", root_rules=rules)
    plan = plan_reduction(original, policy=FamilyPolicy(), action="PARTIAL_CLOSE",
                          requested_quantity=D(".05"), authority_refs=BINDING)
    assert quantities(plan)["root-position"] == D(".04")
    assert plan.residual_quantity == D(".01")


def test_unknown_quantity_or_ambiguous_membership_never_invents_an_allocation():
    for original in (snapshot(root=None), replace(snapshot(), ambiguous=True)):
        plan = plan_reduction(original, policy=FamilyPolicy(), action="PARTIAL_CLOSE",
                              requested_quantity=D(".04"), authority_refs=BINDING)
        assert all(target.quantity == 0 for target in plan.targets)
        assert plan.residual_quantity == D(".04")
        assert plan.reason == "ORIGINAL_MEMBERSHIP_OR_QUANTITY_UNRESOLVED"


def test_explicit_targets_are_not_rounded_or_replaced_by_foreign_positions():
    policy = FamilyPolicy(version=EXPLICIT_LEGS_V1)
    with pytest.raises(FamilyActionError, match="foreign or manual"):
        plan_reduction(snapshot(), policy=policy, action="PARTIAL_CLOSE",
                       explicit_targets={"manual-position": D(".01")}, authority_refs=BINDING)
    plan = plan_reduction(snapshot(), policy=policy, action="PARTIAL_CLOSE",
                          explicit_targets={"root-position": D(".015")}, authority_refs=BINDING)
    assert quantities(plan)["root-position"] == 0 and plan.residual_quantity == D(".015")
    with pytest.raises(FamilyActionError, match="aggregate request"):
        plan_reduction(snapshot(), policy=policy, action="PARTIAL_CLOSE", requested_quantity=D(".04"),
                       explicit_targets={"root-position": D(".02")}, authority_refs=BINDING)


def test_plan_identity_binds_the_original_snapshot_policy_and_current_authority():
    original = snapshot()
    plan = plan_reduction(original, policy=FamilyPolicy(), action="PARTIAL_CLOSE",
                          requested_quantity=D(".040"), authority_refs=BINDING)
    reordered = replace(original, legs=tuple(reversed(original.legs)))
    same = plan_reduction(reordered, policy=FamilyPolicy(), action="PARTIAL_CLOSE",
                          requested_quantity=D(".04"), authority_refs=BINDING)
    assert plan.digest == same.digest
    newer = plan_reduction(original, policy=FamilyPolicy(), action="PARTIAL_CLOSE", requested_quantity=D(".04"),
                           authority_refs={**BINDING, "fence_ref": "new-fence"})
    assert newer.digest != plan.digest
    with pytest.raises(FamilyActionError, match="lease/fence"):
        plan_reduction(original, policy=FamilyPolicy(), action="PARTIAL_CLOSE", requested_quantity=D(".04"),
                       authority_refs={**BINDING, "fence_ref": None})
