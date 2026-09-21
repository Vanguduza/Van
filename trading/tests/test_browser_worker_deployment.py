from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy/van-trading-core/browser/harness_service.py"
BOOTSTRAP = ROOT / "deploy/van-trading-core/browser/bootstrap-browser-runtime.sh"
UNIT = ROOT / "deploy/van-trading-core/systemd/vati-browser-harness.service"
ADAPTER = ROOT / "backend/van_gateway/browser/adapters.py"


def test_harness_worker_is_real_python_and_has_fixed_surface():
    text = SERVICE.read_text(encoding="utf-8")
    ast.parse(text)
    for route in (
        '"/navigate"',
        '"/page_info"',
        '"/click"',
        '"/fill"',
        '"/press"',
        '"/scroll"',
        '"/screenshot"',
        '"/wait"',
        '"/upload"',
        '"/tabs"',
    ):
        assert route in text
    assert '"/js"' not in text
    assert '"/cdp"' not in text
    assert '"/exec"' not in text
    assert '"/shell"' not in text


def test_harness_worker_fails_closed_on_scope_and_helper_authoring():
    text = SERVICE.read_text(encoding="utf-8")
    assert "browser harness worker refuses a non-loopback bind" in text
    assert "URL_OUTSIDE_TASK_DOMAIN" in text
    assert 'body.get("mode") != "PRODUCTION_ACTUATOR"' in text
    assert 'body.get("allow_helper_authoring") is not False' in text
    assert "HELPER_AUTHORING_FORBIDDEN" in text
    assert "SECRET_REFERENCE_REQUIRED" in text
    assert "UPLOAD_FILE_REFERENCE_REQUIRED" in text


def test_gateway_passes_task_domain_and_secret_reference_not_value():
    text = ADAPTER.read_text(encoding="utf-8")
    assert '"target_domain": task.target_domain' in text
    assert "browser_fill_requires_secret_reference" in text
    assert "value_ref=value_ref" in text
    assert "allow_helper_authoring" in text


def test_harness_systemd_identity_is_bounded():
    text = UNIT.read_text(encoding="utf-8")
    assert "User=van-browser" in text
    assert "NoNewPrivileges=true" in text
    assert "ProtectSystem=strict" in text
    assert "CapabilityBoundingSet=" in text
    assert "EnvironmentFile=/opt/van-trading/config/browser-runtime.env" in text


def test_bootstrap_pins_and_health_checks_harness_worker():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "browser-harness==0.1.13" in text
    assert "vati-browser-harness.service" in text
    assert "127.0.0.1:${VAN_HARNESS_PORT:-9141}/health" in text
    assert "BROWSER_HARNESS_RUNTIME_GREEN" in text
