from __future__ import annotations

import fnmatch
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Request as FastRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from commander.accounts import ACCOUNT_COMMANDS, ACCOUNT_TOOL_SCHEMAS, AccountControlSettings, build_account_handlers, redact_args
from commander.auth import NonceCache, verify_request

REDACT = re.compile(r"(?i)(password|passwd|token|api[_-]?key|secret|bearer|signing[_-]?key)(\s*[:=]\s*)\S+")
UNIT_RE = re.compile(r"^[A-Za-z0-9@._-]+$")
DEFAULT_UNITS = ("vati-session@*.service", "vati-commander.service", "vati-vekl.service", "vati-supabase.service", "vati-mt5-pull.service", "caddy.service")
COMMANDS = ("status", "ledger_status", "services", "restart_service", "tail_log", "run_backtest", "vekl_resolve", "halt", "doctor", "accounts") + ACCOUNT_COMMANDS
Runner = Callable[[list[str], int], tuple[int, str, str]]


def default_runner(argv: list[str], timeout_s: int) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, check=False)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout_s}s"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


@dataclass
class CommanderSettings:
    token_file: str = os.environ.get("VAN_COMMANDER_TOKEN_FILE", "/opt/van-trading/secrets/commander.token")
    ledger: str = os.environ.get("VAN_COMMANDER_LEDGER", "/var/lib/van-trading/ledger/vati.sqlite")
    heartbeat_dir: str = os.environ.get("VAN_COMMANDER_HEARTBEAT_DIR", "/var/lib/van-trading/heartbeats")
    log_dir: str = os.environ.get("VAN_COMMANDER_LOG_DIR", "/var/log/van-trading")
    data_dir: str = os.environ.get("VAN_COMMANDER_DATA_DIR", "/var/lib/van-trading")
    repo_root: str = os.environ.get("VAN_COMMANDER_REPO", str(Path(__file__).resolve().parents[2]))
    vekl_url: str = os.environ.get("VAN_VEKL_URL", "http://127.0.0.1:9134")
    vekl_token: str = os.environ.get("VAN_VEKL_TOKEN", "")
    accounts_registry: str = os.environ.get("VAN_ACCOUNTS_REGISTRY", "/opt/van-trading/config/accounts.json")
    secrets_dir: str = os.environ.get("VAN_SECRETS", "/opt/van-trading/secrets")
    account_control: Optional[AccountControlSettings] = None   # injected for tests; else derived
    units: tuple[str, ...] = tuple(filter(None, os.environ.get("VAN_COMMANDER_UNITS", ",".join(DEFAULT_UNITS)).split(",")))
    backtest_timeout_s: int = int(os.environ.get("VAN_COMMANDER_BACKTEST_TIMEOUT", "600"))
    max_log_lines: int = 400
    python: str = sys.executable
    runner: Runner = field(default=default_runner)
    token: Optional[str] = None      # injected for tests; otherwise read from token_file

    def load_token(self) -> str:
        if self.token:
            return self.token
        p = Path(self.token_file)
        if not p.is_file():
            raise RuntimeError(f"commander token file missing: {self.token_file}")
        if stat.S_IMODE(p.stat().st_mode) & 0o077:
            raise RuntimeError("commander token file must be mode 0600")
        tok = p.read_text().strip()
        if len(tok) < 32:
            raise RuntimeError("commander token too short (need ≥ 32 chars)")
        return tok

    def unit_allowed(self, unit: str) -> bool:
        return bool(UNIT_RE.match(unit)) and any(fnmatch.fnmatch(unit, pat) for pat in self.units)


def redact(text: str) -> str:
    return REDACT.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)


