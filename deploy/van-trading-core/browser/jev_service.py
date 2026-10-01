#!/usr/bin/env python3
"""Private Jev Ultrafast proposal worker for VAN.

Jev is a fast semantic selector only. It never receives a shell, browser cookies,
storage, screenshots, broker authority, or an autonomous browser loop. It never
executes an action. The Gateway checks the proposal and Browser Harness revalidates
page freshness before one observed node may execute.

Pinned upstream:
  browser-use/jev-ultrafast@1231850a0bf1a0c0341fe408ef1668dbbfdfac46
  jev-ultrafast 0.1.0
  TypeSafe decision model jev-1.13.0
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jev_ultrafast.model import choose

SERVICE_VERSION = "van-jev-ultrafast-worker/1"
UPSTREAM_VERSION = "0.1.0"
UPSTREAM_COMMIT = "1231850a0bf1a0c0341fe408ef1668dbbfdfac46"
MAX_BODY_BYTES = 256 * 1024
MAX_ACTIONS = 260
MAX_TEXT = 6000
MAX_GOAL = 8000

BIND = os.getenv("VAN_JEV_BIND", "127.0.0.1")
PORT = int(os.getenv("VAN_JEV_PORT", "9142"))
MODEL = os.getenv("VAN_JEV_TYPESAFE_MODEL", "jev-1.13.0")
REQUIRE_STARTUP_QUALIFICATION = os.getenv(
    "VAN_JEV_REQUIRE_STARTUP_QUALIFICATION", "1"
) == "1"
QUALIFICATION_FILE = Path(
    os.getenv("VAN_JEV_QUALIFICATION_FILE", "/run/van-jev/qualified.json")
)
SECRET_ROOT = Path(
    os.getenv("VAN_JEV_SECRET_ROOT", "/var/lib/van-trading/browser/jev-secrets")
)
KEY_REF = os.getenv(
    "VAN_JEV_TYPESAFE_KEY_REF", "secretref://browser/jev-typesafe"
)

if BIND not in {"127.0.0.1", "::1", "localhost"}:
    raise SystemExit("Jev worker refuses a non-loopback bind")

_REF = re.compile(r"^secretref://browser/([A-Za-z0-9._-]{1,128})$")
_HOST = re.compile(r"^[a-z0-9][a-z0-9.-]{0,252}$")
_SENSITIVE = (
    re.compile(r"(?i)\b(?:set-)?cookie\b\s*[:=]"),
    re.compile(
        r"(?i)\b(?:session(?:id|_id|-token)|access[_-]?token|refresh[_-]?token|"
        r"api[_-]?key|password)\b\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\bauthorization\b\s*[:=]\s*(?:bearer|basic)\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\b\d{6}\b\s*(?:is your|otp|verification code)"),
)

_QUALIFIED = False
_QUALIFICATION: dict[str, Any] = {}


class WorkerError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _secret(ref: str) -> str:
    match = _REF.fullmatch(ref)
    if not match:
        raise WorkerError("JEV_KEY_REFERENCE_INVALID", 503)
    root = SECRET_ROOT.resolve()
    path = (root / match.group(1)).resolve()
    if path.parent != root or not path.is_file():
        raise WorkerError("JEV_KEY_UNAVAILABLE", 503)
    size = path.stat().st_size
    if size < 16 or size > 16384:
        raise WorkerError("JEV_KEY_UNAVAILABLE", 503)
    return path.read_text(encoding="utf-8").strip()


def _domain(value: Any) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if not domain or not _HOST.fullmatch(domain) or ".." in domain:
        raise WorkerError("JEV_DOMAIN_INVALID", 422)
    return domain


def _same_domain(url: str, domain: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme in {"https", "http"} and (
        host == domain or host.endswith("." + domain)
    )


def _scan_sensitive(payload: Any) -> None:
    blob = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), default=str
    )
    if any(pattern.search(blob) for pattern in _SENSITIVE):
        raise WorkerError("JEV_PAGE_CONTAINS_SENSITIVE_MATERIAL", 409)


def _validate_page(raw: Any, domain: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise WorkerError("JEV_PAGE_REQUIRED", 422)
    url = str(raw.get("url") or "")
    if url and url != "about:blank" and not _same_domain(url, domain):
        raise WorkerError("JEV_PAGE_OUTSIDE_TASK_DOMAIN", 403)
    actions = raw.get("actions")
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise WorkerError("JEV_ACTION_SPACE_INVALID", 422)
    safe_actions: list[dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            raise WorkerError("JEV_ACTION_INVALID", 422)
        kind = str(item.get("kind") or "")
        if kind not in {"click", "fill", "select", "scroll", "wait"}:
            raise WorkerError("JEV_ACTION_KIND_INVALID", 422)
        safe_actions.append(dict(item))
    page = {
        "url": url,
        "title": str(raw.get("title") or "")[:1000],
        "text": str(raw.get("text") or "")[:MAX_TEXT],
        "actions": safe_actions,
        "fingerprint": str(raw.get("fingerprint") or "")[:128],
    }
    _scan_sensitive(page)
    return page


def _choose(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("allow_text_generation") is not False:
        raise WorkerError("JEV_TEXT_GENERATION_FORBIDDEN", 403)
    if body.get("allow_unbounded_agent_loop") is not False:
        raise WorkerError("JEV_UNBOUNDED_LOOP_FORBIDDEN", 403)
    if str(body.get("profile_alias") or "") != "muse_owner":
        raise WorkerError("JEV_PROFILE_NOT_ADMITTED", 403)

    domain = _domain(body.get("target_domain"))
    if domain != "muse.ai":
        raise WorkerError("JEV_DOMAIN_NOT_ADMITTED", 403)

    goal = str(body.get("goal") or "").strip()
    if not goal or len(goal) > MAX_GOAL:
        raise WorkerError("JEV_GOAL_INVALID", 422)

    page = _validate_page(body.get("page"), domain)
    history = body.get("history") if isinstance(body.get("history"), list) else []
    history = [dict(x) for x in history[-10:] if isinstance(x, dict)]
    _scan_sensitive({"goal": goal, "history": history})

    os.environ["TYPESAFE_API_KEY"] = _secret(KEY_REF)
    os.environ["TYPESAFE_MODEL"] = MODEL
    os.environ.pop("TEXT_MODEL_API_KEY", None)
    os.environ.pop("TEXT_MODEL", None)
    os.environ.pop("TEXT_MODEL_BASE_URL", None)

    decision = choose(page, goal, history)
    resolved_model = str(decision.get("model") or "")
    if resolved_model != MODEL:
        raise WorkerError("JEV_MODEL_DRIFT", 503)

    choice = str(decision.get("choice") or "")
    operation = str(decision.get("operation") or "")
    action = next(
        (a for a in page["actions"] if str(a.get("id")) == choice),
        None,
    )
    if operation in {"DONE", "BLOCKED"}:
        action = None
    elif action is None:
        raise WorkerError("JEV_DECISION_ACTION_MISSING", 502)

    return {
        "ok": True,
        "runtime_version": UPSTREAM_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "model": resolved_model,
        "choice": choice,
        "operation": operation,
        "action": action,
        "fingerprint": page["fingerprint"],
        "confidence": float(decision.get("confidence") or 0.0),
        "latency_ms": int(decision.get("latency_ms") or 0),
        "text_generation": False,
        "executes_actions": False,
    }


def _run_live_qualification() -> dict[str, Any]:
    """Paid, side-effect-free Jev canary. No browser operation is executed."""
    global _QUALIFIED, _QUALIFICATION

    result = _choose(
        {
            "task_id": "jev-startup-canary",
            "profile_alias": "muse_owner",
            "target_domain": "muse.ai",
            "goal": "Click the Open Muse workspace button.",
            "allow_text_generation": False,
            "allow_unbounded_agent_loop": False,
            "page": {
                "url": "https://muse.ai/",
                "title": "Muse qualification",
                "text": "Open your Muse workspace.",
                "fingerprint": "startup-canary-v1",
                "actions": [
                    {
                        "id": "e1",
                        "node": 1,
                        "kind": "click",
                        "role": "button",
                        "label": "Open Muse workspace",
                        "value": "",
                    }
                ],
            },
            "history": [],
        }
    )
    if result.get("operation") != "CLICK":
        raise WorkerError("JEV_STARTUP_CANARY_OPERATION_MISMATCH", 503)
    action = result.get("action")
    if not isinstance(action, dict) or str(action.get("id")) != "e1":
        raise WorkerError("JEV_STARTUP_CANARY_TARGET_MISMATCH", 503)
    if result.get("model") != MODEL:
        raise WorkerError("JEV_STARTUP_CANARY_MODEL_MISMATCH", 503)

    receipt = {
        "qualified": True,
        "runtime_version": UPSTREAM_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "model": MODEL,
        "canary": "single_observed_click_no_execution",
        "text_generation": False,
        "executes_actions": False,
        "verified_at_unix": int(time.time()),
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    QUALIFICATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUALIFICATION_FILE.with_name(QUALIFICATION_FILE.name + ".tmp")
    tmp.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    os.replace(tmp, QUALIFICATION_FILE)

    _QUALIFIED = True
    _QUALIFICATION = receipt
    return dict(receipt)


class Handler(BaseHTTPRequestHandler):
    server_version = SERVICE_VERSION

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False
        ).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._send(404, {"ok": False, "error": "NOT_FOUND"})
            return
        try:
            key_present = bool(_secret(KEY_REF))
        except WorkerError:
            key_present = False
        self._send(
            200,
            {
                "ok": True,
                "service": SERVICE_VERSION,
                "runtime_version": UPSTREAM_VERSION,
                "upstream_commit": UPSTREAM_COMMIT,
                "bind": BIND,
                "model": MODEL,
                "model_key_present": key_present,
                "startup_qualified": _QUALIFIED,
                "qualification": dict(_QUALIFICATION),
                "text_generation": False,
                "executes_actions": False,
                "autonomous_loop": False,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path not in {"/choose", "/qualify"}:
                raise WorkerError("OPERATION_NOT_ALLOWED", 404)
            raw_len = self.headers.get("content-length")
            if raw_len is None:
                raise WorkerError("CONTENT_LENGTH_REQUIRED", 411)
            length = int(raw_len)
            if length < 0 or length > MAX_BODY_BYTES:
                raise WorkerError("REQUEST_TOO_LARGE", 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise WorkerError("REQUEST_BODY_NOT_OBJECT", 422)
            if self.path == "/qualify":
                self._send(200, {"ok": True, **_run_live_qualification()})
                return
            if REQUIRE_STARTUP_QUALIFICATION and not _QUALIFIED:
                raise WorkerError("JEV_NOT_STARTUP_QUALIFIED", 503)
            self._send(200, _choose(body))
        except WorkerError as exc:
            self._send(exc.status, {"ok": False, "error": exc.code})
        except (ValueError, json.JSONDecodeError):
            self._send(422, {"ok": False, "error": "REQUEST_INVALID"})
        except Exception:
            self._send(503, {"ok": False, "error": "JEV_UNAVAILABLE"})

    def log_message(self, *_args: Any) -> None:
        return


def main() -> None:
    if REQUIRE_STARTUP_QUALIFICATION:
        _run_live_qualification()
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
