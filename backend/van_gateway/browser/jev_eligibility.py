"""Programme B contract B2 — browser privacy eligibility for the Jev proposal lane.

Decides whether one browser observation may be described to ``dial-jev`` PROPOSE_ACTION
(module ``van.browser.ultrafast.action.v1``) and, if so, builds the only payload shape VAN
may send: ``van.browser.action_payload.v1`` (DDS
``agent-system/schemas/jev/browser-action-payload.v1.schema.json``, which names this file as
its producer). The eligibility vocabulary is the one the DDS B2 corpus and privacy test
already consume (``tests/fixtures/jev/browser-payload-corpus.v1.json``).

Rules, all deny-biased:

* Only ``PUBLIC_ELIGIBLE`` and ``SANITIZABLE_ELIGIBLE`` carry a ``jev_payload``. Every other
  class carries ``None``; the router must not call Jev for them.
* Unknown is ineligible. An observation type that carries no origin/session facts, an
  unadmitted profile, a non-https scheme, an IDN or literal-IP host, an adversarial page, zero
  usable targets or too many targets are ``POLICY_DENIED``. An unknown authentication or cookie
  state is treated as an authenticated session (``OWNER_PRIVATE``).
* A label that itself carries private data (email, handle, phone/account digit runs, card,
  IBAN, account-like token, timestamp, owner-profile term) makes the *observation*
  ineligible. It is never "sanitised" into a shorter label that still leaks. Elements are
  only *withheld* for reasons that are not private data: a URL in the label, homoglyph or
  zero-width obfuscation, an unknown role, an over-long or empty label, a sign-in entry
  point, a personal-data input field, a hidden element.
* Nothing from the page other than role and a short label is sent: no URL, host, title,
  timestamp, selector, element ref, owner identity, account id or page content. Target ids
  are random per observation (``t_`` + 16 hex) and map back to VAN element refs only through
  ``EligibilityResult.target_map``, which never leaves VAN. The epoch is random too; a
  caller-provided epoch is never forwarded because it could be a timestamp.

Classes and precedence (first present wins; every finding is still listed in ``reasons``,
grouped in this order):

``POLICY_DENIED`` > ``CREDENTIAL`` > ``TRADING_PROTECTED`` > ``OWNER_PRIVATE``.

Policy reuse: the profile posture comes from ``config/browser/profiles.yaml`` and the
owner-admitted domains from ``config/browser/domains.yaml`` through the existing
``load_browser_policy()``; the domains.yaml ``prohibited`` categories (private network,
cloud metadata, broker order surfaces) are enforced as host checks; literal-IP handling
reuses the automation ``DomainPolicy`` SSRF network list; secret and injection scanning reuse
``BrowserPolicyEngine``. The Jev-specific additions (public allowlist, sensitive host/path
tables, owner-profile terms) live in ``JevEligibilityPolicy``. The public allowlist is empty
by default: populating it is an owner policy decision, so by default nothing is
``PUBLIC_ELIGIBLE`` and public origins can at most be ``SANITIZABLE_ELIGIBLE``.

Observation model: VAN's existing ``BrowserObservation`` (browser/models.py) carries Stagehand
controls but no URL, profile, authentication or cookie state, so it cannot be classified and
is ``POLICY_DENIED`` (``AMBIGUOUS_OBSERVATION_TYPE``). ``JevPageObservation`` below is the
minimal frozen record an adapter must fill in to be classified.

Never authority: an eligible result only permits *asking* Jev for a proposal. Jev never
executes, and every proposal is re-validated VAN-side (B1/B5).
"""

from __future__ import annotations

import ipaddress
import json
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, unquote, urlsplit

from van_gateway.automation.policy import BrowserPolicy, DomainPolicy, load_browser_policy
from van_gateway.browser.models import InjectionAssessment
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.models import ActionClass

# --------------------------------------------------------------------------- contract

PAYLOAD_SCHEMA = "van.browser.action_payload.v1"
EFFECT_DIRECTION = "PROPOSE_ACTION"
#: Mirrors the DDS schema enums/limits. ``tests/test_jev_browser_eligibility.py`` checks
#: these against the vendored schema so a drift fails a test rather than a payload.
CLOSED_OPERATIONS: tuple[str, ...] = ("click", "fill", "select", "scroll", "press_key", "done", "abstain")
ALLOWED_ROLES: frozenset[str] = frozenset({
    "button", "link", "textbox", "searchbox", "combobox", "checkbox", "radio", "tab",
    "menuitem", "option", "listbox", "switch", "slider", "spinbutton", "generic",
})
CEILINGS: tuple[str, ...] = ("A0", "A1", "A2", "A3")
ORIGIN_CLASSES: tuple[str, ...] = ("PUBLIC_ALLOWLISTED", "PUBLIC_UNLISTED")
MAX_TARGETS = 40
MAX_LABEL_LEN = 64
TARGET_ID_RE = re.compile(r"^t_[0-9a-f]{16}$")
EPOCH_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PAYLOAD_KEYS = frozenset({
    "payload_schema", "effect_direction", "closed_operation_set", "origin_class", "targets",
    "action_class_ceiling", "observation_epoch",
})
TARGET_KEYS = frozenset({"target_id", "role", "label"})


