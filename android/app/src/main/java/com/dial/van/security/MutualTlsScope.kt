package com.dial.van.security

import java.net.URI

/**
 * Which connections the pinned VAN CA and the client certificate apply to: exactly the direct
 * gateway endpoint compiled into the build (same scheme, host and port), and nothing else.
 *
 * Applying them everywhere would break any other HTTPS the app makes, and would strand a phone
 * whose saved gateway URL still points at an older, publicly-certified route: every call there
 * would fail verification against the private CA.
 */
object MutualTlsScope {
    fun applies(directBaseUrl: String, target: String): Boolean {
        val direct = authority(directBaseUrl) ?: return false
        return authority(target) == direct
    }

    /** `host:port` of an https or wss URL, with default ports made explicit; null for anything else. */
    private fun authority(url: String): String? {
        val uri = runCatching { URI(url.trim()) }.getOrNull() ?: return null
        val scheme = uri.scheme?.lowercase() ?: return null
        if (scheme != "https" && scheme != "wss") return null
        val host = uri.host?.lowercase()?.takeIf { it.isNotEmpty() } ?: return null
        val port = if (uri.port == -1) 443 else uri.port
        return "$host:$port"
    }
}