class CmdBody(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "hermes"


TOOL_SCHEMAS = {
    "status": {"description": "Session heartbeats, ledger head, VEKL health and unit states on van-trading-core.", "properties": {}},
    "ledger_status": {"description": "Event counts by kind and full chain verification of the VATI ledger.", "properties": {}},
    "services": {"description": "Active/enabled state of the allowlisted vati-* systemd units.", "properties": {}},
    "restart_service": {"description": "Restart one allowlisted vati-* unit (audited). Open positions keep venue stops; no orders are placed by a restart.", "properties": {"unit": {"type": "string"}}, "required": ["unit"]},
    "tail_log": {"description": "Last N journal lines of an allowlisted unit, secrets redacted.", "properties": {"unit": {"type": "string"}, "lines": {"type": "integer", "default": 100}}, "required": ["unit"]},
    "run_backtest": {"description": "Run `python -m vati backtest` on files under the data directory; bounded by timeout; result is a candidate, never a promotion.", "properties": {"config": {"type": "string"}, "bars": {"type": "string"}}, "required": ["config", "bars"]},
    "vekl_resolve": {"description": "Resolve trading engineering knowledge through the dedicated trading VEKL; returns an activation id.", "properties": {"instruction": {"type": "string"}, "affected_paths": {"type": "array", "items": {"type": "string"}}}, "required": ["instruction"]},
    "halt": {"description": "Owner-signed halt (A4): appends KILL_SWITCH OWNER_HALT to the ledger; sessions stop new orders. Requires owner_signature_ref.", "properties": {"owner_signature_ref": {"type": "string"}, "reason": {"type": "string"}}, "required": ["owner_signature_ref"]},
    "doctor": {"description": "Host diagnostics: runtimes, disk, ledger reachability, VEKL, heartbeat ages, secret file modes.", "properties": {}},
    "accounts": {"description": "Public view of the account registry (aliases, broker kind, safety identity). Never credentials.", "properties": {}},
    **ACCOUNT_TOOL_SCHEMAS,
}


def create_app(settings: Optional[CommanderSettings] = None) -> FastAPI:
    st = settings or CommanderSettings()
    app = FastAPI(title="Van Trading Commander", version="1.0.0")
    nonces = NonceCache()
    audit_path = Path(st.log_dir) / "commander-audit.jsonl"
    started = time.time()

    def audit(cmd: str, requested_by: str, args: dict, result: str) -> None:
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a") as f:
                f.write(json.dumps({"ts": int(time.time()), "cmd": cmd, "by": requested_by, "args": redact_args({k: v for k, v in args.items() if k != "owner_signature_ref"}), "result": result[:200]}) + "\n")
        except OSError:
            pass

    def ledger():
        from vati.core.ledger_pg import open_ledger
        return open_ledger(st.ledger)

    def heartbeats() -> list[dict]:
        out = []
        d = Path(st.heartbeat_dir)
        if d.is_dir():
            for p in sorted(d.glob("*.json")):
                try:
                    hb = json.loads(p.read_text()); hb["age_s"] = int(time.time() - hb.get("updated_ms", 0) / 1000); hb["file"] = p.name; out.append(hb)
                except (OSError, ValueError):
                    out.append({"file": p.name, "error": "unreadable"})
        return out

    def vekl_get(path: str) -> dict:
        try:
            req = Request(st.vekl_url + path, headers={"Authorization": f"Bearer {st.vekl_token}"} if st.vekl_token else {})
            with urlopen(req, timeout=5) as r:  # noqa: S310 — loopback service
                return json.loads(r.read())
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:200]}

    def units_state() -> list[dict]:
        out = []
        for pat in st.units:
            if "*" in pat:
                code, o, _ = st.runner(["systemctl", "list-units", "--all", "--no-legend", "--plain", pat], 10)
                names = [ln.split()[0] for ln in o.splitlines() if ln.strip()] if code == 0 else []
            else:
                names = [pat]
            for u in names:
                _, active, _ = st.runner(["systemctl", "is-active", u], 10)
                _, enabled, _ = st.runner(["systemctl", "is-enabled", u], 10)
                out.append({"unit": u, "active": active.strip() or "unknown", "enabled": enabled.strip() or "unknown"})
        return out

    # ------------------------------------------------------------ commands
    def cmd_status(a: dict) -> dict:
        led = None
        try:
            led = ledger(); lg = {"head": led.head(), "events": led.count(), "backend": type(led).__name__}
        except Exception as exc:  # noqa: BLE001
            lg = {"error": str(exc)[:200]}
        finally:
            if led is not None:
                led.close()
        return {"host": platform.node(), "uptime_s": int(time.time() - started), "heartbeats": heartbeats(), "ledger": lg, "vekl": vekl_get("/health"), "units": units_state()}

    def cmd_ledger_status(a: dict) -> dict:
        from vati.core.events import EventKind
        led = ledger()
        try:
            ok, n = led.verify_chain()
            return {"chain_ok": ok, "events": n, "head": led.head(), "counts": {k.value: led.count(k) for k in EventKind if led.count(k)}}
        finally:
            led.close()

    def cmd_services(a: dict) -> dict:
        return {"units": units_state()}

    def cmd_restart(a: dict) -> dict:
        unit = str(a.get("unit", ""))
        if not st.unit_allowed(unit):
            raise HTTPException(403, f"unit not in allowlist: {unit}")
        code, o, e = st.runner(["systemctl", "restart", unit], 60)
        _, active, _ = st.runner(["systemctl", "is-active", unit], 10)
        return {"unit": unit, "restarted": code == 0, "active": active.strip(), "stderr": redact(e)[:300]}

    def cmd_tail(a: dict) -> dict:
        unit = str(a.get("unit", "")); lines = max(1, min(int(a.get("lines", 100)), st.max_log_lines))
        if not st.unit_allowed(unit):
            raise HTTPException(403, f"unit not in allowlist: {unit}")
        code, o, e = st.runner(["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "cat"], 20)
        return {"unit": unit, "lines": redact(o).splitlines()[-lines:], "error": redact(e)[:200] if code else ""}

    def _under_data(p: str) -> Path:
        root = Path(st.data_dir).resolve()
        cand = (root / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
        if root not in cand.parents and cand != root:
            raise HTTPException(403, f"path must be under {root}")
        if not cand.is_file():
            raise HTTPException(404, f"no such file: {cand}")
        return cand

    def cmd_backtest(a: dict) -> dict:
        cfg, bars = _under_data(str(a.get("config", ""))), _under_data(str(a.get("bars", "")))
        out_path = Path(st.data_dir) / "backtests" / f"bt-{int(time.time())}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        code, o, e = st.runner([st.python, "-m", "vati", "backtest", "--bars", str(bars), "--config", str(cfg), "--out", str(out_path)], st.backtest_timeout_s)
        summary = json.loads(out_path.read_text()) if out_path.is_file() else None
        return {"exit_code": code, "summary": summary, "result_path": str(out_path) if summary else None, "stderr": redact(e)[-400:], "authority": "candidate evidence only; promotion stays owner-signed"}

    def cmd_vekl(a: dict) -> dict:
        body = json.dumps({"instruction": str(a.get("instruction", "")), "affected_paths": list(a.get("affected_paths", [])), "requested_by": "commander"}).encode()
        try:
            req = Request(st.vekl_url + "/resolve", data=body, method="POST", headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {st.vekl_token}"} if st.vekl_token else {})})
            with urlopen(req, timeout=15) as r:  # noqa: S310
                return json.loads(r.read())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"trading VEKL unavailable: {str(exc)[:200]}")

    def cmd_halt(a: dict) -> dict:
        sig = str(a.get("owner_signature_ref", "")).strip()
        if not sig:
            raise HTTPException(403, "owner-signed authority (A4) required: owner_signature_ref is empty")
        from vati.core.events import EventKind, make_event
        led = ledger()
        try:
            now = int(time.time() * 1000)
            ev = make_event(EventKind.KILL_SWITCH, "van-commander", {"trigger": "OWNER_HALT", "sig": sig, "reason": str(a.get("reason", ""))[:300], "channel": "commander"}, event_time_ms=now, received_time_ms=now, correlation_id="owner")
            chain = led.append(ev)
        finally:
            led.close()
        return {"halted": True, "event_hash": ev.hash, "chain_hash": chain, "note": "sessions observe OWNER_HALT on their next loop and stop new orders; open positions keep their venue stops"}

    def cmd_doctor(a: dict) -> dict:
        du = shutil.disk_usage(st.data_dir if Path(st.data_dir).exists() else "/")
        _, node, _ = st.runner(["node", "--version"], 5)
        checks = {"python": platform.python_version(), "node": node.strip() or "missing", "disk_free_gb": round(du.free / 1e9, 2), "ledger": st.ledger.split("@")[-1] if st.ledger.startswith("postgres") else st.ledger,
                  "vekl": vekl_get("/health").get("ok", False), "heartbeats": [{"file": h.get("file"), "status": h.get("status"), "age_s": h.get("age_s")} for h in heartbeats()], "units": units_state()}
        secrets_dir = Path(st.token_file).parent
        bad = []
        if secrets_dir.is_dir():
            for p in secrets_dir.iterdir():
                if p.is_file() and stat.S_IMODE(p.stat().st_mode) & 0o077:
                    bad.append(p.name)
        checks["secret_files_with_loose_mode"] = bad
        try:
            led = ledger(); checks["ledger_reachable"] = True; checks["ledger_events"] = led.count(); led.close()
        except Exception as exc:  # noqa: BLE001
            checks["ledger_reachable"] = False; checks["ledger_error"] = str(exc)[:200]
        checks["ok"] = checks["ledger_reachable"] and not bad and du.free > 2e9
        return checks

    def cmd_accounts(a: dict) -> dict:
        from vati.accounts import AccountRegistry
        p = Path(st.accounts_registry)
        if not p.is_file():
            return {"accounts": [], "registry": str(p), "note": "no registry yet: add one with `python -m vati accounts add`"}
        return {"accounts": AccountRegistry(p).public(), "registry": str(p)}

    handlers = {"status": cmd_status, "ledger_status": cmd_ledger_status, "services": cmd_services, "restart_service": cmd_restart, "tail_log": cmd_tail, "run_backtest": cmd_backtest,
                "vekl_resolve": cmd_vekl, "halt": cmd_halt, "doctor": cmd_doctor, "accounts": cmd_accounts,
                **build_account_handlers(st.account_control or AccountControlSettings(registry_path=st.accounts_registry, secrets_dir=st.secrets_dir))}
    assert set(handlers) == set(COMMANDS) == set(TOOL_SCHEMAS)

    # ------------------------------------------------------------ routes
    @app.get("/health")
    async def health():
        return {"ok": True, "service": "van-trading-commander", "commands": list(COMMANDS), "uptime_s": int(time.time() - started)}

    @app.get("/v1/tools")
    async def tools(request: FastRequest):
        ok, why = verify_request(st.load_token(), request.headers, "GET", "/v1/tools", b"", nonces=nonces)
        if not ok:
            raise HTTPException(401, why)
        return {"tools": [{"name": n, "description": s["description"], "inputSchema": {"type": "object", "properties": s["properties"], "required": s.get("required", [])}} for n, s in TOOL_SCHEMAS.items()]}

    @app.post("/v1/cmd/{name}")
    async def command(name: str, request: FastRequest):
        body = await request.body()
        ok, why = verify_request(st.load_token(), request.headers, "POST", f"/v1/cmd/{name}", body, nonces=nonces)
        if not ok:
            raise HTTPException(401, why)
        if name not in handlers:
            raise HTTPException(404, f"unknown command {name}; this is not a shell")
        try:
            parsed = CmdBody.model_validate_json(body or b"{}")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, str(exc)[:200])
        try:
            result = handlers[name](parsed.args)
        except HTTPException as exc:
            audit(name, parsed.requested_by, parsed.args, f"refused:{exc.detail}")
            raise
        audit(name, parsed.requested_by, parsed.args, "ok")
        return JSONResponse({"command": name, "result": result})

    return app


app = create_app() if os.environ.get("VAN_COMMANDER_AUTOCREATE") == "1" else None
