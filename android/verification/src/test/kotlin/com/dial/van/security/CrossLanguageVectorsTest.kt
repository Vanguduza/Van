package com.dial.van.security

import java.io.File
import java.security.MessageDigest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.json.JSONObject

/**
 * The device's half of two formats the gateway also implements.
 *
 * The vectors in `evidence/van-remote-browser/cross_language_vectors.json` were produced by
 * the gateway. `tests/contracts/test_cross_language_vectors.py` keeps them in step with the
 * Python implementation; this keeps the Kotlin one in step with them. Neither side can drift
 * without one of the two failing, which is the property a pair of independently-tested
 * implementations does not have.
 *
 * The case that motivated this: both canonicalizers sorted keys and dropped whitespace and
 * agreed on every ASCII document, while Python escaped non-ASCII and Kotlin did not. A
 * profile alias with an accent in it produced a digest that matched nowhere.
 */
class CrossLanguageVectorsTest {

    private val vectors: JSONObject by lazy {
        val file = File("../../evidence/van-remote-browser/cross_language_vectors.json")
        assertTrue(file.exists(), "vectors missing at ${file.absolutePath}")
        JSONObject(file.readText(Charsets.UTF_8))
    }

    private fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Test
    fun `canonical json matches the gateway byte for byte`() {
        val cases = vectors.getJSONArray("canonical_json")
        assertTrue(cases.length() >= 6, "too few cases to prove anything")
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val payload = case.getJSONObject("payload")
            assertEquals(
                case.getString("canonical"),
                VanCanonicalJson.render(payload),
                "canonical form diverged for ${payload}",
            )
            assertEquals(case.getString("sha256"), VanCanonicalJson.sha256Hex(payload))
        }
    }

    @Test
    fun `the device proof signing input matches the gateway`() {
        val cases = vectors.getJSONArray("device_proof")
        assertTrue(cases.length() >= 3)
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val body = case.getString("body_utf8").toByteArray(Charsets.UTF_8)
            assertEquals(case.getString("body_sha256"), DeviceProofCanonical.sha256Hex(body))
            val signingInput = DeviceProofCanonical.signingInput(
                method = case.getString("method"),
                path = case.getString("path"),
                deviceId = case.getString("device_id"),
                issuedAtMs = case.getLong("issued_at_ms"),
                bodySha256 = case.getString("body_sha256"),
            )
            assertEquals(
                case.getString("signing_input_sha256"),
                sha256Hex(signingInput),
                "signing input diverged for ${case.getString("path")}",
            )
        }
    }

    @Test
    fun `a key order the gateway never used still canonicalizes the same`() {
        // The vectors are serialized documents, so the payloads arrive in one order. The
        // rule being tested is that order does not matter, and a fixture cannot show that
        // by itself.
        val a = JSONObject().put("z", 1).put("a", 2).put("m", 3)
        val b = JSONObject().put("m", 3).put("a", 2).put("z", 1)
        assertEquals(VanCanonicalJson.render(a), VanCanonicalJson.render(b))
        assertEquals("""{"a":2,"m":3,"z":1}""", VanCanonicalJson.render(a))
    }

    @Test
    fun `a lowercase method signs the same bytes as an uppercase one`() {
        assertEquals(
            DeviceProofCanonical.signingInput("POST", "/p", "d", 1, "abc").toList(),
            DeviceProofCanonical.signingInput("post", "/p", "d", 1, "abc").toList(),
        )
    }

    @Test
    fun `a signature is always sixty four bytes whatever the DER spelling`() {
        // A DER integer whose leading bit is set gains a padding zero, so the same key
        // produces signatures of two different lengths. The gateway accepts both, which is
        // exactly why a device that sent DER would work until it did not.
        val r = ByteArray(33).also { it[0] = 0; it[1] = 0xFF.toByte() }
        val s = ByteArray(32).also { it[0] = 0x01 }
        val der = byteArrayOf(0x30, (2 + r.size + 2 + s.size).toByte()) +
            byteArrayOf(0x02, r.size.toByte()) + r +
            byteArrayOf(0x02, s.size.toByte()) + s
        assertEquals(64, DeviceProofCanonical.derToP1363(der).size)
    }
}