class EligibilityClass(str, Enum):
    PUBLIC_ELIGIBLE = "PUBLIC_ELIGIBLE"
    SANITIZABLE_ELIGIBLE = "SANITIZABLE_ELIGIBLE"
    OWNER_PRIVATE = "OWNER_PRIVATE"
    CREDENTIAL = "CREDENTIAL"
    TRADING_PROTECTED = "TRADING_PROTECTED"
    POLICY_DENIED = "POLICY_DENIED"

    @property
    def eligible(self) -> bool:
        return self in (EligibilityClass.PUBLIC_ELIGIBLE, EligibilityClass.SANITIZABLE_ELIGIBLE)


_PRECEDENCE: tuple[EligibilityClass, ...] = (
    EligibilityClass.POLICY_DENIED,
    EligibilityClass.CREDENTIAL,
    EligibilityClass.TRADING_PROTECTED,
    EligibilityClass.OWNER_PRIVATE,
)


@dataclass(frozen=True)
class EligibilityResult:
    eligibility_class: EligibilityClass
    reasons: tuple[str, ...]
    jev_payload: dict | None
    #: opaque ``t_*`` id -> VAN-internal element ref. VAN-side only; never sent.
    target_map: dict[str, str]
    observation_epoch: str

    @property
    def eligible(self) -> bool:
        return self.eligibility_class.eligible

    @property
    def data_class(self) -> str | None:
        """The DDS egress data class the payload is sent under, or None when not sendable."""
        if self.eligibility_class is EligibilityClass.PUBLIC_ELIGIBLE:
            return "PUBLIC"
        if self.eligibility_class is EligibilityClass.SANITIZABLE_ELIGIBLE:
            return "INTERNAL_SANITIZED"
        return None


# ------------------------------------------------------------------------ observation


@dataclass(frozen=True)
class ObservedElement:
    """One interactive element as the adapter saw it. Only ``role`` and a normalised label
    can ever leave VAN; every other field is scanned and then discarded."""

    ref: str
    role: str
    label: str = ""
    aria_label: str = ""
    placeholder: str = ""
    title: str = ""
    #: current input value, if the adapter read one; scanned, never sent.
    value: str = ""
    input_type: str = ""
    autocomplete: str = ""
    hidden: bool = False


@dataclass(frozen=True)
class JevPageObservation:
    """Minimal record for B2. ``authenticated`` / ``cookies_present`` are tri-state; None
    (the adapter could not tell) is treated as an authenticated session."""

    url: str
    profile_alias: str
    authenticated: bool | None
    cookies_present: bool | None
    elements: tuple[ObservedElement, ...] = ()
    page_title: str = ""
    injection_assessment: InjectionAssessment = InjectionAssessment.NONE_DETECTED


# ----------------------------------------------------------------------------- policy

_OWNER_ORIGIN = "OWNER_ACCOUNT_ORIGIN"
_CRED_ORIGIN = "CREDENTIAL_AUTH_FLOW_ORIGIN"
_TRADING_ORIGIN = "TRADING_FINANCIAL_ORIGIN"

#: host (exact or any subdomain; ``host/path-prefix`` for path-scoped entries) -> reason codes.
DEFAULT_SENSITIVE_HOSTS: Mapping[str, tuple[str, ...]] = {
    **{h: (_CRED_ORIGIN, _OWNER_ORIGIN) for h in (
        "accounts.google.com", "login.microsoftonline.com", "login.live.com", "appleid.apple.com",
        "login.yahoo.com", "signin.aws.amazon.com", "account.proton.me",
    )},
    **{h: (_OWNER_ORIGIN,) for h in (
        "myaccount.google.com", "mail.google.com", "drive.google.com", "docs.google.com",
        "calendar.google.com", "contacts.google.com", "photos.google.com", "keep.google.com",
        "console.cloud.google.com", "admin.google.com", "outlook.live.com", "outlook.office.com",
        "outlook.office365.com", "onedrive.live.com", "portal.azure.com", "account.microsoft.com",
        "icloud.com", "mail.yahoo.com", "mail.proton.me", "dropbox.com", "box.com", "slack.com",
        "web.whatsapp.com", "messenger.com", "console.aws.amazon.com", "github.com/settings",
        "mychart.org", "patientaccess.com",
    )},
    **{h: (_CRED_ORIGIN,) for h in (
        "paypal.com", "stripe.com", "pay.google.com", "checkout.shopify.com", "klarna.com",
    )},
    **{h: (_TRADING_ORIGIN,) for h in (
        "wise.com", "revolut.com", "monzo.com", "starlingbank.com", "chase.com", "wellsfargo.com",
        "bankofamerica.com", "citi.com", "hsbc.com", "hsbc.co.uk", "barclays.co.uk",
        "lloydsbank.com", "natwest.com", "santander.co.uk", "nationwide.co.uk",
        "interactivebrokers.com", "ibkr.com", "etoro.com", "robinhood.com", "schwab.com",
        "fidelity.com", "vanguard.com", "trading212.com", "degiro.com", "oanda.com", "ig.com",
        "plus500.com", "tradingview.com", "binance.com", "coinbase.com", "kraken.com",
        "metatrader5.com", "mql5.com",
    )},
}

