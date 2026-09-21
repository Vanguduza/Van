package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val NOW = 1_700_000_000_000L

private fun request(
    accept: List<String> = emptyList(),
    session: String = "ibs_1",
) = FileChooserRequest(
    sessionId = session, targetId = "t1", acceptTypes = accept, multiple = false,
)

private fun ticket(
    state: UploadState = UploadState.ATTACHED,
    retained: Boolean = false,
    name: String = "P45 2019.pdf",
) = UploadTicket(
    uploadId = "up_1", sessionId = "ibs_1", targetId = "t1",
    displayName = name, byteSize = 1024, declaredMime = "application/pdf",
    createdAtMs = NOW, state = state, ownerRetained = retained,
)

/**
 * Rev 1.5 §19 — a page asked for a file, and what VAN does and does not do with it.
 */
class BrowserUploadPolicyTest {

    @Test
    fun `a ticket has nowhere to put a byte`() {
        // §19's prohibition made structural rather than remembered. The type carries a
        // name, a size and a mime; there is no content field for a log line or a Hermes
        // payload to reach into.
        val fields = UploadTicket::class.java.declaredFields
            .filterNot { it.isSynthetic }
            .map { it.name }
            .toSet()
        assertEquals(
            setOf(
                "uploadId", "sessionId", "targetId", "displayName", "byteSize",
                "declaredMime", "createdAtMs", "state", "ownerRetained",
            ),
            fields,
        )
    }

    @Test
    fun `a log line about an upload does not carry the filename`() {
        // "P45 2019 — Jane Okonkwo.pdf" in a log says who the owner is and what they were
        // doing. A filename is content.
        val logged = BrowserUploadPolicy.loggableFields(ticket(name = "P45 2019 — Jane Okonkwo.pdf"))
        assertFalse(logged.values.any { it.contains("Jane") }, "$logged")
        assertFalse(logged.values.any { it.contains("P45") }, "$logged")
        assertEquals("27", logged["name_length"])
    }

    @Test
    fun `uploading a file is not asking VAN to read it`() {
        // A VAN that inferred consent from the upload would read the owner's documents
        // because they attached one to a form.
        assertFalse(BrowserUploadPolicy.mayAnalyse(ticket(), ownerAskedToAnalyse = false))
        assertTrue(BrowserUploadPolicy.mayAnalyse(ticket(), ownerAskedToAnalyse = true))
    }

    @Test
    fun `analysis needs the file to have actually arrived`() {
        assertFalse(
            BrowserUploadPolicy.mayAnalyse(
                ticket(state = UploadState.TRANSFERRING), ownerAskedToAnalyse = true,
            ),
        )
    }

    @Test
    fun `an ephemeral copy expires`() {
        // §19 step 8. A file uploaded and forgotten should be gone before the owner has
        // left the room, not sitting on a shared host overnight.
        val t = ticket()
        assertFalse(BrowserUploadPolicy.expired(t, NOW + 60_000))
        assertTrue(BrowserUploadPolicy.expired(t, NOW + BrowserUploadPolicy.DEFAULT_TTL_MS))
        assertEquals(NOW + BrowserUploadPolicy.DEFAULT_TTL_MS, t.expiresAtMs())
    }

    @Test
    fun `a copy the owner asked to keep does not expire`() {
        val kept = ticket(retained = true)
        assertFalse(BrowserUploadPolicy.expired(kept, NOW + 10 * BrowserUploadPolicy.DEFAULT_TTL_MS))
        assertNull(kept.expiresAtMs())
    }

    @Test
    fun `a chooser from a session that is no longer on screen is refused`() {
        // The owner closed the browser and opened a new session while the picker was up.
        // Attaching the file to the old target puts it somewhere they are not looking.
        assertEquals(
            UploadRefusal.SESSION_STALE,
            BrowserUploadPolicy.admit(
                request(session = "ibs_old"), "a.pdf", 10, "application/pdf", "ibs_1",
            ),
        )
    }

    @Test
    fun `a name that is not a name is refused`() {
        for (name in listOf("../../.bashrc", "a/b.pdf", "..\\x", "", "   ", ".")) {
            assertEquals(
                UploadRefusal.NAME_UNSAFE,
                BrowserUploadPolicy.admit(request(), name, 10, "application/pdf", "ibs_1"),
                name,
            )
        }
    }

    @Test
    fun `an empty file and an enormous one are both refused`() {
        assertEquals(
            UploadRefusal.TOO_LARGE,
            BrowserUploadPolicy.admit(request(), "a.pdf", 0, "application/pdf", "ibs_1"),
        )
        assertEquals(
            UploadRefusal.TOO_LARGE,
            BrowserUploadPolicy.admit(
                request(), "a.pdf", BrowserUploadPolicy.MAX_BYTES + 1, "application/pdf", "ibs_1",
            ),
        )
        assertNull(
            BrowserUploadPolicy.admit(
                request(), "a.pdf", BrowserUploadPolicy.MAX_BYTES, "application/pdf", "ibs_1",
            ),
        )
    }

    @Test
    fun `a type the page will not take is refused here rather than after the transfer`() {
        // Otherwise the owner pays for the upload and the page says no at the end of it.
        assertEquals(
            UploadRefusal.TYPE_NOT_ACCEPTED,
            BrowserUploadPolicy.admit(
                request(accept = listOf("image/*")), "a.pdf", 10, "application/pdf", "ibs_1",
            ),
        )
    }
}

/**
 * The `accept` attribute, in the shapes the web actually uses.
 */
class UploadAcceptMatchingTest {

    @Test
    fun `no accept attribute means anything`() {
        // An absent `accept` in HTML means the input takes anything. Treating an empty
        // list as "nothing" breaks every plain file input on the web.
        assertTrue(BrowserUploadPolicy.accepts(emptyList(), "a.pdf", "application/pdf"))
    }

    @Test
    fun `an extension matches on the extension`() {
        assertTrue(BrowserUploadPolicy.accepts(listOf(".pdf"), "Statement.PDF", "application/pdf"))
        assertFalse(BrowserUploadPolicy.accepts(listOf(".pdf"), "photo.jpg", "image/jpeg"))
    }

    @Test
    fun `a wildcard type matches its family`() {
        assertTrue(BrowserUploadPolicy.accepts(listOf("image/*"), "photo.jpg", "image/jpeg"))
        assertFalse(BrowserUploadPolicy.accepts(listOf("image/*"), "a.pdf", "application/pdf"))
    }

    @Test
    fun `an exact type matches exactly, parameters and case aside`() {
        assertTrue(
            BrowserUploadPolicy.accepts(listOf("text/csv"), "rows.csv", "TEXT/CSV; charset=utf-8"),
        )
        assertFalse(BrowserUploadPolicy.accepts(listOf("text/csv"), "rows.txt", "text/plain"))
    }

    @Test
    fun `any of several accepted forms is enough`() {
        assertTrue(
            BrowserUploadPolicy.accepts(
                listOf(".doc", ".docx", "application/pdf"), "a.pdf", "application/pdf",
            ),
        )
    }

    @Test
    fun `a file with no extension does not match an extension rule`() {
        assertFalse(BrowserUploadPolicy.accepts(listOf(".pdf"), "Statement", "application/pdf"))
    }

    @Test
    fun `star slash star takes everything`() {
        assertTrue(BrowserUploadPolicy.accepts(listOf("*/*"), "anything", "application/octet-stream"))
    }
}
