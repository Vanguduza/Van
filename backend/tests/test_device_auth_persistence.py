from __future__ import annotations

import hashlib
import hmac

import pytest
from cryptography.fernet import Fernet

from van_gateway.auth.service import AuthError, AuthService
from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_device_credential_survives_gateway_restart_encrypted(tmp_path):
    db = tmp_path / "auth.sqlite3"
    key = Fernet.generate_key().decode()
    credential = "owner-device-test-material"
    canonical = "command|idem|device-1|1|A1||hello"

    store = Store(str(db))
    await store.migrate()
    first = AuthService(store, key)
    await first.enroll("device-1", credential, "PEM", "owner phone")

    row = await store.fetchone(
        "SELECT encrypted_secret FROM devices WHERE device_id = ?",
        ("device-1",),
    )
    assert row is not None
    ciphertext = str(row["encrypted_secret"])
    assert ciphertext
    assert credential not in ciphertext

    restarted = AuthService(store, key)
    assert await restarted.load_persisted_secrets() == 1
    expected = hmac.new(credential.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert restarted.sign("device-1", canonical) == expected
    restarted.verify_signature("device-1", canonical, expected)


@pytest.mark.asyncio
async def test_wrong_device_vault_key_fails_closed(tmp_path):
    db = tmp_path / "auth.sqlite3"
    store = Store(str(db))
    await store.migrate()
    first = AuthService(store, Fernet.generate_key().decode())
    await first.enroll("device-1", "test-material", "PEM")

    restarted = AuthService(store, Fernet.generate_key().decode())
    with pytest.raises(AuthError) as exc:
        await restarted.load_persisted_secrets()
    assert exc.value.code == "device_secret_decryption_failed"


@pytest.mark.asyncio
async def test_revoked_device_is_not_rehydrated(tmp_path):
    db = tmp_path / "auth.sqlite3"
    key = Fernet.generate_key().decode()
    store = Store(str(db))
    await store.migrate()
    first = AuthService(store, key)
    await first.enroll("device-1", "test-material", "PEM")
    await first.revoke("device-1")
    grant = await store.fetchone(
        "SELECT revoked_at_unix FROM capability_grants WHERE device_id = ?",
        ("device-1",),
    )
    assert grant is not None
    assert grant["revoked_at_unix"] is not None

    restarted = AuthService(store, key)
    assert await restarted.load_persisted_secrets() == 0
    with pytest.raises(AuthError) as exc:
        restarted.sign("device-1", "payload")
    assert exc.value.code == "secret_unavailable"
