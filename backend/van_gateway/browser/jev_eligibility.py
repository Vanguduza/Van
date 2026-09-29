"""Programme B contract B2 — pre-Jev browser observation eligibility.

Decides, before any byte of a browser observation can reach ``dial-jev``, whether the
observation may be offered to Jev's ``PROPOSE_ACTION`` lane at all, and if so builds the
minimal purpose-specific payload.

Invariant: only ``PUBLIC_ELIGIBLE`` and ``SANITIZABLE_ELIGIBLE`` ever carry a
``jev_payload``. Every other outcome — and every unknown or ambiguous input — is a
fallback with ``jev_payload: None``. Nothing here is eligible by default.

The payload is built to pass the DDS Jev egress checker *unchanged*
(``judgment/data-policy.mjs`` + ``auxiliary/data-classification.mjs``): the element text
field is ``label`` (never ``name``), there are no timestamp keys, no prohibited fields, no
URLs, no page/document contents, no owner identity and no stable identifiers — target ids
are opaque ``t_<random>`` values minted fresh for every observation. The checker is the
floor, not the goal: this classifier refuses far more than the checker would.

Decision precedence when several signals fire (all are recorded in ``reasons``):
CREDENTIAL > TRADING_PROTECTED > POLICY_DENIED > OWNER_PRIVATE > eligible.

Reuses the existing VAN browser policy rather than inventing a second one:
``input_protocol.NAVIGABLE_SCHEMES`` (scheme), ``subagent.plausible_hostname`` (no literal
IPs / single-label hosts), ``BrowserPolicyEngine.assess_injection`` and
``scan_for_secrets`` (page content), ``automation.payments`` (instruments and payment
intent/endpoints) and the ``config/browser/profiles.yaml`` profile posture. VAN has no
domain denylist, so the small set of never-offered host classes below is local to this
module and additive only.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from van_gateway.automation.payments import looks_like_payment, scan_for_instrument
from van_gateway.browser.input_protocol import NAVIGABLE_SCHEMES
from van_gateway.browser.models import BrowserObservation, InjectionAssessment
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.subagent import plausible_hostname

PAYLOAD_SCHEMA = "van.browser.action_payload.v1"
JEV_MODULE_ID = "van.browser.ultrafast.action.v1"
CLOSED_OPERATION_SET = ("click", "fill", "select", "scroll", "press_key", "done", "abstain")
MAX_LABEL_CHARS = 64
MAX_TARGETS = 40


class Eligibility(str, Enum):
    PUBLIC_ELIGIBLE = "PUBLIC_ELIGIBLE"
    SANITIZABLE_ELIGIBLE = "SANITIZABLE_ELIGIBLE"
    OWNER_PRIVATE = "OWNER_PRIVATE"
    CREDENTIAL = "CREDENTIAL"
    TRADING_PROTECTED = "TRADING_PROTECTED"
    POLICY_DENIED = "POLICY_DENIED"


ELIGIBLE = frozenset({Eligibility.PUBLIC_ELIGIBLE, Eligibility.SANITIZABLE_ELIGIBLE})
_PRECEDENCE = (
    Eligibility.CREDENTIAL,
    Eligibility.TRADING_PROTECTED,
    Eligibility.POLICY_DENIED,
    Eligibility.OWNER_PRIVATE,
)

# --------------------------------------------------------------------------- origins

#: Explicit public allowlist. Only these hosts can be PUBLIC_ELIGIBLE, and only these can
#: override an authenticated-session signal. Suffix match on a dot boundary.
DEFAULT_PUBLIC_ALLOWLIST = frozenset({
    "wikipedia.org", "docs.python.org", "developer.mozilla.org", "www.bbc.co.uk",
    "www.bbc.com", "www.reuters.com", "apnews.com", "duckduckgo.com", "www.bing.com",
    "news.ycombinator.com", "arxiv.org", "www.w3.org", "nodejs.org", "pypi.org",
    "docs.github.com", "www.gov.uk", "www.nhs.uk", "www.weather.gov",
})

#: Owner-account origins: a page here is the owner's data whatever the session says.
_OWNER_ACCOUNT_HOSTS = frozenset({
    "mail.google.com", "drive.google.com", "docs.google.com", "calendar.google.com",
    "contacts.google.com", "photos.google.com", "myaccount.google.com", "admin.google.com",
    "outlook.live.com", "outlook.office.com", "outlook.office365.com", "onedrive.live.com",
    "sharepoint.com", "icloud.com", "dropbox.com", "notion.so", "slack.com",
    "console.aws.amazon.com", "console.cloud.google.com", "portal.azure.com",
    "dashboard.stripe.com", "notebooklm.google.com", "web.whatsapp.com", "mail.proton.me",
})
_OWNER_HOST_PREFIXES = ("mail.", "webmail.", "admin.", "console.", "portal.", "dashboard.",
                        "my.", "account.", "accounts.", "intranet.")
_OWNER_PATH = re.compile(
    r"(?i)/(?:admin|settings|account|accounts|preferences|profile|inbox|mail|messages|"
    r"dashboard|billing|orders|my|me|watchlist|wp-admin|user|users)(?:/|$)"
)

#: Auth-flow origins/paths → CREDENTIAL.
_AUTH_HOST_PREFIXES = ("login.", "signin.", "auth.", "sso.", "id.", "idp.", "accounts.")
_AUTH_PATH = re.compile(
    r"(?i)/(?:login|log-in|signin|sign-in|signup|sign-up|auth|oauth2?|sso|saml|2fa|mfa|otp|"
    r"verify|verification|password|reset-password|forgot|checkout|payment|pay)(?:/|$|\?)"
)

#: Broker / trading / banking / payment origins and VATI surfaces → TRADING_PROTECTED.
_FINANCIAL_HOSTS = frozenset({
    "interactivebrokers.com", "ibkr.com", "schwab.com", "fidelity.com", "etrade.com",
    "robinhood.com", "oanda.com", "fxcm.com", "ig.com", "plus500.com", "etoro.com",
    "binance.com", "coinbase.com", "kraken.com", "tradingview.com", "metatrader5.com",
    "mql5.com", "trading212.com", "hl.co.uk", "vanguard.com", "chase.com",
    "bankofamerica.com", "wellsfargo.com", "barclays.co.uk", "hsbc.com", "hsbc.co.uk",
    "lloydsbank.com", "natwest.com", "monzo.com", "revolut.com", "paypal.com", "wise.com",
    "americanexpress.com", "capitalone.com", "citi.com", "santander.co.uk",
})
_FINANCIAL_HOST_TOKENS = frozenset({
    "bank", "banking", "broker", "brokerage", "trade", "trading", "trader", "forex", "fx",
    "crypto", "wallet", "invest", "investing", "securities", "vati",
})
_TRADING_PATH = re.compile(r"(?i)/(?:trade|trading|brokerage|portfolio|positions|vati)(?:/|$)")
_TRADING_TEXT = re.compile(
    r"(?i)\b(?:stop[- ]?loss|take[- ]?profit|leverage|lot size|pips?|open positions?|"
    r"close position|market order|limit order|order ticket|margin (?:level|call)|"
    r"buy/sell|vati|place trade)\b"
)

#: Host classes never offered to a model: cloud metadata and private-name TLDs.
_DENIED_HOSTS = frozenset({"metadata.google.internal", "metadata", "localhost"})
_DENIED_SUFFIXES = (".internal", ".local", ".lan", ".home.arpa", ".onion", ".localhost",
                    ".corp", ".intranet")

# ---------------------------------------------------------------------- controls

_CREDENTIAL_INPUT_TYPES = frozenset({"password"})
_CREDENTIAL_AUTOCOMPLETE = re.compile(
    r"(?i)^(?:current-password|new-password|one-time-code|cc-[a-z-]+|webauthn)$"
)
_CREDENTIAL_TEXT = re.compile(
    r"(?i)\b(?:pass(?:word|phrase|code)|pin(?: code)?|otp|one[- ]time (?:code|password)|"
    r"verification code|security code|2fa|two[- ]factor|authenticator|mfa|passkey|"
    r"cvv2?|cvc|card number|card holder|cardholder|expiry|expiration date|"
    r"sort code|routing number|iban|recovery code|backup code|secret)\b"
)
#: Controls that lead *into* an auth flow. They are withheld from Jev (never a target),
#: which is stricter than offering them; they do not by themselves make a page a credential page.
_AUTH_ENTRY_TEXT = re.compile(r"(?i)\b(?:sign[- ]?in|log[- ]?in|sign[- ]?up|register|create account)\b")
#: Evidence the session is signed in, wherever it appears on the page.
_SIGNED_IN_TEXT = re.compile(
    r"(?i)\b(?:sign[- ]?out|log[- ]?out|signed in as|logged in as|my account|your account|"
    r"switch account|welcome back|hi,)\b"
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_HANDLE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{2,}")
_DIGIT_RUN = re.compile(r"\+?\d[\d \-.()]*\d")
_ACCOUNT_TOKEN = re.compile(r"\b(?=[A-Za-z0-9-]*[A-Za-z])(?=(?:[A-Za-z-]*\d){3,})[A-Za-z0-9-]{4,}\b")
_TIME_OF_DAY = re.compile(r"\b\d{1,2}:\d{2}\b")
_DATE = re.compile(
    r"(?i)\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2} (?:jan|feb|mar|apr|may|jun|"
    r"jul|aug|sep|oct|nov|dec)[a-z]* \d{4})\b"
)

_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox", "checkbox", "radio", "tab",
    "menuitem", "option", "listbox", "switch", "slider", "spinbutton",
})
_ROLE_BY_METHOD = {"click": "button", "tap": "button", "fill": "textbox", "type": "textbox",
                   "input": "textbox", "select": "combobox", "selectoption": "combobox"}


# ------------------------------------------------------------------------ contract


@dataclass(frozen=True)
class PageContext:
    """What the Browser Fabric knows about the page that ``BrowserObservation`` does not carry.

    ``session_authenticated`` of ``None`` means unknown, and unknown is resolved from the
    profile posture: only an ``authentication: none`` profile counts as signed out.
    """

    url: str
    profile_alias: str
    session_authenticated: bool | None = None
    page_title: str = ""


@dataclass(frozen=True)
class EligibilityDecision:
    eligibility: Eligibility
    reasons: tuple[str, ...]
    data_class: str | None
    jev_payload: dict[str, Any] | None
    #: Local only — maps each opaque ``t_`` id back to its index in ``observation.controls``.
    #: Never part of ``jev_payload`` and never sent to Jev.
    target_index: Mapping[str, int] = field(default_factory=dict)

    @property
    def eligible(self) -> bool:
        return self.eligibility in ELIGIBLE

    def as_contract(self) -> dict[str, Any]:
        """The B2 wire shape (``target_index`` stays inside VAN)."""
        return {
            "eligibility": self.eligibility.value,
            "reasons": list(self.reasons),
            "data_class": self.data_class,
            "jev_payload": self.jev_payload,
        }


# ------------------------------------------------------------------------- helpers


def _host_matches(host: str, domains: Iterable[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _control_text(control: Mapping[str, Any]) -> str:
    parts = []
    for key in ("label", "name", "text", "description", "aria_label", "placeholder", "title",
                "value", "role", "type", "input_type", "autocomplete", "method"):
        value = control.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _raw_label(control: Mapping[str, Any]) -> str:
    for key in ("label", "name", "aria_label", "text", "description", "placeholder", "title"):
        value = control.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def private_label_findings(label: str, owner_terms: Iterable[str] = ()) -> list[str]:
    """Why a label cannot leave VAN. Empty means the label looks public."""
    found: list[str] = []
    if _EMAIL.search(label):
        found.append("EMAIL")
    if _HANDLE.search(label):
        found.append("HANDLE")
    for run in _DIGIT_RUN.findall(label):
        if sum(ch.isdigit() for ch in run) >= 5:
            found.append("DIGIT_RUN")
            break
    if _ACCOUNT_TOKEN.search(label):
        found.append("ACCOUNT_LIKE_TOKEN")
    if _TIME_OF_DAY.search(label) or _DATE.search(label):
        found.append("TIMESTAMP")
    if scan_for_instrument(label):
        found.append("PAYMENT_INSTRUMENT")
    lowered = label.lower()
    for term in owner_terms:
        term = term.strip().lower()
        if len(term) >= 2 and re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered):
            found.append("OWNER_PROFILE_TERM")
            break
    return found


def _mint(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


# ---------------------------------------------------------------------- classifier


def classify_observation(
    observation: BrowserObservation,
    page: PageContext | None,
    *,
    owner_terms: Iterable[str] = (),
    profiles: Mapping[str, Mapping[str, Any]] | None = None,
    public_allowlist: Iterable[str] = DEFAULT_PUBLIC_ALLOWLIST,
    action_class_ceiling: str = "A1",
    observation_epoch: str | None = None,
) -> EligibilityDecision:
    """B2 — classify one observation; build a Jev payload only when eligible.

    ``profiles`` defaults to ``config/browser/profiles.yaml`` via the shared loader.
    ``owner_terms`` are the owner's personal names/handles when the caller has them; a
    label containing one is private.
    """
    signals: dict[Eligibility, list[str]] = {e: [] for e in _PRECEDENCE}

    def deny(cls: Eligibility, reason: str) -> None:
        signals[cls].append(reason)

    if not isinstance(observation, BrowserObservation):
        return _fallback(Eligibility.POLICY_DENIED, ["AMBIGUOUS_OBSERVATION_TYPE"])
    if page is None or not isinstance(page, PageContext):
        return _fallback(Eligibility.POLICY_DENIED, ["AMBIGUOUS_PAGE_CONTEXT_MISSING"])

    # ---- origin (reuses the VAN navigation/hostname policy)
    url = page.url.strip()
    if not url.lower().startswith(NAVIGABLE_SCHEMES):
        return _fallback(Eligibility.POLICY_DENIED, ["POLICY_SCHEME_NOT_NAVIGABLE"])
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return _fallback(Eligibility.POLICY_DENIED, ["AMBIGUOUS_URL_UNPARSEABLE"])
    path = parts.path or "/"
    if not host or not plausible_hostname(host):
        deny(Eligibility.POLICY_DENIED, "POLICY_HOST_NOT_PLAUSIBLE")
    if host in _DENIED_HOSTS or host.endswith(_DENIED_SUFFIXES):
        deny(Eligibility.POLICY_DENIED, "POLICY_HOST_DENIED")
    if parts.username or parts.password:
        deny(Eligibility.CREDENTIAL, "CREDENTIAL_IN_URL")

    allowlisted = bool(host) and _host_matches(host, public_allowlist)

    # ---- profile / session posture
    if profiles is None:
        from van_gateway.automation.policy import load_browser_policy

        profiles = load_browser_policy().profiles
    profile = profiles.get(page.profile_alias)
    if profile is None:
        deny(Eligibility.POLICY_DENIED, "AMBIGUOUS_PROFILE_NOT_ADMITTED")
        signed_out_profile = False
    else:
        signed_out_profile = str(profile.get("authentication", "")).strip().lower() == "none"
    authenticated = page.session_authenticated
    if authenticated is None:
        authenticated = not signed_out_profile
    if authenticated and not allowlisted:
        deny(Eligibility.OWNER_PRIVATE, "OWNER_AUTHENTICATED_SESSION")
    if not signed_out_profile and not allowlisted:
        deny(Eligibility.OWNER_PRIVATE, "OWNER_PROFILE_NOT_PUBLIC")

    # ---- owner-account origins (the allowlist never overrides these)
    if host in _OWNER_ACCOUNT_HOSTS or _host_matches(host, _OWNER_ACCOUNT_HOSTS) or host.startswith(_OWNER_HOST_PREFIXES):
        deny(Eligibility.OWNER_PRIVATE, "OWNER_ACCOUNT_ORIGIN")
    if _OWNER_PATH.search(path):
        deny(Eligibility.OWNER_PRIVATE, "OWNER_ACCOUNT_PATH")

    # ---- auth-flow origins
    if host.startswith(_AUTH_HOST_PREFIXES) or _AUTH_PATH.search(path):
        deny(Eligibility.CREDENTIAL, "CREDENTIAL_AUTH_FLOW_ORIGIN")

    # ---- financial / trading origins
    host_tokens = set(re.split(r"[.\-]", host))
    if _host_matches(host, _FINANCIAL_HOSTS) or host_tokens & _FINANCIAL_HOST_TOKENS:
        deny(Eligibility.TRADING_PROTECTED, "TRADING_FINANCIAL_ORIGIN")
    if _TRADING_PATH.search(path):
        deny(Eligibility.TRADING_PROTECTED, "TRADING_PATH")
    payment = looks_like_payment(url=url, domain=host)
    if payment:
        deny(Eligibility.CREDENTIAL, f"CREDENTIAL_PAYMENT:{payment}")

    # ---- page content (reuses BrowserPolicyEngine containment)
    content = {"controls": observation.controls, "extraction": observation.extraction,
               "title": page.page_title}
    scanned = BrowserPolicyEngine.assess_injection(content)
    if InjectionAssessment.NONE_DETECTED is not scanned or \
            observation.injection_assessment is not InjectionAssessment.NONE_DETECTED:
        deny(Eligibility.POLICY_DENIED, "POLICY_INJECTION_SUSPECTED")
    if BrowserPolicyEngine.scan_for_secrets(content):
        deny(Eligibility.CREDENTIAL, "CREDENTIAL_SECRET_MATERIAL")
    if scan_for_instrument(content):
        deny(Eligibility.CREDENTIAL, "CREDENTIAL_PAYMENT_INSTRUMENT")
    page_text = " ".join([page.page_title, _flatten(observation.extraction)])
    if _SIGNED_IN_TEXT.search(page_text):
        deny(Eligibility.OWNER_PRIVATE, "OWNER_SIGNED_IN_EVIDENCE")
    if _TRADING_TEXT.search(page_text):
        deny(Eligibility.TRADING_PROTECTED, "TRADING_PAGE_TEXT")
    if private_label_findings(page.page_title, owner_terms):
        deny(Eligibility.OWNER_PRIVATE, "OWNER_PRIVATE_TITLE")

    # ---- controls → targets
    targets: list[dict[str, str]] = []
    target_index: dict[str, int] = {}
    withheld = 0
    for index, raw in enumerate(observation.controls):
        if not isinstance(raw, Mapping):
            deny(Eligibility.POLICY_DENIED, "AMBIGUOUS_CONTROL_SHAPE")
            continue
        text = _control_text(raw)
        input_type = str(raw.get("input_type") or raw.get("type") or "").strip().lower()
        autocomplete = str(raw.get("autocomplete") or "").strip()
        if input_type in _CREDENTIAL_INPUT_TYPES or _CREDENTIAL_AUTOCOMPLETE.match(autocomplete) \
                or _CREDENTIAL_TEXT.search(text):
            deny(Eligibility.CREDENTIAL, "CREDENTIAL_FIELD")
            continue
        if looks_like_payment(operation=text):
            deny(Eligibility.CREDENTIAL, "CREDENTIAL_PAYMENT_CONTROL")
            continue
        if _TRADING_TEXT.search(text):
            deny(Eligibility.TRADING_PROTECTED, "TRADING_CONTROL")
            continue
        if _SIGNED_IN_TEXT.search(text):
            deny(Eligibility.OWNER_PRIVATE, "OWNER_SIGNED_IN_EVIDENCE")
            continue
        label = _raw_label(raw)
        findings = private_label_findings(label, owner_terms)
        if findings:
            deny(Eligibility.OWNER_PRIVATE, "OWNER_PRIVATE_LABEL:" + ",".join(sorted(set(findings))))
            continue
        if not label or _AUTH_ENTRY_TEXT.search(label):
            withheld += 1
            continue
        role = str(raw.get("role") or "").strip().lower()
        if role not in _ROLES:
            role = _ROLE_BY_METHOD.get(str(raw.get("method") or "").strip().lower(), "generic")
        target_id = _mint("t")
        target_index[target_id] = index
        targets.append({"target_id": target_id, "role": role, "label": label[:MAX_LABEL_CHARS]})
        if len(targets) > MAX_TARGETS:
            deny(Eligibility.POLICY_DENIED, "AMBIGUOUS_TOO_MANY_TARGETS")
            break

    if action_class_ceiling not in ("A0", "A1", "A2", "A3"):
        deny(Eligibility.POLICY_DENIED, f"POLICY_ACTION_CLASS_NOT_PROPOSABLE:{action_class_ceiling}")

    reasons = [r for cls in _PRECEDENCE for r in dict.fromkeys(signals[cls])]
    for cls in _PRECEDENCE:
        if signals[cls]:
            return _fallback(cls, reasons)

    # ---- eligible: build the minimal payload
    public = allowlisted and signed_out_profile and not authenticated and withheld == 0
    eligibility = Eligibility.PUBLIC_ELIGIBLE if public else Eligibility.SANITIZABLE_ELIGIBLE
    data_class = "PUBLIC" if public else "INTERNAL_SANITIZED"
    reasons.append("PUBLIC_ALLOWLISTED_ORIGIN" if allowlisted else "PUBLIC_UNLISTED_ORIGIN")
    if withheld:
        reasons.append(f"TARGETS_WITHHELD:{withheld}")
    payload = {
        "payload_schema": PAYLOAD_SCHEMA,
        "effect_direction": "PROPOSE_ACTION",
        "closed_operation_set": list(CLOSED_OPERATION_SET),
        "origin_class": "PUBLIC_ALLOWLISTED" if allowlisted else "PUBLIC_UNLISTED",
        "targets": targets,
        "action_class_ceiling": action_class_ceiling,
        "observation_epoch": observation_epoch or _mint("e"),
    }
    return EligibilityDecision(eligibility, tuple(reasons), data_class, payload, target_index)


def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(v) for v in value)
    return ""


def _fallback(eligibility: Eligibility, reasons: list[str]) -> EligibilityDecision:
    return EligibilityDecision(eligibility, tuple(reasons), None, None, {})


__all__ = [
    "CLOSED_OPERATION_SET",
    "DEFAULT_PUBLIC_ALLOWLIST",
    "ELIGIBLE",
    "Eligibility",
    "EligibilityDecision",
    "JEV_MODULE_ID",
    "PAYLOAD_SCHEMA",
    "PageContext",
    "classify_observation",
    "private_label_findings",
]
