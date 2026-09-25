package com.dial.van.security

import java.io.ByteArrayOutputStream
import java.nio.charset.StandardCharsets
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import java.util.Base64

/**
 * The smallest PKCS#10 the gateway accepts: subject CN=<device id>, the key's own
 * SubjectPublicKeyInfo, no attributes, ecdsa-with-SHA256. Written out rather than pulled
 * from a library because it is forty lines of DER and the Keystore key cannot be handed to
 * one that wants the private key material.
 */
internal object Pkcs10 {
    private val OID_COMMON_NAME = byteArrayOf(0x55, 0x04, 0x03)                                   // 2.5.4.3
    private val OID_ECDSA_SHA256 = byteArrayOf(0x2A, 0x86.toByte(), 0x48, 0xCE.toByte(), 0x3D, 0x04, 0x03, 0x02) // 1.2.840.10045.4.3.2

    fun build(commonName: String, publicKey: PublicKey, privateKey: PrivateKey): ByteArray {
        val info = requestInfo(commonName, publicKey)
        val signature = Signature.getInstance("SHA256withECDSA").run { initSign(privateKey); update(info); sign() }
        return seq(info, seq(tlv(0x06, OID_ECDSA_SHA256)), tlv(0x03, byteArrayOf(0) + signature))
    }

    /** The signed part: CertificationRequestInfo (version 0, subject, SPKI, empty attributes). */
    fun requestInfo(commonName: String, publicKey: PublicKey): ByteArray {
        val name = seq(set(seq(tlv(0x06, OID_COMMON_NAME), tlv(0x0C, commonName.toByteArray(StandardCharsets.UTF_8)))))
        return seq(tlv(0x02, byteArrayOf(0)), name, publicKey.encoded, tlv(0xA0, ByteArray(0)))
    }

    /** [build], PEM-armoured as the gateway's `csr_pem` field expects. */
    fun pem(commonName: String, publicKey: PublicKey, privateKey: PrivateKey): String {
        val b64 = Base64.getEncoder().encodeToString(build(commonName, publicKey, privateKey)).chunked(64).joinToString("\n")
        return "-----BEGIN CERTIFICATE REQUEST-----\n$b64\n-----END CERTIFICATE REQUEST-----\n"
    }

    private fun seq(vararg parts: ByteArray) = tlv(0x30, concat(parts))
    private fun set(vararg parts: ByteArray) = tlv(0x31, concat(parts))
    private fun concat(parts: Array<out ByteArray>) = ByteArrayOutputStream().apply { parts.forEach { write(it) } }.toByteArray()

    fun tlv(tag: Int, value: ByteArray): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(tag)
        val n = value.size
        when {
            n < 0x80 -> out.write(n)
            n <= 0xFF -> { out.write(0x81); out.write(n) }
            n <= 0xFFFF -> { out.write(0x82); out.write(n shr 8); out.write(n and 0xFF) }
            else -> error("der_too_long")
        }
        out.write(value)
        return out.toByteArray()
    }
}
