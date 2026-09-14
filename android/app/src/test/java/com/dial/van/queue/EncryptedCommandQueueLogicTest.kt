package com.dial.van.queue

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
            createdAtEpochMs = 0,
            expiresAtEpochMs = Long.MAX_VALUE,
            attemptCount = 3,
        )
        assertEquals(key, cmd.idempotencyKey)
        assertEquals(3, cmd.attemptCount)
    }

    private fun assertEquals(expected: Any?, actual: Any?) {
        org.junit.Assert.assertEquals(expected, actual)
    }
}
