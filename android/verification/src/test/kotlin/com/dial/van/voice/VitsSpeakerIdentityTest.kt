package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VitsSpeakerIdentityTest {
    @Test fun `pinned LJS VITS uses speaker zero when the native speaker count is zero`() {
        assertTrue(VitsSpeakerIdentity.accepts(22050, 0, 0))
    }
    @Test fun `zero native speaker count never authorizes another speaker identity`() {
        for (speaker in listOf(-1, 1, 2, Int.MAX_VALUE)) assertFalse(VitsSpeakerIdentity.accepts(22050, 0, speaker))
    }
    @Test fun `multi speaker models retain their exact native identity bounds`() {
        assertTrue(VitsSpeakerIdentity.accepts(24000, 2, 0))
        assertTrue(VitsSpeakerIdentity.accepts(24000, 2, 1))
        assertFalse(VitsSpeakerIdentity.accepts(24000, 2, 2))
        assertFalse(VitsSpeakerIdentity.accepts(24000, 2, -1))
    }
    @Test fun `invalid native rate or speaker metadata is still refused`() {
        for (rate in listOf(-1, 0)) assertFalse(VitsSpeakerIdentity.accepts(rate, 0, 0))
        assertFalse(VitsSpeakerIdentity.accepts(22050, -1, 0))
    }
}
