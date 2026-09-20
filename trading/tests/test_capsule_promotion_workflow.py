"""Anti-gap tests for the owner strategy-promotion production join."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from conftest import passing_certificate
from conftest_owner_authority import OWNER_KEY_ID, OwnerAuthorityHarness
from commander.app import CommanderSettings, create_app
from commander.auth import sign_headers
from vati.authority import OwnerAuthorityVerifier
from vati.core import EventKind, Ledger
from vati.learning import Environment, LearningHooks
from vati.learning.replay import restore_learning_runtime
from vati.risk.contracts import StrategyState
from vati.strategies import CapsuleRegistry

REG = Path(__file__).resolve().parents[1] / "strategies" / "registry"
HERMES_TOKEN = "h" * 40
GATEWAY_TOKEN = "g" * 40


def _call(client, name, token, args):
    body = json.dumps({"args": args}).encode()
    headers = {
        **sign_headers(token, "POST", f"/v1/cmd/{name}", body),
        "content-type": "application/json",
    }
    return client.post(f"/v1/cmd/{name}", content=body, headers=headers)


def _fixture(tmp_path):
    capsules = tmp_path / "capsules"
    shutil.copytree(REG, capsules)
    ledger_path = tmp_path / "vati.sqlite"
    Ledger(ledger_path).close()
    owner = OwnerAuthorityHarness()
    now = int(time.time())
    reg = CapsuleRegistry.load_dir(capsules)
    current = reg.get("FX-TREND-PULLBACK-01")
    cert = passing_certificate(
        strategy_id=current.strategy_id,
        capsule_hash=current.capsule_hash,
    )
    token = owner.token(
        act="capsule-promote",
        subject=f"{current.strategy_id}:SHADOW:{cert.validation_hash}",
        issued_at_unix=now,
    )
    args = {
        "strategy_id": current.strategy_id,
        "target_state": "SHADOW",
        "owner_signature_ref": token,
        "certificate": cert.as_dict() | {"validation_hash": cert.validation_hash},
        "evidence_refs": ["artifact:test-validation"],
        "approved_at_unix": now,
    }
    settings = CommanderSettings(
        tokens={"hermes": HERMES_TOKEN, "van-gateway": GATEWAY_TOKEN},
        ledger=str(ledger_path),
        heartbeat_dir=str(tmp_path / "hb"),
        log_dir=str(tmp_path / "log"),
        data_dir=str(tmp_path / "data"),
        capsule_dir=str(capsules),
        _owner_authority=owner.verifier,
    )
    return capsules, ledger_path, owner, current.data, args, TestClient(create_app(settings))


def test_capsule_promotion_is_hidden_from_agents_and_committed_by_gateway(tmp_path):
    capsules, ledger_path, _owner, _original, args, client = _fixture(tmp_path)

    tools = client.get(
        "/v1/tools",
        headers=sign_headers(HERMES_TOKEN, "GET", "/v1/tools", b""),
    )
    assert tools.status_code == 200
    assert "capsule_promote" not in {x["name"] for x in tools.json()["tools"]}

    assert _call(client, "capsule_promote", HERMES_TOKEN, args).status_code == 403
    response = _call(client, "capsule_promote", GATEWAY_TOKEN, args)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["promoted"] is True
    assert result["from"] == "DEMO" and result["to"] == "SHADOW"
    assert result["validation_hash"] == args["certificate"]["validation_hash"]
    assert result["requires_session_restart"] is True

    projected = json.loads(
        (capsules / "FX-TREND-PULLBACK-01.json").read_text())
    assert projected["state"] == "SHADOW"
    assert projected["capsule_hash"] == result["capsule_hash"]

    ledger = Ledger(ledger_path)
    events = list(ledger.iter(EventKind.CAPSULE_STATE))
    assert len(events) == 1
    event = events[0]
    assert event.producer == "vati-capsule-promotion"
    assert event.payload["authority"] == "OWNER_SIGNED_PROMOTION"
    assert event.payload["validation_hash"] == result["validation_hash"]
    assert event.payload["capsule"]["capsule_hash"] == result["capsule_hash"]
    assert event.payload["owner_authority_ref"].startswith("owner-authority:")
    assert ledger.verify_chain()[0]


def test_promotion_token_replay_is_refused_after_commander_restart(tmp_path):
    capsules, ledger_path, owner, original, args, client = _fixture(tmp_path)
    first = _call(client, "capsule_promote", GATEWAY_TOKEN, args)
    assert first.status_code == 200, first.text

    # Simulate a crash after the authoritative ledger commit but before/during
    # registry projection by restoring the pre-promotion file.
    (capsules / "FX-TREND-PULLBACK-01.json").write_text(
        json.dumps(original, indent=2) + "\n"
    )

    fresh_verifier = OwnerAuthorityVerifier({OWNER_KEY_ID: owner.pem})
    fresh = TestClient(create_app(CommanderSettings(
        tokens={"hermes": HERMES_TOKEN, "van-gateway": GATEWAY_TOKEN},
        ledger=str(ledger_path),
        heartbeat_dir=str(tmp_path / "hb2"),
        log_dir=str(tmp_path / "log2"),
        data_dir=str(tmp_path / "data2"),
        capsule_dir=str(capsules),
        _owner_authority=fresh_verifier,
    )))
    replay = _call(fresh, "capsule_promote", GATEWAY_TOKEN, args)
    assert replay.status_code == 409
    assert "already been consumed" in replay.json()["detail"]
    assert Ledger(ledger_path).count(EventKind.CAPSULE_STATE) == 1

    # A different, otherwise valid authority cannot fork the stale file either:
    # ledger reconstruction makes SHADOW current before the certificate-parent check.
    second = dict(args)
    second["owner_signature_ref"] = owner.token(
        act="capsule-promote",
        subject=(
            "FX-TREND-PULLBACK-01:SHADOW:"
            + args["certificate"]["validation_hash"]
        ),
        issued_at_unix=args["approved_at_unix"],
    )
    fork = _call(fresh, "capsule_promote", GATEWAY_TOKEN, second)
    assert fork.status_code == 409
    assert "current strategy revision" in fork.json()["detail"]
    assert Ledger(ledger_path).count(EventKind.CAPSULE_STATE) == 1


def test_expired_promotion_token_cannot_be_revived_with_old_approval_timestamp(
    tmp_path, monkeypatch
):
    _capsules, ledger_path, _owner, _original, args, client = _fixture(tmp_path)
    original_approved_at = int(args["approved_at_unix"])

    # The old defect verified token expiry against this caller-supplied timestamp.
    # Advancing only the commander's trusted clock proves that replaying the old
    # timestamp cannot make an expired authority current again.
    monkeypatch.setattr(
        "commander.strategies.time.time",
        lambda: original_approved_at + 301,
    )
    replay = _call(client, "capsule_promote", GATEWAY_TOKEN, args)
    assert replay.status_code == 403
    assert "expired" in replay.json()["detail"]
    assert Ledger(ledger_path).count(EventKind.CAPSULE_STATE) == 0

    # Even when the caller updates the presentation timestamp to "now", the
    # original owner token itself is expired and must fail cryptographic policy.
    fresh_args = dict(args)
    fresh_args["approved_at_unix"] = original_approved_at + 301
    expired = _call(client, "capsule_promote", GATEWAY_TOKEN, fresh_args)
    assert expired.status_code == 403
    assert "expired" in expired.json()["detail"]
    assert Ledger(ledger_path).count(EventKind.CAPSULE_STATE) == 0


def test_ledgered_owner_promotion_repairs_missing_registry_projection_on_restart(tmp_path):
    capsules, ledger_path, _owner, original, args, client = _fixture(tmp_path)
    first = _call(client, "capsule_promote", GATEWAY_TOKEN, args)
    assert first.status_code == 200, first.text

    # Leave only the durable event authoritative.
    (capsules / "FX-TREND-PULLBACK-01.json").write_text(
        json.dumps(original, indent=2) + "\n"
    )
    registry = CapsuleRegistry.load_dir(capsules)
    engine = SimpleNamespace(
        registry=registry,
        m=SimpleNamespace(capsule_health={}, broker_liquidity={}),
    )
    hooks = LearningHooks(environment=Environment.LIVE, broker="zse")
    report = restore_learning_runtime(
        Ledger(ledger_path), hooks, {"DELTA": engine}
    )
    restored = registry.get("FX-TREND-PULLBACK-01")
    assert restored.state is StrategyState.SHADOW
    assert restored.capsule_hash == first.json()["result"]["capsule_hash"]
    assert report.owner_promotions_restored == 1


def test_stale_capsule_state_event_cannot_roll_newer_projection_backward(tmp_path):
    capsules, ledger_path, _owner, _original, args, client = _fixture(tmp_path)
    first = _call(client, "capsule_promote", GATEWAY_TOKEN, args)
    assert first.status_code == 200, first.text
    promoted = json.loads(
        (capsules / "FX-TREND-PULLBACK-01.json").read_text())

    # The ledger contains the legitimate promotion whose parent is the old DEMO
    # capsule. Loading the already-projected SHADOW capsule must not replay that
    # event as a second mutation or replace it with an older lineage state.
    registry = CapsuleRegistry.load_dir(capsules)
    engine = SimpleNamespace(
        registry=registry,
        m=SimpleNamespace(capsule_health={}, broker_liquidity={}),
    )
    report = restore_learning_runtime(
        Ledger(ledger_path),
        LearningHooks(environment=Environment.LIVE, broker="zse"),
        {"DELTA": engine},
    )
    assert registry.get("FX-TREND-PULLBACK-01").capsule_hash == promoted["capsule_hash"]
    assert report.owner_promotions_restored == 0
