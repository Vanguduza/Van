package com.dial.van.connectivity

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.Base64
import javax.net.ssl.X509TrustManager

/** Signed pins narrow existing private/platform CA trust; they never disable verification. */
class SignedPinTrustManager(
    private val delegates: List<X509TrustManager>,
    private val pins: Set<String>,
) : X509TrustManager {
    override fun getAcceptedIssuers(): Array<X509Certificate> = delegates.flatMap {
        it.acceptedIssuers.toList()
    }.toTypedArray()

    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
        delegates.first().checkClientTrusted(chain, authType)
    }

    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
        require(delegates.isNotEmpty() && pins.isNotEmpty())
        if (chain.isEmpty() || chain.size > 32) throw CertificateException("connectivity_certificate_chain_invalid")
        var accepted = false
        for (trust in delegates) {
            try { trust.checkServerTrusted(chain, authType); accepted = true; break }
            catch (_: CertificateException) { /* Try the other existing CA authority. */ }
        }
        if (!accepted) throw CertificateException("connectivity_certificate_untrusted")
        if (chain.none { certificate ->
            val digest = MessageDigest.getInstance("SHA-256").digest(certificate.publicKey.encoded)
            "sha256/${Base64.getEncoder().encodeToString(digest)}" in pins &&
                belongsToLeafPath(chain.firstOrNull(), certificate, chain, emptySet())
        }) throw CertificateException("connectivity_certificate_pin_mismatch")
    }

    /** Extra peer-supplied certificates are not part of a validated server identity. */
    private fun belongsToLeafPath(
        current: X509Certificate?, pinned: X509Certificate,
        supplied: Array<X509Certificate>, visited: Set<X509Certificate>,
    ): Boolean {
        current ?: return false
        if (current == pinned) return true
        if (current in visited) return false
        return supplied.any { issuer ->
            issuer != current && issuer.basicConstraints >= 0 &&
                current.issuerX500Principal == issuer.subjectX500Principal &&
                runCatching { current.verify(issuer.publicKey) }.isSuccess &&
                belongsToLeafPath(issuer, pinned, supplied, visited + current)
        }
    }
}
