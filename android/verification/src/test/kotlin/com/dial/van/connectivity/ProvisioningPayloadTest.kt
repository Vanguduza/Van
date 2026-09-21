package com.dial.van.connectivity

import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.json.JSONObject

/**
 * Rev 1.5 ADR-RB-026 — the only way into a production VAN, and every way it is refused.
 *
 * The payload travels over ADB, through a shell, and can end up in a device log. That is
 * acceptable only because three properties hold at once: it expires in minutes, it is
 * single-use, and it is not sufficient on its own to enrol. Two of those three are decided
 * here, so each has a test that fails if it is relaxed — and the third, hardware
 * attestation, is §0D.3's and is checked at the Gateway.
 *
 * Every case below is a payload that is *almost* acceptable, because a payload that is
 * obviously wrong was never the risk.
 */
class ProvisioningPayloadTest {

    private val generator = KeyPairGenerator.getInstance("EC").apply {
        initialize(ECGenParameterSpec("secp256r1"))
    }

    private fun keys(): Pair<PrivateKey, String> {
        val pair = generator.generateKeyPair()
        val pem = "-----BEGIN PUBLIC KEY-----\n" +
            Base64.getEncoder().encodeToString(pair.public.encoded) +
            "\n-----END PUBLIC KEY-----"
        return pair.private to pem
    }

    private fun sign(json: JSONObject, privateKey: PrivateKey): String {
        val der = Signature.getInstance("SHA256withECDSA").run {
            initSign(privateKey)
            update(ConnectivityManifestVerifier.canonical(json))
            sign()
        }
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

    private val token = "b".repeat(43)

    private fun payload(
        extra: Map<String, Any> = emptyMap(),
        remove: Set<String> = emptySet(),
    ): JSONObject {
        val json = JSONObject()
            .put("payload_version", ProvisioningVerifier.PAYLOAD_VERSION)
            .put("provisioning_id", "prov_abc123")
            .put("gateway_url", "https://van.example")
            .put("pairing_token", token)
            .put("bootstrap_token", token)
            .put("attestation_challenge", "chal-1")
            .put("expected_manifest_version", 4)
            .put("issued_at_ms", 1_000L)
            .put("expires_at_ms", 601_000L)
        extra.forEach { (k, v) -> json.put(k, v) }
        remove.forEach { json.remove(it) }
        return json
    }

    private fun verify(
        json: JSONObject = payload(),
        key: PrivateKey? = null,
        pem: String? = null,
        kid: String = "prov-1",
        nowMs: Long = 2_000L,
        alreadyAccepted: Set<String> = emptySet(),
        allowInsecureLoopback: Boolean = false,
        signature: String? = null,
    ): ProvisioningVerdict {
        val (generated, generatedPem) = keys()
        val privateKey = key ?: generated
        val publicPem = pem ?: generatedPem
        return ProvisioningVerifier.verify(
            payloadJson = json.toString(),
            signatureHex = signature ?: sign(json, privateKey),
            kid = kid,
            trustedKeys = mapOf("prov-1" to publicPem),
            nowMs = nowMs,
            alreadyAccepted = alreadyAccepted,
            allowInsecureLoopback = allowInsecureLoopback,
        )
    }

    private fun reasonOf(verdict: ProvisioningVerdict): String =
        (verdict as ProvisioningVerdict.Refused).reason

    @Test
    fun `a payload the installer just minted is accepted`() {
        val (privateKey, pem) = keys()
        val verdict = verify(key = privateKey, pem = pem)
        val accepted = verdict as ProvisioningVerdict.Accepted
        assertEquals("https://van.example", accepted.payload.gatewayUrl)
        assertEquals(token, accepted.payload.bootstrapToken)
        assertEquals(4, accepted.payload.expectedManifestVersion)
    }

    @Test
    fun `a payload signed by a key this build does not pin is refused`() {
        // Not "tried against every key we hold": an unknown kid is the end of it.
        val (privateKey, _) = keys()
        val (_, otherPem) = keys()
        assertEquals(
            "provisioning_signature_invalid",
            reasonOf(verify(key = privateKey, pem = otherPem)),
        )
    }

    @Test
    fun `an unknown kid is refused before anything else is read`() {
        assertEquals("provisioning_unknown_kid", reasonOf(verify(kid = "someone-elses-key")))
    }

    @Test
    fun `a payload altered after signing is refused`() {
        val (privateKey, pem) = keys()
        val original = payload()
        val signature = sign(original, privateKey)
        // The attacker's own Gateway, one field changed, signature untouched.
        val tampered = payload(extra = mapOf("gateway_url" to "https://attacker.example"))
        assertEquals(
            "provisioning_signature_invalid",
            reasonOf(verify(json = tampered, key = privateKey, pem = pem, signature = signature)),
        )
    }

    @Test
    fun `an expired payload is refused even with a perfect signature`() {
        // The first of the three properties that make the ADB channel survivable. A
        // payload read out of a log an hour later must be worth nothing.
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_payload_expired",
            reasonOf(verify(key = privateKey, pem = pem, nowMs = 601_000L)),
        )
    }

