package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val NOW = 1_700_000_000_000L

private fun record(
    id: String = "sc_1",
    url: String = "https://example.com/statements",
    title: String = "Statements",
    profile: String = "public_research",
    sensitivity: ShortcutSensitivity = ShortcutSensitivity.ORDINARY,
) = BrowserShortcutRecord(
    shortcutId = id,
    canonicalUrl = url,
    title = title,
    faviconDigestOrRef = "sha256:abc",
    profileAlias = profile,
    createdAtMs = NOW,
    sensitivity = sensitivity,
)

/**
 * Rev 1.5 §5.8, ADR-RB-023 — a shortcut is a bookmark with a stable name, never a way in.
 */
class BrowserShortcutStoreTest {

    @Test
    fun `the launcher gets an id, a label and an icon, and nothing else`() {
        // Asserted on the field set rather than on the call site, because the failure this
        // guards against is a field added to the record later and carried along by being
        // in scope.
        val fields = ShortcutLauncherPayload::class.java.declaredFields
            .filterNot { it.isSynthetic }
            .map { it.name }
            .toSet()
        assertEquals(setOf("shortcutId", "label", "iconRef"), fields)
    }

    @Test
    fun `nothing in the forbidden list can appear in a payload`() {
        val payload = BrowserShortcutStore.launcherPayload(record())
        val rendered = payload.toString().lowercase()
        for (forbidden in BrowserShortcutStore.FORBIDDEN_IN_A_SHORTCUT) {
            assertFalse(rendered.contains(forbidden), forbidden)
        }
        // And the record's own url is not in it either: the destination resolves through
        // the registry, so the tile does not need to name it.
        assertFalse(rendered.contains("example.com"))
    }

    @Test
    fun `an authenticated page's tile says VAN, not what the page is`() {
        // A tile reading "Inbox — owner@example.com" tells whoever picks up the phone who
        // owns it and where they bank, before it is unlocked.
        val payload = BrowserShortcutStore.launcherPayload(
            record(title = "Inbox — owner@example.com", sensitivity = ShortcutSensitivity.AUTHENTICATED),
        )
        assertEquals(BrowserShortcutStore.GENERIC_LABEL, payload.label)
        assertNull(payload.iconRef, "a bank's mark says the same thing its name would")
    }

    @Test
    fun `an untitled ordinary page still gets a usable label`() {
        val payload = BrowserShortcutStore.launcherPayload(record(title = "  "))
        assertEquals(BrowserShortcutStore.GENERIC_LABEL, payload.label)
    }

    @Test
    fun `a shortcut opens when the device is bound and the profile exists`() {
        val store = BrowserShortcutStore()
        store.put(record())
        val resolved = store.resolve("sc_1", deviceBound = true, availableProfiles = setOf("public_research"))
        assertTrue(resolved is ShortcutResolution.Open)
    }

    @Test
    fun `an unbound device does not navigate`() {
        // §5.8 states it and this is the one that matters: the tile is on a home screen
        // someone else may be holding.
        val store = BrowserShortcutStore()
        store.put(record())
        val resolved = store.resolve("sc_1", deviceBound = false, availableProfiles = setOf("public_research"))
        assertEquals(
            ShortcutResolution.Refused(ShortcutRefusal.DEVICE_NOT_BOUND), resolved,
        )
    }

    @Test
    fun `an unknown shortcut and a revoked one are different answers`() {
        // "I do not know this" and "you removed this" are different sentences, and a
        // launcher tile that survives revocation is the normal case rather than an error.
        val store = BrowserShortcutStore()
        store.put(record())
        assertTrue(store.revoke("sc_1", NOW + 1))
        assertEquals(
            ShortcutResolution.Refused(ShortcutRefusal.REVOKED),
            store.resolve("sc_1", true, setOf("public_research")),
        )
        assertEquals(
            ShortcutResolution.Refused(ShortcutRefusal.UNKNOWN_SHORTCUT),
            store.resolve("sc_missing", true, setOf("public_research")),
        )
    }

