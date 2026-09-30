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
#
# Redaction: no element ever carries a ``value``. Input, textarea, select and contenteditable
# contents are never read into a name or description (a textarea's text is its value). Every
# field B2 would treat as sensitive (type=password; autocomplete cc-*, *-password,
# one-time-code; a name/id/label/placeholder naming a password, PIN, OTP, card, CVC, IBAN,
# account or sort code) is marked ``sensitive``; whether any field holds a value is reported
# only as the boolean ``value_present``. No cookie or storage content is read: page_info
# reports ``cookies_present`` and ``authenticated`` as booleans or None (unknown) only.

MAX_ELEMENTS = 200
MAX_ELEMENTS_BYTES = 65536
MAX_ELEMENT_TEXT = 256
MAX_LOCATOR_LEN = 1024
MAX_ELEMENT_ATTRIBUTES = 32
REDACTED = "[REDACTED]"
ELEMENT_STRING_KEYS = (
    "locator", "locator_kind", "role", "name", "description", "type", "autocomplete",
    "placeholder", "inputmode", "pattern", "tag",
)
ELEMENT_BOOL_KEYS = ("hidden", "landmark", "disabled", "sensitive", "value_present")
ATTRIBUTE_NAME_RE = re.compile(r"^(?:id|name|type|class|role|href|action|formaction|aria-label|title|alt|target|data-[a-z0-9_.:-]{1,48})$")
SENSITIVE_NAME_RE = re.compile(
    r"pass(?:word|code|phrase)?|pwd|secret|token|otp|one[-_ ]?time|2fa|mfa|\bpin\b|cvv|cvc|csc|"
    r"security[-_ ]?code|card|cc[-_]?(?:num|number|exp|csc|name)|iban|sort[-_ ]?code|routing|"
    r"account[-_ ]?(?:no|num|number)|acct|ssn|social[-_ ]?security|passport|expiry|"
    r"auth|session|csrf|xsrf|api[-_ ]?key|private[-_ ]?key|credential",
    re.IGNORECASE,
)

ELEMENTS_JS = r"""
(async (mode, target) => {
  const MAX = 200, MAX_BYTES = 60000, TEXT = 256, SCAN = 3000;
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
      return clip(u.origin + u.pathname + (keys.length ? '?' + keys.join('&') : ''));
    } catch (e) { return ''; }
  }
  function attrsOf(el) {
    const out = {}; let data = 0;
    for (const a of ['id', 'name', 'type', 'class', 'role', 'aria-label', 'title', 'alt', 'target']) {
      const v = el.getAttribute(a); if (v != null && v !== '') out[a] = clip(v);
    }
    for (const a of ['href', 'action', 'formaction']) { const v = el.getAttribute(a); if (v) out[a] = safeUrl(v); }
    for (const a of el.attributes) {
      if (!a.name.startsWith('data-') || data >= 16) continue;
      data++;
      out[a.name] = SENSITIVE.test(a.name) ? '[REDACTED]' : clip(a.value);
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
    return {
      locator, locator_kind: kind, role, name, description,
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
"""


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
            attributes[name] = REDACTED if name.startswith("data-") and SENSITIVE_NAME_RE.search(name) else _clip(value)
    out["attributes"] = attributes
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
    for the page: no cookie (CDP, HttpOnly included), no local/session storage entry and no
    IndexedDB database. Anything else is None (unknown), which B2 treats as signed in.
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
    ):
        authenticated, basis = False, "NO_SESSION_STATE"
    else:
        authenticated, basis = None, "UNKNOWN"
    return {"authenticated": authenticated, "cookies_present": cookies, "authentication_basis": basis}


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
    cookies = None
    try:
        got = cdp("Network.getCookies", urls=[str(info.get("url") or "")])
        cookies = bool(got.get("cookies")) if isinstance(got, dict) and isinstance(got.get("cookies"), list) else None
    except Exception:
        cookies = None
    info["__van_snapshot__"] = snapshot if isinstance(snapshot, dict) else {"elements_error": True}
    info["__van_cookies__"] = cookies
info["harness_version"] = "0.1.13"
print("__VAN_JSON__" + json.dumps(info))
""".replace("__ELEMENTS_LIST__", json.dumps(elements_expression("list")))

DESCRIBE_SCRIPT = r"""
import json, os
info = page_info()
out = {"url": info.get("url"), "title": info.get("title")}
if "dialog" in info:
    out["dialog"] = True
else:
    expr = __DESCRIBE_JS__ + "(" + json.dumps("describe") + "," + json.dumps(os.environ["VAN_BH_LOCATOR"]) + ")"
    out["describe"] = js(expr)
