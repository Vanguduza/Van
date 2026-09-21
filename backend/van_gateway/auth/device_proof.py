"""Rev 1.5 §0D.3 / ADR-RB-025 — proof of possession, and the attestation behind it.

§0D.3 rules out the obvious implementation in so many words:

    if (Build.MODEL == "SM-S928B") allow()

because another S24 Ultra passes the same check. What cannot be copied is the private half
of a hardware-backed key, so the binding is a public-key fingerprint and every privileged
request carries a signature over the request itself. A stolen bearer token is then not
enough: the thief would also need a key that, by construction, never left the phone's secure
hardware.

Two things this module refuses to do:

* **It never treats an absent attestation extension as "probably fine".** A key with no
  attestation is a key that has not said where it lives, and §0D.3's whole point is knowing
  that.
* **It never decides the verdict from the certificate alone.** The chain says the key is
  hardware-backed; only the Gateway's own challenge says it is *this* enrolment.

The attestation parsing here is the real ASN.1 structure Android emits, read with a small
DER reader rather than a dependency. It is tested against structures built in the tests,
which is honest about what that proves: the shape is checked, and whether a real S24
produces a chain this verifier accepts is a device gate (RB-120), recorded as such.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import Enum

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

#: The OID Android puts the key attestation extension under.
ATTESTATION_OID = "1.3.6.1.4.1.11129.2.1.17"

#: Tags inside the authorization list that this verifier reads. There are many more; these
#: are the ones §0D.3's binding depends on.
TAG_ROOT_OF_TRUST = 704
TAG_ATTESTATION_APPLICATION_ID = 709

#: Marks a tag returned from `read_tlv` as a high-tag-number form, whose class bits live
#: in the upper half of the value and whose number lives in the lower half.
_HIGH_TAG_FLAG = 1 << 24

#: How long a signed request may be in flight. Long enough for a slow network, short enough
#: that a captured signature is not a durable credential.
PROOF_SKEW_MS = 120_000


class SecurityLevel(str, Enum):
    SOFTWARE = "SOFTWARE"
    TRUSTED_ENVIRONMENT = "TRUSTED_ENVIRONMENT"
    STRONG_BOX = "STRONG_BOX"

    @property
    def hardware_backed(self) -> bool:
        return self in {SecurityLevel.TRUSTED_ENVIRONMENT, SecurityLevel.STRONG_BOX}


_SECURITY_LEVELS = {
    0: SecurityLevel.SOFTWARE,
    1: SecurityLevel.TRUSTED_ENVIRONMENT,
    2: SecurityLevel.STRONG_BOX,
}


class VerifiedBootState(str, Enum):
    VERIFIED = "VERIFIED"
    SELF_SIGNED = "SELF_SIGNED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"


_BOOT_STATES = {
    0: VerifiedBootState.VERIFIED,
    1: VerifiedBootState.SELF_SIGNED,
    2: VerifiedBootState.UNVERIFIED,
    3: VerifiedBootState.FAILED,
}


class DeviceProofError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------------------- DER reading


@dataclass
class _Der:
    """A deliberately small DER reader.

    Written rather than pulled in because the alternative is admitting an ASN.1 library to
    parse one extension, and §32's dependency rules apply to convenience as much as to
    features. It reads only what it needs and refuses anything it does not understand: a
    lenient parser on a security-bearing structure is how a malformed attestation becomes an
    accepted one.
    """

    data: bytes
    pos: int = 0

    def read_tlv(self) -> tuple[int, bytes]:
        """Returns `(tag, value)` where a context-specific tag is its full number.

        Android's authorization lists are tagged with the authorization tag itself — 704
        for the root of trust, 709 for the application id — and anything above 30 uses
        DER's high-tag-number form: the low five bits set to 1, then the number in base-128
        continuation bytes. A reader that only handles the single-byte form does not
        misparse those, it silently never finds them, which is worse: the verifier would
        then see an attestation with no root of trust and no application id on every real
        device, and would refuse each one for the wrong reason.
        """
        if self.pos >= len(self.data):
            raise DeviceProofError("attestation_truncated")
        first = self.data[self.pos]
        self.pos += 1
        tag = first
        if first & 0x1F == 0x1F:
            number = 0
            while True:
                if self.pos >= len(self.data):
                    raise DeviceProofError("attestation_truncated")
                byte = self.data[self.pos]
                self.pos += 1
                number = (number << 7) | (byte & 0x7F)
                if number > 0xFFFF:
                    raise DeviceProofError("attestation_tag_too_large")
                if not byte & 0x80:
                    break
            # The class bits and the tag number are kept in separate halves of the
            # returned value. Packing a 704 into the same low byte as the class bits — the
            # first attempt here — made `704 & 0xC0` collide with the class mask, so every
            # authorization entry was skipped as "not context-specific" and the verifier
            # saw an attestation with no root of trust at all.
            tag = _HIGH_TAG_FLAG | ((first & 0xE0) << 16) | number
        length = self._read_length()
        if self.pos + length > len(self.data):
            raise DeviceProofError("attestation_truncated")
        value = self.data[self.pos : self.pos + length]
        self.pos += length
        return tag, value

    def _read_length(self) -> int:
        if self.pos >= len(self.data):
            raise DeviceProofError("attestation_truncated")
        first = self.data[self.pos]
        self.pos += 1
        if first < 0x80:
            return first
        count = first & 0x7F
        if count == 0 or count > 4:
            raise DeviceProofError("attestation_length_unsupported")
        if self.pos + count > len(self.data):
            raise DeviceProofError("attestation_truncated")
        length = int.from_bytes(self.data[self.pos : self.pos + count], "big")
        self.pos += count
        return length

    def at_end(self) -> bool:
        return self.pos >= len(self.data)


def _read_integer(raw: bytes) -> int:
    return int.from_bytes(raw, "big", signed=False) if raw else 0


@dataclass(frozen=True)
class AttestationFacts:
    """What the extension actually says. Absent fields stay None rather than defaulting."""

    attestation_version: int
    attestation_security_level: SecurityLevel
    keymaster_security_level: SecurityLevel
    challenge: bytes
    verified_boot_state: VerifiedBootState | None
    package_name: str | None
    signing_cert_sha256: str | None


def parse_attestation_extension(extension: bytes) -> AttestationFacts:
    """Read Android's KeyDescription. Refuses rather than guesses."""
    reader = _Der(extension)
    tag, body = reader.read_tlv()
    if tag != 0x30:
        raise DeviceProofError("attestation_not_a_sequence")

    inner = _Der(body)
    _, version_raw = inner.read_tlv()
    _, attestation_level_raw = inner.read_tlv()
    _, _keymaster_version = inner.read_tlv()
    _, keymaster_level_raw = inner.read_tlv()
    _, challenge = inner.read_tlv()
    _, _unique_id = inner.read_tlv()
    software_tag, software_enforced = inner.read_tlv()
    tee_tag, tee_enforced = inner.read_tlv()
    if software_tag != 0x30 or tee_tag != 0x30:
        raise DeviceProofError("attestation_authorization_list_malformed")

    boot_state: VerifiedBootState | None = None
    package_name: str | None = None
    signing_cert: str | None = None
    # §0D.3 reads the *TEE-enforced* list. The software-enforced one is written by the
    # operating system and is exactly what a compromised device can lie in.
    for tag_number, value in _authorization_entries(tee_enforced):
        if tag_number == TAG_ROOT_OF_TRUST:
            boot_state = _root_of_trust_state(value)
        elif tag_number == TAG_ATTESTATION_APPLICATION_ID:
            package_name, signing_cert = _application_id(value)

    attestation_level = _SECURITY_LEVELS.get(_read_integer(attestation_level_raw))
    keymaster_level = _SECURITY_LEVELS.get(_read_integer(keymaster_level_raw))
    if attestation_level is None or keymaster_level is None:
        raise DeviceProofError("attestation_security_level_unknown")

    return AttestationFacts(
        attestation_version=_read_integer(version_raw),
        attestation_security_level=attestation_level,
        keymaster_security_level=keymaster_level,
        challenge=challenge,
        verified_boot_state=boot_state,
        package_name=package_name,
        signing_cert_sha256=signing_cert,
    )


