package com.dial.van.queue

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EncryptedCommandQueueLogicTest {

    @Test
    fun expiredSensitiveCommandDetected() {
        val cmd = QueuedCommand(
            id = "1",
            idempotencyKey = "key",
            kind = CommandKind.HERMES_DISPATCH.name,
            payloadJson = "{}",
            sensitivity = CommandSensitivity.DESTRUCTIVE.name,
            createdAtEpochMs = 0,
            expiresAtEpochMs = 1000,
        )
        assertTrue(cmd.isExpired(1000))
        assertFalse(cmd.isExpired(999))
        assertEquals(ActionClass.A4, cmd.actionClassEnum())
    }

    @Test
    fun idempotencyKeyPreservedInModel() {
        val key = "stable-key-abc"
        val cmd = QueuedCommand(
            id = "1",
            idempotencyKey = key,
            kind = CommandKind.TASK.name,
            payloadJson = "{}",
            sensitivity = CommandSensitivity.NORMAL.name,
            actionClass = ActionClass.A1.name,
            createdAtEpochMs = 0,
            expiresAtEpochMs = Long.MAX_VALUE,
            attemptCount = 3,
        )
        assertEquals(key, cmd.idempotencyKey)
        assertEquals(3, cmd.attemptCount)
        assertEquals(ActionClass.A1, cmd.actionClassEnum())
    }

    @Test
    fun legacyElevatedEntriesMapConservativelyToA3() {
        val cmd = QueuedCommand(
            id = "legacy",
            idempotencyKey = "legacy-key",
            kind = CommandKind.HERMES_DISPATCH.name,
            payloadJson = "{}",
            sensitivity = CommandSensitivity.ELEVATED.name,
            createdAtEpochMs = 0,
            expiresAtEpochMs = Long.MAX_VALUE,
        )
        assertEquals(ActionClass.A3, cmd.actionClassEnum())
    }

    @Test
    fun a5IsNeverReplayEligible() {
        val cmd = QueuedCommand(
            id = "a5",
            idempotencyKey = "a5-key",
            kind = CommandKind.HERMES_DISPATCH.name,
            payloadJson = "{}",
            sensitivity = CommandSensitivity.SECRET.name,
            actionClass = ActionClass.A5.name,
            createdAtEpochMs = 0,
            expiresAtEpochMs = Long.MAX_VALUE,
        )
        assertFalse(cmd.isReplayEligible(1))
    }

    @Test
    fun noStaleReplayCannotRetryAfterFirstAttempt() {
        val fresh = QueuedCommand(
            id = "halt",
            idempotencyKey = "turn-1:trading.halt",
            kind = CommandKind.HERMES_DISPATCH.name,
            payloadJson = "{}",
            sensitivity = CommandSensitivity.DESTRUCTIVE.name,
            actionClass = ActionClass.A4.name,
            replayPolicy = ReplayPolicy.NO_STALE_REPLAY.name,
            createdAtEpochMs = 0,
            expiresAtEpochMs = 5000,
            attemptCount = 0,
        )
        assertTrue(fresh.isReplayEligible(1000))
        assertFalse(fresh.copy(attemptCount = 1).isReplayEligible(1000))
        assertFalse(fresh.isReplayEligible(5000))
    }
}
