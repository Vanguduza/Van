from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_import_hermes_google_attestation(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "tools" / "google"))
    from import_hermes_google_attestation import import_attestation

    attestation = {
        "schema_version": 1,
        "host": "dial-hermes-control",
        "attested_at": "2026-09-15",
        "principal": {"subject": "hermes:test-owner", "account_kind": "personal", "ai_plan": "PRO"},
        "identity_alias": "owner_google_account",
        "flags": {
            "gemini_runtime_configured": True,
            "consumer_connected_capabilities": ["jules"],
        },
        "capabilities": [
            {"id": "gemini", "state": "CONFIGURED", "evidence": "hermes://test/gemini"},
            {"id": "jules", "state": "CONFIGURED", "evidence": "hermes://test/jules"},
        ],
    }
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(attestation), encoding="utf-8")
    db = tmp_path / "mesh.sqlite3"
    result = await import_attestation(path, str(db))
    assert result["ok"] is True
    assert result["principal_registered"] is True
    by_id = {item["capability_id"]: item for item in result["recorded"]}
    assert result["identity_alias"] == "owner_google_account"
    assert by_id["gemini"]["state"] == "CONFIGURED"
    assert by_id["jules"]["state"] == "CONFIGURED"


@pytest.mark.asyncio
async def test_import_delegated_antigravity_attestation(tmp_path):
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "tools" / "google"))
    from import_hermes_google_attestation import import_attestation

    attestation = {
        "schema_version": 1,
        "host": "dial-hermes-control",
        "attested_at": "2026-09-15",
        "identity_alias": "antigravity_worker_account",
        "principal": {"subject": "hermes:test-antigravity-worker", "account_kind": "personal", "ai_plan": "UNKNOWN"},
        "flags": {"consumer_connected_capabilities": ["antigravity"]},
        "capabilities": [
            {"id": "antigravity", "state": "READY", "evidence": "live://test/antigravity-worker"}
        ],
    }
    path = tmp_path / "delegated.json"
    path.write_text(json.dumps(attestation), encoding="utf-8")
    result = await import_attestation(path, str(tmp_path / "mesh.sqlite3"))
    assert result["identity_alias"] == "antigravity_worker_account"
    assert result["principal_registered"] is True
    assert result["recorded"] == [{"capability_id": "antigravity", "state": "READY", "evidence": "live://test/antigravity-worker"}]


@pytest.mark.asyncio
async def test_canonical_attestation_rejects_delegated_capability(tmp_path):
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "tools" / "google"))
    from import_hermes_google_attestation import import_attestation

    attestation = {
        "schema_version": 1,
        "host": "dial-hermes-control",
        "principal": {"subject": "hermes:test-owner"},
        "capabilities": [{"id": "antigravity", "state": "CONFIGURED", "evidence": "hermes://wrong-identity"}],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(attestation), encoding="utf-8")
    with pytest.raises(SystemExit, match="bound to antigravity_worker_account"):
        await import_attestation(path, str(tmp_path / "mesh.sqlite3"))
