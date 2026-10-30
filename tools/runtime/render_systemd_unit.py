#!/usr/bin/env python3
"""Render VAN's unit templates for the installer-selected local paths, without secrets."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def quote(value: str, *, command: bool = False) -> str:
    """A systemd quoted item, with literal specifiers and ExecStart dollar characters."""
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("unit paths must not contain control characters")
    value = value.replace("%", "%%")
    if command:
        value = value.replace("$", "$$")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def single_path(path: Path) -> str:
    """WorkingDirectory/EnvironmentFile take literal paths, without list quotation."""
    value = str(path)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("unit paths must not contain control characters")
    return value.replace("%", "%%")


def environment_path(path: Path) -> str:
    # EnvironmentFile is passed through glob(3), even when the caller selected
    # one literal file. Escape its metacharacters and literal backslashes.
    return "".join("\\" + character if character in "\\*?[" else character
                   for character in single_path(path))


def render(service: str, *, home: Path, state_root: Path, config_root: Path,
           cloudflared: Path | None = None, python: Path | None = None) -> str:
    home, state_root, config_root = (path.expanduser().resolve() for path in (home, state_root, config_root))
    if service == "gateway":
        backend = state_root / "runtime/backend"
        selected_python = (python or state_root / "venv/bin/python").expanduser()
        # venv/bin/python commonly links to the system interpreter. Preserve that
        # entry point: resolving the final symlink would bypass pyvenv.cfg.
        interpreter = selected_python.parent.resolve() / selected_python.name
        changes = {
            "WorkingDirectory=%h/.local/share/van/runtime/backend": f"WorkingDirectory={single_path(backend)}",
            "Environment=PYTHONPATH=%h/.local/share/van/runtime/backend:%h/.local/share/van/runtime": f"Environment={quote('PYTHONPATH=' + str(backend) + ':' + str(backend.parent))}",
            "EnvironmentFile=%h/.config/van/google-workspace.env": f"EnvironmentFile={environment_path(config_root / 'google-workspace.env')}",
            "EnvironmentFile=%h/.config/van/gateway.env": f"EnvironmentFile={environment_path(config_root / 'gateway.env')}",
            "EnvironmentFile=-%h/.config/van/owner-core.env": f"EnvironmentFile=-{environment_path(config_root / 'owner-core.env')}",
            "EnvironmentFile=-%h/.config/van/trading-commander.env": f"EnvironmentFile=-{environment_path(config_root / 'trading-commander.env')}",
            "ExecStart=%h/.local/share/van/venv/bin/python -m van_gateway.mtls.serve":
                "ExecStart=/bin/sh -c 'exec \"$$0\" -m van_gateway.mtls.serve' "
                f"{quote(str(interpreter), command=True)}",
            "ReadWritePaths=%h/.local/share/van %h/.local/state/van":
                f"ReadWritePaths={quote(str(state_root))} {quote(str(home / '.local/state/van'))}",
        }
        filename = "van-gateway.service"
    elif service == "tunnel":
        if cloudflared is None:
            raise ValueError("the tunnel unit requires its selected cloudflared executable")
        token = config_root / "cloudflare-tunnel.token"
        changes = {
            "ExecStart=%h/bin/cloudflared tunnel --no-autoupdate run --token-file %h/.config/van/cloudflare-tunnel.token":
                "ExecStart=/bin/sh -c 'exec \"$$0\" tunnel --no-autoupdate run --token-file \"$$1\"' "
                f"{quote(str(cloudflared.expanduser().resolve()), command=True)} {quote(str(token), command=True)}",
            "ReadOnlyPaths=%h/.config/van/cloudflare-tunnel.token": f"ReadOnlyPaths={quote(str(token))}",
        }
        filename = "van-cloudflare-tunnel.service"
    else:
        raise ValueError(f"unknown unit kind: {service}")
    lines = (ROOT / "deploy/systemd" / filename).read_text(encoding="utf-8").splitlines()
    missing = set(changes) - set(lines)
    if missing:
        raise ValueError("the unit template's path directives changed; rendering must be updated")
    return "\n".join(changes.get(line, line) for line in lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=("gateway", "tunnel"), required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--cloudflared", type=Path)
    parser.add_argument("--python", type=Path, help="immutable dependency-environment interpreter for the gateway")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = render(args.service, home=args.home, state_root=args.state_root,
                  config_root=args.config_root, cloudflared=args.cloudflared, python=args.python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".van-unit-", dir=args.output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            os.fchmod(file.fileno(), 0o644)
            file.write(text)
        os.replace(temporary, args.output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    main()
