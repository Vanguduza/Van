#!/usr/bin/env python3
"""Provision VAN's permanent Google Workspace OAuth credential plane.

This helper is deliberately split into explicit phases:

1. ```install-client``` validates and stores a downloaded *Desktop app* OAuth
   client JSON with owner-only permissions.
2. ```prepare``` creates an RFC 7636 PKCE authorization request and prints only
   the Google consent URL. The verifier/state are kept in an owner-only local
   state file; no OAuth secret enters a prompt or repository.
3. ```exchange``` accepts the browser's final loopback URL, validates the state,
   exchanges the short-lived code, encrypts the returned refresh token into
   VAN's SQLite vault, and stores only runtime client configuration in an
   owner-only environment file.
4. ```certify``` performs token-safe, metadata-only API canaries and upgrades the
   ```workspace_api``` capability to READY only when all required APIs answer.

The browser running the consent flow does not need a loopback listener. A
Desktop OAuth client redirects to the loopback URL; the browser reports that
127.0.0.1 refused the connection, copy that final URL and pass it to
```exchange```. The authorization code is short-lived and is not persisted.

"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from van_gateway.google.mesh import (
    GoogleCapabilityRegistry,
    GoogleCapabilityState,
    GoogleIdentityBroker,
)
from van_gateway.google.service import GoogleService, NARROW_SCOPES
from van_gateway.google.transport import GoogleOAuthTokenClient
from van_gateway.storage.db import Store

DEFAULT_CLIENT_PATH = Path.home() / ".local" / "share" / "van" / "google-workspace-oauth-client.json"
DEFAULT_COMPAT_CLIENT_PATH = Path.home() / ".hermes" / "google_client_secret.json"
DEFAULT_PENDING_PATH = Path.home() / ".local" / "state" / "van" / "google-workspace-oauth-pending.json"
DEFAULT_ENV_PATH = Path.home() / ".config" / "van" / "google-workspace.env"
DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "van" / "van_gateway.sqlite3"
DEFAULT_RECEIPT_PATH = Path.home() / ".local" / "state" / "van" / "google-workspace-live-receipt.json"
DEFAULT_PROJECT_ID = "gen-lang-client-0177797379"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
MAX_PENDING_AGE_SECONDS = 15 * 60


def _secure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)


def _write_private(path: Path, text: str) -> None:
    _secure_parent(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _load_client(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"oauth_client_missing:{path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit("oauth_client_invalid_json") from exc
    installed = raw.get("installed")
    if not isinstance(installed, dict):
        raise SystemExit("oauth_client_not_desktop_app")
    client_id = str(installed.get("client_id") or "").strip()
    client_secret = str(installed.get("client_secret") or "").strip()
    auth_uri = str(installed.get("auth_uri") or AUTH_ENDPOINT).strip()
    token_uri = str(installed.get("token_uri") or TOKEN_ENDPOINT).strip()
    if not client_id or not client_secret:
        raise SystemExit("oauth_client_missing_id_or_secret")
    if "accounts.google.com" not in auth_uri or "oauth2.googleapis.com" not in token_uri:
        raise SystemExit("oauth_client_unexpected_google_endpoints")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": auth_uri,
        "token_uri": token_uri,
    }


def install_client(source: Path, target: Path, compat: Path) -> None:
    _load_client(source)
    _secure_parent(target)
    shutil.copyfile(source, target)
    os.chmod(target, 0o600)

    # Compatibility location expected by earlier Hermes-side diagnostics. Keep
    # one canonical file; the compatibility path is a symlink, not a copy.
    compat.parent.mkdir(parents=True, exist_ok=True)
    try:
        if compat.exists() or compat.is_symlink():
            compat.unlink()
        compat.symlink_to(target)
    except OSError:
        shutil.copyfile(target, compat)
        os.chmod(compat, 0o600)

    print(f"client_installed={target}")
    print(f"compat_client={compat}")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def prepare(client_path: Path, pending_path: Path, port: int) -> None:
    client = _load_client(client_path)
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    redirect_uri = f"http://127.0.0.1:{port}/"
    pending = {
        "schema_version": 1,
        "created_at_unix": int(time.time()),
        "client_path": str(client_path),
        "state": state,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "scopes": list(NARROW_SCOPES),
    }
    _write_private(pending_path, json.dumps(pending, indent=2) + "\n")

    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(NARROW_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    print("Open this URL in the browser signed into the owner Google account:")
    print(f"{AUTH_ENDPOINT}?{urlencode(params)}")
    print()
    print("After consent, the browser may show 127.0.0.1 refused to connect.")
    print("Copy the COMPLETE final browser URL and use it with the exchange phase.")
    print(f"pending_state={pending_path}")


def _read_pending(path: Path) -> dict[str, Any]:
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit("oauth_pending_state_missing") from exc
    created = int(pending.get("created_at_unix") or 0)
    if created <= 0 or int(time.time()) - created > MAX_PENDING_AGE_SECONDS:
        raise SystemExit("oauth_pending_state_expired; run prepare again")
    return pending


def _parse_callback(callback_url: str, expected_redirect: str, expected_state: str) -> str:
    parsed = urlparse(callback_url.strip())
    expected = urlparse(expected_redirect)
    if parsed.scheme != expected.scheme or parsed.hostname != expected.hostname or parsed.port != expected.port:
        raise SystemExit("oauth_callback_redirect_mismatch")
    query = parse_qs(parsed.query)
    if query.get("error"):
        raise SystemExit(f"oauth_consent_error:{query['error'][0]}")
    state = (query.get("state") or [""])[0]
    if not state or not secrets.compare_digest(state, expected_state):
        raise SystemExit("oauth_state_mismatch")
    code = (query.get("code") or [""])[0]
    if not code:
        raise SystemExit("oauth_code_missing")
    return code


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _write_runtime_env(
    path: Path,
    *,
    fernet_key: str,
    client_id: str,
    client_secret: str,
    db_path: Path,
    project_id: str,
) -> None:
    lines = [
        "# VAN Google Workspace OAuth runtime configuration.",
        "# Owner-only; generated by authorize_workspace_oauth.py.",
        f"VAN_DATABASE_PATH={db_path}",
        f"VAN_GOOGLE_TOKEN_FERNET_KEY={fernet_key}",
        f"VAN_GOOGLE_OAUTH_CLIENT_ID={client_id}",
        f"VAN_GOOGLE_OAUTH_CLIENT_SECRET={client_secret}",
        f"VAN_GOOGLE_CLOUD_PROJECT_ID={project_id}",
        "",
    ]
    _write_private(path, "\n".join(lines))


async def _exchange(
    callback_url: str,
    pending_path: Path,
    env_path: Path,
    db_path: Path,
    receipt_path: Path,
    project_id: str,
) -> None:
    pending = _read_pending(pending_path)
    client_path = Path(str(pending["client_path"]))
    client = _load_client(client_path)
    code = _parse_callback(
        callback_url,
        str(pending["redirect_uri"]),
        str(pending["state"]),
    )
    data = {
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "code": code,
        "code_verifier": pending["code_verifier"],
        "grant_type": "authorization_code",
        "redirect_uri": pending["redirect_uri"],
    }
    async with httpx.AsyncClient(timeout=30.0) as http:
        response = await http.post(client["token_uri"], data=data, headers={"Accept": "application/json"})
    if response.status_code >= 400:
        raise SystemExit(f"oauth_code_exchange_failed:{response.status_code}")
    token_data = response.json()
    refresh_token = str(token_data.get("refresh_token") or "")
    if not refresh_token:
        raise SystemExit("oauth_refresh_token_missing; run prepare again and approve consent")

    existing = _read_env(env_path)
    fernet_key = existing.get("VAN_GOOGLE_TOKEN_FERNET_KEY") or Fernet.generate_key().decode("ascii")
    _write_runtime_env(
        env_path,
        fernet_key=fernet_key,
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        db_path=db_path,
        project_id=project_id,
    )
    _secure_parent(db_path)
    store = Store(str(db_path))
    await store.migrate()
    service = GoogleService(store, fernet_key)
    await service.store_refresh_token("owner", refresh_token, list(NARROW_SCOPES))
    os.chmod(db_path, 0o600)

    receipt = {
        "schema_version": 1,
        "connected_at_unix": int(time.time()),
        "project_id": project_id,
        "client_id_sha256": hashlib.sha256(client["client_id"].encode("utf-8")).hexdigest(),
        "scopes": list(NARROW_SCOPES),
        "credential_plane": "workspace_oauth",
        "refresh_token_persisted": "encrypted_sqlite",
    }
    _write_private(receipt_path, json.dumps(receipt, indent=2) + "\n")
    try:
        pending_path.unlink()
    except FileNotFoundError:
        pass

    print("workspace_oauth_connected=true")
    print(f"vault={db_path}")
    print(f"runtime_env={env_path}")
    print("refresh_token_storage=encrypted_sqlite")
    print("next=certify")


def _load_required_runtime(env_path: Path) -> dict[str, str]:
    env = _read_env(env_path)
    required = (
        "VAN_GOOGLE_TOKEN_FERNET_KEY",
        "VAN_GOOGLE_OAUTH_CLIENT_ID",
        "VAN_GOOGLE_OAUTH_CLIENT_SECRET",
        "VAN_DATABASE_PATH",
    )
    missing = [k for k in required if not env.get(k)]
    if missing:
        raise SystemExit(f"runtime_env_incomplete:{','.join(missing)}")
    return env


async def _certify(env_path: Path, receipt_path: Path) -> None:
    env = _load_required_runtime(env_path)
    db_path = Path(env["VAN_DATABASE_PATH"])
    store = Store(str(db_path))
    await store.migrate()
    service = GoogleService(store, env["VAN_GOOGLE_TOKEN_FERNET_KEY"])
    refresh = await service._refresh_token("owner")
    oauth = GoogleOAuthTokenClient(
        env["VAN_GOOGLE_OAUTH_CLIENT_ID"],
        env["VAN_GOOGLE_OAUTH_CLIENT_SECRET"],
    )
    try:
        access = await oauth.access_token(refresh)
    except RuntimeError as exc:
        raise SystemExit(f"oauth_refresh_canary_failed:{exc}") from exc

    probes = {
        "gmail": ("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile", None),
        "calendar": ("GET", "https://www.googleapis.com/calendar/v3/users/me/calendarList", {"maxResults": "1"}),
        "drive": ("GET", "https://www.googleapis.com/drive/v3/about", {"fields": "user(permissionId)"}),
        "contacts": ("GET", "https://people.googleapis.com/v1/people/me", {"personFields": "names"}),
        "tasks": ("GET", "https://tasks.googleapis.com/tasks/v1/users/@me/lists", {"maxResults": "1"}),
    }
    results: dict[str, int] = {}
    headers = {"Authorization": f"Bearer {access}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as http:
        for name, (method, url, params) in probes.items():
            response = await http.request(method, url, headers=headers, params=params)
            results[name] = response.status_code

    for name, status in results.items():
        print(f"{name}_http_status={status}")
    failures = {name: status for name, status in results.items() if status < 200 or status >= 300}
    if failures:
        raise SystemExit("workspace_api_canary_failed")

    registry = GoogleCapabilityRegistry(str(ROOT / "registries" / "google_capabilities.json"))
    broker = GoogleIdentityBroker(store, registry)
    await broker.record_capability_evidence(
        "workspace_api",
        state=GoogleCapabilityState.READY,
        evidence_pointer="live://dial-hermes-control/workspace-oauth/canary",
        metadata={
            "source": "authorize_workspace_oauth.py",
            "verified_at_unix": int(time.time()),
            "services": sorted(results),
            "token_material_recorded": False,
        },
        owner_id="owner_google_account",
    )

    prior = {}
    if receipt_path.exists():
        try:
            prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    prior.update(
        {
            "certified_at_unix": int(time.time()),
            "services": {name: "READY" for name in results},
            "workspace_api_state": "READY",
            "evidence_pointer": "live://dial-hermes-control/workspace-oauth/canary",
        }
    )
    _write_private(receipt_path, json.dumps(prior, indent=2) + "\n")
    print("workspace_api_state=READY")
    print(f"receipt={receipt_path}")


async def _status(env_path: Path) -> None:
    env = _read_env(env_path)
    if not env:
        print("runtime_env=missing")
        print("workspace_oauth_connected=false")
        return
    db_value = env.get("VAN_DATABASE_PATH", "")
    fernet = env.get("VAN_GOOGLE_TOKEN_FERNET_KEY", "")
    if not db_value or not fernet:
        print("runtime_env=incomplete")
        print("workspace_oauth_connected=false")
        return
    store = Store(db_value)
    await store.migrate()
    service = GoogleService(store, fernet)
    status = await service.status()
    print(f"workspace_oauth_connected={str(status.connected).lower()}")
    print(f"services={json.dumps(status.services, sort_keys=True)}")
    print(f"degraded={json.dumps(status.degraded)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision and certify VAN Google Workspace OAuth")
    parser.add_argument("--client-path", type=Path, default=DEFAULT_CLIENT_PATH)
    parser.add_argument("--compat-client-path", type=Path, default=DEFAULT_COMPAT_CLIENT_PATH)
    parser.add_argument("--pending-path", type=Path, default=DEFAULT_PENDING_PATH)
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--database-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--receipt-path", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install-client", help="Validate and securely install a Desktop OAuth client JSON")
    install.add_argument("source", type=Path)

    prepare_cmd = sub.add_parser("prepare", help="Create a PKCE consent URL")
    prepare_cmd.add_argument("--port", type=int, default=53682)

    exchange = sub.add_parser("exchange", help="Exchange a final loopback callback URL for an encrypted refresh token")
    exchange.add_argument("callback_url")

    sub.add_parser("certify", help="Run metadata-only live API canaries and mark workspace_api READY")
    sub.add_parser("status", help="Show token-safe Workspace connection status")
    return parser


async def main() -> int:
    args = build_parser().parse_args()
    if args.command == "install-client":
        install_client(args.source, args.client_path, args.compat_client_path)
    elif args.command == "prepare":
        prepare(args.client_path, args.pending_path, args.port)
    elif args.command == "exchange":
        await _exchange(
            args.callback_url,
            args.pending_path,
            args.env_path,
            args.database_path,
            args.receipt_path,
            args.project_id,
        )
    elif args.command == "certify":
        await _certify(args.env_path, args.receipt_path)
    elif args.command == "status":
        await _status(args.env_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
