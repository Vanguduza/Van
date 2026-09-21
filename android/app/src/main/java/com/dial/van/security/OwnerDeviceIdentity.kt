package com.dial.van.security

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.Signature
import java.security.cert.X509Certificate
import java.security.spec.ECGenParameterSpec

/**
 * Rev 1.5 §0D.3 / ADR-RB-025 — what makes this phone *the owner's phone*.
 *
 * §0D.3 names the wrong implementation outright: a `Build.MODEL` check, which passes on any
 * other S24 Ultra, and on an emulator that says it is one. The right one is a key pair whose
 * private half is generated inside the secure element and cannot be exported, plus the
 * attestation certificate that says so — and then a signature over every privileged request,
 * so a copied access token on another device buys nothing.
 *
 * Three things here are deliberate and each has a failure they prevent:
 *
 *  * **StrongBox first, TEE second, and the difference is reported.** A phone without a
 *    secure element still enrols, but the gateway records `TRUSTED_ENVIRONMENT` rather than
 *    `STRONGBOX` and the owner can see which they have. Silently accepting the weaker one
 *    and calling both "hardware-backed" is how a binding stops meaning anything.
 *  * **No user authentication on this key.** VAN heartbeats a browser session while the
 *    screen is off; a proof key gated on biometrics would make the session die whenever the
 *    owner put the phone down. Owner *approval* is a different key — `OwnerApprovalKeyManager`
 *    — and that one is gated, because an approval is a decision and a proof is an identity.
 *  * **The key is never regenerated silently.** `ensureKey` returns the existing key if there
 *    is one. Regenerating would look like recovery and would actually be this device
 *    quietly becoming a different device, which the gateway would refuse anyway — after the
 *    owner had lost their binding.
 *
 * None of this can be executed in the repository's harnesses: Keystore, StrongBox and
 * attestation are device facts. The pure parts — the signing input and the DER walk over
 * the attestation extension — live in [DeviceProofCanonical] and in the gateway's own
 * parser, and both are tested. Whether a real S24 emits a chain the gateway accepts is a
 * device gate (RB-120) and is recorded as one.
 */
class OwnerDeviceIdentity {

    data class KeyMaterial(
        val publicKeyPem: String,
        /** The Google attestation extension, base64, exactly as the gateway parses it. */
        val attestationExtensionBase64: String,
        /** SHA-256 of the chain's root, for the gateway to pin once it has seen it. */
        val attestationRootFingerprint: String,
        /** True when the private half lives in a discrete secure element. */
        val strongBoxBacked: Boolean,
    )

    class IdentityUnavailable(val reason: String, cause: Throwable? = null) :
        Exception(reason, cause)

    private val keyStore: KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    fun isEnrolled(): Boolean = keyStore.containsAlias(ALIAS)

    /**
     * The key for this device, generating it against [challenge] if it does not exist.
     *
     * @param challenge the attestation challenge the gateway issued for this enrolment. It
     *   is baked into the certificate, which is what stops a chain captured from one
     *   enrolment being replayed into another.
     */
    fun ensureKey(challenge: ByteArray): KeyMaterial {
        if (!keyStore.containsAlias(ALIAS)) {
            generate(challenge, strongBox = true)
        }
        return describe()
    }

    /**
     * Discard this device's identity. Only for a rebind the owner asked for: the gateway
     * issues a fresh bootstrap token, and without deleting the old key the new enrolment
     * would attest a key the gateway has already seen bound to the revoked binding.
     */
    fun forget() {
        if (keyStore.containsAlias(ALIAS)) keyStore.deleteEntry(ALIAS)
    }

