"""Review I4 MAJOR-A — the browser action classifier, redesigned to fail safe.

Three review rounds (I2 N-6, I3 MAJOR-2, I4 MAJOR-A) each found commitment controls the
word/stem denylist did not know: ``#transfernow``, ``aria-label=Оплатить``, ``#pɑynow``
(U+0251), "支付", "Donate $50", ``data-testid=pay-button``, a ``name=pan type=tel`` card
field. A denylist can never be complete, so it is no longer the primary control.

Primary control — structural rules (fail safe)
==============================================

A targeted ``click``, ``fill`` or ``select`` is **A4 (owner takeover) unless VAN can
positively establish that it is low-risk**. Low-risk means all of:

* ``R1`` every character of the observed text folds to ASCII: a letter of any script other
  than Latin (Cyrillic, Greek, Armenian, Han, Kana, Arabic, Cherokee ...) or any character
  the fold leaves unmapped (``€``, an emoji, ``•``) is A4. This is the backstop for
  everything the denylist cannot enumerate: every non-Latin-script language and every
  homoglyph outside the fold table;
* ``R2`` no risk stem (the denylist below) in the folded text, read as squashed
  ``[a-z0-9]`` substrings and as words;
* ``R3`` the element's role/type is outside the risky set (``_RISKY_ROLES``);
* ``R4`` for fill/select: nothing about the field — type, name, id, autocomplete,
  inputmode, pattern, maxlength, placeholder, label — signals a payment instrument or a
  number-like secret (card number, expiry, CVC, PIN, IBAN, account/routing number);
* ``R5`` there is evidence at all: an element the Harness reported, or (click only) a
  locator. No evidence -> A4.

Unresolved targets (``R6``)
===========================

When the Harness does not report (and bind) the element, only the locator is known. Every
targeted operation on an unresolved target is A4 (``R6_UNRESOLVED_TARGET`` /
``R6_UNRESOLVED_WRITE``). Review I4 let a plain-ASCII click through as A2; review I5 and the
owner decision of 2026-09-30 withdrew that: an action may run only on the element the
Harness bound at describe time and re-verifies when it acts (``task_scope`` rule (b)), and
an unresolved target cannot be that element. The router also treats as unresolved a hidden
element, a frame, a shadow host, an element whose centre hits something else (an overlay, or
a wrapper around another control), and a role that is not a control (``generic``).

Review I5 additions (defence in depth; the task scope is the primary control)
=============================================================================

* ``R7`` a name-from-content role (button, link, tab, option ...) whose accessible name
  differs from its visible ``text`` (``aria-label="Next"`` on "Pay 500 now");
* ``R8`` a click with an empty name, or a name-from-content control with no visible text
  (image-only / icon-only controls — their image and CSS file names are read as ``media``);
* ``R3`` also covers an effective submit (``submits``: a ``<button>`` with no type in a
  form), and the form's ``action``/``formaction`` are read as text;
* ``press_key`` is classified against the focused element (``assess_key_press``: ``R6``
  unknown focus, ``R9`` Enter/Space on a non-control, ``R10`` a non-navigation key outside a
  field);
* MAJOR-6 money/trading/commitment verbs in ``_RISK_STEMS`` / ``_RISK_WORDS``;
* ``R11`` (integration G8) the Harness redacted part of what the control shows (its
  ``text``, a ``media`` entry, or its form's ``action``/``formaction``): review I5 E1
  masks card/account digit runs, token-like runs and field values there, and a masked span
  may have held a risk word, so the target is never positively low-risk.

Defence in depth — the denylist (``_RISK_STEMS``, ``_PAYMENT_FIELD_STEMS``)
============================================================================

Still applied (R2/R4) after folding: NFKD, combining marks (Mn) dropped, NFKC, format
characters (Cf) dropped, case-folded, then Latin-extended/IPA/small-capital letters mapped
to ASCII (``_LATIN_FOLD``) and — for the denylist and the payment boundary only — the
cross-script confusables (Cyrillic, Greek, Armenian, Cherokee) mapped too
(``_CROSS_SCRIPT_CONFUSABLES``). This is not full UTS #39 (no dependency is added); R1 is
the backstop for whatever the tables miss.

False-positive trade-off (accepted deliberately)
================================================

Every false positive raises the class to A4, which is never automated: the step goes to
the owner. That is the fail-safe direction; a false negative clicks a pay button. Known
over-matches, each pinned by a test (``test_browser_review_i4_fail_safe_classifier.py``):

* every control on a page in a non-Latin script (R1): a Russian, Chinese, Japanese,
  Arabic, Greek or Hebrew site is owner-operated for targeted actions;
* a price or symbol in a label (``€``, ``£``, ``•``, emoji) (R1); ``$`` next to a digit (R2);
* substring stems: "Sign in" / "Design" / "Assign" (sign), "Facebook" / "Bookmark" (book),
  "Buyer guide" (buy), "order by date" (order), "Accept cookies" (accept), "Sender"
  (send), "Authority" (authori), "Reserved" (reserve), "Remove filter" (remove);
* ``type=submit`` (a search form's submit button reads "submit");
* a switch (R3), a file/image input (R3);
* fills: a Bootstrap ``.card`` wrapper in the selector, a birth year with
  ``inputmode=numeric maxlength=4``, a 3-4 digit numeric code, a "PIN" field, a "Pan"
  select on a cooking site, and every fill into a field the Harness did not report (R6).
* review I5 (pinned in ``test_browser_review_i5_task_scope.py``): "Continue reading",
  "Complete profile", "Industrial design" (trial), "Proceedings", "Place of birth", "Claim a
  username", "Swap panels", "Investigate logs", "Executive summary", "Discharge summary",
  "Desktop update" (topup), "Euro 2024"; every submit button, including a search form's
  (R3); an icon-font ligature beside a label (R7: name "Next", text "arrow_forward Next"); an
  icon-only or title-only button (R8); every unresolved click (R6).
* words the classifier cannot tell from benign navigation stay A2 — "Next", "Go", "Ok",
  "Yes", "I understand": on a page inside the task's scope they run, and only the scope
  (a path the task declares) holds a page like I5's ``/words``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

TARGETED_OPERATIONS = frozenset({"click", "fill", "select"})
WRITE_OPERATIONS = frozenset({"fill", "select"})
TARGETLESS_OPERATIONS = frozenset({"done", "abstain", "scroll"})

# ------------------------------------------------------------------ folding

#: Latin-script letters (Latin Extended, IPA, phonetic small capitals) that NFKD does not
#: decompose to ASCII, plus a small set of typographic punctuation. Lower-case keys: the
#: text is case-folded first. Anything not here and not ASCII after the fold is R1 (A4).
_LATIN_FOLD = str.maketrans({
    # Latin Extended letters without a canonical decomposition
    "ł": "l", "ø": "o", "đ": "d", "ħ": "h", "ı": "i", "ȷ": "j", "æ": "ae", "œ": "oe",
    "þ": "th", "ð": "d", "ƀ": "b", "ƈ": "c", "ɓ": "b", "ɗ": "d", "ɠ": "g", "ƙ": "k",
    "ƚ": "l", "ɱ": "m", "ɲ": "n", "ƥ": "p", "ʠ": "q", "ɽ": "r", "ʂ": "s", "ƭ": "t",
    "ʋ": "v", "ⱳ": "w", "ƴ": "y", "ȥ": "z", "ƒ": "f", "ĸ": "k", "ŧ": "t", "ɇ": "e",
    "ɨ": "i", "ɍ": "r", "ɏ": "y", "ƶ": "z", "ǥ": "g", "ȼ": "c", "ƣ": "oi", "ŉ": "n",
    # IPA
    "ɑ": "a", "ɐ": "a", "ɒ": "o", "ɕ": "c", "ɖ": "d", "ɘ": "e", "ə": "e", "ɛ": "e",
    "ɜ": "e", "ɞ": "e", "ɡ": "g", "ɢ": "g", "ɦ": "h", "ɧ": "h", "ɩ": "i", "ɪ": "i",
    "ʝ": "j", "ɟ": "j", "ɫ": "l", "ɬ": "l", "ɭ": "l", "ʟ": "l", "ɯ": "m", "ɰ": "m",
    "ɳ": "n", "ɴ": "n", "ɵ": "o", "ɶ": "oe", "ɸ": "f", "ɹ": "r", "ɺ": "r", "ɻ": "r",
    "ɼ": "r", "ɾ": "r", "ʀ": "r", "ʁ": "r", "ʃ": "s", "ʈ": "t", "ʉ": "u", "ʊ": "u",
    "ʌ": "v", "ʍ": "w", "ʎ": "y", "ʏ": "y", "ʐ": "z", "ʑ": "z", "ʒ": "z", "ɔ": "o",
    # phonetic small capitals
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ʜ": "h", "ᴊ": "j",
    "ᴋ": "k", "ᴍ": "m", "ᴏ": "o", "ᴘ": "p", "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v",
    "ᴡ": "w", "ᴢ": "z", "ᴦ": "r",
    # typographic punctuation that carries no risk
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "“": '"', "”": '"', "„": '"',
    "‟": '"', "″": '"', "«": '"', "»": '"', "‹": "'", "›": "'", "‐": "-", "‑": "-",
    "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-", "·": ".", "×": "x", "⁄": "/",
    "←": " ", "→": " ", "↑": " ", "↓": " ",
})

#: Cross-script look-alikes, applied only where a *match* is wanted (the denylist and the
#: payment boundary), never to decide R1: a Cyrillic "а" is A4 by R1 whatever it looks like.
#: Cyrillic/Greek as the shared jev_eligibility table plus Armenian and Cherokee (which
#: case-folds to its capitals).
_CROSS_SCRIPT_CONFUSABLES = str.maketrans({
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o",
    "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "ь": "b", "і": "i", "ї": "i",
    "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ӏ": "l", "ԛ": "q", "ԝ": "w", "ɡ": "g",
    "п": "n", "г": "r", "и": "u", "з": "3", "ч": "4",
    # Greek
    "α": "a", "β": "b", "γ": "y", "ε": "e", "η": "n", "ι": "i", "κ": "k", "μ": "u",
    "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ω": "w", "ϲ": "c",
    "ϳ": "j", "ς": "c",
    # Armenian
    "ա": "w", "ց": "g", "հ": "h", "յ": "j", "ո": "n", "ս": "u", "օ": "o", "զ": "q",
    "ռ": "n", "ք": "p", "ւ": "l", "ե": "t", "գ": "q", "ղ": "n", "ճ": "a",
    # Cherokee (casefold maps the small letters to these capitals)
    "Ꭺ": "a", "Ᏼ": "b", "Ꮯ": "c", "Ꭼ": "e", "Ꮋ": "h", "Ꭵ": "i", "Ꭻ": "j", "Ꮶ": "k",
    "Ꮮ": "l", "Ꮇ": "m", "Ꮲ": "p", "Ꭱ": "r", "Ꮪ": "s", "Ꭲ": "t", "Ꮩ": "v", "Ꮃ": "w",
    "Ꮓ": "z", "Ꮐ": "g", "Ꮍ": "y", "Ꮞ": "4", "Ꮟ": "b", "Ᏻ": "g", "Ꮤ": "w",
})


def _strip_marks(text: str) -> str:
    """NFKD, combining marks (Mn) dropped, NFKC, format characters (Cf) dropped; control
    and separator characters as spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = unicodedata.normalize("NFKC", text)
    out = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        out.append(" " if category in ("Cc", "Zs", "Zl", "Zp") else char)
    return "".join(out)


