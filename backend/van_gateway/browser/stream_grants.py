"""Rev 1.5 §5.5 — the short-lived grant the Browser Stream Runtime verifies.

The media path does not go through the Gateway (§6.4), so the stream host has to be able to
decide, on its own, whether the phone connecting to it is allowed to. That decision is made
from a signed grant rather than from a shared secret, for one reason: **the stream host is
the public-facing machine.** A symmetric key on it would let anyone who compromised the
media host mint their own grants; a public verifier lets them verify grants and nothing else.

The signing key is dedicated (§5.5). It is not the owner-approval key and not the device
enrolment key: three different questions, three different key planes, so compromising the
one that lives on the media path cannot approve an action or enrol a phone.

`kid` is mandatory and rotation keeps the previous verifier for an overlap window, because
a rotation that invalidates live grants disconnects the owner mid-session.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

from van_gateway.storage.db import Store

GRANT_AUDIENCE = "van-browser-stream-runtime"
GRANT_VERSION = 1

#: §5.5 — what a grant may authorise. Anything not in this set is not a scope, it is a typo,
#: and a typo that silently becomes "no scope" is how an unauthorised connection looks
#: authorised.
ALLOWED_SCOPES = frozenset({"webrtc.signal", "browser.view", "browser.owner_input"})

#: Short by design. The grant authorises a connection, not a session: the session's life is
#: governed by the profile lease, and a long-lived grant would let a stolen one be redeemed
#: long after the owner closed the tab.
DEFAULT_TTL_MS = 120_000


class StreamGrantError(Exception):
    pass


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


@dataclass(frozen=True)
class SigningKey:
    """The Gateway's half. The private key never leaves the Gateway host (§5.5)."""

    kid: str
    private_pem: str

    def key(self) -> ec.EllipticCurvePrivateKey:
        loaded = serialization.load_pem_private_key(self.private_pem.encode("utf-8"), password=None)
        if not isinstance(loaded, ec.EllipticCurvePrivateKey):
            raise StreamGrantError("stream_grant_key_not_ec")
        if loaded.curve.name != "secp256r1":
            raise StreamGrantError(f"stream_grant_key_wrong_curve:{loaded.curve.name}")
        return loaded

    def public_pem(self) -> str:
        return (
            self.key()
            .public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )


def generate_signing_key(kid: str) -> SigningKey:
    """Used by provisioning and by tests. Production keys are generated once, off this path."""
    private = ec.generate_private_key(ec.SECP256R1())
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return SigningKey(kid=kid, private_pem=pem)