print("__VAN_JSON__" + json.dumps(out))
""".replace("__DESCRIBE_JS__", json.dumps(ELEMENTS_JS.strip()))


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
    """Resolve one locator to the element shape page_info reports (review I4).

    For a target the bounded page_info list did not include. The element is the one the
    Harness would act on for this locator, reported under the locator exactly as given.
    """
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > MAX_LOCATOR_LEN:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    result = run_harness(alias, DESCRIBE_SCRIPT, {"VAN_BH_LOCATOR": locator})
    if not isinstance(result, dict):
        raise WorkerError("BROWSER_DESCRIBE_INVALID", 502)
    current = str(result.get("url") or "")
    if current and current != "about:blank":
        assert_url_in_domain(current, domain)
    described = result.get("describe") if isinstance(result.get("describe"), dict) else {}
    if described.get("error") == "LOCATOR_INVALID":
        raise WorkerError("LOCATOR_INVALID", 422)
    element = sanitize_element(described.get("element"))
    if element is not None:
        element["locator"] = locator
    matches = described.get("matches")
    return {
        "url": result.get("url"), "title": result.get("title"), "element": element,
        "matches": matches if isinstance(matches, int) and not isinstance(matches, bool) else 0,
        "harness_version": HARNESS_VERSION,
    }


def navigate(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    url = assert_url_in_domain(str(body.get("url") or ""), domain)
    script = r"""
import json, os
url = os.environ["VAN_BH_URL"]
cur = current_tab()
if not cur or str(cur.get("url") or "").startswith("about:blank"):
    new_tab(url)
else:
    goto_url(url)
wait_for_load()
print("__VAN_JSON__" + json.dumps({"navigated": True}))
"""
    run_harness(alias, script, {"VAN_BH_URL": url})
    return page_info_result(alias, domain)


def click(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    script = r"""
import json, os
sel = os.environ["VAN_BH_LOCATOR"]
expr = "(()=>{const e=document.querySelector(" + json.dumps(sel) + ");if(!e)return null;const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,w:r.width,h:r.height};})()"
box = js(expr)
if not box or box.get("w", 0) <= 0 or box.get("h", 0) <= 0:
    raise RuntimeError("locator not found or not visible")
click_at_xy(float(box["x"]), float(box["y"]))
print("__VAN_JSON__" + json.dumps({"clicked": True}))
"""
    run_harness(alias, script, {"VAN_BH_LOCATOR": locator})
    return page_info_result(alias, domain)


def fill(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    secret = resolve_secret(body.get("value_ref"))
    script = r"""
import json, os
fill_input(os.environ["VAN_BH_LOCATOR"], os.environ["VAN_BH_SECRET"], clear_first=True, timeout=5)
print("__VAN_JSON__" + json.dumps({"filled": True}))
"""
    run_harness(alias, script, {"VAN_BH_LOCATOR": locator, "VAN_BH_SECRET": secret})
    return page_info_result(alias, domain)


def press(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    key = str(body.get("key") or "")
    if not key or len(key) > 64:
        raise WorkerError("KEY_REQUIRED", 422)
    run_harness(
        alias,
        'import json,os\npress_key(os.environ["VAN_BH_KEY"])\nprint("__VAN_JSON__"+json.dumps({"pressed":True}))\n',
        {"VAN_BH_KEY": key},
    )
    return page_info_result(alias, domain)


def scroll_page(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    request = body.get("request") if isinstance(body.get("request"), dict) else {}
    dx = int(request.get("x", request.get("delta_x", 0)) or 0)
    dy = int(request.get("y", request.get("delta_y", 0)) or 0)
    if abs(dx) > 20000 or abs(dy) > 20000:
        raise WorkerError("SCROLL_DELTA_OUT_OF_RANGE", 422)
    run_harness(
        alias,
        'import json,os\ninfo=page_info()\nx=max(0,int(info.get("w",0))//2)\ny=max(0,int(info.get("h",0))//2)\nscroll(x,y,dy=int(os.environ["VAN_BH_DY"]),dx=int(os.environ["VAN_BH_DX"]))\nprint("__VAN_JSON__"+json.dumps({"scrolled":True}))\n',
        {"VAN_BH_DX": str(dx), "VAN_BH_DY": str(dy)},
    )
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
    script = r"""
import json, os
selector = os.environ["VAN_BH_LOCATOR"]
doc = cdp("DOM.getDocument", depth=1)
node = cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector)
if not node.get("nodeId"):
    raise RuntimeError("upload locator not found")
cdp("DOM.setFileInputFiles", nodeId=node["nodeId"], files=[os.environ["VAN_BH_UPLOAD"]])
print("__VAN_JSON__" + json.dumps({"uploaded": True}))
"""
    run_harness(alias, script, {"VAN_BH_LOCATOR": locator, "VAN_BH_UPLOAD": str(path)})
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