def fold_latin(text: Any) -> str:
    """The R1 fold: marks/format characters removed, case-folded, Latin look-alikes mapped.

    Cross-script look-alikes are *not* mapped, so a Cyrillic or Armenian letter survives as
    non-ASCII and trips R1.
    """
    text = _strip_marks(str(text or "")).casefold()
    # Case folding can re-introduce a mark ("İ" -> "i" + U+0307): strip again.
    return _strip_marks(text).translate(_LATIN_FOLD)


def fold(text: Any) -> str:
    """The matching fold: ``fold_latin`` plus the cross-script confusables."""
    return fold_latin(text).translate(_CROSS_SCRIPT_CONFUSABLES)


def unmapped_characters(text: Any) -> str:
    """The characters of ``text`` that do not fold to ASCII (R1). Empty means clean."""
    return "".join(dict.fromkeys(c for c in fold_latin(text) if ord(c) > 0x7E or (ord(c) < 0x20 and c not in "\t\n\r")))


def words(text: Any) -> str:
    """Selector/attribute text as words: ``//button[@id='payNow_btn']`` -> ``button id pay Now btn``."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text or ""))
    return re.sub(r"[^A-Za-z0-9]+", " ", text).strip()


# ------------------------------------------------------------------ the denylist (R2, R4)

#: Kept as documentation of the historic word list; ``_RISK_STEMS`` is a strict superset
#: (asserted by a test), so nothing that matched before can stop matching.
HIGH_RISK_WORDS = re.compile(
    r"\b(pay|payment|purchase|buy|checkout|order|transfer|send|submit|confirm|delete|remove|"
    r"sign|authori[sz]e|approve|subscribe|withdraw|deposit)\b",
    re.IGNORECASE,
)

#: Commitment stems, matched as substrings of the folded ``[a-z0-9]`` text. Any targeted
#: operation whose observed text contains one is A4.
_RISK_STEMS: tuple[str, ...] = (
    # money and commerce
    "pay", "buy", "checkout", "purchase", "order", "transfer", "send", "withdraw", "deposit",
    "donate", "donation", "wager", "placebet", "placemybet", "refund",
    # consent and commitment
    "submit", "confirm", "authori", "approve", "subscri", "sign", "agree", "accept",
    "enrol", "upgrade", "renew", "book", "reserve",
    # irreversible account changes
    "delete", "remove", "deactivat", "closeaccount", "closemyaccount", "cancelaccount",
    "cancelmyaccount", "terminateaccount", "terminatemyaccount", "cancelmembership",
    "cancelplan",
    # localised (folded: marks stripped, "ł" -> "l"): de, es, fr, it, nl, pl, pt
    "zahlen", "zahlung", "kaufen", "bestell", "uberweis", "spende", "abonn", "kostenpflichtig",
    "pagar", "pago", "paga", "comprar", "compra", "pedido", "reservar",
    "acheter", "commande", "payer", "paiement",
    "acquist", "ordina",
    "betal", "afreken", "bestel", "koop",
    "zaplac", "zamow", "kupuj", "kupic",
    "finalizar", "encomend",
    # Review I5 MAJOR-6 — money, trading and commitment verbs (defence in depth; the task
    # scope is the primary control). Substring stems: each is distinctive enough inside a
    # squashed id/label. Known over-matches are listed in the module docstring.
    "charge", "invest", "pledge", "contribut", "topup", "unlock", "trial", "finaliz",
    "finalis", "proceed", "complete", "finish", "redeem", "execut", "addtocart",
    "addtobasket", "addtobag", "dollar", "euro",
)

#: Payment-instrument / number-like-secret field stems (fill/select only).
_PAYMENT_FIELD_STEMS: tuple[str, ...] = (
    "card", "cvc", "cvv", "iban", "securitycode", "ccnum", "ccexp", "cccsc", "ccname",
    "cctype", "creditcard", "expiry", "expiration", "expdate", "validthru", "validthrough",
    "accountnumber", "accountno", "routing", "sortcode", "swift", "bankleitzahl",
    "kontonummer", "rekeningnummer",
    # localised card / expiry words (folded)
    "karte", "tarjeta", "carte", "carta", "kaart", "karta", "cartao", "kortnummer",
    "vencimiento", "caducidad", "scadenza", "vervaldatum", "ablaufdatum", "gultig", "validade",
)

#: Word tokens that name a payment/secret field but are too short to use as substrings.
_PAYMENT_FIELD_TOKENS = frozenset({
    "pan", "cc", "exp", "csc", "cvv2", "bic", "pin", "ssn", "aba", "tan",
})

#: HTML autocomplete payment tokens (``cc-number``, ``cc-csc``, ``cc-exp`` ...).
_CC_AUTOCOMPLETE = re.compile(r"(?<![a-z0-9])cc-[a-z]")

#: "MM / YY", "MM/AA", "MM-JJ", "mm/yyyy" in any label or placeholder.
_EXPIRY_SHAPE = re.compile(r"(?<![a-z])mm\s*[/\-.]\s*(?:yy|yyyy|aa|aaaa|jj|jjjj|rr|rrrr)(?![a-z])")

#: "DD/MM/YYYY" is a date, not an expiry: removed before ``_EXPIRY_SHAPE`` is searched.
_DAY_MONTH = re.compile(r"dd\s*[/\-.]\s*mm")


def _expiry_shape(folded: str) -> bool:
    return bool(_EXPIRY_SHAPE.search(_DAY_MONTH.sub(" ", folded)))


#: A card-number-like placeholder: digit/x/* groups ("1234 1234 1234 1234", "xxxx-xxxx").
_DIGIT_GROUPS = re.compile(r"(?:[0-9x*#]{4}[\s\-]+){2,}[0-9x*#]{2,4}")

#: A money amount: "$50", "50 $", "USD 5", "5 EUR" (non-ASCII currency signs are R1).
_MONEY_AMOUNT = re.compile(r"\$\s?\d|\d\s?\$|\b(?:usd|eur|gbp|zar|chf|jpy|cny|inr)\s?\d|\d\s?(?:usd|eur|gbp|zar|chf|jpy|cny|inr)\b")

#: Removed before the substring scan only; the word scan still sees ``b-order`` as "b order".
_SUBSTRING_CARVE_OUTS: tuple[str, ...] = ("border",)

#: Roles/types whose activation commits or is outside what a click should do blind (R3).
_RISKY_ROLES = frozenset({"switch", "submit", "image", "file"})

#: The ``inputmode``/``type`` values that make a field number-like.
_NUMERIC_INPUT = frozenset({"numeric", "decimal", "tel", "number"})

#: A number-like field named in text ("inputmode numeric", "type tel").
_NUMERIC_WORDS = re.compile(r"\b(?:inputmode|type|input_type)\s+(?:numeric|decimal|tel|number)\b")

#: Digit lengths of the number-like secrets: CVC/PIN (3-4) and PAN (12-19).
_SECRET_DIGIT_LENGTHS = frozenset({3, 4, *range(12, 20)})


def _squash(folded: str) -> str:
    for token in _SUBSTRING_CARVE_OUTS:
        folded = folded.replace(token, " ")
    return re.sub(r"[^a-z0-9]+", "", folded)


def _tokens(texts: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for text in texts:
        out.update(w.casefold() for w in words(text).split())
        out.update(w for w in words(fold(text)).split())
    return out


#: Risk words too short or too common inside other words to use as substrings ("kopen"
#: is inside "link | open"), matched as whole folded words instead.
_RISK_WORDS = frozenset({
    "kopen", "kup", "kupi", "bet", "tip",
    # Review I5 MAJOR-6: short commitment verbs that occur inside unrelated words
    # ("forbidden", "bestseller", "mistake", "marketplace", "trademark", "current",
    # "calendar", "committee", "wireless"), so matched as whole words only.
    "bid", "bids", "bidding", "sell", "selling", "trade", "trading", "stake", "staking",
    "place", "wire", "commit", "claim", "rent", "lend", "hire", "mint", "swap", "cart",
    "basket", "continue",
})


def _segments(texts: Iterable[str]) -> list[str]:
    """Each text, split on the `` | `` that joins observed-text forms, so squashing never
    fuses the end of one field with the start of the next ("link" + "open")."""
    return [seg for text in texts for seg in str(text).split(" | ") if seg]


def risk_stem_hits(texts: Iterable[str]) -> list[str]:
    """R2 — the commitment stems (and money amounts) present in ``texts``, folded."""
    hits: list[str] = []
    texts = _segments(texts)
    hits.extend(sorted(f"word:{w}" for w in _tokens(texts) & _RISK_WORDS))
    for text in texts:
        folded = fold(text)
        squashed = _squash(folded)
        hits.extend(stem for stem in _RISK_STEMS if stem in squashed)
        if HIGH_RISK_WORDS.search(words(folded)) or HIGH_RISK_WORDS.search(words(text)):
            hits.append("word")
        if _MONEY_AMOUNT.search(folded):
            hits.append("money_amount")
    return list(dict.fromkeys(hits))


def payment_field_text_hits(texts: Iterable[str]) -> list[str]:
    """R4 (text part) — payment-instrument / number-like-secret signals in ``texts``."""
    texts = _segments(texts)
    hits: list[str] = []
    for text in texts:
        folded = fold(text)
        squashed = _squash(folded)
        hits.extend(stem for stem in _PAYMENT_FIELD_STEMS if stem in squashed)
        if _CC_AUTOCOMPLETE.search(folded):
            hits.append("cc-autocomplete")
        if _expiry_shape(folded):
            hits.append("mm/yy")
        if _DIGIT_GROUPS.search(folded):
            hits.append("digit_groups")
    tokens = _tokens(texts)
    hits.extend(sorted(f"token:{t}" for t in tokens & _PAYMENT_FIELD_TOKENS))
    joined = fold(" | ".join(texts))
    if _NUMERIC_WORDS.search(joined):
        lengths = {int(n) for n in re.findall(r"\bmaxlength\s+(\d+)", joined)}
        if lengths & _SECRET_DIGIT_LENGTHS:
            hits.append("numeric_maxlength_text")
    return list(dict.fromkeys(hits))


# ------------------------------------------------------------------ element evidence

#: Element keys that are not text (booleans, bounds, the Harness binding and the page URL,
#: which the task-scope gate judges) and must not be read as words.
_NON_TEXT_KEYS = frozenset({
    "hidden", "maxlength", "minlength", "size", "visible", "enabled", "disabled",
    "binding", "page_url", "occluded", "shadow_host", "frame", "submits",
    # el.type: every <button> reports "submit" even outside a form; whether it submits is
    # ``submits`` (R3), and the attribute ``type`` is still read.
    "effective_type",
})


#: Structural keys read as "key value" ("inputmode numeric", "type tel") so the text a
#: label-only caller receives still says what kind of field it is.
_NAMED_KEYS = frozenset({"type", "input_type", "inputmode", "inputMode", "pattern"})


def element_texts(element: dict[str, Any] | None, locator: str | None = None) -> list[str]:
    """Every string the Harness reported about the element (top level and ``attributes``,
    attribute names included), then the locator. Reads everything rather than a list of
    keys, so a new ``data-*``, ``class``, ``aria-describedby`` text or accessible
    description cannot be missed by omission."""
    parts: list[str] = []

    def add(value: Any, name: str | None = None) -> None:
        if isinstance(value, str) and value:
            parts.append(f"{name} {value}" if name else value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                add(item, name)
        elif isinstance(value, dict):
            for key, item in value.items():
                add(item, str(key))

    for key, value in (element or {}).items():
        if key in _NON_TEXT_KEYS or key == "attributes":
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            continue
        # data-* keys reported at top level carry their name, like attributes do.
        named = str(key).startswith(("data-", "data_", "aria-")) or key in _NAMED_KEYS
        add(value, key if named else None)
    attributes = (element or {}).get("attributes")
    if isinstance(attributes, dict):
        for name, value in attributes.items():
            if name in _NON_TEXT_KEYS:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                continue
            add(value, str(name))
    # Bounds are not words, but "maxlength 4" beside "inputmode numeric" is a CVC/PIN field
    # even when only the joined text reaches the classifier (a label-only caller).
    for source in (element or {}, attributes if isinstance(attributes, dict) else {}):
        for key in ("maxlength", "maxLength"):
            value = source.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip():
                parts.append(f"maxlength {value}")
    if locator:
        parts.append(locator)
    # Markup inside a reported name ("P<span>a</span>y now") read with the tags removed too.
    parts += [re.sub(r"<[^>]*>", "", p) for p in parts if "<" in p and ">" in p]
    return list(dict.fromkeys(parts))


def _field(element: dict[str, Any], *names: str) -> str:
    """A field from the element or its ``attributes``, as folded text ("" when absent)."""
    attributes = element.get("attributes") if isinstance(element.get("attributes"), dict) else {}
    values = []
    for name in names:
        for source in (element, attributes):
            value = source.get(name)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                values.append(str(value))
    return fold(" ".join(values)).strip()


def _int(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else None


def _pattern_digit_lengths(pattern: str) -> set[int]:
    """Digit counts a ``pattern`` attribute admits, for the common shapes
    ``\\d{3,4}``, ``[0-9]{16}``, ``\\d{12,19}``."""
    if not re.search(r"\\d|\[0-9\]", pattern):
        return set()
    lengths: set[int] = set()
    for low, comma, high in re.findall(r"\{(\d+)(,?)(\d*)\}", pattern):
        lo = int(low)
        hi = int(high) if high else (40 if comma else lo)
        lengths.update(range(lo, min(hi, 40) + 1))
    return lengths


def structural_field_hits(element: dict[str, Any] | None) -> list[str]:
    """R4 (structure part) — what the field's attributes say, whatever its label says."""
    if not isinstance(element, dict):
        return []
    hits: list[str] = []
    input_type = _field(element, "type", "input_type")
    inputmode = _field(element, "inputmode", "inputMode")
    autocomplete = _field(element, "autocomplete", "x-autocompletetype", "autocompletetype")
    pattern_raw = " ".join(
        str(v) for v in (element.get("pattern"), (element.get("attributes") or {}).get("pattern")
                         if isinstance(element.get("attributes"), dict) else None) if isinstance(v, str)
    )
    maxlength = _int(_field(element, "maxlength", "maxLength"))
    numeric = bool({input_type, inputmode} & _NUMERIC_INPUT) or bool(_pattern_digit_lengths(pattern_raw))
    if _CC_AUTOCOMPLETE.search(autocomplete):
        hits.append("autocomplete:cc")
    if numeric and maxlength in _SECRET_DIGIT_LENGTHS:
        hits.append(f"numeric_maxlength:{maxlength}")
    if _pattern_digit_lengths(pattern_raw) & _SECRET_DIGIT_LENGTHS:
        hits.append("pattern_secret_digits")
    if input_type == "password" and numeric:
        hits.append("numeric_password")
    placeholder = _field(element, "placeholder")
    if _DIGIT_GROUPS.search(placeholder) or len(re.sub(r"\D", "", placeholder)) >= 12:
        hits.append("placeholder:digit_groups")
    if _expiry_shape(placeholder):
        hits.append("placeholder:mm/yy")
    if input_type in ("tel", "number") or inputmode in ("numeric", "decimal"):
        hint_tokens = _tokens(element_texts(element)) & _PAYMENT_FIELD_TOKENS
        if hint_tokens:
            hits.append(f"numeric_with_hint:{','.join(sorted(hint_tokens))}")
    return hits