    private fun generate(challenge: ByteArray, strongBox: Boolean) {
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setAttestationChallenge(challenge)
            // Deliberately absent: setUserAuthenticationRequired(true). See the class note.
            .apply {
                if (strongBox && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    setIsStrongBoxBacked(true)
                }
            }
            .build()
        val generator = KeyPairGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE,
        )
        try {
            generator.initialize(spec)
            generator.generateKeyPair()
        } catch (unavailable: StrongBoxUnavailableException) {
            if (!strongBox) throw IdentityUnavailable("device_key_generation_failed", unavailable)
            // Reported rather than hidden: `describe()` reads the security level back out of
            // the attestation, so the gateway is told TEE and records TEE.
            generate(challenge, strongBox = false)
        }
    }

    private fun describe(): KeyMaterial {
        val chain = keyStore.getCertificateChain(ALIAS)
            ?: throw IdentityUnavailable("device_key_has_no_attestation")
        if (chain.isEmpty()) throw IdentityUnavailable("device_key_has_no_attestation")
        val leaf = chain.first() as X509Certificate
        val extension = leaf.getExtensionValue(ATTESTATION_OID)
            ?: throw IdentityUnavailable("device_key_not_attested")
        val root = chain.last() as X509Certificate

        return KeyMaterial(
            publicKeyPem = pem(leaf.publicKey.encoded),
            // getExtensionValue returns the extension wrapped in an OCTET STRING; the
            // gateway parses the SEQUENCE inside it, so the wrapper comes off here rather
            // than being a special case in a parser that also reads bare extensions.
            attestationExtensionBase64 = Base64.encodeToString(
                unwrapOctetString(extension), Base64.NO_WRAP,
            ),
            attestationRootFingerprint = sha256Hex(root.encoded),
            strongBoxBacked = hasStrongBoxLevel(leaf),
        )
    }

    /**
     * The security level byte in the attestation, read from the certificate rather than
     * from whether `setIsStrongBoxBacked` threw.
     *
     * Those are different questions: generation can succeed on a device that quietly
     * downgrades, and the certificate is the only account of where the key actually lives.
     */
    private fun hasStrongBoxLevel(leaf: X509Certificate): Boolean {
        val bytes = unwrapOctetString(leaf.getExtensionValue(ATTESTATION_OID) ?: return false)
        // attestationSecurityLevel is the second field of the top-level SEQUENCE and is an
        // ENUMERATED: 0 software, 1 trusted environment, 2 StrongBox.
        var index = 0
        if (bytes.getOrNull(index)?.toInt()?.and(0xFF) != 0x30) return false
        index = skipHeader(bytes, index) ?: return false
        index = skipValue(bytes, index) ?: return false // attestationVersion
        if (index + 2 >= bytes.size) return false
        val length = bytes[index + 1].toInt() and 0xFF
        if (length != 1) return false
        return (bytes[index + 2].toInt() and 0xFF) == 2
    }

    private fun skipHeader(bytes: ByteArray, at: Int): Int? {
        if (at + 1 >= bytes.size) return null
        val first = bytes[at + 1].toInt() and 0xFF
        return if (first < 0x80) at + 2 else at + 2 + (first and 0x7F)
    }

    private fun skipValue(bytes: ByteArray, at: Int): Int? {
        if (at + 1 >= bytes.size) return null
        val first = bytes[at + 1].toInt() and 0xFF
        return if (first < 0x80) {
            at + 2 + first
        } else {
            val count = first and 0x7F
            if (at + 2 + count > bytes.size) return null
            var length = 0
            for (offset in 0 until count) length = (length shl 8) or (bytes[at + 2 + offset].toInt() and 0xFF)
            at + 2 + count + length
        }
    }

    private fun unwrapOctetString(der: ByteArray): ByteArray {
        if (der.isEmpty() || (der[0].toInt() and 0xFF) != 0x04) return der
        val first = der[1].toInt() and 0xFF
        val start = if (first < 0x80) 2 else 2 + (first and 0x7F)
        return der.copyOfRange(start, der.size)
    }

    private fun pem(encoded: ByteArray): String {
        val body = Base64.encodeToString(encoded, Base64.NO_WRAP).chunked(64).joinToString("\n")
        return "-----BEGIN PUBLIC KEY-----\n$body\n-----END PUBLIC KEY-----"
    }

    private fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /** A signing handle for [DeviceProofSigner]. Never leaves this class as key material. */
    internal fun privateKey(): PrivateKey =
        (keyStore.getKey(ALIAS, null) as? PrivateKey)
            ?: throw IdentityUnavailable("device_key_missing")

    companion object {
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "van_owner_device_identity_v1"
        private const val ATTESTATION_OID = "1.3.6.1.4.1.11129.2.1.17"
    }
}

/**
 * ADR-RB-025 — the two headers every privileged owner request carries.
 *
 * The signature covers the method, the path, the device id, the moment and the digest of
 * the body. Leaving any one of those out would let a captured proof be reused: without the
 * path, a heartbeat's proof would authorise a session close; without the body digest, a
 * request to take control would authorise one to hand it to an agent.
 */
class DeviceProofSigner(private val identity: OwnerDeviceIdentity) {

    fun headers(
        method: String,
        path: String,
        deviceId: String,
        body: ByteArray,
        nowMs: Long = System.currentTimeMillis(),
    ): Map<String, String> {
        val signingInput = DeviceProofCanonical.signingInput(
            method = method,
            path = path,
            deviceId = deviceId,
            issuedAtMs = nowMs,
            bodySha256 = DeviceProofCanonical.sha256Hex(body),
        )
        val der = Signature.getInstance("SHA256withECDSA").run {
            initSign(identity.privateKey())
            update(signingInput)
            sign()
        }
        return mapOf(
            "X-Van-Device-Proof" to Base64.encodeToString(
                DeviceProofCanonical.derToP1363(der), Base64.NO_WRAP,
            ),
            "X-Van-Device-Proof-Issued-At" to nowMs.toString(),
        )
    }
}
