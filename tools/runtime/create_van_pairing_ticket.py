#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def env_value(path: Path, name: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return ""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create a one-time VAN Android pairing ticket")
    p.add_argument("--label", default="owner-android")
    p.add_argument("--ttl-seconds", type=int, default=600)
    p.add_argument("--gateway-url", default="")
    p.add_argument("--output", default="~/.local/state/van/pairing-ticket.json")
    return p


def main() -> int:
    args = parser().parse_args()
    if not 60 <= args.ttl_seconds <= 3600:
        raise SystemExit("ttl_seconds_must_be_60_to_3600")
    config_root = Path(os.environ.get("VAN_CONFIG_ROOT", "~/.config/van")).expanduser()
    gateway_env = config_root / "gateway.env"
    public_env = config_root / "public-gateway.env"
    internal = env_value(gateway_env, "VAN_INTERNAL_CONTROL_TOKEN")
    if not internal:
        raise SystemExit("internal_control_token_missing")

    gateway_url = args.gateway_url.strip() or env_value(public_env, "VAN_PUBLIC_GATEWAY_URL")
    gateway_url = gateway_url.rstrip("/")
    if not gateway_url.startswith("https://") or "trycloudflare.com" in gateway_url:
        raise SystemExit("stable_https_gateway_url_required")

    body = json.dumps({"label": args.label, "ttl_seconds": args.ttl_seconds}).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:8787/v1/devices/pairing-ticket",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Van-Internal-Token": internal,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"pairing_ticket_http_{exc.code}") from exc
    pairing_token = str(payload.get("pairing_token", "")).strip()
    expires_at = int(payload.get("expires_at_unix", 0))
    if len(pairing_token) < 32 or expires_at <= 0:
        raise SystemExit("pairing_ticket_response_invalid")

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(output.parent, 0o700)
    temp = output.with_name(output.name + ".tmp")
    temp.write_text(
        json.dumps(
            {
                "gateway_url": gateway_url,
                "pairing_token": pairing_token,
                "expires_at_unix": expires_at,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(temp, 0o600)
    temp.replace(output)
    os.chmod(output, 0o600)
    print(f"pairing_file={output}")
    print(f"expires_at_unix={expires_at}")
    print("contains_secret=yes (owner-only file; delete after pairing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