def _role(element: dict[str, Any] | None) -> set[str]:
    if not isinstance(element, dict):
        return set()
    roles = {v for v in (_field(element, "role"), _field(element, "type", "input_type")) if v}
    if element.get("submits") is True:
        # Review I5 MAJOR-4: a <button> with no type in a form submits it (el.type).
        roles.add("submit")
    return roles


#: Roles a resolved target may have (review I5 MAJOR-2): a control. ``generic``, ``none``,
#: ``presentation``, landmarks, headings, images and frames are not something a click can
#: be positively established to mean anything about — the router treats them as unresolved.
INTERACTIVE_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "tab", "menuitem", "menuitemcheckbox",
    "menuitemradio", "option", "switch", "textbox", "searchbox", "combobox", "spinbutton",
    "slider", "treeitem", "gridcell", "listbox",
})

#: Roles whose accessible name comes from their content (the Harness NAME_FROM_CONTENT set).
_NAME_FROM_CONTENT = frozenset({
    "button", "link", "menuitem", "menuitemcheckbox", "menuitemradio", "tab", "option",
    "checkbox", "radio", "switch", "treeitem", "gridcell",
})


def _norm(text: Any) -> str:
    return " ".join(words(fold(text)).lower().split())


#: The Harness's redaction marker (harness_service.REDACTED).
REDACTION_MARKER = "[REDACTED]"


