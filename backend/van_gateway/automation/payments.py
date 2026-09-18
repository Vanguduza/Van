"""Owner decision 2026-09-18 — the payment boundary.

`docs/SECURITY_POLICY.md` §Payments, in the owner's words: *"making payments is
strictly forbidden and can only be done under my strict orders but still without
saving my payment options."*

Two separable rules come out of that, and this module is where both live so
neither drifts:

1. **A payment is never automated.** Not by a workflow, a schedule, a standing
   intent, a browser task or an agent. It is an A4 native action requiring a
   fresh owner approval bound to the exact payee, amount, currency and reference.
   A prior approval is never reusable, so "pay the same invoice again" is a new
   approval, not a replay.

2. **A payment instrument is never stored.** Card numbers, CVVs, bank details,
   wallet credentials and provider tokens must not reach the n8n credential
   store, a browser profile, a workflow artifact, evidence or logs — at any
   credential class. "Remember this card" is refused rather than honoured.

The detectors here are deliberately eager. A false positive costs a refused
workflow and a clear error; a false negative costs money that is hard to recall.
"""

from __future__ import annotations

import json
import re
from typing import Any

from van_gateway.automation.models import PAYMENT_EFFECTS, WorkflowStepEffect
from van_gateway.models import ActionClass


class PaymentBoundaryError(ValueError):
    """Raised when something would automate a payment or persist an instrument."""


