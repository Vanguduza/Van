from __future__ import annotations

import ast
import configparser
import importlib.util
from pathlib import Path
from types import SimpleNamespace

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


def test_harness_unit_allows_only_chromium_sandbox_namespaces():
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(UNIT, encoding="utf-8")
    service = unit["Service"]
    assert set(service["RestrictNamespaces"].split()) == {"user", "pid", "net"}
    assert service.getboolean("NoNewPrivileges") is True
    assert service["CapabilityBoundingSet"] == ""
    assert service["ProtectSystem"] == "strict"
    assert service.getboolean("ProtectHome") is True


def test_chromium_launch_keeps_writable_xdg_paths_inside_each_profile(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("van_harness_launch_test", SERVICE)
    assert spec is not None and spec.loader is not None
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    executable = tmp_path / "chromium"
    executable.write_text("launch fixture", encoding="utf-8")
    monkeypatch.setattr(worker, "CHROMIUM", str(executable))
    monkeypatch.setattr(worker, "PROFILE_ROOT", tmp_path / "profiles")
    monkeypatch.setattr(worker, "RUNTIME_ROOT", tmp_path / "runtime")
    original_home = worker.os.environ.get("HOME")
    launches = []

    def launch(argv, **kwargs):
        profile_arg = next(value for value in argv if value.startswith("--user-data-dir="))
        profile = Path(profile_arg.split("=", 1)[1])
        (profile / "DevToolsActivePort").write_text("9222\n/devtools/browser/test\n", encoding="utf-8")
        launches.append((argv, kwargs))
        return SimpleNamespace(pid=12345, poll=lambda: None)

    monkeypatch.setattr(worker.subprocess, "Popen", launch)
    profile_paths = []
    for alias in ("public_research", "authenticated_owner"):
        session = worker.ChromeSession(alias)
        assert session.ensure() == "http://127.0.0.1:9222"
        argv, kwargs = launches[-1]
        environment = kwargs["env"]
        assert environment.get("HOME") == original_home
        for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            directory = Path(environment[key])
            assert directory.is_relative_to(session.profile_dir)
            assert directory.is_dir()
            assert directory.stat().st_mode & 0o777 == 0o700
        cache = Path(environment["XDG_CACHE_HOME"])
        assert cache.is_relative_to(session.runtime_dir)
        assert cache.is_dir()
        assert cache.stat().st_mode & 0o777 == 0o700
        assert not {
            "--no-sandbox",
            "--disable-namespace-sandbox",
            "--disable-seccomp-filter-sandbox",
        }.intersection(argv)
        profile_paths.append({environment[key] for key in (
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"
        )})
    assert profile_paths[0].isdisjoint(profile_paths[1])
    assert len(launches) == 2


def test_bootstrap_pins_and_health_checks_harness_worker():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "browser-harness==0.1.13" in text
    assert "pillow==12.3.0" in text
    assert "pillow==12.2.0" not in text
    assert "vati-browser-harness.service" in text
    assert "systemctl reset-failed vati-browser-harness.service vati-stagehand.service" in text
    assert "install -d -o van-browser -g van-browser -m 0750 /var/lib/van-trading/browser" in text
    assert "install -d -o van-browser -g van-browser -m 0750 /var/lib/van-trading/evidence/browser" in text
    assert "127.0.0.1:${VAN_HARNESS_PORT:-9141}/health" in text
    assert "BROWSER_HARNESS_RUNTIME_GREEN" in text


def test_bootstrap_grants_only_browser_worker_parent_traverse_access():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "setfacl -m u:van-browser:--x" in text
    assert "apt-get install -y -qq --no-install-recommends acl" in text
    assert "/var/lib/van-trading/evidence/browser" in text
    assert "/var/log/van-trading/browser" in text
    assert "chmod 0711 /var/lib/van-trading" not in text
    assert "chmod 0755 /var/lib/van-trading" not in text


def test_stagehand_readiness_window_allows_cold_arm64_import():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    marker = "systemctl restart vati-stagehand.service"
    tail = text[text.index(marker):]
    assert "for attempt in $(seq 1 15); do" in tail
    assert 'if [[ "$attempt" == 15 ]]; then' in tail


def test_bootstrap_keeps_chromium_sandbox_and_scopes_userns_to_exact_binary():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "APPARMOR_PROFILE=/etc/apparmor.d/van-browser-playwright-chromium" in text
    assert "profile van-browser-playwright-chromium $chromium_path flags=(unconfined)" in text
    assert "userns," in text
    assert 'apparmor_parser -r "$APPARMOR_PROFILE"' in text
    assert "--no-sandbox" not in text
    assert "apparmor_restrict_unprivileged_userns=0" not in text


def test_playwright_chromium_allowlisted_binary_is_runtime_immutable():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'chown -R van-browser:van-browser "$BASE/browsers"' in text
    assert 'chown -R root:van-browser "$BASE/browsers"' in text
    assert 'chmod -R u=rwX,g=rX,o= "$BASE/browsers"' in text
    assert '"$(stat -c \'%U:%G\' "$chromium_path")" == "root:van-browser"' in text
    assert text.index('chown -R root:van-browser "$BASE/browsers"') < text.index('APPARMOR_PROFILE=/etc/apparmor.d/van-browser-playwright-chromium')
