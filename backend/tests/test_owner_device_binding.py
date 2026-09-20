"""Rev 1.5 §§0D.2, 0D.3, 5.7 — one owner device, and configuration it cannot be talked into.

§0D.3 names the wrong implementation explicitly: a `Build.MODEL` check passes on any other
S24 Ultra. The right one is a key whose private half never leaves the phone, which means the
tests that matter here are the ones where something *almost* works — a perfect attestation
answering last week's challenge, a signature lifted from one request onto another, a second
phone enrolling while the first is bound, an old manifest replayed at a device that has
already moved on.

The attestation structures are built in the tests. That is honest about what this proves:
the parser and the policy are exercised against the shape Android documents, and whether a
real S24 emits a chain this verifier accepts is RB-120, a device gate, recorded as one.
"""

from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from conftest_automation import make_store
from van_gateway.auth.device_binding import (
    DeviceBindingError,
    OwnerDeviceBindingService,
)
from van_gateway.auth.device_proof import (
    AttestationPolicy,
    DeviceProofError,
    SecurityLevel,
    VerifiedBootState,
    key_fingerprint,
    parse_attestation_extension,
    request_signing_input,
    verify_attestation,
    verify_request_proof,
)
from van_gateway.connectivity.config import (
    ConnectivityConfigService,
    ConnectivityError,
    sign_manifest,
    verify_manifest,
)

PACKAGE = "com.dial.van"
SIGNING_CERT = "a" * 64


# --------------------------------------------------------------------------- DER helpers


def _der(tag: int, body: bytes) -> bytes:
    if len(body) < 0x80:
        return bytes([tag, len(body)]) + body
    length = len(body).to_bytes((len(body).bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(length)]) + length + body


def _int(value: int) -> bytes:
    raw = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    return _der(0x02, raw)


def _octet(value: bytes) -> bytes:
    return _der(0x04, value)


def _seq(*parts: bytes) -> bytes:
    return _der(0x30, b"".join(parts))


def _tagged(number: int, body: bytes) -> bytes:
    """Context-specific, constructed, in the form Android actually emits.

    Tags above 30 use DER's high-tag-number encoding, and both of the tags this
    attestation carries — 704 and 709 — are above 30. A first version of these helpers
    masked them down to five bits, which produced structures no Android device would ever
    send and which the parser happily read as something else.
    """
    if number < 0x1F:
        return _der(0xA0 | number, body)
    chunks = []
    value = number
    while value:
        chunks.insert(0, value & 0x7F)
        value >>= 7
    encoded = bytes([c | 0x80 for c in chunks[:-1]] + [chunks[-1]])
    header = bytes([0xA0 | 0x1F]) + encoded
    length = len(body)
    if length < 0x80:
        return header + bytes([length]) + body
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return header + bytes([0x80 | len(raw)]) + raw + body


def _root_of_trust(state: int) -> bytes:
    return _tagged(704, _seq(_octet(b"bootkey"), _der(0x01, b"\xff"), _int(state)))


def _application_id(package: str = PACKAGE, cert_hex: str = SIGNING_CERT) -> bytes:
    package_info = _seq(_octet(package.encode()), _int(5))
    signature = _octet(bytes.fromhex(cert_hex))
    return _tagged(709, _seq(_seq(package_info), _seq(signature)))


def _attestation(
    challenge: bytes,
    *,
    security_level: int = 1,
    boot_state: int = 0,
    package: str = PACKAGE,
    cert_hex: str = SIGNING_CERT,
    include_root: bool = True,
) -> bytes:
    tee = _seq(*( [_root_of_trust(boot_state)] if include_root else [] ),
               _application_id(package, cert_hex))
    return _seq(
        _int(4),                    # attestationVersion
        _int(security_level),       # attestationSecurityLevel
        _int(4),                    # keymasterVersion
        _int(security_level),       # keymasterSecurityLevel
        _octet(challenge),
        _octet(b""),                # uniqueId
        _seq(),                     # softwareEnforced
        tee,                        # teeEnforced
    )


def _policy(**kwargs) -> AttestationPolicy:
    base = dict(expected_package=PACKAGE, expected_signing_cert_sha256=SIGNING_CERT)
    base.update(kwargs)
    return AttestationPolicy(**base)


