from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generic_replayer_preserves_session_outbox_records():
    source = _read("android/app/src/main/java/com/dial/van/gateway/QueueReplayer.kt")
    assert "QueueReplayRoute.SESSION_OUTBOX -> continue" in source
    assert "SESSION_ENVELOPE" in source
    # The historical defect deleted every non-command record before the session restore.
    assert "if (!ReplayDispatchPolicy.mayDispatch(cmd.kind)) {\n                queue.remove(cmd.id)" not in source


def test_context_ingest_has_a_non_command_production_consumer():
    replayer = _read("android/app/src/main/java/com/dial/van/gateway/QueueReplayer.kt")
    client = _read("android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt")
    gateway = _read("backend/van_gateway/app.py")

    assert "QueueReplayRoute.CAPTURED_CONTEXT" in replayer
    assert "gateway.ingestCapturedContext(payload)" in replayer
    assert 'postProved("/v1/context/ingest", payload)' in client
    assert '@app.post("/v1/context/ingest")' in gateway
    assert '"authority": "NONE"' in gateway
    assert '"source_trust": "UNTRUSTED_EXTERNAL"' in gateway


def test_capture_producers_emit_stable_context_identity():
    notification = _read(
        "android/app/src/main/java/com/dial/van/notification/VanNotificationListenerService.kt"
    )
    share = _read("android/app/src/main/java/com/dial/van/share/ShareIntakeActivity.kt")
    assert 'put("context_id", "notif:$hash")' in notification
    assert 'put("context_id", "share:$shareId")' in share
