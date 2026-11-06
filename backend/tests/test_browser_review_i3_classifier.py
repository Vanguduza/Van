"""Review I3 MAJOR-2 — the shared action classifier missed payment signals and pay-button spellings.

Reviewer I3's probes (review-i3/probes/classify_variants.py, ccfill_router.py,
paynow_router.py) showed every item below classified A2/A3 and executed:

* ``autocomplete`` cc-number / cc-csc / cc-exp, top-level and under ``attributes`` (the
  key was not in the observed text at all);
* ``name=cardnumber``, ``#ccnum``, "Kartennummer", ``#cardnum``;
* ``#paynow``, ``#buynow``, ``#placeorder``, ``button.submitorder``,
  ``[data-testid=checkoutbutton]``, ``#confirmpurchase`` (word-bounded patterns only);
* "Pa<ZWSP>y now", "P<Cyrillic а>y now", fullwidth "Ｐａｙ now" (no normalisation).

The live Harness reports no element list, so router lane 1 classifies on the locator's
words alone: the locator-only cases are checked through the router with an empty resolver.
"""

from __future__ import annotations

import pytest

import test_browser_interaction_router as tr
from van_gateway.automation.verifier import PostconditionSpec
from van_gateway.browser.interaction_router import (
    DeterministicAction,
    RouterAction,
    RouterLane,
    StepState,
    default_action_classifier,
    observed_element_text,
)
from van_gateway.models import ActionClass


def _class(operation: str, element: dict, locator: str) -> str:
    return default_action_classifier(operation, {"label": observed_element_text(element, locator)}, None)


# ------------------------------------------------------------------ Harness-observed elements

CARD_FIELDS = [
    pytest.param({"ref": "#f", "role": "textbox", "label": "Number", "autocomplete": "cc-number"}, "#f", id="autocomplete=cc-number"),
    pytest.param({"ref": "#f", "role": "textbox", "label": "Code", "autocomplete": "cc-csc"}, "#f", id="autocomplete=cc-csc"),
    pytest.param({"ref": "#f", "role": "textbox", "label": "MM / YY", "autocomplete": "cc-exp"}, "#f", id="autocomplete=cc-exp"),
    pytest.param({"ref": "#f", "role": "textbox", "label": "Number", "attributes": {"autocomplete": "cc-number"}}, "#f", id="attributes.autocomplete=cc-number"),
    pytest.param({"ref": "#f", "role": "textbox", "label": "Code", "attributes": {"autocomplete": "cc-csc"}}, "#f", id="attributes.autocomplete=cc-csc"),
    pytest.param({"ref": "#f", "role": "textbox", "label": "MM / YY", "attributes": {"autocomplete": "cc-exp"}}, "#f", id="attributes.autocomplete=cc-exp"),
    pytest.param({"ref": "input[name=cardnumber]", "role": "textbox", "label": "Number", "name": "cardnumber"}, "input[name=cardnumber]", id="name=cardnumber"),
    pytest.param({"ref": "#ccnum", "role": "textbox", "label": "Number"}, "#ccnum", id="#ccnum"),
    pytest.param({"ref": "#cardnum", "role": "textbox", "label": "Number"}, "#cardnum", id="#cardnum"),
    pytest.param({"ref": "#f", "role": "textbox", "label": "Kartennummer"}, "#f", id="Kartennummer"),
]


@pytest.mark.parametrize("operation", ["fill", "select"])
@pytest.mark.parametrize("element,locator", CARD_FIELDS)
def test_payment_instrument_fields_are_a4_for_fill_and_select(operation, element, locator):
    assert _class(operation, element, locator) == "A4"


PAY_BUTTONS = ["#paynow", "#buynow", "#placeorder", "button.submitorder",
               "[data-testid=checkoutbutton]", "#confirmpurchase"]


@pytest.mark.parametrize("locator", PAY_BUTTONS)
def test_concatenated_pay_button_ids_are_a4_even_labelled_continue(locator):
    assert _class("click", {"ref": locator, "role": "button", "label": "Continue"}, locator) == "A4"


DISGUISED_PAY_LABELS = [
    pytest.param("Pa​y now", id="zero-width-space"),
    pytest.param("Pаy now", id="cyrillic-a"),
    pytest.param("Ｐａｙ now", id="fullwidth"),
    pytest.param("Pay­now", id="soft-hyphen"),
]


@pytest.mark.parametrize("label", DISGUISED_PAY_LABELS)
def test_disguised_pay_labels_are_folded_before_matching(label):
    assert _class("click", {"ref": "#b", "role": "button", "label": label}, "#b") == "A4"


@pytest.mark.parametrize("label", DISGUISED_PAY_LABELS)
def test_disguised_pay_labels_reach_the_payment_boundary_as_pay_now(label):
    from van_gateway.automation.payments import looks_like_payment

    text = observed_element_text({"ref": "#b", "role": "button", "label": label}, "#b")
    assert looks_like_payment(operation="click", goal=text) == "payment_intent_in_text"


