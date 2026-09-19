package com.dial.van.gateway

import android.content.Context
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dial.van.BuildConfig
import com.dial.van.security.OwnerApprovalKeyManager
import com.dial.van.visual.VanLiveVisualState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import java.security.Signature
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * VAN secure gateway client. Android is a deterministic edge, never an agent runtime.
 * Owner commands and authoritative reads cross this authenticated boundary into the
 * gateway/Hermes control plane. Secure pairing/device-access authentication remains
 * independent from the signed per-command owner-intent envelope.
 */
class VanGatewayClient(context: Context) {

    private val prefs = EncryptedSharedPreferences.create(
        context.applicationContext,
        "van_gateway_creds",
        MasterKey.Builder(context.applicationContext).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    private val approvalKeys = OwnerApprovalKeyManager()

    var baseUrl: String
        get() {
            val configured = prefs.getString(KEY_BASE, null)
            return if (configured.isNullOrBlank()) {
                defaultGatewayBaseUrl()
            } else {
                try {
                    normalizeGatewayBaseUrl(configured)
                } catch (_: IllegalArgumentException) {
                    defaultGatewayBaseUrl()
                }
            }
        }
        set(value) = prefs.edit().putString(KEY_BASE, normalizeGatewayBaseUrl(value)).apply()

    private fun defaultGatewayBaseUrl(): String {
        val buildConfigured = BuildConfig.VAN_GATEWAY_BASE_URL.trim()
        if (buildConfigured.isNotBlank()) return normalizeGatewayBaseUrl(buildConfigured)
        check(BuildConfig.DEBUG) {
            "Production VAN_GATEWAY_BASE_URL is missing; release builds must inject a stable HTTPS endpoint."
        }
        return "http://127.0.0.1:8787"
    }

    private fun normalizeGatewayBaseUrl(value: String): String {
        val normalized = value.trim().trimEnd('/')
        require(normalized.isNotBlank()) { "gateway_url_blank" }
        val secure = normalized.startsWith("https://", ignoreCase = true)
        val debugLoopback = BuildConfig.DEBUG && (
            normalized.startsWith("http://127.0.0.1", ignoreCase = true) ||
                normalized.startsWith("http://localhost", ignoreCase = true)
            )
        require(secure || debugLoopback) { "gateway_url_must_use_https" }
        return normalized
    }

    var deviceId: String?
        get() = prefs.getString(KEY_DEVICE, null)
        set(value) = prefs.edit().putString(KEY_DEVICE, value).apply()

    private var deviceSecret: String?
        get() = prefs.getString(KEY_SECRET, null)
        set(value) = prefs.edit().putString(KEY_SECRET, value).apply()

    private var ingressToken: String?
        get() = prefs.getString(KEY_INGRESS_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_INGRESS_TOKEN, value).apply()

    private var deviceAccessToken: String?
        get() = prefs.getString(KEY_DEVICE_ACCESS_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_DEVICE_ACCESS_TOKEN, value).apply()

    fun hasIngressToken(): Boolean = !ingressToken.isNullOrBlank()

    fun isEnrolled(): Boolean = !deviceId.isNullOrBlank() && !deviceSecret.isNullOrBlank()

    fun isPaired(): Boolean = isEnrolled() && hasIngressToken() && !deviceAccessToken.isNullOrBlank()

    fun newA4ApprovalSignature(): Signature = approvalKeys.newSigningSignature()

    suspend fun pairThisDevice(
        gatewayUrl: String,
        pairingToken: String,
        label: String = "android",
    ): JSONObject = withContext(Dispatchers.IO) {
        val normalizedUrl = normalizeGatewayBaseUrl(gatewayUrl)
        val normalizedPairingToken = pairingToken.trim()
        require(normalizedPairingToken.length >= MIN_PAIRING_TOKEN_CHARS) { "pairing_token_too_short" }
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val secret = Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        val id = "android-${UUID.randomUUID()}"
        val body = JSONObject()
            .put("pairing_token", normalizedPairingToken)
            .put("device_id", id)
            .put("device_secret", secret)
            .put("public_key_pem", approvalKeys.publicKeyPem())
            .put("label", label)
        val response = postJsonAt(normalizedUrl, "/v1/devices/pair", body, useIngress = false)
        val returnedIngress = response.optString("ingress_token").trim()
        val returnedDeviceAccess = response.optString("device_access_token").trim()
        require(returnedIngress.length >= MIN_INGRESS_TOKEN_CHARS) { "pairing_response_missing_ingress_token" }
        require(returnedDeviceAccess.length >= MIN_DEVICE_ACCESS_TOKEN_CHARS) { "pairing_response_missing_device_access_token" }
        prefs.edit()
            .putString(KEY_BASE, normalizedUrl)
            .putString(KEY_INGRESS_TOKEN, returnedIngress)
            .putString(KEY_DEVICE_ACCESS_TOKEN, returnedDeviceAccess)
            .putString(KEY_DEVICE, id)
            .putString(KEY_SECRET, secret)
            .apply()
        response.remove("ingress_token")
        response.remove("device_access_token")
        response
    }

    suspend fun health(): JSONObject = withContext(Dispatchers.IO) { getJson("/health") }

    suspend fun googleMesh(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/google/mesh") }

    suspend fun briefing(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/briefing") }

    suspend fun tradingTrades(view: String, limit: Int = 12): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/trades?view=${encodeQuery(view)}&limit=$limit")
    }

    suspend fun tradingPortfolio(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/portfolio") }

    suspend fun tradingAccounts(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/accounts") }

    suspend fun tradingMarketState(symbol: String? = null): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/market-state" + (symbol?.let { "?symbol=${encodeQuery(it)}" } ?: ""))
    }

    suspend fun tradingRisk(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/risk") }

    suspend fun tradingTradeDetail(tradeIntentId: String): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/trades/${encodeSegment(tradeIntentId)}")
    }

    suspend fun tradingBars(symbol: String, timeframe: String = "H1", limit: Int = 300): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/bars?symbol=${encodeQuery(symbol)}&timeframe=${encodeQuery(timeframe)}&limit=$limit")
    }

    suspend fun tradingAccountAction(
        action: String,
        args: kotlinx.serialization.json.JsonObject,
        approvalProof: kotlinx.serialization.json.JsonObject? = null,
    ): Pair<Int, String> = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        val secret = deviceSecret ?: error("not_enrolled")
        val body = com.dial.van.trading.AccountOnboarding.requestBody(
            secret, id, System.currentTimeMillis() / 1000L, action, args, approvalProof,
        )
        val conn = (URL("$baseUrl/v1/trading/accounts/action").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            applyIngressAuth(this)
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 90_000
        }
        conn.outputStream.use { it.write(body.toString().toByteArray(StandardCharsets.UTF_8)) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        code to (stream?.bufferedReader()?.readText() ?: "{}")
    }

    /**
     * The one-time challenge the device signs inside the biometric before a trading
     * account or credential change (P1-SEC-004).
     *
     * The challenge is bound to this device, this action and a digest of these exact
     * arguments, so an approval for one change cannot be presented for another.
     */
    suspend fun tradingAccountChallenge(
        action: String,
        args: kotlinx.serialization.json.JsonObject,
    ): Pair<Int, String> = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        val secret = deviceSecret ?: error("not_enrolled")
        val body = com.dial.van.trading.AccountOnboarding.requestBody(
            secret, id, System.currentTimeMillis() / 1000L, action, args,
        )
        val conn = (URL("$baseUrl/v1/trading/accounts/challenge").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            applyIngressAuth(this)
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        conn.outputStream.use { it.write(body.toString().toByteArray(StandardCharsets.UTF_8)) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        code to (stream?.bufferedReader()?.use { it.readText() } ?: "")
    }

    suspend fun decisions(): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/decisions"))
    }

    suspend fun resolveDecision(decisionId: String, approved: Boolean): JSONObject = withContext(Dispatchers.IO) {
        postJson(
            "/v1/decisions/${encodeSegment(decisionId)}/resolve",
            JSONObject().put("approved", approved),
        )
    }

    suspend fun projects(): JSONArray = withContext(Dispatchers.IO) {
        getJson("/v1/projects").optJSONArray("projects") ?: JSONArray()
    }

    suspend fun projectTruth(projectId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/projects/${encodeSegment(projectId)}/truth")
    }

    suspend fun attention(): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/attention"))
    }

    suspend fun browserStatus(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/browser/status")
    }

    suspend fun browserTasks(): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/browser/tasks"))
    }