#: Host labels (any label left of the registrable domain) -> reason code.
_HOST_LABEL_CODES: Mapping[str, str] = {
    **{k: _OWNER_ORIGIN for k in ("admin", "mail", "webmail", "console", "dashboard", "my",
                                   "portal", "mychart", "patient", "intranet")},
    **{k: _CRED_ORIGIN for k in ("login", "signin", "auth", "sso", "accounts", "account", "id",
                                  "idp", "oauth", "secure", "pay", "payments", "checkout", "billing")},
    **{k: _TRADING_ORIGIN for k in ("bank", "banking", "broker", "brokerage", "trade", "trading",
                                     "wallet", "crypto", "exchange", "vati")},
}
#: Substrings that mark a money surface anywhere in a non-TLD host label.
_TRADING_HOST_SUBSTRINGS = ("bank", "broker", "trading", "wallet")

_OWNER_PATH_SEGMENTS = frozenset({
    "account", "accounts", "myaccount", "my-account", "settings", "profile", "wp-admin", "admin",
    "inbox", "mail", "messages", "dashboard", "billing", "orders", "invoices", "u", "user",
    "users", "me",
})
_CRED_PATH_SEGMENTS = frozenset({
    "login", "signin", "sign-in", "logon", "wp-login.php", "oauth", "oauth2", "authorize", "sso",
    "2fa", "mfa", "otp", "password", "reset-password", "checkout", "payment", "payments",
})
_TRADING_PATH_SEGMENTS = frozenset({"trade", "trading", "positions", "portfolio", "wallet"})

_PRIVATE_NETWORK_SUFFIXES = (".local", ".internal", ".lan", ".home.arpa", ".localhost", ".corp", ".intranet")
_CLOUD_METADATA_HOSTS = frozenset({"metadata.google.internal", "169.254.169.254", "fd00:ec2::254"})

_PRIVATE_QUERY_KEYS = frozenset({
    "token", "access_token", "id_token", "refresh_token", "code", "state", "session",
    "sessionid", "sid", "auth", "key", "api_key", "apikey", "email", "user", "userid",
    "user_id", "uid", "account", "acct", "password", "pwd", "signature", "sig", "otp",
    "phone", "name", "ticket", "jwt",
})
_URL_PATH_PRIVATE_CODES = frozenset({"EMAIL", "HANDLE", "OWNER_PROFILE_TERM", "IBAN", "CARD_NUMBER"})


@dataclass(frozen=True)
class JevEligibilityPolicy:
    browser_policy: BrowserPolicy = field(default_factory=load_browser_policy)
    #: public origins the owner has admitted for PUBLIC_ELIGIBLE. Empty by default.
    public_allowlist: frozenset[str] = frozenset()
    sensitive_hosts: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_SENSITIVE_HOSTS))
    #: owner names, usernames, handles etc. Any occurrence makes a page ineligible.
    owner_private_terms: tuple[str, ...] = ()
    max_targets: int = MAX_TARGETS
    max_label_len: int = MAX_LABEL_LEN


# ------------------------------------------------------------------ text normalisation

#: Cyrillic/Greek letters that render like Latin ones. Folded before scanning so a
#: homoglyph cannot hide an email or an owner name from the detectors.
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
    "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ӏ": "l", "ԛ": "q", "ԝ": "w", "ɡ": "g",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
    "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    "α": "a", "ο": "o", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "τ": "t",
    "υ": "u", "χ": "x", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I",
    "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})


def _script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    for script in ("LATIN", "CYRILLIC", "GREEK"):
        if name.startswith(script):
            return script
    return "OTHER"


def _mixed_script(text: str) -> bool:
    for token in re.split(r"\s+", text):
        if len({s for s in (_script(c) for c in token) if s}) > 1:
            return True
    return False


def _has_format_chars(text: str) -> bool:
    """Zero-width, bidi override and other invisible format characters (Unicode Cf)."""
    return any(unicodedata.category(c) == "Cf" for c in text or "")


