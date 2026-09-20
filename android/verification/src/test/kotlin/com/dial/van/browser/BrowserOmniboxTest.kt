package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Rev 1.5 §17.2 — what the owner typed, classified without asking anyone.
 */
class BrowserOmniboxTest {

    private fun navigate(typed: String, to: String) {
        val resolved = BrowserOmnibox.resolve(typed)
        assertEquals(OmniboxIntent.NAVIGATE, resolved.intent, "$typed -> ${resolved.reason}")
        assertEquals(to, resolved.value)
    }

    private fun search(typed: String) {
        val resolved = BrowserOmnibox.resolve(typed)
        assertEquals(OmniboxIntent.SEARCH, resolved.intent, "$typed -> ${resolved.reason}")
        assertEquals(typed.trim(), resolved.value)
    }

    @Test
    fun `an address with a scheme goes exactly where it says`() {
        navigate("https://example.com/pricing", "https://example.com/pricing")
        navigate("http://example.com", "http://example.com")
    }

    @Test
    fun `a bare host gets https, never http`() {
        // §9.14's rule applied to the owner's own typing. VAN upgrading to http would be
        // VAN choosing the insecure one on the owner's behalf.
        navigate("example.com", "https://example.com")
        navigate("example.com/a/b?c=d#e", "https://example.com/a/b?c=d#e")
        navigate("sub.example.co.uk", "https://sub.example.co.uk")
    }

    @Test
    fun `anything with a space is a search`() {
        // Including the ones that contain a host: "site:example.com pricing" is a query
        // and treating it as an address would navigate to a page that does not exist.
        search("what is a viewport")
        search("site:example.com pricing")
        search("example.com pricing")
    }

    @Test
    fun `a query whose last word looks like a host is still a query`() {
        // The case that makes the whitespace check load-bearing rather than redundant.
        // Every example above falls out as a search through some other clause — no dot,
        // an unparseable last label, a scheme — so a mutation deleting the whitespace
        // check survived them all.
        //
        // This one does not: with the check gone, "cheap flights example.com" parses as a
        // host whose last label is a plausible TLD, and VAN navigates to
        // `https://cheap flights example.com` instead of searching for it.
        search("cheap flights example.com")
        search("compare prices amazon.co.uk")
        val resolved = BrowserOmnibox.resolve("cheap flights example.com")
        assertEquals("contains_whitespace", resolved.reason)
    }

    @Test
    fun `a single label is a search`() {
        // "pricing" is what someone is looking for, not a host. The exception is the one
        // host with no dot that people actually type.
        search("pricing")
        search("dinner")
        navigate("localhost", "https://localhost")
        navigate("localhost:8080/admin", "https://localhost:8080/admin")
    }

    @Test
    fun `something that is not a hostname is a search even with a dot in it`() {
        search("3.14")
        search("version.2")
        search("file.7z")
    }

    @Test
    fun `an empty label is not a host`() {
        search("example..com")
        search(".com")
    }

    @Test
    fun `a punycode host is a host`() {
        navigate("xn--bcher-kva.example", "https://xn--bcher-kva.example")
    }

    @Test
    fun `a scheme VAN will not navigate becomes a search rather than a refusal`() {
        // The owner who typed this meant something. A refusal dialog teaches them nothing
        // and a search at least tries.
        for (typed in listOf(
            "javascript:alert(1)",
            "file:///etc/passwd",
            "data:text/html,<h1>x</h1>",
            "chrome://settings",
            "intent://evil#Intent;scheme=http;end",
            "content://media/external/images/1",
        )) {
            val resolved = BrowserOmnibox.resolve(typed)
            assertEquals(OmniboxIntent.SEARCH, resolved.intent, typed)
            assertTrue(resolved.reason.startsWith("scheme_not_navigable:"), resolved.reason)
        }
    }

    @Test
    fun `whitespace around an address does not make it a search`() {
        navigate("  https://example.com  ", "https://example.com")
    }

    @Test
    fun `nothing typed is nothing to do`() {
        assertEquals("", BrowserOmnibox.resolve("   ").value)
    }
}

/**
 * §17.2 — "do not leak typed owner input to a suggestion provider without policy."
 *
 * An address bar is where people type things they have not decided to say. These are the
 * cases where VAN asks nobody.
 */
class SuggestionPolicyTest {

    @Test
    fun `the default asks nobody`() {
        assertFalse(SuggestionPolicy.OFF.leavesTheDevice)
        assertFalse(BrowserOmnibox.mayRequestSuggestions(SuggestionPolicy.OFF, "bank of"))
    }

    @Test
    fun `local history is not a request`() {
        // The distinction a boolean would lose: "suggest nothing" and "suggest from what
        // this device already knows" are both "nothing leaves", and the owner may want
        // the second.
        assertFalse(SuggestionPolicy.LOCAL_HISTORY_ONLY.leavesTheDevice)
        assertFalse(
            BrowserOmnibox.mayRequestSuggestions(SuggestionPolicy.LOCAL_HISTORY_ONLY, "bank of"),
        )
    }

    @Test
    fun `consent allows a query to be asked about`() {
        assertTrue(
            BrowserOmnibox.mayRequestSuggestions(
                SuggestionPolicy.REMOTE_WITH_OWNER_CONSENT, "how to renew a passport",
            ),
        )
    }

    @Test
    fun `an address is never sent to a suggestion provider`() {
        // Sending it would tell the provider the page the owner is about to open, which is
        // not what a suggestion is for and is not what they consented to.
        assertFalse(
            BrowserOmnibox.mayRequestSuggestions(
                SuggestionPolicy.REMOTE_WITH_OWNER_CONSENT, "https://bank.example/login",
            ),
        )
        assertFalse(
            BrowserOmnibox.mayRequestSuggestions(
                SuggestionPolicy.REMOTE_WITH_OWNER_CONSENT, "bank.example",
            ),
        )
    }

    @Test
    fun `something that looks like a credential is never sent`() {
        assertFalse(
            BrowserOmnibox.mayRequestSuggestions(
                SuggestionPolicy.REMOTE_WITH_OWNER_CONSENT, "owner@example.com:hunter2",
            ),
        )
    }

    @Test
    fun `an empty box asks nothing`() {
        assertFalse(
            BrowserOmnibox.mayRequestSuggestions(SuggestionPolicy.REMOTE_WITH_OWNER_CONSENT, "  "),
        )
    }
}
