"""Server-side derivation of a command's effective content trust.

The audit found that any application's notification could become a device-signed owner
command. The notification listener captured arbitrary app text, the queue replayer sent
the whole JSON payload as the command's `text`, and the Android client hardcoded
`context_trust = "CONVERSATION"` on every request. The gateway's prompt-injection screen
only ran when the client declared `UNTRUSTED`, so it never fired.

The defect was not the missing branch on the device. It was that **the device declared
its own trust level**. A cryptographic device signature proves which device sent the
envelope; it proves nothing about who authored the text inside it.

So trust is derived here, from the origin channel and the shape of the payload, and the
client's declaration can only ever *lower* it. A client that lies about its channel still
cannot raise trust, because channels that carry third-party content are pinned to
UNTRUSTED regardless of what arrives.
"""

from __future__ import annotations

import re

from van_gateway.models import ContentTrust, OriginChannel

#: Channels whose content originates outside the owner's own typing or speech. Anything
#: arriving on one of these is third-party data and is pinned UNTRUSTED. A device cannot
#: opt out: this mapping is not read from the request.
THIRD_PARTY_CHANNELS: frozenset[OriginChannel] = frozenset(
    {
        OriginChannel.NOTIFICATION_EVENT,
        OriginChannel.SHARE_INTENT,
        OriginChannel.AUTOMATION,
        OriginChannel.HERMES_EVENT,
        OriginChannel.SYSTEM_EVENT,
    }
)

#: Channels where the owner is the author. The owner authored the words, so the content
#: may be treated as conversation — but never higher. OWNER_SIGNED, PROJECT_TRUTH and the
#: other elevated tiers are gateway-side classifications and are not client-assertable.
OWNER_AUTHORED_CHANNELS: frozenset[OriginChannel] = frozenset(
    {
        OriginChannel.VOICE,
        OriginChannel.TEXT,
        OriginChannel.UI,
    }
)

#: The ceiling a client may claim on an owner-authored channel.
MAX_CLIENT_ASSERTABLE_TRUST = ContentTrust.CONVERSATION

#: Trust tiers ordered least to most authoritative, for ceiling comparisons.
_TRUST_ORDER: tuple[ContentTrust, ...] = (
    ContentTrust.UNTRUSTED,
    ContentTrust.CONVERSATION,
    ContentTrust.HERMES_MEMORY,
    ContentTrust.DETERMINISTIC_STATE,
    ContentTrust.CAPABILITY_GRANT,
    ContentTrust.PROJECT_TRUTH,
    ContentTrust.OWNER_SIGNED,
)

#: Markers that a payload is a serialized capture of third-party content rather than
#: something the owner typed. The notification listener emits `"untrusted_content": true`
#: and `"source": "notification"`; the share receiver emits its own envelope. If one of
#: these arrives claiming an owner-authored channel, the channel claim is not believed.
_CAPTURED_CONTENT_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r'"untrusted_content"\s*:\s*true', re.I),
    re.compile(r'"source"\s*:\s*"(?:notification|share|share_intent|clipboard)"', re.I),
    re.compile(r'"package"\s*:\s*"[a-z0-9_]+(?:\.[a-z0-9_]+)+"', re.I),
)


def _rank(trust: ContentTrust) -> int:
    try:
        return _TRUST_ORDER.index(trust)
    except ValueError:  # an unknown tier is treated as the least authoritative
        return 0


def looks_like_captured_content(text: str) -> bool:
    """True when the text is a serialized third-party capture, not owner prose.

    This is the belt to the channel's braces. The queue replayer's defect was that a
    notification envelope was dispatched with the JSON as the command text while the
    channel still said UI, so the channel alone would not have caught it.
    """
    return any(pattern.search(text) for pattern in _CAPTURED_CONTENT_MARKERS)


def derive_effective_trust(
    *,
    origin_channel: OriginChannel,
    declared_trust: ContentTrust,
    text: str,
) -> tuple[ContentTrust, str | None]:
    """Return the trust the gateway will actually enforce, and why it differs.

    The second element is a non-None reason whenever the derived trust is lower than what
    the client declared, so the downgrade is auditable rather than silent.
    """
    if origin_channel in THIRD_PARTY_CHANNELS:
        if declared_trust != ContentTrust.UNTRUSTED:
            return (
                ContentTrust.UNTRUSTED,
                f"origin_channel {origin_channel.value} carries third-party content; "
                f"declared {declared_trust.value} is not client-assertable",
            )
        return ContentTrust.UNTRUSTED, None

    if looks_like_captured_content(text):
        return (
            ContentTrust.UNTRUSTED,
            "payload carries captured third-party content markers; "
            f"declared {declared_trust.value} on channel {origin_channel.value} is not believed",
        )

    if _rank(declared_trust) > _rank(MAX_CLIENT_ASSERTABLE_TRUST):
        return (
            MAX_CLIENT_ASSERTABLE_TRUST,
            f"declared {declared_trust.value} exceeds the client-assertable ceiling "
            f"{MAX_CLIENT_ASSERTABLE_TRUST.value}",
        )

    return declared_trust, None