# ------------------------------------------------------------------ false-positive trade-off

@pytest.mark.parametrize("label,locator", [
    ("Next", "#next"), ("Open statement", "a.statement-link"), ("Search", "button.border-0"),
    ("Download PDF", "#download"), ("Display", "#display"),
])
def test_benign_controls_stay_automatable(label, locator):
    assert _class("click", {"ref": locator, "role": "button", "label": label}, locator) == "A2"


@pytest.mark.parametrize("label,locator", [
    ("Buyer guide", "a.buyer-guide"), ("order by date", "#sort-order"),
])
def test_accepted_false_positives_fail_safe_to_the_owner(label, locator):
    """Documented trade-off: substring stems over-match, and an over-match is A4 -> owner."""
    assert _class("click", {"ref": locator, "role": "button", "label": label}, locator) == "A4"


def test_the_border_carve_out_cannot_hide_a_real_order():
    assert _class("click", {"ref": "#b-order", "role": "button", "label": "Go"}, "#b-order") == "A4"


# ------------------------------------------------------------------ through the router

_PC = PostconditionSpec(kind="READ_BACK", field="title", expected="x")

LOCATOR_ONLY = [
    ("click", "#paynow"), ("click", "#buynow"), ("click", "#placeorder"), ("click", "button.submitorder"),
    ("click", "[data-testid=checkoutbutton]"), ("click", "#confirmpurchase"),
    ("fill", "#cardnum"), ("fill", "#ccnum"), ("fill", "input[name=cardnumber]"), ("fill", "#cc-exp"),
    ("fill", "#kartennummer"),
]


@pytest.mark.parametrize("operation,locator", LOCATOR_ONLY)
async def test_lane1_locator_only_classification_hands_to_the_owner(operation, locator):
    """The live Harness reports no elements: lane 1 classifies on the locator alone."""
    ex = tr.FakeExecutor()
    router = tr.make_router(executor=ex, target_resolver=tr.FakeResolver({}), eligibility_classifier=None,
                            semantic_fallback=tr.FakeStagehand(None))
    s = tr.step(action_class_ceiling="A3", postcondition=_PC, deterministic_action=DeterministicAction(
        operation=operation, locator=locator,
        value_ref="secretref://owner/x" if operation == "fill" else None))
    s.task = s.task.model_copy(update={"action_class": ActionClass.A3})
    result = await router.route(s)
    assert result.state is StepState.OWNER_TAKEOVER
    assert "DETERMINISTIC_ACTION_NOT_AUTOMATABLE:A4" in result.reasons
    assert ex.executed == []


CC_ELEMENTS = {
    "#f1": {"ref": "#f1", "role": "textbox", "label": "Number", "autocomplete": "cc-number"},
    "#f2": {"ref": "#f2", "role": "textbox", "label": "Code", "attributes": {"autocomplete": "cc-csc"}},
    "#f3": {"ref": "#f3", "role": "textbox", "label": "MM / YY", "autocomplete": "cc-exp"},
}


class _Proposes:
    def __init__(self, locator: str) -> None:
        self.locator = locator

    async def propose(self, task, step):
        return RouterAction(lane=RouterLane.STAGEHAND, operation="fill", locator=self.locator,
                            value_ref="secretref://owner/x", action_class=None, description="Enter the number")


@pytest.mark.parametrize("locator", sorted(CC_ELEMENTS))
@pytest.mark.parametrize("lane", ["deterministic", "stagehand"])
async def test_autocomplete_cc_fields_are_never_filled_by_lane_1_or_3(locator, lane):
    ex = tr.FakeExecutor()
    router = tr.make_router(
        executor=ex, target_resolver=tr.FakeResolver(CC_ELEMENTS), eligibility_classifier=None,
        semantic_fallback=_Proposes(locator) if lane == "stagehand" else tr.FakeStagehand(None))
    det = (DeterministicAction(operation="fill", locator=locator, value_ref="secretref://owner/x")
           if lane == "deterministic" else None)
    s = tr.step(action_class_ceiling="A3", postcondition=_PC, deterministic_action=det)
    s.task = s.task.model_copy(update={"action_class": ActionClass.A3})
    result = await router.route(s)
    assert result.state is StepState.OWNER_TAKEOVER
    assert ex.executed == []


def test_accepted_false_positive_card_wrapper_in_a_fill_selector():
    """A Bootstrap `.card` wrapper in a fill selector over-matches "card": owner, fail-safe."""
    locator = ".card input[name=email]"
    assert _class("fill", {"ref": locator, "role": "textbox", "label": "Email"}, locator) == "A4"


@pytest.mark.parametrize("token", ["cc-given-name", "cc-family-name", "cc-exp-month", "cc-additional-name"])
def test_every_cc_autocomplete_token_is_a_payment_field(token):
    """Any `cc-*` autocomplete token (not just the three stems) names a card field."""
    element = {"ref": "#f", "role": "textbox", "label": "Name", "autocomplete": token}
    assert _class("fill", element, "#f") == "A4"