def redacted_content(element: dict[str, Any] | None) -> bool:
    """Integration G8 — True when the Harness masked part of the element's shown content."""
    if not isinstance(element, dict):
        return False
    shown: list[Any] = [element.get("text")]
    media = element.get("media")
    if isinstance(media, (list, tuple)):
        shown.extend(media)
    form = element.get("form")
    if isinstance(form, dict):
        shown.extend([form.get("action"), form.get("formaction")])
    return any(isinstance(v, str) and REDACTION_MARKER in v for v in shown)


def content_rules(operation: str, element: dict[str, Any] | None) -> list[str]:
    """Review I5 MAJOR-1/-5 — the accessible name is not the only thing a control shows.

    For a Harness-reported element (it carries ``text``): a click with an empty name is A4
    (``R8``); a name-from-content role with no visible text is A4 (``R8``) — an image-only
    or icon-only control is judged by its media names, but is never positively low-risk;
    and a name-from-content role whose name differs from its visible text is A4 (``R7``:
    ``aria-label``/``aria-labelledby`` saying "Next" over a "Pay 500 now" button).
    """
    if not isinstance(element, dict) or operation != "click":
        return []
    name = _norm(element.get("name") or element.get("label") or "")
    rules: list[str] = []
    if not name:
        rules.append("R8_EMPTY_NAME")
    if "text" not in element:
        return rules
    text = _norm(element.get("text"))
    role = _field(element, "role")
    if role in _NAME_FROM_CONTENT:
        if not text:
            rules.append("R8_EMPTY_TEXT")
        elif name and name != text:
            rules.append("R7_NAME_CONTENT_MISMATCH")
    return rules


