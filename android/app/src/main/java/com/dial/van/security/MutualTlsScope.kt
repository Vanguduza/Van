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

    /**
     * The gateway address to use. A build that pins a direct endpoint (an https address and
     * a CA) always uses it, even over an address saved on the phone by an earlier build or
     * provisioning. That is how a phone paired over an older route moves to the direct link
     * on upgrade, keeping its device id and tokens, which the same gateway issued. The value
     * comes from the signed APK, never from anything typed or received, so this is not a
     * "change server address" path. Otherwise the saved address, or null for the caller's
     * default.
     */
    fun effectiveBaseUrl(saved: String?, buildDirect: String, buildPinsCa: Boolean): String? {
        val direct = buildDirect.trim().trimEnd('/')
        if (buildPinsCa && authority(direct) != null) return direct
        return saved?.trim()?.takeIf { it.isNotEmpty() }
    }

    /**
     * Routes the gateway answers without a client certificate: what a phone must reach
     * before it holds one. Must equal `_NO_CERT_POSTS` in
     * backend/van_gateway/mtls/transport.py (tests/contracts holds the two together).
     * These go over a channel that never presents a certificate, so a connection or TLS
     * session opened for them is never reused for a call that needs one.
     */
    val PRE_ENROLMENT_PATHS: Set<String> = setOf(
        "/v1/devices/pair",
        "/v1/devices/bootstrap/challenge",
        "/v1/devices/bootstrap/attest",
        "/v1/devices/tls-certificate",
    )

    fun isPreEnrolment(url: String): Boolean {
        val path = runCatching { URI(url.trim()).path }.getOrNull() ?: return false
        return path in PRE_ENROLMENT_PATHS
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
