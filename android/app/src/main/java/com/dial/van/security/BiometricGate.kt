package com.dial.van.security

import android.util.Base64
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import java.nio.charset.StandardCharsets
import java.security.Signature

/**
 * Biometric gate for A4 (destructive / send-as-owner) approvals.
 */
class BiometricGate(private val activity: FragmentActivity) {

    fun canAuthenticate(): Boolean {
        val manager = BiometricManager.from(activity)
        return manager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
            BiometricManager.BIOMETRIC_SUCCESS
    }

    /*
     * `requestA4Approval` used to live here: a BiometricPrompt with no CryptoObject, whose
     * only output was that the prompt had succeeded. Trading account and credential
     * changes used it while owner commands used the strong path below, so the weakest
     * gate in the app guarded the surface that issues broker signing keys (P1-SEC-004).
     *
     * It is deleted rather than deprecated. A prompt that returns a boolean produces
     * nothing the gateway can check, so there is no correct caller for it, and leaving it
     * available would make the next such surface a one-line mistake. Everything that
     * needs owner approval now takes a gateway-issued challenge through
     * requestA4CommandApproval and sends back a signature the gateway verifies.
     */

    /**
     * Authenticate the owner and sign the exact gateway-issued A4 challenge.
     * The supplied Signature is initialized with a per-use-auth Android Keystore
     * private key, so successful prompt UI alone is not accepted as authority.
     */
    fun requestA4CommandApproval(
        signature: Signature,
        challenge: String,
        title: String = "Approve VAN action",
        subtitle: String = "Confirm this destructive or send-as-owner action",
        onApproved: (signatureBase64: String) -> Unit,
        onDenied: (String) -> Unit,
    ) {
        if (!canAuthenticate()) {
            onDenied("Biometric hardware unavailable")
            return
        }
        if (challenge.isBlank()) {
            onDenied("Approval challenge missing")
            return
        }

        val executor = ContextCompat.getMainExecutor(activity)
        val prompt = BiometricPrompt(
            activity,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    try {
                        val authenticated = result.cryptoObject?.signature
                            ?: throw IllegalStateException("Biometric crypto signature unavailable")
                        authenticated.update(challenge.toByteArray(StandardCharsets.UTF_8))
                        val signed = authenticated.sign()
                        onApproved(Base64.encodeToString(signed, Base64.NO_WRAP))
                    } catch (t: Throwable) {
                        onDenied(t.message ?: "Approval signing failed")
                    }
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    onDenied(errString.toString())
                }

                override fun onAuthenticationFailed() {
                    onDenied("Authentication failed")
                }
            },
        )

        prompt.authenticate(
            promptInfo(title, subtitle),
            BiometricPrompt.CryptoObject(signature),
        )
    }

    private fun promptInfo(title: String, subtitle: String): BiometricPrompt.PromptInfo =
        BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
            .setNegativeButtonText("Cancel")
            .build()
}
