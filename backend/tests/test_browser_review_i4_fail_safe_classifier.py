"""Review I4 MAJOR-A — the action classifier fails safe instead of enumerating risk.

Reviewer I4's probes (review-i4/probes/router_bypass.py, assign_bypass.py,
classify_bypass.py) showed the stem denylist still clicked ``#transfernow``,
``#sendmoney``, ``#withdrawfunds``, ``#subscribenow``, ``#confirmtransfer``,
``aria-label=Оплатить/Купить``, ``#pɑynow`` (U+0251), "Páy now", 支付 / 立即购买 / 購入する,
it/nl/pl/pt/es/fr/de pay and order words, "Donate $50", "Book now",
``data-testid=pay-button``, ``class=btn-pay`` and aria-describedby-only text at A2, and
classified ``name=pan type=tel``, localized card labels, "MM / YY", ``exp`` and a PAN
placeholder as only A3.

``van_gateway.browser.action_risk`` now makes a targeted click/fill/select A4 unless it is
positively low-risk (R1 Latin/ASCII after folding, R2 no risk stem, R3 role outside the
risky set, R4 no payment/secret-field signal, R5 evidence, R6 the unresolved-target rule).
Every I4 case below must end in owner takeover or payment refusal with nothing executed:
through the classifier, router lane 1, router lane 3, the deterministic
``/v1/browser/assignments`` plan path end to end, and the HybridBrowserWorker Stagehand path.
"""

from __future__ import annotations

import pathlib
import re
import tempfile

import pytest
from cryptography.fernet import Fernet

import test_browser_api as t
import test_browser_interaction_router as tr
from test_browser_semantic_worker import FakeHarness as SemanticHarness
from test_browser_semantic_worker import FakeStagehand, _assignment, _task
from van_gateway.automation.payments import looks_like_payment
from van_gateway.automation.verifier import PostconditionSpec
from van_gateway.browser.action_risk import (
    _PAYMENT_FIELD_STEMS,
    _RISK_STEMS,
    HIGH_RISK_WORDS,
    assess_action,
    fold,
    unmapped_characters,
)
from van_gateway.browser.interaction_router import (
    DeterministicAction,
    RouterAction,
    RouterLane,
    StepState,
    default_action_classifier,
    explain_action_class,
    observed_element_text,
    observed_target,
)
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.subagent import BrowserSubagentRunner, SubagentStop
from van_gateway.browser.worker import HybridBrowserWorker
from van_gateway.config import get_settings
from van_gateway.models import ActionClass

_PC = PostconditionSpec(kind="READ_BACK", field="title", expected="x")


@pytest.fixture(autouse=True)
def _browser_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "browser.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", t.INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", t.INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", t.INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _btn(name: str, **kw) -> dict:
    return {"locator": "#b", "role": "button", "name": name, **kw}


def _field(name: str, **kw) -> dict:
    return {"locator": "#f", "role": "textbox", "name": name, **kw}


# ------------------------------------------------------------------ the I4 cases

#: (operation, locator) exactly as I4's router/assign probes sent them: the Harness reports
#: no element, so only the locator is known.
I4_UNRESOLVED = [
    ("click", "#transfernow"), ("click", "#sendmoney"), ("click", "#withdrawfunds"),
    ("click", "#subscribenow"), ("click", "#confirmtransfer"),
    ("click", "[aria-label=Оплатить]"), ("click", '[aria-label="Купить"]'),
    ("click", "#pɑynow"), ("click", '[title="Páy now"]'), ("click", "#paynow"),
    ("fill", "input[name=pan]"),
]

