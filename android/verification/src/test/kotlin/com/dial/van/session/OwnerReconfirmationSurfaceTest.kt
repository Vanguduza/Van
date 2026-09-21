package com.dial.van.session

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val NOW_RECONFIRM = 1_700_000_000_000L

class OwnerReconfirmationSurfaceTest {

    private fun entry(
        liveContext: Boolean = true,
        createdAt: Long = NOW_RECONFIRM,
        ttlMs: Long = DurableOutbox.DEFAULT_TTL_MS,
    ): OutboxEntry = assertNotNull(
        DurableOutbox.admit(
            messageId = "msg_1",
            commandId = "cmd_owner_12345678",
            idempotencyKey = "idem_1",
            turnId = "turn_1",
            actionClass = "A2",
            requiresLiveOwnerContext = liveContext,
            payloadRef = "msg_1",
            nowMs = createdAt,
            ttlMs = ttlMs,
        ),
    )

    private fun envelope(text: String = "Send the project update when I am back online") =
        JSONObject()
            .put("message_id", "msg_1")
            .put("payload", JSONObject().put("text", text))

    @Test
    fun only_work_waiting_for_owner_is_projected() {
        assertNotNull(
            OwnerReconfirmationSurface.project(
                entry(liveContext = true), envelope(), NOW_RECONFIRM + 1_000,
            ),
        )
        assertNull(
            OwnerReconfirmationSurface.project(
                entry(liveContext = false), envelope(), NOW_RECONFIRM + 1_000,
            ),
        )
    }

    @Test
    fun a_stale_ordinary_command_becomes_an_owner_question() {
        val request = assertNotNull(
            OwnerReconfirmationSurface.project(
                entry(liveContext = false),
                envelope(),
                NOW_RECONFIRM + DurableOutbox.STALE_AFTER_MS,
            ),
        )
        assertEquals("cmd_owner_12345678", request.commandId)
        assertTrue(request.ownerReadableState.startsWith("Waiting for you"))
    }

    @Test
    fun the_surface_shows_the_owners_command_rather_than_an_opaque_queue_id() {
        val request = assertNotNull(
            OwnerReconfirmationSurface.project(
                entry(), envelope("Open the saved research and summarize the changes"), NOW_RECONFIRM + 1,
            ),
        )
        assertEquals("Open the saved research and summarize the changes", request.commandText)
        assertEquals("A2", request.actionClass)
    }

    @Test
    fun owner_preview_is_bounded_and_missing_text_has_truthful_fallback() {
        val long = "x".repeat(600)
        val bounded = assertNotNull(
            OwnerReconfirmationSurface.project(entry(), envelope(long), NOW_RECONFIRM + 1),
        )
        assertEquals(280, bounded.commandText.length)

        val fallback = assertNotNull(
            OwnerReconfirmationSurface.project(
                entry(), JSONObject().put("payload", JSONObject()), NOW_RECONFIRM + 1,
            ),
        )
        assertTrue(fallback.commandText.startsWith("Queued command"))
    }

    @Test
    fun reconfirmation_cannot_revive_expired_work() {
        val expired = entry(ttlMs = 2_000)
        assertNull(
            OwnerReconfirmationSurface.reconfirm(expired, NOW_RECONFIRM + 2_000),
        )
    }

    @Test
    fun explicit_confirmation_preserves_identity_and_releases_only_that_held_entry() {
        val original = entry()
        val confirmed = assertNotNull(
            OwnerReconfirmationSurface.reconfirm(original, NOW_RECONFIRM + 5_000),
        )
        assertEquals(original.messageId, confirmed.messageId)
        assertEquals(original.commandId, confirmed.commandId)
        assertEquals(original.idempotencyKey, confirmed.idempotencyKey)
        assertEquals(original.storability, confirmed.storability)
        assertEquals(NOW_RECONFIRM + 5_000, confirmed.reconfirmedAtMs)
        assertTrue(
            DurableOutbox.flush(confirmed, NOW_RECONFIRM + 6_000) is FlushVerdict.Send,
        )
    }
}
