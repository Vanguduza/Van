package com.dial.van.share

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * P1-AND-001's companion. The one security-relevant rule on the share path is that content
 * carrying a credential is dropped rather than queued — the owner sharing a password reset
 * email to VAN must not put that password in VAN's queue — and it was written against
 * `android.content.Intent`, so it could not be tested without a device.
 */
class ShareIntakeTest {

    @Test
    fun `a shared credential is dropped, not queued`() {
        for (text in listOf(
            "Your OTP is 448122",
            "Here is the api key: sk-live-abc",
            "bearer eyJhbGciOi",
            "My password is hunter2",
            "Your verification code is 9921",
            "Recovery code: 8812-2213",
        )) {
            assertEquals(
                ShareSensitivity.SECRET, ShareIntake.classify(text, null), text,
            )
        }
    }

    @Test
    fun `ordinary content is kept`() {
        assertEquals(
            ShareSensitivity.NORMAL,
            ShareIntake.classify("The quarterly report is out, revenue up 4%", "Q3 results"),
        )
    }

    @Test
    fun `a secret in the subject counts as much as one in the body`() {
        assertEquals(
            ShareSensitivity.SECRET,
            ShareIntake.classify("see attached", "Your one-time code"),
        )
    }

    @Test
    fun `kind follows the mime type and the number of items`() {
        assertEquals(ShareKind.TEXT, ShareIntake.kindFor("text/plain", 0))
        assertEquals(ShareKind.IMAGE, ShareIntake.kindFor("image/png", 1))
        assertEquals(ShareKind.FILE, ShareIntake.kindFor("application/pdf", 1))
        assertEquals(ShareKind.MULTIPLE, ShareIntake.kindFor("image/*", 3))
        assertEquals(ShareKind.TEXT, ShareIntake.kindFor(null, 0))
    }

    @Test
    fun `blank text and empty uris do not become empty fields`() {
        val payload = ShareIntake.payload("text/plain", "   ", "", listOf("", "content://a"))
        assertEquals(null, payload.text)
        assertEquals(null, payload.subject)
        assertEquals(listOf("content://a"), payload.uris)
    }

    @Test
    fun `the owner is told what happened, including when nothing was kept`() {
        val secret = ShareIntake.payload("text/plain", "Your OTP is 1234", null)
        val line = ShareIntake.acknowledgement(secret, ShareSensitivity.SECRET)
        assertTrue(line.contains("not kept"), line)

        val normal = ShareIntake.payload("text/plain", "read this", "Q3 results")
        assertTrue(
            ShareIntake.acknowledgement(normal, ShareSensitivity.NORMAL).contains("Q3 results"),
        )
    }

    @Test
    fun `no acknowledgement leaks the shared content back`() {
        // A secret share must not be echoed in the confirmation that it was dropped.
        val secret = ShareIntake.payload("text/plain", "password is hunter2", null)
        val line = ShareIntake.acknowledgement(secret, ShareSensitivity.SECRET)
        assertTrue(!line.contains("hunter2"), line)
    }
}
