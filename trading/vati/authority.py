"""Owner authority: a signature that is checked, not a string that is present.

P0-TRADE-001. Every trading authority surface asked the same question — "is
`owner_signature_ref` a non-empty string?" — and every one of them accepted `"x"`. Mandate
admission, kill-switch clear, owner halt, capsule promotion, the commander's halt and the
gateway's trading writes all shared the pattern. No algorithm, no key, no authority record,
no expiry, no revocation. Only PlatformCeilings bounded what an unsigned mandate could then
do.

This module is the one place that answers it properly, and both deployables use it: the
trading VM imports it directly, and the gateway already imports `vati` (see
`van_gateway/trading/service.py`), so there is one implementation rather than two that
drift.

The design is deliberately narrow, because a general-purpose token format invites a
general-purpose bypass:

  * **The act is inside the signature.** A token authorising a kill-switch clear cannot be
    replayed to halt trading or promote a strategy. The old refs were interchangeable
    because they meant nothing.
  * **So is the subject.** "Clear the kill switch" is not authority; "clear DAILY_LOSS on
    session s-1" is.
  * **Everything expires.** An authority with no expiry is a standing grant nobody decided
    to give (P2-SEC-008 is the same defect elsewhere).
  * **Single use.** A nonce is consumed on the first successful verification, so a token
    recovered from the ledger — where these are deliberately recorded in the clear — cannot
    be used again.
  * **No keys means no authority.** An empty registry fails every verification. Failing
    open here would reproduce the finding exactly: a check that is present and answers yes.

The token is readable on purpose. These end up in the ledger and in audit rows, and an
operator reading one should be able to see what was authorised without tooling.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableSet

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

PREFIX = "van-oa1"
ALGORITHM = "ECDSA_P256_SHA256"

#: A one-shot act — halt, clear, promote — is authorised for minutes. An authority that
#: outlives the decision it expresses is a standing grant nobody decided to give.
MAX_ACT_LIFETIME_SECONDS = 15 * 60

#: A standing document — a mandate — is re-read on every process start, so it is neither
#: one-shot nor short-lived. It still expires: ninety days is a review cycle, not a
#: formality, and P2-SEC-008 is exactly what happens when something is issued for ten
#: years because nobody wanted to think about renewal.
MAX_STANDING_LIFETIME_SECONDS = 90 * 24 * 3600

#: Retained under the old name for callers that predate the split.
MAX_LIFETIME_SECONDS = MAX_ACT_LIFETIME_SECONDS


class OwnerAuthorityError(PermissionError):
    """The authority is absent, malformed, unsigned, expired, reused, or for another act."""


@dataclass(frozen=True)
class OwnerAuthority:
    """What a verified token actually authorises."""

    act: str
    subject: str
    issued_at_unix: int
    expires_at_unix: int
    nonce: str
    key_id: str

    @property
    def ref(self) -> str:
        """A short, stable reference to record in a ledger entry."""
        return f"owner-authority:{self.key_id}:{self.nonce}"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical_statement(
    *, act: str, subject: str, issued_at_unix: int, expires_at_unix: int, nonce: str
) -> str:
    """Exactly what the owner's key signs. Every field that bounds the grant is in it."""
    return "|".join(
        [PREFIX, act, subject, str(int(issued_at_unix)), str(int(expires_at_unix)), nonce]
    )


