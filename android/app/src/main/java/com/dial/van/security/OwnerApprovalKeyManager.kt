package com.dial.van.security

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * Device-bound owner-approval key for A4 commands.
 *
 * The private key never leaves Android Keystore. Every signature requires a
 * fresh BIOMETRIC_STRONG authentication. The public key is enrolled with the
 * VAN gateway during the secure pairing ceremony and is used only to verify
 * one-time owner approval challenges.
 */
class OwnerApprovalKeyManager {

    private val keyStore: KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    fun ensureKey(): Unit {
        if (keyStore.containsAlias(KEY_ALIAS)) return

        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
        val builder = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_SIGN,
        )
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(true)
            .setInvalidatedByBiometricEnrollment(true)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            builder.setUserAuthenticationParameters(
                0,
                KeyProperties.AUTH_BIOMETRIC_STRONG,
            )
        } else {
            @Suppress("DEPRECATION")
            builder.setUserAuthenticationValidityDurationSeconds(-1)
        }

        generator.initialize(builder.build())
        generator.generateKeyPair()
    }

    fun publicKeyPem(): String {
        ensureKey()
        val certificate = keyStore.getCertificate(KEY_ALIAS)
            ?: error("owner_approval_certificate_missing")
        val encoded = Base64.encodeToString(certificate.publicKey.encoded, Base64.NO_WRAP)
        val body = encoded.chunked(64).joinToString("\n")
        return "-----BEGIN PUBLIC KEY-----\n$body\n-----END PUBLIC KEY-----\n"
    }

    fun ownerAuthorityKeyId(): String {
        ensureKey()
        val certificate = keyStore.getCertificate(KEY_ALIAS)
            ?: error("owner_approval_certificate_missing")
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(certificate.publicKey.encoded)
            .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
        return "device-" + digest.take(24)
    }

    fun prepareOwnerAuthority(
        act: String,
        subject: String,
        issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
        lifetimeSeconds: Long = OwnerAuthorityToken.DEFAULT_LIFETIME_SECONDS,
    ): OwnerAuthorityToken.Prepared = OwnerAuthorityToken.prepare(
        act = act,
        subject = subject,
        keyId = ownerAuthorityKeyId(),
        issuedAtUnix = issuedAtUnix,
        lifetimeSeconds = lifetimeSeconds,
    )

    fun newSigningSignature(): Signature {
        ensureKey()
        val privateKey = keyStore.getKey(KEY_ALIAS, null) as? PrivateKey
            ?: error("owner_approval_private_key_missing")
        return Signature.getInstance(SIGNATURE_ALGORITHM).apply {
            initSign(privateKey)
        }
    }

    fun reset() {
        if (keyStore.containsAlias(KEY_ALIAS)) {
            keyStore.deleteEntry(KEY_ALIAS)
        }
    }

    companion object {
        const val KEY_ALIAS = "van_owner_approval_v1"
        const val SIGNATURE_ALGORITHM = "SHA256withECDSA"
        const val PROOF_ALGORITHM = "ECDSA_P256_SHA256"
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    }
}
