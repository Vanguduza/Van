"""What the phone stores offline must be something the Gateway can accept.

The outbox holds a command as the payload of a session envelope, and the Gateway's
`command.submit` delegate turns that payload straight into a `CommandRequest`. If a
required field is missing the delegate refuses it as `command_payload_invalid` — hours
after the owner was told their work was saved, on a reconnect they are not watching.

That is a worse failure than losing the command outright, because nothing looks wrong
until it is too late to redo, and it is exactly what the first version of the C16b
storage path did: it stored `{text, action_class, idempotency_key}` and `CommandRequest`
requires `command_id`, `issued_at_unix` and `signature` as well.

Neither side can execute the other, so this reads the Kotlin builder's own `body.put`
calls and holds them against the Python model's required fields. Two languages, one
question: is the thing that gets written down a thing that can be delivered?
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt"
sys.path.insert(0, str(ROOT / "backend"))


def _builder_source() -> str:
    """Just `buildCommandBody`, so a `put` elsewhere in the file cannot stand in for one here."""
    source = CLIENT.read_text(encoding="utf-8")
    start = source.index("fun buildCommandBody(")
    end = source.index("suspend fun dispatchCommand(", start)
    return source[start:end]


def _fields_the_phone_writes() -> set[str]:
    fields = set(re.findall(r'\.put\(\s*"([a-z_]+)"', _builder_source()))
    assert fields, "no fields parsed from buildCommandBody — this test would pass vacuously"
    return fields


def _fields_the_gateway_requires() -> set[str]:
    from van_gateway.models import CommandRequest

    return {
        name
        for name, field in CommandRequest.model_fields.items()
        if field.is_required()
    }


def test_the_stored_body_carries_every_field_the_gateway_requires():
    writes = _fields_the_phone_writes()
    required = _fields_the_gateway_requires()
    # `device_id` is the one the Gateway supplies itself, from the authenticated session,
    # and a body that asserted its own would be asserting who it is.
    missing = required - writes - {"device_id"}
    assert not missing, (
        f"a command stored offline would be refused as command_payload_invalid on the "
        f"flush, because the phone never writes: {sorted(missing)}"
    )


def test_the_offline_path_stores_the_body_prepared_before_dispatch():
    """Guards the guard.

    The request builder remains authoritative, but a lost reply must retain that
    exact prepared request. Building a second signed body in the failure path
    changes the command identity, signature and issue time of a request that may
    already have reached the gateway.
    """
    controller = (
        ROOT / "android/app/src/main/java/com/dial/van/control/VanCommandController.kt"
    ).read_text(encoding="utf-8")
    dispatch_source = CLIENT.read_text(encoding="utf-8")
    dispatch = dispatch_source.index("suspend fun dispatchCommand(")
    publish = dispatch_source.index("private fun publishCommandVisualStatus(", dispatch)
    dispatched = dispatch_source[dispatch:publish]
    assert "val body = buildCommandBody(" in dispatched
    assert "val bodyText = body.toString()" in dispatched
    assert dispatched.index("onPreparedCommand(bodyText)") < dispatched.index("postRawAt(")
    assert re.search(r'postRawAt\(baseUrl,\s*"/v1/commands",\s*bodyText', dispatched)
    assert "onPreparedCommand = { preparedBody = it }" in controller
    assert "recordFailure(command, t, preparedBody)" in controller
    stored = controller.index("private fun storeSignedBody(")
    following = controller[stored:controller.index("fun reportUndelivered(", stored)]
    assert "OfflineSubmission.preparedReplay(preparedBody, command.idempotencyKey)" in following
    assert "return store(body, needsReconfirm)" in following
    assert "buildCommandBody(" not in following, "offline recovery must not re-sign an uncertain dispatch"


def test_the_signature_is_over_the_moment_the_owner_issued_it():
    """A stored command must not be re-signed on the way out.

    `issued_at_unix` is inside the canonical string, so signing at flush time would make
    a day-old instruction look fresh and defeat the Gateway's `owner_intent_max_age_seconds`
    refusal — the one rule that stops an offline replay running long after it meant
    anything.
    """
    assert '"issued_at_unix", issuedAtUnix' in _builder_source()
    orchestrator = (ROOT / "backend/van_gateway/orchestrator.py").read_text(encoding="utf-8")
    assert "command_age > self.owner_intent_max_age_seconds" in orchestrator
