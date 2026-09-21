package com.dial.van.security

import java.math.BigInteger
import java.security.MessageDigest

/**
 * The parts of the proof that are pure arithmetic over bytes, so they can be executed in
 * the JVM harness and compared against the gateway's own implementation by
 * `tests/contracts/test_cross_language_vectors.py`.
 *
 * The gateway builds the same string in `van_gateway/auth/device_proof.py`. One of the two
 * changing — a separator, a case, the order of two fields — produces a signature that
 * verifies nowhere, and the symptom on the phone is every privileged request failing with
 * `device_proof_invalid` and no indication which side is wrong.
 */
object DeviceProofCanonical {

    const val VERSION_TAG: String = "van-device-proof-v1"

    /** Tolerance the gateway allows on `issued_at_ms`; mirrored so the phone can refuse early. */
    const val SKEW_MS: Long = 120_000

    fun signingInput(
        method: String,
        path: String,
        deviceId: String,
        issuedAtMs: Long,
        bodySha256: String,
    ): ByteArray = listOf(
        VERSION_TAG,
        method.uppercase(),
        path,
        deviceId,
        issuedAtMs.toString(),
        bodySha256,
    ).joinToString("\n").toByteArray(Charsets.UTF_8)

    fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /**
     * The fixed-width `r || s` the gateway expects, from the DER the JCA produces.
     *
     * The gateway accepts both spellings, but only this one is a constant 64 bytes — and a
     * DER signature whose `r` happens to start with a high bit gains a leading zero, so a
     * device that sent DER would produce proofs of two different lengths depending on the
     * key and the message. That is exactly the kind of difference that works for weeks.
     */
    fun derToP1363(der: ByteArray): ByteArray {
        var index = 2
        // A long-form length on the outer SEQUENCE (never happens for P-256, but a parser
        // that assumes is a parser that is wrong once).
        if ((der[1].toInt() and 0xFF) >= 0x80) index = 2 + (der[1].toInt() and 0x7F)
        require(der[index].toInt() == 0x02) { "device_proof_signature_malformed" }
        val rLength = der[index + 1].toInt() and 0xFF
        val r = BigInteger(der.copyOfRange(index + 2, index + 2 + rLength))
        index += 2 + rLength
        require(der[index].toInt() == 0x02) { "device_proof_signature_malformed" }
        val sLength = der[index + 1].toInt() and 0xFF
        val s = BigInteger(der.copyOfRange(index + 2, index + 2 + sLength))
        return pad32(r) + pad32(s)
    }

    private fun pad32(value: BigInteger): ByteArray {
        val raw = value.toByteArray().dropWhile { it.toInt() == 0 }.toByteArray()
        require(raw.size <= 32) { "device_proof_signature_malformed" }
        return ByteArray(32 - raw.size) + raw
    }
}
