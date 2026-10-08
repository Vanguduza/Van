package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VoiceTurnLifecycleTest {
    @Test fun `cancelled turn cannot admit late final or processed transcript`() {
        val lifecycle = VoiceTurnLifecycle()
        val token = lifecycle.begin("turn-1")
        assertTrue(lifecycle.claimFinal(token))
        lifecycle.cancel()
        assertFalse(lifecycle.finish(token))
        assertFalse(lifecycle.claimFinal(token))
    }

    @Test fun `replacement rejects old callbacks even with same owner turn id`() {
        val lifecycle = VoiceTurnLifecycle()
        val old = lifecycle.begin("turn-1")
        assertTrue(lifecycle.claimFinal(old))
        val replacement = lifecycle.begin("turn-1")
        assertFalse(lifecycle.acceptsRecognition(old))
        assertFalse(lifecycle.finish(old))
        assertTrue(lifecycle.claimFinal(replacement))
        assertTrue(lifecycle.finish(replacement))
    }

    @Test fun `finishing audio permits one final transcript while duplicate finals are rejected`() {
        val lifecycle = VoiceTurnLifecycle()
        val token = lifecycle.begin("turn-1")
        // Closing the audio pipe does not cancel the token; the recognizer may drain EOS.
        assertTrue(lifecycle.acceptsRecognition(token))
        assertTrue(lifecycle.claimFinal(token))
        assertFalse(lifecycle.claimFinal(token))
        assertTrue(lifecycle.finish(token))
        assertFalse(lifecycle.finish(token))
    }
}
