from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generic_replayer_preserves_session_outbox_records():
    source = _read("android/app/src/main/java/com/dial/van/gateway/QueueReplayer.kt")
    # Both session work and unresolved/foreign kinds retain their original owner.
    # This arm must precede the generic command claim, not merely exist somewhere.
    replay = source[source.index("suspend fun replayNow()") : source.index("enum class QueueReplayRoute")]
    held = replay.index("QueueReplayRoute.SESSION_OUTBOX, QueueReplayRoute.UNKNOWN_HELD -> continue")
    context = replay.index("QueueReplayRoute.CAPTURED_CONTEXT -> {")
    command = replay.index("QueueReplayRoute.OWNER_COMMAND -> Unit")
    claim = replay.index("queue.claimGeneric(")
    assert held < context < command < claim
    assert "queue.remove(" not in replay
    assert "queue.purgeExpired(" not in replay
    context_branch = replay[context:command]
    assert "queue.finishCapturedContext(cmd, expiredOnly = true)" in context_branch
    assert context_branch.index("transport.ingestCapturedContext(") < context_branch.index("queue.finishCapturedContext(cmd)")
    assert "catch (cancelled: CancellationException) { throw cancelled }" in context_branch
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