#: Harness-observed elements (the unit G5b element shape).
I4_CLICKS = [
    pytest.param(_btn("支付"), id="zh-pay"),
    pytest.param(_btn("立即购买"), id="zh-buy-now"),
    pytest.param(_btn("購入する"), id="ja-purchase"),
    pytest.param(_btn("Оплатить"), id="ru-pay"),
    pytest.param(_btn("Купить"), id="ru-buy"),
    pytest.param(_btn("ادفع الآن"), id="ar-pay-now"),
    pytest.param(_btn("Paga ora"), id="it-pay-now"),
    pytest.param(_btn("Acquista ora"), id="it-buy-now"),
    pytest.param(_btn("Betalen"), id="nl-pay"),
    pytest.param(_btn("Afrekenen"), id="nl-checkout"),
    pytest.param(_btn("Zapłać"), id="pl-pay"),
    pytest.param(_btn("Finalizar compra"), id="pt-checkout"),
    pytest.param(_btn("Realizar pedido"), id="es-place-order"),
    pytest.param(_btn("Commander"), id="fr-order"),
    pytest.param(_btn("Überweisen"), id="de-transfer"),
    pytest.param(_btn("Jetzt kaufen"), id="de-buy-now"),
    pytest.param(_btn("Donate $50"), id="donate-50"),
    pytest.param(_btn("Book now"), id="book-now"),
    pytest.param(_btn("Pɑy now"), id="latin-alpha-U+0251"),
    pytest.param(_btn("Páy now"), id="combining-acute"),
    pytest.param(_btn("Páy now"), id="precomposed-acute"),
    pytest.param(_btn("Pạy now"), id="dot-below"),
    pytest.param(_btn("Ᏼuy now"), id="cherokee-B"),
    pytest.param(_btn("Bսy now"), id="armenian-u"),
    pytest.param(_btn("Pa‍y now"), id="zwj"),
    pytest.param(_btn("P<span>a</span>y now"), id="inline-markup"),
    pytest.param(_btn("Continue", locator="#transfernow"), id="id-transfernow"),
    pytest.param(_btn("Continue", locator="#sendmoney"), id="id-sendmoney"),
    pytest.param(_btn("Continue", locator="#withdrawfunds"), id="id-withdrawfunds"),
    pytest.param(_btn("Continue", locator="#subscribenow"), id="id-subscribenow"),
    pytest.param(_btn("Continue", locator="#confirmtransfer"), id="id-confirmtransfer"),
    pytest.param(_btn("Continue", attributes={"data-testid": "pay-button"}), id="data-testid-pay-button"),
    pytest.param(_btn("Continue", **{"data-testid": "pay-button"}), id="top-level-data-testid"),
    pytest.param(_btn("Continue", attributes={"class": "btn btn-pay"}), id="class-btn-pay"),
    pytest.param(_btn("Continue", **{"class": "btn-pay"}), id="top-level-class"),
    pytest.param(_btn("Continue", description="Pay $40 now"), id="accessible-description"),
    pytest.param(_btn("Continue", attributes={"aria-describedby": "Pay $40 now"}), id="aria-describedby-text"),
    pytest.param(_btn("Continue", aria_describedby="Pay $40 now"), id="aria_describedby-key"),
    pytest.param(_btn("Delete account"), id="delete-account"),
    pytest.param(_btn("Close my account"), id="close-account"),
    pytest.param(_btn("Cancel membership"), id="cancel-membership"),
    pytest.param(_btn("I agree"), id="agree"),
    pytest.param(_btn("Upgrade plan"), id="upgrade"),
    pytest.param(_btn("Renew"), id="renew"),
    pytest.param(_btn("Reserve table"), id="reserve"),
    pytest.param(_btn("Enrol"), id="enrol"),
    pytest.param(_btn("Authorise"), id="authorise"),
    pytest.param(_btn("Deposit"), id="deposit"),
]