    suspend fun browserEscalations(): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/browser/escalations"))
    }

    suspend fun browserPolicy(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/browser/policy")
    }

    suspend fun browserEvidence(taskId: String): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/browser/tasks/${encodeSegment(taskId)}/evidence"))
    }

    // ---------------------------------------------------------------- missions
    //
    // Rev 1 §§33, 43 — the surfaces Home, Missions, Needs You, Activity and
    // Understanding read. Every one is a real gateway read; §48 forbids screens
    // disconnected from live APIs, so there is deliberately no local fixture
    // behind any of these.

    suspend fun missions(activeOnly: Boolean = false): JSONArray = withContext(Dispatchers.IO) {
        val suffix = if (activeOnly) "?active=true" else ""
        JSONArray(rawGet("/v1/missions$suffix"))
    }

    suspend fun mission(missionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/missions/${encodeSegment(missionId)}")
    }

    suspend fun missionActivity(missionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/missions/${encodeSegment(missionId)}/activity")
    }

    suspend fun missionEvidence(missionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/missions/${encodeSegment(missionId)}/evidence")
    }

    /** §33 — one surface for everything waiting on the owner. */
    suspend fun needsYou(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/needs-you")
    }

    /** §34 — the owner timeline, already grouped by mission by the gateway. */
    suspend fun activityFeed(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/activity")
    }

    suspend fun capabilityStatus(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/capabilities/status")
    }

    /** Cancelling your own mission is yours to say (§2.3). */
    suspend fun cancelMission(missionId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/missions/${encodeSegment(missionId)}/cancel", JSONObject())
    }

    /**
     * A note on the record. It does not move the mission by itself — Android is
     * not a planner (§2.3), so this becomes an event Hermes reads on its turn.
     */
    suspend fun messageMission(missionId: String, message: String): JSONObject =
        withContext(Dispatchers.IO) {
            postJson(
                "/v1/missions/${encodeSegment(missionId)}/message",
                JSONObject().put("message", message),
            )
        }

    // ----------------------------------------------------------- understanding

    /** §33 — what VAN believes about how the owner works, and how firmly. */
    suspend fun understanding(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/understanding")
    }

    suspend fun confirmUnderstanding(assertionId: String): JSONObject =
        withContext(Dispatchers.IO) {
            postJson("/v1/understanding/${encodeSegment(assertionId)}/confirm", JSONObject())
        }

    suspend fun correctUnderstanding(assertionId: String, newValue: String): JSONObject =
        withContext(Dispatchers.IO) {
            postJson(
                "/v1/understanding/${encodeSegment(assertionId)}/correct",
                JSONObject().put("new_value", newValue),
            )
        }

    suspend fun rejectUnderstanding(assertionId: String): JSONObject =
        withContext(Dispatchers.IO) {
            postJson("/v1/understanding/${encodeSegment(assertionId)}/reject", JSONObject())
        }

    /** §63.5 — inferred understanding must be reversible, in practice. */
    suspend fun revertAdaptation(changeId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/understanding/adaptation/${encodeSegment(changeId)}/revert", JSONObject())
    }

    suspend fun confirmAdaptation(changeId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/understanding/adaptation/${encodeSegment(changeId)}/confirm", JSONObject())
    }

    /** §36 — every standing grant, where it came from, when it was last used. */
    suspend fun permissions(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/permissions")
    }

    suspend fun revokePermission(grantId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/permissions/${encodeSegment(grantId)}/revoke", JSONObject())
    }

    suspend fun autonomy(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/autonomy") }

    suspend fun technologyRadar(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/technology-radar")
    }

    /** §41 — the scoreboard, including every dimension VAN cannot yet measure. */
    suspend fun evalReport(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/eval") }

    suspend fun events(afterSeq: Long = 0L): JSONObject = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        getJson("/v1/events?device_id=${encodeQuery(id)}&after_seq=$afterSeq")
    }

    /**
     * Rev 3.1 signed owner-intent envelope. Authority-bearing provenance fields are HMAC-covered
     * by signature v2. Pairing/device-access authentication remains mandatory on the transport.
     */
    suspend fun dispatchCommand(
        text: String,
        actionClass: String = "A1",
        projectId: String? = null,
        idempotencyKey: String,
        approvalToken: String? = null,
        approvalChallengeId: String? = null,
        approvalSignatureBase64: String? = null,
        approvalAlgorithm: String = OwnerApprovalKeyManager.PROOF_ALGORITHM,
        issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
        turnId: String? = null,
        originChannel: String = "UI",
        expiresAtUnix: Long? = null,
        noStaleReplay: Boolean = false,
        speechEvidenceRef: String? = null,
        contextCapsuleRevision: Int? = null,
        contextCapsuleHash: String? = null,
        declaredTrust: String = TRUST_CONVERSATION,
    ): JSONObject = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        val secret = deviceSecret ?: error("not_enrolled")
        val commandId = UUID.randomUUID().toString()
        val nonce = UUID.randomUUID().toString()
        val principalType = "OWNER_DEVICE"
        val requestedBy = "device:$id"
        // Trust is a property of who authored the text, not of which device sent it.
        // Hardcoding CONVERSATION here is what allowed any app's notification to reach the
        // owner-authority path labelled trusted (finding P0-SEC-002). The caller must now
        // state the provenance, and a third-party channel is pinned UNTRUSTED. The gateway
        // derives this independently and will not believe an elevated claim, so this is a
        // correctness fix on the device, not the security boundary itself.
        val contextTrust = contextTrustFor(originChannel, declaredTrust)
        val canonical = listOf(
            "v2",
            commandId,
            idempotencyKey,
            id,
            issuedAtUnix.toString(),
            actionClass,
            projectId ?: "",
            turnId ?: "",
            originChannel,
            principalType,
            requestedBy,
            expiresAtUnix?.toString() ?: "",
            nonce,
            contextCapsuleRevision?.toString() ?: "",
            contextCapsuleHash ?: "",
            speechEvidenceRef ?: "",
            if (noStaleReplay) "1" else "0",
            contextTrust,
            text,
        ).joinToString("|")
        val signature = hmacSha256(secret, canonical)
        val body = JSONObject()
            .put("command_id", commandId)
            .put("idempotency_key", idempotencyKey)
            .put("device_id", id)
            .put("issued_at_unix", issuedAtUnix)
            .put("signature", signature)
            .put("signature_version", 2)
            .put("text", text)
            .put("action_class", actionClass)
            .put("context_trust", contextTrust)
            .put("origin_channel", originChannel)
            .put("principal_type", principalType)
            .put("requested_by", requestedBy)
            .put("nonce", nonce)
            .put("no_stale_replay", noStaleReplay)
        if (projectId != null) body.put("project_id", projectId)
        if (approvalToken != null) body.put("approval_token", approvalToken)
        if (approvalChallengeId != null && approvalSignatureBase64 != null) {
            body.put(
                "approval_proof",
                JSONObject()
                    .put("challenge_id", approvalChallengeId)
                    .put("signature_b64", approvalSignatureBase64)
                    .put("algorithm", approvalAlgorithm),
            )
        }
        if (turnId != null) body.put("turn_id", turnId)
        if (expiresAtUnix != null) body.put("expires_at_unix", expiresAtUnix)
        if (speechEvidenceRef != null) body.put("speech_evidence_ref", speechEvidenceRef)
        if (contextCapsuleRevision != null) body.put("context_capsule_revision", contextCapsuleRevision)
        if (contextCapsuleHash != null) body.put("context_capsule_hash", contextCapsuleHash)

        VanLiveVisualState.dispatchStarted()
        try {
            val response = postJson("/v1/commands", body)
            publishCommandVisualStatus(response)
            response
        } catch (exc: Throwable) {
            VanLiveVisualState.warning(urgency = 0.35f)
            VanLiveVisualState.settleToIdle(delayMs = 1_500L, allowCritical = true)
            throw exc
        }
    }

    /** Map protocol truth to presence without inventing task completion. */
    private fun publishCommandVisualStatus(response: JSONObject) {
        when (response.optString("status")) {
            "approval_required" -> VanLiveVisualState.waitingForOwner()

            "accepted", "in_flight", "submitted", "executing", "verifying" -> {
                VanLiveVisualState.dispatchAccepted()
                VanLiveVisualState.settleToIdle(delayMs = 900L)
            }

            "VERIFIED_SUCCESS", "verified_success", "succeeded", "success", "completed" -> {
                VanLiveVisualState.transition(
                    state = com.dial.van.visual.VanDurableState.SUCCESS,
                    urgency = 0f,
                )
                VanLiveVisualState.settleToIdle(delayMs = 1_200L)
            }

            "degraded", "UNVERIFIABLE", "VERIFICATION_FAILED", "PARTIAL_SUCCESS" -> {
                VanLiveVisualState.warning(urgency = 0.35f)
                VanLiveVisualState.settleToIdle(delayMs = 1_500L, allowCritical = true)
            }

            "denied", "expired", "conflict", "rejected", "rejected_untrusted", "failed", "error" -> {
                VanLiveVisualState.warning(urgency = 0.40f)
                VanLiveVisualState.settleToIdle(delayMs = 1_800L, allowCritical = true)
            }

            else -> VanLiveVisualState.settleToIdle(delayMs = 700L)
        }
    }

    private fun hmacSha256(secret: String, canonical: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(StandardCharsets.UTF_8), "HmacSHA256"))
        val raw = mac.doFinal(canonical.toByteArray(StandardCharsets.UTF_8))
        return raw.joinToString("") { b -> "%02x".format(b) }
    }

    private fun postJson(path: String, body: JSONObject): JSONObject =
        postJsonAt(baseUrl, path, body, useIngress = true)

    private fun postJsonAt(
        rootUrl: String,
        path: String,
        body: JSONObject,
        useIngress: Boolean,
    ): JSONObject {
        val conn = (URL("$rootUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            if (useIngress) applyIngressAuth(this)
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 60_000
        }
        conn.outputStream.use { it.write(body.toString().toByteArray(StandardCharsets.UTF_8)) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseText = stream?.bufferedReader()?.readText() ?: "{}"
        if (code !in 200..299) throw GatewayHttpException(code, responseText)
        return JSONObject(responseText)
    }

    private fun getJson(path: String): JSONObject = JSONObject(rawGet(path))

    private fun applyIngressAuth(conn: HttpURLConnection) {
        val ingress = ingressToken?.takeIf { it.isNotBlank() } ?: error("ingress_token_unconfigured")
        val device = deviceAccessToken?.takeIf { it.isNotBlank() } ?: error("device_access_token_unconfigured")
        conn.setRequestProperty("X-Van-Ingress-Token", ingress)
        conn.setRequestProperty("X-Van-Device-Token", device)
    }

    private fun rawGet(path: String): String {
        val conn = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            applyIngressAuth(this)
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseText = stream?.bufferedReader()?.readText() ?: "[]"
        if (code !in 200..299) throw GatewayHttpException(code, responseText)
        return responseText
    }

    private fun encodeSegment(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())
        .replace("+", "%20")

    private fun encodeQuery(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())

    companion object {
        private const val KEY_BASE = "base_url"
        private const val KEY_DEVICE = "device_id"
        private const val KEY_SECRET = "device_secret"
        private const val KEY_INGRESS_TOKEN = "ingress_token"
        private const val KEY_DEVICE_ACCESS_TOKEN = "device_access_token"
        private const val MIN_INGRESS_TOKEN_CHARS = 32
        private const val MIN_DEVICE_ACCESS_TOKEN_CHARS = 32
        private const val MIN_PAIRING_TOKEN_CHARS = 32
    }

    companion object {
        const val TRUST_CONVERSATION = "CONVERSATION"
        const val TRUST_UNTRUSTED = "UNTRUSTED"

        /** Channels whose content is authored by a third party, not by the owner. */
        private val THIRD_PARTY_CHANNELS = setOf(
            "NOTIFICATION_EVENT",
            "SHARE_INTENT",
            "AUTOMATION",
            "HERMES_EVENT",
            "SYSTEM_EVENT",
        )

        /**
         * Resolve the trust label to send. A third-party channel is always UNTRUSTED and a
         * caller cannot raise it. Mirrors the gateway's own derivation so the device and the
         * server agree; the gateway remains authoritative either way.
         */
        fun contextTrustFor(originChannel: String, declaredTrust: String): String =
            if (originChannel in THIRD_PARTY_CHANNELS) TRUST_UNTRUSTED else declaredTrust
    }

}

class GatewayHttpException(val code: Int, val body: String) : Exception("gateway_http_$code: $body")
