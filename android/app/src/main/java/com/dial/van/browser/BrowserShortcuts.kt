package com.dial.van.browser

/**
 * Rev 1.5 §5.8 and ADR-RB-023 — home-screen shortcuts, and the authority they do not carry.
 *
 * A launcher shortcut is a file on a filesystem VAN does not control. Anything inside one
 * is readable by whatever can read the launcher's data, survives an uninstall of VAN in
 * some launchers, and is copied to a new device by a backup VAN did not consent to. So
 * ADR-RB-023's rule is absolute: **a shortcut contains an opaque id and presentation, and
 * nothing else.** Not a token, not a cookie, not a grant, not even a session identifier.
 *
 * The id resolves through this registry, and then normal device authentication happens.
 * A shortcut is a bookmark with a stable name; it is never a way in.
 *
 * Pure, so the rule can be executed rather than reviewed: `launcherPayload` is the exact
 * set of fields that leave VAN, and a test asserts that set rather than trusting the call
 * site to have remembered.
 */

/** §5.8's record, held in VAN's own protected storage. */
data class BrowserShortcutRecord(
    val shortcutId: String,
    val canonicalUrl: String,
    val title: String,
    val faviconDigestOrRef: String? = null,
    val profileAlias: String,
    val createdAtMs: Long,
    val lastOpenedAtMs: Long? = null,
    val sensitivity: ShortcutSensitivity = ShortcutSensitivity.ORDINARY,
    val revokedAtMs: Long? = null,
) {
    val revoked: Boolean get() = revokedAtMs != null
}

/**
 * Whether the page behind this shortcut is one the owner was logged into.
 *
 * It changes what the *launcher* is allowed to show, not whether the shortcut works: a
 * pinned tile whose label is "Inbox — owner@example.com" tells anyone holding the phone
 * something about the owner before it is unlocked.
 */
enum class ShortcutSensitivity {
    /** A public page. Its own title is fine on a home screen. */
    ORDINARY,

    /** Behind a login. The tile says VAN, not what the page is. */
    AUTHENTICATED,
}

/** Why a shortcut did not open. Each is a different thing to tell the owner. */
enum class ShortcutRefusal {
    UNKNOWN_SHORTCUT,
    REVOKED,
    DEVICE_NOT_BOUND,
    PROFILE_UNAVAILABLE,
}

sealed interface ShortcutResolution {
    data class Open(val record: BrowserShortcutRecord) : ShortcutResolution
    data class Refused(val reason: ShortcutRefusal) : ShortcutResolution
}

/**
 * The fields that go into the launcher. This type existing at all is the point: the
 * shortcut is built from *this*, not from a `BrowserShortcutRecord`, so a field added to
 * the record cannot leak onto the home screen by being in scope.
 */
data class ShortcutLauncherPayload(
    val shortcutId: String,
    val label: String,
    val iconRef: String?,
)

