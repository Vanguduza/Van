"""Owner authority fixtures for the trading suites (P0-TRADE-001).

Before this, "owner-signed" was a non-empty string, so a test could authorise anything by
passing "sig". Now a test has to hold the owner's key, which is the point: the tests
exercise the same path a real owner does.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vati.authority import OwnerAuthorityVerifier, sign_token

OWNER_KEY_ID = "owner-test-1"


def owner_keypair():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")
    return key, pem


class OwnerAuthorityHarness:
    """A registered owner key, the verifier that trusts it, and a way to sign an act."""

    def __init__(self) -> None:
        self.key, self.pem = owner_keypair()
        self.verifier = OwnerAuthorityVerifier({OWNER_KEY_ID: self.pem})

    def token(
        self,
        *,
        act: str,
        subject: str,
        issued_at_unix: int | None = None,
        lifetime_seconds: int = 300,
    ) -> str:
        return sign_token(
            self.key, act=act, subject=subject, key_id=OWNER_KEY_ID,
            issued_at_unix=issued_at_unix, lifetime_seconds=lifetime_seconds,
        )

    def stranger_token(
        self, *, act: str, subject: str, issued_at_unix: int | None = None
    ) -> str:
        """Signed by a key this host does not trust. Structurally perfect, and refused."""
        other, _ = owner_keypair()
        return sign_token(
            other, act=act, subject=subject, key_id=OWNER_KEY_ID,
            issued_at_unix=issued_at_unix,
        )
