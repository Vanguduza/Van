package com.dial.van.gateway

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dial.van.visual.VanLiveVisualState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Signed client for Van secure gateway. Does not launch models; Hermes stays behind the gateway.
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
        get() = prefs.getString(KEY_BASE, "http://127.0.0.1:8787")!!
        set(value) = prefs.edit().putString(KEY_BASE, value.trimEnd('/')).apply()

    var deviceId: String?
        get() = prefs.getString(KEY_DEVICE, null)
        set(value) = prefs.edit().putString(KEY_DEVICE, value).apply()

    private var deviceSecret: String?
        get() = prefs.getString(KEY_SECRET, null)
        set(value) = prefs.edit().putString(KEY_SECRET, value).apply()

    fun isEnrolled(): Boolean = !deviceId.isNullOrBlank() && !deviceSecret.isNullOrBlank()

    suspend fun enroll(deviceId: String, deviceSecret: String, label: String = "android"): JSONObject =
        withContext(Dispatchers.IO) {
            val body = JSONObject()
                .put("device_id", deviceId)
                .put("device_secret", deviceSecret)
                .put("public_key_pem", "android-device")
                .put("label", label)
            val resp = postJson("/v1/devices/enroll", body, signed = false)
            this@VanGatewayClient.deviceId = deviceId
            this@VanGatewayClient.deviceSecret = deviceSecret
            resp
        }

    suspend fun health(): JSONObject = withContext(Dispatchers.IO) { getJson("/health") }

    suspend fun googleMesh(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/google/mesh") }

    suspend fun briefing(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/briefing") }

    suspend fun decisions(): org.json.JSONArray = withContext(Dispatchers.IO) {
        val text = rawGet("/v1/decisions")
        org.json.JSONArray(text)
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
            val response = postJson("/v1/commands", body, signed = false)
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

            // Accepted/in_flight means Hermes owns the work. This is not SUCCESS; the owner-turn
            // handoff is complete, so it may settle after a brief WORKING acknowledgement.
            "accepted", "in_flight" -> {
                VanLiveVisualState.dispatchAccepted()
                VanLiveVisualState.settleToIdle(delayMs = 900L)
            }

            // Command-scoped degradation is a visible warning. Persistent subsystem degradation
            // is independently sourced from DegradedModeStore and cannot be hidden by this settle.
            "degraded" -> {
                VanLiveVisualState.warning(urgency = 0.35f)
                VanLiveVisualState.settleToIdle(delayMs = 1_500L, allowCritical = true)
            }

            "denied", "expired", "conflict", "rejected", "rejected_untrusted" -> {
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

    private fun postJson(path: String, body: JSONObject, signed: Boolean): JSONObject {
        val conn = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
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

    private fun rawGet(path: String): String {
        val conn = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.readText() ?: "[]"
        if (code !in 200..299) throw GatewayHttpException(code, text)
        return text
    }

    companion object {
        private const val KEY_BASE = "base_url"
        private const val KEY_DEVICE = "device_id"
        private const val KEY_SECRET = "device_secret"
    }
}

class GatewayHttpException(val code: Int, val body: String) : Exception("gateway_http_$code: $body")
