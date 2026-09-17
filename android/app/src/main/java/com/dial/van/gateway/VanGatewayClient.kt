package com.dial.van.gateway

import android.content.Context
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
import java.security.SecureRandom
import android.util.Base64
import java.nio.charset.StandardCharsets
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * VAN secure gateway client. Android UI never executes shell/SSH directly; owner commands and
 * authoritative admin reads cross this boundary into the gateway/Hermes control plane.
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

    private var deviceAccessToken: String?
        get() = prefs.getString(KEY_DEVICE_ACCESS_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_DEVICE_ACCESS_TOKEN, value).apply()

    fun hasIngressToken(): Boolean = !ingressToken.isNullOrBlank()

    fun isEnrolled(): Boolean = !deviceId.isNullOrBlank() && !deviceSecret.isNullOrBlank()

    fun isPaired(): Boolean = isEnrolled() && hasIngressToken() && !deviceAccessToken.isNullOrBlank()

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
        val id = "android-${java.util.UUID.randomUUID()}"
        val body = JSONObject()
            .put("pairing_token", normalizedPairingToken)
            .put("device_id", id)
            .put("device_secret", secret)
            .put("public_key_pem", "android-device")
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

    suspend fun dispatchCommand(
        text: String,
        actionClass: String = "A1",
        projectId: String? = null,
        idempotencyKey: String,
        approvalToken: String? = null,
        issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
    ): JSONObject = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        val secret = deviceSecret ?: error("not_enrolled")
        val commandId = java.util.UUID.randomUUID().toString()
        val canonical = listOf(
            commandId,
            idempotencyKey,
            id,
            issuedAtUnix.toString(),
            actionClass,
            projectId ?: "",
            text,
        ).joinToString("|")
        val signature = hmacSha256(secret, canonical)
        val body = JSONObject()
            .put("command_id", commandId)
            .put("idempotency_key", idempotencyKey)
            .put("device_id", id)
            .put("issued_at_unix", issuedAtUnix)
            .put("signature", signature)
            .put("text", text)
            .put("action_class", actionClass)
            .put("context_trust", "CONVERSATION")
        if (projectId != null) body.put("project_id", projectId)
        if (approvalToken != null) body.put("approval_token", approvalToken)

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

            "accepted", "in_flight" -> {
                VanLiveVisualState.dispatchAccepted()
                VanLiveVisualState.settleToIdle(delayMs = 900L)
            }

            "succeeded", "success", "completed" -> {
                // Only an explicit authoritative completion may become success.
                VanLiveVisualState.transition(
                    state = com.dial.van.visual.VanDurableState.SUCCESS,
                    urgency = 0f,
                )
                VanLiveVisualState.settleToIdle(delayMs = 1_200L)
            }

            "degraded" -> {
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
        val text = stream?.bufferedReader()?.readText() ?: "{}"
        if (code !in 200..299) throw GatewayHttpException(code, text)
        return JSONObject(text)
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
        val text = stream?.bufferedReader()?.readText() ?: "[]"
        if (code !in 200..299) throw GatewayHttpException(code, text)
        return text
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
}

class GatewayHttpException(val code: Int, val body: String) : Exception("gateway_http_$code: $body")
