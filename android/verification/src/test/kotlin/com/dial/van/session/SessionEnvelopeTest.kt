package com.dial.van.session

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue
import org.json.JSONObject

/**
 * Rev 1.5 §§20.4, 20.9, 20.12 — the envelope, and the two things a failover must not do.
 *
 * `tests/contracts/test_cross_language_vectors.py` checks the digest and the field names
 * against the gateway. These check the behaviour the gateway cannot see: what the phone
 * does with a message it has already sent once.
 */
class SessionEnvelopeTest {

    private fun payload() = JSONObject().put("text", "book the flight").put("urgency", 2)

    private fun envelope(pathEpoch: Int = 0) = SessionEnvelope.build(
        messageId = "msg_1",
        vanSessionId = "vs_1",
        sessionEpoch = 3,
        pathEpoch = pathEpoch,
        deviceId = "s24",
        kind = "command.submit",
        createdAtMs = 1_700_000_000_000,
        payload = payload(),
        idempotencyKey = "idem_1",
    )

    @Test
    fun `the digest is computed from the payload rather than taken on trust`() {
        val built = envelope()
        assertEquals(
            SessionEnvelope.payloadDigest(payload()),
            built.getString("payload_digest"),
        )
    }

    @Test
    fun `a different payload digests differently`() {
        val other = JSONObject().put("text", "cancel the flight").put("urgency", 2)
        assertNotEquals(
            SessionEnvelope.payloadDigest(payload()),
            SessionEnvelope.payloadDigest(other),
        )
    }

    @Test
    fun `key order in the payload does not change the digest`() {
        // The same command built two different ways is one command. If it were not, a
        // resend after a reconnect would be admitted as new work.
        val a = JSONObject().put("text", "x").put("urgency", 2)
        val b = JSONObject().put("urgency", 2).put("text", "x")
        assertEquals(SessionEnvelope.payloadDigest(a), SessionEnvelope.payloadDigest(b))
    }

    @Test
    fun `re-addressing a message after a failover keeps its identity`() {
        // §20.12 — this is the whole reason `readdress` exists instead of calling `build`
        // again. A new message id or a new idempotency key here turns one owner command
        // into two, and the only place it shows up is a real failover on a real network.
        val original = envelope(pathEpoch = 0)
        val moved = SessionEnvelope.readdress(original, pathEpoch = 1)

        assertEquals(1, moved.getInt("path_epoch"))
        assertEquals(original.getString("message_id"), moved.getString("message_id"))
        assertEquals(original.getString("idempotency_key"), moved.getString("idempotency_key"))
        assertEquals(original.getString("payload_digest"), moved.getString("payload_digest"))
        assertEquals(original.getInt("session_epoch"), moved.getInt("session_epoch"))
    }

    @Test
    fun `re-addressing does not mutate the message it was given`() {
        val original = envelope(pathEpoch = 0)
        SessionEnvelope.readdress(original, pathEpoch = 7)
        assertEquals(0, original.getInt("path_epoch"))
    }

    @Test
    fun `optional identifiers are absent rather than null`() {
        // A null `command_id` on the wire is not the same as no command id: one asserts
        // that this message has none, the other leaves the gateway's default in place.
        val built = envelope()
        assertTrue(!built.has("command_id"))
        assertTrue(!built.has("turn_id"))
    }
}

class ResumePolicyTest {

    @Test
    fun `the same epoch is a plain resume`() {
        assertEquals(ResumeOutcome.RESUMED, ResumePolicy.classify(4, 4, null))
    }

    @Test
    fun `a higher server epoch means anything unacknowledged must go again`() {
        assertEquals(ResumeOutcome.RESUMED_WITH_NEW_EPOCH, ResumePolicy.classify(4, 5, null))
    }

    @Test
    fun `an unknown session is replaced rather than silently emptied`() {
        assertEquals(ResumeOutcome.SESSION_REPLACED, ResumePolicy.classify(4, null, "session_unknown"))
    }

    @Test
    fun `a gateway that has gone backwards is refused`() {
        // A restored-from-backup gateway with an older epoch would otherwise be replayed
        // into, re-running work the owner has already watched finish.
        assertEquals(ResumeOutcome.REFUSED, ResumePolicy.classify(9, 4, null))
    }

    @Test
    fun `a refusal the device cannot fix is not retried as a resume`() {
        assertEquals(ResumeOutcome.REFUSED, ResumePolicy.classify(4, 4, "session_device_mismatch"))
    }

    @Test
    fun `only unacknowledged events are resent`() {
        assertEquals(
            listOf(5L, 6L, 7L),
            ResumePolicy.unacknowledged(listOf(7L, 3L, 5L, 4L, 6L), lastServerAckSeq = 4L),
        )
    }

    @Test
    fun `the last acknowledged event is not sent again`() {
        // Off by one in either direction: the owner's last message is lost, or it is sent
        // twice. Both are silent.
        assertEquals(emptyList(), ResumePolicy.unacknowledged(listOf(1L, 2L), 2L))
        assertEquals(listOf(2L), ResumePolicy.unacknowledged(listOf(1L, 2L), 1L))
    }
}
