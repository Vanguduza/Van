"""Run the installers against isolated paths with service and HTTP effects mocked."""

import os
from pathlib import Path
import subprocess
import sys
import shutil
import hashlib

import pytest

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[2]


def _executable(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    path.chmod(0o755)


def _fixture(tmp_path):
    home = tmp_path / "home"
    state = tmp_path / 'state % $ colon: " quote \\ space'
    config = tmp_path / 'config % $ colon: " quote \\ space'
    bin_dir = tmp_path / "mock-bin"
    config.mkdir()
    home.mkdir()
    google = f"VAN_GOOGLE_TOKEN_FERNET_KEY={Fernet.generate_key().decode()}\n"
    gateway = (f"VAN_DATABASE_PATH={tmp_path}/gateway.sqlite3\nVAN_HERMES_BASE_URL=http://hermes.invalid\n"
               f"VAN_DEVICE_SECRET_FERNET_KEY={Fernet.generate_key().decode()}\n"
               "VAN_INGRESS_TOKEN=synthetic-install-ingress-0123456789abcdef\n")
    (config / "google-workspace.env").write_text(google)
    (config / "gateway.env").write_text(gateway)
    mock = tmp_path / "mock-python.py"
    mock.write_text("""
import os, sys, urllib.request
from pathlib import Path
if sys.argv[1:3] == ['-m', 'pip']:
    if os.environ.get('INSTALLER_TEST_PIP_FAIL') == '1':
        raise SystemExit(1)
    raise SystemExit(0)
if sys.argv[1:3] == ['-m', 'venv']:
    target = Path(sys.argv[3]) / 'bin/python'
    target.parent.mkdir(parents=True)
    target.write_text('#!/bin/sh\\nexec "' + sys.executable + '" "' + __file__ + '" "$@"\\n')
    target.chmod(0o755)
    raise SystemExit(0)
if sys.argv[1:] == ['-']:
    sys.path.insert(0, os.getcwd())
    source = sys.stdin.read()
    if 'urllib.request' in source:
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
        urllib.request.urlopen = lambda *args, **kwargs: Response()
        urllib.request.OpenerDirector.open = lambda *args, **kwargs: Response()
    exec(compile(source, '<installer>', 'exec'), {'__name__': '__main__'})
else:
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
""")
    wrapper = f'#!/bin/sh\nexec "{sys.executable}" "{mock}" "$@"\n'
    _executable(bin_dir / "python3", wrapper)
    _executable(state / "venv/bin/python", wrapper)
    _executable(bin_dir / "systemctl", "#!/bin/sh\nexit 0\n")
    cloudflared = tmp_path / 'cloudflared % $ " \\ bin'
    _executable(cloudflared, "#!/bin/sh\nexit 0\n")
    env = {**os.environ, "HOME": str(home), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
           "VAN_STATE_ROOT": str(state), "VAN_CONFIG_ROOT": str(config),
           "VAN_CLOUDFLARED_BIN": str(cloudflared)}
    env.pop("VAN_INSTALL_STAGE_ONLY", None)
    return home, state, config, cloudflared, env, google, gateway


def _run(script, env):
    result = subprocess.run(["bash", str(ROOT / "tools/runtime" / script)], env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _quoted(path, *, command=False):
    value = str(path).replace("%", "%%")
    if command:
        value = value.replace("$", "$$")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _environment_path(path):
    return "".join("\\" + character if character in "\\*?[" else character
                   for character in str(path).replace("%", "%%"))


def test_gateway_full_install_selects_overrides_and_preserves_configuration_on_repeat(tmp_path):
    home, state, config, _, env, google, gateway = _fixture(tmp_path)
    _run("install_van_gateway_service.sh", env)
    path = home / ".config/systemd/user/van-gateway.service"
    unit = path.read_text()
    assert f"WorkingDirectory={str(state / 'runtime/backend').replace('%', '%%')}" in unit
    assert f"EnvironmentFile={_environment_path(config / 'gateway.env')}" in unit
    assert f"EnvironmentFile=-{_environment_path(config / 'trading-commander.env')}" in unit
    lock = hashlib.sha256((ROOT / 'backend/requirements.lock').read_bytes()).hexdigest()
    interpreter = state / 'venvs' / lock / 'bin/python'
    assert "ExecStart=/bin/sh -c 'exec \"$$0\" -m van_gateway.mtls.serve' " + _quoted(interpreter, command=True) in unit
    assert f"ReadWritePaths={_quoted(state)}" in unit
    assert "%h/.local/share/van" not in unit
    assert (state / "runtime/backend/van_gateway/app.py").is_file()
    assert (state / "runtime/services/browser_control_agent/client.py").is_file()
    _run("install_van_gateway_service.sh", env)
    assert path.read_text() == unit
    assert (config / "google-workspace.env").read_text() == google
    assert (config / "gateway.env").read_text() == gateway


def test_dependency_failure_preserves_serving_runtime_interpreter_and_unit(tmp_path):
    home, state, config, _, env, _, _ = _fixture(tmp_path)
    old = state / "runtime"
    old.mkdir()
    (old / "serving-marker").write_text("owner runtime still selected")
    unit = home / ".config/systemd/user/van-gateway.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("serving unit unchanged")
    interpreter = state / "venv/bin/python"
    before = interpreter.read_bytes()
    result = subprocess.run(["bash", str(ROOT / "tools/runtime/install_van_gateway_service.sh")],
                            env={**env, "INSTALLER_TEST_PIP_FAIL": "1"}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 4, result.stdout + result.stderr
    assert "serving interpreter unchanged" in result.stderr
    assert interpreter.read_bytes() == before
    assert (old / "serving-marker").read_text() == "owner runtime still selected"
    assert unit.read_text() == "serving unit unchanged"
    assert not (state / "runtime.previous").exists()
    assert not list((state / "venvs").iterdir())


def test_tunnel_full_install_uses_selected_binary_and_token_file_without_copying_token(tmp_path):
    home, _, config, cloudflared, env, google, gateway = _fixture(tmp_path)
    token = "synthetic-named-tunnel-token"
    (config / "cloudflare-tunnel.token").write_text(token)
    (config / "public-gateway.env").write_text("VAN_PUBLIC_GATEWAY_URL=https://gateway.invalid\n")
    _run("install_van_cloudflare_tunnel.sh", env)
    path = home / ".config/systemd/user/van-cloudflare-tunnel.service"
    unit = path.read_text()
    assert "ExecStart=/bin/sh -c 'exec \"$$0\" tunnel --no-autoupdate run --token-file \"$$1\"' " + _quoted(cloudflared, command=True) in unit
    assert _quoted(config / 'cloudflare-tunnel.token', command=True) in unit
    assert f"ReadOnlyPaths={_quoted(config / 'cloudflare-tunnel.token')}" in unit
    assert token not in unit
    _run("install_van_cloudflare_tunnel.sh", env)
    assert path.read_text() == unit
    assert (config / "cloudflare-tunnel.token").read_text() == token
    assert (config / "google-workspace.env").read_text() == google
    assert (config / "gateway.env").read_text() == gateway


def test_default_gateway_roots_still_match_the_default_home(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("van_unit_renderer", ROOT / "tools/runtime/render_systemd_unit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    unit = module.render("gateway", home=tmp_path, state_root=tmp_path / ".local/share/van",
                         config_root=tmp_path / ".config/van")
    assert f"WorkingDirectory={tmp_path / '.local/share/van/runtime/backend'}" in unit
    assert f"EnvironmentFile={tmp_path / '.config/van/gateway.env'}" in unit


def test_unit_renderer_rejects_path_control_character_injection(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "tools/runtime/render_systemd_unit.py"),
                             "--service", "gateway", "--home", str(tmp_path),
                             "--state-root", str(tmp_path / "state\nExecStart=bad"),
                             "--config-root", str(tmp_path / "config"), "--output", str(tmp_path / "unit")],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert not (tmp_path / "unit").exists()


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="the systemd parser is not installed")
def test_systemd_accepts_special_paths_without_ignoring_environment_files(tmp_path):
    home, _, config, _, env, _, _ = _fixture(tmp_path)
    (config / "cloudflare-tunnel.token").write_text("synthetic-tunnel-token")
    (config / "public-gateway.env").write_text("VAN_PUBLIC_GATEWAY_URL=https://gateway.invalid\n")
    _run("install_van_gateway_service.sh", env)
    _run("install_van_cloudflare_tunnel.sh", env)
    directory = home / ".config/systemd/user"
    result = subprocess.run(["systemd-analyze", "verify", "--man=no",
                             str(directory / "van-gateway.service"),
                             str(directory / "van-cloudflare-tunnel.service")],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ignoring" not in result.stderr.lower(), result.stderr
    assert "not absolute" not in result.stderr.lower(), result.stderr


@pytest.mark.skipif(shutil.which("cc") is None, reason="native glob verification needs a C compiler")
def test_environment_file_glob_resolves_the_selected_literal_special_path(tmp_path):
    home, _, config, _, env, _, _ = _fixture(tmp_path)
    _run("install_van_gateway_service.sh", env)
    source = tmp_path / "glob.c"
    source.write_text('#include <glob.h>\n#include <stdio.h>\n'
                      'int main(int argc, char **argv) { glob_t g = {0}; '
                      'int r = glob(argv[1], 0, NULL, &g); '
                      'if (r || g.gl_pathc != 1) return 1; '
                      'puts(g.gl_pathv[0]); globfree(&g); return 0; }\n')
    binary = tmp_path / "glob-probe"
    subprocess.run(["cc", str(source), "-o", str(binary)], check=True, capture_output=True)
    unit = (home / ".config/systemd/user/van-gateway.service").read_text()
    pattern = next(line.split("=", 1)[1] for line in unit.splitlines()
                   if line.startswith("EnvironmentFile=") and line.endswith("/gateway.env"))
    # systemd resolves specifiers before applying the C library's glob operation.
    result = subprocess.run([str(binary), pattern.replace("%%", "%")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(config / "gateway.env")