def build_token(
    *,
    act: str,
    subject: str,
    issued_at_unix: int,
    expires_at_unix: int,
    nonce: str,
    key_id: str,
    signature: bytes,
) -> str:
    payload = {
        "act": act,
        "subject": subject,
        "iat": int(issued_at_unix),
        "exp": int(expires_at_unix),
        "nonce": nonce,
        "kid": key_id,
    }
    encoded = _b64u(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{PREFIX}.{encoded}.{_b64u(signature)}"


def sign_token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    act: str,
    subject: str,
    key_id: str,
    issued_at_unix: int | None = None,
    lifetime_seconds: int = 300,
    nonce: str | None = None,
) -> str:
    """Produce a token. Used by the owner's device and by tests; never by a server."""
    issued = int(time.time()) if issued_at_unix is None else int(issued_at_unix)
    expires = issued + min(int(lifetime_seconds), MAX_STANDING_LIFETIME_SECONDS)
    chosen_nonce = nonce or _b64u(os.urandom(12))
    statement = canonical_statement(
        act=act, subject=subject, issued_at_unix=issued,
        expires_at_unix=expires, nonce=chosen_nonce,
    )
    signature = private_key.sign(statement.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return build_token(
        act=act, subject=subject, issued_at_unix=issued, expires_at_unix=expires,
        nonce=chosen_nonce, key_id=key_id, signature=signature,
    )


def load_owner_keys(path: str | os.PathLike[str] | None = None) -> dict[str, str]:
    """Registered owner authority keys, by key id.

    An absent or empty registry is legal and means no owner authority can be verified,
    which fails every guarded operation closed. That is the intended behaviour on a host
    that has not been given the owner's public key, not a condition to work around.
    """
    candidate = Path(path) if path is not None else Path(
        os.environ.get("VAN_OWNER_AUTHORITY_KEYS", "")
        or Path(__file__).resolve().parents[2] / "registries" / "owner_authority_keys.json"
    )
    if not candidate.is_file():
        return {}
    data = json.loads(candidate.read_text(encoding="utf-8"))
    keys = data.get("keys", data) if isinstance(data, dict) else {}
    return {str(k): str(v) for k, v in keys.items() if str(v).strip()}


class OwnerAuthorityVerifier:
    """Verifies a token against a registered key, for one act on one subject."""

    def __init__(
        self,
        keys: Mapping[str, str] | None = None,
        *,
        consumed: MutableSet[str] | None = None,
        revoked_key_ids: Iterable[str] = (),
    ) -> None:
        self.keys = dict(keys) if keys is not None else load_owner_keys()
        # Single use is enforced here so that a caller that forgets to pass a store still
        # gets it for the life of the process, rather than silently getting nothing.
        self.consumed: MutableSet[str] = consumed if consumed is not None else set()
        self.revoked_key_ids = frozenset(revoked_key_ids)

    def verify(
        self,
        token: str | None,
        *,
        act: str,
        subject: str,
        now_unix: int | None = None,
        single_use: bool = True,
        max_lifetime_seconds: int = MAX_ACT_LIFETIME_SECONDS,
    ) -> OwnerAuthority:
        """Verify a token for one act on one subject.

        `single_use` is on by default because most acts are decisions made once. It is
        turned off only for a standing document, which is re-read every time the process
        starts; there the replay bound is the document's own expiry and the fact that the
        signature covers its version, so a widened mandate needs a new signature.
        """
        now = int(time.time()) if now_unix is None else int(now_unix)
        if not token or not str(token).strip():
            raise OwnerAuthorityError(
                f"{act} requires owner authority: no token supplied"
            )
        parts = str(token).strip().split(".")
        if len(parts) != 3 or parts[0] != PREFIX:
            raise OwnerAuthorityError(
                f"{act} requires owner authority: not a {PREFIX} token. "
                "A bare reference string is not a signature."
            )
        try:
            payload = json.loads(_unb64u(parts[1]))
            signature = _unb64u(parts[2])
        except (ValueError, json.JSONDecodeError) as exc:
            raise OwnerAuthorityError(f"{act}: owner authority is malformed") from exc

        key_id = str(payload.get("kid", ""))
        if not key_id or key_id in self.revoked_key_ids:
            raise OwnerAuthorityError(f"{act}: owner authority key {key_id!r} is not usable")
        pem = self.keys.get(key_id)
        if not pem:
            raise OwnerAuthorityError(
                f"{act}: owner authority key {key_id!r} is not registered on this host"
            )

        if str(payload.get("act", "")) != act:
            raise OwnerAuthorityError(
                f"{act}: owner authority is for {payload.get('act')!r}, not this act"
            )
        if str(payload.get("subject", "")) != subject:
            raise OwnerAuthorityError(
                f"{act}: owner authority is for {payload.get('subject')!r}, not {subject!r}"
            )

        issued = int(payload.get("iat", 0))
        expires = int(payload.get("exp", 0))
        if expires <= issued:
            raise OwnerAuthorityError(f"{act}: owner authority expires before it is issued")
        if expires - issued > max_lifetime_seconds:
            raise OwnerAuthorityError(
                f"{act}: owner authority lifetime exceeds {max_lifetime_seconds}s"
            )
        if now >= expires:
            raise OwnerAuthorityError(f"{act}: owner authority expired at {expires}")
        if now + 60 < issued:
            raise OwnerAuthorityError(f"{act}: owner authority is not valid yet")

        nonce = str(payload.get("nonce", ""))
        if not nonce:
            raise OwnerAuthorityError(f"{act}: owner authority carries no nonce")

        statement = canonical_statement(
            act=act, subject=subject, issued_at_unix=issued,
            expires_at_unix=expires, nonce=nonce,
        )
        try:
            public_key = serialization.load_pem_public_key(pem.encode("utf-8"))
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                raise OwnerAuthorityError(f"{act}: registered key {key_id!r} is not EC")
            public_key.verify(signature, statement.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise OwnerAuthorityError(f"{act}: owner authority signature is invalid") from exc
        except ValueError as exc:
            raise OwnerAuthorityError(f"{act}: owner authority could not be checked") from exc

        # Consumed last, so a token is only spent by a check it actually passed.
        if single_use:
            fingerprint = hashlib.sha256(f"{key_id}|{nonce}".encode("utf-8")).hexdigest()
            if fingerprint in self.consumed:
                raise OwnerAuthorityError(
                    f"{act}: owner authority was already used. These are recorded in the "
                    "ledger in the clear, so a single-use rule is what stops a replay."
                )
            self.consumed.add(fingerprint)

        return OwnerAuthority(
            act=act, subject=subject, issued_at_unix=issued, expires_at_unix=expires,
            nonce=nonce, key_id=key_id,
        )


__all__ = [
    "ALGORITHM",
    "MAX_ACT_LIFETIME_SECONDS",
    "MAX_LIFETIME_SECONDS",
    "MAX_STANDING_LIFETIME_SECONDS",
    "OwnerAuthority",
    "OwnerAuthorityError",
    "OwnerAuthorityVerifier",
    "PREFIX",
    "build_token",
    "canonical_statement",
    "load_owner_keys",
    "sign_token",
]