I4_FIELDS = [
    pytest.param(_field("Number", type="tel", attributes={"name": "pan"}), id="type-tel-name-pan"),
    pytest.param({"locator": "input[name=pan]", "role": "textbox", "name": "Number", "type": "tel"}, id="input-name-pan"),
    pytest.param(_field("Número de tarjeta"), id="es-card-number"),
    pytest.param(_field("Numero carta"), id="it-card-number"),
    pytest.param(_field("Kaartnummer"), id="nl-card-number"),
    pytest.param(_field("Номер карты"), id="ru-card-number"),
    pytest.param(_field("卡号"), id="zh-card-number"),
    pytest.param(_field("MM / YY"), id="label-mm-yy"),
    pytest.param(_field("Date", placeholder="MM / YY"), id="placeholder-mm-yy"),
    pytest.param(_field("Exp date", attributes={"name": "exp"}), id="exp"),
    pytest.param(_field("CSC"), id="csc"),
    pytest.param(_field("Code", inputmode="numeric", maxlength="4"), id="numeric-maxlength-4"),
    pytest.param(_field("Code", inputmode="numeric", maxlength=3), id="numeric-maxlength-3-int"),
    pytest.param(_field("Number", inputmode="numeric", maxlength="19"), id="numeric-maxlength-19"),
    pytest.param(_field("Code", pattern="[0-9]{3,4}"), id="pattern-3-4-digits"),
    pytest.param(_field("Number", placeholder="1234 1234 1234 1234"), id="pan-placeholder"),
    pytest.param(_field("Number", placeholder="•••• •••• •••• ••••"), id="bullet-placeholder"),
    pytest.param(_field("Name", autocomplete="cc-name"), id="autocomplete-cc-name"),
    pytest.param(_field("Number", attributes={"autocomplete": "CC-NUMBER"}), id="autocomplete-upper"),
    pytest.param(_field("Number", attributes={"x-autocompletetype": "cc-number"}), id="x-autocompletetype"),
    pytest.param(_field("Routing no."), id="routing"),
    pytest.param(_field("PIN", type="password", inputmode="numeric"), id="numeric-pin"),
]


# ------------------------------------------------------------------ classifier units

@pytest.mark.parametrize("element", I4_CLICKS)
def test_every_i4_commitment_click_is_a4(element):
    target = observed_target("click", element, element["locator"])
    assert default_action_classifier("click", target, None) == "A4", explain_action_class("click", target)


@pytest.mark.parametrize("element", I4_CLICKS)
def test_every_i4_commitment_click_is_a4_through_the_label_only_path(element):
    """I4's instrument: the joined observed text as a bare label (older callers)."""
    label = observed_element_text(element, element["locator"])
    assert default_action_classifier("click", {"label": label}, None) == "A4"


@pytest.mark.parametrize("operation", ["fill", "select"])
@pytest.mark.parametrize("element", I4_FIELDS)
def test_every_i4_payment_or_secret_field_is_a4(operation, element):
    target = observed_target(operation, element, element["locator"])
    assert default_action_classifier(operation, target, None) == "A4", explain_action_class(operation, target)


@pytest.mark.parametrize("operation,locator", I4_UNRESOLVED)
def test_every_i4_unresolved_locator_is_a4(operation, locator):
    target = observed_target(operation, "TARGET_NOT_RESOLVED_BY_HARNESS", locator)
    assert default_action_classifier(operation, target, None) == "A4", explain_action_class(operation, target)


# ------------------------------------------------------------------ the rules, one by one

def test_r1_non_latin_script_is_a4_even_with_no_stem():
    """A Cyrillic word that is not a risk word ("Далее" = Next) is still A4: R1 is the
    backstop for every language the denylist does not know."""
    rules = explain_action_class("click", observed_target("click", _btn("Далее"), "#b")).rules
    assert rules[0].startswith("R1_NON_LATIN_OR_UNMAPPED")


def test_r1_a_fully_confusable_cyrillic_label_is_still_non_latin():
    """"Сосо" (all Cyrillic look-alikes) folds to "coco" for matching, but R1 reads it
    before the cross-script map, so it is A4."""
    assert fold("Сосо") == "coco"
    assert unmapped_characters("Сосо")
    assert explain_action_class("click", observed_target("click", _btn("Сосо"), "#b")).action_class == "A4"


def test_r1_unmapped_symbol_is_a4():
    assert explain_action_class("click", observed_target("click", _btn("Continue €10"), "#b")).rules == (
        "R1_NON_LATIN_OR_UNMAPPED:€",
    )


def test_fold_is_nfkd_mn_nfkc_cf_then_latin_and_confusables():
    assert fold("Páy") == "pay"  # combining mark dropped
    assert fold("Páy") == "pay"  # precomposed decomposed then dropped
    assert fold("Pɑy") == "pay"  # IPA alpha
    assert fold("Zapłać") == "zaplac"  # ł mapped
    assert fold("Pa​y") == "pay"  # Cf dropped
    assert fold("Ｐａｙ") == "pay"  # NFKC fullwidth
    assert fold("Bսy") == "buy"  # Armenian
    assert fold("Ᏼuy") == "buy"  # Cherokee
    assert unmapped_characters("Páy now Zapłać Überweisen Pɑy") == ""
    assert unmapped_characters("Bսy") == "ս"


