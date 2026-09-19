package com.dial.van.status

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P2-UX-001 — the Command Centre showed the owner `A4`, `BIOMETRIC_STRONG`, `HMAC`,
 * `reason_code`, raw scope JSON and `truth_sha`. Each is a correct name for what it is and
 * none of them is a thing a person reads.
 */
class OwnerLanguageTest {

    @Test
    fun `an action class is described by what it costs, not by its letter`() {
        for (cls in listOf("A1", "A2", "A3", "A4", "A5")) {
            val text = OwnerLanguage.actionClass(cls)
            assertFalse(text.contains(cls), "$cls leaked into \"$text\"")
            assertTrue(text.first().isUpperCase(), text)
        }
        assertEquals("Changes something you cannot easily undo", OwnerLanguage.actionClass("A4"))
        assertEquals("Reads something", OwnerLanguage.actionClass(" a1 "))
    }

    @Test
    fun `an unrecognised class is not printed raw`() {
        assertEquals("Unknown", OwnerLanguage.actionClass("A9"))
        assertEquals("Unknown", OwnerLanguage.actionClass(null))
        assertEquals("Unknown", OwnerLanguage.actionClass(""))
    }

    @Test
    fun `no command status is shown to the owner as its own name`() {
        // The Command Centre printed `status.name` under every message, so the owner read
        // PARTIALLY_SUCCEEDED and COULD_NOT_VERIFY off their own phone.
        val rendered = VanCommandStatus.entries.associateWith { OwnerLanguage.commandStatus(it) }
        for ((status, text) in rendered) {
            assertFalse(text.contains('_'), "$status renders as $text")
            assertFalse(text == status.name, "$status renders as its own name")
            // VAN's own name is allowed to be capitalised; an internal constant is not.
            assertFalse(
                OwnerLanguage.isInternalLooking(text),
                "$status renders as an internal value: $text",
            )
            assertTrue(text.isNotBlank(), status.name)
        }
        // Distinct wording per status, or the projection P0-EXEC-003 made exhaustive is
        // collapsed again one layer up: "Done" for COULD_NOT_VERIFY would undo it exactly.
        assertEquals(rendered.size, rendered.values.toSet().size, "$rendered")
    }

    @Test
    fun `the three outcomes that are not success read as three different things`() {
        assertEquals("Done", OwnerLanguage.commandStatus(VanCommandStatus.SUCCEEDED))
        for (status in listOf(
            VanCommandStatus.PARTIALLY_SUCCEEDED,
            VanCommandStatus.COULD_NOT_VERIFY,
            VanCommandStatus.UNKNOWN,
            VanCommandStatus.EXPIRED,
        )) {
            assertNotEquals(
                OwnerLanguage.commandStatus(VanCommandStatus.SUCCEEDED),
                OwnerLanguage.commandStatus(status),
                status.name,
            )
        }
    }

    @Test
    fun `only the class that needs approval says so`() {
        assertTrue(OwnerLanguage.approvalSentence("A4")!!.contains("fingerprint or face"))
        for (cls in listOf("A1", "A2", "A3", "A5", null)) {
            assertNull(OwnerLanguage.approvalSentence(cls), cls.toString())
        }
    }

    @Test
    fun `Android's own constants are translated`() {
        assertEquals("your fingerprint or face", OwnerLanguage.authenticator("BIOMETRIC_STRONG"))
        assertEquals("your PIN or pattern", OwnerLanguage.authenticator("DEVICE_CREDENTIAL"))
        for (name in listOf("BIOMETRIC_STRONG", "BIOMETRIC_WEAK", "DEVICE_CREDENTIAL", "WHAT", null)) {
            val text = OwnerLanguage.authenticator(name)
            assertFalse(text.contains('_'), text)
            assertFalse(text.any { it.isUpperCase() && text.indexOf('_') >= 0 }, text)
        }
    }

    @Test
    fun `the owner is not told about HMAC`() {
        for (name in listOf("HMAC", "COMMAND_HMAC", "INGRESS_TOKEN", "DEVICE_ACCESS_TOKEN", "x")) {
            val text = OwnerLanguage.credential(name)
            assertFalse(text.uppercase().contains("HMAC"), text)
            assertFalse(text.contains('_'), text)
        }
        assertEquals("this phone's signing key", OwnerLanguage.credential("hmac"))
    }

    @Test
    fun `every refusal reason is a sentence the owner can act on`() {
        for ((code, sentence) in OwnerLanguage.REASONS) {
            assertEquals(sentence, OwnerLanguage.reason(code))
            assertFalse(sentence.contains('_'), "$code -> $sentence")
            assertTrue(sentence.first().isUpperCase(), sentence)
            assertTrue(sentence.trimEnd().endsWith("."), sentence)
        }
    }

