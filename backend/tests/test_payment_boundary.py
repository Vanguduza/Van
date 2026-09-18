"""Owner decision 2026-09-18 — payments are never automated, instruments never stored.

`docs/SECURITY_POLICY.md` §Payments. The owner's constraint has two halves and
both are tested here, because a system that blocks the obvious "pay this invoice"
workflow but lets a step POST to `api.stripe.com/v1/charges` has not implemented
the rule.
"""

from __future__ import annotations

import pytest

from conftest_automation import policy_with_domains, sample_ir
from van_gateway.automation.credentials import (
    CredentialAlias,
    CredentialClass,
    CredentialResolver,
)
from van_gateway.automation.models import (
    Primitive,
    RetryClass,
    WorkflowIRStep,
    WorkflowStepEffect,
)
from van_gateway.automation.payments import (
    PaymentBoundaryError,
    assert_no_instrument,
    assert_not_automated_payment,
    assert_payment_action_is_owner_approved,
    looks_like_payment,
    scan_for_instrument,
)
from van_gateway.automation.policy import PolicyError
from van_gateway.automation.validator import WorkflowValidator
from van_gateway.models import ActionClass

DOMAIN = "reports.example.com"


# ------------------------------------------------------ instrument detection


@pytest.mark.parametrize(
    "value",
    [
        "4111111111111111",           # Visa test PAN
        "4111 1111 1111 1111",        # space grouped
        "5500-0000-0000-0004",        # dash grouped
        "cvv: 123",
        "expiry 09/28",
        "GB29NWBK60161331926819",     # IBAN
        "sort code 60-16-13",
        "account number 31926819",
        "routing number 021000021",
        "sk_live_abcdef0123456789",
        "payment_token = tok_abc123",
    ],
)
def test_instrument_shapes_are_detected(value):
    assert scan_for_instrument(value), f"undetected instrument: {value}"


@pytest.mark.parametrize(
    "value",
    [
        "order 1234567890123456789012",   # long id, fails Luhn
        "timestamp 1758153600000",
        "sha256:abc123",
        "invoice INV-2026-0918",
        "quantity 4111",
    ],
)
def test_ordinary_numbers_are_not_false_positives(value):
    """A false positive blocks legitimate work, so the Luhn check matters."""
    assert not scan_for_instrument(value), f"false positive on: {value}"


def test_assert_no_instrument_refuses_rather_than_redacts():
    with pytest.raises(PaymentBoundaryError, match="payment_instrument_in_evidence"):
        assert_no_instrument({"card": "4111111111111111"}, context="evidence")


# ----------------------------------------------------------- payment intent


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation": "payment_send"},
        {"operation": "capture_payment"},
        {"goal": "make a payment to the supplier"},
        {"goal": "transfer funds to savings"},
        {"goal": "wire transfer for invoice 12"},
        {"operation": "create_charge"},
        {"goal": "settle invoice 4821"},
        {"operation": "payout"},
    ],
)
def test_payment_intent_is_detected_from_text(kwargs):
    assert looks_like_payment(**kwargs) is not None


@pytest.mark.parametrize(
    "target",
    [
        {"domain": "api.stripe.com"},
        {"domain": "api-m.paypal.com"},
        {"domain": "api.adyen.com"},
        {"domain": "api.paystack.co"},
        {"url": "https://billing.example.com/v1/payment_intents"},
        {"url": "https://billing.example.com/v2/payouts"},
        {"url": "https://shop.example.com/v1/orders/abc/capture"},
    ],
)
def test_payment_destinations_are_detected(target):
    """A step that never says "pay" but POSTs to a payment API is still a payment."""
    assert looks_like_payment(**target) is not None


def test_declared_payment_effect_is_detected():
    assert looks_like_payment(effects=[WorkflowStepEffect.PAYMENT]) == "declared_effect:PAYMENT"


def test_instrument_persistence_intent_is_detected():
    for goal in (
        "save my card for next time",
        "remember this payment method",
        "store card on file",
        "tokenize card",
        "setup future usage",
    ):
        assert looks_like_payment(goal=goal) is not None, goal


def test_ordinary_automation_is_not_flagged():
    assert looks_like_payment(operation="fetch", goal="collect broker statements",
                              url=f"https://{DOMAIN}/statements", domain=DOMAIN) is None


@pytest.mark.parametrize(
    "goal",
    [
        "download the payroll report",
        "read the payment terms page",
        "summarise this month's paycheck",
        "find the payments dashboard and screenshot it",
        "check whether the invoice was paid",
        "list unpaid invoices",
        "export the payments ledger to CSV",
    ],
)
def test_reading_about_payments_is_not_paying(goal):
    """The boundary blocks transacting, not the word "payment".

    These are ordinary reads. Flagging them would make the automation fabric
    useless for exactly the finance admin work it is meant to absorb.
    """
    assert looks_like_payment(goal=goal) is None, goal


@pytest.mark.parametrize(
    "goal",
    [
        "complete the checkout and pay",
        "proceed to checkout",
        "confirm the purchase",
        "pay now",
        "pay the invoice",
        "add to cart and buy",
        "place order and pay",
    ],
)
def test_transacting_phrasings_are_caught(goal):
    """The phrasings a browser agent would actually use."""
    assert looks_like_payment(goal=goal) is not None, goal


# --------------------------------------------------- validator integration


def _payment_ir(**step_overrides):
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[1] = steps[1].model_copy(update=step_overrides)
    return ir.model_copy(update={"steps": steps})


def test_workflow_declaring_a_payment_effect_is_refused():
    ir = _payment_ir(effects=[WorkflowStepEffect.PAYMENT])
    report = WorkflowValidator(policy_with_domains(DOMAIN)).validate(ir)
    assert not report.ok
    assert any("PROHIBITED_EFFECT" in e and "PAYMENT" in e for e in report.errors)
    assert any("AUTOMATED_PAYMENT_PROHIBITED" in e for e in report.errors)


