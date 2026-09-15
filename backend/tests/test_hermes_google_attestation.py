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
        "flags": {
            "gemini_runtime_configured": True,
            "consumer_connected_capabilities": ["jules", "antigravity"],
        },
        "capabilities": [
            {"id": "gemini", "state": "CONFIGURED", "evidence": "hermes://test/gemini"},
            {"id": "jules", "state": "CONFIGURED", "evidence": "hermes://test/jules"},
            {
                "id": "antigravity",
                "state": "CAPACITY_LIMITED",
                "evidence": "live://antigravity/capacity_limited",
                "metadata": {"scope": "antigravity_only"},
            },
        ],
    }
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(attestation), encoding="utf-8")
    db = tmp_path / "mesh.sqlite3"
    result = await import_attestation(path, str(db))
    assert result["ok"] is True
    assert result["principal_registered"] is True
    by_id = {item["capability_id"]: item for item in result["recorded"]}
    assert by_id["gemini"]["state"] == "CONFIGURED"
    assert by_id["jules"]["state"] == "CONFIGURED"
    assert by_id["antigravity"]["state"] == "CAPACITY_LIMITED"