    @Test
    fun `a payload with no expiry at all is refused rather than treated as immortal`() {
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_payload_has_no_expiry",
            reasonOf(verify(json = payload(remove = setOf("expires_at_ms")), key = privateKey, pem = pem)),
        )
    }

    @Test
    fun `a payload this device has already accepted is refused`() {
        // The second property. A replay of our own payload has a perfect signature, so
        // this cannot be a signature check — and refusing it here means the replay never
        // reaches the network and this device can say what happened.
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_already_used",
            reasonOf(verify(key = privateKey, pem = pem, alreadyAccepted = setOf("prov_abc123"))),
        )
    }

    @Test
    fun `a payload carrying a standing credential is refused`() {
        // The bootstrap token is fine — earning a credential is the point. An ingress
        // token is not: it would still be valid tomorrow, and no expiry on the envelope
        // repairs a secret that outlives it.
        val (privateKey, pem) = keys()
        val verdict = verify(
            json = payload(extra = mapOf("ingress_token" to "t".repeat(40))),
            key = privateKey, pem = pem,
        )
        assertTrue(
            reasonOf(verdict).startsWith("provisioning_carries_standing_credential:"),
            reasonOf(verdict),
        )
    }

    @Test
    fun `every forbidden field is actually refused`() {
        val (privateKey, pem) = keys()
        for (field in ProvisioningVerifier.FORBIDDEN_FIELDS) {
            val verdict = verify(
                json = payload(extra = mapOf(field to "value")), key = privateKey, pem = pem,
            )
            assertEquals(
                "provisioning_carries_standing_credential:$field", reasonOf(verdict), field,
            )
        }
    }

    @Test
    fun `a plain http gateway is refused in a release build`() {
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_url_must_use_https",
            reasonOf(verify(
                json = payload(extra = mapOf("gateway_url" to "http://van.example")),
                key = privateKey, pem = pem,
            )),
        )
    }

    @Test
    fun `loopback over http is accepted only when the build says so`() {
        val (privateKey, pem) = keys()
        val json = payload(extra = mapOf("gateway_url" to "http://127.0.0.1:8787"))
        assertEquals(
            "provisioning_url_must_use_https",
            reasonOf(verify(json = json, key = privateKey, pem = pem)),
        )
        assertTrue(
            verify(json = json, key = privateKey, pem = pem, allowInsecureLoopback = true)
                is ProvisioningVerdict.Accepted,
        )
    }

    @Test
    fun `an unsupported payload version is refused rather than parsed as this one`() {
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_payload_version_unsupported",
            reasonOf(verify(json = payload(extra = mapOf("payload_version" to 99)),
                            key = privateKey, pem = pem)),
        )
    }

    @Test
    fun `a bootstrap token too short to be one is refused`() {
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_bootstrap_token_too_short",
            reasonOf(verify(json = payload(extra = mapOf("bootstrap_token" to "short")),
                            key = privateKey, pem = pem)),
        )
    }

    @Test
    fun `a payload with no pairing token is refused`() {
        // §0D.3 needs both credentials. One that bound the hardware but never paired
        // would leave a device with an identity and no way to speak; one that paired
        // without binding would leave working tokens on a phone that is not the owner's,
        // which is the failure the whole section exists to prevent.
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_pairing_token_too_short",
            reasonOf(verify(json = payload(remove = setOf("pairing_token")),
                            key = privateKey, pem = pem)),
        )
    }

    @Test
    fun `both single-use tokens survive verification and neither is loggable`() {
        val (privateKey, pem) = keys()
        val accepted = verify(key = privateKey, pem = pem) as ProvisioningVerdict.Accepted
        assertEquals(token, accepted.payload.pairingToken)
        assertEquals(token, accepted.payload.bootstrapToken)
        assertTrue(token !in accepted.payload.loggableFields.toString())
    }

    @Test
    fun `a payload with no attestation challenge is refused`() {
        // §0D.3's binding is what makes a leaked payload useless. A payload with no
        // challenge would authorise an enrolment nothing is attested against.
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_challenge_missing",
            reasonOf(verify(json = payload(extra = mapOf("attestation_challenge" to "  ")),
                            key = privateKey, pem = pem)),
        )
    }

    @Test
    fun `what may be logged excludes the token and the challenge`() {
        val (privateKey, pem) = keys()
        val accepted = verify(key = privateKey, pem = pem) as ProvisioningVerdict.Accepted
        val logged = accepted.payload.loggableFields.toString()
        assertTrue(token !in logged, logged)
        assertTrue("chal-1" !in logged, logged)
        // And the thing an owner actually needs to see is present.
        assertTrue("https://van.example" in logged, logged)
    }

    @Test
    fun `the replay check runs before the signature so a replay costs nothing`() {
        // A replay of our own payload verifies. If the order were reversed the device
        // would do the elliptic-curve work first and reach the same answer, which is only
        // wasted effort — but it would also report the reason as a signature problem if
        // the payload had been re-signed, which sends an installer to the wrong place.
        val (privateKey, pem) = keys()
        assertEquals(
            "provisioning_already_used",
            reasonOf(verify(
                json = payload(extra = mapOf("gateway_url" to "https://van.example")),
                key = privateKey, pem = pem, signature = "00".repeat(64),
                alreadyAccepted = setOf("prov_abc123"),
            )),
        )
    }
}

