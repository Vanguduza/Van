"""P0-TRADE-001: owner authority is a signature that is checked.

Every trading authority surface asked whether `owner_signature_ref` was a non-empty string
and every one of them accepted `"x"`. Mandate admission, kill-switch clear, owner halt,
capsule promotion, the commander's halt and the gateway's trading writes all shared it.

These tests are about the primitive. The surfaces have their own tests, each asserting that
the string that used to work no longer does.
"""

from __future__ import annotations

import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from conftest_owner_authority import OWNER_KEY_ID, OwnerAuthorityHarness, owner_keypair
from vati.authority import (
    MAX_ACT_LIFETIME_SECONDS,
    MAX_STANDING_LIFETIME_SECONDS,
    OwnerAuthorityError,
    OwnerAuthorityVerifier,
    build_token,
    canonical_statement,
    load_owner_keys,
    sign_token,
)


@pytest.fixture
def owner():
    return OwnerAuthorityHarness()


def _hand_built_token(owner, *, act, subject, issued, expires, nonce="forged-nonce"):
    """A correctly signed token with bounds the shipped signer would refuse to produce.

    The signer clamps lifetimes, so the verifier's own lifetime check can only be reached
    by a token built some other way — an older issuer, a different implementation, or
    somebody with the key and an intent. That is precisely the case worth testing.
    """
    from vati.authority import build_token

    statement = canonical_statement(
        act=act, subject=subject, issued_at_unix=issued, expires_at_unix=expires, nonce=nonce
    )
    signature = owner.key.sign(statement.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return build_token(
        act=act, subject=subject, issued_at_unix=issued, expires_at_unix=expires,
        nonce=nonce, key_id=OWNER_KEY_ID, signature=signature,
    )


class TestWhatUsedToPass:
    @pytest.mark.parametrize(
        "presented",
        ["", "   ", "x", "sig", "owner:sig", "sig:owner-device:abc123",
         "REPLACE_WITH_DEVICE_SIGNATURE_REF", None],
    )
    def test_a_reference_string_is_not_a_signature(self, owner, presented):
        with pytest.raises(OwnerAuthorityError):
            owner.verifier.verify(presented, act="owner-halt", subject="s-1")

    def test_something_shaped_like_a_token_is_not_one(self, owner):
        for shaped in ("van-oa1.aaa.bbb", "van-oa1..", "van-oa1.eyJhIjoxfQ.zzzz"):
            with pytest.raises(OwnerAuthorityError):
                owner.verifier.verify(shaped, act="owner-halt", subject="s-1")


class TestTheGrantIsBounded:
    def test_an_act_is_not_transferable(self, owner):
        token = owner.token(act="owner-halt", subject="s-1")
        with pytest.raises(OwnerAuthorityError, match="not this act"):
            owner.verifier.verify(token, act="kill-switch-clear", subject="s-1")

    def test_a_subject_is_not_transferable(self, owner):
        token = owner.token(act="owner-halt", subject="s-1")
        with pytest.raises(OwnerAuthorityError, match="not 's-2'"):
            owner.verifier.verify(token, act="owner-halt", subject="s-2")

    def test_an_expired_authority_is_refused(self, owner):
        token = owner.token(act="owner-halt", subject="s-1", issued_at_unix=1000)
        with pytest.raises(OwnerAuthorityError, match="expired"):
            owner.verifier.verify(token, act="owner-halt", subject="s-1", now_unix=100_000)

    def test_an_authority_from_the_future_is_refused(self, owner):
        token = owner.token(act="owner-halt", subject="s-1", issued_at_unix=100_000)
        with pytest.raises(OwnerAuthorityError, match="not valid yet"):
            owner.verifier.verify(token, act="owner-halt", subject="s-1", now_unix=1000)

    def test_an_over_long_act_lifetime_is_refused(self, owner):
        """An act that authorises itself for a month is a standing grant in disguise."""
        token = owner.token(
            act="owner-halt", subject="s-1", issued_at_unix=1000,
            lifetime_seconds=MAX_ACT_LIFETIME_SECONDS + 60,
        )
        with pytest.raises(OwnerAuthorityError, match="lifetime exceeds"):
            owner.verifier.verify(token, act="owner-halt", subject="s-1", now_unix=1100)

    def test_a_standing_document_may_be_longer_but_still_expires(self, owner):
        token = owner.token(
            act="mandate-admit", subject="m:1", issued_at_unix=1000,
            lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS,
        )
        verified = owner.verifier.verify(
            token, act="mandate-admit", subject="m:1", now_unix=2000,
            single_use=False, max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS,
        )
        assert verified.expires_at_unix == 1000 + MAX_STANDING_LIFETIME_SECONDS

        # The signer clamps, so an over-long token has to be forged by hand — which is
        # exactly the case the verifier's own check exists for.
        assert owner.token(
            act="mandate-admit", subject="m:1", issued_at_unix=1000,
            lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS * 10,
        ), "the signer should still produce a token, clamped"
        forged = _hand_built_token(
            owner, act="mandate-admit", subject="m:1", issued=1000,
            expires=1000 + MAX_STANDING_LIFETIME_SECONDS + 86400,
        )
        with pytest.raises(OwnerAuthorityError, match="lifetime exceeds"):
            owner.verifier.verify(
                forged, act="mandate-admit", subject="m:1", now_unix=2000,
                single_use=False, max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS,
            )


class TestTheKeyMatters:
    def test_a_key_this_host_does_not_hold_is_refused(self, owner):
        token = owner.stranger_token(act="owner-halt", subject="s-1")
        with pytest.raises(OwnerAuthorityError, match="signature is invalid"):
            owner.verifier.verify(token, act="owner-halt", subject="s-1")

    def test_an_unregistered_key_id_is_refused(self, owner):
        other, _ = owner_keypair()
        token = sign_token(other, act="owner-halt", subject="s-1", key_id="somebody-else")
        with pytest.raises(OwnerAuthorityError, match="not registered"):
            owner.verifier.verify(token, act="owner-halt", subject="s-1")

    def test_a_revoked_key_is_refused_even_though_the_signature_is_good(self, owner):
        verifier = OwnerAuthorityVerifier(
            {OWNER_KEY_ID: owner.pem}, revoked_key_ids=[OWNER_KEY_ID]
        )
        token = owner.token(act="owner-halt", subject="s-1")
        with pytest.raises(OwnerAuthorityError, match="not usable"):
            verifier.verify(token, act="owner-halt", subject="s-1")

    def test_an_empty_registry_authorises_nothing(self, owner):
        """A host nobody enrolled the owner's key on cannot halt or promote anything."""
        empty = OwnerAuthorityVerifier({})
        token = owner.token(act="owner-halt", subject="s-1")
        with pytest.raises(OwnerAuthorityError, match="not registered"):
            empty.verify(token, act="owner-halt", subject="s-1")

    def test_the_shipped_registry_holds_no_keys(self):
        """A committed key would be a private key's public half with no owner behind it."""
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "registries" / "owner_authority_keys.json"
        assert path.is_file()
        assert load_owner_keys(path) == {}


class TestAndroidWireParity:
    def test_android_vector_matches_python_token_bytes(self):
        import base64

        subject = "FX-TREND-PULLBACK-01:SHADOW:" + "a" * 64
        statement = canonical_statement(
            act="capsule-promote",
            subject=subject,
            issued_at_unix=1770000000,
            expires_at_unix=1770000300,
            nonce="nonce_-123",
        )
        assert statement == (
            "van-oa1|capsule-promote|" + subject
            + "|1770000000|1770000300|nonce_-123"
        )
        token = build_token(
            act="capsule-promote",
            subject=subject,
            issued_at_unix=1770000000,
            expires_at_unix=1770000300,
            nonce="nonce_-123",
            key_id="device-0123456789abcdef01234567",
            signature=bytes(range(1, 17)),
        )
        assert token == (
            "van-oa1."
            "eyJhY3QiOiJjYXBzdWxlLXByb21vdGUiLCJleHAiOjE3NzAwMDAzMDAsImlhdCI6MTc3MDAwMDAwMCwia2lkIjoiZGV2aWNlLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2NyIsIm5vbmNlIjoibm9uY2VfLTEyMyIsInN1YmplY3QiOiJGWC1UUkVORC1QVUxMQkFDSy0wMTpTSEFET1c6YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYSJ9."
            "AQIDBAUGBwgJCgsMDQ4PEA"
        )
        payload = token.split(".")[1]
        assert base64.urlsafe_b64decode(
            payload + "=" * (-len(payload) % 4)
        ).decode().startswith('{"act":"capsule-promote","exp":1770000300')


class TestReplay:
    def test_an_act_token_is_single_use(self, owner):
        token = owner.token(act="owner-halt", subject="s-1")
        owner.verifier.verify(token, act="owner-halt", subject="s-1")
        with pytest.raises(OwnerAuthorityError, match="already used"):
            owner.verifier.verify(token, act="owner-halt", subject="s-1")

    def test_a_failed_check_does_not_spend_the_token(self, owner):
        """Otherwise a wrong guess at the subject would burn the owner's authority."""
        token = owner.token(act="owner-halt", subject="s-1")
        with pytest.raises(OwnerAuthorityError):
            owner.verifier.verify(token, act="owner-halt", subject="s-2")
        assert owner.verifier.verify(token, act="owner-halt", subject="s-1").nonce

    def test_a_standing_document_may_be_read_repeatedly(self, owner):
        token = owner.token(act="mandate-admit", subject="m:1", issued_at_unix=1000,
                            lifetime_seconds=86400)
        for _ in range(3):
            owner.verifier.verify(
                token, act="mandate-admit", subject="m:1", now_unix=2000,
                single_use=False, max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS,
            )


class TestTheSignedStatement:
    def test_every_bound_on_the_grant_is_inside_the_signature(self):
        statement = canonical_statement(
            act="owner-halt", subject="s-1", issued_at_unix=10, expires_at_unix=20, nonce="n"
        )
        for bound in ("owner-halt", "s-1", "10", "20", "n"):
            assert bound in statement

    def test_tampering_with_the_payload_breaks_the_signature(self, owner):
        import base64
        import json

        token = owner.token(act="owner-halt", subject="s-1")
        prefix, payload, signature = token.split(".")
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        decoded["subject"] = "s-2"
        tampered = base64.urlsafe_b64encode(
            json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        with pytest.raises(OwnerAuthorityError):
            owner.verifier.verify(
                f"{prefix}.{tampered}.{signature}", act="owner-halt", subject="s-2"
            )

    def test_a_verified_authority_yields_a_reference_safe_to_record(self, owner):
        verified = owner.verifier.verify(
            owner.token(act="owner-halt", subject="s-1"), act="owner-halt", subject="s-1"
        )
        assert verified.ref.startswith("owner-authority:")
        assert "van-oa1" not in verified.ref, "the raw token must not end up in a ledger"
