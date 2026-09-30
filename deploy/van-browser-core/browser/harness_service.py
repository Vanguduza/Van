#!/usr/bin/env python3
"""Private VAN Browser Harness HTTP worker.

The worker exposes only the fixed operations required by the gateway Browser Harness
adapter and delegates browser mechanics to browser-harness 0.1.13. It never accepts
Python, JavaScript, raw CDP, shell, helper source, cookies, or literal credentials over
HTTP. Authority remains in VAN Gateway.
"""
from __future__ import annotations

import atexit
import contextlib
import hashlib
import hmac
import json
import os
import re
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HARNESS_VERSION = "0.1.13"
SERVICE_VERSION = "van-browser-harness-worker/1"
MAX_BODY_BYTES = 131072
PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SECRET_RE = re.compile(r"^secretref://browser/([A-Za-z0-9._-]{1,128})$")
FILE_RE = re.compile(r"^fileref://downloads/([A-Za-z0-9._-]{1,180})$")

BIND = os.getenv("VAN_HARNESS_BIND", "127.0.0.1")
PORT = int(os.getenv("VAN_HARNESS_PORT", "9141"))
HARNESS_BIN = os.getenv(
    "VAN_BROWSER_HARNESS_BIN",
    "/opt/van-browser-core/runtime/harness-venv/bin/browser-harness",
)
CHROMIUM = os.getenv("VAN_CHROMIUM_EXECUTABLE", "")
PROFILE_ROOT = Path(
    os.getenv("VAN_BROWSER_PROFILE_ROOT", "/var/lib/van-browser-core/profiles")
)
DOWNLOAD_ROOT = Path(
    os.getenv("VAN_BROWSER_DOWNLOAD_ROOT", "/var/lib/van-browser-core/downloads")
)
SECRET_ROOT = Path(
    os.getenv("VAN_BROWSER_SECRET_ROOT", "/var/lib/van-browser-core/secrets")
)
RUNTIME_ROOT = Path(os.getenv("VAN_BROWSER_RUNTIME_ROOT", "/run/van-browser-core"))
#: Review I4 MINOR-A — where the lease fence persists the newest generation per profile.
HARNESS_STATE_ROOT = Path(
    os.getenv("VAN_HARNESS_STATE_ROOT", "/var/lib/van-browser-core/harness-state")
)
#: Review I5 F2 — written by bootstrap.sh when it creates the fence state directory. While it
#: exists, a missing fence manifest means the state was lost (not a first boot): fenced
#: calls are refused rather than the fence silently restarting at "nothing seen".
HARNESS_FENCE_INSTALL_MARKER = Path(
    os.getenv("VAN_HARNESS_FENCE_INSTALL_MARKER", "/etc/van-browser-core/harness-fence-installed")
)
#: Review I5 F3 — the key the gateway MACs each lease fence with (shared with the gateway's
#: VAN_BROWSER_HARNESS_FENCE_KEY_FILE). A file path; the key never appears in env or repo.
HARNESS_FENCE_KEY_FILE = os.getenv("VAN_HARNESS_FENCE_KEY_FILE", "")
#: Owner decision 2026-09-29 §1 — the trust zone this worker was installed into, written by
#: deploy/van-browser-core/bootstrap.sh. Reported, never inferred; the gateway's placement
#: gate refuses production Stagehand unless the zone is van-browser-core.
TRUST_ZONE = os.getenv("VAN_TRUST_ZONE", "")
REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("VAN_BROWSER_WORKER_TIMEOUT_SECONDS", "45")
)

if BIND not in {"127.0.0.1", "::1", "localhost"}:
    raise SystemExit("browser harness worker refuses a non-loopback bind")


class WorkerError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def safe_alias(value: Any) -> str:
    alias = str(value or "").strip()
    if not PROFILE_RE.fullmatch(alias):
        raise WorkerError("PROFILE_ALIAS_INVALID", 422)
    return alias


def safe_domain(value: Any) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if not domain or len(domain) > 253:
        raise WorkerError("TARGET_DOMAIN_REQUIRED", 422)
    if any(not re.fullmatch(r"[a-z0-9-]{1,63}", part) for part in domain.split(".")):
        raise WorkerError("TARGET_DOMAIN_INVALID", 422)
    return domain