def test_r2_stems_are_a_superset_of_the_historic_word_list():
    alternatives = HIGH_RISK_WORDS.pattern.replace("\\b", " ").replace("[sz]", "s")
    words = re.findall(r"[a-z]+", alternatives)
    assert len(words) == 18 and "authorise" in words
    for word in words:
        assert any(stem in word for stem in _RISK_STEMS), word
    for stem in ("transfer", "send", "withdraw", "deposit", "subscri", "authori", "approve", "confirm",
                 "submit", "donate", "book", "reserve", "sign", "agree", "accept", "enrol", "upgrade",
                 "renew", "closeaccount", "cancelaccount", "terminateaccount", "delete"):
        assert stem in _RISK_STEMS, stem
    assert {"card", "cvc", "iban", "tarjeta", "carta", "kaart"} <= set(_PAYMENT_FIELD_STEMS)


def test_r3_risky_role_is_a4():
    rules = explain_action_class("click", observed_target("click", {"locator": "#t", "role": "switch", "name": "Dark mode"}, "#t")).rules
    assert rules == ("R3_RISKY_ROLE:switch",)


def test_r4_structure_decides_whatever_the_label_says():
    element = {"locator": "#f", "role": "textbox", "name": "Number", "inputmode": "numeric", "maxlength": 16}
    rules = explain_action_class("fill", observed_target("fill", element, "#f")).rules
    assert rules and rules[0].startswith("R4_PAYMENT_OR_SECRET_FIELD")


def test_r5_no_evidence_is_a4():
    assert assess_action("click", element=None, locator=None, resolved=False).action_class == "A4"
    assert default_action_classifier("click", None, None) == "A4"
    # A target that carries no text at all: R5 alone decides.
    assert explain_action_class("click", {"label": ""}).rules == ("R5_NO_EVIDENCE",)
    assert default_action_classifier("click", {"label": ""}, None) == "A4"


def test_r6_unresolved_target_decision():
    """Click: A2 only on a plain-ASCII locator with no risk stem. Fill/select: always A4."""
    unresolved = "TARGET_NOT_RESOLVED_BY_HARNESS"
    assert explain_action_class("click", observed_target("click", unresolved, "#next")).action_class == "A2"
    assert explain_action_class("fill", observed_target("fill", unresolved, "#email")).rules == ("R6_UNRESOLVED_WRITE",)
    assert explain_action_class("select", observed_target("select", unresolved, "#sort")).rules == ("R6_UNRESOLVED_WRITE",)
    rules = explain_action_class("click", observed_target("click", unresolved, "#café")).rules
    assert "R6_UNRESOLVED_LOCATOR_NOT_PLAIN_ASCII" in rules


def test_payment_boundary_reads_folded_text():
    """Payments first needs the boundary to see "pay now" behind a mark or a homoglyph."""
    for name in ("Páy now", "Pɑy now", "Pa​y now"):
        text = observed_element_text(_btn(name), "#b")
        assert looks_like_payment(operation="click", goal=text) == "payment_intent_in_text", name


# ------------------------------------------------------------------ benign set (false-positive trade-off)

BENIGN_CLICKS = [
    pytest.param({"locator": "#next", "role": "link", "name": "Next page", "attributes": {"href": "/p/2"}}, id="next-page"),
    pytest.param({"locator": "#search", "role": "button", "name": "Search"}, id="search"),
    pytest.param({"locator": "#details", "role": "button", "name": "Show details",
                  "attributes": {"class": "btn btn-link", "data-testid": "details-toggle"}}, id="show-details"),
    pytest.param({"locator": "#close", "role": "button", "name": "Close dialog",
                  "attributes": {"aria-label": "Close dialog", "class": "close"}}, id="close-dialog"),
    pytest.param({"locator": "#x", "role": "button", "name": "×", "attributes": {"aria-label": "Close dialog"}}, id="times-close"),
    pytest.param({"locator": "#back", "role": "button", "name": "Zurück"}, id="latin-diacritic"),
    pytest.param({"locator": "#report", "role": "link", "name": "Open statement"}, id="open-statement"),
]