    @Test
    fun `a revoked shortcut is not listed and cannot be revived by renaming`() {
        val store = BrowserShortcutStore()
        store.put(record())
        store.revoke("sc_1", NOW + 1)
        assertTrue(store.all().isEmpty())
        assertFalse(store.rename("sc_1", "Something else", null))
        assertEquals(
            ShortcutResolution.Refused(ShortcutRefusal.REVOKED),
            store.resolve("sc_1", true, setOf("public_research")),
        )
    }

    @Test
    fun `revoking twice is not two revocations`() {
        val store = BrowserShortcutStore()
        store.put(record())
        assertTrue(store.revoke("sc_1", NOW + 1))
        assertFalse(store.revoke("sc_1", NOW + 2))
        assertEquals(NOW + 1, store.get("sc_1")?.revokedAtMs)
    }

    @Test
    fun `a profile that no longer exists refuses rather than falling back`() {
        // Falling back to whichever profile is available is how a shortcut to a public
        // page opens in the browser holding the owner's logged-in cookies.
        val store = BrowserShortcutStore()
        store.put(record(profile = "retired_profile"))
        assertEquals(
            ShortcutResolution.Refused(ShortcutRefusal.PROFILE_UNAVAILABLE),
            store.resolve("sc_1", true, setOf("public_research", "authenticated_owner")),
        )
    }

    @Test
    fun `renaming changes the label and never the destination`() {
        // A tile whose destination can be changed in place is a tile the owner cannot
        // trust, and the same icon pointing somewhere new is what a malicious page wants.
        val store = BrowserShortcutStore()
        store.put(record())
        assertTrue(store.rename("sc_1", "Bank statements", "sha256:def"))
        val after = store.get("sc_1")!!
        assertEquals("Bank statements", after.title)
        assertEquals("https://example.com/statements", after.canonicalUrl)
    }
}

/**
 * §17.5 — a link another app handed to VAN.
 */
class BrowserExternalLinkTest {

    @Test
    fun `an ordinary link opens untrusted, in the public profile`() {
        // Not the authenticated one. A link from a messaging app opening in the browser
        // holding the owner's logged-in cookies is the whole of the attack.
        val outcome = BrowserExternalLink.accept("https://example.com/article")
        assertEquals(
            BrowserExternalLink.Outcome.OpenUntrusted(
                "https://example.com/article", BrowserExternalLink.UNTRUSTED_PROFILE,
            ),
            outcome,
        )
        assertEquals("public_research", BrowserExternalLink.UNTRUSTED_PROFILE)
    }

    @Test
    fun `only http and https are accepted`() {
        for (url in listOf(
            "javascript:alert(1)",
            "file:///etc/passwd",
            "content://media/1",
            "intent://x#Intent;scheme=http;end",
            "data:text/html,<h1>x</h1>",
            "vanapp://open",
        )) {
            assertEquals(
                BrowserExternalLink.Outcome.Refused(
                    BrowserExternalLink.Refusal.SCHEME_NOT_ACCEPTED,
                ),
                BrowserExternalLink.accept(url),
                url,
            )
        }
    }

    @Test
    fun `a second scheme inside the address is refused`() {
        // The redirect the sending app wrote. VAN does not carry it across just because
        // the outer scheme was https.
        for (url in listOf(
            "https://example.com/#intent://evil",
            "https://example.com/r?to=javascript:alert(1)",
            "http://example.com/x?next=file:///etc/passwd",
        )) {
            assertEquals(
                BrowserExternalLink.Outcome.Refused(BrowserExternalLink.Refusal.NESTED_SCHEME),
                BrowserExternalLink.accept(url),
                url,
            )
        }
    }

    @Test
    fun `something that is not an address is refused rather than searched`() {
        // Unlike the omnibox: the owner typing is expressing intent, and another app
        // sending VAN a fragment is not.
        for (url in listOf(null, "", "   ", "https:", "https:/example.com", "https://")) {
            assertEquals(
                BrowserExternalLink.Outcome.Refused(BrowserExternalLink.Refusal.MALFORMED),
                BrowserExternalLink.accept(url),
                "$url",
            )
        }
    }
}