# ------------------------------------------------------------------ the classifier


@dataclass(frozen=True)
class RiskAssessment:
    """The class VAN derived and the rules that decided it (``R1``..``R6``, ``LOW_RISK``)."""

    action_class: str
    rules: tuple[str, ...]


def assess_action(
    operation: str,
    *,
    element: dict[str, Any] | None = None,
    locator: str | None = None,
    resolved: bool = True,
    extra_texts: Iterable[str] = (),
) -> RiskAssessment:
    """Classify one operation on one target. Fails safe: see the module docstring."""
    if operation in TARGETLESS_OPERATIONS:
        return RiskAssessment("A0", ("TARGETLESS",))
    texts = element_texts(element if resolved else None, locator) + [t for t in extra_texts if t]
    rules: list[str] = []
    bad = "".join(unmapped_characters(t) for t in texts)
    if bad:
        rules.append(f"R1_NON_LATIN_OR_UNMAPPED:{''.join(dict.fromkeys(bad))[:16]}")
    stems = risk_stem_hits(texts)
    if stems:
        rules.append(f"R2_RISK_STEM:{','.join(stems[:6])}")
    risky_roles = _role(element) & _RISKY_ROLES if resolved else set()
    if risky_roles:
        rules.append(f"R3_RISKY_ROLE:{','.join(sorted(risky_roles))}")
    if resolved:
        rules.extend(content_rules(operation, element))
        if operation in TARGETED_OPERATIONS and redacted_content(element):
            rules.append("R11_REDACTED_CONTENT")
    if operation in WRITE_OPERATIONS:
        field_hits = payment_field_text_hits(texts) + (structural_field_hits(element) if resolved else [])
        if field_hits:
            rules.append(f"R4_PAYMENT_OR_SECRET_FIELD:{','.join(field_hits[:6])}")
    if operation in TARGETED_OPERATIONS:
        if not texts:
            rules.append("R5_NO_EVIDENCE")
        if not resolved:
            # Review I5 / owner decision 2026-09-30: an action runs only on the element the
            # Harness bound and verifies at the moment it acts. A target the Harness did not
            # resolve cannot be that element, click included (I4 let a plain-ASCII locator
            # through as A2).
            rules.append("R6_UNRESOLVED_WRITE" if operation in WRITE_OPERATIONS else "R6_UNRESOLVED_TARGET")
    if rules:
        return RiskAssessment("A4", tuple(rules))
    if operation == "fill":
        return RiskAssessment("A3", ("LOW_RISK",))
    return RiskAssessment("A2", ("LOW_RISK",))


