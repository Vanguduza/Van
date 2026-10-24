package com.dial.van.connectivity

import com.dial.van.security.VanCanonicalJson
import kotlinx.coroutines.CancellationException
import org.json.JSONObject

/** Resumes only the exact signed provisioning attempt that earned this phone its credentials. */
object ProvisioningRecovery {
    data class PreparedPairing(val payloadFingerprint: String, val deviceId: String, val accessToken: String)

    /** Preparation must commit before any network side effect; retries reuse that exact identity. */
    suspend fun completePrebound(
        payload: ProvisioningPayload,
        prepare: () -> PreparedPairing,
        recoverBinding: suspend () -> JSONObject?,
        bind: suspend () -> JSONObject,
        pair: suspend () -> JSONObject,
        nowMs: Long = System.currentTimeMillis(),
    ): JSONObject {
        require(nowMs < payload.expiresAtMs) { "provisioning_payload_expired" }
        val prepared = prepare()
        require(prepared.payloadFingerprint == fingerprint(payload) && prepared.deviceId.isNotBlank() &&
            prepared.accessToken.length >= 32) { "provisioning_pending_identity_mismatch" }
        val binding = recoverBinding() ?: bind()
        val receipt = pair()
        require(receipt.optString("device_id") == prepared.deviceId &&
            receipt.optString("device_access_token") == prepared.accessToken &&
            receipt.optString("ingress_token").length >= 32) { "provisioning_pairing_receipt_mismatch" }
        return binding
    }
    data class Pairing(
        val payloadFingerprint: String?, val gatewayUrl: String, val deviceId: String,
        val paired: Boolean, val provisionedDeviceId: String? = deviceId,
    )

    fun fingerprint(payload: ProvisioningPayload): String = VanCanonicalJson.sha256Hex(
        JSONObject()
            .put("provisioning_id", payload.provisioningId).put("gateway_url", payload.gatewayUrl)
            .put("pairing_token", payload.pairingToken).put("bootstrap_token", payload.bootstrapToken)
            .put("attestation_challenge", payload.attestationChallenge)
            .put("expected_manifest_version", payload.expectedManifestVersion)
            .put("issued_at_ms", payload.issuedAtMs).put("expires_at_ms", payload.expiresAtMs),
    )

    suspend fun complete(
        payload: ProvisioningPayload,
        pairing: () -> Pairing,
        pair: suspend () -> Unit,
        bindingStatus: suspend () -> JSONObject,
        localKeyFingerprint: () -> String?,
        bind: suspend (mayReplaceUnboundKey: Boolean) -> JSONObject,
        nowMs: Long = System.currentTimeMillis(),
    ): JSONObject {
        require(nowMs < payload.expiresAtMs) { "provisioning_payload_expired" }
        val expected = fingerprint(payload)
        fun matches(saved: Pairing) = saved.paired && saved.deviceId.isNotBlank() &&
            saved.deviceId == saved.provisionedDeviceId &&
            saved.gatewayUrl == payload.gatewayUrl.trim().trimEnd('/') && saved.payloadFingerprint == expected
        val saved = pairing()
        if (saved.paired) {
            require(matches(saved)) { "provisioning_existing_identity_mismatch" }
        } else {
            pair()
            require(matches(pairing())) { "provisioning_pairing_state_incomplete" }
        }
        val status = try {
            bindingStatus()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // On the direct link an unbound device cannot yet obtain its TLS certificate.
            // An unavailable status never authorises replacing a key that might be bound.
            null
        }
        if (status?.optBoolean("bound", false) == true) {
            val local = localKeyFingerprint()
            require(!local.isNullOrBlank() && status.optString("device_key_fingerprint") == local) {
                "provisioning_bound_key_mismatch"
            }
            return status
        }
        return bind(status?.optBoolean("configured", false) == true && status.has("bound") &&
            !status.optBoolean("bound", true))
    }
}