def _tag_parts(tag: int) -> tuple[int, int]:
    """Split a tag from `read_tlv` into `(class_bits, number)`."""
    if tag & _HIGH_TAG_FLAG:
        return (tag >> 16) & 0xE0, tag & 0xFFFF
    return tag & 0xE0, tag & 0x1F


def _authorization_entries(body: bytes):
    """Yield `(authorization_tag, value)` for each context-specific entry."""
    reader = _Der(body)
    while not reader.at_end():
        tag, value = reader.read_tlv()
        class_bits, number = _tag_parts(tag)
        if class_bits & 0xC0 != 0x80:
            # Not context-specific: not an authorization entry.
            continue
        yield number, value


def _root_of_trust_state(body: bytes) -> VerifiedBootState | None:
    reader = _Der(body)
    tag, inner = reader.read_tlv()
    if tag != 0x30:
        return None
    fields = _Der(inner)
    _, _verified_boot_key = fields.read_tlv()
    _, _device_locked = fields.read_tlv()
    _, state_raw = fields.read_tlv()
    return _BOOT_STATES.get(_read_integer(state_raw))


def _application_id(body: bytes) -> tuple[str | None, str | None]:
    """AttestationApplicationId: the package set and the signing certificate digests."""
    reader = _Der(body)
    tag, inner = reader.read_tlv()
    if tag != 0x30:
        return None, None
    fields = _Der(inner)
    _, package_set = fields.read_tlv()
    _, signature_set = fields.read_tlv()

    packages = _Der(package_set)
    package_name = None
    if not packages.at_end():
        _, package_info = packages.read_tlv()
        info = _Der(package_info)
        _, name_raw = info.read_tlv()
        package_name = name_raw.decode("utf-8", errors="replace")

    signatures = _Der(signature_set)
    signing_cert = None
    if not signatures.at_end():
        _, digest = signatures.read_tlv()
        signing_cert = digest.hex()
    return package_name, signing_cert