#: Keys that activate the focused element (a click on it).
_ACTIVATION_KEYS = frozenset({"enter", "numpadenter", " ", "space", "spacebar"})
#: Keys that move focus/scroll and change nothing by themselves.
_NAVIGATION_KEYS = frozenset({
    "tab", "arrowup", "arrowdown", "arrowleft", "arrowright", "pageup", "pagedown", "home",
    "end", "escape",
})
#: Roles/tags that take typed text.
_FIELD_ROLES = frozenset({"textbox", "searchbox", "combobox", "spinbutton"})


def key_activates(key: str | None) -> bool:
    """Enter/Space, alone or with modifiers ("Shift+Enter"), activate the focused element."""
    raw = str(key or "")
    if raw.endswith(" "):  # " " is Space in Playwright/CDP key names ("Shift+ " too)
        return True
    return raw.split("+")[-1].strip().lower() in _ACTIVATION_KEYS


def _is_field(element: dict[str, Any]) -> bool:
    tag = _field(element, "tag")
    typ = _field(element, "effective_type", "type")
    return (
        _field(element, "role") in _FIELD_ROLES
        or tag == "textarea"
        or (tag == "input" and typ not in ("button", "submit", "reset", "image", "checkbox", "radio", "file", "range", "color"))
    )


def assess_key_press(key: str | None, focused: dict[str, Any] | None, *, resolved: bool = True) -> RiskAssessment:
    """Review I5 MAJOR-3 — ``press_key`` is classified against ``document.activeElement``.

    * unknown focus (the Harness did not report/bind it) -> A4 (``R6_UNRESOLVED_FOCUS``);
    * Enter/Space (with or without modifiers) -> a click on the focused element;
    * any other key in a field -> a fill of that field;
    * a navigation key (Tab, arrows, Page/Home/End, Escape) outside a field -> A2;
    * any other key outside a field -> A4 (``R10_KEY_OUTSIDE_FIELD``): its effect is the
      page's keyboard handler, which nothing observed.
    """
    if not key:
        return RiskAssessment("A4", ("R5_NO_KEY",))
    if not resolved or not isinstance(focused, dict):
        return RiskAssessment("A4", ("R6_UNRESOLVED_FOCUS",))
    if key_activates(key):
        if _field(focused, "role") not in INTERACTIVE_ROLES:
            return RiskAssessment("A4", ("KEY_ACTIVATES_FOCUSED", "R9_FOCUS_NOT_A_CONTROL"))
        inner = assess_action("click", element=focused, locator=None, resolved=True)
        return RiskAssessment(inner.action_class, ("KEY_ACTIVATES_FOCUSED",) + inner.rules)
    if _is_field(focused):
        inner = assess_action("fill", element=focused, locator=None, resolved=True)
        return RiskAssessment(inner.action_class, ("KEY_FILLS_FOCUSED",) + inner.rules)
    last = str(key).split("+")[-1].strip().lower()
    if last in _NAVIGATION_KEYS:
        return RiskAssessment("A2", ("KEY_NAVIGATES",))
    return RiskAssessment("A4", ("R10_KEY_OUTSIDE_FIELD",))


