package com.dial.van.connectivity

import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.json.JSONObject

/**
 * Rev 1.5 §0D.2 / ADR-RB-027 — the device's half of signed connectivity.
 *
 * The owner build has no field to type a server address into, so this verifier is the only
 * thing standing between a manifest and the endpoints VAN will trust. Every test here is a
 * manifest that is almost acceptable: signed by the wrong key, signed correctly but older
 * than what the device already has, correct but carrying a credential, or correct with one
 * character changed after signing.
 */
class ConnectivityManifestTest {

    private val generator = KeyPairGenerator.getInstance("EC").apply {
        initialize(ECGenParameterSpec("secp256r1"))
    }

    private fun keys(): Pair<java.security.PrivateKey, String> {
        val pair = generator.generateKeyPair()
        val pem = "-----BEGIN PUBLIC KEY-----\n" +
            Base64.getEncoder().encodeToString(pair.public.encoded) +
            "\n-----END PUBLIC KEY-----"
        return pair.private to pem
    }

    /** Signs the same canonical bytes the gateway signs. */
    private fun sign(json: JSONObject, privateKey: java.security.PrivateKey): String {
        val der = Signature.getInstance("SHA256withECDSA").run {
            initSign(privateKey)
            update(ConnectivityManifestVerifier.canonical(json))
            sign()
        }
        // DER to P1363: the wire format is r||s, fixed width.
        var index = 2
        require(der[index].toInt() == 0x02)
        val rLength = der[index + 1].toInt()
        val r = BigInteger(der.copyOfRange(index + 2, index + 2 + rLength))
        index += 2 + rLength
        require(der[index].toInt() == 0x02)
        val sLength = der[index + 1].toInt()
        val s = BigInteger(der.copyOfRange(index + 2, index + 2 + sLength))
        fun pad(value: BigInteger): ByteArray {
            val raw = value.toByteArray().dropWhile { it.toInt() == 0 }.toByteArray()
            return ByteArray(32 - raw.size) + raw
        }
        return (pad(r) + pad(s)).joinToString("") { "%02x".format(it) }
    }

    private fun manifest(version: Int = 3, extra: Map<String, Any> = emptyMap()): JSONObject {
        val json = JSONObject()
            .put("manifest_version", version)
            .put("gateway_url", "https://van.example")
            .put("session_websocket_url", "wss://van.example/v1/session/ws")
            .put("browser_stream_signal_url", "https://stream.example/rtc")
        extra.forEach { (key, value) -> json.put(key, value) }
        return json
    }

    @Test
    fun `a correctly signed manifest is accepted and parsed`() {
        val (privateKey, pem) = keys()
        val json = manifest()
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = json.toString(),
            signatureHex = sign(json, privateKey),
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 2,
        )
        val accepted = verdict as ManifestVerdict.Accepted
        assertEquals("https://van.example", accepted.manifest.gatewayUrl)
        assertTrue(accepted.manifest.hasBrowserStream)
    }

    @Test
    fun `key order and whitespace do not change the verdict`() {
        // The device rebuilds the canonical bytes rather than hashing what arrived, so a
        // manifest that was re-serialized in transit still verifies — and one that was
        // edited still does not.
        val (privateKey, pem) = keys()
        val json = manifest()
        val signature = sign(json, privateKey)
        val reordered = JSONObject(json.toString()).toString().replace(",", ", ")
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = reordered,
            signatureHex = signature,
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 0,
        )
        assertTrue(verdict is ManifestVerdict.Accepted)
    }

    @Test
    fun `one character changed after signing is refused`() {
        val (privateKey, pem) = keys()
        val json = manifest()
        val signature = sign(json, privateKey)
        val tampered = json.put("gateway_url", "https://attacker.example")
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = tampered.toString(),
            signatureHex = signature,
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 0,
        )
        assertEquals(
            "connectivity_manifest_signature_invalid",
            (verdict as ManifestVerdict.Refused).reason,
        )
    }

    @Test
    fun `an unknown signing key is refused rather than tried against every key`() {
        val (privateKey, _) = keys()
        val (_, otherPem) = keys()
        val json = manifest()
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = json.toString(),
            signatureHex = sign(json, privateKey),
            kid = "cfg-unknown",
            trustedKeys = mapOf("cfg-1" to otherPem),
            knownVersion = 0,
        )
        assertEquals(
            "connectivity_manifest_unknown_kid",
            (verdict as ManifestVerdict.Refused).reason,
        )
    }

    @Test
    fun `an older manifest cannot be replayed at a device that has moved on`() {
        val (privateKey, pem) = keys()
        val old = manifest(version = 2)
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = old.toString(),
            signatureHex = sign(old, privateKey),
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 5,
        )
        assertEquals("connectivity_manifest_rollback", (verdict as ManifestVerdict.Refused).reason)
    }

    @Test
    fun `the same version the device already trusts is not applied again`() {
        val (privateKey, pem) = keys()
        val json = manifest(version = 5)
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = json.toString(),
            signatureHex = sign(json, privateKey),
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 5,
        )
        assertTrue(verdict is ManifestVerdict.Refused)
    }

    @Test
    fun `a manifest carrying a credential is refused`() {
        // §0D.2 — this is not configuration. It is a secret in a file the app caches, and a
        // copy of the app would inherit it.
        val (privateKey, pem) = keys()
        val json = manifest(extra = mapOf("pairing_token" to "secret"))
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = json.toString(),
            signatureHex = sign(json, privateKey),
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 0,
        )
        assertTrue(
            (verdict as ManifestVerdict.Refused).reason.startsWith(
                "connectivity_manifest_carries_credential",
            ),
        )
    }

    @Test
    fun `an unversioned manifest is refused`() {
        val (privateKey, pem) = keys()
        val json = JSONObject().put("gateway_url", "https://van.example")
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = json.toString(),
            signatureHex = sign(json, privateKey),
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 0,
        )
        assertEquals(
            "connectivity_manifest_unversioned",
            (verdict as ManifestVerdict.Refused).reason,
        )
    }

    @Test
    fun `malformed json is refused rather than throwing at the caller`() {
        val (_, pem) = keys()
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = "{not json",
            signatureHex = "00".repeat(64),
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 0,
        )
        assertEquals("connectivity_manifest_malformed", (verdict as ManifestVerdict.Refused).reason)
    }

    @Test
    fun `a signature of the wrong length is refused`() {
        val (_, pem) = keys()
        val json = manifest()
        val verdict = ConnectivityManifestVerifier.verify(
            manifestJson = json.toString(),
            signatureHex = "abcd",
            kid = "cfg-1",
            trustedKeys = mapOf("cfg-1" to pem),
            knownVersion = 0,
        )
        assertEquals(
            "connectivity_manifest_signature_invalid",
            (verdict as ManifestVerdict.Refused).reason,
        )
    }
}