@pytest.mark.parametrize("element", BENIGN_CLICKS)
def test_benign_clicks_stay_a2(element):
    target = observed_target("click", element, element["locator"])
    assert default_action_classifier("click", target, None) == "A2", explain_action_class("click", target)


@pytest.mark.parametrize("element", [
    {"locator": "#q", "role": "searchbox", "name": "Search", "type": "search", "placeholder": "Search products"},
    {"locator": "#email", "role": "textbox", "name": "Email", "type": "email", "autocomplete": "email"},
    {"locator": "#dob", "role": "textbox", "name": "Date of birth", "placeholder": "DD/MM/YYYY"},
    {"locator": "#zip", "role": "textbox", "name": "ZIP", "inputmode": "numeric", "maxlength": 5},
    {"locator": "#pw", "role": "textbox", "name": "Password", "type": "password"},
], ids=["search", "email", "dob", "zip", "password"])
def test_benign_fills_stay_a3(element):
    target = observed_target("fill", element, element["locator"])
    assert default_action_classifier("fill", target, None) == "A3", explain_action_class("fill", target)


@pytest.mark.parametrize("operation,element", [
    ("click", {"locator": "#si", "role": "link", "name": "Sign in"}),
    ("click", {"locator": "#fb", "role": "link", "name": "Facebook"}),
    ("click", {"locator": "#ok", "role": "button", "name": "Accept cookies"}),
    ("click", {"locator": "#go", "role": "button", "name": "Search", "type": "submit"}),
    ("click", {"locator": "#ru", "role": "link", "name": "Далее"}),
    ("click", {"locator": "#price", "role": "button", "name": "View £20 plan"}),
    ("fill", {"locator": "#year", "role": "textbox", "name": "Birth year", "inputmode": "numeric", "maxlength": 4}),
], ids=["sign-in", "facebook", "accept-cookies", "submit-search", "cyrillic-next", "price", "birth-year"])
def test_accepted_false_positives_fail_safe_to_the_owner(operation, element):
    """Documented trade-off (action_risk docstring): these over-match and go to the owner."""
    target = observed_target(operation, element, element["locator"])
    assert default_action_classifier(operation, target, None) == "A4"


# ------------------------------------------------------------------ router lane 1 end to end

def _lane1(operation, locator, elements, *, ceiling="A3"):
    ex = tr.FakeExecutor()
    router = tr.make_router(executor=ex, target_resolver=tr.FakeResolver(elements), eligibility_classifier=None,
                            semantic_fallback=tr.FakeStagehand(None))
    s = tr.step(action_class_ceiling=ceiling, postcondition=_PC, deterministic_action=DeterministicAction(
        operation=operation, locator=locator,
        value_ref="secretref://owner/x" if operation == "fill" else None))
    s.task = s.task.model_copy(update={"action_class": ActionClass(ceiling)})
    return router, ex, s


def _ends_in_lane_4(result) -> bool:
    return (result.lane, result.state) in {
        (RouterLane.OWNER_TAKEOVER, StepState.OWNER_TAKEOVER),
        (RouterLane.POLICY_REFUSAL, StepState.POLICY_REFUSED),
    }


@pytest.mark.parametrize("operation,locator", I4_UNRESOLVED)
async def test_lane1_i4_unresolved_locators_never_execute(operation, locator):
    router, ex, s = _lane1(operation, locator, {})
    result = await router.route(s)
    assert _ends_in_lane_4(result), result.reasons
    assert "DETERMINISTIC_ACTION_NOT_AUTOMATABLE:A4" in result.reasons
    assert ex.executed == []


async def test_lane1_folded_pay_locator_is_a_payment_refusal_first():
    router, ex, s = _lane1("click", '[title="Páy now"]', {})
    result = await router.route(s)
    assert result.state is StepState.POLICY_REFUSED and ex.executed == []
    assert any("automated_payment_prohibited_in_interaction_router_deterministic" in r for r in result.reasons)


@pytest.mark.parametrize("element", I4_CLICKS)
async def test_lane1_i4_resolved_clicks_never_execute(element):
    router, ex, s = _lane1("click", element["locator"], {element["locator"]: element})
    result = await router.route(s)
    assert _ends_in_lane_4(result), result.reasons
    assert ex.executed == []


