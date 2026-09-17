package com.dial.van.gateway

import android.content.Context
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dial.van.BuildConfig
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
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * VAN secure gateway client. Android is a deterministic edge, never an agent runtime.
 * Owner commands cross this signed boundary into the gateway/Hermes control plane.
 */
class VanGatewayClient(context: Context) {

    private val prefs = EncryptedSharedPreferences.create(
        context.applicationContext,
        "van_gateway_creds",
        MasterKey.Builder(context.applicationContext).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

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

    fun hasIngressToken(): Boolean = !ingressToken.isNullOrBlank()

    fun configureIngress(baseUrl: String, token: String) {
        val normalizedToken = token.trim()
        require(normalizedToken.length >= MIN_INGRESS_TOKEN_CHARS) { "ingress_token_too_short" }
        val normalizedUrl = normalizeGatewayBaseUrl(baseUrl)
        prefs.edit()
            .putString(KEY_BASE, normalizedUrl)
            .putString(KEY_INGRESS_TOKEN, normalizedToken)
            .apply()
    }

    fun isEnrolled(): Boolean = !deviceId.isNullOrBlank() && !deviceSecret.isNullOrBlank()

    suspend fun enrollThisDevice(label: String = "android"): JSONObject {
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val secret = Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        val id = "android-${UUID.randomUUID()}"
        return enroll(id, secret, label)
    }

    suspend fun enroll(deviceId: String, deviceSecret: String, label: String = "android"): JSONObject =
        withContext(Dispatchers.IO) {
            val body = JSONObject()
                .put("device_id", deviceId)
                .put("device_secret", deviceSecret)
                .put("public_key_pem", "android-device")
                .put("label", label)
            val resp = postJson("/v1/devices/enroll", body)
            this@VanGatewayClient.deviceId = deviceId
            this@VanGatewayClient.deviceSecret = deviceSecret
            resp
        }

    suspend fun health(): JSONObject = withContext(Dispatchers.IO) { getJson("/health") }

    suspend fun googleMesh(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/google/mesh") }

    suspend fun briefing(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/briefing") }

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

    suspend fun events(afterSeq: Long = 0L): JSONObject = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        getJson("/v1/events?device_id=${encodeQuery(id)}&after_seq=$afterSeq")
    }

    /**
     * Rev 3.1 signed owner-intent envelope. Authority-bearing provenance fields are
     * HMAC-covered by signature v2. ``client_context`` remains non-authoritative.
     */
    suspend fun dispatchCommand(
        text: String,
        actionClass: String = "A1",
        projectId: String? = null,
        idempotencyKey: String,
        approvalToken: String? = null,
        issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
        turnId: String? = null,
        originChannel: String = "UI",
        expiresAtUnix: Long? = null,
        noStaleReplay: Boolean = false,
        speechEvidenceRef: String? = null,
        contextCapsuleRevision: Int? = null,
        contextCapsuleHash: String? = null,
    ): JSONObject = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        val secret = deviceSecret ?: error("not_enrolled")
        val commandId = UUID.randomUUID().toString()
        val nonce = UUID.randomUUID().toString()
        val principalType = "OWNER_DEVICE"
        val requestedBy = "device:$id"
        val contextTrust = "CONVERSATION"
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

    private fun postJson(path: String, body: JSONObject): JSONObject {
        val conn = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            applyIngressAuth(this)
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
        val token = ingressToken?.takeIf { it.isNotBlank() } ?: error("ingress_token_unconfigured")
        conn.setRequestProperty("X-Van-Ingress-Token", token)
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
        private const val MIN_INGRESS_TOKEN_CHARS = 32
    }
}

class GatewayHttpException(val code: Int, val body: String) : Exception("gateway_http_$code: $body")
