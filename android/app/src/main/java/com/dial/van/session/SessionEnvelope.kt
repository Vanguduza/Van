package com.dial.van.session

import com.dial.van.security.VanCanonicalJson
import org.json.JSONObject

/**
 * Rev 1.5 §20.4 — the transport-independent envelope, built on the device.
 *
 * The same bytes have to mean the same thing whether they arrive over the WebSocket, the
 * HTTP/2 fallback or the replay floor, because the Gateway admits them through one door
 * (§20.12). Two rules in here are the ones that actually do work:
 *
 *  * `payloadDigest` is computed from the payload, never asserted by the caller. The
 *    Gateway recomputes it and refuses a mismatch; a device that guessed would have its
 *    own command dropped later as a duplicate of something it never sent.
 *  * `idempotencyKey` is stable across a resend on a *different path*. A failover that
 *    minted a new key would turn one owner command into two, which is the failure §20.12
 *    exists to prevent and the one a healthy network never shows you.
 *
 * High-frequency browser input deliberately does not come through here: §20.4 keeps the
 * pixel-adjacent path out of the semantic envelope, and `BrowserInputProtocol` carries it.
 */
object SessionEnvelope {

    const val PROTOCOL_VERSION: Int = 1

    /**
     * The gateway's `Direction` enum, spelled its way. The first version of this file
     * said `DEVICE_TO_GATEWAY`, which reads better and is rejected by the envelope
     * validator — a cross-language contract test caught it before it shipped, which is
     * the whole reason that test reads the gateway's own vectors rather than a copy.
     */
    const val DIRECTION_UPSTREAM: String = "UPSTREAM"
    const val DIRECTION_DOWNSTREAM: String = "DOWNSTREAM"

    /**
     * The digest the Gateway compares on a resubmission.
     *
     * Canonical JSON, so a payload that was re-serialized on the way out — a different key
     * order, a reformatted number — still digests to the same value.
     */
    fun payloadDigest(payload: JSONObject): String = VanCanonicalJson.sha256Hex(payload)

    /**
     * @param idempotencyKey must be carried unchanged across retries and failovers. Pass
     *   the key from the first attempt, not a fresh one.
     */
    fun build(
        messageId: String,
        vanSessionId: String,
        sessionEpoch: Int,
        pathEpoch: Int,
        deviceId: String,
        kind: String,
        createdAtMs: Long,
        payload: JSONObject,
        idempotencyKey: String,
        turnId: String? = null,
        commandId: String? = null,
        correlationId: String? = null,
        expiresAtMs: Long? = null,
    ): JSONObject {
        val envelope = JSONObject()
            .put("protocol_version", PROTOCOL_VERSION)
            .put("message_id", messageId)
            .put("van_session_id", vanSessionId)
            .put("session_epoch", sessionEpoch)
            .put("path_epoch", pathEpoch)
            .put("device_id", deviceId)
            .put("direction", DIRECTION_UPSTREAM)
            .put("kind", kind)
            .put("created_at_ms", createdAtMs)
            .put("idempotency_key", idempotencyKey)
            .put("payload_digest", payloadDigest(payload))
            .put("payload", payload)
        turnId?.let { envelope.put("turn_id", it) }
        commandId?.let { envelope.put("command_id", it) }
        correlationId?.let { envelope.put("correlation_id", it) }
        expiresAtMs?.let { envelope.put("expires_at_ms", it) }
        return envelope
    }

    /**
     * The same message re-addressed to a new path after a failover (§20.9).
     *
     * Everything that identifies the *work* is preserved; only the path epoch moves. This
     * is deliberately not `build(...)` with a new id: re-minting `message_id` or
     * `idempotency_key` here is precisely how a failover doubles an owner's command.
     */
    fun readdress(envelope: JSONObject, pathEpoch: Int): JSONObject =
        JSONObject(envelope.toString()).put("path_epoch", pathEpoch)

    /**
     * The id a command stored before any session existed is addressed to.
     *
     * §20.14's whole case is a command issued with no network, and with no network there
     * is no `van_session_id` to build an envelope with — `/v1/session/open` is an HTTP
     * call. Refusing to store it, which is what `submit` did, means the owner loses the
     * instruction they gave in a tunnel: the exact failure the outbox exists to prevent.
     *
     * So it is stored addressed to nothing in particular and [rebind] stamps the real
     * session onto it when one exists. The placeholder is a constant rather than an empty
     * string so that a value which reached the wire by mistake is recognisable in a
     * Gateway log rather than looking like a field somebody forgot to set.
     */
    const val UNBOUND_SESSION_ID: String = "unbound"

    /**
     * Address a stored envelope to the session that now exists, keeping its identity.
     *
     * The mirror of [readdress], and separate from it for the same reason the path epoch
     * is: `message_id`, `idempotency_key` and `payload_digest` are untouched, so a Gateway
     * that has somehow seen this command already recognises it rather than running it
     * twice. What changes is where it is addressed, never what it says.
     */
    fun rebind(envelope: JSONObject, vanSessionId: String, sessionEpoch: Int): JSONObject =
        JSONObject(envelope.toString())
            .put("van_session_id", vanSessionId)
            .put("session_epoch", sessionEpoch)

    /** True for an envelope stored before there was a session to address it to. */
    fun isUnbound(envelope: JSONObject): Boolean =
        envelope.optString("van_session_id") == UNBOUND_SESSION_ID
}

/**
 * §20.9 — what the device may do with a session it is resuming.
 *
 * Resume is not reconnect. A reconnect that silently started a new session would lose the
 * turn the owner was in the middle of and show them an empty screen with no error, so the
 * cases are separated and named.
 */
enum class ResumeOutcome {
    /** Same session, same epoch: replay from `lastServerAckSeq` and carry on. */
    RESUMED,

    /** The Gateway bumped the epoch; anything unacknowledged must be re-submitted. */
    RESUMED_WITH_NEW_EPOCH,

    /** The session is gone. A new one is created and the owner is told, not shown a blank. */
    SESSION_REPLACED,

    /** Refused for a reason that a retry cannot change. */
    REFUSED,
}

object ResumePolicy {

    /**
     * @param serverEpoch the epoch the Gateway reports for this session, or null when it
     *   does not know the session at all.
     */
    fun classify(localEpoch: Int, serverEpoch: Int?, refusalReason: String?): ResumeOutcome = when {
        refusalReason != null && refusalReason != "session_unknown" -> ResumeOutcome.REFUSED
        serverEpoch == null -> ResumeOutcome.SESSION_REPLACED
        serverEpoch == localEpoch -> ResumeOutcome.RESUMED
        serverEpoch > localEpoch -> ResumeOutcome.RESUMED_WITH_NEW_EPOCH
        // A server epoch *behind* the device's is not a resume; it is a Gateway that has
        // been restored from an older state, and replaying into it would re-run work the
        // owner has already seen finish.
        else -> ResumeOutcome.REFUSED
    }

    /**
     * Which client events still need sending after a resume.
     *
     * Everything the Gateway has not acknowledged, and nothing it has. The off-by-one here
     * is the difference between losing the owner's last message and sending it twice.
     */
    fun unacknowledged(pending: List<Long>, lastServerAckSeq: Long): List<Long> =
        pending.filter { it > lastServerAckSeq }.sorted()
}