def _keypair() -> tuple[str, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return pem, key


# --------------------------------------------------------------------------- parsing


class TestAttestationParsing:
    def test_the_facts_are_read_from_the_tee_enforced_list(self):
        facts = parse_attestation_extension(_attestation(b"challenge-1"))
        assert facts.attestation_security_level is SecurityLevel.TRUSTED_ENVIRONMENT
        assert facts.verified_boot_state is VerifiedBootState.VERIFIED
        assert facts.package_name == PACKAGE
        assert facts.signing_cert_sha256 == SIGNING_CERT
        assert facts.challenge == b"challenge-1"

    def test_a_truncated_extension_is_refused_rather_than_partially_believed(self):
        raw = _attestation(b"c")
        with pytest.raises(DeviceProofError):
            parse_attestation_extension(raw[:10])

    def test_something_that_is_not_a_sequence_is_refused(self):
        with pytest.raises(DeviceProofError) as caught:
            parse_attestation_extension(_octet(b"not a key description"))
        assert caught.value.reason == "attestation_not_a_sequence"


# --------------------------------------------------------------------------- policy


class TestAttestationPolicy:
    def test_a_matching_attestation_is_accepted(self):
        verdict = verify_attestation(
            extension=_attestation(b"challenge-1"), challenge=b"challenge-1", policy=_policy()
        )
        assert verdict.accepted is True

    def test_a_perfect_attestation_for_the_wrong_challenge_is_refused(self):
        """A chain captured from an earlier enrolment is cryptographically flawless and
        answers a question nobody asked."""
        verdict = verify_attestation(
            extension=_attestation(b"last-weeks-challenge"),
            challenge=b"todays-challenge", policy=_policy(),
        )
        assert verdict.accepted is False
        assert verdict.refusal == "attestation_challenge_mismatch"

    def test_a_software_key_is_refused(self):
        verdict = verify_attestation(
            extension=_attestation(b"c", security_level=0), challenge=b"c", policy=_policy()
        )
        assert verdict.refusal == "attestation_not_hardware_backed"

    def test_an_unverified_boot_state_is_refused(self):
        verdict = verify_attestation(
            extension=_attestation(b"c", boot_state=2), challenge=b"c", policy=_policy()
        )
        assert verdict.refusal.startswith("attestation_verified_boot")

    def test_a_missing_root_of_trust_is_not_treated_as_probably_fine(self):
        verdict = verify_attestation(
            extension=_attestation(b"c", include_root=False), challenge=b"c", policy=_policy()
        )
        assert verdict.accepted is False

    def test_another_app_on_the_same_phone_is_refused(self):
        """§0D.3's binding is package plus signing identity plus key, not just the key."""
        verdict = verify_attestation(
            extension=_attestation(b"c", package="com.example.other"),
            challenge=b"c", policy=_policy(),
        )
        assert verdict.refusal == "attestation_package_mismatch"

    def test_a_rebuilt_app_with_a_different_signing_key_is_refused(self):
        verdict = verify_attestation(
            extension=_attestation(b"c", cert_hex="b" * 64), challenge=b"c", policy=_policy()
        )
        assert verdict.refusal == "attestation_signing_cert_mismatch"

    def test_an_unlisted_attestation_root_is_refused_when_roots_are_pinned(self):
        policy = _policy(allowed_root_fingerprints=frozenset({"c" * 64}))
        verdict = verify_attestation(
            extension=_attestation(b"c"), challenge=b"c", policy=policy,
            root_fingerprint="d" * 64,
        )
        assert verdict.refusal == "attestation_root_not_allowed"


# --------------------------------------------------------------------------- possession


class TestProofOfPossession:
    def _sign(self, key, *, method="POST", path="/v1/commands", device_id="phone",
              issued_at_ms=1_000, body=b"{}"):
        signing_input = request_signing_input(
            method=method, path=path, device_id=device_id, issued_at_ms=issued_at_ms,
            body_sha256=hashlib.sha256(body).hexdigest(),
        )
        return key.sign(signing_input, ec.ECDSA(hashes := __import__(
            "cryptography.hazmat.primitives.hashes", fromlist=["SHA256"]
        ).SHA256()))

    def test_a_correct_proof_verifies(self):
        pem, key = _keypair()
        verify_request_proof(
            public_key_pem=pem, signature=self._sign(key), method="POST",
            path="/v1/commands", device_id="phone", issued_at_ms=1_000, body=b"{}",
            now_ms=1_500,
        )

    def test_a_signature_lifted_onto_another_request_is_refused(self):
        """The body digest is in the signing input for exactly this."""
        pem, key = _keypair()
        signature = self._sign(key, body=b'{"text":"what is the weather"}')
        with pytest.raises(DeviceProofError) as caught:
            verify_request_proof(
                public_key_pem=pem, signature=signature, method="POST",
                path="/v1/commands", device_id="phone", issued_at_ms=1_000,
                body=b'{"text":"transfer the money"}', now_ms=1_500,
            )
        assert caught.value.reason == "device_proof_invalid"

    def test_a_signature_for_another_route_is_refused(self):
        pem, key = _keypair()
        signature = self._sign(key, path="/v1/commands")
        with pytest.raises(DeviceProofError):
            verify_request_proof(
                public_key_pem=pem, signature=signature, method="POST",
                path="/v1/devices/rebind", device_id="phone", issued_at_ms=1_000,
                body=b"{}", now_ms=1_500,
            )

    def test_an_old_proof_is_not_a_durable_credential(self):
        pem, key = _keypair()
        with pytest.raises(DeviceProofError) as caught:
            verify_request_proof(
                public_key_pem=pem, signature=self._sign(key), method="POST",
                path="/v1/commands", device_id="phone", issued_at_ms=1_000,
                body=b"{}", now_ms=1_000 + 10 * 60_000,
            )
        assert caught.value.reason == "device_proof_stale"

    def test_another_devices_key_does_not_verify(self):
        pem, _ = _keypair()
        _, other = _keypair()
        with pytest.raises(DeviceProofError):
            verify_request_proof(
                public_key_pem=pem, signature=self._sign(other), method="POST",
                path="/v1/commands", device_id="phone", issued_at_ms=1_000,
                body=b"{}", now_ms=1_500,
            )


# --------------------------------------------------------------------------- binding


@pytest.mark.asyncio
class TestOwnerDeviceBinding:
    async def _service(self, tmp_path, **policy):
        store = await make_store(tmp_path)
        return OwnerDeviceBindingService(store, _policy(**policy)), store

    async def test_a_device_binds_once_and_becomes_the_owners(self, tmp_path):
        service, _ = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        binding = await service.bind(
            token=token, device_id="s24", public_key_pem=pem,
            attestation_extension=_attestation(challenge.encode()), now_ms=1_100,
        )
        assert binding.device_id == "s24"
        assert binding.device_key_fingerprint == key_fingerprint(pem)
        assert (await service.active()).binding_id == binding.binding_id

    async def test_a_second_phone_cannot_enrol_while_one_is_bound(self, tmp_path):
        """§0D.3 — the package may install elsewhere and must be non-functional there."""
        service, _ = await self._service(tmp_path)
        first_token, first_challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        await service.bind(
            token=first_token, device_id="s24", public_key_pem=pem,
            attestation_extension=_attestation(first_challenge.encode()), now_ms=1_100,
        )
        second_token, second_challenge = await service.create_bootstrap_token(now_ms=1_200)
        other_pem, _ = _keypair()
        with pytest.raises(DeviceBindingError) as caught:
            await service.bind(
                token=second_token, device_id="another-phone", public_key_pem=other_pem,
                attestation_extension=_attestation(second_challenge.encode()), now_ms=1_300,
            )
        assert caught.value.reason == "owner_device_already_bound"

    async def test_a_bootstrap_token_is_single_use(self, tmp_path):
        service, _ = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        await service.bind(
            token=token, device_id="s24", public_key_pem=pem,
            attestation_extension=_attestation(challenge.encode()), now_ms=1_100,
        )
        with pytest.raises(DeviceBindingError) as caught:
            await service.challenge_for(token, now_ms=1_200)
        assert caught.value.reason == "bootstrap_token_spent"

    async def test_an_expired_bootstrap_token_is_refused(self, tmp_path):
        service, _ = await self._service(tmp_path)
        token, _ = await service.create_bootstrap_token(now_ms=1_000)
        with pytest.raises(DeviceBindingError) as caught:
            await service.challenge_for(token, now_ms=1_000 + 2 * 60 * 60_000)
        assert caught.value.reason == "bootstrap_token_expired"

    async def test_the_token_is_stored_only_as_a_hash(self, tmp_path):
        """A readable bootstrap token in the database is a second copy of the credential."""
        service, store = await self._service(tmp_path)
        token, _ = await service.create_bootstrap_token(now_ms=1_000)
        rows = await store.fetchall("SELECT token_sha256 FROM owner_device_bootstrap_tokens")
        assert token not in {r["token_sha256"] for r in rows}
        assert rows[0]["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()

    async def test_a_refused_attestation_binds_nothing_and_is_recorded(self, tmp_path):
        """§0E.1 D5 — no silent downgrade to a weaker binding."""
        service, store = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        with pytest.raises(DeviceBindingError):
            await service.bind(
                token=token, device_id="rooted-phone", public_key_pem=pem,
                attestation_extension=_attestation(challenge.encode(), boot_state=2),
                now_ms=1_100,
            )
        assert await service.active() is None
        events = await store.fetchall(
            "SELECT outcome, refusal_reason FROM device_attestation_events"
        )
        assert events[0]["outcome"] == "REFUSED"
        assert events[0]["refusal_reason"].startswith("attestation_verified_boot")

    async def test_a_refused_enrolment_does_not_spend_the_token(self, tmp_path):
        service, _ = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        with pytest.raises(DeviceBindingError):
            await service.bind(
                token=token, device_id="rooted-phone", public_key_pem=pem,
                attestation_extension=_attestation(challenge.encode(), security_level=0),
                now_ms=1_100,
            )
        # The owner's real phone must still be able to enrol with the token they were given.
        assert await service.challenge_for(token, now_ms=1_200) == challenge

    async def test_every_privileged_request_proves_possession(self, tmp_path):
        service, _ = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, key = _keypair()
        await service.bind(
            token=token, device_id="s24", public_key_pem=pem,
            attestation_extension=_attestation(challenge.encode()), now_ms=1_100,
        )
        from cryptography.hazmat.primitives import hashes as h

        signature = key.sign(
            request_signing_input(
                method="POST", path="/v1/commands", device_id="s24", issued_at_ms=2_000,
                body_sha256=hashlib.sha256(b"{}").hexdigest(),
            ),
            ec.ECDSA(h.SHA256()),
        )
        binding = await service.require_proof(
            device_id="s24", signature=signature, method="POST", path="/v1/commands",
            issued_at_ms=2_000, body=b"{}", now_ms=2_100,
        )
        assert binding.device_id == "s24"

    async def test_a_copied_token_without_the_key_is_refused(self, tmp_path):
        """ADR-RB-025, stated as the attack it prevents."""
        service, _ = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        await service.bind(
            token=token, device_id="s24", public_key_pem=pem,
            attestation_extension=_attestation(challenge.encode()), now_ms=1_100,
        )
        _, thief = _keypair()
        from cryptography.hazmat.primitives import hashes as h

        forged = thief.sign(
            request_signing_input(
                method="POST", path="/v1/commands", device_id="s24", issued_at_ms=2_000,
                body_sha256=hashlib.sha256(b"{}").hexdigest(),
            ),
            ec.ECDSA(h.SHA256()),
        )
        with pytest.raises(DeviceBindingError):
            await service.require_proof(
                device_id="s24", signature=forged, method="POST", path="/v1/commands",
                issued_at_ms=2_000, body=b"{}", now_ms=2_100,
            )

    async def test_a_revoked_binding_stops_working_without_deleting_its_history(self, tmp_path):
        service, store = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        await service.bind(
            token=token, device_id="s24", public_key_pem=pem,
            attestation_extension=_attestation(challenge.encode()), now_ms=1_100,
        )
        await service.revoke(reason="phone lost", now_ms=3_000)
        assert await service.active() is None
        rows = await store.fetchall("SELECT status, revoke_reason FROM owner_device_bindings")
        assert rows[0]["status"] == "REVOKED"
        assert rows[0]["revoke_reason"] == "phone lost"

    async def test_rebinding_revokes_and_issues_in_one_step(self, tmp_path):
        service, _ = await self._service(tmp_path)
        token, challenge = await service.create_bootstrap_token(now_ms=1_000)
        pem, _ = _keypair()
        await service.bind(
            token=token, device_id="s24", public_key_pem=pem,
            attestation_extension=_attestation(challenge.encode()), now_ms=1_100,
        )
        new_token, new_challenge = await service.rebind_token(
            reason="replaced handset", now_ms=4_000
        )
        replacement_pem, _ = _keypair()
        binding = await service.bind(
            token=new_token, device_id="s24-new", public_key_pem=replacement_pem,
            attestation_extension=_attestation(new_challenge.encode()), now_ms=4_100,
        )
        assert binding.device_id == "s24-new"
        assert (await service.active()).device_id == "s24-new"


# --------------------------------------------------------------------------- manifest


class TestConnectivityManifest:
    """Half of these are synchronous, so the class carries no asyncio mark; the async ones
    are marked individually. A blanket mark on a sync test is a warning that trains people
    to ignore warnings."""

    def _keys(self):
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        public = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        return private, public

    def test_a_signed_manifest_verifies(self):
        private, public = self._keys()
        manifest = {"manifest_version": 3, "gateway_url": "https://van.example"}
        verify_manifest(
            manifest, sign_manifest(manifest, private_pem=private),
            trusted_keys={"cfg-1": public}, kid="cfg-1",
        )

    def test_an_edited_manifest_does_not_verify(self):
        private, public = self._keys()
        manifest = {"manifest_version": 3, "gateway_url": "https://van.example"}
        signature = sign_manifest(manifest, private_pem=private)
        with pytest.raises(ConnectivityError) as caught:
            verify_manifest(
                {**manifest, "gateway_url": "https://attacker.example"}, signature,
                trusted_keys={"cfg-1": public}, kid="cfg-1",
            )
        assert caught.value.reason == "connectivity_manifest_signature_invalid"

    def test_an_unknown_signing_key_is_refused_rather_than_tried_against_every_key(self):
        private, public = self._keys()
        manifest = {"manifest_version": 3}
        with pytest.raises(ConnectivityError) as caught:
            verify_manifest(
                manifest, sign_manifest(manifest, private_pem=private),
                trusted_keys={"cfg-1": public}, kid="cfg-unknown",
            )
        assert caught.value.reason == "connectivity_manifest_unknown_kid"

    def test_an_old_manifest_cannot_be_replayed_at_a_device_that_moved_on(self):
        """Rollback protection: the old manifest is perfectly signed and points somewhere
        that may now belong to someone else."""
        private, public = self._keys()
        old = {"manifest_version": 2, "gateway_url": "https://old.example"}
        with pytest.raises(ConnectivityError) as caught:
            verify_manifest(
                old, sign_manifest(old, private_pem=private),
                trusted_keys={"cfg-1": public}, kid="cfg-1", minimum_version=5,
            )
        assert caught.value.reason == "connectivity_manifest_rollback"

    @pytest.mark.asyncio
    async def test_publishing_replaces_the_active_manifest(self, tmp_path):
        store = await make_store(tmp_path)
        private, public = self._keys()
        service = ConnectivityConfigService(store, private_pem=private, kid="cfg-1")
        await service.publish({"manifest_version": 1, "gateway_url": "https://a"}, now_ms=1_000)
        await service.publish({"manifest_version": 2, "gateway_url": "https://b"}, now_ms=2_000)
        active = await service.active()
        assert active.manifest_version == 2
        served = await service.serve(known_version=1)
        verify_manifest(
            served["manifest"], served["signature"],
            trusted_keys={"cfg-1": public}, kid=served["kid"], minimum_version=2,
        )

    @pytest.mark.asyncio
    async def test_a_device_that_already_has_the_current_manifest_is_told_nothing(self, tmp_path):
        store = await make_store(tmp_path)
        private, _ = self._keys()
        service = ConnectivityConfigService(store, private_pem=private, kid="cfg-1")
        await service.publish({"manifest_version": 4, "gateway_url": "https://a"}, now_ms=1_000)
        assert await service.serve(known_version=4) is None

    @pytest.mark.asyncio
    async def test_republishing_an_older_version_is_refused(self, tmp_path):
        store = await make_store(tmp_path)
        private, _ = self._keys()
        service = ConnectivityConfigService(store, private_pem=private, kid="cfg-1")
        await service.publish({"manifest_version": 4}, now_ms=1_000)
        with pytest.raises(ConnectivityError) as caught:
            await service.publish({"manifest_version": 3}, now_ms=2_000)
        assert caught.value.reason == "connectivity_manifest_not_newer"

    @pytest.mark.asyncio
    async def test_a_manifest_carrying_a_credential_is_refused(self, tmp_path):
        """§0D.2 — configuration, not a credential the device caches and a copy inherits."""
        store = await make_store(tmp_path)
        private, _ = self._keys()
        service = ConnectivityConfigService(store, private_pem=private, kid="cfg-1")
        with pytest.raises(ConnectivityError) as caught:
            await service.publish(
                {"manifest_version": 1, "pairing_token": "secret"}, now_ms=1_000
            )
        assert "carries_credential" in caught.value.reason

    @pytest.mark.asyncio
    async def test_an_unversioned_manifest_is_refused(self, tmp_path):
        store = await make_store(tmp_path)
        private, _ = self._keys()
        service = ConnectivityConfigService(store, private_pem=private, kid="cfg-1")
        with pytest.raises(ConnectivityError):
            await service.publish({"gateway_url": "https://a"}, now_ms=1_000)
