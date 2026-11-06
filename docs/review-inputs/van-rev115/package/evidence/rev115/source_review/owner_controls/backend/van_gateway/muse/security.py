"""Transport authentication, distinct from owner approval and from source evidence."""
from __future__ import annotations
import base64
import hmac
import json
import os
import stat
from datetime import datetime
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from .models import MuseError, canonical, digest


def protected_read(path: str, *, secret: bool = True) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            meta = os.fstat(fd)
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid not in (0, os.getuid()) or meta.st_size > 65536 or meta.st_mode & (0o077 if secret else 0o022):
                raise MuseError("muse_configuration_permissions", 503)
            return os.read(fd, 65537)
        finally:
            os.close(fd)
    except OSError as exc:
        raise MuseError("muse_configuration_unavailable", 503) from exc


def require_relay(path: str, presented: str):
    value = protected_read(path).decode().strip()
    if len(value) < 32 or len(value) > 512 or any(ch.isspace() for ch in value):
        raise MuseError("muse_relay_credential_invalid", 503)
    if not presented or not hmac.compare_digest(value, presented):
        raise MuseError("muse_relay_unauthorized", 403)


def signer(path: str):
    raw = protected_read(path)
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (TypeError, ValueError) as exc:
        raise MuseError("muse_signer_invalid", 503) from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise MuseError("muse_signer_invalid", 503)
    def sign(envelope):
        sig = key.sign(canonical(envelope).encode())
        return {"envelope": envelope, "signature": base64.urlsafe_b64encode(sig).decode().rstrip("=")}
    return sign


SITE_OPERATIONS = frozenset({"muse_interaction_read", "muse_interaction_events", "muse_interaction_action", "muse_interaction_receipt"})


def verify_site(body: dict, policy_file: str, now_ms: int):
    try:
        policy = json.loads(protected_read(policy_file, secret=False))
        if policy.get("enabled") is not True or set(policy.get("allowed_operations", [])) - SITE_OPERATIONS:
            raise ValueError()
        if set(body) != {"envelope", "signature"}:
            raise ValueError()
        e = body["envelope"]
        expected = {"schema_version", "principal", "authority_class", "audience", "site_origin", "subject", "policy_generation", "command_id", "operation", "arguments", "payload_hash", "issued_at", "expires_at", "nonce"}
        if not isinstance(e, dict) or set(e) != expected or e["schema_version"] != 1:
            raise ValueError()
        if e["principal"] != "MUSE_SITE_OWNER" or e["authority_class"] != "OWNER_SITE_MUSE_TYPED":
            raise ValueError()
        for field in ("audience", "site_origin", "subject", "policy_generation"):
            if e[field] != policy[field]:
                raise ValueError()
        if e["operation"] not in policy["allowed_operations"] or e["payload_hash"] != digest({"operation":e["operation"], "arguments":e["arguments"]}):
            raise ValueError()
        issued = int(datetime.fromisoformat(e["issued_at"].replace("Z", "+00:00")).timestamp()*1000)
        expires = int(datetime.fromisoformat(e["expires_at"].replace("Z", "+00:00")).timestamp()*1000)
        if not issued <= now_ms + 5000 or not now_ms < expires or not 0 < expires-issued <= 120000:
            raise ValueError()
        raw = policy["public_key"]
        if isinstance(raw, dict):
            if raw.get("kty") != "OKP" or raw.get("crv") != "Ed25519" or "d" in raw:
                raise ValueError()
            raw = raw["x"]
        pub = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(raw + "="*(-len(raw)%4)))
        sig = body["signature"]
        pub.verify(base64.urlsafe_b64decode(sig + "="*(-len(sig)%4)), canonical(e).encode())
        if not isinstance(e["arguments"], dict):
            raise ValueError()
        return e
    except MuseError:
        raise
    except Exception as exc:
        raise MuseError("muse_site_signature_invalid", 403) from exc