#: Instrument shapes. These are what "without saving my payment options" means in
#: bytes: a card PAN, a CVV beside it, an IBAN, a sort code/account pair, and the
#: live secret keys of the common payment providers.
_INSTRUMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 13-19 digit PAN, optionally space/dash grouped. Bounded so long digit runs
    # (timestamps, ids) do not match.
    ("card_pan", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")),
    ("cvv", re.compile(r"(?i)\b(?:cvv|cvc|cvv2|csc|security[ _-]?code)\b\s*[:=]?\s*\d{3,4}\b")),
    ("expiry", re.compile(r"(?i)\b(?:exp(?:iry|iration)?)\b\s*[:=]?\s*(?:0[1-9]|1[0-2])\s*/\s*\d{2,4}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("sort_code", re.compile(r"(?i)\bsort[ _-]?code\b\s*[:=]?\s*\d{2}-?\d{2}-?\d{2}\b")),
    ("account_number", re.compile(r"(?i)\b(?:bank[ _-]?)?account[ _-]?(?:number|no)\b\s*[:=]?\s*\d{6,17}\b")),
    ("routing_number", re.compile(r"(?i)\b(?:routing|aba)[ _-]?(?:number|no)?\b\s*[:=]?\s*\d{9}\b")),
    ("stripe_secret", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,}\b")),
    ("paypal_secret", re.compile(r"(?i)\bpaypal[_-]?(?:client[_-]?)?secret\b\s*[:=]\s*\S+")),
    ("payment_token", re.compile(r"(?i)\b(?:payment|card|wallet)[ _-]?token\b\s*[:=]\s*\S+")),
)

#: Intent shapes. A step that says it is paying is treated as paying, regardless
#: of the effect list it declared — a workflow cannot mislabel its way past this.
#:
#: A bare "pay" is deliberately NOT a trigger: "payroll report", "payment terms"
#: and "paycheck summary" are ordinary reads. What triggers is "pay" in a
#: transacting construction — as a conjoined verb ("and pay"), with an object
#: ("pay the invoice"), or with an immediacy adverb ("pay now").
_PAYMENT_INTENT = re.compile(
    r"(?i)(?:"
    r"\bmake[ _-]+a?[ _-]*payment\b"
    r"|\bpay(?:ment)?[ _-]+(?:send|submit|execute|create|initiate|capture)\b"
    r"|\bsend[ _-]+(?:money|funds|payment)\b"
    r"|\btransfer[ _-]+funds\b|\bwire[ _-]+transfer\b"
    r"|\bcharge[ _-]+(?:card|customer)\b|\bcreate[ _-]+charge\b|\bcapture[ _-]+payment\b"
    r"|\bcheckout[ _-]+(?:complete|submit)\b"
    r"|\b(?:complete|submit|confirm|finish|proceed[ _-]+to)[ _-]+(?:the[ _-]+)?"
    r"(?:checkout|purchase|order[ _-]+and[ _-]+pay|payment)\b"
    r"|\band[ _-]+pay\b|\bthen[ _-]+pay\b"
    r"|\bpay[ _-]+(?:now|the|this|for|invoice|bill|balance)\b"
    r"|\bplace[ _-]+order[ _-]+and[ _-]+pay\b"
    r"|\bpayout\b|\bdisburse\b|\bsettle[ _-]+(?:invoice|bill|balance)\b|\bremit\b"
    r"|\badd[ _-]+to[ _-]+cart[ _-]+and[ _-]+(?:buy|purchase|pay)\b"
    r")"
)

#: Persistence shapes. "Save my card for next time" in all its usual spellings.
#: ``_DET`` absorbs an optional determiner ("my", "this", "the"), so
#: "remember this payment method" reads the same as "remember my card".
_DET = r"(?:[ _-]+(?:my|this|that|the|a))?[ _-]+"
_INSTRUMENT_PERSISTENCE = re.compile(
    r"(?i)\b(?:"
    rf"save{_DET}(?:card|payment|bank)"
    rf"|remember{_DET}(?:card|payment)"
    rf"|store{_DET}(?:card|payment)"
    rf"|vault{_DET}(?:card|payment)"
    r"|tokeni[sz]e[ _-]+card"
    r"|setup[ _-]+future[ _-]+usage"
    r"|save[ _-]+for[ _-]+later"
    r"|card[ _-]+on[ _-]+file"
    r")\b"
)

#: Payment provider endpoints. Reaching one from an automation is a payment path
#: even if nothing in the step says "pay".
_PAYMENT_ENDPOINT = re.compile(
    r"(?i)(?:"
    r"api\.stripe\.com|api\.paypal\.com|api-m\.paypal\.com|api\.adyen\.com"
    r"|[a-z0-9-]+\.adyen\.com|api\.braintreegateway\.com|api\.squareup\.com"
    r"|api\.checkout\.com|api\.mollie\.com|api\.razorpay\.com|api\.paystack\.co"
    r"|api\.flutterwave\.com|api\.wise\.com|api\.gocardless\.com"
    r")"
)

#: Provider path fragments that move money, for a host not in the list above.
_PAYMENT_PATH = re.compile(
    r"(?i)/v\d+/(?:payment_intents|payments|charges|payouts|transfers|refunds"
    r"|payment_methods|setup_intents|orders/[^/]+/capture)\b"
)


def scan_for_instrument(payload: Any) -> list[str]:
    """Return the names of instrument patterns present. Empty means clean."""
    blob = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    hits: list[str] = []
    for name, pattern in _INSTRUMENT_PATTERNS:
        match = pattern.search(blob)
        if match is None:
            continue
        if name == "card_pan" and not _luhn(re.sub(r"[ -]", "", match.group(0))):
            # A 13-19 digit run that fails Luhn is an id, not a card number.
            continue
        hits.append(name)
    return hits


def _luhn(digits: str) -> bool:
    """Luhn check, so ordinary long numbers are not mistaken for card numbers."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def assert_no_instrument(payload: Any, *, context: str) -> None:
    """Refuse rather than redact, so a stored instrument is a loud failure."""
    hits = scan_for_instrument(payload)
    if hits:
        raise PaymentBoundaryError(f"payment_instrument_in_{context}:{','.join(sorted(hits))}")


def looks_like_payment(
    *,
    operation: str = "",
    goal: str = "",
    url: str = "",
    domain: str = "",
    effects: list[WorkflowStepEffect] | None = None,
) -> str | None:
    """Return the reason this is a payment, or None.

    Checks declared effects, stated intent and destination independently: a step
    is a payment if *any* of them say so, so omitting the PAYMENT effect while
    POSTing to a payment endpoint does not get through.
    """
    for effect in effects or []:
        if effect in PAYMENT_EFFECTS:
            return f"declared_effect:{effect.value}"

    text = " ".join(part for part in (operation, goal) if part)
    if text:
        if _PAYMENT_INTENT.search(text):
            return "payment_intent_in_text"
        if _INSTRUMENT_PERSISTENCE.search(text):
            return "instrument_persistence_in_text"

    target = " ".join(part for part in (url, domain) if part)
    if target:
        if _PAYMENT_ENDPOINT.search(target):
            return "payment_provider_endpoint"
        if _PAYMENT_PATH.search(target):
            return "payment_api_path"
    return None


def assert_not_automated_payment(
    *,
    operation: str = "",
    goal: str = "",
    url: str = "",
    domain: str = "",
    effects: list[WorkflowStepEffect] | None = None,
    context: str,
) -> None:
    """The core rule: no automation path may move money."""
    reason = looks_like_payment(
        operation=operation, goal=goal, url=url, domain=domain, effects=effects
    )
    if reason is not None:
        raise PaymentBoundaryError(f"automated_payment_prohibited_in_{context}:{reason}")


def assert_payment_action_is_owner_approved(
    *,
    action_class: ActionClass,
    owner_approved: bool,
    approval_binding: dict[str, Any] | None,
    context: str = "payment_action",
) -> None:
    """The narrow exception: a payment as an A4 native action, freshly approved.

    The binding must name payee, amount, currency and reference, so the approval
    the owner gave is the payment that happens — a re-used or under-specified
    approval is refused.
    """
    if action_class is not ActionClass.A4:
        raise PaymentBoundaryError(f"payment_requires_a4:{context}:{action_class.value}")
    if not owner_approved:
        raise PaymentBoundaryError(f"payment_requires_fresh_owner_approval:{context}")

    binding = approval_binding or {}
    required = ("payee", "amount", "currency", "reference")
    missing = [field for field in required if not binding.get(field)]
    if missing:
        raise PaymentBoundaryError(
            f"payment_approval_binding_incomplete:{context}:{','.join(missing)}"
        )
    # The instrument is supplied under owner control at payment time and never
    # travels through, or is retained by, VAN.
    assert_no_instrument(binding, context=f"{context}_approval_binding")


__all__ = [
    "PaymentBoundaryError",
    "assert_no_instrument",
    "assert_not_automated_payment",
    "assert_payment_action_is_owner_approved",
    "looks_like_payment",
    "scan_for_instrument",
]
