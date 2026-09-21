"""Rev 1.5 §0D.2 and ADR-RB-024/027 — connectivity is signed configuration, not a form.

The owner production build exposes no editable Gateway URL, no Hermes URL, no pairing token
and no certificate pin. §0D.2 lists them because each one is a field an attacker would love
the owner to fill in: a phishing page that persuades someone to retype a "new server
address" is a complete compromise of an assistant that holds their mail, their calendar and
their money.

So endpoints arrive as a manifest signed by a pinned authority key, and the device verifies
it before believing a word of it. Rotation is a new signed manifest with a higher version;
a broken endpoint is repaired by configuration or by a new build, never by asking the owner
to type a hostname.

Two rules the verifier enforces that are easy to leave out:

* **A manifest may not go backwards.** Accepting a lower version lets an attacker who
  captured an old manifest roll the device back to an endpoint they have since taken over.
* **`kid` must be known before the signature is checked.** An unknown key is a refusal, not
  an invitation to try every key we have.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from enum import Enum

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

from van_gateway.storage.db import Store

MANIFEST_VERSION_FIELD = "manifest_version"


class ManifestStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    #: Signed and stored but not yet in force: a manifest can be staged before a cutover.
    STAGED = "STAGED"


class ConnectivityError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SignedManifest:
    version_id: str
    manifest_version: int
    manifest_json: str
    signature: str
    signing_kid: str
    manifest_sha256: str
    status: ManifestStatus
    issued_at_ms: int


def canonical_manifest(manifest: dict) -> bytes:
    """Sorted keys, no whitespace. Two processes must agree on the bytes they sign."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(manifest: dict, *, private_pem: str) -> str:
    key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ConnectivityError("connectivity_key_not_ec")
    der = key.sign(canonical_manifest(manifest), ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(der)
    return (r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex()


def verify_manifest(
    manifest: dict,
    signature_hex: str,
    *,
    trusted_keys: dict[str, str],
    kid: str,
    minimum_version: int = 0,
) -> None:
    """What the device does before believing an endpoint. Raises with a named reason.

    Implemented here as well as on the device because the Gateway is where a staged
    manifest is checked before it is ever served: shipping an unverifiable manifest to the
    phone would strand it, and the phone is the one place that cannot be fixed remotely.
    """
    if kid not in trusted_keys:
        raise ConnectivityError("connectivity_manifest_unknown_kid")
    version = int(manifest.get(MANIFEST_VERSION_FIELD, 0))
    if version <= 0:
        raise ConnectivityError("connectivity_manifest_unversioned")
    if version < minimum_version:
        # Rollback protection. An old manifest is perfectly signed and points at an
        # endpoint that may now belong to somebody else.
        raise ConnectivityError("connectivity_manifest_rollback")

    raw = bytes.fromhex(signature_hex)
    if len(raw) != 64:
        raise ConnectivityError("connectivity_manifest_signature_malformed")
    der = asym_utils.encode_dss_signature(
        int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
    )
    public = serialization.load_pem_public_key(trusted_keys[kid].encode("utf-8"))
    try:
        public.verify(der, canonical_manifest(manifest), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise ConnectivityError("connectivity_manifest_signature_invalid") from exc


#: §0D.2's forbidden fields, as a set the tests and the service both read. A manifest that
#: carries a pairing token or a device id is not configuration — it is a credential in a
#: file the device caches, and it would survive being copied to another phone.
FORBIDDEN_MANIFEST_FIELDS = frozenset({
    "pairing_token", "device_token", "device_id", "ingress_token", "hermes_token",
    "internal_control_token", "access_token", "refresh_token", "client_secret",
})


class ConnectivityConfigService:
    def __init__(self, store: Store, *, private_pem: str | None = None, kid: str = "") -> None:
        self.store = store
        self.private_pem = private_pem
        self.kid = kid

    async def publish(
        self, manifest: dict, *, activate: bool = True, now_ms: int | None = None
    ) -> SignedManifest:
        """Sign, store, and optionally cut over.

        The version must move forward here too: a Gateway that republishes version 3 after
        version 4 would strand every device that has already refused the rollback.
        """
        if self.private_pem is None or not self.kid:
            raise ConnectivityError("connectivity_signing_unconfigured")
        leaked = FORBIDDEN_MANIFEST_FIELDS & set(manifest)
        if leaked:
            raise ConnectivityError(f"connectivity_manifest_carries_credential:{sorted(leaked)[0]}")
        version = int(manifest.get(MANIFEST_VERSION_FIELD, 0))
        if version <= 0:
            raise ConnectivityError("connectivity_manifest_unversioned")

        now = int(time.time() * 1000) if now_ms is None else now_ms
        current = await self.active()
        if current is not None and version <= current.manifest_version:
            raise ConnectivityError("connectivity_manifest_not_newer")

        raw = canonical_manifest(manifest)
        signature = sign_manifest(manifest, private_pem=self.private_pem)
        import hashlib

        record = SignedManifest(
            version_id=f"cfg_{uuid.uuid4().hex}",
            manifest_version=version,
            manifest_json=raw.decode("utf-8"),
            signature=signature,
            signing_kid=self.kid,
            manifest_sha256=hashlib.sha256(raw).hexdigest(),
            status=ManifestStatus.ACTIVE if activate else ManifestStatus.STAGED,
            issued_at_ms=now,
        )
        async with self.store.connection() as db:
            if activate:
                await db.execute(
                    "UPDATE connectivity_config_versions SET status = ?, retired_at_ms = ? "
                    "WHERE status = ?",
                    (ManifestStatus.RETIRED.value, now, ManifestStatus.ACTIVE.value),
                )
            await db.execute(
                """
                INSERT INTO connectivity_config_versions(
                  version_id, manifest_sha256, manifest_json, signature, signing_kid,
                  status, issued_at_ms, activated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.version_id, record.manifest_sha256, record.manifest_json,
                    record.signature, record.signing_kid, record.status.value,
                    now, now if activate else None,
                ),
            )
            await db.commit()
        return record

    async def active(self) -> SignedManifest | None:
        row = await self.store.fetchone(
            "SELECT * FROM connectivity_config_versions WHERE status = ?",
            (ManifestStatus.ACTIVE.value,),
        )
        if row is None:
            return None
        manifest = json.loads(row["manifest_json"])
        return SignedManifest(
            version_id=row["version_id"],
            manifest_version=int(manifest.get(MANIFEST_VERSION_FIELD, 0)),
            manifest_json=row["manifest_json"],
            signature=row["signature"],
            signing_kid=row["signing_kid"],
            manifest_sha256=row["manifest_sha256"],
            status=ManifestStatus(row["status"]),
            issued_at_ms=int(row["issued_at_ms"]),
        )

    async def serve(self, *, known_version: int = 0) -> dict | None:
        """GET /v1/connectivity/manifest — a newer manifest, or nothing.

        Returning the current one unconditionally would mean every poll re-verifies a
        signature the device already trusts, which is work the phone does not need to do.
        """
        current = await self.active()
        if current is None or current.manifest_version <= known_version:
            return None
        return {
            "manifest": json.loads(current.manifest_json),
            "signature": current.signature,
            "kid": current.signing_kid,
            "manifest_sha256": current.manifest_sha256,
        }
