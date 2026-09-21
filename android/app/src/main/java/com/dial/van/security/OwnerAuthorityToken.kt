package com.dial.van.security

import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import java.util.Base64

/**
 * Pure codec for VATI's short-lived owner-authority token.
 *
 * This class never touches Android Keystore. It prepares the exact canonical
 * statement that must be signed under BIOMETRIC_STRONG and assembles the
 * resulting DER ECDSA signature into the wire token accepted by
 * vati.authority.OwnerAuthorityVerifier.
 */
object OwnerAuthorityToken {
    const val PREFIX = "van-oa1"
    const val DEFAULT_LIFETIME_SECONDS = 300L
    private const val NONCE_BYTES = 18

    data class Prepared(
        val act: String,
        val subject: String,
        val keyId: String,
        val issuedAtUnix: Long,
        val expiresAtUnix: Long,
        val nonce: String,
    ) {
        init {
            require(act.isNotBlank()) { "owner_authority_act_blank" }
            require(subject.isNotBlank()) { "owner_authority_subject_blank" }
            require(keyId.isNotBlank()) { "owner_authority_key_id_blank" }
            require(nonce.isNotBlank()) { "owner_authority_nonce_blank" }
            require(expiresAtUnix > issuedAtUnix) { "owner_authority_expiry_invalid" }
        }

        val canonical: String
            get() = listOf(
                PREFIX,
                act,
                subject,
                issuedAtUnix.toString(),
                expiresAtUnix.toString(),
                nonce,
            ).joinToString("|")

        val payloadJson: String
            get() = "{" +
                "\"act\":" + quote(act) + "," +
                "\"exp\":" + expiresAtUnix + "," +
                "\"iat\":" + issuedAtUnix + "," +
                "\"kid\":" + quote(keyId) + "," +
                "\"nonce\":" + quote(nonce) + "," +
                "\"subject\":" + quote(subject) +
                "}"

        val payloadBase64Url: String
            get() = base64Url(payloadJson.toByteArray(StandardCharsets.UTF_8))

        fun assembleFromSignatureBase64(signatureBase64: String): String {
            val signature = Base64.getDecoder().decode(signatureBase64)
            require(signature.isNotEmpty()) { "owner_authority_signature_blank" }
            return PREFIX + "." + payloadBase64Url + "." + base64Url(signature)
        }
    }

    fun prepare(
        act: String,
        subject: String,
        keyId: String,
        issuedAtUnix: Long,
        lifetimeSeconds: Long = DEFAULT_LIFETIME_SECONDS,
        nonce: String = randomNonce(),
    ): Prepared {
        require(lifetimeSeconds in 1..DEFAULT_LIFETIME_SECONDS) {
            "owner_authority_lifetime_out_of_bounds"
        }
        return Prepared(
            act = act,
            subject = subject,
            keyId = keyId,
            issuedAtUnix = issuedAtUnix,
            expiresAtUnix = issuedAtUnix + lifetimeSeconds,
            nonce = nonce,
        )
    }

    private fun randomNonce(): String {
        val bytes = ByteArray(NONCE_BYTES).also { SecureRandom().nextBytes(it) }
        return base64Url(bytes)
    }

    private fun base64Url(bytes: ByteArray): String =
        Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)

    /**
     * Python's json.dumps(sort_keys=True,separators=(",",":")) uses ensure_ascii=True
     * by default. Payload field order is already alphabetical above, so this quote
     * function preserves byte-for-byte compatibility, including surrogate pairs.
     */
    private fun quote(value: String): String = buildString {
        append('"')
        value.forEach { ch ->
            when (ch) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\b' -> append("\\b")
                '\u000C' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> when {
                    ch.code < 0x20 || ch.code > 0x7E ->
                        append("\\u").append(ch.code.toString(16).padStart(4, '0'))
                    else -> append(ch)
                }
            }
        }
        append('"')
    }
}
