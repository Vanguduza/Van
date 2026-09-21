package com.dial.van.provisioning

import android.app.Activity
import android.os.Bundle
import android.util.Base64
import android.util.Log
import com.dial.van.VanApplication
import com.dial.van.connectivity.ProvisioningVerdict
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Rev 1.5 ADR-RB-026 — where the installer's payload enters the app.
 *
 * Started by the deployment pipeline over ADB, not by the owner and not from a launcher:
 *
 * ```
 * adb shell am start -n com.dial.van/.provisioning.ProvisioningActivity \
 *     --es van_provisioning <base64 of {"payload":…,"signature":…,"kid":…}>
 * ```
 *
 * **Why an exported activity is acceptable here, stated because it usually is not.** This
 * component can be started by anything on the device. That buys an attacker nothing,
 * because the entry point holds no authority: the payload must be signed by a key compiled
 * into this build, must not have expired, must not have been used, and still only earns a
 * pair of single-use tokens whose value depends on a hardware attestation the caller
 * cannot produce (§0D.3). The signature is the guard. Exportedness is the channel.
 *
 * Deliberately thin. Everything decided here — and every way a payload is refused — lives
 * in `ProvisioningVerifier`, which is pure and runs in `android/verification`, because the
 * cases that matter (an expired payload, a replay, a payload signed by a key this build
 * does not pin) cannot be staged on a real installation run.
 *
 * It finishes immediately. There is no screen: the owner is not part of this, which is
 * §0D.2's whole point.
 */
class ProvisioningActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        val encoded = intent?.getStringExtra(EXTRA) ?: run {
            finishWith("provisioning_no_payload")
            return
        }
        val envelope = runCatching {
            JSONObject(String(Base64.decode(encoded, Base64.DEFAULT), Charsets.UTF_8))
        }.getOrNull() ?: run {
            finishWith("provisioning_malformed")
            return
        }

        when (val verdict = app.provisioning.verify(envelope)) {
            is ProvisioningVerdict.Refused -> finishWith(verdict.reason)
            is ProvisioningVerdict.Accepted -> {
                // Launched on the application scope rather than this activity's: the
                // activity finishes at once, and a provisioning run cancelled halfway
                // would leave a device paired and unbound — the §0D.3 state where working
                // tokens sit on a phone with no hardware identity.
                app.appScope.launch(Dispatchers.IO) {
                    val result = runCatching {
                        app.gatewayClient.provisionThisDevice(verdict.payload)
                    }
                    if (result.isSuccess) {
                        // Recorded only now. Marking it used before the network step
                        // would make a payload that failed to reach the Gateway
                        // permanently unusable on a phone that never enrolled.
                        app.provisioning.consume(verdict.payload.provisioningId)
                        Log.i(TAG, "provisioned ${verdict.payload.loggableFields}")
                    } else {
                        Log.w(TAG, "provisioning_failed: ${result.exceptionOrNull()?.message}")
                    }
                }
                finishWith("accepted")
            }
        }
    }

    /**
     * The installer reads this from the log, which is why it is a reason and not a boolean.
     *
     * Safe to log: every value is a refusal name from `ProvisioningVerifier`, and the
     * payload's own loggable fields exclude both tokens and the attestation challenge.
     */
    private fun finishWith(reason: String) {
        Log.i(TAG, "provisioning: $reason")
        finish()
    }

    companion object {
        const val EXTRA = "van_provisioning"
        private const val TAG = "VanProvisioning"
    }
}
