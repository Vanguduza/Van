from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "google" / "authorize_workspace_oauth.py"
SPEC = importlib.util.spec_from_file_location("authorize_workspace_oauth", TOOL_PATH)
assert SPEC and SPEC.loader
oauth_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oauth_tool)


def desktop_client() -> str:
    return """{
      "installed": {
        "client_id": "desktop-client.apps.googleusercontent.com",
        "project_id": "example",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_secret": "client-secret",
        "redirect_uris": ["http://localhost"]
      }
    }"""


def test_load_client_requires_desktop_shape(tmp_path: Path):
    client = tmp_path / "client.json"
    client.write_text('{"web":{"client_id":"x","client_secret":"y"}}', encoding="utf-8")
    with pytest.raises(SystemExit, match="oauth_client_not_desktop_app"):
        oauth_tool._load_client(client)


def test_install_and_prepare_are_private_and_pkce_scoped(tmp_path: Path, capsys):
    source = tmp_path / "download.json"
    target = tmp_path / "private" / "client.json"
    compat = tmp_path / "compat" / "google_client_secret.json"
    pending = tmp_path / "state" / "pending.json"
    source.write_text(desktop_client(), encoding="utf-8")

    oauth_tool.install_client(source, target, compat)
    assert target.exists()
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert compat.exists() or compat.is_symlink()

    capsys.readouterr()
    oauth_tool.prepare(target, pending, 53682)
    output = capsys.readouterr().out
    url = next(line for line in output.splitlines() if line.startswith("https://accounts.google.com/"))
    params = parse_qs(urlparse(url).query)
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://127.0.0.1:53682/"]
    assert set(params["scope"][0].split()) == set(oauth_tool.NARROW_SCOPES)
    assert oct(pending.stat().st_mode & 0o777) == "0o600"


def test_callback_validation_rejects_state_mismatch():
    with pytest.raises(SystemExit, match="oauth_state_mismatch"):
        oauth_tool._parse_callback(
            "http://127.0.0.1:53682/?code=abc&state=wrong",
            "http://127.0.0.1:53682/",
            "expected",
        )


def test_runtime_env_is_owner_only(tmp_path: Path):
    env_path = tmp_path / "config" / "google-workspace.env"
    db_path = tmp_path / "data" / "van.sqlite3"
    oauth_tool._write_runtime_env(
        env_path,
        fernet_key="fernet-key",
        client_id="client-id",
        client_secret="client-secret",
        db_path=db_path,
        project_id="project-id",
    )
    assert oct(env_path.stat().st_mode & 0o777) == "0o600"
    content = env_path.read_text(encoding="utf-8")
    assert "VAN_GOOGLE_TOKEN_FERNET_KEY=fernet-key" in content
    assert f"VAN_DATABASE_PATH={db_path}" in content