@pytest.mark.parametrize("element", I4_FIELDS)
async def test_lane1_i4_resolved_fields_never_filled(element):
    router, ex, s = _lane1("fill", element["locator"], {element["locator"]: element})
    result = await router.route(s)
    assert _ends_in_lane_4(result), result.reasons
    assert ex.executed == []


@pytest.mark.parametrize("element", BENIGN_CLICKS)
async def test_lane1_benign_clicks_execute_at_a2(element):
    router, ex, s = _lane1("click", element["locator"], {element["locator"]: element}, ceiling="A2")
    result = await router.route(s)
    assert result.state is StepState.VERIFIED_SUCCESS, result.reasons
    assert [(a.locator, a.action_class) for a in ex.executed] == [(element["locator"], "A2")]
    assert any(r.startswith("DETERMINISTIC_ACTION_RISK:LOW_RISK") for r in result.reasons)


async def test_lane1_unresolved_plain_click_runs_and_unresolved_fill_does_not():
    router, ex, s = _lane1("click", "#next", {}, ceiling="A2")
    assert (await router.route(s)).state is StepState.VERIFIED_SUCCESS
    router, ex, s = _lane1("fill", "#email", {})
    result = await router.route(s)
    assert result.state is StepState.OWNER_TAKEOVER and ex.executed == []
    assert "DETERMINISTIC_ACTION_RISK:R6_UNRESOLVED_WRITE" in result.reasons


# ------------------------------------------------------------------ router lane 3

class _Proposes:
    def __init__(self, operation: str, locator: str, description: str) -> None:
        self.action = RouterAction(lane=RouterLane.STAGEHAND, operation=operation, locator=locator,
                                   value_ref="secretref://owner/x" if operation == "fill" else None,
                                   action_class=None, description=description)

    async def propose(self, task, step):
        return self.action


@pytest.mark.parametrize("element", I4_CLICKS[:12] + I4_CLICKS[26:38])
async def test_lane3_i4_clicks_never_execute(element):
    ex = tr.FakeExecutor()
    router = tr.make_router(executor=ex, target_resolver=tr.FakeResolver({element["locator"]: element}),
                            eligibility_classifier=None,
                            semantic_fallback=_Proposes("click", element["locator"], "Continue"))
    result = await router.route(tr.step(action_class_ceiling="A2", postcondition=_PC))
    assert _ends_in_lane_4(result), result.reasons
    assert "STAGEHAND_ACTION_ABOVE_CEILING:A4" in result.reasons
    assert ex.executed == []


# ------------------------------------------------------------------ /v1/browser/assignments end to end

class _PlanHarness:
    def __init__(self, elements=None):
        self.calls: list[tuple[str, str]] = []
        self.elements = elements

    async def navigate(self, task, url):
        self.calls.append(("navigate", url))
        return {}

    async def page_info(self, task):
        page = {"url": f"https://{t.DOMAIN}/x", "title": "Statement", "extraction": {}}
        if self.elements is not None:
            page["elements"] = [dict(e) for e in self.elements]
        return page

    async def click(self, task, loc):
        self.calls.append(("click", loc))
        return {}

    async def fill_ref(self, task, loc, ref):
        self.calls.append(("fill", loc))
        return {}


async def _assign(steps, *, elements=None, ceiling="A2"):
    from van_gateway.browser.worker import HybridBrowserWorker as Worker

    harness = _PlanHarness(elements)
    ac, _api, _store = await t._client(pathlib.Path(tempfile.mkdtemp()), worker=Worker(harness, None),
                                        verifier=t._Verdict())
    async with ac:
        task = await t._make_task(ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC",
                                  action_class=ceiling)
        response = await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={
            "task_id": task["task_id"], "turn_id": "t1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN],
            "action_class_ceiling": ceiling, "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
            "plan": {"steps": steps},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "Statement"},
        })
    assert response.status_code == 200, response.text
    return response.json(), harness