def assess_supplementary_text(operation: str, text: str | None) -> RiskAssessment:
    """A description/instruction that can only make a class stricter: ``A0`` (no signal)
    unless it is non-Latin/unmapped, names a risk stem, or (fill/select) a payment field."""
    if operation in TARGETLESS_OPERATIONS or not text:
        return RiskAssessment("A0", ("NO_SIGNAL",))
    rules: list[str] = []
    bad = unmapped_characters(text)
    if bad:
        rules.append(f"R1_NON_LATIN_OR_UNMAPPED:{bad[:16]}")
    stems = risk_stem_hits([text])
    if stems:
        rules.append(f"R2_RISK_STEM:{','.join(stems[:6])}")
    if operation in WRITE_OPERATIONS:
        hits = payment_field_text_hits([text])
        if hits:
            rules.append(f"R4_PAYMENT_OR_SECRET_FIELD:{','.join(hits[:6])}")
    return RiskAssessment("A4", tuple(rules)) if rules else RiskAssessment("A0", ("NO_SIGNAL",))


def judged_text(*texts: str | None) -> str:
    """Raw, word-split and folded forms of ``texts`` as one string: what the payment
    boundary reads, so "Páy now", "#pɑy-now" and "Pа<ZWSP>y now" reach it as "pay now"."""
    parts = [t for t in texts if t]
    forms = parts + [words(p) for p in parts] + [fold(p) for p in parts] + [words(fold(p)) for p in parts]
    return " | ".join(dict.fromkeys(t for t in forms if t))


__all__ = [
    "HIGH_RISK_WORDS",
    "INTERACTIVE_ROLES",
    "RiskAssessment",
    "assess_action",
    "assess_key_press",
    "assess_supplementary_text",
    "content_rules",
    "key_activates",
    "element_texts",
    "fold",
    "fold_latin",
    "judged_text",
    "payment_field_text_hits",
    "risk_stem_hits",
    "structural_field_hits",
    "unmapped_characters",
    "words",
]
