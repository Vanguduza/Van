package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val NOW = 1_700_000_000_000L

private fun persisted(
    at: Long = NOW,
    observed: String = "VAN is driving — tap Take Control to steer",
) = PersistedBrowserSession(
    sessionId = "ibs_1",
    profileAlias = "authenticated_owner",
    lastViewportRevision = 7,
    lastEventCursor = 412,
    lastSpokenSegment = 3,
    persistedAtMs = at,
    lastObservedState = observed,
    lastObservedControlGeneration = 4,
)

/**
 * Rev 1.5 §29.10 — the phone was killed, and what it may believe when it comes back.
 */
class BrowserProcessRecoveryTest {

    @Test
    fun `a restored session says nothing to the owner until the Gateway has`() {
        // §29.10 step 6, and the reason this module exists. The snapshot says the agent
        // was driving; the work may have finished, failed, or been taken over from another
        // device. Showing it would be VAN reporting a state it has no evidence for.
        val restored = BrowserProcessRecovery.restore(persisted(), NOW + 5_000)
        assertEquals(RestoreDisposition.RESUMABLE_PENDING_GATEWAY, restored.disposition)
        assertEquals("ibs_1", restored.sessionId)
        assertNull(restored.ownerVisibleState)
    }

    @Test
    fun `there is no argument that produces an owner-visible state from the cache`() {
        // Asserted on the signature rather than on one call: the "still working" a stale
        // snapshot would produce has to be unreachable, not merely unused.
        val parameters = BrowserProcessRecovery::class.java.methods
            .single { it.name == "restore" }
            .parameterTypes
            .map { it.simpleName }
        assertEquals(listOf("PersistedBrowserSession", "long"), parameters)
    }

    @Test
    fun `cursors are restored because they are positions rather than verdicts`() {
        val restored = BrowserProcessRecovery.restore(persisted(), NOW + 5_000)
        assertEquals(412, restored.resumeEventCursor)
        // §21.16 across a process death: from what was spoken, not from what arrived.
        assertEquals(3, restored.resumeSpeechSegment)
    }

    @Test
    fun `a record older than a session's life is not about that session`() {
        val restored = BrowserProcessRecovery.restore(
            persisted(), NOW + BrowserProcessRecovery.MAX_AGE_MS,
        )
        assertEquals(RestoreDisposition.NOTHING_TO_RESTORE, restored.disposition)
        assertNull(restored.sessionId)
    }

    @Test
    fun `nothing persisted is nothing to restore`() {
        assertEquals(
            RestoreDisposition.NOTHING_TO_RESTORE,
            BrowserProcessRecovery.restore(null, NOW).disposition,
        )
    }

    @Test
    fun `a clock that went backwards still asks rather than discarding`() {
        // The record is not necessarily wrong; its age cannot be reasoned about. Asking
        // the Gateway costs one call and is right either way.
        val restored = BrowserProcessRecovery.restore(persisted(at = NOW + 60_000), NOW)
        assertEquals(RestoreDisposition.RESUMABLE_PENDING_GATEWAY, restored.disposition)
    }

    @Test
    fun `the Gateway saying no drops the record entirely`() {
        val restored = BrowserProcessRecovery.restore(persisted(), NOW + 1_000)
        val reconciled = BrowserProcessRecovery.reconcile(restored, false, null)
        assertEquals(RestoreDisposition.GATEWAY_SAYS_GONE, reconciled.disposition)
        assertNull(reconciled.sessionId, "and takes the session id with it")
    }

    @Test
    fun `only the Gateway's answer becomes what the owner sees`() {
        val restored = BrowserProcessRecovery.restore(persisted(), NOW + 1_000)
        val reconciled = BrowserProcessRecovery.reconcile(restored, true, "Ready")
        assertEquals(RestoreDisposition.CONFIRMED_BY_GATEWAY, reconciled.disposition)
        assertEquals("Ready", reconciled.ownerVisibleState)
        assertEquals("ibs_1", reconciled.sessionId)
    }

    @Test
    fun `reconciliation cannot see the cached state`() {
        // A reconciliation that could see it could prefer it, and the one case where that
        // matters is the one where the cache is wrong.
        val parameters = BrowserProcessRecovery::class.java.methods
            .single { it.name == "reconcile" }
            .parameterTypes
            .map { it.simpleName }
        assertFalse(parameters.contains("PersistedBrowserSession"), "$parameters")
    }

    @Test
    fun `media does not reconnect until the session is confirmed`() {
        // §29.8. Negotiating WebRTC against a grant for a session the Gateway has already
        // ended fails in a way that looks like a network problem and is not.
        val restored = BrowserProcessRecovery.restore(persisted(), NOW + 1_000)
        assertFalse(BrowserProcessRecovery.mayReconnectMedia(restored))
        assertFalse(
            BrowserProcessRecovery.mayReconnectMedia(
                BrowserProcessRecovery.reconcile(restored, false, null),
            ),
        )
        assertTrue(
            BrowserProcessRecovery.mayReconnectMedia(
                BrowserProcessRecovery.reconcile(restored, true, "Ready"),
            ),
        )
    }
}

/**
 * ADR-RB-022 — a rotation is not a process death, and neither is a split-screen transition.
 */
class ActivityLifetimeContractTest {

    @Test
    fun `the Activity rebuilds only what it owns`() {
        for (component in BrowserProcessRecovery.ACTIVITY_OWNS) {
            assertTrue(BrowserProcessRecovery.rebuiltOnActivityRecreation(component), component)
        }
    }

    @Test
    fun `the session, the media and the cursors outlive it`() {
        // A browser that restarted navigation on rotation loses the page the owner was
        // reading because they turned the phone.
        for (component in BrowserProcessRecovery.OUTLIVES_THE_ACTIVITY) {
            assertFalse(BrowserProcessRecovery.rebuiltOnActivityRecreation(component), component)
        }
    }

    @Test
    fun `the two lists do not overlap`() {
        assertTrue(
            BrowserProcessRecovery.ACTIVITY_OWNS
                .intersect(BrowserProcessRecovery.OUTLIVES_THE_ACTIVITY)
                .isEmpty(),
        )
    }
}
