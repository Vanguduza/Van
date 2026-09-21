package com.dial.van.session

import com.dial.van.queue.CommandKind
import com.dial.van.queue.CommandSensitivity
import com.dial.van.queue.QueuedCommand
import com.dial.van.queue.ReplayPolicy
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Rev 1.5 §20.14 — what survives the process being killed.
 *
 * For one checkpoint, nothing did. The outbox policy lived in an `ArrayDeque` inside
 * `VanHermesSessionManager` while `EncryptedCommandQueue` held commands on disk, so a
 * command could outlive the app and the metadata deciding whether it may be *silently
 * replayed* could not. Android kills backgrounded processes as a matter of routine; a
 * store-and-forward guarantee that does not survive that is a word.
 *
 * The tests below are about the three moments §20.14 needs to survive — admission,
 * reconfirmation, and the command leaving — and about the one thing a restore must never
 * do, which is guess.
 */
class OutboxPersistenceTest {

    private val NOW = 1_700_000_000_000L

    private fun entry(
        actionClass: String = "A1",
        requiresLiveOwnerContext: Boolean = false,
        reconfirmedAtMs: Long? = null,
        attemptCount: Int = 0,
        lastAttemptPath: String? = null,
    ): OutboxEntry = assertNotNull(
        DurableOutbox.admit(
            messageId = "msg_1", commandId = "cmd_1", idempotencyKey = "idem_1",
            turnId = "turn_1", actionClass = actionClass,
            requiresLiveOwnerContext = requiresLiveOwnerContext,
            payloadRef = "msg_1", nowMs = NOW,
        ),
    ).copy(
        reconfirmedAtMs = reconfirmedAtMs,
        attemptCount = attemptCount,
        lastAttemptPath = lastAttemptPath,
    )

    @Test
    fun `an entry survives a round trip through the queue record unchanged`() {
        // The whole claim, in one assertion: what goes to disk comes back identical.
        val original = entry(
            actionClass = "A3", requiresLiveOwnerContext = true,
            reconfirmedAtMs = NOW + 60_000, attemptCount = 2, lastAttemptPath = "primary-wss",
        )
        val restored = OutboxPersistence.toEntry(
            OutboxPersistence.toCommand(original, "{\"message_id\":\"msg_1\"}"),
        )
        assertEquals(original, restored)
    }

    @Test
    fun `a reconfirmation survives the process dying`() {
        // §20.15's failure mode if it does not: the owner is asked the same question
        // twice, which is how somebody learns to stop reading the question.
        val asked = entry(requiresLiveOwnerContext = true)
        assertTrue(DurableOutbox.flush(asked, NOW) is FlushVerdict.NeedsReconfirmation)

        val answered = DurableOutbox.reconfirm(asked, NOW + 1_000)
        val afterDeath = assertNotNull(
            OutboxPersistence.toEntry(OutboxPersistence.toCommand(answered, "{}")),
        )
        assertEquals(NOW + 1_000, afterDeath.reconfirmedAtMs)
        assertTrue(DurableOutbox.flush(afterDeath, NOW + 2_000) is FlushVerdict.Send)
    }

    @Test
    fun `the expiry that survives is the entrys own and not the queues default`() {
        // The queue's default is twenty-four hours and the outbox's is four. Storing the
        // queue's would silently extend a window the outbox had already decided, and the
        // command would flush twenty hours after it should have been dropped.
        val e = entry()
        val command = OutboxPersistence.toCommand(e, "{}")
        assertEquals(e.expiresAtMs, command.expiresAtEpochMs)
        assertEquals(DurableOutbox.DEFAULT_TTL_MS, command.expiresAtEpochMs - command.createdAtEpochMs)
    }

    @Test
    fun `an attempt count survives so three failures on one path are not three on three`() {
        val attempted = DurableOutbox.attempted(entry(), "fallback-http2")
        val restored = assertNotNull(
            OutboxPersistence.toEntry(OutboxPersistence.toCommand(attempted, "{}")),
        )
        assertEquals(1, restored.attemptCount)
        assertEquals("fallback-http2", restored.lastAttemptPath)
    }

    @Test
    fun `a record with no storability is refused rather than reconstructed`() {
        // The guess this exists to prevent. Guess SAFE_TO_RETRY and an approval-bearing
        // command replays silently; guess NEVER_STORE and the owner's work is dropped
        // without them being told. Neither is acceptable, so there is no guess.
        val orphan = QueuedCommand(
            id = "x", idempotencyKey = "k", kind = CommandKind.SESSION_ENVELOPE.name,
            payloadJson = "{}", sensitivity = CommandSensitivity.NORMAL.name,
            createdAtEpochMs = NOW, expiresAtEpochMs = NOW + 1_000,
            sessionMessageId = "msg_1", storability = null,
        )
        assertNull(OutboxPersistence.toEntry(orphan))
    }

    @Test
    fun `a record from another part of the app is not read as session work`() {
        val other = QueuedCommand(
            id = "x", idempotencyKey = "k", kind = CommandKind.REMINDER.name,
            payloadJson = "{}", sensitivity = CommandSensitivity.NORMAL.name,
            createdAtEpochMs = NOW, expiresAtEpochMs = NOW + 1_000,
            sessionMessageId = "msg_1", storability = CommandStorability.SAFE_TO_RETRY.name,
        )
        assertNull(OutboxPersistence.toEntry(other))
    }

    @Test
    fun `an unrecognised storability is refused rather than defaulted`() {
        val futureName = QueuedCommand(
            id = "x", idempotencyKey = "k", kind = CommandKind.SESSION_ENVELOPE.name,
            payloadJson = "{}", sensitivity = CommandSensitivity.NORMAL.name,
            createdAtEpochMs = NOW, expiresAtEpochMs = NOW + 1_000,
            sessionMessageId = "msg_1", storability = "SOMETHING_A_LATER_BUILD_ADDED",
        )
        assertNull(OutboxPersistence.toEntry(futureName))
    }

    @Test
    fun `the two vocabularies on the record cannot disagree`() {
        // `sensitivity` is the queue's older word and `actionClass` is the exact one.
        // Both are on the record and a reader may use either, so they are derived from
        // one source rather than passed in separately.
        for ((actionClass, sensitivity) in listOf(
            "A1" to CommandSensitivity.NORMAL,
            "A3" to CommandSensitivity.ELEVATED,
            "A4" to CommandSensitivity.DESTRUCTIVE,
            "A5" to CommandSensitivity.SECRET,
        )) {
            assertEquals(sensitivity, OutboxPersistence.sensitivityFor(actionClass), actionClass)
        }
    }

    @Test
    fun `anything needing the owner present is stored as NO_STALE_REPLAY`() {
        // So the queue's own older machinery enforces §20.14 too, rather than both being
        // correct and only one of them being consulted.
        assertEquals(
            ReplayPolicy.NO_STALE_REPLAY,
            OutboxPersistence.replayPolicyFor(entry(requiresLiveOwnerContext = true)),
        )
        assertEquals(ReplayPolicy.NORMAL, OutboxPersistence.replayPolicyFor(entry()))
    }

    @Test
    fun `an A4 never reaches the record at all`() {
        // Not because this mapper refuses it — because `admit` returned null and there is
        // nothing to map. The only way to store one is to not call the classifier.
        assertNull(
            DurableOutbox.admit(
                messageId = "m", commandId = "c", idempotencyKey = "i", turnId = "t",
                actionClass = "A4", requiresLiveOwnerContext = false,
                payloadRef = "m", nowMs = NOW,
            ),
        )
    }
}