def assert_url_in_domain(url: str, domain: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WorkerError("URL_SCHEME_FORBIDDEN", 422)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != domain and not host.endswith("." + domain):
        raise WorkerError("URL_OUTSIDE_TASK_DOMAIN", 403)
    return url


def safe_child(root: Path, name: str) -> Path:
    root = root.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root:
        raise WorkerError("REFERENCE_PATH_INVALID", 422)
    return candidate


def resolve_secret(value_ref: Any) -> str:
    match = SECRET_RE.fullmatch(str(value_ref or ""))
    if not match:
        raise WorkerError("SECRET_REFERENCE_REQUIRED", 422)
    path = safe_child(SECRET_ROOT, match.group(1))
    if not path.is_file():
        raise WorkerError("SECRET_REFERENCE_UNAVAILABLE", 409)
    if path.stat().st_size > 16384:
        raise WorkerError("SECRET_REFERENCE_TOO_LARGE", 409)
    return path.read_text(encoding="utf-8").rstrip("\r\n")


def resolve_upload(file_ref: Any) -> Path:
    match = FILE_RE.fullmatch(str(file_ref or ""))
    if not match:
        raise WorkerError("UPLOAD_FILE_REFERENCE_REQUIRED", 422)
    path = safe_child(DOWNLOAD_ROOT, match.group(1))
    if not path.is_file():
        raise WorkerError("UPLOAD_FILE_REFERENCE_UNAVAILABLE", 409)
    return path


class ChromeSession:
    def __init__(self, alias: str) -> None:
        self.alias = alias
        self.profile_dir = safe_child(PROFILE_ROOT, alias)
        self.runtime_dir = safe_child(RUNTIME_ROOT, alias)
        self.process: subprocess.Popen[str] | None = None
        self.cdp_url: str | None = None
        self.lock = threading.RLock()

    def ensure(self) -> str:
        with self.lock:
            if self.process is not None and self.process.poll() is None and self.cdp_url:
                self._publish_cdp()
                return self.cdp_url
            if not CHROMIUM or not Path(CHROMIUM).is_file():
                raise WorkerError("CHROMIUM_EXECUTABLE_UNAVAILABLE", 503)
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            active = self.profile_dir / "DevToolsActivePort"
            active.unlink(missing_ok=True)
            self.process = subprocess.Popen(
                [
                    CHROMIUM,
                    "--headless=new",
                    "--remote-debugging-address=127.0.0.1",
                    "--remote-debugging-port=0",
                    f"--user-data-dir={self.profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-dev-shm-usage",
                    "--disable-background-networking",
                    "--disable-component-update",
                    # Network-effect guard (unit G9c): keepalive requests and shared workers
                    # otherwise escape CDP Fetch interception.
                    *NETWORK_GUARD_CHROMIUM_FLAGS,
                    "about:blank",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise WorkerError("CHROMIUM_START_FAILED", 503)
                if active.is_file():
                    lines = active.read_text(encoding="utf-8").splitlines()
                    if lines and lines[0].isdigit():
                        self.cdp_url = f"http://127.0.0.1:{int(lines[0])}"
                        self._publish_cdp()
                        return self.cdp_url
                time.sleep(0.1)
            self.stop()
            raise WorkerError("CHROMIUM_START_TIMEOUT", 503)

    def _publish_cdp(self) -> None:
        if not self.cdp_url or self.process is None:
            return
        target = self.runtime_dir / "cdp-endpoint.json"
        tmp = self.runtime_dir / ".cdp-endpoint.json.tmp"
        tmp.write_text(
            json.dumps(
                {
                    "profile_alias": self.alias,
                    "cdp_url": self.cdp_url,
                    "pid": self.process.pid,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)

    def stop(self) -> None:
        with self.lock:
            proc, self.process = self.process, None
            self.cdp_url = None
            (self.runtime_dir / "cdp-endpoint.json").unlink(missing_ok=True)
            if proc is None or proc.poll() is not None:
                return
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


class BrowserPool:
    def __init__(self) -> None:
        self.sessions: dict[str, ChromeSession] = {}
        self.lock = threading.RLock()

    def get(self, alias: str) -> ChromeSession:
        with self.lock:
            return self.sessions.setdefault(alias, ChromeSession(alias))

    def close(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
        for session in sessions:
            session.stop()


POOL = BrowserPool()
atexit.register(POOL.close)


def harness_env(alias: str, cdp_url: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    runtime = safe_child(RUNTIME_ROOT, alias)
    paths = {
        "BH_HOME": runtime / "harness-home",
        "BH_RUNTIME_DIR": runtime / "harness-runtime",
        "BH_TMP_DIR": runtime / "harness-tmp",
        "BH_AGENT_WORKSPACE": runtime / "fixed-agent-workspace",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        **{key: str(value) for key, value in paths.items()},
        "BU_NAME": f"van_{alias}",
        "BU_CDP_URL": cdp_url,
        "BH_DOMAIN_SKILLS": "0",
        "BH_OPEN_LIVE_URL": "0",
        "BH_TAB_MARKER": "0",
    }
    if extra:
        env.update(extra)
    return env


def run_harness(alias: str, script: str, extra: dict[str, str] | None = None) -> Any:
    if not Path(HARNESS_BIN).is_file():
        raise WorkerError("BROWSER_HARNESS_EXECUTABLE_UNAVAILABLE", 503)
    session = POOL.get(alias)
    cdp_url = session.ensure()
    with session.lock:
        try:
            completed = subprocess.run(
                [HARNESS_BIN],
                input=script,
                text=True,
                capture_output=True,
                env=harness_env(alias, cdp_url, extra),
                timeout=REQUEST_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerError("BROWSER_HARNESS_TIMEOUT", 504) from exc
    if completed.returncode != 0:
        raise WorkerError("BROWSER_HARNESS_REQUEST_FAILED", 502)
    marker = "__VAN_JSON__"
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(marker):
            try:
                return json.loads(line[len(marker):])
            except json.JSONDecodeError as exc:
                raise WorkerError("BROWSER_HARNESS_RESPONSE_INVALID", 502) from exc
    raise WorkerError("BROWSER_HARNESS_RESPONSE_MISSING", 502)


# --------------------------------------------------------------------- element reporting
#
# Review I4 root cause: page_info returned no ``elements``, so the gateway's
# HarnessTargetResolver resolved nothing, the router's lane 1 classified on locator words
# alone and B2 (jev_eligibility) denied every page. The Harness now reports a bounded list of
# interactive and landmark elements, computed in the page (the same Chromium the Harness acts
# on) by ELEMENTS_JS below, then re-bounded and re-redacted here by sanitize_elements().
#
# Element shape (one dict per element; unit G5a's classifier and the gateway adapters read it):
#   locator       CSS selector the Harness executes back verbatim (/click, /fill, /describe);
#                 verified in-page to match exactly this element. Stable forms first:
#                 #id, tag[data-testid=...], tag[name=...], then an nth-of-type path.
#   locator_kind  "id" | "test_id" | "name" | "path" ("given" from /describe)
#   role          explicit role attribute, else the implicit ARIA role of the tag
#   name          accessible name (aria-labelledby > aria-label > label/alt/value-of-button >
#                 contents for name-from-content roles > title > placeholder)
#   description   aria-describedby text, else a title not already used as the name
#   attributes    {id, name, type, class, role, href, action, formaction, aria-label, title,
#                 alt, target, data-*}; href/action/formaction keep origin+path and query
#                 *names* only; data-* values under a sensitive name are "[REDACTED]"
#   type, autocomplete, placeholder, inputmode, maxlength (int|None), pattern, hidden (bool)
#   tag, landmark (bool), disabled (bool), checked (bool|None), sensitive (bool),
#   value_present (bool)
# Review I5 (unit G6a) — what the element *shows* and *does*, not only its accessible name:
#   text          the visible text content, its own field (MAJOR-1): aria-hidden text, text
#                 in an open shadow root, img alt and button-like input values included;
#                 for a form field, its label text. Never a field's value or contenteditable
#                 contents. Classified by the gateway like the name, and a name-from-content
#                 role whose name differs from its text is A4.
#   media         img alt/src/srcset file names, background-image file names, CSS ::before/
#                 ::after content, svg title/desc, descendant aria-label/title (MAJOR-5)
#   effective_type el.type (a <button> with no type is "submit")
#   submits       the element submits a form when activated (MAJOR-4)
#   form          {action, method, formaction, formmethod, target, id, name} of the form
#                 owner (origin+path and query names only), or None
#   frame         the element is an iframe/frame/object/embed (never a resolved target)
#   occluded      /describe only: the hit test at its centre lands on something else
#   shadow_host   /describe only: it hosts a shadow root (open or closed)
# /describe also returns ``binding`` {backend_node_id, digest}: the CDP backendNodeId of the
# very node described and a digest of what was classified. /click, /press and /fill act on
# that node (never a re-queried selector) and refuse when it is gone, changed, not the node
# at the click point, or outside the task scope (MAJOR-2, owner decision 2026-09-30).
#
# Redaction: no element ever carries a ``value``. Input, textarea, select and contenteditable
# contents are never read into a name or description (a textarea's text is its value). Every
# field B2 would treat as sensitive (type=password; autocomplete cc-*, *-password,
# one-time-code; a name/id/label/placeholder naming a password, PIN, OTP, card, CVC, IBAN,
# account or sort code) is marked ``sensitive``; whether any field holds a value is reported
# only as the boolean ``value_present``. No cookie or storage content is read: page_info
# reports ``cookies_present`` and ``authenticated`` as booleans or None (unknown) only.

MAX_ELEMENTS = 200
#: Review I5: each element now also reports text, media, form and effective type.
MAX_ELEMENTS_BYTES = 98304
MAX_ELEMENT_TEXT = 256
MAX_LOCATOR_LEN = 1024
MAX_ELEMENT_ATTRIBUTES = 32
REDACTED = "[REDACTED]"
ELEMENT_STRING_KEYS = (
    "locator", "locator_kind", "role", "name", "description", "type", "autocomplete",
    "placeholder", "inputmode", "pattern", "tag", "text", "effective_type",
)
ELEMENT_BOOL_KEYS = ("hidden", "landmark", "disabled", "sensitive", "value_present", "submits", "frame")
#: Review I5 — the element's form owner, reported as these string keys only.
ELEMENT_FORM_KEYS = ("action", "method", "formaction", "formmethod", "target", "id", "name")
MAX_ELEMENT_MEDIA = 16
ATTRIBUTE_NAME_RE = re.compile(r"^(?:id|name|type|class|role|href|action|formaction|aria-label|title|alt|target|data-[a-z0-9_.:-]{1,48})$")
SENSITIVE_NAME_RE = re.compile(
    r"pass(?:word|code|phrase)?|pwd|secret|token|otp|one[-_ ]?time|2fa|mfa|\bpin\b|cvv|cvc|csc|"
    r"security[-_ ]?code|card|cc[-_]?(?:num|number|exp|csc|name)|iban|sort[-_ ]?code|routing|"
    r"account[-_ ]?(?:no|num|number)|acct|ssn|social[-_ ]?security|passport|expiry|"
    r"auth|session|csrf|xsrf|api[-_ ]?key|private[-_ ]?key|credential",
    re.IGNORECASE,
)

#: Review I5 E1 — the Python half of the value redaction (the page script also compares with
#: the page's field values, which never leave the page). Digit-heavy values (6+ digits: card,
#: account, phone, SSN) and token-like runs are redacted from data-*, aria-label/title/alt
#: copies and URL path segments.
_TOKEN_RUN_RE = re.compile(r"[A-Za-z0-9_\-+/=.~%]{16,}")
_PROTOCOL_ONLY_RE = re.compile(r"^[a-z][a-z0-9+.-]*:$")
VALUE_REDACTED_ATTRIBUTES = frozenset({"aria-label", "title", "alt"})
URL_ATTRIBUTES = frozenset({"href", "action", "formaction"})


def secret_like(value: str) -> bool:
    if sum(ch.isdigit() for ch in value) >= 6:
        return True
    for run in _TOKEN_RUN_RE.findall(value):
        if len(run) >= 32 or (re.search(r"\d", run) and re.search(r"[A-Za-z]", run)):
            return True
    return False


_DIGIT_RUN_RE = re.compile(r"\d[\d \-./]*\d")


def mask_digit_runs(value: str) -> str:
    """Replace a run carrying 6+ digits (a card or account number in a title copied into a
    description) and leave the words around it."""
    return _DIGIT_RUN_RE.sub(lambda m: REDACTED if sum(c.isdigit() for c in m.group()) >= 6 else m.group(), value)


def redact_url(value: str) -> str:
    """origin + path (secret-like segments replaced) + query *names*; never values."""
    from urllib.parse import unquote, urlsplit

    if _PROTOCOL_ONLY_RE.fullmatch(value):
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return REDACTED
    if parts.scheme and parts.scheme not in {"http", "https"}:
        return f"{parts.scheme}:"
    origin = ""
    if parts.netloc:
        host = parts.hostname or ""
        origin = f"{parts.scheme}://{host}" + (f":{parts.port}" if parts.port else "")
    segments = []
    for segment in parts.path.split("/"):
        decoded = unquote(segment)
        segments.append(REDACTED if segment and (secret_like(decoded) or len(decoded) >= 32) else segment)
    names = [item.split("=", 1)[0] for item in parts.query.split("&") if item]
    return _clip(origin + "/".join(segments) + ("?" + "&".join(names) if names else ""))


def mask_secret_runs(value: str) -> str:
    """Integration G8 — mask_digit_runs plus token-like runs (the secret_like rules), words kept.

    Applied to the G6a fields that carry page text (``text``, ``media``, the form owner's
    names). The gateway reads a masked text/media entry as A4 (action_risk ``R11``)."""
    value = mask_digit_runs(value)
    return _TOKEN_RUN_RE.sub(
        lambda m: REDACTED if len(m.group()) >= 32 or (re.search(r"\d", m.group()) and re.search(r"[A-Za-z]", m.group())) else m.group(),
        value,
    )


#: el.type values the Harness reports as ``effective_type`` (a page can redefine el.type).
EFFECTIVE_TYPES = frozenset({
    "button", "checkbox", "color", "date", "datetime-local", "email", "file", "hidden", "image",
    "month", "number", "password", "radio", "range", "reset", "search", "select-multiple",
    "select-one", "submit", "tel", "text", "textarea", "time", "url", "week",
})
FORM_METHODS = frozenset({"get", "post", "dialog", "other"})


def sanitize_form(form: Any) -> dict[str, str] | None:
    if not isinstance(form, dict):
        return None
    out = {k: _clip(form.get(k) if isinstance(form.get(k), str) else "") for k in ELEMENT_FORM_KEYS}
    for key in ("action", "formaction"):
        out[key] = redact_url(out[key]) if out[key] else ""
    for key in ("method", "formmethod"):
        out[key] = out[key].lower() if out[key].lower() in FORM_METHODS else ("other" if out[key] else "")
    for key in ("target", "id", "name"):
        out[key] = mask_secret_runs(out[key])
    return out


def sanitize_attribute(name: str, value: str) -> str:
    if name in URL_ATTRIBUTES:
        return redact_url(value)
    if name.startswith("data-"):
        return REDACTED if SENSITIVE_NAME_RE.search(name) or secret_like(value) else _clip(value)
    if name in VALUE_REDACTED_ATTRIBUTES and secret_like(value):
        return REDACTED
    return _clip(value)


ELEMENTS_JS = r"""
(async (mode, target) => {
  const MAX = 200, MAX_BYTES = 92000, TEXT = 256, SCAN = 3000;
  const SENSITIVE = /pass(word|code|phrase)?|pwd|secret|token|otp|one[-_ ]?time|2fa|mfa|\bpin\b|cvv|cvc|csc|security[-_ ]?code|card|cc[-_]?(num|number|exp|csc|name)|iban|sort[-_ ]?code|routing|account[-_ ]?(no|num|number)|acct|ssn|social[-_ ]?security|passport|expiry|auth|session|csrf|xsrf|api[-_ ]?key|private[-_ ]?key|credential/i;
  const SENSITIVE_AUTOCOMPLETE = /^(cc-|current-password|new-password|one-time-code)/;
  const SIGN_OUT = /^\s*(sign|log)[\s-]?out\b|^\s*logout\b/i;
  const INTERACTIVE = 'a[href],button,input:not([type="hidden" i]),select,textarea,summary,[role],[contenteditable=""],[contenteditable="true" i],[tabindex]:not([tabindex="-1"]),[onclick]';
  const LANDMARK_SEL = 'nav,main,header,footer,aside,form,section[aria-label],section[aria-labelledby],dialog';
  const ROLE_INTERACTIVE = new Set(['button','link','textbox','searchbox','combobox','checkbox','radio','tab','menuitem','menuitemcheckbox','menuitemradio','option','listbox','switch','slider','spinbutton','treeitem','gridcell','generic']);
  const ROLE_LANDMARK = new Set(['navigation','main','banner','contentinfo','complementary','form','region','search','dialog','alertdialog']);
  const NAME_FROM_CONTENT = new Set(['button','link','menuitem','menuitemcheckbox','menuitemradio','tab','option','checkbox','radio','switch','treeitem','gridcell','heading','tooltip']);
  const SKIP_TEXT = new Set(['SCRIPT','STYLE','NOSCRIPT','TEXTAREA','SELECT','OPTION','INPUT','TEMPLATE']);
  const clip = (s) => { s = String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); return s.length > TEXT ? s.slice(0, TEXT) : s; };
  // Review I5 E1 — values a page mirrors out of its fields (data-value, data-pan...) or carries
  // as secrets (card numbers, reset tokens) are redacted wherever an attribute or URL path
  // would otherwise report them. Field values are read only to compare; never reported.
  const VALUELESS = new Set(['button', 'submit', 'reset', 'image', 'checkbox', 'radio', 'file', 'color', 'range']);
  const digitsOf = (v) => String(v).replace(/\D+/g, '');
  const FIELD_VALUES = (() => {
    const out = [];
    try {
      for (const f of document.querySelectorAll('input,textarea,select,[contenteditable=""],[contenteditable="true" i]')) {
        if (out.length >= 400) break;
        const tag = f.localName, type = (f.getAttribute('type') || '').toLowerCase();
        if (tag === 'input' && VALUELESS.has(type)) continue;
        const vals = [];
        try { vals.push(f.isContentEditable && tag !== 'input' && tag !== 'textarea' ? f.textContent : f.value); } catch (e) { /* unreadable */ }
        vals.push(f.getAttribute('value'));
        for (let v of vals) { v = String(v == null ? '' : v).trim(); if (v.length >= 3) out.push(v.toLowerCase()); }
      }
    } catch (e) { /* no fields */ }
    return out;
  })();
  function secretLike(v) {
    v = String(v == null ? '' : v);
    if (digitsOf(v).length >= 6) return true;
    for (const run of v.match(/[A-Za-z0-9_\-+\/=.~%]{16,}/g) || []) {
      if (run.length >= 32 || (/\d/.test(run) && /[A-Za-z]/.test(run))) return true;
    }
    const low = v.toLowerCase().trim(), dv = digitsOf(v);
    for (const f of FIELD_VALUES) {
      if (low === f || (f.length >= 4 && low.includes(f))) return true;
      const df = digitsOf(f);
      if (df.length >= 4 && dv.includes(df)) return true;
    }
    return false;
  }
  // Integration G8 — G6b's E1 redaction extended to the G6a fields that carry page text
  // (text, media, the form owner's names): a card/account digit run, a token-like run or a
  // field's value is replaced where it appears, and the words around it are kept. The
  // gateway treats a redacted text/media entry as A4 (R11), so a redaction can never hide
  // a risk word from the classifier.
  const DIGIT_RUN = /\d[\d \-.\/]*\d/g;
  const TOKEN_RUN = /[A-Za-z0-9_\-+\/=.~%]{16,}/g;
  const reEsc = (v) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  function maskSecrets(v) {
    let s = String(v == null ? '' : v);
    if (!s) return s;
    s = s.replace(DIGIT_RUN, (m) => digitsOf(m).length >= 6 ? '[REDACTED]' : m);
    s = s.replace(TOKEN_RUN, (m) => (m.length >= 32 || (/\d/.test(m) && /[A-Za-z]/.test(m))) ? '[REDACTED]' : m);
    for (const f of FIELD_VALUES) {
      if (f.length < 4) continue;
      s = s.replace(new RegExp(reEsc(f), 'gi'), '[REDACTED]');
    }
    return s;
  }
  const esc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, (c) => '\\' + c);
  const unique = (sel, el) => { try { const n = document.querySelectorAll(sel); return n.length === 1 && n[0] === el; } catch (e) { return false; } };
  function locatorFor(el) {
    if (el.id) { const s = '#' + esc(el.id); if (unique(s, el)) return [s, 'id']; }
    for (const a of ['data-testid', 'data-test', 'data-qa', 'data-cy']) {
      const v = el.getAttribute(a);
      if (v) { const s = el.localName + '[' + a + '="' + esc(v) + '"]'; if (unique(s, el)) return [s, 'test_id']; }
    }
    const nm = el.getAttribute('name');
    if (nm) { const s = el.localName + '[name="' + esc(nm) + '"]'; if (unique(s, el)) return [s, 'name']; }
    const parts = []; let n = el;
    while (n && n.nodeType === 1 && n !== document.documentElement) {
      if (n !== el && n.id && unique('#' + esc(n.id), n)) { parts.unshift('#' + esc(n.id)); n = null; break; }
      let i = 1, s = n; while ((s = s.previousElementSibling)) if (s.localName === n.localName) i++;
      parts.unshift(n.localName + ':nth-of-type(' + i + ')');
      n = n.parentElement;
    }
    if (n === document.documentElement) parts.unshift('html');
    const s = parts.join(' > ');
    return unique(s, el) ? [s, 'path'] : [null, null];
  }
  function implicitRole(el) {
    const tag = el.localName, type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a' || tag === 'area') return el.hasAttribute('href') ? 'link' : 'generic';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'input') {
      if (['button', 'submit', 'reset', 'image', 'file', 'color'].includes(type)) return 'button';
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'range') return 'slider';
      if (type === 'number') return 'spinbutton';
      if (type === 'search') return el.hasAttribute('list') ? 'combobox' : 'searchbox';
      return el.hasAttribute('list') ? 'combobox' : 'textbox';
    }
    if (tag === 'select') return (el.multiple || el.size > 1) ? 'listbox' : 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'nav') return 'navigation';
    if (tag === 'main') return 'main';
    if (tag === 'aside') return 'complementary';
    if (tag === 'form') return 'form';
    if (tag === 'section') return 'region';
    if (tag === 'dialog') return 'dialog';
    if (tag === 'header' || tag === 'footer') {
      if (el.closest('article,aside,main,nav,section') && el.closest('article,aside,main,nav,section') !== el) return 'generic';
      return tag === 'header' ? 'banner' : 'contentinfo';
    }
    if (el.isContentEditable) return 'textbox';
    return 'generic';
  }
  function roleOf(el) {
    const r = (el.getAttribute('role') || '').trim().toLowerCase().split(/\s+/)[0];
    return r || implicitRole(el);
  }
  function textOf(node, depth) {
    if (!node || depth > 12) return '';
    if (node.nodeType === 3) return node.nodeValue || '';
    if (node.nodeType !== 1) return '';
    if (SKIP_TEXT.has(node.tagName) || node.isContentEditable) {
      if (node.tagName === 'INPUT') {
        const t = (node.getAttribute('type') || '').toLowerCase();
        if (['button', 'submit', 'reset'].includes(t)) return ' ' + (node.getAttribute('value') || '') + ' ';
        if (t === 'image') return ' ' + (node.getAttribute('alt') || '') + ' ';
      }
      return ' ';
    }
    if (node.getAttribute('aria-hidden') === 'true') return '';
    if (node.tagName === 'IMG') return ' ' + (node.getAttribute('alt') || '') + ' ';
    let out = '';
    for (const c of node.childNodes) { out += textOf(c, depth + 1); if (out.length > TEXT * 2) break; }
    return out;
  }
  // Review I5 MAJOR-1/-5 — what the element shows: text content (aria-hidden and open
  // shadow content included, field values and contenteditable contents never), and the
  // file names / alt text of the images it renders.
  function rawText(node, depth) {
    if (!node || depth > 12) return '';
    if (node.nodeType === 3) return node.nodeValue || '';
    if (node.nodeType === 11) { let o = ''; for (const c of node.childNodes) { o += rawText(c, depth + 1); if (o.length > TEXT * 2) break; } return o; }
    if (node.nodeType !== 1) return '';
    const tag = node.tagName;
    // OUTPUT: its content is its value (review I5 probe OUTVAL; integration G8).
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'TEMPLATE' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'OPTION' || tag === 'OUTPUT') return ' ';
    if (tag === 'INPUT') {
      const t = (node.getAttribute('type') || '').toLowerCase();
      if (['button', 'submit', 'reset'].includes(t)) return ' ' + (node.getAttribute('value') || (t === 'submit' ? 'Submit' : t === 'reset' ? 'Reset' : '')) + ' ';
      if (t === 'image') return ' ' + (node.getAttribute('alt') || '') + ' ';
      return ' ';
    }
    if (node.isContentEditable) return ' ';
    // An ARIA field's content is its value (integration G8): never a container's text either.
    if (FIELD_ROLES.has((node.getAttribute('role') || '').trim().toLowerCase().split(/\s+/)[0])) return ' ';
    if (tag === 'IMG') return ' ' + (node.getAttribute('alt') || '') + ' ';
    let out = '';
    const kids = node.shadowRoot ? [node.shadowRoot, ...node.childNodes] : node.childNodes;
    for (const c of kids) { out += rawText(c, depth + 1); if (out.length > TEXT * 2) break; }
    return out;
  }
  // An ARIA field (role textbox/searchbox/spinbutton/combobox) shows its value as its text
  // content: rawText() reads it as nothing, on its own or inside a container (integration G8,
  // E1 x MAJOR-1).
  const FIELD_ROLES = new Set(['textbox', 'searchbox', 'spinbutton', 'combobox']);
  function isFieldEl(el) {
    const tag = el.localName, t = (el.getAttribute('type') || '').toLowerCase();
    return (tag === 'input' && !['button', 'submit', 'reset', 'image'].includes(t)) || tag === 'textarea' || tag === 'select' || el.isContentEditable;
  }
  function contentText(el) {
    if (isFieldEl(el)) return clip(maskSecrets(el.labels && el.labels.length ? Array.from(el.labels).map((l) => rawText(l, 0)).join(' ') : ''));
    return clip(maskSecrets(String(rawText(el, 0)).replace(/\s+/g, ' ').trim()));
  }
  function fileName(u) {
    try {
      if (/^\s*data:/i.test(u)) return 'data-url';
      const x = new URL(u, location.href);
      const seg = x.pathname.split('/').filter(Boolean).pop() || x.hostname;
      try { return clip(decodeURIComponent(seg)); } catch (e) { return clip(seg); }
    } catch (e) { return clip(String(u).slice(-64)); }
  }
  function cssNames(node, pseudo) {
    const out = [];
    try {
      const cs = getComputedStyle(node, pseudo);
      (cs.backgroundImage || '').replace(/url\(\s*(['"]?)(.*?)\1\s*\)/g, (m, q, u) => { out.push(fileName(u)); return m; });
      if (pseudo) { const c = cs.content || ''; if (c && c !== 'none' && c !== 'normal') out.push(clip(c.replace(/^["']|["']$/g, ''))); }
    } catch (e) { /* unreadable style: nothing */ }
    return out;
  }
  function mediaOf(el) {
    const out = []; let seen = 0;
    const visit = (node, depth) => {
      if (!node || depth > 8 || seen > 60 || out.length >= 32) return;
      if (node.nodeType === 11) { for (const c of node.children) visit(c, depth + 1); return; }
      if (node.nodeType !== 1) return;
      seen++;
      const tag = node.localName;
      if (tag === 'img' || (tag === 'input' && (node.getAttribute('type') || '').toLowerCase() === 'image')) {
        const alt = node.getAttribute('alt'); if (alt) out.push(clip(alt));
        const src = node.getAttribute('src'); if (src) out.push(fileName(src));
        const set = node.getAttribute('srcset');
        if (set) set.split(',').forEach((part) => { const u = part.trim().split(/\s+/)[0]; if (u) out.push(fileName(u)); });
      }
      if ((tag === 'title' || tag === 'desc') && node.namespaceURI === 'http://www.w3.org/2000/svg') out.push(clip(node.textContent));
      if (tag === 'use') { const h = node.getAttribute('href') || node.getAttribute('xlink:href'); if (h) out.push(fileName(h)); }
      if (node !== el) {
        const al = node.getAttribute('aria-label'); if (al) out.push(clip(al));
        const ti = node.getAttribute('title'); if (ti) out.push(clip(ti));
      }
      for (const pseudo of [null, '::before', '::after']) out.push(...cssNames(node, pseudo));
      if (node.shadowRoot) visit(node.shadowRoot, depth + 1);
      for (const c of node.children) visit(c, depth + 1);
    };
    visit(el, 0);
    return Array.from(new Set(out.filter(Boolean).map((m) => clip(maskSecrets(m))))).slice(0, 16);
  }
  const FRAME_TAGS = new Set(['iframe', 'frame', 'object', 'embed', 'portal', 'fencedframe']);
  // Review I5 MAJOR-4 — the element's effective type and what activating it submits.
  function submitsOf(el) {
    const tag = el.localName, t = String(el.type || '').toLowerCase();
    return !!el.form && ((tag === 'button' && t === 'submit') || (tag === 'input' && (t === 'submit' || t === 'image')));
  }
  // Only the enumerated values are reported (a page can put anything in these attributes, or
  // redefine el.type): anything else is ''.
  const FORM_METHODS = new Set(['get', 'post', 'dialog']);
  const formMethod = (v) => { v = String(v || '').trim().toLowerCase(); return FORM_METHODS.has(v) ? v : (v ? 'other' : ''); };
  const EFFECTIVE_TYPES = new Set(__EFFECTIVE_TYPES__);
  const effectiveType = (el) => { let t = ''; try { t = String(el.type || '').toLowerCase(); } catch (e) { t = ''; } return EFFECTIVE_TYPES.has(t) ? t : ''; };
  function formOf(el) {
    const f = el.form;
    if (!f || typeof HTMLFormElement === 'undefined' || !(f instanceof HTMLFormElement)) return null;
    const attr = (n, a) => HTMLElement.prototype.getAttribute.call(n, a);
    const abs = (v) => { try { return new URL(v == null ? location.href : v, document.baseURI).href; } catch (e) { return ''; } };
    const sub = submitsOf(el);
    return {
      action: safeUrl(abs(attr(f, 'action'))), method: formMethod(attr(f, 'method') || 'get'),
      formaction: sub && el.hasAttribute('formaction') ? safeUrl(abs(el.getAttribute('formaction'))) : '',
      formmethod: sub ? formMethod(el.getAttribute('formmethod') || '') : '',
      target: clip(maskSecrets(attr(f, 'target') || '')), id: clip(maskSecrets(attr(f, 'id') || '')), name: clip(maskSecrets(attr(f, 'name') || '')),
    };
  }
  const byIds = (el, attr) => (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean).map((id) => {
    const r = document.getElementById(id); return r ? (r.getAttribute('aria-label') || textOf(r, 0)) : '';
  }).join(' ');
  function nameOf(el, role) {
    let n = clip(byIds(el, 'aria-labelledby')); if (n) return [n, false];
    n = clip(el.getAttribute('aria-label')); if (n) return [n, false];
    const tag = el.localName, type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && ['button', 'submit', 'reset'].includes(type)) {
      n = clip(el.getAttribute('value') || (type === 'submit' ? 'Submit' : type === 'reset' ? 'Reset' : '')); if (n) return [n, false];
    }
    if (tag === 'input' && type === 'image') { n = clip(el.getAttribute('alt')); if (n) return [n, false]; }
    if (el.labels && el.labels.length) { n = clip(Array.from(el.labels).map((l) => textOf(l, 0)).join(' ')); if (n) return [n, false]; }
    if (tag === 'fieldset') { const lg = el.querySelector('legend'); n = clip(lg ? textOf(lg, 0) : ''); if (n) return [n, false]; }
    if ((NAME_FROM_CONTENT.has(role) || tag === 'button' || tag === 'a' || tag === 'summary') && !el.isContentEditable) {
      n = clip(textOf(el, 0)); if (n) return [n, false];
    }
    n = clip(el.getAttribute('title')); if (n) return [n, true];
    n = clip(el.getAttribute('placeholder')); if (n) return [n, false];
    return ['', false];
  }
  function isHidden(el) {
    if (el.closest('[hidden],[aria-hidden="true"],[inert]')) return true;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse' || parseFloat(cs.opacity) === 0) return true;
    if (typeof el.checkVisibility === 'function' && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return true;
    const r = el.getBoundingClientRect();
    return !(r.width > 0 && r.height > 0);
  }
  function safeUrl(raw) {
    if (!raw) return '';
    try {
      const u = new URL(raw, location.href);
      if (!/^https?:$/.test(u.protocol)) return clip(u.protocol);
      const keys = Array.from(u.searchParams.keys());
      // Review I5 E1 — a path segment that is a token, a long identifier or a field's value
      // (/reset/tok_9f8e7d6c5b4a/confirm) is replaced; query values are already dropped.
      const path = u.pathname.split('/').map((seg) => {
        let d = seg; try { d = decodeURIComponent(seg); } catch (e) { /* keep raw */ }
        return seg && (secretLike(d) || d.length >= 32) ? '[REDACTED]' : seg;
      }).join('/');
      return clip(u.origin + path + (keys.length ? '?' + keys.join('&') : ''));
    } catch (e) { return ''; }
  }
  function attrsOf(el) {
    const out = {}; let data = 0;
    for (const a of ['id', 'name', 'type', 'class', 'role', 'aria-label', 'title', 'alt', 'target']) {
      const v = el.getAttribute(a);
      if (v != null && v !== '') out[a] = (['aria-label', 'title', 'alt'].includes(a) && secretLike(v)) ? '[REDACTED]' : clip(v);
    }
    for (const a of ['href', 'action', 'formaction']) { const v = el.getAttribute(a); if (v) out[a] = safeUrl(v); }
    for (const a of el.attributes) {
      if (!a.name.startsWith('data-') || data >= 16) continue;
      data++;
      out[a.name] = (SENSITIVE.test(a.name) || secretLike(a.value)) ? '[REDACTED]' : clip(a.value);
    }
    return out;
  }
  function describe(el, given) {
    const [locator, kind] = given ? [given, 'given'] : locatorFor(el);
    if (!locator) return null;
    const role = roleOf(el);
    const [name, titleUsed] = nameOf(el, role);
    let description = clip(byIds(el, 'aria-describedby'));
    if (!description && !titleUsed) description = clip(el.getAttribute('title'));
    const tag = el.localName, type = (el.getAttribute('type') || (tag === 'input' ? 'text' : '')).toLowerCase();
    const autocomplete = clip((el.getAttribute('autocomplete') || '').toLowerCase());
    const placeholder = clip(el.getAttribute('placeholder'));
    const ml = parseInt(el.getAttribute('maxlength') || '', 10);
    const isField = tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable;
    const valueless = tag === 'input' && ['button', 'submit', 'reset', 'image', 'checkbox', 'radio'].includes(type);
    let valuePresent = false;
    if (isField && !valueless) {
      try {
        if (tag === 'select') valuePresent = el.selectedIndex >= 0 && !!el.value;
        else if (el.isContentEditable && tag !== 'input' && tag !== 'textarea') valuePresent = (el.textContent || '').trim().length > 0;
        else valuePresent = String(el.value || '').length > 0;
      } catch (e) { valuePresent = true; }
    }
    const sensitive = isField && !valueless && (
      type === 'password' || SENSITIVE_AUTOCOMPLETE.test(autocomplete) ||
      SENSITIVE.test([el.getAttribute('name'), el.id, name, placeholder, autocomplete, el.getAttribute('aria-label')].filter(Boolean).join(' '))
    );
    const isCtl = ['button', 'input', 'select', 'textarea'].includes(tag);
    return {
      locator, locator_kind: kind, role, name, description,
      text: contentText(el), media: mediaOf(el),
      effective_type: isCtl ? effectiveType(el) : '',
      submits: submitsOf(el), form: formOf(el), frame: FRAME_TAGS.has(tag),
      attributes: attrsOf(el), type, autocomplete, placeholder,
      inputmode: clip((el.getAttribute('inputmode') || '').toLowerCase()),
      maxlength: Number.isFinite(ml) && ml >= 0 ? ml : null,
      pattern: clip(el.getAttribute('pattern')),
      hidden: isHidden(el), tag, landmark: ROLE_LANDMARK.has(role),
      disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      checked: (type === 'checkbox' || type === 'radio') ? !!el.checked : null,
      sensitive: !!sensitive, value_present: !!valuePresent,
    };
  }
  if (mode === 'element') {
    // Review I5 MAJOR-2 — the node itself (CDP-bound, ``this`` of Runtime.callFunctionOn),
    // never a re-queried selector. ``_box`` is the centre the Harness hit-tests and clicks.
    if (!target || !target.isConnected) return { element: null };
    const d = describe(target, '(bound)');
    const r = target.getBoundingClientRect();
    d._box = { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height,
               in_viewport: r.width > 0 && r.height > 0 && r.left + r.width / 2 >= 0 && r.top + r.height / 2 >= 0 &&
                            r.left + r.width / 2 < innerWidth && r.top + r.height / 2 < innerHeight };
    d._url = String(location.href);
    return { element: d };
  }
  if (mode === 'describe') {
    let matches = 0, el = null;
    try { const all = document.querySelectorAll(target); matches = all.length; el = all[0] || null; } catch (e) { return { error: 'LOCATOR_INVALID' }; }
    if (!el) return { element: null, matches: 0 };
    // The element the Harness would act on for this locator (querySelector's first match),
    // reported under the locator exactly as given.
    return { element: describe(el, target), matches };
  }
  const seen = new Set(), visible = [], landmarks = [], hidden = [];
  let scanned = 0, signOut = false;
  const cands = document.querySelectorAll(INTERACTIVE + ',' + LANDMARK_SEL + ',[role]');
  for (const el of cands) {
    if (scanned++ >= SCAN) break;
    if (seen.has(el)) continue; seen.add(el);
    const role = roleOf(el);
    const isLandmark = ROLE_LANDMARK.has(role);
    const explicit = el.hasAttribute('role');
    if (explicit && !isLandmark && !ROLE_INTERACTIVE.has(role)) continue;
    if (role === 'region' && !el.hasAttribute('aria-label') && !el.hasAttribute('aria-labelledby')) continue;
    const d = describe(el);
    if (!d) continue;
    if (!d.hidden && (d.role === 'button' || d.role === 'link' || d.role === 'menuitem') && SIGN_OUT.test(d.name)) signOut = true;
    (d.hidden ? hidden : isLandmark ? landmarks : visible).push(d);
  }
  const out = []; let bytes = 2, truncated = cands.length > SCAN;
  for (const d of visible.concat(landmarks, hidden)) {
    const size = JSON.stringify(d).length + 1;
    if (out.length >= MAX || bytes + size > MAX_BYTES) { truncated = true; break; }
    out.push(d); bytes += size;
  }
  let storage = null;
  try { storage = (localStorage.length || 0) + (sessionStorage.length || 0); } catch (e) { storage = null; }
  let idb = null;
  try { if (indexedDB && indexedDB.databases) { idb = (await indexedDB.databases()).length; } } catch (e) { idb = null; }
  let docCookie = null;
  try { docCookie = document.cookie.length > 0; } catch (e) { docCookie = null; }
  return {
    elements: out, elements_total: visible.length + landmarks.length + hidden.length,
    elements_truncated: truncated, sign_out_control: signOut,
    storage_entries: storage, indexeddb_databases: idb, document_cookie_present: docCookie,
  };
})
""".replace("__EFFECTIVE_TYPES__", json.dumps(sorted(EFFECTIVE_TYPES)))


def elements_expression(mode: str, target: str | None = None) -> str:
    """The in-page expression for ``mode`` ("list" | "describe"); ``target`` is data only."""
    return ELEMENTS_JS.strip() + "(" + json.dumps(mode) + "," + json.dumps(target) + ")"


def _clip(value: Any, limit: int = MAX_ELEMENT_TEXT) -> str:
    text = " ".join(str(value).split()) if value is not None else ""
    return text[:limit]


def sanitize_element(raw: Any) -> dict[str, Any] | None:
    """Re-bound one in-page element record to the published shape.

    Defence in depth: the page script already omits values, but a page can redefine DOM
    built-ins, so nothing here trusts it. Unknown keys (``value`` above all) are dropped,
    strings are clipped, and attribute names are whitelisted.
    """
    if not isinstance(raw, dict):
        return None
    locator = raw.get("locator")
    if not isinstance(locator, str) or not locator or len(locator) > MAX_LOCATOR_LEN:
        return None
    out: dict[str, Any] = {}
    for key in ELEMENT_STRING_KEYS:
        value = raw.get(key)
        out[key] = value if key == "locator" else _clip(value if isinstance(value, str) else "")
    # Review I5 E1 — a title used as the description can carry a card number.
    out["description"] = mask_digit_runs(out["description"])
    for key in ELEMENT_BOOL_KEYS:
        out[key] = raw.get(key) is True
    # Unknown visibility is hidden: the gateway refuses to act on a hidden target.
    out["hidden"] = raw.get("hidden") is not False
    checked = raw.get("checked")
    out["checked"] = checked if isinstance(checked, bool) else None
    maxlength = raw.get("maxlength")
    out["maxlength"] = maxlength if isinstance(maxlength, int) and not isinstance(maxlength, bool) and maxlength >= 0 else None
    attributes: dict[str, str] = {}
    raw_attributes = raw.get("attributes")
    if isinstance(raw_attributes, dict):
        for name, value in raw_attributes.items():
            if len(attributes) >= MAX_ELEMENT_ATTRIBUTES:
                break
            if not isinstance(name, str) or not ATTRIBUTE_NAME_RE.fullmatch(name) or not isinstance(value, str):
                continue
            attributes[name] = sanitize_attribute(name, value)
    out["attributes"] = attributes
    media = raw.get("media")
    out["media"] = [mask_secret_runs(_clip(m)) for m in media if isinstance(m, str) and m.strip()][:MAX_ELEMENT_MEDIA] if isinstance(media, list) else []
    out["form"] = sanitize_form(raw.get("form"))
    # Integration G8 — G6b's E1 redaction on the G6a fields: visible text is masked like the
    # description, and effective_type is one of the enumerated el.type values or "".
    out["text"] = mask_secret_runs(out["text"])
    if out["effective_type"] not in EFFECTIVE_TYPES:
        out["effective_type"] = ""
    if out["type"] == "password" or out["autocomplete"].startswith(("cc-", "current-password", "new-password", "one-time-code")):
        out["sensitive"] = True
    return out


def sanitize_elements(raw: Any) -> tuple[list[dict[str, Any]], bool]:
    """Bound the list to MAX_ELEMENTS entries and MAX_ELEMENTS_BYTES of JSON."""
    out: list[dict[str, Any]] = []
    truncated = False
    size = 2
    for item in raw if isinstance(raw, list) else ():
        element = sanitize_element(item)
        if element is None:
            continue
        cost = len(json.dumps(element, separators=(",", ":"), ensure_ascii=False)) + 1
        if len(out) >= MAX_ELEMENTS or size + cost > MAX_ELEMENTS_BYTES:
            truncated = True
            break
        out.append(element)
        size += cost
    return out, truncated


def tri_state(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def session_facts(snapshot: dict[str, Any], identity: str, cookies: bool | None) -> dict[str, Any]:
    """``authenticated`` / ``cookies_present`` as booleans or None — never contents.

    ``authenticated`` is True on positive evidence (an account-identity marker, a visible
    sign-out control). It is False only when the profile demonstrably holds no session state
    for the page: no cookie for the site on any path or sibling host (CDP, HttpOnly
    included), no local/session storage entry, no IndexedDB database and no other origin
    storage in use, all read over CDP (review I5 E2). Anything else is None (unknown), which
    B2 treats as signed in.
    """
    doc_cookie = tri_state(snapshot.get("document_cookie_present"))
    if cookies is None and doc_cookie is True:
        cookies = True
    elif cookies is False and doc_cookie is True:
        cookies = True
    if identity:
        authenticated, basis = True, "IDENTITY_MARKER"
    elif snapshot.get("sign_out_control") is True:
        authenticated, basis = True, "SIGN_OUT_CONTROL"
    elif (
        cookies is False
        and snapshot.get("storage_entries") == 0
        and snapshot.get("indexeddb_databases") == 0
        and snapshot.get("storage_usage_bytes", 0) == 0
    ):
        authenticated, basis = False, "NO_SESSION_STATE"
    else:
        authenticated, basis = None, "UNKNOWN"
    return {"authenticated": authenticated, "cookies_present": cookies, "authentication_basis": basis}


# --------------------------------------------------------------------- binding + task scope
#
# Review I5 MAJOR-2 / owner decision 2026-09-30. Shared, verbatim, by this module and by the
# fixed scripts below (which run inside browser-harness and cannot import this module):
#   _van_digest(el)        digest of the fields the gateway classifies; /describe returns it in
#                          ``binding`` and /click, /press, /fill refuse when the bound node no
#                          longer produces it (TARGET_CHANGED)
#   _van_scope_violation   the task-scope rule of backend/van_gateway/browser/task_scope.py
#                          (origin exact, path prefix on a segment boundary); the gateway sends
#                          the task's scope with every action and the Harness re-checks the
#                          page at the moment it acts
VAN_HELPERS_PY = r"""
import hashlib as _vh_hashlib, json as _vh_json
from urllib.parse import urlsplit as _vh_urlsplit

def _van_digest(el):
    el = el or {}
    keep = {k: el.get(k) for k in ("role", "name", "text", "media", "description", "type",
                                     "effective_type", "tag", "form", "submits", "frame")}
    attrs = dict(el.get("attributes") or {})
    attrs.pop("class", None)
    keep["attributes"] = attrs
    return _vh_hashlib.sha256(_vh_json.dumps(keep, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def _van_origin(parts):
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    default = {"http": 80, "https": 443}.get(scheme)
    return scheme + "://" + host + ((":" + str(port)) if port and port != default else "")

def _van_scope_violation(scope, url, what="PAGE"):
    entries = (scope or {}).get("entries") if isinstance(scope, dict) else None
    if not entries:
        return "TASK_SCOPE_MISSING"
    try:
        parts = _vh_urlsplit(str(url or ""))
        parts.port
    except ValueError:
        return "TASK_SCOPE_" + what + "_URL_INVALID"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "TASK_SCOPE_" + what + "_URL_NOT_HTTP"
    origin, path = _van_origin(parts), parts.path or "/"
    same_origin = False
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("origin") != origin:
            continue
        same_origin = True
        prefix = entry.get("path_prefix")
        if not prefix or (path.startswith(prefix) if prefix.endswith("/") else (path == prefix or path.startswith(prefix + "/"))):
            return None
    return "TASK_SCOPE_" + what + ("_PATH_OUTSIDE" if same_origin else "_ORIGIN_OUTSIDE")
"""
exec(compile(VAN_HELPERS_PY, "<van-helpers>", "exec"))  # noqa: S102 - the fixed helper source above

#: Interactive nodes a click must not pass through on its way from the hit node up to the
#: bound element (a wrapper whose centre is a pay button is not "the wrapper").
INTERACTIVE_SELECTOR = (
    'a[href],area[href],button,input,select,textarea,summary,label,[role=button],[role=link],'
    '[role=checkbox],[role=radio],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],'
    '[role=tab],[role=option],[role=switch],[role=treeitem],[role=gridcell],[onclick],'
    '[tabindex]:not([tabindex="-1"]),[contenteditable=""],[contenteditable="true" i],iframe,frame,object,embed'
)

#: this = the bound element, hit = the node at the click point (DOM.getNodeForLocation, which
#: pierces open and closed shadow roots). Walks the composed tree from the hit node up.
HIT_FN = r"""function (hit) {
  const INTER = __INTER__;
  let n = hit; if (n && n.nodeType === 3) n = n.parentNode;
  if (n === this) return 'SELF';
  let crossed = false;
  while (n) {
    if (n === this) return crossed ? 'INTERACTIVE_DESCENDANT' : 'DESCENDANT';
    if (n.nodeType === 1 && n.matches && n.matches(INTER)) crossed = true;
    n = n.parentNode || n.host || null;
  }
  return 'OTHER';
}""".replace("__INTER__", json.dumps(INTERACTIVE_SELECTOR))

#: this = the bound element. Installs window-capture listeners for the duration of the
#: actuation: any pointer/mouse/click/key/submit event whose composed path does not reach the
#: bound element (without passing another interactive node) is cancelled before the page sees
#: it — the element swapped, moved or was overlaid between the hit test and the click. A
#: submit counts only when the bound element is its submitter (or, for a field, its form).
GUARD_FN = r"""function () {
  const el = this, INTER = __INTER__, blocked = [], seen = [];
  const isField = (n) => { const t = (n.getAttribute('type') || '').toLowerCase(), g = n.localName;
    return (g === 'input' && !['button', 'submit', 'reset', 'image'].includes(t)) || g === 'textarea' || g === 'select' || n.isContentEditable; };
  const within = (path) => {
    const i = path.indexOf(el); if (i < 0) return false;
    for (let k = 0; k < i; k++) { const n = path[k]; if (n.nodeType === 1 && n.matches && n.matches(INTER)) return false; }
    return true;
  };
  const on = (e) => {
    if (e.type === 'submit') {
      if (e.submitter === el || (el.form && e.target === el.form && isField(el))) { seen.push('submit'); return; }
    } else if (within(e.composedPath())) { seen.push(e.type); return; }
    const t = e.composedPath()[0];
    blocked.push(e.type + ':' + ((t && (t.id || t.localName)) || '?'));
    e.preventDefault(); e.stopImmediatePropagation();
  };
  // keyup is not guarded: after Tab it fires, legitimately, on the element focus moved to.
  const types = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'auxclick', 'dblclick',
                 'keydown', 'keypress', 'submit'];
  types.forEach((t) => window.addEventListener(t, on, true));
  return { finish() { types.forEach((t) => window.removeEventListener(t, on, true)); return { blocked, seen }; } };
}""".replace("__INTER__", json.dumps(INTERACTIVE_SELECTOR))

#: The focused element, through open shadow roots (a closed one stops at its host, which is
#: then an unresolved target).
FOCUS_JS = r"""(() => { let a = document.activeElement; while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement; return a || document.body; })()"""

#: Script prologue: bind a CDP node, re-describe it, and refuse with a typed code.
BOUND_PROLOGUE_PY = r"""
import json, os
__VAN_HELPERS__
_ELEMENT_FN = "function(){ return (" + __ELEMENTS_JS__ + ")('element', this); }"
_PREP_FN = "function(){ if (!this.isConnected) return {element: null}; try { this.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'}); } catch (e) {} return (" + __ELEMENTS_JS__ + ")('element', this); }"

class _VanRefused(Exception):
    pass

def _van_call(object_id, fn, args=None, by_value=True):
    r = cdp("Runtime.callFunctionOn", objectId=object_id, functionDeclaration=fn,
            arguments=args or [], awaitPromise=True, returnByValue=by_value)
    if r.get("exceptionDetails"):
        raise _VanRefused("TARGET_SCRIPT_FAILED")
    return r.get("result") or {}

def _van_bind(binding, scope):
    if not isinstance(binding, dict) or not isinstance(binding.get("backend_node_id"), int) or not binding.get("digest"):
        raise _VanRefused("TARGET_BINDING_REQUIRED")
    if not isinstance(scope, dict) or not scope.get("entries"):
        raise _VanRefused("TASK_SCOPE_REQUIRED")
    info = page_info()
    if "dialog" in info:
        raise _VanRefused("PAGE_DIALOG_OPEN")
    try:
        obj = cdp("DOM.resolveNode", backendNodeId=int(binding["backend_node_id"]))["object"]["objectId"]
    except Exception:
        raise _VanRefused("TARGET_BINDING_LOST")
    el = (_van_call(obj, _PREP_FN).get("value") or {}).get("element")
    if not isinstance(el, dict):
        raise _VanRefused("TARGET_BINDING_LOST")
    violation = _van_scope_violation(scope, el.get("_url"))
    if violation:
        raise _VanRefused(violation)
    if _van_digest(el) != binding["digest"]:
        raise _VanRefused("TARGET_CHANGED")
    if el.get("hidden"):
        raise _VanRefused("TARGET_HIDDEN")
    return obj, el

def _van_hit(obj, el):
    box = el.get("_box") or {}
    if not box.get("in_viewport") or box.get("w", 0) <= 0 or box.get("h", 0) <= 0:
        raise _VanRefused("TARGET_NOT_VISIBLE")
    x, y = float(box["x"]), float(box["y"])
    try:
        at = cdp("DOM.getNodeForLocation", x=int(x), y=int(y), includeUserAgentShadowDOM=False)
        hit = cdp("DOM.resolveNode", backendNodeId=int(at["backendNodeId"]))["object"]["objectId"]
    except Exception:
        raise _VanRefused("TARGET_HIT_TEST_FAILED")
    verdict = _van_call(obj, __HIT_FN__, [{"objectId": hit}]).get("value")
    if verdict not in ("SELF", "DESCENDANT"):
        raise _VanRefused("TARGET_NOT_HIT:" + str(verdict))
    return x, y

def _van_guard(obj):
    return _van_call(obj, __GUARD_FN__, by_value=False).get("objectId")

def _van_finish(guard):
    try:
        out = _van_call(guard, "function(){ return this.finish(); }").get("value") or {}
    except Exception:
        # The page navigated during the actuation (the guard's context is gone). A blocked
        # event is cancelled, so a navigation means the bound element's activation ran.
        return {"blocked": [], "seen": [], "navigated": True}
    if out.get("blocked"):
        raise _VanRefused("TARGET_MOVED_DURING_ACTUATION:" + ",".join(out["blocked"][:4]))
    return out

def _van_finish_after_net(guard, net):
    # The network verdict outranks the event guard's: a blocked write is what the owner
    # must see, and the event guard's listeners are removed either way.
    try:
        done = _van_finish(guard)
    except _VanRefused:
        _van_net_verdict(net)
        raise
    _van_net_verdict(net)
    return done

def _van_emit(payload):
    print("__VAN_JSON__" + json.dumps(payload))
"""

# --------------------------------------------------------------------- network-effect guard
#
# Owner decision 2026-09-30 (answer to review I6 M4, "Network-effect guard"): a page can move
# money inside a JavaScript handler behind any label ("Next", "Go"), and no check before the
# click can see it. So while the Harness acts, it intercepts the page's network requests and
# fails every *write* unless the task is admitted as mutating; a blocked write ends the step
# in lane 4 (owner takeover) with ``NETWORK_WRITE_BLOCKED:<kind>``.
#
# Mechanism (Chromium 1194, measured by unit G9c against a local HTTPS server):
#   * ``Fetch.enable`` (all URLs, request stage) on the page session, and on a browser-target
#     session (``Target.attachToBrowserTarget``): the browser session is the only one that
#     sees browser-initiated navigations, i.e. a popup's / ``target=_blank`` document.
#   * ``Target.autoAttachRelated(page, waitForDebuggerOnStart)``: every out-of-process
#     iframe and service worker related to the page is attached — new ones *paused* until
#     their own ``Fetch.enable`` is in place — so their requests are intercepted too.
#     Dedicated-worker requests arrive on the page session. Without this, a cross-origin
#     iframe's POST and a service worker's own fetch escaped page-session interception.
#   * Chromium launch flags (``ChromeSession.ensure``): ``KeepAliveInBrowserMigration`` off
#     (with it on, sendBeacon, ``fetch(..., {keepalive})`` and ``<a ping>`` from a page a
#     service worker controls bypassed every Fetch session) and ``SharedWorker`` off (a
#     shared worker is not a related target and its requests escaped). Chromium honours
#     only the last ``--disable-features``: this must stay the launch's only one.
#   * A request answered by nobody stays paused: ``Fetch.disable`` / detaching the session
#     does not release it (measured: it never reaches the server). A lost event therefore
#     fails closed.
# The guard is enabled before the action's input is dispatched and refuses the action
# (``NETWORK_GUARD_UNAVAILABLE``) when any part cannot be enabled. The input is dispatched
# on a helper thread while this thread answers paused requests (a handler's synchronous XHR
# would otherwise deadlock the dispatch), then the guard stays on for a settle window:
# until the network is idle (no in-flight request and no network event for
# NETWORK_GUARD_IDLE_MS) or NETWORK_GUARD_SETTLE_MAX_MS after the input returned, whichever
# comes first.
#
# Write classification (anything else is a read and continues):
#   method other than GET/HEAD/OPTIONS                  -> POST | PUT | PATCH | DELETE | OTHER_METHOD
#   resourceType Ping (sendBeacon, <a ping>)             -> BEACON
#   a request carrying a body                            -> BODY
#   Accept: text/event-stream (EventSource open)         -> EVENTSOURCE
#   a document request after a form submission           -> FORM_SUBMIT (GET forms too)
#   a main-frame navigation outside the task scope       -> NAVIGATION_OUT_OF_SCOPE
#   a popup / new-window document                        -> POPUP
#   a write from an out-of-process (cross-site) iframe   -> CROSS_ORIGIN_FRAME
#   a WebSocket open                                     -> WEBSOCKET (detected, see below)
# A task admitted as mutating may write to URLs inside its task scope only; any other write
# is blocked as OUT_OF_SCOPE_WRITE (cross-origin frames and popups stay blocked).
# WebSocket handshakes are not interceptable by CDP Fetch in this Chromium (measured), so a
# WebSocket opened during the action is detected (``Network.webSocketCreated``) and ends the
# step in lane 4, but its handshake is not prevented.
# The refusal carries only the closed-vocabulary kind: never a URL, body or header.
NETWORK_GUARD_IDLE_MS = 500
NETWORK_GUARD_SETTLE_MAX_MS = 2000
#: browser-harness 0.1.13's daemon keeps the newest 500 events; a drain this large may have
#: lost some, which is refused rather than trusted.
NETWORK_GUARD_OVERFLOW_EVENTS = 480
NETWORK_WRITE_KINDS = frozenset({
    "POST", "PUT", "PATCH", "DELETE", "OTHER_METHOD", "BEACON", "BODY", "EVENTSOURCE",
    "FORM_SUBMIT", "NAVIGATION_OUT_OF_SCOPE", "POPUP", "CROSS_ORIGIN_FRAME", "WEBSOCKET",
    "OUT_OF_SCOPE_WRITE",
})
NETWORK_REFUSALS = frozenset({"NETWORK_GUARD_UNAVAILABLE", "NETWORK_GUARD_OVERFLOW"})
#: Chromium flags the guard depends on (see above). Added to ChromeSession's launch.
NETWORK_GUARD_CHROMIUM_FLAGS = (
    "--disable-features=KeepAliveInBrowserMigration",
    "--disable-blink-features=SharedWorker",
)

NETWORK_GUARD_PY = r"""
import threading as _ng_threading, time as _ng_time

_NG_READ = ("GET", "HEAD", "OPTIONS")
_NG_METHODS = ("POST", "PUT", "PATCH", "DELETE")

class _VanNetGuard:
    def __init__(self, policy):
        policy = policy if isinstance(policy, dict) else {}
        self.mutating = policy.get("mutating") is True
        self.scope = policy.get("scope") if isinstance(policy.get("scope"), dict) else {}
        self.children = {}
        self.browser_sid = None
        self.main_frame = None
        self.blocked = []
        self.broken = None
        self.form_frames = set()
        self.inflight = set()
        self.last = _ng_time.monotonic()
        self.enabled_page = False

    def _in_scope(self, url):
        return _van_scope_violation(self.scope, url, "WRITE") is None

    def start(self):
        try:
            drain_events()
            self.main_frame = cdp("Page.getFrameTree")["frameTree"]["frame"]["id"]
            cdp("Fetch.enable", patterns=[{"urlPattern": "*"}])
            self.enabled_page = True
            self.browser_sid = cdp("Target.attachToBrowserTarget")["sessionId"]
            cdp("Fetch.enable", session_id=self.browser_sid, patterns=[{"urlPattern": "*"}])
            cdp("Target.autoAttachRelated", targetId=self.main_frame, waitForDebuggerOnStart=True)
        except _VanRefused:
            raise
        except Exception:
            self.stop()
            raise _VanRefused("NETWORK_GUARD_UNAVAILABLE")
        # Existing related targets (out-of-process iframes, service workers) attach now; the
        # input is not dispatched until each has its own interception.
        deadline = _ng_time.monotonic() + 1.0
        quiet_since = _ng_time.monotonic()
        seen = -1
        while _ng_time.monotonic() < deadline:
            self.pump()
            if len(self.children) != seen:
                seen, quiet_since = len(self.children), _ng_time.monotonic()
            elif _ng_time.monotonic() - quiet_since >= 0.15:
                break
            _ng_time.sleep(0.02)
        try:
            frames = [t for t in cdp("Target.getTargets")["targetInfos"] if t.get("type") == "iframe"]
        except Exception:
            frames = None
        attached = set(self.children.values())
        if frames is None or any((f.get("targetId"), "iframe") not in attached for f in frames):
            self.broken = self.broken or "NETWORK_GUARD_UNAVAILABLE"
        if self.broken:
            self.stop()
            raise _VanRefused(self.broken)

    def _answer(self, sid, rid, kind):
        try:
            if kind:
                cdp("Fetch.failRequest", session_id=sid, requestId=rid, errorReason="BlockedByClient")
            else:
                cdp("Fetch.continueRequest", session_id=sid, requestId=rid)
        except Exception:
            pass

    def classify(self, ev):
        p = ev.get("params") or {}
        req = p.get("request") or {}
        sid = ev.get("session_id")
        method = str(req.get("method") or "").upper()
        url = str(req.get("url") or "")
        rtype = p.get("resourceType")
        headers = req.get("headers") if isinstance(req.get("headers"), dict) else {}
        accept = " ".join(str(v) for k, v in headers.items() if str(k).lower() == "accept")
        origin_kind = self.children.get(sid, (None, "page"))[1]
        if sid is not None and sid == self.browser_sid:
            if rtype != "Document":
                return None  # the browser's own traffic; page-originated requests pause on page sessions
            if p.get("frameId") != self.main_frame:
                return "POPUP"
        kind = None
        if method not in _NG_READ:
            kind = method if method in _NG_METHODS else "OTHER_METHOD"
        if rtype == "Ping":
            kind = "BEACON"
        elif kind is None and (req.get("hasPostData") or req.get("postData")):
            kind = "BODY"
        if "text/event-stream" in accept:
            kind = "EVENTSOURCE"
        if rtype == "Document" and p.get("frameId") in self.form_frames:
            kind = "FORM_SUBMIT"
        if kind is None:
            if rtype == "Document" and p.get("frameId") == self.main_frame and _van_scope_violation(self.scope, url, "NAVIGATE"):
                return "NAVIGATION_OUT_OF_SCOPE"
            return None
        if origin_kind == "iframe":
            return "CROSS_ORIGIN_FRAME"
        if self.mutating:
            return None if self._in_scope(url) else "OUT_OF_SCOPE_WRITE"
        return kind

    def _attached(self, ev):
        p = ev.get("params") or {}
        sid = p.get("sessionId")
        info = p.get("targetInfo") or {}
        ttype = str(info.get("type") or "")
        if ttype == "browser" or sid == self.browser_sid:
            return  # this guard's own browser-target session
        self.children[sid] = (info.get("targetId"), ttype)
        ok = True
        if ttype in ("iframe", "page", "service_worker"):
            try:
                cdp("Fetch.enable", session_id=sid, patterns=[{"urlPattern": "*"}])
            except Exception:
                ok = False
            try:
                cdp("Network.enable", session_id=sid)
            except Exception:
                pass
            if ttype == "iframe":
                try:
                    cdp("Page.enable", session_id=sid)
                except Exception:
                    pass
        elif ttype != "worker":
            ok = False  # a target kind whose requests this guard cannot see: stays paused
        if not ok:
            self.broken = self.broken or "NETWORK_GUARD_UNAVAILABLE"
            return
        try:
            cdp("Runtime.runIfWaitingForDebugger", session_id=sid)
        except Exception:
            pass

    def handle(self, ev):
        m = str(ev.get("method") or "")
        p = ev.get("params") or {}
        sid = ev.get("session_id")
        now = _ng_time.monotonic()
        if m == "Target.attachedToTarget":
            self._attached(ev)
        elif m == "Fetch.requestPaused":
            self.last = now
            kind = self.classify(ev)
            if kind:
                self.blocked.append(kind)
            self._answer(sid, p.get("requestId"), kind)
        elif m == "Page.frameRequestedNavigation":
            self.last = now
            if str(p.get("reason") or "").startswith("formSubmission"):
                self.form_frames.add(p.get("frameId"))
        elif m == "Network.webSocketCreated":
            self.last = now
            url = str(p.get("url") or "")
            http_url = ("https" + url[3:]) if url.startswith("wss") else (("http" + url[2:]) if url.startswith("ws") else url)
            if not (self.mutating and self._in_scope(http_url)) or self.children.get(sid, (None, ""))[1] == "iframe":
                self.blocked.append("WEBSOCKET")
        elif m == "Network.requestWillBeSent":
            self.last = now
            self.inflight.add((sid, p.get("requestId")))
        elif m in ("Network.loadingFinished", "Network.loadingFailed"):
            self.last = now
            self.inflight.discard((sid, p.get("requestId")))
        elif m.startswith(("Network.", "Fetch.")):
            self.last = now

    def pump(self):
        events = drain_events()
        if len(events) >= __OVERFLOW__:
            self.broken = self.broken or "NETWORK_GUARD_OVERFLOW"
        for ev in events:
            self.handle(ev)

    def run(self, action):
        box = {}
        def _go():
            try:
                action()
            except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
                box["error"] = exc
        worker = _ng_threading.Thread(target=_go, daemon=True)
        worker.start()
        limit = _ng_time.monotonic() + 30.0
        while worker.is_alive():
            self.pump()
            if _ng_time.monotonic() > limit:
                self.broken = self.broken or "NETWORK_GUARD_UNAVAILABLE"
                break
            _ng_time.sleep(0.01)
        done = _ng_time.monotonic()
        self.last = max(self.last, done)
        while _ng_time.monotonic() - done < __SETTLE_MAX_S__:
            self.pump()
            now = _ng_time.monotonic()
            if not self.inflight and now - self.last >= __IDLE_S__:
                break
            _ng_time.sleep(0.02)
        return box.get("error")

    def stop(self):
        try:
            self.pump()
        except Exception:
            pass
        try:
            # Cancels autoAttachRelated (and detaches its sessions). Browser-level auto-attach
            # accepts only flatten=True; without it the call fails and every frame created
            # later would wait for a debugger forever.
            cdp("Target.setAutoAttach", autoAttach=False, waitForDebuggerOnStart=False, flatten=True)
        except Exception:
            pass
        for sid in list(self.children):
            try:
                cdp("Target.detachFromTarget", sessionId=sid)
            except Exception:
                pass
        if self.browser_sid:
            try:
                cdp("Target.detachFromTarget", sessionId=self.browser_sid)
            except Exception:
                pass
        if self.enabled_page:
            try:
                cdp("Fetch.disable")
            except Exception:
                pass

def _van_net_run(action):
    '''Run ``action`` (the input dispatch) under the network-effect guard. Returns the guard;
    ``_van_net_verdict`` turns what it saw into the typed refusal.'''
    try:
        policy = json.loads(os.environ.get("VAN_BH_NETGUARD") or "null")
    except ValueError:
        policy = None
    if not isinstance(policy, dict) or "drain_events" not in globals():
        raise _VanRefused("NETWORK_GUARD_UNAVAILABLE")
    guard = _VanNetGuard(policy)
    guard.start()
    try:
        guard.error = guard.run(action)
    finally:
        guard.stop()
    return guard

def _van_net_verdict(guard):
    if guard.blocked:
        raise _VanRefused("NETWORK_WRITE_BLOCKED:" + guard.blocked[0])
    if guard.broken:
        raise _VanRefused(guard.broken)
    if guard.error is not None:
        raise guard.error
""".replace("__OVERFLOW__", str(NETWORK_GUARD_OVERFLOW_EVENTS)).replace(
    "__SETTLE_MAX_S__", repr(NETWORK_GUARD_SETTLE_MAX_MS / 1000)).replace(
    "__IDLE_S__", repr(NETWORK_GUARD_IDLE_MS / 1000))

EFFECT_MAC_CONTEXT = "van-harness-effect/1"


def scope_digest(scope: Any) -> str:
    """sha256 of the task scope exactly as the gateway sent it (canonical JSON)."""
    return hashlib.sha256(
        json.dumps(scope if isinstance(scope, dict) else None, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def effect_mac(key: bytes, alias: str, generation: int, holder_id: str, task_id: str,
               mutating: bool, digest: str) -> str:
    """HMAC-SHA256 binding the task's admitted effects (mutating flag + scope digest) to the
    lease fence. Same bytes as ``harness_effect_mac`` in backend/van_gateway/browser/adapters.py."""
    message = (f"{EFFECT_MAC_CONTEXT}\n{alias}\n{int(generation)}\n{holder_id}\n{task_id}\n"
               f"{'1' if mutating else '0'}\n{digest}").encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def network_guard_env(body: dict[str, Any], alias: str) -> dict[str, str]:
    """The guard policy for one action: ``mutating`` and the task scope.

    ``mutating`` is honoured only when the fence key verifies ``effect_mac`` over the lease
    fence, the task id, the flag and the scope digest; without a key it is always False (the
    default, fail closed). With a key every guarded action must carry a valid ``effect_mac``
    (it binds the scope too), else it is refused before anything runs.
    """
    scope = body.get("task_scope") if isinstance(body.get("task_scope"), dict) else None
    claimed = body.get("mutating") is True
    key = getattr(FENCE, "_key", None)
    mutating = False
    if key is not None or getattr(FENCE, "_require_mac", False):
        generation, holder, mac = body.get("lease_generation"), body.get("lease_holder_id"), body.get("effect_mac")
        if key is None or not isinstance(mac, str) or isinstance(generation, bool) or not isinstance(generation, int) \
                or not isinstance(holder, str) or not hmac.compare_digest(
                    mac, effect_mac(key, alias, generation, holder, str(body.get("task_id") or ""), claimed, scope_digest(scope))):
            raise WorkerError("NETWORK_EFFECT_MAC_INVALID", 403)
        mutating = claimed
    return {"VAN_BH_NETGUARD": json.dumps({"mutating": mutating, "scope": scope})}


def _bound_script(body: str) -> str:
    """A fixed script: the bound prologue, then ``body`` run with typed refusals."""
    prologue = (
        BOUND_PROLOGUE_PY.replace("__VAN_HELPERS__", VAN_HELPERS_PY + NETWORK_GUARD_PY)
        .replace("__ELEMENTS_JS__", json.dumps(ELEMENTS_JS.strip()))
        .replace("__HIT_FN__", json.dumps(HIT_FN))
        .replace("__GUARD_FN__", json.dumps(GUARD_FN))
    )
    indented = "\n".join("    " + line for line in body.strip().splitlines())
    return prologue + "try:\n" + indented + "\nexcept _VanRefused as _exc:\n    _van_emit({\"refused\": str(_exc)})\n"


PAGE_INFO_SCRIPT = r"""
import json
info = page_info()
if "dialog" not in info:
    visible = js("document.body ? document.body.innerText.slice(0, 32768) : ''") or ""
    identity = js("(()=>{const e=document.querySelector('[data-van-account-identity],meta[name=\\\"van-account-identity\\\"]');return e ? (e.content || e.getAttribute('data-van-account-identity') || e.textContent || '') : '';})()") or ""
    info["extraction"] = {"visible_text": str(visible)[:32768]}
    if identity:
        info["account_identity"] = str(identity)[:256]
    try:
        snapshot = js(__ELEMENTS_LIST__) or {}
    except Exception:
        snapshot = {"elements_error": True}
    snapshot = snapshot if isinstance(snapshot, dict) else {"elements_error": True}
    # Review I5 E2 — session state is read over CDP, never from page JS (a page can redefine
    # Storage.prototype.length or indexedDB.databases). Counts only; no content is kept.
    from urllib.parse import urlsplit
    parts = urlsplit(str(info.get("url") or ""))
    host = (parts.hostname or "").lower().rstrip(".")
    origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme in ("http", "https") and host else ""
    labels = host.split(".")
    # The registrable domain, over-approximated as the last two labels: a sibling SSO host
    # (auth.example.com for docs.example.com) counts; over-inclusion only yields "unknown".
    site = ".".join(labels[-2:]) if len(labels) >= 2 and not host.replace(".", "").isdigit() else host
    cookies = None
    try:
        got = cdp("Network.getAllCookies")
        listed = got.get("cookies") if isinstance(got, dict) else None
        if isinstance(listed, list) and site:
            # Any cookie for the site, on any path or sibling host.
            cookies = any(
                isinstance(c, dict) and (lambda d: d == site or d.endswith("." + site))(str(c.get("domain") or "").lower().lstrip(".").rstrip("."))
                for c in listed
            )
    except Exception:
        cookies = None
    for key in ("storage_entries", "indexeddb_databases", "storage_usage_bytes"):
        snapshot[key] = None
    if origin:
        try:
            count = 0
            for local in (True, False):
                got = cdp("DOMStorage.getDOMStorageItems", storageId={"securityOrigin": origin, "isLocalStorage": local})
                entries = got.get("entries") if isinstance(got, dict) else None
                if not isinstance(entries, list):
                    raise ValueError("entries")
                count += len(entries)
            snapshot["storage_entries"] = count
        except Exception:
            pass
        try:
            got = cdp("IndexedDB.requestDatabaseNames", securityOrigin=origin)
            names = got.get("databaseNames") if isinstance(got, dict) else None
            if isinstance(names, list):
                snapshot["indexeddb_databases"] = len(names)
        except Exception:
            pass
        try:
            got = cdp("Storage.getUsageAndQuota", origin=origin)
            usage = got.get("usage") if isinstance(got, dict) else None
            if isinstance(usage, (int, float)) and not isinstance(usage, bool):
                snapshot["storage_usage_bytes"] = int(usage)
        except Exception:
            pass
    info["__van_snapshot__"] = snapshot
    info["__van_cookies__"] = cookies
info["harness_version"] = "0.1.13"
print("__VAN_JSON__" + json.dumps(info))
""".replace("__ELEMENTS_LIST__", json.dumps(elements_expression("list")))

DESCRIBE_SCRIPT = r"""
import json, os
__VAN_HELPERS__
info = page_info()
out = {"url": info.get("url"), "title": info.get("title")}
if "dialog" in info:
    out["dialog"] = True
else:
    # Review I5 MAJOR-2: the node is found once, bound by its CDP backendNodeId, and described
    # through that binding; /click, /press and /fill act on the same node, never a re-query.
    focus = os.environ.get("VAN_BH_FOCUS") == "1"
    loc = os.environ.get("VAN_BH_LOCATOR", "")
    matches = 1
    if focus:
        expr = __FOCUS_JS__
    else:
        counted = cdp("Runtime.evaluate", expression="document.querySelectorAll(" + json.dumps(loc) + ").length", returnByValue=True)
        if counted.get("exceptionDetails"):
            out["describe"] = {"error": "LOCATOR_INVALID"}
        matches = (counted.get("result") or {}).get("value") or 0
        expr = "document.querySelector(" + json.dumps(loc) + ")"
    if "describe" not in out:
        found = cdp("Runtime.evaluate", expression=expr, returnByValue=False)
        obj = (found.get("result") or {}).get("objectId")
        if found.get("exceptionDetails"):
            out["describe"] = {"error": "LOCATOR_INVALID"}
        elif not obj:
            out["describe"] = {"element": None, "matches": 0}
        else:
            node = cdp("DOM.describeNode", objectId=obj)["node"]
            r = cdp("Runtime.callFunctionOn", objectId=obj, awaitPromise=True, returnByValue=True,
                    functionDeclaration="function(){ return (" + __ELEMENTS_JS__ + ")('element', this); }")
            el = ((r.get("result") or {}).get("value") or {}).get("element") if not r.get("exceptionDetails") else None
            if not isinstance(el, dict):
                out["describe"] = {"element": None, "matches": 0}
            else:
                # Author shadow roots only: <input>, <video> ... carry a user-agent one.
                el["shadow_host"] = any(r.get("shadowRootType") in ("open", "closed") for r in node.get("shadowRoots") or [])
                box = el.get("_box") or {}
                occluded = None
                if box.get("in_viewport"):
                    try:
                        at = cdp("DOM.getNodeForLocation", x=int(box["x"]), y=int(box["y"]), includeUserAgentShadowDOM=False)
                        hit = cdp("DOM.resolveNode", backendNodeId=int(at["backendNodeId"]))["object"]["objectId"]
                        v = cdp("Runtime.callFunctionOn", objectId=obj, functionDeclaration=__HIT_FN__,
                                arguments=[{"objectId": hit}], returnByValue=True)
                        occluded = ((v.get("result") or {}).get("value")) not in ("SELF", "DESCENDANT")
                    except Exception:
                        occluded = True
                el["occluded"] = occluded
                out["describe"] = {
                    "element": el, "matches": matches, "page_url": el.get("_url"),
                    "binding": {"backend_node_id": int(node["backendNodeId"]), "digest": _van_digest(el)},
                }
print("__VAN_JSON__" + json.dumps(out))
""".replace("__VAN_HELPERS__", VAN_HELPERS_PY).replace("__ELEMENTS_JS__", json.dumps(ELEMENTS_JS.strip())).replace(
    "__FOCUS_JS__", json.dumps(FOCUS_JS)).replace("__HIT_FN__", json.dumps(HIT_FN))


def shape_page_info(result: dict[str, Any]) -> dict[str, Any]:
    """Turn the raw harness page_info into the published shape (elements + session facts)."""
    snapshot = result.pop("__van_snapshot__", None)
    cookies = tri_state(result.pop("__van_cookies__", None))
    if not isinstance(snapshot, dict):
        # A native dialog is open (or the script could not run): nothing is observable.
        result["elements"] = []
        result["elements_truncated"] = False
        result.update({"authenticated": None, "cookies_present": None, "authentication_basis": "UNKNOWN"})
        return result
    elements, truncated = sanitize_elements(snapshot.get("elements"))
    result["elements"] = elements
    result["elements_truncated"] = bool(truncated or snapshot.get("elements_truncated") is True)
    if snapshot.get("elements_error"):
        result["elements_error"] = True
    result.update(session_facts(snapshot, str(result.get("account_identity") or ""), cookies))
    return result


def page_info_result(alias: str, domain: str) -> dict[str, Any]:
    result = run_harness(alias, PAGE_INFO_SCRIPT)
    if not isinstance(result, dict):
        raise WorkerError("BROWSER_PAGE_INFO_INVALID", 502)
    current = str(result.get("url") or "")
    if current and current != "about:blank":
        assert_url_in_domain(current, domain)
    return shape_page_info(result)


def describe(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    """Resolve one locator — or, with ``focus: true``, the focused element — to the element
    shape page_info reports, bound to that node (review I4, I5 MAJOR-2/-3).

    The element is the one the Harness acts on for this locator (querySelector's first
    match), reported under the locator exactly as given, with ``binding`` (its CDP
    backendNodeId and the digest of what was classified) and ``page_url``. /click, /press
    and /fill take the binding back and act on that node only.
    """
    focus = body.get("focus") is True
    locator = "(focused)" if focus else str(body.get("locator") or "")
    if not locator or len(locator) > MAX_LOCATOR_LEN:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    env = {"VAN_BH_FOCUS": "1"} if focus else {"VAN_BH_LOCATOR": locator}
    result = run_harness(alias, DESCRIBE_SCRIPT, env)
    if not isinstance(result, dict):
        raise WorkerError("BROWSER_DESCRIBE_INVALID", 502)
    current = str(result.get("url") or "")
    if current and current != "about:blank":
        assert_url_in_domain(current, domain)
    described = result.get("describe") if isinstance(result.get("describe"), dict) else {}
    if described.get("error") == "LOCATOR_INVALID":
        raise WorkerError("LOCATOR_INVALID", 422)
    raw = described.get("element")
    element = sanitize_element({**raw, "locator": locator} if isinstance(raw, dict) else raw)
    binding = described.get("binding") if isinstance(described.get("binding"), dict) else None
    if element is not None:
        element["locator"] = locator
        # Unknown (off-screen) is not "occluded"; the click-time hit test is authoritative.
        element["occluded"] = raw.get("occluded") is True
        element["shadow_host"] = raw.get("shadow_host") is not False
    node_id = binding.get("backend_node_id") if binding else None
    digest = binding.get("digest") if binding else None
    matches = described.get("matches")
    return {
        "url": result.get("url"), "title": result.get("title"), "element": element,
        "matches": matches if isinstance(matches, int) and not isinstance(matches, bool) else 0,
        "binding": (
            {"backend_node_id": node_id, "digest": digest}
            if element is not None and isinstance(node_id, int) and not isinstance(node_id, bool)
            and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) else None
        ),
        "page_url": described.get("page_url") if isinstance(described.get("page_url"), str) else None,
        "harness_version": HARNESS_VERSION,
    }


def _guarded_script(body: str) -> str:
    """A fixed unbound script whose input runs under the network-effect guard."""
    prologue = ("import json, os\n" + VAN_HELPERS_PY + "\nclass _VanRefused(Exception):\n    pass\n"
                + NETWORK_GUARD_PY)
    indented = "\n".join("    " + line for line in body.strip().splitlines())
    return (prologue + "try:\n" + indented + "\nexcept _VanRefused as _exc:\n"
            "    print(\"__VAN_JSON__\" + json.dumps({\"refused\": str(_exc)}))\n")


NAVIGATE_SCRIPT = _guarded_script(r"""
url = os.environ["VAN_BH_URL"]
def _go():
    # Always the attached tab (browser-harness's new_tab() reuses a blank one the same way):
    # a new tab would be outside the guard, which fails its document as a POPUP.
    goto_url(url)
    wait_for_load()
_van_net_verdict(_van_net_run(_go))
print("__VAN_JSON__" + json.dumps({"navigated": True}))
""")

SCROLL_SCRIPT = _guarded_script(r"""
info = page_info()
x = max(0, int(info.get("w", 0)) // 2)
y = max(0, int(info.get("h", 0)) // 2)
_van_net_verdict(_van_net_run(lambda: scroll(x, y, dy=int(os.environ["VAN_BH_DY"]), dx=int(os.environ["VAN_BH_DX"]))))
print("__VAN_JSON__" + json.dumps({"scrolled": True}))
""")

UPLOAD_SCRIPT = _guarded_script(r"""
selector = os.environ["VAN_BH_LOCATOR"]
doc = cdp("DOM.getDocument", depth=1)
node = cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector)
if not node.get("nodeId"):
    raise RuntimeError("upload locator not found")
_van_net_verdict(_van_net_run(lambda: cdp("DOM.setFileInputFiles", nodeId=node["nodeId"], files=[os.environ["VAN_BH_UPLOAD"]])))
print("__VAN_JSON__" + json.dumps({"uploaded": True}))
""")


def navigate(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    url = assert_url_in_domain(str(body.get("url") or ""), domain)
    _assert_scope(body, url, "NAVIGATE")
    _refused(run_harness(alias, NAVIGATE_SCRIPT, {"VAN_BH_URL": url, **network_guard_env(body, alias)}))
    return page_info_result(alias, domain)


def _binding_env(body: dict[str, Any]) -> dict[str, str]:
    """The bound node and the task scope an actuation carries (review I5 MAJOR-2, owner
    decision 2026-09-30). Absent either, the script refuses (TARGET_BINDING_REQUIRED /
    TASK_SCOPE_REQUIRED) before touching the page."""
    binding = body.get("binding") if isinstance(body.get("binding"), dict) else None
    scope = body.get("task_scope") if isinstance(body.get("task_scope"), dict) else None
    return {"VAN_BH_BINDING": json.dumps(binding), "VAN_BH_SCOPE": json.dumps(scope)}


def _refusal_code(raw: str) -> str:
    """The typed code of a script refusal. A network-guard refusal keeps its kind, which is
    from a closed vocabulary (``NETWORK_WRITE_KINDS``) — never page data."""
    head, _, tail = raw.partition(":")
    if head == "NETWORK_WRITE_BLOCKED":
        return head + ":" + (tail if tail in NETWORK_WRITE_KINDS else "OTHER")
    return head[:64]


def _refused(result: Any) -> None:
    """A bound script's typed refusal becomes a 409 carrying the code (nothing was actuated,
    or the actuation was cancelled by the guard before the page saw it)."""
    if isinstance(result, dict) and isinstance(result.get("refused"), str):
        raise WorkerError(_refusal_code(result["refused"]), 409)


CLICK_SCRIPT = _bound_script(r"""
binding = json.loads(os.environ["VAN_BH_BINDING"])
scope = json.loads(os.environ["VAN_BH_SCOPE"])
obj, el = _van_bind(binding, scope)
x, y = _van_hit(obj, el)
guard = _van_guard(obj)
net = _van_net_run(lambda: click_at_xy(x, y))
done = _van_finish_after_net(guard, net)
if not done.get("navigated") and "click" not in (done.get("seen") or []):
    raise _VanRefused("TARGET_NOT_ACTIVATED")
_van_emit({"clicked": True})
""")


def click(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    """Review I5 MAJOR-2 — click the *bound* node, at a point where it is the node hit.

    The node comes from the ``binding`` /describe returned (CDP backendNodeId), not from the
    locator: re-querying the selector let the page swap which element matched between the
    classification and the click. Before the click the Harness re-describes the node and
    refuses when it is detached (TARGET_BINDING_LOST), no longer what was classified
    (TARGET_CHANGED), hidden or off-screen, the page is outside the task scope
    (TASK_SCOPE_*), or the node at its centre — through open and closed shadow roots — is
    neither it nor a non-interactive descendant of it (TARGET_NOT_HIT: an overlay, a wrapper
    around another control, a shadow host). During the click a guard cancels any event that
    does not reach the bound node (TARGET_MOVED_DURING_ACTUATION).
    """
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    _refused(run_harness(alias, CLICK_SCRIPT, {"VAN_BH_LOCATOR": locator, **_binding_env(body), **network_guard_env(body, alias)}))
    return page_info_result(alias, domain)


FILL_SCRIPT = _bound_script(r"""
binding = json.loads(os.environ["VAN_BH_BINDING"])
scope = json.loads(os.environ["VAN_BH_SCOPE"])
obj, el = _van_bind(binding, scope)
focused = _van_call(obj, "function(){ this.focus(); let a = document.activeElement; while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement; if (a !== this) return false; if (typeof this.select === 'function') this.select(); else { const r = document.createRange(); r.selectNodeContents(this); const s = getSelection(); s.removeAllRanges(); s.addRange(r); } return true; }").get("value")
if focused is not True:
    raise _VanRefused("TARGET_NOT_FOCUSABLE")
guard = _van_guard(obj)
net = _van_net_run(lambda: cdp("Input.insertText", text=os.environ["VAN_BH_SECRET"]))
_van_finish_after_net(guard, net)
_van_emit({"filled": True})
""")


def fill(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    """Fill the *bound* field (review I5 MAJOR-2): focused through its binding, verified to
    hold focus, then the referenced secret inserted — never typed into whatever a re-queried
    selector matches."""
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    secret = resolve_secret(body.get("value_ref"))
    _refused(run_harness(alias, FILL_SCRIPT, {"VAN_BH_LOCATOR": locator, "VAN_BH_SECRET": secret, **_binding_env(body), **network_guard_env(body, alias)}))
    return page_info_result(alias, domain)


PRESS_SCRIPT = _bound_script(r"""
binding = json.loads(os.environ["VAN_BH_BINDING"])
scope = json.loads(os.environ["VAN_BH_SCOPE"])
obj, el = _van_bind(binding, scope)
still = _van_call(obj, "function(){ let a = document.activeElement; while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement; return (a || document.body) === this; }").get("value")
if still is not True:
    raise _VanRefused("FOCUS_CHANGED")
guard = _van_guard(obj)
net = _van_net_run(lambda: press_key(os.environ["VAN_BH_KEY"]))
_van_finish_after_net(guard, net)
_van_emit({"pressed": True})
""")


def press(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    """Review I5 MAJOR-3 — press a key into the *bound* focused element.

    The gateway classified the key against ``document.activeElement`` (/describe with
    ``focus: true``): Enter/Space as a click on it, other keys in a field as a fill. The
    Harness refuses when focus has moved off that node (FOCUS_CHANGED), it changed, or the
    page left the task scope, and cancels any activation that does not reach it.
    """
    key = str(body.get("key") or "")
    if not key or len(key) > 64:
        raise WorkerError("KEY_REQUIRED", 422)
    _refused(run_harness(alias, PRESS_SCRIPT, {"VAN_BH_KEY": key, **_binding_env(body), **network_guard_env(body, alias)}))
    return page_info_result(alias, domain)


def _assert_scope(body: dict[str, Any], url: str, what: str) -> None:
    """Owner decision 2026-09-30 — when the gateway sends the task scope with a navigate or
    scroll, the Harness re-checks the destination/page against it."""
    scope = body.get("task_scope")
    if scope is None:
        return
    violation = _van_scope_violation(scope if isinstance(scope, dict) else {}, url, what)
    if violation:
        raise WorkerError(violation, 409)


def scroll_page(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    request = body.get("request") if isinstance(body.get("request"), dict) else {}
    dx = int(request.get("x", request.get("delta_x", 0)) or 0)
    dy = int(request.get("y", request.get("delta_y", 0)) or 0)
    if abs(dx) > 20000 or abs(dy) > 20000:
        raise WorkerError("SCROLL_DELTA_OUT_OF_RANGE", 422)
    if body.get("task_scope") is not None:
        _assert_scope(body, str(run_harness(alias, 'import json\nprint("__VAN_JSON__"+json.dumps({"url": page_info().get("url")}))\n').get("url") or ""), "PAGE")
    _refused(run_harness(alias, SCROLL_SCRIPT, {"VAN_BH_DX": str(dx), "VAN_BH_DY": str(dy), **network_guard_env(body, alias)}))
    return page_info_result(alias, domain)


def screenshot(alias: str, domain: str) -> dict[str, Any]:
    script = r"""
import hashlib, json
p = capture_screenshot(max_dim=1800)
with open(p, "rb") as f:
    data = f.read()
print("__VAN_JSON__" + json.dumps({"screenshot_digest": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "contains_secrets": False}))
"""
    result = run_harness(alias, script)
    info = page_info_result(alias, domain)
    return {**result, "url": info.get("url"), "title": info.get("title")}


def wait(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    condition = body.get("condition") if isinstance(body.get("condition"), dict) else {}
    kind = str(condition.get("kind") or "load")
    if kind == "load":
        run_harness(alias, 'import json\nwait_for_load(timeout=10)\nprint("__VAN_JSON__"+json.dumps({"waited":"load"}))\n')
    elif kind == "selector":
        selector = str(condition.get("selector") or "")
        if not selector or len(selector) > 2048:
            raise WorkerError("WAIT_SELECTOR_REQUIRED", 422)
        run_harness(
            alias,
            'import json,os\nok=wait_for_element(os.environ["VAN_BH_LOCATOR"],timeout=10)\nprint("__VAN_JSON__"+json.dumps({"waited":"selector","matched":bool(ok)}))\n',
            {"VAN_BH_LOCATOR": selector},
        )
    elif kind == "milliseconds":
        ms = int(condition.get("value", 0) or 0)
        if ms < 0 or ms > 10000:
            raise WorkerError("WAIT_DURATION_OUT_OF_RANGE", 422)
        time.sleep(ms / 1000)
    else:
        raise WorkerError("WAIT_KIND_UNSUPPORTED", 422)
    return page_info_result(alias, domain)


def upload(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    path = resolve_upload(body.get("file_ref"))
    _refused(run_harness(alias, UPLOAD_SCRIPT, {"VAN_BH_LOCATOR": locator, "VAN_BH_UPLOAD": str(path), **network_guard_env(body, alias)}))
    return page_info_result(alias, domain)


def tabs(alias: str, domain: str) -> dict[str, Any]:
    script = r"""
import json
items = [{"targetId": str(t.get("targetId") or ""), "title": str(t.get("title") or "")[:512], "url": str(t.get("url") or "")[:4096]} for t in list_tabs()]
print("__VAN_JSON__" + json.dumps({"tabs": items}))
"""
    result = run_harness(alias, script)
    safe = []
    for tab in result.get("tabs", []):
        url = str(tab.get("url") or "")
        if url.startswith(("http://", "https://")):
            try:
                assert_url_in_domain(url, domain)
            except WorkerError:
                continue
        safe.append(tab)
    return {"tabs": safe, "harness_version": HARNESS_VERSION}


OPERATIONS = {
    "/navigate": navigate,
    "/click": click,
    "/fill": fill,
    "/press": press,
    "/scroll": scroll_page,
    "/wait": wait,
    "/upload": upload,
}


FENCE_MAC_CONTEXT = "van-harness-fence/1"
MIN_FENCE_KEY_BYTES = 32


def fence_mac(key: bytes, alias: str, generation: int, holder_id: str) -> str:
    """HMAC-SHA256 the gateway sends with a fence (review I5 F3); same bytes on both sides."""
    message = f"{FENCE_MAC_CONTEXT}\n{alias}\n{int(generation)}\n{holder_id}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def load_fence_key(path: str) -> bytes | None:
    """The fence key from ``path`` (surrounding whitespace stripped), or None when unset.

    A configured path that is unreadable or holds fewer than 32 bytes is an error: the
    caller fails closed rather than running unauthenticated.
    """
    if not path:
        return None
    key = Path(path).read_bytes().strip()
    if len(key) < MIN_FENCE_KEY_BYTES:
        raise ValueError("fence key shorter than 32 bytes")
    return key


class LeaseFence:
    """Refuse actions under a stale page-lease generation (review I3 MAJOR-3, I4 MINOR-A, I5).

    The gateway's broker increments a profile's lease generation on every acquisition and
    sends the generation an action runs under (``lease_generation`` + ``lease_holder_id``).
    The worker remembers the newest generation it has seen per profile and refuses any
    fenced action carrying an older one (or the same one under another holder), so work
    still holding a lease the profile has since been re-leased past is not applied to the
    new holder's page.

    Review I4 MINOR-A — the fence works both ways:

    * A *mutating* operation (``MUTATING_OPERATIONS``) without a generation is refused
      (``LEASE_FENCE_REQUIRED``). Reads may be unfenced; a fenced read is still checked.
    * The newest generation is persisted per profile under ``VAN_HARNESS_STATE_ROOT``
      (written and fsynced *before* the action runs). Unreadable state refuses the action.

    Review I5:

    * F1 — ``admit`` holds the profile's lock from the check until the operation has been
      applied, so the check is atomic with the apply: once a newer generation has been
      admitted no older one can still be applying, and an older call that is applying
      finishes before the newer one is checked.
    * F2 — every profile that has ever been fenced is listed in a manifest next to the
      state files, and bootstrap.sh writes an install marker. A state file missing for a
      listed profile, or a manifest missing while the install marker exists, refuses the
      call (``LEASE_FENCE_STATE_MISSING``, 503) instead of re-admitting any generation.
      First boot (empty manifest, or no manifest and no install marker) admits.
    * F3 — with a key configured every fence must carry ``lease_mac`` =
      HMAC-SHA256(key, alias, generation, holder); a local caller without the key cannot
      advance the fence to lock the real holder out. ``require_mac`` without a key (a
      production worker whose key is missing or unreadable) refuses every fenced call.

    Owner interactive input does not travel through this worker: it is the browser stream
    host / control agent path, fenced by the interactive control lease and its control
    generation (``InteractiveSessionService.assert_may_actuate``).
    """

    FILE_PREFIX = "lease-fence-"
    MANIFEST = "lease-fence-manifest.json"

    def __init__(
        self,
        state_root: Path | None = None,
        *,
        key: bytes | None = None,
        require_mac: bool = False,
        install_marker: Path | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._profile_locks: dict[str, threading.RLock] = {}
        self._newest: dict[str, tuple[int, str]] = {}
        self._state_root = state_root
        self._key = key
        self._require_mac = require_mac or key is not None
        self._install_marker = install_marker

    def _path(self, alias: str) -> Path | None:
        if self._state_root is None:
            return None
        return safe_child(self._state_root, f"{self.FILE_PREFIX}{alias}.json")

    def _manifest_path(self) -> Path | None:
        return None if self._state_root is None else self._state_root / self.MANIFEST

    def _manifest(self) -> set[str] | None:
        """Profiles that have a persisted fence; None when there is no manifest."""
        path = self._manifest_path()
        if path is None or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            aliases = data["aliases"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WorkerError("LEASE_FENCE_STATE_INVALID", 503) from exc
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise WorkerError("LEASE_FENCE_STATE_INVALID", 503)
        return set(aliases)

    def _load(self, alias: str) -> tuple[int, str] | None:
        if alias in self._newest:
            return self._newest[alias]
        path = self._path(alias)
        if path is None:
            return None
        manifest = self._manifest()
        if not path.exists():
            if manifest is None:
                if self._install_marker is not None and self._install_marker.exists():
                    # Installed, but the whole fence state is gone: not a first boot.
                    raise WorkerError("LEASE_FENCE_STATE_MISSING", 503)
                return None
            if alias in manifest:
                raise WorkerError("LEASE_FENCE_STATE_MISSING", 503)
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            generation, holder = data["generation"], data["holder_id"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WorkerError("LEASE_FENCE_STATE_INVALID", 503) from exc
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1 or not isinstance(holder, str):
            raise WorkerError("LEASE_FENCE_STATE_INVALID", 503)
        self._newest[alias] = (generation, holder)
        return self._newest[alias]

    @staticmethod
    def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def _store(self, alias: str, generation: int, holder: str) -> None:
        path = self._path(alias)
        if path is not None:
            try:
                # State first, then the manifest entry: a crash between the two leaves state
                # without an entry (still enforced), never an entry without state.
                self._write_atomic(path, {"profile_alias": alias, "generation": generation, "holder_id": holder})
                manifest = self._manifest() or set()
                if alias not in manifest:
                    self._write_atomic(self._manifest_path(), {"schema_version": 1, "aliases": sorted(manifest | {alias})})
            except OSError as exc:
                raise WorkerError("LEASE_FENCE_STATE_UNWRITABLE", 503) from exc
        self._newest[alias] = (generation, holder)

    def _verify_mac(self, alias: str, generation: int, holder: str, body: dict[str, Any]) -> None:
        if self._key is None:
            if self._require_mac:
                raise WorkerError("LEASE_FENCE_KEY_UNCONFIGURED", 503)
            return
        mac = body.get("lease_mac")
        if not isinstance(mac, str) or not hmac.compare_digest(
            mac, fence_mac(self._key, alias, generation, holder)
        ):
            raise WorkerError("LEASE_FENCE_MAC_INVALID", 403)

    def profile_lock(self, alias: str) -> threading.RLock:
        with self._lock:
            return self._profile_locks.setdefault(alias, threading.RLock())

    def check(self, alias: str, body: dict[str, Any], mutating: bool = True) -> None:
        raw = body.get("lease_generation")
        if raw is None:
            if mutating:
                raise WorkerError("LEASE_FENCE_REQUIRED", 428)
            return
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
            raise WorkerError("LEASE_GENERATION_INVALID", 422)
        holder = body.get("lease_holder_id")
        if not isinstance(holder, str) or not holder or len(holder) > 128:
            raise WorkerError("LEASE_HOLDER_REQUIRED", 422)
        self._verify_mac(alias, raw, holder, body)
        with self._lock:
            newest = self._load(alias)
            if newest is not None:
                if raw < newest[0]:
                    raise WorkerError("LEASE_GENERATION_STALE", 409)
                if raw == newest[0] and holder != newest[1]:
                    # One generation has exactly one holder.
                    raise WorkerError("LEASE_GENERATION_STALE", 409)
                if newest == (raw, holder):
                    return
            self._store(alias, raw, holder)

    @contextlib.contextmanager
    def admit(self, alias: str, body: dict[str, Any], mutating: bool = True):
        """Check the fence and keep the profile locked until the operation has run (I5 F1)."""
        with self.profile_lock(alias):
            self.check(alias, body, mutating)
            yield


#: Operations that change the page. Each must carry the lease generation it runs under.
MUTATING_OPERATIONS = frozenset({"/navigate", "/click", "/fill", "/press", "/scroll", "/upload"})
#: Reads. Unfenced is allowed; a fenced read is checked like any other call.
READ_OPERATIONS = frozenset({"/page_info", "/screenshot", "/tabs", "/describe", "/wait"})



def _module_fence() -> LeaseFence:
    # A production worker (a trust zone is configured) or one told to use a key file must
    # have a usable key; otherwise every fenced call is refused (fail closed, review I5 F3).
    try:
        key = load_fence_key(HARNESS_FENCE_KEY_FILE)
    except (OSError, ValueError):
        key = None
    return LeaseFence(
        HARNESS_STATE_ROOT,
        key=key,
        require_mac=bool(TRUST_ZONE) or bool(HARNESS_FENCE_KEY_FILE),
        install_marker=HARNESS_FENCE_INSTALL_MARKER,
    )


FENCE = _module_fence()


class Handler(BaseHTTPRequestHandler):
    server_version = SERVICE_VERSION

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[van-browser-harness] {self.address_string()} {fmt % args}", flush=True)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {
                "ok": True,
                "service": SERVICE_VERSION,
                "runtime_version": HARNESS_VERSION,
                "helper_authoring": False,
                "raw_cdp_http": False,
                "bind": BIND,
                "trust_zone": TRUST_ZONE or None,
            })
            return
        self.send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        try:
            raw_length = self.headers.get("content-length")
            if raw_length is None:
                raise WorkerError("CONTENT_LENGTH_REQUIRED", 411)
            length = int(raw_length)
            if length < 0 or length > MAX_BODY_BYTES:
                raise WorkerError("REQUEST_TOO_LARGE", 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise WorkerError("REQUEST_BODY_NOT_OBJECT", 422)
            if body.get("mode") != "PRODUCTION_ACTUATOR":
                raise WorkerError("HARNESS_MODE_REQUIRED", 403)
            if body.get("allow_helper_authoring") is not False:
                raise WorkerError("HELPER_AUTHORING_FORBIDDEN", 403)
            alias = safe_alias(body.get("profile_alias"))
            domain = safe_domain(body.get("target_domain"))
            if self.path not in MUTATING_OPERATIONS and self.path not in READ_OPERATIONS:
                raise WorkerError("OPERATION_NOT_ALLOWED", 404)
            # Review I5 F1 — the fence check and the operation run under one profile lock.
            with FENCE.admit(alias, body, mutating=self.path in MUTATING_OPERATIONS):
                if self.path == "/page_info":
                    result = page_info_result(alias, domain)
                elif self.path == "/describe":
                    result = describe(body, alias, domain)
                elif self.path == "/screenshot":
                    result = screenshot(alias, domain)
                elif self.path == "/tabs":
                    result = tabs(alias, domain)
                else:
                    operation = OPERATIONS.get(self.path)
                    if operation is None:
                        raise WorkerError("OPERATION_NOT_ALLOWED", 404)
                    result = operation(body, alias, domain)
            self.send_json(200, result)
        except WorkerError as exc:
            self.send_json(exc.status, {"error": exc.code})
        except (ValueError, json.JSONDecodeError):
            self.send_json(422, {"error": "REQUEST_INVALID"})
        except Exception:
            self.send_json(502, {"error": "BROWSER_WORKER_FAILURE"})


def main() -> None:
    if TRUST_ZONE or HARNESS_FENCE_KEY_FILE:
        try:
            if load_fence_key(HARNESS_FENCE_KEY_FILE) is None:
                raise ValueError("unset")
        except (OSError, ValueError) as exc:
            raise SystemExit(
                "browser harness worker refuses to start without a readable "
                "VAN_HARNESS_FENCE_KEY_FILE (>= 32 bytes)"
            ) from exc
    for path in (PROFILE_ROOT, DOWNLOAD_ROOT, SECRET_ROOT, RUNTIME_ROOT, HARNESS_STATE_ROOT):
        path.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((BIND, PORT), Handler)

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        POOL.close()


if __name__ == "__main__":
    main()