def _normalise(text: str) -> str:
    """NFKC, drop format/control characters, ASCII digits, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text or "")
    out = []
    for c in text:
        cat = unicodedata.category(c)
        if cat == "Cf" or (cat == "Cc" and c not in "\t\n\r"):
            continue
        if c.isdecimal() and not ("0" <= c <= "9"):
            c = str(unicodedata.decimal(c))
        out.append(c)
    return re.sub(r"\s+", " ", "".join(out)).strip()


_DEOBFUSCATIONS = (
    (re.compile(r"\s*[\[\(\{<]\s*(?:at|@)\s*[\]\)\}>]\s*", re.I), "@"),
    (re.compile(r"\s*[\[\(\{<]\s*(?:dot|\.)\s*[\]\)\}>]\s*", re.I), "."),
    (re.compile(r"\b([A-Za-z0-9._%+-]+)\s+at\s+([A-Za-z0-9-]+)\s+dot\s+([A-Za-z]{2,})\b", re.I), r"\1@\2.\3"),
    (re.compile(r"\s+dot\s+(?=[A-Za-z]{2,}\b)", re.I), "."),
    (re.compile(r"\bhxxp", re.I), "http"),
)


def _variants(text: str) -> tuple[str, str, str]:
    """(folded, deobfuscated, squeezed) forms scanned by the private-data detectors."""
    folded = _normalise(text).translate(_CONFUSABLES)
    deob = folded
    for pattern, repl in _DEOBFUSCATIONS:
        deob = pattern.sub(repl, deob)
    squeezed = re.sub(r"\s+", "", deob)
    return folded, deob, squeezed


# ------------------------------------------------------------------ private detectors

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_HANDLE_RE = re.compile(r"(?<![\w.@])@[A-Za-z0-9_]{2,}")
_DATE_TIME_RE = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?",
    re.I,
)
_DIGIT_RUN_RE = re.compile(r"\+?\d(?:[\s\-.()/_,·•]*\d){4,}")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_TOKEN_RE = re.compile(r"(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{20,}")
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_ACCOUNT_LIKE_RE = re.compile(r"\b(?=(?:[A-Za-z\-]*\d){3})(?=[A-Za-z0-9\-]*[A-Za-z])[A-Za-z0-9\-]{8,}\b")
#: DDS data-classification.mjs SECRET_PATTERNS plus a JWT shape, restated so page secret
#: material is refused here rather than at the DDS egress checker.
_SECRET_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:API_KEY|ACCESS_TOKEN|REFRESH_TOKEN|CLIENT_SECRET|PASSWORD|SIGNING_KEY)\b\s*[=:]\s*[^\s,;]+", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
)
_RESTRICTED_FIELD_RE = re.compile(
    r"\b(?:card\s*number|cvv2?|cvc|security\s*code|expiry|expiration\s*date|iban|sort\s*code|"
    r"routing\s*number|account\s*number|bank\s*account|national\s*id|passport\s*number|"
    r"social\s*security|ssn|tax\s*id)\b",
    re.I,
)
_CREDENTIAL_WORDS_RE = re.compile(
    r"\b(?:pass(?:word|code|phrase)|otp|one[- ]?time\s*(?:code|password|passcode)|"
    r"verification\s*code|2fa|mfa|two[- ]factor|authenticator\s*code|pin\s*code|pin)\b",
    re.I,
)
_SIGNED_IN_RE = re.compile(r"\b(?:sign(?:ed)?\s*out|log(?:ged)?\s*out|logout|signout|switch\s*account)\b", re.I)
_AUTH_ENTRY_RE = re.compile(
    r"\b(?:sign\s*in|log\s*in|login|signin|sign\s*up|signup|register|create\s*account|"
    r"my\s*account|your\s*account|account|profile|settings|forgot|reset\s*password)\b",
    re.I,
)
_PAYMENT_CONTROL_RE = re.compile(
    r"\b(?:pay\s*now|pay\s*\S*\s*now|place\s*order|confirm\s*(?:payment|order|purchase|transfer)|"
    r"complete\s*purchase|buy\s*now|send\s*money|transfer\s*funds|withdraw|deposit)\b",
    re.I,
)
_TRADING_CONTROL_RE = re.compile(
    r"\b(?:stop[- ]?loss|take[- ]?profit|leverage|market\s*order|limit\s*order|close\s*position|"
    r"open\s*position|buy\s*/\s*sell|margin\s*call|lot\s*size)\b",
    re.I,
)
_URL_IN_LABEL_RE = re.compile(
    r"(?:\b(?:https?|ftp|file|javascript|data):|\bwww\.|"
    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|co|uk|de|fr|gov|edu|info|app|dev|ai|me|us|ly|biz)\b)",
    re.I,
)

_INPUT_ROLES = frozenset({"textbox", "searchbox", "combobox", "spinbutton"})
_PERSONAL_AUTOCOMPLETE = ("email", "tel", "name", "given-name", "family-name", "street-address",
                          "address", "postal-code", "bday", "username", "organization")
_PERSONAL_INPUT_TYPES = frozenset({"email", "tel"})
_PERSONAL_FIELD_WORDS_RE = re.compile(
    r"\b(?:e-?mail|phone|mobile|full\s*name|first\s*name|last\s*name|surname|address|postcode|zip|"
    r"date\s*of\s*birth|username|user\s*name)\b",
    re.I,
)


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def _owner_term_hit(folded: str, squeezed: str, terms: Iterable[str]) -> bool:
    low = folded.lower()
    letters = re.sub(r"[^a-z0-9]", "", squeezed.lower())
    for term in terms:
        t_folded = _normalise(term).translate(_CONFUSABLES).lower()
        if len(t_folded) < 3:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(t_folded)}(?![a-z0-9])", low):
            return True
        t_letters = re.sub(r"[^a-z0-9]", "", t_folded)
        if len(t_letters) >= 5 and t_letters in letters:
            return True
    return False


def secret_material(text: str) -> bool:
    if not text:
        return False
    folded = _normalise(text).translate(_CONFUSABLES)
    return any(p.search(folded) for p in _SECRET_RES) or bool(BrowserPolicyEngine.scan_for_secrets(folded))


def private_data_findings(text: str, *, owner_terms: Sequence[str] = ()) -> list[str]:
    """Sorted reason codes for private data in one piece of text. Empty means none detected.

    Scans folded (NFKC + homoglyph), deobfuscated ([at]/[dot]/"at … dot") and
    whitespace-squeezed forms, so obfuscated emails, homoglyphs, fullwidth and non-ASCII
    digits and split digits are caught.
    """
    if not text:
        return []
    folded, deob, squeezed = _variants(text)
    found: set[str] = set()
    if any(_EMAIL_RE.search(v) for v in (folded, deob, squeezed)):
        found.add("EMAIL")
    if _HANDLE_RE.search(folded) or _HANDLE_RE.search(deob):
        found.add("HANDLE")
    if _DATE_TIME_RE.search(deob):
        found.add("TIMESTAMP")
    no_dates = _DATE_TIME_RE.sub(" ", deob)
    runs = [re.sub(r"\D", "", m.group(0)) for m in _DIGIT_RUN_RE.finditer(no_dates)]
    if runs or sum(c.isdigit() for c in no_dates) >= 7:
        found.add("DIGIT_RUN")
    if any(13 <= len(r) <= 19 and _luhn(r) for r in runs):
        found.add("CARD_NUMBER")
    if _IBAN_RE.search(squeezed.upper()):
        found.add("IBAN")
    if _TOKEN_RE.search(folded) or _HEX_RE.search(folded) or _ACCOUNT_LIKE_RE.search(folded):
        found.add("ACCOUNT_LIKE_TOKEN")
    if owner_terms and _owner_term_hit(folded, squeezed, owner_terms):
        found.add("OWNER_PROFILE_TERM")
    return sorted(found)


# ----------------------------------------------------------------------------- helpers


def _host_matches(host: str, entries: Iterable[str]) -> bool:
    for entry in entries:
        entry = entry.lower().strip()
        if "/" not in entry and (host == entry or host.endswith("." + entry)):
            return True
    return False


def _host_codes(host: str, path: str, table: Mapping[str, tuple[str, ...]]) -> list[str]:
    codes: list[str] = []
    for entry, entry_codes in table.items():
        e_host, _, e_path = entry.lower().partition("/")
        if not (host == e_host or host.endswith("." + e_host)):
            continue
        if e_path and not path.lower().lstrip("/").startswith(e_path):
            continue
        codes += [c for c in entry_codes if c not in codes]
    return codes


class _Findings:
    def __init__(self) -> None:
        self.items: list[tuple[EligibilityClass, str]] = []

    def add(self, cls: EligibilityClass, reason: str) -> None:
        if not any(r == reason for _, r in self.items):
            self.items.append((cls, reason))

    def __bool__(self) -> bool:
        return bool(self.items)

    def verdict(self) -> tuple[EligibilityClass, tuple[str, ...]]:
        ordered = sorted(self.items, key=lambda item: _PRECEDENCE.index(item[0]))  # stable
        return ordered[0][0], tuple(r for _, r in ordered)


def _new_epoch() -> str:
    return "e_" + secrets.token_hex(8)


def _ineligible(cls: EligibilityClass, reasons: Sequence[str], epoch: str) -> EligibilityResult:
    return EligibilityResult(cls, tuple(reasons), None, {}, epoch)


def _normalise_ceiling(value: Any) -> str | None:
    raw = value.value if isinstance(value, ActionClass) else value
    return raw if isinstance(raw, str) and raw in CEILINGS else None


def _normalise_ops(ops: Any) -> list[str] | None:
    if isinstance(ops, (str, bytes)) or not isinstance(ops, Iterable):
        return None
    out: list[str] = []
    for op in ops:
        if op not in CLOSED_OPERATIONS:
            return None
        if op not in out:
            out.append(op)
    return out or None


def _profile_is_public(profile: Mapping[str, Any] | None) -> bool:
    # profiles.yaml ``authentication: none`` is read as None by the repo's YAML reader, so
    # both spellings mean "no authentication"; a *missing* key is not public.
    if profile is None or "authentication" not in profile:
        return False
    return profile.get("authentication") in (None, "none") and str(profile.get("persistence")) == "ephemeral"


def _literal_ip_codes(host: str) -> list[str]:
    """Reuse the automation SSRF network list: a literal IP is never plausible, and one in
    a blocked network is also denied."""
    address = ipaddress.ip_address(host)
    codes = ["POLICY_HOST_NOT_PLAUSIBLE"]
    for network in DomainPolicy().blocked_networks:
        if address in ipaddress.ip_network(network, strict=False):
            codes.append("POLICY_HOST_DENIED")
            break
    return codes


def withheld_reason(element: ObservedElement, *, max_label_len: int = MAX_LABEL_LEN) -> str | None:
    """Why one element on an otherwise clean page is not offered as a target (None: offered).

    Only non-private reasons live here; private data in any text field has already made the
    whole observation ineligible before this runs.
    """
    raw = element.aria_label or element.label
    label = _normalise(raw)
    folded = label.translate(_CONFUSABLES)
    joined = _normalise(" ".join(t for t in (element.label, element.aria_label, element.placeholder, element.title) if t))
    itype, auto = (element.input_type or "").lower(), (element.autocomplete or "").lower()
    if element.hidden:
        return "HIDDEN"
    if element.role not in ALLOWED_ROLES:
        return "ROLE_UNKNOWN"
    if not label:
        return "LABEL_EMPTY"
    if _has_format_chars(raw) or _mixed_script(label):
        return "LABEL_OBFUSCATED"
    if len(label) > max_label_len:
        return "LABEL_TOO_LONG"
    if _URL_IN_LABEL_RE.search(_variants(joined)[1]):
        return "URL_IN_LABEL"
    if re.search(r"\d{4,}", folded):
        return "NUMBER_IN_LABEL"
    if _AUTH_ENTRY_RE.search(folded) or _CREDENTIAL_WORDS_RE.search(folded):
        return "AUTH_ENTRYPOINT"
    if itype in _PERSONAL_INPUT_TYPES or auto.startswith(_PERSONAL_AUTOCOMPLETE) or (
        (element.role in _INPUT_ROLES or itype) and _PERSONAL_FIELD_WORDS_RE.search(joined)
    ):
        return "PERSONAL_DATA_FIELD"
    return None


# ------------------------------------------------------------------- payload self-check


def payload_violations(payload: Any) -> list[str]:
    """Check a payload against the DDS schema constraints and the DDS egress secret rules.

    Used as the last guard before a payload is returned; a non-empty result means the
    observation is refused, never that the payload is patched.
    """
    v: list[str] = []
    if not isinstance(payload, dict):
        return ["payload:not_object"]
    if set(payload) != PAYLOAD_KEYS:
        v.append("payload:keys")
    if payload.get("payload_schema") != PAYLOAD_SCHEMA:
        v.append("payload_schema")
    if payload.get("effect_direction") != EFFECT_DIRECTION:
        v.append("effect_direction")
    ops = payload.get("closed_operation_set")
    if not isinstance(ops, list) or not ops or len(set(ops)) != len(ops) or any(o not in CLOSED_OPERATIONS for o in ops):
        v.append("closed_operation_set")
    if payload.get("origin_class") not in ORIGIN_CLASSES:
        v.append("origin_class")
    if payload.get("action_class_ceiling") not in CEILINGS:
        v.append("action_class_ceiling")
    epoch = payload.get("observation_epoch")
    if not isinstance(epoch, str) or not EPOCH_RE.match(epoch):
        v.append("observation_epoch")
    targets = payload.get("targets")
    if not isinstance(targets, list) or len(targets) > MAX_TARGETS:
        v.append("targets")
        targets = []
    seen: set[str] = set()
    for i, t in enumerate(targets):
        if not isinstance(t, dict) or set(t) != TARGET_KEYS:
            v.append(f"targets[{i}]:keys")
            continue
        tid, role, label = t.get("target_id"), t.get("role"), t.get("label")
        if not isinstance(tid, str) or not TARGET_ID_RE.match(tid) or tid in seen:
            v.append(f"targets[{i}].target_id")
        seen.add(tid if isinstance(tid, str) else "")
        if role not in ALLOWED_ROLES:
            v.append(f"targets[{i}].role")
        if not isinstance(label, str) or not (1 <= len(label) <= MAX_LABEL_LEN):
            v.append(f"targets[{i}].label")
    if any(p.search(json.dumps(payload, ensure_ascii=False)) for p in _SECRET_RES):
        v.append("secret_pattern")
    return v


# ------------------------------------------------------------------------- classifier

POLICY = EligibilityClass.POLICY_DENIED
CRED = EligibilityClass.CREDENTIAL
TRADE = EligibilityClass.TRADING_PROTECTED
OWNER = EligibilityClass.OWNER_PRIVATE
_ORIGIN_CODE_CLASS = {_OWNER_ORIGIN: OWNER, _CRED_ORIGIN: CRED, _TRADING_ORIGIN: TRADE}


def classify_observation(
    observation: Any,
    *,
    closed_operation_set: Sequence[str],
    action_class_ceiling: Any,
    policy: JevEligibilityPolicy | None = None,
) -> EligibilityResult:
    epoch = _new_epoch()

    ops = _normalise_ops(closed_operation_set)
    if ops is None:
        return _ineligible(POLICY, ["AMBIGUOUS_OPERATION_SET"], epoch)
    ceiling = _normalise_ceiling(action_class_ceiling)
    if ceiling is None:
        return _ineligible(POLICY, ["POLICY_ACTION_CLASS_CEILING"], epoch)
    if not isinstance(observation, JevPageObservation):
        return _ineligible(POLICY, ["AMBIGUOUS_OBSERVATION_TYPE"], epoch)
    elements = tuple(observation.elements or ())
    if not all(isinstance(e, ObservedElement) for e in elements):
        return _ineligible(POLICY, ["AMBIGUOUS_OBSERVATION_TYPE"], epoch)
    pol = policy or JevEligibilityPolicy()
    terms = pol.owner_private_terms
    f = _Findings()

    # ---- origin -------------------------------------------------------------------
    try:
        parts = urlsplit(observation.url or "")
        host = (parts.hostname or "").rstrip(".").lower()
        scheme = parts.scheme.lower()
    except ValueError:
        return _ineligible(POLICY, ["POLICY_SCHEME_NOT_NAVIGABLE"], epoch)
    if scheme != "https" or not host:
        return _ineligible(POLICY, ["POLICY_SCHEME_NOT_NAVIGABLE"], epoch)

    literal_ip = False
    try:
        ipaddress.ip_address(host)
        literal_ip = True
    except ValueError:
        pass
    if literal_ip:
        for code in _literal_ip_codes(host):
            f.add(POLICY, code)
    else:
        try:
            host.encode("ascii")
            idn = any(label.startswith("xn--") for label in host.split("."))
        except UnicodeEncodeError:
            idn = True
        if idn or "." not in host:
            f.add(POLICY, "POLICY_HOST_NOT_PLAUSIBLE")
        if host == "localhost" or host.endswith(_PRIVATE_NETWORK_SUFFIXES) or host in _CLOUD_METADATA_HOSTS:
            f.add(POLICY, "POLICY_HOST_DENIED")
    if host in _CLOUD_METADATA_HOSTS:
        f.add(POLICY, "POLICY_HOST_DENIED")

    # ---- page adversarial content ---------------------------------------------------
    texts = [observation.page_title] + [
        t for e in elements for t in (e.label, e.aria_label, e.placeholder, e.title, e.value)
    ]
    scanned = BrowserPolicyEngine.assess_injection(" \n ".join(_normalise(t) for t in texts if t))
    # Either verdict counts: the adapter cannot downgrade the scan, nor the scan the adapter.
    if (
        scanned is not InjectionAssessment.NONE_DETECTED
        or observation.injection_assessment is not InjectionAssessment.NONE_DETECTED
    ):
        f.add(POLICY, "POLICY_INJECTION_SUSPECTED")

    # ---- profile (admission) ---------------------------------------------------------
    profile = pol.browser_policy.profiles.get(observation.profile_alias)
    if profile is None:
        f.add(POLICY, "AMBIGUOUS_PROFILE_NOT_ADMITTED")

    # ---- origin classes ----------------------------------------------------------------
    path = unquote(parts.path or "")
    labels = host.split(".")
    origin_codes: list[str] = []
    if not literal_ip:
        origin_codes += _host_codes(host, path, pol.sensitive_hosts)
        if _host_matches(host, pol.browser_policy.admitted_domains):
            origin_codes.append(_OWNER_ORIGIN)
        sub_labels = labels[:-2] if len(labels) > 2 else []
        origin_codes += [_HOST_LABEL_CODES[lbl] for lbl in sub_labels if lbl in _HOST_LABEL_CODES]
        if any(s in lbl for lbl in labels[:-1] for s in _TRADING_HOST_SUBSTRINGS):
            origin_codes.append(_TRADING_ORIGIN)
    segments = [s.lower() for s in path.split("/") if s]
    if any(s in _CRED_PATH_SEGMENTS for s in segments):
        origin_codes.append(_CRED_ORIGIN)
    if any(s in _TRADING_PATH_SEGMENTS for s in segments):
        origin_codes.append(_TRADING_ORIGIN)
    for code in (_CRED_ORIGIN, _TRADING_ORIGIN):
        if code in origin_codes:
            f.add(_ORIGIN_CODE_CLASS[code], code)

    # ---- credential / trading surfaces on the page -------------------------------------
    for e in elements:
        e_texts = [t for t in (e.label, e.aria_label, e.placeholder, e.title, e.value) if t]
        joined = _normalise(" ".join(e_texts)).translate(_CONFUSABLES)
        itype, auto = (e.input_type or "").lower(), (e.autocomplete or "").lower()
        is_input = e.role in _INPUT_ROLES or bool(itype)
        if itype == "password" or auto in ("current-password", "new-password", "one-time-code") or auto.startswith("cc-") or (
            is_input and (_CREDENTIAL_WORDS_RE.search(joined) or _RESTRICTED_FIELD_RE.search(joined))
        ):
            f.add(CRED, "CREDENTIAL_FIELD")
    if any(secret_material(t) for t in texts if t):
        f.add(CRED, "CREDENTIAL_SECRET_MATERIAL")
    for e in elements:
        joined = _normalise(" ".join(t for t in (e.label, e.aria_label, e.title) if t)).translate(_CONFUSABLES)
        if _PAYMENT_CONTROL_RE.search(joined):
            f.add(CRED, "CREDENTIAL_PAYMENT_CONTROL")
    for e in elements:
        joined = _normalise(" ".join(t for t in (e.label, e.aria_label, e.title) if t)).translate(_CONFUSABLES)
        if _TRADING_CONTROL_RE.search(joined):
            f.add(TRADE, "TRADING_CONTROL")

    # ---- owner-private signals ------------------------------------------------------------
    if observation.authenticated is not False or observation.cookies_present is not False:
        f.add(OWNER, "OWNER_AUTHENTICATED_SESSION")
    if not _profile_is_public(profile):
        f.add(OWNER, "OWNER_PROFILE_NOT_PUBLIC")
    if _OWNER_ORIGIN in origin_codes:
        f.add(OWNER, _OWNER_ORIGIN)
    if any(s in _OWNER_PATH_SEGMENTS for s in segments):
        f.add(OWNER, "OWNER_ACCOUNT_PATH")
    if parts.username is not None or parts.password is not None:
        f.add(OWNER, "OWNER_PRIVATE_URL")
    query_pairs = parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(parts.fragment, keep_blank_values=True)
    if any(k.lower() in _PRIVATE_QUERY_KEYS for k, _ in query_pairs) or any(
        private_data_findings(v, owner_terms=terms) for _, v in query_pairs
    ) or set(private_data_findings(path.replace("/", " "), owner_terms=terms)) & _URL_PATH_PRIVATE_CODES:
        f.add(OWNER, "OWNER_PRIVATE_URL")
    if _SIGNED_IN_RE.search(_normalise(observation.page_title)) or any(
        _SIGNED_IN_RE.search(_normalise(" ".join((e.label, e.aria_label, e.title))).translate(_CONFUSABLES))
        for e in elements
    ):
        f.add(OWNER, "OWNER_SIGNED_IN_EVIDENCE")
    for e in elements:
        codes: set[str] = set()
        for t in (e.label, e.aria_label, e.placeholder, e.title):
            codes.update(private_data_findings(t, owner_terms=terms))
        if codes:
            f.add(OWNER, "OWNER_PRIVATE_LABEL:" + ",".join(sorted(codes)))
        if e.value and (e.role in _INPUT_ROLES or e.input_type) and (e.input_type or "").lower() not in ("submit", "button"):
            f.add(OWNER, "OWNER_PRIVATE_INPUT_VALUE")
    if private_data_findings(observation.page_title, owner_terms=terms):
        f.add(OWNER, "OWNER_PRIVATE_TITLE")

    if f:
        cls, reasons = f.verdict()
        return _ineligible(cls, reasons, epoch)

    # ---- targets (only for an otherwise clean, public, unauthenticated page) -----------
    targets: list[dict[str, str]] = []
    target_map: dict[str, str] = {}
    withheld = 0
    for e in elements:
        if withheld_reason(e, max_label_len=pol.max_label_len):
            withheld += 1
            continue
        tid = "t_" + secrets.token_hex(8)
        while tid in target_map:
            tid = "t_" + secrets.token_hex(8)
        target_map[tid] = e.ref
        targets.append({"target_id": tid, "role": e.role, "label": _normalise(e.aria_label or e.label)})

    if not targets:
        return _ineligible(POLICY, ["AMBIGUOUS_NO_TARGETS"], epoch)
    if len(targets) > pol.max_targets:
        return _ineligible(POLICY, ["AMBIGUOUS_TOO_MANY_TARGETS"], epoch)

    allowlisted = _host_matches(host, pol.public_allowlist)
    payload = {
        "payload_schema": PAYLOAD_SCHEMA,
        "effect_direction": EFFECT_DIRECTION,
        "closed_operation_set": ops,
        "origin_class": "PUBLIC_ALLOWLISTED" if allowlisted else "PUBLIC_UNLISTED",
        "targets": targets,
        "action_class_ceiling": ceiling,
        "observation_epoch": epoch,
    }
    if payload_violations(payload):
        return _ineligible(POLICY, ["POLICY_PAYLOAD_SELF_CHECK_FAILED"], epoch)

    reasons = ["PUBLIC_ALLOWLISTED_ORIGIN" if allowlisted else "PUBLIC_UNLISTED_ORIGIN"]
    if withheld:
        reasons.append(f"TARGETS_WITHHELD:{withheld}")
    cls = EligibilityClass.PUBLIC_ELIGIBLE if allowlisted and not withheld else EligibilityClass.SANITIZABLE_ELIGIBLE
    return EligibilityResult(cls, tuple(reasons), payload, target_map, epoch)


__all__ = [
    "CLOSED_OPERATIONS",
    "DEFAULT_SENSITIVE_HOSTS",
    "EligibilityClass",
    "EligibilityResult",
    "JevEligibilityPolicy",
    "JevPageObservation",
    "ObservedElement",
    "classify_observation",
    "payload_violations",
    "private_data_findings",
    "withheld_reason",
]
