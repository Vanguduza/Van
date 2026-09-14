package com.dial.van.security

import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

/**
 * Biometric gate for A4 (destructive / send-as-owner) approvals.
 */
class BiometricGate(private val activity: FragmentActivity) {

    fun canAuthenticate(): Boolean {
        val manager = BiometricManager.from(activity)
        return manager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
            BiometricManager.BIOMETRIC_SUCCESS
    }

    fun requestA4Approval(
        title: String = "Approve sensitive action",
        subtitle: String = "Owner biometric required for A4 class actions",
        onApproved: () -> Unit,
        onDenied: (String) -> Unit,
    ) {
        if (!canAuthenticate()) {
            onDenied("Biometric hardware unavailable")
            return
        }

        val executor = ContextCompat.getMainExecutor(activity)
        val prompt = BiometricPrompt(
            activity,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    onApproved()
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    onDenied(errString.toString())
                }

                override fun onAuthenticationFailed() {
                    onDenied("Authentication failed")
                }
            },
        )

        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
            .setNegativeButtonText("Cancel")
            .build()

        prompt.authenticate(info)
    }
}
