#!/usr/bin/env python3
"""ADR-RB-024/026/027 — make the connectivity signing key, and the anchor the APK pins.

Provisioning needs two halves of one key and nothing in the repository produced either:

* the **private key** on the Gateway host (`VAN_CONNECTIVITY_SIGNING_KEY_FILE`), which signs
  provisioning payloads and connectivity manifests. Without it
  `POST /v1/devices/provisioning-payload` answers 503 `connectivity_signing_unconfigured`;
* the **public anchor** compiled into the APK (`VAN_CONNECTIVITY_TRUSTED_KEYS`). Without it a
  debug build refuses every payload and a release build refuses to assemble.

The anchor's format is the part that is easy to get wrong: `kid=PEM` on **one line**, with the
PEM's line breaks written as the two characters `\\n` (`ConnectivityTrustedKeys.parse` splits
entries on real newlines and unescapes `\\n` inside each). A PEM pasted with real line breaks
parses to no key at all, and the phone just waits.

    # on the Gateway host — writes the key with mode 0600 and refuses to overwrite one
    python3 tools/provisioning/generate_connectivity_key.py --out /etc/van/connectivity-1.pem

    # the anchor again, later, from the same key (for the next APK build)
    python3 tools/provisioning/generate_connectivity_key.py --anchor-from /etc/van/connectivity-1.pem

The private key is printed nowhere. Only the public anchor and the two setting names are.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DEFAULT_KID = "connectivity-1"


def generate(out: Path) -> ec.EllipticCurvePrivateKey:
    """Write a new P-256 key (the curve the device's 64-byte r||s signatures assume)."""
    if out.exists():
        raise FileExistsError(f"{out} exists; rotating a pinned key is a new kid, not an overwrite")
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)
    return key


def load(path: Path) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("connectivity key must be an EC P-256 private key")
    return key


def check_kid(kid: str) -> None:
    if not kid or "=" in kid or "\n" in kid:
        raise ValueError("kid must be non-empty and contain no '=' or newline")


def anchor(key: ec.EllipticCurvePrivateKey, kid: str) -> str:
    """The one-line `kid=PEM` entry `VAN_CONNECTIVITY_TRUSTED_KEYS` expects."""
    check_kid(kid)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii").strip()
    return f"{kid}=" + public.replace("\n", "\\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--out", type=Path, help="write a new private key here (mode 0600)")
    source.add_argument("--anchor-from", type=Path, help="print the anchor for an existing key")
    parser.add_argument("--kid", default=DEFAULT_KID, help=f"key id (default {DEFAULT_KID})")
    args = parser.parse_args(argv)

    try:
        # Before anything is written: a refused kid must not leave a key file behind.
        check_kid(args.kid)
        key = generate(args.out) if args.out else load(args.anchor_from)
        line = anchor(key, args.kid)
    except (FileExistsError, ValueError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    path = args.out or args.anchor_from
    print("# Gateway host (.env or the service environment):")
    print(f"VAN_CONNECTIVITY_SIGNING_KEY_FILE={path.resolve()}")
    print(f"VAN_CONNECTIVITY_SIGNING_KID={args.kid}")
    print("# Android build (gradle property or environment), exactly one line:")
    print(f"VAN_CONNECTIVITY_TRUSTED_KEYS={line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
