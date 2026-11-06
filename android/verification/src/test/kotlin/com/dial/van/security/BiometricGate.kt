package com.dial.van.security

import androidx.fragment.app.FragmentActivity
import java.security.Signature

/** Tests controller behavior after the Android biometric boundary, never real authentication. */
class BiometricGate(activity: FragmentActivity) {
    fun requestA4CommandApproval(
        signature: Signature,
        challenge: String,
        onApproved: (String) -> Unit,
        onDenied: (String) -> Unit,
    ) { onApproved("test-only-biometric-signature") }
}
