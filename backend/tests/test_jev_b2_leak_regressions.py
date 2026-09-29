"""Reviewer I minor 1 — B2 labels that leaked private data (probe review-i/probes/b2/b2.py).

Every label below used to be sent to dial-jev on an otherwise clean public page. The 57 DDS
fixtures must still reproduce exactly (``test_jev_browser_eligibility.py``); this file pins
the new detections and that ordinary public labels still pass.
"""

from __future__ import annotations

import pytest

from van_gateway.browser.interaction_router import (
    build_eligibility_policy,
    build_interaction_router,
    load_owner_private_terms,
)
from van_gateway.browser.jev_eligibility import (
    JevEligibilityPolicy,
    JevPageObservation,
    ObservedElement as E,
    classify_observation,
    private_data_findings,
)
from van_gateway.config import Settings

URL = "https://docs.python.org/3/library/json.html"
BASE = E(ref="a#next", role="link", label="Next topic")


def _classify(*elements, title="json", policy=None):
    obs = JevPageObservation(url=URL, profile_alias="public_research", authenticated=False,
                             cookies_present=False, elements=(BASE, *elements), page_title=title)
    return classify_observation(obs, closed_operation_set=("click", "scroll", "done", "abstain"),
                                action_class_ceiling="A2", policy=policy)


LEAKS = {
    "Code 481|516": "DIGIT_RUN",
    "Ref 481:516": "DIGIT_RUN",
    "Ref 48+15+16": "DIGIT_RUN",
    "Ref 481 516": "DIGIT_RUN",
    "Ref 48/15-16.2": "DIGIT_RUN",
    "jane.doe@example": "EMAIL",
    "jane.doe@example/com": "EMAIL",
    "acct one two three four five six seven eight": "DIGIT_RUN",
    "pin nine 8 seven 6 five": "DIGIT_RUN",
    "SW1A 1AA": "POSTCODE",
    "EC1A 1BB": "POSTCODE",
    "221B Baker Street": "STREET_ADDRESS",
    "10 Downing St": "STREET_ADDRESS",
}


@pytest.mark.parametrize(("label", "code"), list(LEAKS.items()))
def test_leaking_label_is_detected_and_the_page_is_not_sent(label, code):
    assert code in private_data_findings(label)
    result = _classify(E(ref="#b", role="button", label=label))
    assert result.eligibility_class.value == "OWNER_PRIVATE", result.reasons
    assert result.jev_payload is None


@pytest.mark.parametrize("label", [
    "Signed in as Jane Doe", "Logged in as jdoe", "signed in as Ana", "Hi Jane Doe",
    "Hello, Jane", "Welcome back, Priya", "Good morning Tom",
])
def test_a_page_addressing_a_person_is_signed_in(label):
    result = _classify(E(ref="#b", role="button", label=label))
    assert result.eligibility_class.value == "OWNER_PRIVATE"
    assert "OWNER_SIGNED_IN_EVIDENCE" in result.reasons
    assert result.jev_payload is None


def test_a_greeting_in_the_title_is_signed_in():
    result = _classify(title="Hello, Jane - Dashboard")
    assert "OWNER_SIGNED_IN_EVIDENCE" in result.reasons and result.jev_payload is None


@pytest.mark.parametrize("label", [
    "Next topic", "Python 3.12 documentation", "Hello World example", "Hello, world!",
    "Welcome to Python.org", "Welcome back", "Hi there", "Section 4.3.2.1", "Version 3.12.1",
    "Page 1 of 20", "Chapter 12: Classes", "Table 3 | Figure 4", "C++ reference", "Use a+b",
    "Ratio 16:9", "HTTP/1.1", "Step 1 of 3", "One two three", "M25 motorway", "A1 paper",
])
def test_ordinary_public_labels_still_pass(label):
    assert private_data_findings(label) == []
    result = _classify(E(ref="#b", role="button", label=label))
    assert result.jev_payload is not None, (label, result.reasons)


def test_a_bare_name_needs_the_owner_terms():
    """Names alone are not detectable without destroying utility ("Next Topic" is two
    capitalised words too). That is what owner_private_terms is for."""
    assert _classify(E(ref="#b", role="button", label="Jane Doe")).jev_payload is not None
    policy = JevEligibilityPolicy(owner_private_terms=("Jane Doe",))
    result = _classify(E(ref="#b", role="button", label="Jane Doe"), policy=policy)
    assert result.jev_payload is None and "OWNER_PRIVATE_LABEL:OWNER_PROFILE_TERM" in result.reasons


# ---------------------------------------------------------------- owner terms wiring


def test_owner_terms_file_is_read_one_term_per_line(tmp_path):
    path = tmp_path / "terms"
    path.write_text("# owner\nJane Doe\n\njdoe\nJane Doe\n", encoding="utf-8")
    assert load_owner_private_terms(str(path)) == ("Jane Doe", "jdoe")
    assert load_owner_private_terms("") == ()
    assert load_owner_private_terms(str(tmp_path / "missing")) == ()


def test_production_router_disables_the_jev_lane_without_owner_terms():
    router = build_interaction_router(settings=Settings(), harness=object(), stagehand=object(), jev_client=None)
    assert "JEV_LANE_DISABLED:OWNER_PRIVATE_TERMS_UNCONFIGURED" in router.jev_lane_disabled_reasons()
    assert build_eligibility_policy(Settings()) is None


def test_production_router_passes_configured_owner_terms_to_b2(tmp_path):
    path = tmp_path / "terms"
    path.write_text("Jane Doe\n", encoding="utf-8")
    settings = Settings(browser_jev_owner_private_terms_file=str(path))

    class Jev:
        configured = True

    router = build_interaction_router(settings=settings, harness=object(), stagehand=object(), jev_client=Jev())
    assert router.eligibility_policy.owner_private_terms == ("Jane Doe",)
    assert not any("OWNER_PRIVATE_TERMS" in r for r in router.jev_lane_disabled_reasons())


@pytest.mark.parametrize("label", ["Ratio 16:9 & 4:3", "Figures 1, 2 & 3; 4 & 5"])
def test_bare_digits_split_by_other_punctuation_are_not_a_spelled_run(label):
    assert "DIGIT_RUN" not in private_data_findings(label)