class BrowserShortcutStore(
    private val records: MutableMap<String, BrowserShortcutRecord> = linkedMapOf(),
) {

    fun all(): List<BrowserShortcutRecord> = records.values.filterNot { it.revoked }

    fun put(record: BrowserShortcutRecord) {
        records[record.shortcutId] = record
    }

    fun get(shortcutId: String): BrowserShortcutRecord? = records[shortcutId]

    /**
     * ADR-RB-023 — revoked, not deleted.
     *
     * The tile stays on the home screen until the launcher is told, and a launcher that is
     * never told is the normal case. A deleted record makes that tile
     * `UNKNOWN_SHORTCUT`, which reads as "VAN is broken"; a revoked one can say "you
     * removed this", which is what happened.
     */
    fun revoke(shortcutId: String, nowMs: Long): Boolean {
        val existing = records[shortcutId] ?: return false
        if (existing.revoked) return false
        records[shortcutId] = existing.copy(revokedAtMs = nowMs)
        return true
    }

    /**
     * The owner renamed the page, or its favicon changed.
     *
     * The canonical URL is deliberately not updatable: a shortcut whose destination can be
     * changed in place is a shortcut the owner cannot trust, and the same tile pointing
     * somewhere new is exactly what a malicious page would want.
     */
    fun rename(shortcutId: String, title: String, faviconDigestOrRef: String?): Boolean {
        val existing = records[shortcutId] ?: return false
        if (existing.revoked) return false
        records[shortcutId] = existing.copy(title = title, faviconDigestOrRef = faviconDigestOrRef)
        return true
    }

    fun markOpened(shortcutId: String, nowMs: Long) {
        records[shortcutId]?.let { records[shortcutId] = it.copy(lastOpenedAtMs = nowMs) }
    }

    /**
     * §5.8 — "if the shortcut record is missing, revoked or device binding is invalid, the
     * shortcut does not navigate."
     *
     * All three, in that order, and each with its own reason: "I do not know this
     * shortcut" and "this phone is not the owner's device" are different sentences and the
     * second is the one worth reading twice.
     */
    fun resolve(
        shortcutId: String,
        deviceBound: Boolean,
        availableProfiles: Set<String>,
    ): ShortcutResolution {
        val record = records[shortcutId]
            ?: return ShortcutResolution.Refused(ShortcutRefusal.UNKNOWN_SHORTCUT)
        if (record.revoked) return ShortcutResolution.Refused(ShortcutRefusal.REVOKED)
        if (!deviceBound) return ShortcutResolution.Refused(ShortcutRefusal.DEVICE_NOT_BOUND)
        if (record.profileAlias !in availableProfiles) {
            return ShortcutResolution.Refused(ShortcutRefusal.PROFILE_UNAVAILABLE)
        }
        return ShortcutResolution.Open(record)
    }

    companion object {
        /** The label a generic "open VAN Browser" tile carries. */
        const val GENERIC_LABEL = "VAN Browser"

        /**
         * ADR-RB-023 — everything that may not appear in a shortcut.
         *
         * Named rather than described so a test can look for them. The list is the
         * decision; the payload type is the mechanism.
         */
        val FORBIDDEN_IN_A_SHORTCUT = setOf(
            "gateway_token", "device_token", "profile_cookie", "browser_stream_grant",
            "turn_credential", "hermes_token", "session_id", "control_lease_id",
        )

        /**
         * What the launcher is given, and all it is given.
         *
         * An authenticated page's own title does not go on a home screen: a tile reading
         * "Inbox — owner@example.com" tells whoever picks the phone up who owns it and
         * where they bank, before it is unlocked.
         */
        fun launcherPayload(record: BrowserShortcutRecord): ShortcutLauncherPayload =
            when (record.sensitivity) {
                ShortcutSensitivity.ORDINARY -> ShortcutLauncherPayload(
                    shortcutId = record.shortcutId,
                    label = record.title.ifBlank { GENERIC_LABEL },
                    iconRef = record.faviconDigestOrRef,
                )
                ShortcutSensitivity.AUTHENTICATED -> ShortcutLauncherPayload(
                    shortcutId = record.shortcutId,
                    label = GENERIC_LABEL,
                    // Not the site's favicon either: a bank's mark on a home screen says
                    // the same thing its name would.
                    iconRef = null,
                )
            }
    }
}

/**
 * §17.5 — an http/https link another app handed to VAN.
 *
 * Rev 1.5 as issued cross-references a "§9.14" that the document does not contain, so the
 * rule is stated here in full rather than by reference: **an external VIEW intent is
 * untrusted navigation input, not an owner command.** It opens an address in a session the
 * owner can see. It does not create a Mission, it does not carry authority, and it never
 * reaches the authenticated profile — a link from a messaging app that opened in the
 * browser holding the owner's logged-in cookies is the whole of the attack.
 */
object BrowserExternalLink {

    /** The only two schemes VAN accepts from another app. */
    private val ACCEPTED_SCHEMES = setOf("http", "https")

    enum class Refusal {
        SCHEME_NOT_ACCEPTED,
        MALFORMED,
        /** An `intent:` URL wrapping something else, or a nested scheme. */
        NESTED_SCHEME,
    }

    sealed interface Outcome {
        /**
         * Open it — in the public profile, with no Mission and no authority.
         *
         * `profileAlias` is fixed rather than a parameter on purpose: a caller that could
         * choose would eventually choose the authenticated one.
         */
        data class OpenUntrusted(val url: String, val profileAlias: String) : Outcome

        data class Refused(val reason: Refusal) : Outcome
    }

    const val UNTRUSTED_PROFILE = "public_research"

    fun accept(rawUrl: String?): Outcome {
        val url = rawUrl?.trim().orEmpty()
        if (url.isEmpty()) return Outcome.Refused(Refusal.MALFORMED)
        val scheme = url.substringBefore(':', missingDelimiterValue = "").lowercase()
        if (scheme !in ACCEPTED_SCHEMES) return Outcome.Refused(Refusal.SCHEME_NOT_ACCEPTED)
        val rest = url.substringAfter(':')
        if (!rest.startsWith("//")) return Outcome.Refused(Refusal.MALFORMED)
        val authority = rest.removePrefix("//").substringBefore('/')
            .substringBefore('?').substringBefore('#')
        if (authority.isEmpty()) return Outcome.Refused(Refusal.MALFORMED)
        // `https://example.com/#intent://...` and friends: a second scheme anywhere in the
        // address is a redirect the sending app wrote, and VAN does not carry it.
        if (NESTED.containsMatchIn(url.substringAfter("//"))) {
            return Outcome.Refused(Refusal.NESTED_SCHEME)
        }
        return Outcome.OpenUntrusted(url, UNTRUSTED_PROFILE)
    }

    private val NESTED = Regex("(?i)\\b(intent|javascript|data|file|content|chrome)\\s*:")
}
