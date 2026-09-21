package com.dial.van.session

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val NOW = 1_700_000_000_000L

private fun admit(
    actionClass: String = "A2",
    liveContext: Boolean = false,
    at: Long = NOW,
    ttl: Long = DurableOutbox.DEFAULT_TTL_MS,
) = DurableOutbox.admit(
    messageId = "msg_1",
    commandId = "cmd_1",
    idempotencyKey = "idem_1",
    turnId = "turn_1",
    actionClass = actionClass,
    requiresLiveOwnerContext = liveContext,
    payloadRef = "queue://1",
    nowMs = at,
    ttlMs = ttl,
)

/**
 * Rev 1.5 §§20.14, 20.15 — what the phone holds with no path, and the sentence that
 * shapes all of it: "A4/destructive actions do not silently execute hours later because
 * connectivity returned."
 */
class DurableOutboxTest {

    @Test
    fun `the record carries what section 20_14 asks for and not the payload`() {
        // `payloadRef`, not a payload. The command body is in the encrypted queue and has
        // no business in a metadata record that gets logged, compared and counted.
        val fields = OutboxEntry::class.java.declaredFields
            .filterNot { it.isSynthetic }
            .map { it.name }
            .toSet()
        assertEquals(
            setOf(
                "messageId", "commandId", "idempotencyKey", "turnId", "createdAtMs",
                "expiresAtMs", "storability", "actionClass", "requiresLiveOwnerContext",
                "payloadRef", "lastAttemptPath", "attemptCount", "reconfirmedAtMs",
            ),
            fields,
        )
    }

    @Test
    fun `an irreversible command is never stored at all`() {
        // The classification is not a flag on a stored record: there is no record. The
        // only way to keep an A4 is to not call `admit`, and no argument overrides it.
        assertNull(admit(actionClass = "A4"))
        assertNull(admit(actionClass = "A5"))
    }

    @Test
    fun `ordinary work is stored and flushes silently`() {
        val entry = assertNotNull(admit())
        assertEquals(CommandStorability.SAFE_TO_RETRY, entry.storability)
        assertTrue(DurableOutbox.flush(entry, NOW + 1_000) is FlushVerdict.Send)
    }

    @Test
    fun `something that needed the owner present is asked again`() {
        // "Read that back to me" replayed later is not the same request.
        val entry = assertNotNull(admit(liveContext = true))
        assertEquals(CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT, entry.storability)
        assertTrue(
            DurableOutbox.flush(entry, NOW + 1_000) is FlushVerdict.NeedsReconfirmation,
        )
    }

    @Test
    fun `an old but still valid command is asked about rather than sent`() {
        // Distinct from expiry, and the case §20.14 is really about: the command is still
        // reversible and still inside its TTL, and the owner has almost certainly
        // forgotten issuing it. Sending it silently is the surprise.
        val entry = assertNotNull(admit())
        assertTrue(DurableOutbox.flush(entry, NOW + 60_000) is FlushVerdict.Send)
        assertTrue(
            DurableOutbox.flush(entry, NOW + DurableOutbox.STALE_AFTER_MS)
                is FlushVerdict.NeedsReconfirmation,
        )
    }

    @Test
    fun `an expired command is dropped rather than asked about`() {
        // "Do you still want the thing you asked for four hours ago" is a worse question
        // than "that did not happen", so expiry is checked before reconfirmation.
        val entry = assertNotNull(admit(liveContext = true))
        val verdict = DurableOutbox.flush(entry, NOW + DurableOutbox.DEFAULT_TTL_MS)
        assertTrue(verdict is FlushVerdict.Expired, "$verdict")
    }

    @Test
    fun `a reconfirmed command flushes even though it is stale`() {
        val entry = DurableOutbox.reconfirm(assertNotNull(admit()), NOW + 40 * 60_000)
        assertTrue(
            DurableOutbox.flush(entry, NOW + 41 * 60_000) is FlushVerdict.Send,
        )
    }

    @Test
    fun `reconfirmation does not rewrite what kind of command it was`() {
        // What an audit of "why did this run at 11pm" needs to read is the original
        // classification, not a record that has been relabelled into looking ordinary.
        val entry = DurableOutbox.reconfirm(assertNotNull(admit(liveContext = true)), NOW + 1)
        assertEquals(CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT, entry.storability)
        assertEquals(NOW + 1, entry.reconfirmedAtMs)
    }

    @Test
    fun `reconfirmation cannot revive an expired command`() {
        val entry = DurableOutbox.reconfirm(assertNotNull(admit()), NOW + 1)
        assertTrue(
            DurableOutbox.flush(entry, NOW + DurableOutbox.DEFAULT_TTL_MS)
                is FlushVerdict.Expired,
        )
    }

    @Test
    fun `a NEVER_STORE entry that somehow exists is refused rather than sent`() {
        // `admit` cannot produce one. This is the belt for the case where something
        // bypassed it — a migration, a hand-built record, a future caller — because the
        // consequence is an irreversible action running from a queue.
        val entry = assertNotNull(admit()).copy(storability = CommandStorability.NEVER_STORE)
        val verdict = DurableOutbox.flush(entry, NOW + 1)
        assertTrue(verdict is FlushVerdict.Refused, "$verdict")
    }

    @Test
    fun `attempts are counted and the path recorded`() {
        // §20.14 asks for both. Three failures on one path is a different problem from
        // one failure on each of three.
        var entry = assertNotNull(admit())
        entry = DurableOutbox.attempted(entry, "wss")
        entry = DurableOutbox.attempted(entry, "h2")
        assertEquals(2, entry.attemptCount)
        assertEquals("h2", entry.lastAttemptPath)
    }

    @Test
    fun `depths are reported by what may be done with each item`() {
        // §20.15. A hundred SAFE_TO_RETRY is a network outage; one
        // REQUIRE_RECONFIRM_ON_RECONNECT is a person waiting to be asked something.
        val entries = listOfNotNull(
            admit(), admit(), admit(actionClass = "A3"), admit(liveContext = true),
        )
        assertEquals(
            mapOf(
                CommandStorability.SAFE_TO_RETRY to 2,
                CommandStorability.STORE_UNTIL_TTL to 1,
                CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT to 1,
            ),
            DurableOutbox.depthsByStorability(entries),
        )
    }

    @Test
    fun `queued never reads as submitted`() {
        // §20.15's whole point: the owner can tell the difference. Three surfaces
        // inventing their own wording is how they stop being able to.
        val queued = DurableOutbox.ownerReadableState(assertNotNull(admit()), NOW + 1)
        assertTrue(queued.startsWith("Queued"), queued)
        for (word in listOf("submitted", "running", "completed", "done", "sent")) {
            assertTrue(!queued.lowercase().contains(word), "$queued contains $word")
        }
    }

    @Test
    fun `every outcome has a sentence and none of them claims the work happened`() {
        val entries = listOf(
            assertNotNull(admit()) to NOW + 1,
            assertNotNull(admit()) to NOW + DurableOutbox.DEFAULT_TTL_MS,
            assertNotNull(admit(liveContext = true)) to NOW + 1,
            assertNotNull(admit()).copy(storability = CommandStorability.NEVER_STORE) to NOW + 1,
        )
        for ((entry, at) in entries) {
            val sentence = DurableOutbox.ownerReadableState(entry, at)
            assertTrue(sentence.isNotBlank())
            assertTrue(!sentence.lowercase().contains("completed"), sentence)
        }
    }
}