    @Test
    fun `an unknown reason code is de-snaked rather than shown raw`() {
        // A new reason appearing on screen should read as slightly awkward English, never as
        // browser_mutation_domain_not_admitted.
        assertEquals(
            "Browser mutation domain not admitted.",
            OwnerLanguage.reason("browser_mutation_domain_not_admitted"),
        )
        assertEquals("Scope violation.", OwnerLanguage.reason("SCOPE_VIOLATION:mail.google.com").let {
            if (it == OwnerLanguage.REASONS["scope_violation"]) "Scope violation." else it
        })
        assertEquals("VAN did not say why.", OwnerLanguage.reason(null))
        assertEquals("VAN did not say why.", OwnerLanguage.reason("   "))
    }

    @Test
    fun `a qualified code still finds its sentence`() {
        assertEquals(
            OwnerLanguage.REASONS["scope_violation"],
            OwnerLanguage.reason("scope_violation:mail.google.com"),
        )
    }

    @Test
    fun `a digest is a short labelled reference, not a wall of hex`() {
        val sha = "a1b2c3d4" + "e".repeat(56)
        assertEquals("Project state a1b2c3d4", OwnerLanguage.digestReference("Project state", sha))
        // Too short to be a reference anybody could quote back: better to show nothing.
        assertNull(OwnerLanguage.digestReference("Project state", "a1b2"))
        assertNull(OwnerLanguage.digestReference("Project state", null))
    }

    @Test
    fun `a scope is a sentence instead of JSON`() {
        assertEquals(
            "On mail.google.com. Drafts something for you.",
            OwnerLanguage.scopeSentence(listOf("mail.google.com"), "A2"),
        )
        assertEquals(
            "On a.com and b.com. Reads something.",
            OwnerLanguage.scopeSentence(listOf("a.com", "b.com"), "A1"),
        )
        val many = OwnerLanguage.scopeSentence(listOf("a.com", "b.com", "c.com", "d.com"), "A1")
        assertTrue(many.contains("2 more"), many)
        assertFalse(many.contains("["), many)
        assertFalse(many.contains("{"), many)
    }

    @Test
    fun `a scope arriving as JSON is read back as a sentence`() {
        // The escalation screen rendered `current_scope_json.take(300)` and asked the owner
        // to approve a browser boundary extension by reading it.
        assertEquals(
            "On mail.google.com. Drafts something for you.",
            OwnerLanguage.scopeSentenceFromJson(
                """{"domains":["mail.google.com"],"action_class_ceiling":"A2"}""",
            ),
        )
        assertEquals(
            "On calendar.google.com. Reads something.",
            OwnerLanguage.scopeSentenceFromJson(
                """{"allowed_domains":["calendar.google.com"],"action_class":"A1"}""",
            ),
        )
        val wide = OwnerLanguage.scopeSentenceFromJson(
            """{"domains":["a.com","b.com","c.com"],"action_class_ceiling":"A3"}""",
        )
        assertTrue(wide.contains("1 more"), wide)
        assertFalse(wide.contains("{"), wide)
        assertFalse(wide.contains("["), wide)
    }

    @Test
    fun `an absent or unreadable scope never renders as raw text`() {
        assertEquals("Nothing more than it already has.", OwnerLanguage.scopeSentenceFromJson(null))
        assertEquals("Nothing more than it already has.", OwnerLanguage.scopeSentenceFromJson("  "))
        // Not shown, not truncated, not "{". VAN not being able to read its own field back
        // is a thing the owner needs told, and is not a reason to paste the field.
        val broken = OwnerLanguage.scopeSentenceFromJson("{not json at all")
        assertEquals("Something VAN could not read back to you.", broken)
        assertFalse(OwnerLanguage.isInternalLooking(broken))
    }

    @Test
    fun `values that escaped internal layers are caught before the owner reads them`() {
        val internal = listOf(
            "{\"domains\":[\"mail.google.com\"]}",
            "[\"A2\"]",
            "BIOMETRIC_STRONG",
            "SCOPE_VIOLATION",
            "a".repeat(64),
            "0123456789abcdef0123456789abcdef",
        )
        for (value in internal) {
            assertTrue(OwnerLanguage.isInternalLooking(value), value)
            assertEquals("VAN did not explain this one.", OwnerLanguage.ownerSafe(value))
        }
    }

    @Test
    fun `ordinary English is not mistaken for an internal value`() {
        val fine = listOf(
            "It tried to go somewhere you had not allowed.",
            "Drafts something for you",
            "VAN needs your fingerprint or face before doing this.",
            "OK",
        )
        for (value in fine) {
            assertFalse(OwnerLanguage.isInternalLooking(value), value)
            assertEquals(value, OwnerLanguage.ownerSafe(value))
        }
    }

    @Test
    fun `nothing at all falls back rather than rendering empty`() {
        assertEquals("VAN did not explain this one.", OwnerLanguage.ownerSafe(null))
        assertEquals("VAN did not explain this one.", OwnerLanguage.ownerSafe("  "))
        assertEquals("nothing yet", OwnerLanguage.ownerSafe(null, fallback = "nothing yet"))
    }
}