/**
 * The build-time trust anchor, and the format both readers have to agree on.
 *
 * This class exists because they did not. `ProvisioningIntake` was written with its own
 * parser that read the `kid=PEM` string as JSON; it found nothing, reported the build as
 * having no anchor, and provisioning would have been impossible on a correctly configured
 * release APK. The only symptom would have been a phone sitting on "waiting for the
 * installer" forever, with every test green.
 */
class ConnectivityTrustedKeysTest {

    private val pem = "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----"

    @Test
    fun `a kid and a PEM on one line is one trusted key`() {
        val parsed = ConnectivityTrustedKeys.parse("prov-1=$pem")
        assertEquals(setOf("prov-1"), parsed.keys)
        assertTrue(parsed.getValue("prov-1").contains("BEGIN PUBLIC KEY"))
    }

    @Test
    fun `escaped newlines inside a PEM are restored`() {
        // The value arrives through a Gradle BuildConfig string, where a real newline
        // cannot survive. A parser that did not restore them would hold a PEM that no
        // KeyFactory accepts, and every signature would be "invalid" for the wrong reason.
        val escaped = "prov-1=-----BEGIN PUBLIC KEY-----\\nAAAA\\n-----END PUBLIC KEY-----"
        assertTrue(ConnectivityTrustedKeys.parse(escaped).getValue("prov-1").contains("\n"))
    }

    @Test
    fun `an empty configuration is no keys rather than an error`() {
        // A build given no anchor applies nothing and says so. Throwing here would make a
        // misconfigured build unable to start, which is a worse failure than a refusal.
        assertTrue(ConnectivityTrustedKeys.parse("").isEmpty())
        assertTrue(ConnectivityTrustedKeys.parse("   ").isEmpty())
    }

    @Test
    fun `a malformed line is dropped and the rest survive`() {
        val parsed = ConnectivityTrustedKeys.parse("nonsense\nprov-1=$pem\n=$pem\nprov-2=notapem")
        assertEquals(setOf("prov-1"), parsed.keys)
    }

    @Test
    fun `a value that is not a public key is not a trusted key`() {
        // The check that stops a truncated build argument becoming an anchor nobody can
        // use and nobody notices.
        assertTrue(ConnectivityTrustedKeys.parse("prov-1=hunter2").isEmpty())
    }
}
