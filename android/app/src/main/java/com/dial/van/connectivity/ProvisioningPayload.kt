package com.dial.van.connectivity

import org.json.JSONObject

/**
 * Rev 1.5 ADR-RB-026 and §0D.2 — what the installer hands this phone, and why it is the
 * only way in.
 *
 * §0D.2 forbids the production build from exposing an editable Gateway URL or a pairing
 * token, and the reason is not tidiness. A field that asks the owner for a server address
 * is a phishing surface with their entire assistant behind it: anyone who persuades them to
 * retype an address owns every command from that moment, and nothing on the phone would
 * look wrong. The same is true of a pairing code, which is exactly the kind of string
 * somebody can be talked into reading out.
 *
 * So the first installation is provisioned by the deployment pipeline. It hands the device
 * one signed document, verified against the same pinned connectivity authority key this
 * build already trusts for manifests, and the owner types nothing.
 *
 * Three properties carry the weight, and the delivery channel is why. The installer sends
 * this over ADB, so it goes through a shell and can end up in a device log. That is
 * survivable only because a payload that leaks is already useless:
 *
 *  * **it expires in minutes** — [expiresAtMs], checked here;
 *  * **it is single-use** — the Gateway consumes the bootstrap token atomically, and this
 *    device also refuses a `provisioning_id` it has already accepted, so a replay on the
 *    same phone does not even reach the network;
 *  * **it is not sufficient on its own** — enrolment must be attested by a hardware-backed
 *    Keystore key that whoever read the log does not have (§0D.3).
 *
 * Remove any one of the three and the channel stops being acceptable. That is the reason
 * none of them is a configuration option.
 *
 * Pure: no Android imports, so every refusal below is executed in `android/verification`
 * rather than reasoned about.
 */
data class ProvisioningPayload(
    val provisioningId: String,
    val gatewayUrl: String,
    /** Earns this device its ingress and access tokens (`POST /v1/devices/pair`). */
    val pairingToken: String,
    /** Authorises the hardware-attested binding that makes those tokens device-specific. */
    val bootstrapToken: String,
    val attestationChallenge: String,
    val expectedManifestVersion: Int,
    val issuedAtMs: Long,
    val expiresAtMs: Long,
) {
    /**
     * What may be written to a log or shown on a diagnostics screen.
     *
     * The token and the challenge are deliberately absent, and the gateway URL is present:
     * knowing where this phone was pointed is what an owner needs to see, and it is not a
     * secret — it is in the signed manifest already.
     */
    val loggableFields: Map<String, Any>
        get() = mapOf(
            "provisioning_id" to provisioningId,
            "gateway_url" to gatewayUrl,
            "expected_manifest_version" to expectedManifestVersion,
            "expires_at_ms" to expiresAtMs,
        )
}

sealed class ProvisioningVerdict {
    data class Accepted(val payload: ProvisioningPayload) : ProvisioningVerdict()

    /** Refusals carry a reason, because "provisioning failed" tells an installer nothing. */
    data class Refused(val reason: String) : ProvisioningVerdict()
}

object ProvisioningVerifier {

    /** Bumped when the fields change. An unknown version is refused, never parsed as this one. */
    const val PAYLOAD_VERSION: Int = 1

    /**
     * Fields that would make this a standing credential rather than a way to earn one.
     *
     * The bootstrap and pairing tokens are not here: carrying them is the payload's job,
     * and both are single-use and consumed atomically by the Gateway. `pairing_token` is
     * forbidden in a *manifest* and permitted here, which is not inconsistency: a manifest
     * is long-lived configuration the device caches and re-reads, so a token in one is a
     * credential sitting in a file. This envelope exists for minutes.
     *
     * What must never be here is anything that outlives enrolment. An ingress token
     * delivered this way would be a permanent credential sent over a channel that logs,
     * and no expiry on the envelope repairs that — the secret would still be valid
     * tomorrow.
     */
    val FORBIDDEN_FIELDS: Set<String> = setOf(
        "ingress_token", "device_access_token", "device_secret", "internal_control_token",
        "hermes_token", "access_token", "refresh_token", "client_secret", "private_key",
    )

    /** The shortest either single-use token may be. Mirrors the Gateway's own floor. */
    const val MIN_TOKEN_CHARS: Int = 32

