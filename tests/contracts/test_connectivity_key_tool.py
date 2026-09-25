"""The connectivity key tool produces a key the Gateway signs with and an anchor the APK accepts.

End to end in the repository's own terms: the private key signs a real provisioning payload
with the Gateway's signer, and the anchor line — parsed the way `ConnectivityTrustedKeys.parse`
parses it — verifies that payload with the Gateway's verifier (the device's mirror).
"""

from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "provisioning" / "generate_connectivity_key.py"
sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.connectivity.provisioning import (  # noqa: E402
    build_provisioning_payload,
    sign_provisioning_payload,
    verify_provisioning_payload,
)


def _tool():
    spec = importlib.util.spec_from_file_location("generate_connectivity_key", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_like_the_device(raw: str) -> dict[str, str]:
    """A transcription of ConnectivityTrustedKeys.parse."""
    keys = {}
    for line in raw.split("\n"):
        sep = line.find("=")
        if sep <= 0:
            continue
        kid = line[:sep].strip()
        pem = line[sep + 1:].strip().replace("\\n", "\n")
        if kid and "BEGIN PUBLIC KEY" in pem:
            keys[kid] = pem
    return keys


def test_a_generated_key_signs_a_payload_its_anchor_verifies(tmp_path: Path, capsys) -> None:
    key_file = tmp_path / "etc" / "connectivity-1.pem"
    assert _tool().main(["--out", str(key_file)]) == 0
    printed = capsys.readouterr().out
    assert "PRIVATE KEY" not in printed
    anchor_line = next(l for l in printed.splitlines() if l.startswith("VAN_CONNECTIVITY_TRUSTED_KEYS="))
    anchor = anchor_line.split("=", 1)[1]
    assert "\n" not in anchor

    payload = build_provisioning_payload(
        gateway_url="https://van.example", pairing_token="p" * 40,
        bootstrap_token="b" * 40, attestation_challenge="challenge",
    )
    signature = sign_provisioning_payload(payload, private_pem=key_file.read_text())
    verify_provisioning_payload(
        payload, signature, trusted_keys=_parse_like_the_device(anchor), kid="connectivity-1",
    )


def test_the_private_key_is_owner_only_and_never_overwritten(tmp_path: Path) -> None:
    key_file = tmp_path / "k.pem"
    assert _tool().main(["--out", str(key_file)]) == 0
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    before = key_file.read_bytes()
    assert _tool().main(["--out", str(key_file)]) == 2
    assert key_file.read_bytes() == before


def test_the_anchor_can_be_reprinted_from_the_same_key(tmp_path: Path, capsys) -> None:
    key_file = tmp_path / "k.pem"
    _tool().main(["--out", str(key_file), "--kid", "connectivity-2"])
    first = capsys.readouterr().out.splitlines()[-1]
    _tool().main(["--anchor-from", str(key_file), "--kid", "connectivity-2"])
    assert capsys.readouterr().out.splitlines()[-1] == first
    assert first.startswith("VAN_CONNECTIVITY_TRUSTED_KEYS=connectivity-2=")


@pytest.mark.parametrize("kid", ["", "a=b", "a\nb"])
def test_a_kid_that_would_break_the_anchor_line_is_refused(tmp_path: Path, kid: str) -> None:
    assert _tool().main(["--out", str(tmp_path / "k.pem"), "--kid", kid]) == 2
    assert not (tmp_path / "k.pem").exists()