# --------------------------------------------------------------------------- the verdict


@dataclass(frozen=True)
class AttestationPolicy:
    """What this deployment insists on before a device may be the owner's.

    Every field here is a refusal waiting to happen, which is the point: §0E.1 D5 requires
    that a failed attestation blocks certification with no silent downgrade to model-name or
    bearer-token binding.
    """

    expected_package: str
    expected_signing_cert_sha256: str
    require_hardware_backed: bool = True
    require_verified_boot: bool = True
    allowed_root_fingerprints: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AttestationVerdict:
    accepted: bool
    facts: AttestationFacts | None
    refusal: str | None = None


def verify_attestation(
    *,
    extension: bytes,
    challenge: bytes,
    policy: AttestationPolicy,
    root_fingerprint: str | None = None,
) -> AttestationVerdict:
    """The whole check, in one place, with the refusal named.

    The challenge comparison is what stops a replayed attestation: a chain captured from an
    earlier enrolment is cryptographically perfect and answers the wrong question.
    """
    try:
        facts = parse_attestation_extension(extension)
    except DeviceProofError as exc:
        return AttestationVerdict(False, None, exc.reason)

    if facts.challenge != challenge:
        return AttestationVerdict(False, facts, "attestation_challenge_mismatch")
    if policy.require_hardware_backed and not facts.attestation_security_level.hardware_backed:
        return AttestationVerdict(False, facts, "attestation_not_hardware_backed")
    if policy.require_verified_boot and facts.verified_boot_state is not VerifiedBootState.VERIFIED:
        return AttestationVerdict(
            False, facts,
            f"attestation_verified_boot_{(facts.verified_boot_state or 'absent')}".lower(),
        )
    if facts.package_name != policy.expected_package:
        # §0D.3: the binding is package + signing identity + key. A key attested by a
        # different app on the same phone is a different application asking.
        return AttestationVerdict(False, facts, "attestation_package_mismatch")
    if (facts.signing_cert_sha256 or "").lower() != policy.expected_signing_cert_sha256.lower():
        return AttestationVerdict(False, facts, "attestation_signing_cert_mismatch")
    if policy.allowed_root_fingerprints:
        if root_fingerprint is None:
            return AttestationVerdict(False, facts, "attestation_root_absent")
        if root_fingerprint.lower() not in {f.lower() for f in policy.allowed_root_fingerprints}:
            return AttestationVerdict(False, facts, "attestation_root_not_allowed")
    return AttestationVerdict(True, facts, None)


# --------------------------------------------------------------------------- possession


def request_signing_input(
    *, method: str, path: str, device_id: str, issued_at_ms: int, body_sha256: str
) -> bytes:
    """What the phone signs. Fixed order, explicit separators.

    The body digest is in here so a signature cannot be lifted from one request and
    attached to another with the same method and path — which is the difference between
    proving possession and proving possession *of this request*.
    """
    return "\n".join([
        "van-device-proof-v1", method.upper(), path, device_id, str(issued_at_ms), body_sha256,
    ]).encode("utf-8")


def verify_request_proof(
    *,
    public_key_pem: str,
    signature: bytes,
    method: str,
    path: str,
    device_id: str,
    issued_at_ms: int,
    body: bytes,
    now_ms: int | None = None,
) -> None:
    """ADR-RB-025 — a copied access token without the private key is insufficient.

    Raises with a named reason; returns None when the proof holds.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    if abs(now - issued_at_ms) > PROOF_SKEW_MS:
        raise DeviceProofError("device_proof_stale")

    signing_input = request_signing_input(
        method=method, path=path, device_id=device_id, issued_at_ms=issued_at_ms,
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    public = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(public, ec.EllipticCurvePublicKey):
        raise DeviceProofError("device_proof_key_not_ec")
    if len(signature) == 64:
        signature = asym_utils.encode_dss_signature(
            int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
        )
    try:
        public.verify(signature, signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise DeviceProofError("device_proof_invalid") from exc


def key_fingerprint(public_key_pem: str) -> str:
    """The stable identity of a device key: SHA-256 over its DER SubjectPublicKeyInfo."""
    public = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    der = public.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()