    /**
     * Verify one payload.
     *
     * @param trustedKeys the pinned authority keys compiled into this build, by `kid`.
     * @param alreadyAccepted provisioning ids this device has already consumed.
     * @param allowInsecureLoopback true only for a debug build. A release build passes
     *   false, and the separation is here rather than at the Gateway because the Gateway
     *   cannot tell which build it is signing for — one that relaxed the rule would sign a
     *   payload a release device must refuse, and the installer would appear to succeed.
     */
    fun verify(
        payloadJson: String,
        signatureHex: String,
        kid: String,
        trustedKeys: Map<String, String>,
        nowMs: Long,
        alreadyAccepted: Set<String> = emptySet(),
        allowInsecureLoopback: Boolean = false,
    ): ProvisioningVerdict {
        val publicKeyPem = trustedKeys[kid]
            ?: return ProvisioningVerdict.Refused("provisioning_unknown_kid")

        val parsed = runCatching { JSONObject(payloadJson) }.getOrNull()
            ?: return ProvisioningVerdict.Refused("provisioning_malformed")

        if (parsed.optInt("payload_version", 0) != PAYLOAD_VERSION) {
            return ProvisioningVerdict.Refused("provisioning_payload_version_unsupported")
        }
        val leaked = FORBIDDEN_FIELDS.firstOrNull { parsed.has(it) }
        if (leaked != null) {
            return ProvisioningVerdict.Refused("provisioning_carries_standing_credential:$leaked")
        }

        val provisioningId = parsed.optString("provisioning_id", "")
        if (provisioningId.isBlank()) {
            return ProvisioningVerdict.Refused("provisioning_unidentified")
        }
        if (provisioningId in alreadyAccepted) {
            // Checked before the signature, because a replay of *our own* accepted payload
            // has a perfect signature. The Gateway would refuse the consumed token anyway;
            // refusing here means a replay never reaches the network, and means this
            // device can say what happened rather than reporting a server error.
            return ProvisioningVerdict.Refused("provisioning_already_used")
        }

        val expiresAtMs = parsed.optLong("expires_at_ms", 0L)
        if (expiresAtMs <= 0L) {
            return ProvisioningVerdict.Refused("provisioning_payload_has_no_expiry")
        }
        if (nowMs >= expiresAtMs) {
            return ProvisioningVerdict.Refused("provisioning_payload_expired")
        }

        val gatewayUrl = parsed.optString("gateway_url", "").trim().trimEnd('/')
        if (!isAcceptableUrl(gatewayUrl, allowInsecureLoopback)) {
            return ProvisioningVerdict.Refused("provisioning_url_must_use_https")
        }

        val pairingToken = parsed.optString("pairing_token", "").trim()
        if (pairingToken.length < MIN_TOKEN_CHARS) {
            return ProvisioningVerdict.Refused("provisioning_pairing_token_too_short")
        }
        val bootstrapToken = parsed.optString("bootstrap_token", "").trim()
        if (bootstrapToken.length < MIN_TOKEN_CHARS) {
            return ProvisioningVerdict.Refused("provisioning_bootstrap_token_too_short")
        }
        val challenge = parsed.optString("attestation_challenge", "").trim()
        if (challenge.isEmpty()) {
            return ProvisioningVerdict.Refused("provisioning_challenge_missing")
        }

        // Last, and over the rebuilt canonical bytes rather than the transmitted string:
        // two JSON documents can differ in whitespace and key order and mean the same
        // thing, and signing one spelling while verifying another passes only by luck.
        val ok = runCatching {
            ConnectivityManifestVerifier.verifySignatureFor(
                ConnectivityManifestVerifier.canonical(parsed), signatureHex, publicKeyPem,
            )
        }.getOrDefault(false)
        if (!ok) return ProvisioningVerdict.Refused("provisioning_signature_invalid")

        return ProvisioningVerdict.Accepted(
            ProvisioningPayload(
                provisioningId = provisioningId,
                gatewayUrl = gatewayUrl,
                pairingToken = pairingToken,
                bootstrapToken = bootstrapToken,
                attestationChallenge = challenge,
                expectedManifestVersion = parsed.optInt("expected_manifest_version", 0),
                issuedAtMs = parsed.optLong("issued_at_ms", 0L),
                expiresAtMs = expiresAtMs,
            ),
        )
    }

    private fun isAcceptableUrl(url: String, allowInsecureLoopback: Boolean): Boolean {
        if (url.startsWith("https://", ignoreCase = true)) return true
        if (!allowInsecureLoopback) return false
        return url.startsWith("http://127.0.0.1", ignoreCase = true) ||
            url.startsWith("http://localhost", ignoreCase = true)
    }
}
