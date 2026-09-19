package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P1-VOICE-001 — whether VAN can listen for its name, and why not when it cannot.
 *
 * `WakePipeline` was never constructed anywhere in the app, so "Hey Van" did nothing and
 * nothing said so: `WakeCoordinator.KWS_NOT_READY` existed and was unreachable because no
 * coordinator existed either. A keyword-spotting model is a trained artefact rather than
 * code, so what the repository owes is the same thing it owes for the Rive artboard —
 * decide from what is on disk, and say the reason in words the owner can act on.
 */
class WakeModelAssetTest {

    @Test
    fun `no model at all is absent, and says so`() {
        val status = WakeModelPolicy.classify(null)
        assertEquals(WakeModelState.ABSENT, status.state)
        assertFalse(status.ready)
        assertTrue(status.sentence.contains("no wake word model is installed"))
    }

    @Test
    fun `a placeholder is not a model`() {
        // The failure this prevents: a zero-byte or truncated file makes the pipeline
        // constructible, VAN arms, listens, and never wakes — indistinguishable from the
        // defect except that it also reports itself as working.
        assertEquals(WakeModelState.UNUSABLE, WakeModelPolicy.classify(0L).state)
        assertEquals(
            WakeModelState.UNUSABLE,
            WakeModelPolicy.classify(WakeModelPolicy.MIN_MODEL_BYTES - 1).state,
        )
        assertEquals(
            WakeModelState.UNUSABLE,
            WakeModelPolicy.classify(WakeModelPolicy.MAX_MODEL_BYTES + 1).state,
        )
    }

    @Test
    fun `a plausible model with no pinned digest is accepted`() {
        val status = WakeModelPolicy.classify(2L * 1024 * 1024)
        assertEquals(WakeModelState.READY, status.state)
        assertTrue(status.ready)
        assertTrue(status.sentence.contains(WakeModelPolicy.PHRASE))
    }

    @Test
    fun `a model that is not the one the release pinned is refused`() {
        // A model VAN cannot verify is a model that decides when VAN starts listening.
        val status = WakeModelPolicy.classify(
            sizeBytes = 2L * 1024 * 1024, sha256 = "aa", expectedSha256 = "bb",
        )
        assertEquals(WakeModelState.DIGEST_MISMATCH, status.state)
        assertFalse(status.ready)
    }

    @Test
    fun `a matching digest is accepted whatever its case`() {
        assertEquals(
            WakeModelState.READY,
            WakeModelPolicy.classify(2L * 1024 * 1024, "ABCD", "abcd").state,
        )
    }

    @Test
    fun `every state has a sentence and none of them names an enum or a path`() {
        for (state in WakeModelState.entries) {
            val status = WakeModelStatus(state, WakeModelPolicy.PHRASE, null, null)
            assertTrue(status.sentence.isNotBlank(), state.name)
            assertFalse(status.sentence.contains(state.name), status.sentence)
            assertFalse(status.sentence.contains("/"), status.sentence)
        }
    }

    @Test
    fun `only READY reports ready`() {
        for (state in WakeModelState.entries) {
            val status = WakeModelStatus(state, WakeModelPolicy.PHRASE, null, null)
            assertEquals(state == WakeModelState.READY, status.ready, state.name)
        }
    }
}
