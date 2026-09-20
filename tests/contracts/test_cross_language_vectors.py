"""The two byte formats VAN implements twice, pinned to shared vectors.

`evidence/van-remote-browser/cross_language_vectors.json` holds inputs and the bytes the
gateway produces for them. This file asserts the vectors still match the Python
implementation; `android/verification/.../CrossLanguageVectorsTest.kt` asserts the Kotlin
implementation produces the same bytes from the same file.

Why a vectors file rather than comparing the two sources: the difference that mattered when
this was written is invisible in a source diff. Both canonicalizers sorted keys and dropped
whitespace, and they agreed on every ASCII document — but Python's `json.dumps` escapes
non-ASCII as `\\uXXXX` by default and the Kotlin one emitted the character. A manifest or a
command payload with an accent in it verified on the phone and nowhere else, and every test
on either side passed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "evidence" / "van-remote-browser" / "cross_language_vectors.json"
KOTLIN_TEST = (
    ROOT / "android" / "verification" / "src" / "test" / "kotlin" / "com" / "dial" / "van"
    / "security" / "CrossLanguageVectorsTest.kt"
)

sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.auth.device_proof import request_signing_input  # noqa: E402
from van_gateway.session.models import SessionEnvelope  # noqa: E402


@pytest.fixture(scope="module")
def vectors() -> dict:
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def test_the_vectors_file_has_enough_of_the_awkward_cases(vectors):
    """A vectors file of three ASCII objects would pass while proving nothing."""
    canonical = vectors["canonical_json"]
    assert len(canonical) >= 6
    rendered = " ".join(item["canonical"] for item in canonical)
    assert "\\u" in rendered, "no non-ASCII case, which is the drift this file exists for"
    assert "\\ud83d" in rendered, "no astral-plane case, so surrogate pairs are unproven"
    assert any("null" in item["canonical"] for item in canonical)
    assert any("true" in item["canonical"] for item in canonical)
    assert any("[" in item["canonical"] for item in canonical)


def test_every_canonical_vector_is_what_the_gateway_produces_today(vectors):
    for item in vectors["canonical_json"]:
        produced = json.dumps(item["payload"], sort_keys=True, separators=(",", ":"))
        assert produced == item["canonical"], item["payload"]
        assert hashlib.sha256(produced.encode("utf-8")).hexdigest() == item["sha256"]


def test_the_session_envelope_digests_the_same_way(vectors):
    """The envelope is the reason the canonical form has to be exact.

    `admit()` compares this digest to decide whether a resubmitted command is the same
    command. A device that canonicalized differently would have its retry admitted as new
    work — one owner instruction performed twice.
    """
    for item in vectors["canonical_json"]:
        envelope = SessionEnvelope(
            message_id="m1",
            van_session_id="vs_1",
            session_epoch=1,
            path_epoch=0,
            device_id="dev-1",
            direction="UPSTREAM",
            kind="command.submit",
            created_at_ms=1,
            payload=item["payload"],
        )
        assert envelope.digest() == item["sha256"]


def test_every_device_proof_vector_is_what_the_gateway_signs_today(vectors):
    for item in vectors["device_proof"]:
        body = item["body_utf8"].encode("utf-8")
        assert hashlib.sha256(body).hexdigest() == item["body_sha256"]
        signing_input = request_signing_input(
            method=item["method"],
            path=item["path"],
            device_id=item["device_id"],
            issued_at_ms=item["issued_at_ms"],
            body_sha256=item["body_sha256"],
        )
        assert (
            hashlib.sha256(signing_input).hexdigest() == item["signing_input_sha256"]
        ), item["path"]


def test_a_lowercase_method_signs_the_same_bytes_as_an_uppercase_one(vectors):
    """Both sides uppercase. If only one did, every proof from the phone would fail."""
    lowered = [item for item in vectors["device_proof"] if item["method"].islower()]
    assert lowered, "no lowercase-method vector, so the uppercasing rule is untested"


def test_the_kotlin_harness_reads_these_same_vectors():
    """Otherwise this file is one implementation checked against itself.

    The Kotlin test is not executed here — it runs in `android/verification` — but a vectors
    file that only Python reads proves nothing about the other implementation, and that is
    a failure mode this check can see.
    """
    assert KOTLIN_TEST.exists(), f"{KOTLIN_TEST} is missing"
    text = KOTLIN_TEST.read_text(encoding="utf-8")
    assert "cross_language_vectors.json" in text
    assert "canonical_json" in text and "device_proof" in text


# --------------------------------------------------------------- envelope field names

KOTLIN_ENVELOPE = (
    ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van"
    / "session" / "SessionEnvelope.kt"
)


def test_the_device_only_puts_fields_the_gateway_declares():
    """Every key the phone writes has to be a field of the envelope the Gateway validates.

    A key the model does not declare is dropped or rejected depending on the model's
    config, and either way the phone believes it sent something it did not. This is the
    check that caught `DEVICE_TO_GATEWAY`: the *name* was right and the *value* was not,
    so the test below covers the values too.
    """
    import re

    written = set(re.findall(r'\.put\("([a-z_]+)"', KOTLIN_ENVELOPE.read_text()))
    declared = set(SessionEnvelope.model_fields)
    unknown = written - declared
    assert not unknown, f"the device writes fields the gateway does not declare: {sorted(unknown)}"


def test_the_device_uses_the_gateways_spelling_of_direction():
    import re

    from van_gateway.session.models import Direction

    values = set(
        re.findall(r'const val DIRECTION_\w+: String = "(\w+)"', KOTLIN_ENVELOPE.read_text())
    )
    assert values, "no direction constants found, so this check proves nothing"
    allowed = {member.value for member in Direction}
    assert values <= allowed, f"{sorted(values - allowed)} is not a Direction the gateway has"


def test_the_required_envelope_fields_are_all_written():
    """A field the Gateway requires and the phone omits is a 422 on every message."""
    import re

    written = set(re.findall(r'\.put\("([a-z_]+)"', KOTLIN_ENVELOPE.read_text()))
    required = {
        name for name, field in SessionEnvelope.model_fields.items() if field.is_required()
    }
    assert required <= written, f"the device never writes {sorted(required - written)}"


# ------------------------------------------------------------------- proof header names

KOTLIN_SIGNER = (
    ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van"
    / "security" / "OwnerDeviceIdentity.kt"
)
GATEWAY_APP = ROOT / "backend" / "van_gateway" / "app.py"


def test_the_proof_headers_have_the_same_names_on_both_sides():
    """Two correct implementations of a proof, exchanged over headers nobody compared.

    A renamed header is a proof the gateway never looks for: the device signs, sends, and
    is refused with `device_proof_required` — which reads as "the phone did not sign" and
    is the opposite of what happened.
    """
    import re

    device = set(re.findall(r'"(X-Van-Device-Proof[^"]*)"', KOTLIN_SIGNER.read_text()))
    gateway = set(re.findall(r'"(X-Van-Device-Proof[^"]*)"', GATEWAY_APP.read_text()))
    assert device, "the device sends no proof headers"
    assert gateway, "the gateway reads no proof headers"
    assert device == gateway, (
        f"device sends {sorted(device)}, gateway reads {sorted(gateway)}"
    )


def test_the_skew_the_device_mirrors_is_the_gateway_s():
    """The phone refuses early on a clock it knows is too far out; the value must match.

    A device tolerance wider than the gateway's produces proofs that are signed, sent and
    rejected. Narrower, and the device refuses to act while the gateway would have accepted.
    """
    import re

    from van_gateway.auth.device_proof import PROOF_SKEW_MS

    match = re.search(r"const val SKEW_MS: Long = ([0-9_]+)", KOTLIN_SIGNER.read_text())
    if match is None:
        canonical = (
            ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van"
            / "security" / "DeviceProofCanonical.kt"
        )
        match = re.search(r"const val SKEW_MS: Long = ([0-9_]+)", canonical.read_text())
    assert match, "the device declares no skew tolerance"
    assert int(match.group(1).replace("_", "")) == PROOF_SKEW_MS
