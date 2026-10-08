"""Programme B, B0 — one Jev.

VAN is a client of the single DDS `dial-jev` service. These tests fail if VAN grows a second
Jev service/daemon, a second Jev endpoint, a Jev ledger, or a Jev-owned browser session.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from van_gateway.browser.interactive_models import BrowserControlHolder
from van_gateway.config import Settings, get_settings

REPO = Path(__file__).resolve().parents[2]
GATEWAY = REPO / "backend" / "van_gateway"
JEV_PKG = GATEWAY / "jev"
ROUTER = GATEWAY / "browser" / "interaction_router.py"

#: Names a second Jev deployment would carry. B0 forbids every one.
SECOND_JEV_NAMES = re.compile(
    r"jev[-_](browser|ultrafast|memory|router|ledger|daemon|worker|chromium)", re.IGNORECASE
)
#: Anything that would make the Jev client a server, a browser, or a process launcher.
FORBIDDEN_IMPORTS = {
    "playwright", "pyppeteer", "selenium", "subprocess", "multiprocessing", "uvicorn",
    "aiosqlite", "sqlite3",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _scanned_files():
    roots = [GATEWAY, REPO / "deploy", REPO / "tools", REPO / "hermes", REPO / "config"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".sh", ".service", ".yaml", ".yml", ".json", ".toml", ".env", ".example", ""}:
                yield path


def test_no_second_jev_service_name_anywhere_in_van():
    offenders = []
    for path in _scanned_files():
        if SECOND_JEV_NAMES.search(path.name):
            offenders.append(str(path.relative_to(REPO)))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if SECOND_JEV_NAMES.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{number}")
    assert offenders == []


def test_no_jev_systemd_unit_or_daemon_ships_in_van():
    units = [p for p in REPO.rglob("*.service") if "jev" in p.name.lower()]
    assert units == [], "the only Jev unit is DDS dial-jev; VAN ships none"


def test_settings_carry_exactly_one_jev_endpoint():
    endpoint_fields = [
        name for name in Settings.model_fields
        if name.startswith("jev_") and re.search(r"(url|host|port|endpoint)$", name)
    ]
    assert endpoint_fields == ["jev_base_url"]


@pytest.mark.parametrize("path", sorted(JEV_PKG.glob("*.py")) + [ROUTER], ids=lambda p: p.name)
def test_jev_client_code_cannot_serve_browse_spawn_or_keep_a_ledger(path):
    bad = {name for name in _imports(path) if name.split(".")[0] in FORBIDDEN_IMPORTS}
    assert bad == set(), f"{path.name} imports {bad}"
    text = path.read_text(encoding="utf-8")
    assert "FastAPI(" not in text
    assert "start_server" not in text
    assert not re.search(r"CREATE\s+TABLE", text, re.IGNORECASE)


def test_no_jev_table_in_the_van_schema():
    storage = (GATEWAY / "storage" / "db.py").read_text(encoding="utf-8")
    assert not re.search(r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?\w*jev", storage, re.IGNORECASE)


def test_jev_never_holds_browser_control():
    """A Jev-owned browser session would need a control holder. There is none."""
    assert not [h for h in BrowserControlHolder if "JEV" in h.value]
    router = ROUTER.read_text(encoding="utf-8")
    # The router checks the lease; it never issues, delegates or preempts one.
    for verb in (".issue(", ".delegate(", ".owner_preempt(", ".revoke("):
        assert verb not in router


def test_router_and_projection_share_the_one_dial_jev(monkeypatch, tmp_path):
    token = tmp_path / "consumer.token"
    token.write_text("t", encoding="utf-8")
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "one.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "internal")
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "internal")
    monkeypatch.setenv("VAN_JEV_ENABLED", "true")
    monkeypatch.setenv("VAN_JEV_BASE_URL", "http://127.0.0.1:6791")
    monkeypatch.setenv("VAN_JEV_CONSUMER_TOKEN_FILE", str(token))
    monkeypatch.setenv("VAN_JEV_PROJECTION_TOKEN_FILE", str(token))
    get_settings.cache_clear()
    try:
        from van_gateway.app import create_app

        app = create_app()
        advisor = app.state.jev_advisor
        # The router's Jev lane is the same advisor object, not a second client.
        assert app.state.interaction_router.jev is advisor
        assert advisor._base_url == app.state.jev_projection.client._base_url == "http://127.0.0.1:6791"
        # And the router's lease model is the interactive session's, not a Jev one.
        assert app.state.interaction_router.leases is app.state.browser_control_leases
        assert app.state.interaction_router.describe()["jev_service"] == "dial-jev"
    finally:
        get_settings.cache_clear()