class StreamGrantSigner:
    """Mints grants. Lives on the Gateway.

    The envelope is a compact JWS with ES256, which is the same algorithm family VAN already
    uses for owner authority — a deliberate reuse of a reviewed primitive rather than a new
    bespoke token format on the one path that faces the internet.
    """

    def __init__(self, key: SigningKey) -> None:
        self.key = key

    def sign(self, claims: dict[str, Any]) -> str:
        header = {"alg": "ES256", "typ": "JWT", "kid": self.key.kid}
        signing_input = (
            _b64u(json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
            + "."
            + _b64u(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode())
        )
        der = self.key.key().sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = asym_utils.decode_dss_signature(der)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return f"{signing_input}.{_b64u(raw)}"


class StreamGrantVerifier:
    """The stream host's half: public keys only, by `kid`.

    §5.5 requires a rotation overlap — current plus immediately previous — and requires the
    old key to be rejected after it. Both halves matter: without the overlap a rotation
    disconnects whoever is mid-session, and without the expiry a compromised old key stays
    valid forever because nothing ever says it stopped.
    """

    def __init__(self, public_pems: dict[str, str]) -> None:
        if not public_pems:
            raise StreamGrantError("stream_grant_verifier_has_no_keys")
        self.public_pems = dict(public_pems)

    def verify(self, token: str, *, now_ms: int | None = None) -> dict[str, Any]:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        try:
            header_b64, claims_b64, signature_b64 = token.split(".")
        except ValueError as exc:
            raise StreamGrantError("stream_grant_malformed") from exc

        header = json.loads(_b64u_decode(header_b64))
        if header.get("alg") != "ES256":
            # "alg" is attacker-controlled input until it has been checked against what this
            # verifier will actually accept. Accepting whatever it says is the classic JWS
            # confusion, and "none" is the version of it that needs no key at all.
            raise StreamGrantError("stream_grant_algorithm_not_accepted")
        kid = header.get("kid")
        if not kid:
            raise StreamGrantError("stream_grant_missing_kid")
        pem = self.public_pems.get(kid)
        if pem is None:
            raise StreamGrantError(f"stream_grant_unknown_kid:{kid}")

        raw = _b64u_decode(signature_b64)
        if len(raw) != 64:
            raise StreamGrantError("stream_grant_signature_malformed")
        der = asym_utils.encode_dss_signature(
            int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
        )
        public = serialization.load_pem_public_key(pem.encode("utf-8"))
        try:
            public.verify(der, f"{header_b64}.{claims_b64}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise StreamGrantError("stream_grant_signature_invalid") from exc

        claims = json.loads(_b64u_decode(claims_b64))
        if claims.get("version") != GRANT_VERSION:
            raise StreamGrantError("stream_grant_version_unsupported")
        if claims.get("aud") != GRANT_AUDIENCE:
            raise StreamGrantError("stream_grant_wrong_audience")
        if int(claims.get("expires_at_ms", 0)) <= now:
            raise StreamGrantError("stream_grant_expired")
        if int(claims.get("issued_at_ms", 0)) > now + 60_000:
            # A grant from the future is either a clock problem or a forgery attempt, and
            # accepting it would extend its usable life by the skew.
            raise StreamGrantError("stream_grant_issued_in_the_future")
        unknown = set(claims.get("scope") or []) - ALLOWED_SCOPES
        if unknown:
            raise StreamGrantError(f"stream_grant_unknown_scope:{sorted(unknown)[0]}")
        return claims


class StreamGrantService:
    """Mints, records and redeems grants.

    The database row is what makes a grant one-time. The signature says "the Gateway issued
    this"; only the `nonce` unique index says "and it has not been used yet", which is the
    difference between a credential and a capability someone can copy off a screen.
    """

    def __init__(self, store: Store, signer: StreamGrantSigner) -> None:
        self.store = store
        self.signer = signer

    async def mint(
        self,
        *,
        session_id: str,
        device_id: str,
        profile_alias: str,
        scope: list[str],
        max_width: int,
        max_height: int,
        max_fps: int,
        ttl_ms: int = DEFAULT_TTL_MS,
        now_ms: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        unknown = set(scope) - ALLOWED_SCOPES
        if unknown:
            raise StreamGrantError(f"stream_grant_unknown_scope:{sorted(unknown)[0]}")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        grant_id = f"bsg_{uuid.uuid4().hex}"
        nonce = secrets.token_urlsafe(24)
        claims = {
            "version": GRANT_VERSION,
            "grant_id": grant_id,
            "kid": self.signer.key.kid,
            "session_id": session_id,
            "device_id": device_id,
            "profile_alias": profile_alias,
            "aud": GRANT_AUDIENCE,
            "scope": sorted(scope),
            "issued_at_ms": now,
            "expires_at_ms": now + ttl_ms,
            "nonce": nonce,
            "max_width": max_width,
            "max_height": max_height,
            "max_fps": max_fps,
        }
        await self.store.execute(
            """
            INSERT INTO browser_stream_grants(
              grant_id, session_id, device_id, kid, profile_alias, scope_json, nonce,
              issued_at_ms, expires_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                grant_id, session_id, device_id, self.signer.key.kid, profile_alias,
                Store.dumps(sorted(scope)), nonce, now, now + ttl_ms,
            ),
        )
        return self.signer.sign(claims), claims

    async def redeem(self, *, nonce: str, now_ms: int | None = None) -> str:
        """Single use. The second redemption of a nonce is refused, not logged and allowed.

        A grant redeemed twice is either a replay or a copy of the owner's phone, and both
        are the case this exists to stop.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE browser_stream_grants
                   SET redeemed_at_ms = ?
                 WHERE nonce = ? AND redeemed_at_ms IS NULL AND revoked_at_ms IS NULL
                   AND expires_at_ms > ?
                """,
                (now, nonce, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise StreamGrantError("stream_grant_not_redeemable")
            cur = await db.execute(
                "SELECT session_id FROM browser_stream_grants WHERE nonce = ?", (nonce,)
            )
            row = await cur.fetchone()
        return str(row["session_id"])

    async def revoke_for_session(self, session_id: str, *, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE browser_stream_grants SET revoked_at_ms = ? "
            "WHERE session_id = ? AND redeemed_at_ms IS NULL AND revoked_at_ms IS NULL",
            (now, session_id),
        )
