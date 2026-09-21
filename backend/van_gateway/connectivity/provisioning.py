"""Rev 1.5 ADR-RB-026 and §0D.2 — the installer's one call, and nothing for the owner to type.

§0D.2 forbids the production build from exposing an editable Gateway URL or pairing token,
and ADR-RB-026 says why the alternative is not "hide the form": the first installation is
provisioned by the deployment pipeline, and the owner does not type URLs, tokens, IDs or
certificates. A field that asks for a server address is a phishing surface with the owner's
whole assistant behind it — anyone who gets a URL in front of them owns every command from
then on.

So the installer asks the Gateway for one signed payload and hands it to the device. The
payload carries where to connect and a one-time credential to enrol with, and it is signed
by the same pinned connectivity authority key the device already trusts for manifests —
reusing the trust anchor rather than adding a second one, because a second anchor is a
second thing that can be wrong.

It is a separate envelope from the manifest, though, and the reason is lifetime. A manifest
is long-lived, public configuration that rotates; this is single-use, short-lived and
carries a secret. Putting a bootstrap token in a manifest would make it exactly the
"credential in a file the device caches" that `FORBIDDEN_MANIFEST_FIELDS` exists to refuse.

**What this payload does not protect against, stated plainly.** The installer delivers it
over ADB, so it passes through a shell and may be visible in a device log. That is
tolerable only because of what ADR-RB-026 requires of it and this module enforces: it
expires in minutes, it binds to one bootstrap token that the Gateway consumes atomically on
first use, and the enrolment it authorises must be attested by a hardware-backed key that
whoever read the log does not have. A payload that were long-lived, or reusable, or
sufficient on its own to enrol, would not survive that channel — which is why none of those
three is negotiable here.
"""

from __future__ import annotations

import time
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

from van_gateway.connectivity.config import (
    ConnectivityError,
    canonical_manifest,
)

#: Bumped when the payload's fields change. The device refuses anything else rather than
#: parsing an unknown version as this one.
PROVISIONING_PAYLOAD_VERSION = 1

#: ADR-RB-026: "short-lived". Ten minutes is an installer run, not an afternoon.
#:
#: Deliberately far shorter than the bootstrap token's own hour-long TTL. The token is
#: consumed by the Gateway and can afford to outlive the installer; the payload travels
#: over a channel that logs, and it should be useless by the time anyone reads the log.
PROVISIONING_TTL_MS = 10 * 60_000

#: Fields a provisioning payload must never carry.
#:
#: The bootstrap and pairing tokens are deliberately absent from this list — carrying them
#: is the payload's whole job, and both are single-use and consumed atomically by the
#: Gateway. Note that `pairing_token` *is* forbidden in a connectivity manifest, and the
#: difference is not inconsistency: a manifest is long-lived public configuration that the
#: device caches and re-reads, so a token in one is a credential sitting in a file. This
#: envelope exists for minutes and is consumed once.
#:
#: What must not be here is anything that *survives* enrolment. An ingress token or a
#: device access token in a provisioning payload would be a standing credential delivered
#: over a logging channel, and no expiry on the envelope repairs a secret that outlives it.
FORBIDDEN_PAYLOAD_FIELDS = frozenset({
    "ingress_token", "device_access_token", "device_secret", "internal_control_token",
    "hermes_token", "access_token", "refresh_token", "client_secret", "private_key",
})


class ProvisioningError(ConnectivityError):
    """Named the same way as a manifest refusal, so one diagnostics screen reads both."""


