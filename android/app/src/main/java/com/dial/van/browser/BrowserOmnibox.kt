package com.dial.van.browser

/**
 * Rev 1.5 §17.2 — what the owner typed, and what VAN does with it before anything leaves
 * the phone.
 *
 * Two rules, and the second is the one with teeth.
 *
 * **The classification happens locally.** "Is this a URL or a search?" is decided here,
 * from the text, with no network. A remote classifier would mean every keystroke's worth
 * of context travelling somewhere before the owner has decided to go anywhere.
 *
 * **Typed input is not leaked to a suggestion provider without policy.** §17.2 states it
 * directly, and the reason is that an address bar is where people type things they have
 * not decided to say: half a bank's name, a medical term, someone's address. VAN's default
 * is that none of it goes anywhere, and `SuggestionPolicy.OFF` is what that looks like —
 * an omnibox that suggests nothing rather than one that suggests quietly.
 */

enum class OmniboxIntent {
    /** A URL, complete or completable. Navigation goes to exactly this. */
    NAVIGATE,

    /** Not a URL. It becomes a query for the configured engine, resolved on the host. */
    SEARCH,
}

data class OmniboxResolution(
    val intent: OmniboxIntent,
    /** The URL to navigate to, or the query text to search for. Never both. */
    val value: String,
    /** Why this was classified as it was, for the owner and for evidence. */
    val reason: String,
)

/**
 * §17.2 — whether VAN may ask anything about what is being typed.
 *
 * Deliberately not a boolean. `OFF` and `LOCAL_HISTORY_ONLY` are both "nothing leaves the
 * device", and collapsing them would make the owner's choice between "suggest nothing" and
 * "suggest from what I have already visited" unexpressable.
 */
enum class SuggestionPolicy {
    /** Nothing is suggested and nothing is consulted. The default. */
    OFF,

    /** Suggestions come from what this device already knows. No request is made. */
    LOCAL_HISTORY_ONLY,

    /**
     * The owner has explicitly allowed typed text to reach a provider through the
     * Gateway. Never a default, and never inferred from the search engine setting: a
     * choice about where a *committed* search goes is not a choice about every keystroke.
     */
    REMOTE_WITH_OWNER_CONSENT,

    ;

    val leavesTheDevice: Boolean get() = this == REMOTE_WITH_OWNER_CONSENT
}

object BrowserOmnibox {

    /**
     * Schemes VAN will navigate to from the address bar.
     *
     * Everything else — `file:`, `content:`, `javascript:`, `data:`, `chrome:`,
     * `intent:` — is treated as text to search for rather than refused, because the owner
     * typing "file: not found" meant a search and an owner typing `javascript:` meant
     * something VAN will not do either way. Searching is the safe reading of both.
     */
    private val NAVIGABLE_SCHEMES = setOf("http", "https")

    private val SCHEME = Regex("^([A-Za-z][A-Za-z0-9+.\\-]*):")

    /**
     * `host:8080/admin` is a host and a port, not a scheme called `host`.
     *
     * The scheme pattern matches both, and without this `localhost:8080` classified as
     * "scheme not navigable" and became a search. It is the shape anyone developing
     * against a local service types first.
     */
    private val HOST_AND_PORT = Regex("^[A-Za-z][A-Za-z0-9+.\\-]*:\\d+([/?#].*)?$")

    /**
     * Hosts with no dot that are still hosts. `localhost` is here because someone will
     * type it; it resolves on the *host*, not the phone, which is worth knowing.
     */
    private val DOTLESS_HOSTS = setOf("localhost")

    /**
     * A last label that looks like a real TLD: letters only, at least two of them.
     *
     * Deliberately not a public-suffix list. A list would make "example.zzz" a search and
     * "example.dev" a navigation, and the owner's expectation is the opposite of precise:
     * something with a dot and no spaces is an address. Punycode is allowed through as
     * `xn--...`, which is letters and digits and hyphens by construction.
     */
    private val TLD_LIKE = Regex("^(xn--[A-Za-z0-9\\-]+|[A-Za-z]{2,})$")

    fun resolve(typed: String): OmniboxResolution {
        val text = typed.trim()
        if (text.isEmpty()) {
            return OmniboxResolution(OmniboxIntent.SEARCH, "", "empty")
        }

        val scheme = SCHEME.find(text)
            ?.takeIf { !HOST_AND_PORT.matches(text) }
            ?.groupValues?.get(1)?.lowercase()
        if (scheme != null) {
            if (scheme in NAVIGABLE_SCHEMES) {
                return OmniboxResolution(OmniboxIntent.NAVIGATE, text, "explicit_scheme")
            }
            // A scheme VAN does not navigate. Searched rather than refused: the owner who
            // typed `mailto: bob` meant something, and a refusal dialog teaches nothing.
            return OmniboxResolution(OmniboxIntent.SEARCH, text, "scheme_not_navigable:$scheme")
        }

        // A space anywhere means a query. "site:example.com pricing" is a search, and an
        // address with a space in it is not an address.
        if (text.any { it.isWhitespace() }) {
            return OmniboxResolution(OmniboxIntent.SEARCH, text, "contains_whitespace")
        }

        val authority = text.substringBefore('/').substringBefore('?').substringBefore('#')
        val host = authority.substringBefore(':').substringAfterLast('@')
        if (host.isEmpty()) {
            return OmniboxResolution(OmniboxIntent.SEARCH, text, "no_host")
        }
        if (host.lowercase() in DOTLESS_HOSTS) {
            return OmniboxResolution(
                OmniboxIntent.NAVIGATE, "https://$text", "known_dotless_host",
            )
        }
        if (host.count { it == '.' } == 0) {
            return OmniboxResolution(OmniboxIntent.SEARCH, text, "single_label")
        }
        val lastLabel = host.substringAfterLast('.')
        if (!TLD_LIKE.matches(lastLabel)) {
            // "3.14" and "version.2" are not addresses whatever else they are.
            return OmniboxResolution(OmniboxIntent.SEARCH, text, "last_label_not_tld_like")
        }
        if (host.split('.').any { it.isEmpty() }) {
            return OmniboxResolution(OmniboxIntent.SEARCH, text, "empty_label")
        }
        // §9.14's rule, applied to the owner's own typing rather than to a foreign intent:
        // VAN adds https, never http. An owner who wants the insecure one types it.
        return OmniboxResolution(OmniboxIntent.NAVIGATE, "https://$text", "inferred_https")
    }

    /**
     * Whether this keystroke may be sent anywhere at all.
     *
     * Asked per keystroke rather than once, because the policy can change between one and
     * the next and the expensive mistake is the request that went out after the owner
     * turned suggestions off.
     */
    fun mayRequestSuggestions(policy: SuggestionPolicy, typed: String): Boolean {
        if (!policy.leavesTheDevice) return false
        val text = typed.trim()
        if (text.isEmpty()) return false
        // What is already a URL is not a query, and sending it would tell a provider the
        // page the owner is about to open rather than what they are looking for.
        if (resolve(text).intent == OmniboxIntent.NAVIGATE) return false
        // Credentials in the text mean the owner pasted something they should not have,
        // and it does not become safer by being a search.
        if (text.contains('@') && text.contains(':')) return false
        return true
    }
}
