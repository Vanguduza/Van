package com.dial.van.connectivity

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dial.van.BuildConfig
import org.json.JSONObject

/**
 * Rev 1.5 ADR-RB-026 — the installer's payload arriving on the device.
 *
 * This is the Android half: the storage of which provisioning ids have been used, the
 * trust anchor, and the single-use record. Every decision it makes belongs to
 * [ProvisioningVerifier], which is pure and is executed in `android/verification`, because
 * the interesting cases — an expired payload, a replay, a payload signed by a key this
 * build does not pin — are not things anyone can stage on a real installation run.
 *
 * The accepted-id record is the second of the three properties that make the ADB channel
 * survivable, and it is kept *here* rather than only at the Gateway on purpose. The
 * Gateway consumes the bootstrap token atomically and would refuse a replay anyway; what
 * this adds is that a replay never leaves the phone, so the device can say
 * `provisioning_already_used` rather than reporting whatever the server said.
 */
class ProvisioningIntake(context: Context) {

    private val prefs = EncryptedSharedPreferences.create(
        context.applicationContext,
        "van_provisioning",
        MasterKey.Builder(context.applicationContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    private val trustedKeys: Map<String, String> by lazy { parseTrustedKeys() }

    /** Whether this build was given a trust anchor at all. Without one, nothing provisions. */
    val configured: Boolean get() = trustedKeys.isNotEmpty()

    fun accepted(): Set<String> = prefs.getStringSet(KEY_ACCEPTED, emptySet()) ?: emptySet()

    /** Installer handoff survives Activity/process death, encrypted with the other intake state. */
    @Synchronized
    fun stage(envelope: JSONObject): ProvisioningVerdict {
        val verdict = verify(envelope)
        if (verdict is ProvisioningVerdict.Accepted) {
            val previous = pending()
            if (previous != null && ProvisioningRecovery.fingerprint(previous) !=
                ProvisioningRecovery.fingerprint(verdict.payload)) {
                return ProvisioningVerdict.Refused("provisioning_pending_identity_mismatch")
            }
            check(prefs.edit().putString(KEY_PENDING, envelope.toString()).commit()) { "provisioning_pending_store_failed" }
        }
        return verdict
    }

    @Synchronized
    fun pending(nowMs: Long = System.currentTimeMillis()): ProvisioningPayload? {
        val raw = prefs.getString(KEY_PENDING, null) ?: return null
        val envelope = runCatching { JSONObject(raw) }.getOrNull()
        val verdict = envelope?.let { verify(it, nowMs) }
        if (verdict is ProvisioningVerdict.Accepted) return verdict.payload
        check(prefs.edit().remove(KEY_PENDING).commit()) { "provisioning_pending_clear_failed" }
        return null
    }

    /**
     * Verify one payload without consuming it.
     *
     * Separate from [consume] so a caller can report a refusal without recording an
     * acceptance — the first version of this did both in one call, and a payload that
     * failed at the network step afterwards was then permanently unusable on a phone that
     * had never actually enrolled.
     */
    fun verify(envelope: JSONObject, nowMs: Long = System.currentTimeMillis()): ProvisioningVerdict {
        val payload = envelope.optJSONObject("payload")
            ?: return ProvisioningVerdict.Refused("provisioning_malformed")
        return ProvisioningVerifier.verify(
            payloadJson = payload.toString(),
            signatureHex = envelope.optString("signature", ""),
            kid = envelope.optString("kid", ""),
            trustedKeys = trustedKeys,
            nowMs = nowMs,
            alreadyAccepted = accepted(),
            // §0D.2 makes no exception for a release build; a debug build talks to a
            // loopback gateway and cannot use HTTPS to reach it.
            allowInsecureLoopback = BuildConfig.DEBUG,
        )
    }

    /** Record that this payload was used. Called only after enrolment actually succeeded. */
    fun consume(provisioningId: String) {
        check(prefs.edit().putStringSet(KEY_ACCEPTED, accepted() + provisioningId)
            .remove(KEY_PENDING).commit()) { "provisioning_consumption_store_failed" }
    }

    /**
     * The same compiled-in anchor the connectivity manifest uses, through the same parser.
     *
     * One anchor because two would be two things that can be wrong, and one parser because
     * this file's first version wrote its own — it read the `kid=PEM` string as JSON,
     * found nothing, and would have reported a correctly configured release build as
     * unable to provision. The only symptom would have been a phone that sat waiting.
     */
    private fun parseTrustedKeys(): Map<String, String> =
        ConnectivityTrustedKeys.parse(BuildConfig.VAN_CONNECTIVITY_TRUSTED_KEYS)

    private companion object {
        const val KEY_ACCEPTED = "accepted_provisioning_ids"
        const val KEY_PENDING = "pending_signed_envelope"
    }
}