@pytest.mark.parametrize("operation,locator", I4_UNRESOLVED)
async def test_assignments_i4_unresolved_plan_steps_never_execute(operation, locator):
    step = {"kind": operation, "domain": t.DOMAIN, "locator": locator, "instruction": "Continue"}
    if operation == "fill":
        step["value_ref"] = "secretref://owner/x"
    body, harness = await _assign([step], ceiling="A3" if operation == "fill" else "A2")
    assert body["stop_reason"] in ("OWNER_TAKEOVER", "PAYMENT_REFUSED"), body
    assert body["succeeded"] is False
    assert harness.calls == []


@pytest.mark.parametrize("element", [p.values[0] for p in I4_CLICKS[:6]] + [p.values[0] for p in I4_CLICKS[26:32]],
                         ids=lambda e: e["name"] + e["locator"])
async def test_assignments_i4_resolved_clicks_never_execute(element):
    step = {"kind": "click", "domain": t.DOMAIN, "locator": element["locator"], "instruction": "Continue"}
    body, harness = await _assign([step], elements=[element])
    assert body["stop_reason"] in ("OWNER_TAKEOVER", "PAYMENT_REFUSED"), body
    assert harness.calls == []


@pytest.mark.parametrize("element", [p.values[0] for p in I4_FIELDS[:10]], ids=lambda e: e["name"] + e["locator"])
async def test_assignments_i4_card_fields_never_filled(element):
    step = {"kind": "fill", "domain": t.DOMAIN, "locator": element["locator"], "instruction": "Enter",
            "value_ref": "secretref://owner/x"}
    body, harness = await _assign([step], elements=[element], ceiling="A3")
    assert body["stop_reason"] in ("OWNER_TAKEOVER", "PAYMENT_REFUSED"), body
    assert harness.calls == []


async def test_assignments_plan_path_reads_field_structure_not_only_text():
    """A CVC field whose only signal is its ``pattern``: the plan path must classify the
    Harness element's structure, not a text rendering of it."""
    element = {"locator": "#c", "role": "textbox", "name": "Code", "pattern": "[0-9]{3,4}"}
    step = {"kind": "fill", "domain": t.DOMAIN, "locator": "#c", "instruction": "Enter",
            "value_ref": "secretref://owner/x"}
    body, harness = await _assign([step], elements=[element], ceiling="A3")
    assert body["stop_reason"] == "OWNER_TAKEOVER" and harness.calls == []


async def test_assignments_folded_pay_is_refused_as_a_payment_first():
    step = {"kind": "click", "domain": t.DOMAIN, "locator": '[title="Páy now"]', "instruction": "Continue"}
    body, harness = await _assign([step])
    assert body["stop_reason"] == "PAYMENT_REFUSED" and harness.calls == []


async def test_assignments_benign_click_still_runs():
    element = {"locator": "#next", "role": "link", "name": "Next page"}
    step = {"kind": "click", "domain": t.DOMAIN, "locator": "#next", "instruction": "Next page"}
    body, harness = await _assign([step], elements=[element])
    assert body["stop_reason"] == "GOAL_ACHIEVED" and body["succeeded"] is True
    assert harness.calls == [("click", "#next")]


# ------------------------------------------------------------------ HybridBrowserWorker (Stagehand) path

async def _owner_free(_task):
    return False


@pytest.mark.parametrize("element", [p.values[0] for p in I4_CLICKS[:6]] + [p.values[0] for p in I4_CLICKS[26:32]],
                         ids=lambda e: e["name"] + e["locator"])
async def test_semantic_worker_i4_clicks_never_execute(tmp_path, element):
    task = await _task(tmp_path)
    harness = SemanticHarness([{**element, "ref": element["locator"]}])
    control = {"method": "click", "selector": element["locator"], "description": "Continue", "arguments": []}
    result = await BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=_owner_free).run(
        assignment=_assignment(task, action_class_ceiling=ActionClass.A3),
        worker=HybridBrowserWorker(harness, FakeStagehand([[control], []]), task=task), task=task,
        verifier=t._Verdict("VERIFIED"), postcondition=None,
    )
    assert result.stop_reason in (SubagentStop.OWNER_TAKEOVER, SubagentStop.PAYMENT_REFUSED,
                                  SubagentStop.ACTION_CLASS_VIOLATION), result
    assert not result.succeeded
    assert not [c for c in harness.calls if c.startswith("click:")]