def build_provisioning_payload(
    *,
    gateway_url: str,
    pairing_token: str,
    bootstrap_token: str,
    attestation_challenge: str,
    manifest_version: int = 0,
    now_ms: int | None = None,
    ttl_ms: int = PROVISIONING_TTL_MS,
) -> dict:
    """The document the installer hands the device. Signed by the caller, not here.

    `gateway_url` is required to be HTTPS. The one exception a debug build makes for
    loopback lives on the device, where a debug build can be told apart from a release one;
    a Gateway that relaxed it here would sign a payload a release build must refuse, and the
    installer would appear to succeed.
    """
    url = gateway_url.strip().rstrip("/")
    if not url.lower().startswith("https://"):
        raise ProvisioningError("provisioning_url_must_use_https")
    if len(pairing_token.strip()) < 32:
        raise ProvisioningError("provisioning_pairing_token_too_short")
    if len(bootstrap_token.strip()) < 32:
        raise ProvisioningError("provisioning_bootstrap_token_too_short")
    if not attestation_challenge.strip():
        raise ProvisioningError("provisioning_challenge_missing")

    now = int(time.time() * 1000) if now_ms is None else now_ms
    return {
        "payload_version": PROVISIONING_PAYLOAD_VERSION,
        "provisioning_id": f"prov_{uuid.uuid4().hex}",
        "gateway_url": url,
        # Two credentials because they buy two different things, and §0D.3 needs both:
        # the pairing token earns this device its ingress and access tokens, and the
        # bootstrap token authorises the hardware-attested binding that makes those
        # tokens useless on any other handset. A payload with only the first would
        # provision a phone that works anywhere.
        "pairing_token": pairing_token.strip(),
        "bootstrap_token": bootstrap_token.strip(),
        "attestation_challenge": attestation_challenge.strip(),
        # What manifest the device should expect to find. Not the manifest itself: the
        # device fetches and verifies that for itself, and a copy here would be a second
        # place the endpoints are stated.
        "expected_manifest_version": int(manifest_version),
        "issued_at_ms": now,
        "expires_at_ms": now + int(ttl_ms),
    }


def sign_provisioning_payload(payload: dict, *, private_pem: str) -> str:
    """The same curve, canonicalisation and encoding as a manifest signature.

    Sharing the scheme is the point: the device has one verifier, one trust anchor and one
    set of refusal reasons, so a payload that verifies here verifies there for the same
    reasons a manifest does.
    """
    leaked = FORBIDDEN_PAYLOAD_FIELDS & set(payload)
    if leaked:
        raise ProvisioningError(f"provisioning_carries_standing_credential:{sorted(leaked)[0]}")
    key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ProvisioningError("connectivity_key_not_ec")
    der = key.sign(canonical_manifest(payload), ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(der)
    return (r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex()


def verify_provisioning_payload(
    payload: dict,
    signature_hex: str,
    *,
    trusted_keys: dict[str, str],
    kid: str,
    now_ms: int | None = None,
) -> None:
    """What the device does. Implemented here too, and for the same reason the manifest is.

    The Gateway is the last place a bad payload can be caught before it reaches a phone,
    and the phone is the one component that cannot be fixed remotely.
    """
    if kid not in trusted_keys:
        raise ProvisioningError("provisioning_unknown_kid")
    if int(payload.get("payload_version", 0)) != PROVISIONING_PAYLOAD_VERSION:
        raise ProvisioningError("provisioning_payload_version_unsupported")
    leaked = FORBIDDEN_PAYLOAD_FIELDS & set(payload)
    if leaked:
        raise ProvisioningError(f"provisioning_carries_standing_credential:{sorted(leaked)[0]}")

    now = int(time.time() * 1000) if now_ms is None else now_ms
    expires = int(payload.get("expires_at_ms", 0))
    if expires <= 0:
        raise ProvisioningError("provisioning_payload_has_no_expiry")
    if now >= expires:
        raise ProvisioningError("provisioning_payload_expired")

    raw = bytes.fromhex(signature_hex)
    if len(raw) != 64:
        raise ProvisioningError("provisioning_signature_malformed")
    der = asym_utils.encode_dss_signature(
        int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
    )
    public = serialization.load_pem_public_key(trusted_keys[kid].encode("utf-8"))
    try:
        public.verify(der, canonical_manifest(payload), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise ProvisioningError("provisioning_signature_invalid") from exc