def test_workflow_storing_an_instrument_is_refused():
    ir = _payment_ir(effects=[WorkflowStepEffect.PAYMENT_INSTRUMENT_STORAGE])
    report = WorkflowValidator(policy_with_domains(DOMAIN)).validate(ir)
    assert not report.ok
    assert any("PAYMENT_INSTRUMENT_STORAGE" in e for e in report.errors)


def test_workflow_reaching_a_payment_provider_is_refused():
    """The important case: no payment effect declared, but the destination pays."""
    ir = _payment_ir(
        external_domain="api.stripe.com",
        input_bindings={"url": "https://api.stripe.com/v1/charges"},
        effects=[WorkflowStepEffect.NETWORK_READ],
    )
    ir = ir.model_copy(update={"external_domains": ["api.stripe.com"]})
    report = WorkflowValidator(policy_with_domains("api.stripe.com")).validate(ir)
    assert not report.ok
    assert any("AUTOMATED_PAYMENT_PROHIBITED" in e for e in report.errors)


def test_workflow_with_a_card_number_in_inputs_is_refused():
    ir = _payment_ir(input_bindings={"url": f"https://{DOMAIN}/x", "card": "4111111111111111"})
    report = WorkflowValidator(policy_with_domains(DOMAIN)).validate(ir)
    assert not report.ok
    assert any("PAYMENT_INSTRUMENT_PROHIBITED" in e for e in report.errors)


def test_workflow_whose_goal_is_payment_is_refused():
    ir = sample_ir(domain=DOMAIN).model_copy(
        update={"semantic_goal": "make a payment to the electricity supplier"}
    )
    report = WorkflowValidator(policy_with_domains(DOMAIN)).validate(ir)
    assert not report.ok
    assert any("AUTOMATED_PAYMENT_PROHIBITED" in e for e in report.errors)


def test_ordinary_workflow_still_validates():
    """The boundary must not block legitimate automation."""
    report = WorkflowValidator(policy_with_domains(DOMAIN)).validate(sample_ir(domain=DOMAIN))
    assert report.ok, report.errors


# ------------------------------------------------------------- credentials


@pytest.mark.parametrize(
    "alias",
    [
        "connector://stripe/primary",
        "connector://paypal/business",
        "connector://card/visa",
        "connector://bank_account/current",
        "connector://payment/provider",
        "connector://wallet/main",
    ],
)
def test_payment_credentials_are_refused_at_every_class(alias):
    """No class permits an instrument — not even C4 (owner, 2026-09-18)."""
    resolver = CredentialResolver()
    for credential_class in CredentialClass:
        with pytest.raises(PolicyError, match="payment_instrument_credential_prohibited"):
            resolver.register(
                CredentialAlias(alias=alias, credential_class=credential_class, admitted=True)
            )


def test_ordinary_service_password_is_still_permitted():
    """The owner said n8n *can* hold passwords; only payments are prohibited."""
    resolver = CredentialResolver()
    resolver.register(
        CredentialAlias(
            alias="connector://gmail/primary",
            credential_class=CredentialClass.C4_LOW_RISK_INTEGRATION,
            n8n_credential_id="cred_1", admitted=True,
        )
    )
    assert resolver.resolve_for_compilation(["connector://gmail/primary"]) == {
        "connector://gmail/primary": "cred_1"
    }


# ------------------------------------------------- the A4 payment exception


def test_payment_requires_a4():
    with pytest.raises(PaymentBoundaryError, match="payment_requires_a4"):
        assert_payment_action_is_owner_approved(
            action_class=ActionClass.A3, owner_approved=True,
            approval_binding={"payee": "x", "amount": "10", "currency": "USD", "reference": "r"},
        )


def test_payment_requires_fresh_owner_approval():
    with pytest.raises(PaymentBoundaryError, match="requires_fresh_owner_approval"):
        assert_payment_action_is_owner_approved(
            action_class=ActionClass.A4, owner_approved=False,
            approval_binding={"payee": "x", "amount": "10", "currency": "USD", "reference": "r"},
        )


def test_payment_approval_must_bind_payee_amount_currency_reference():
    with pytest.raises(PaymentBoundaryError, match="binding_incomplete"):
        assert_payment_action_is_owner_approved(
            action_class=ActionClass.A4, owner_approved=True,
            approval_binding={"payee": "x", "amount": "10"},
        )


def test_payment_approval_may_not_carry_an_instrument():
    """"without saving my payment options" — the binding records what, not how."""
    with pytest.raises(PaymentBoundaryError, match="payment_instrument_in"):
        assert_payment_action_is_owner_approved(
            action_class=ActionClass.A4, owner_approved=True,
            approval_binding={
                "payee": "Utility Co", "amount": "42.00", "currency": "USD",
                "reference": "INV-1", "card": "4111111111111111",
            },
        )


def test_fully_bound_owner_approved_payment_is_permitted():
    """The one legitimate path: A4, fresh approval, fully bound, no instrument."""
    assert_payment_action_is_owner_approved(
        action_class=ActionClass.A4, owner_approved=True,
        approval_binding={
            "payee": "Utility Co", "amount": "42.00", "currency": "USD", "reference": "INV-1",
        },
    )


def test_automated_context_never_gets_the_exception():
    """Even A4-with-approval is irrelevant to an automation: it cannot pay at all."""
    with pytest.raises(PaymentBoundaryError, match="automated_payment_prohibited"):
        assert_not_automated_payment(
            operation="payment_send", context="standing_automation_run"
        )
