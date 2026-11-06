"""Cryptographic enrollment and Android software/hardware authorization-list layout."""
from dataclasses import replace

import pytest

from attestation_fixtures import signed_attestation_chain
from test_owner_device_binding import _attestation, _keypair, _policy, _seq, _int, _octet, _application_id, _root_of_trust, _der
from van_gateway.auth.device_proof import DeviceProofError, verify_attestation, verify_attestation_chain


def test_signed_android_chain_binds_leaf_key_extension_and_pinned_root():
    pem, _ = _keypair()
    extension = _attestation(b"fresh-challenge")
    chain, root = signed_attestation_chain(pem, extension)
    assert verify_attestation_chain(certificates_der=chain, public_key_pem=pem,
           policy=_policy(allowed_root_fingerprints=frozenset({root})), extension=extension) == (extension,root)


@pytest.mark.parametrize("failure", ["missing_root", "wrong_root", "wrong_key", "changed_extension", "expired", "issuer_not_ca", "changed_signature", "duplicate"])
def test_chain_failures_refuse_before_hardware_metadata_is_trusted(failure):
    pem, _ = _keypair()
    extension = _attestation(b"challenge")
    chain, root = signed_attestation_chain(pem, extension, expired=failure=="expired", issuer_ca=failure!="issuer_not_ca")
    policy = _policy(allowed_root_fingerprints=frozenset({root}))
    if failure=="missing_root": policy=replace(policy,allowed_root_fingerprints=frozenset())
    if failure=="wrong_root": policy=replace(policy,allowed_root_fingerprints=frozenset({"0"*64}))
    if failure=="wrong_key": pem=_keypair()[0]
    if failure=="changed_extension": extension += b"x"
    if failure=="changed_signature": chain[0]=chain[0][:-1]+bytes([chain[0][-1]^1])
    if failure=="duplicate": chain.append(chain[-1])
    with pytest.raises(DeviceProofError):
        verify_attestation_chain(certificates_der=chain,public_key_pem=pem,policy=policy,extension=extension)


def test_application_identity_is_read_from_android_software_list_with_locked_hardware_boot():
    from test_owner_device_binding import _tagged
    packages = _der(0x31,_seq(_octet(b"com.dial.van"),_int(5)))
    digests = _der(0x31,_octet(bytes.fromhex("a"*64)))
    app = _tagged(709,_octet(_seq(packages,digests)))
    extension=_seq(_int(4),_int(1),_int(4),_int(1),_octet(b"challenge"),_octet(b""),
                   _seq(app),_seq(_root_of_trust(0)))
    assert verify_attestation(extension=extension,challenge=b"challenge",policy=_policy()).accepted


def test_verified_but_unlocked_boot_does_not_qualify():
    from test_owner_device_binding import _tagged
    root=_tagged(704,_seq(_octet(b"bootkey"),_der(0x01,b"\x00"),_int(0)))
    extension=_seq(_int(4),_int(1),_int(4),_int(1),_octet(b"challenge"),_octet(b""),
                   _seq(_application_id()),_seq(root))
    verdict=verify_attestation(extension=extension,challenge=b"challenge",policy=_policy())
    assert not verdict.accepted and verdict.refusal=="attestation_device_not_locked"
