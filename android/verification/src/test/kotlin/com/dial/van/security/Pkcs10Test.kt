package com.dial.van.security

import java.io.File
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The phone's half of the mutual-TLS enrolment contract.
 *
 * `evidence/van-mtls/android_pkcs10_vector.json` holds a CSR produced by this encoder.
 * `backend/tests/test_mtls_pki.py` holds the gateway to accepting it; this holds the encoder
 * to reproducing its signed bytes exactly. ECDSA signatures are randomised, so the vector
 * pins the CertificationRequestInfo, which is deterministic, and the signature is verified
 * rather than compared. Set `VAN_PKCS10_VECTOR_WRITE=1` to regenerate it after a deliberate
 * format change; both sides then have to agree with the new bytes.
 */
class Pkcs10Test {

    private val vectorFile = File("../../evidence/van-mtls/android_pkcs10_vector.json")

    private fun der(pem: String): ByteArray = Base64.getMimeDecoder().decode(
        pem.lineSequence().filterNot { it.startsWith("-----") }.joinToString(""),
    )

    /** Minimal DER reader: (tag, header length, content length) at [offset]. */
    private fun header(bytes: ByteArray, offset: Int): Triple<Int, Int, Int> {
        val tag = bytes[offset].toInt() and 0xFF
        val first = bytes[offset + 1].toInt() and 0xFF
        if (first < 0x80) return Triple(tag, 2, first)
        val count = first and 0x7F
        var length = 0
        for (i in 0 until count) length = (length shl 8) or (bytes[offset + 2 + i].toInt() and 0xFF)
        return Triple(tag, 2 + count, length)
    }

    private fun elements(bytes: ByteArray, start: Int, end: Int): List<ByteArray> {
        val out = mutableListOf<ByteArray>()
        var at = start
        while (at < end) {
            val (_, h, n) = header(bytes, at)
            out += bytes.copyOfRange(at, at + h + n)
            at += h + n
        }
        return out
    }

    @Test
    fun `a request is well formed and signed by the key it carries`() {
        val pair = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val deviceId = "dev_0123456789abcdef"
        val pem = Pkcs10.pem(deviceId, pair.public, pair.private)
        assertTrue(pem.startsWith("-----BEGIN CERTIFICATE REQUEST-----\n"))
        assertTrue(pem.lines().filterNot { it.startsWith("-----") || it.isEmpty() }.all { it.length <= 64 })

        val bytes = der(pem)
        val (tag, h, n) = header(bytes, 0)
        assertEquals(0x30, tag)
        assertEquals(bytes.size, h + n, "outer SEQUENCE must cover the whole request")
        val (info, algorithm, bitString) = elements(bytes, h, h + n)
        assertContentEquals(Pkcs10.requestInfo(deviceId, pair.public), info)
        assertContentEquals(byteArrayOf(0x30, 0x0A, 0x06, 0x08, 0x2A, 0x86.toByte(), 0x48, 0xCE.toByte(), 0x3D, 0x04, 0x03, 0x02), algorithm)
        val (_, bh, bn) = header(bitString, 0)
        assertEquals(0x03, bitString[0].toInt())
        assertEquals(0, bitString[bh].toInt(), "no unused bits")
        val signature = bitString.copyOfRange(bh + 1, bh + bn)
        assertTrue(Signature.getInstance("SHA256withECDSA").run { initVerify(pair.public); update(info); verify(signature) })

        if (System.getenv("VAN_PKCS10_VECTOR_WRITE") == "1") {
            vectorFile.parentFile.mkdirs()
            vectorFile.writeText(
                org.json.JSONObject()
                    .put("device_id", deviceId)
                    .put("public_key_spki_b64", Base64.getEncoder().encodeToString(pair.public.encoded))
                    .put("csr_pem", pem)
                    .toString(2) + "\n",
            )
        }
    }

    @Test
    fun `the encoder reproduces the signed bytes of the request the gateway accepts`() {
        assertTrue(vectorFile.exists(), "vector missing at ${vectorFile.absolutePath}")
        val vector = org.json.JSONObject(vectorFile.readText())
        val publicKey = KeyFactory.getInstance("EC")
            .generatePublic(X509EncodedKeySpec(Base64.getDecoder().decode(vector.getString("public_key_spki_b64"))))
        val bytes = der(vector.getString("csr_pem"))
        val (_, h, n) = header(bytes, 0)
        val info = elements(bytes, h, h + n).first()
        assertContentEquals(info, Pkcs10.requestInfo(vector.getString("device_id"), publicKey))
    }

    @Test
    fun `lengths use the shortest DER form`() {
        assertContentEquals(byteArrayOf(0x04, 0x7F), Pkcs10.tlv(0x04, ByteArray(0x7F)).copyOfRange(0, 2))
        assertContentEquals(byteArrayOf(0x04, 0x81.toByte(), 0x80.toByte()), Pkcs10.tlv(0x04, ByteArray(0x80)).copyOfRange(0, 3))
        assertContentEquals(byteArrayOf(0x04, 0x82.toByte(), 0x01, 0x00), Pkcs10.tlv(0x04, ByteArray(0x100)).copyOfRange(0, 4))
    }
}
