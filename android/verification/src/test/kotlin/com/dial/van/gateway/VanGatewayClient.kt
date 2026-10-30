package com.dial.van.gateway

import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger
import java.security.Signature
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.X509TrustManager
import org.json.JSONObject
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow

/** Test-only gateway seam for compiling the real socket/session adapter without Android. */
class VanGatewayClient {
    @Volatile var paired = true
    val openCalls = AtomicInteger()
    val resumeCalls = AtomicInteger()
    val proofCalls = AtomicInteger()
    val commandCalls = AtomicInteger()
    val statusCalls = AtomicInteger()
    val preparedCommands = CopyOnWriteArrayList<String>()
    var onCommand: suspend (JSONObject) -> JSONObject = { body ->
        JSONObject().put("status", "accepted").put("command_id", body.getString("command_id")).put("message", "Working on it")
    }
    var onStatus: suspend (String) -> JSONObject = {
        JSONObject().put("owner_status", "WORKING").put("sentence", "Working on it").put("finished", false)
    }
    val pendingRequests = CopyOnWriteArrayList<List<String>>()
    val resumePaths = CopyOnWriteArrayList<Pair<String, String>>()
    var onOpen: suspend (Int) -> JSONObject = { call ->
        JSONObject().put("van_session_id", "session_$call").put("session_epoch", 1).put("path_epoch", 1)
    }
    var onResume: suspend (Int, List<String>) -> JSONObject = { call, _ ->
        JSONObject().put("accepted", true).put("session_epoch", 1)
            .put("new_path_epoch", call + 1).put("command_states", JSONObject())
    }
    var restoredIdentity: JSONObject? = null
    fun restoredSessionIdentity(): JSONObject? = restoredIdentity

    fun isPaired() = paired
    fun deviceIdOrEmpty() = "test-device"
    fun ensureTlsIdentity() = Unit
    fun tlsTransport(url: String): Pair<SSLSocketFactory, X509TrustManager>? = null
    fun sessionSocketUrl(vanSessionId: String) = "wss://gateway.invalid/v1/session/ws?van_session_id=$vanSessionId"
    fun sessionSocketHeaders(): Map<String, String> {
        val attempt = proofCalls.incrementAndGet()
        return mapOf("X-Van-Device-Proof" to "test-proof-$attempt", "X-Van-Device-Proof-Issued-At" to attempt.toString())
    }
    fun newA4ApprovalSignature(): Signature = Signature.getInstance("SHA256withECDSA")
    suspend fun commandStatus(commandId: String): JSONObject {
        statusCalls.incrementAndGet()
        return onStatus(commandId)
    }
    suspend fun dispatchCommand(
        text: String, actionClass: String = "A1", projectId: String? = null, idempotencyKey: String,
        approvalToken: String? = null, approvalChallengeId: String? = null,
        approvalSignatureBase64: String? = null, issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
        turnId: String? = null, originChannel: String = "UI", expiresAtUnix: Long? = null,
        noStaleReplay: Boolean = false, speechEvidenceRef: String? = null, speakerEvidenceMilli: Int? = null,
        clientContext: Map<String, String> = emptyMap(), onPreparedCommand: (String) -> Unit = {},
    ): JSONObject {
        val call = commandCalls.incrementAndGet()
        val body = JSONObject().put("command_id", "prepared-command-$call").put("nonce", "prepared-nonce-$call")
            .put("idempotency_key", idempotencyKey).put("device_id", "test-device")
            .put("issued_at_unix", issuedAtUnix).put("signature", "test-signature-$call")
            .put("text", text).put("action_class", actionClass).put("client_context", JSONObject(clientContext))
            .put("origin_channel", originChannel).put("turn_id", turnId)
        if (approvalChallengeId != null) body.put("approval_proof", JSONObject().put("challenge_id", approvalChallengeId)
            .put("signature_b64", approvalSignatureBase64))
        val prepared = body.toString()
        preparedCommands += prepared
        onPreparedCommand(prepared)
        return onCommand(body)
    }
    suspend fun sessionOpen(pathId: String, routeId: String, protocol: String = "WSS", pathClass: String = "A_REALTIME"): JSONObject = onOpen(openCalls.incrementAndGet())
    suspend fun sessionUpstream(envelope: JSONObject): JSONObject = JSONObject().put("accepted", true).put("kind", envelope.getString("kind"))
    fun sessionDownstream(vanSessionId: String, afterSeq: Long): Flow<JSONObject> = emptyFlow()
    suspend fun sessionResume(
        vanSessionId: String, sessionEpoch: Int, lastEventSeq: Long,
        pendingCommandIds: List<String>, pathId: String, routeId: String,
        pathClass: String = "A_REALTIME",
    ): JSONObject {
        pendingRequests += pendingCommandIds
        resumePaths += pathId to pathClass
        return onResume(resumeCalls.incrementAndGet(), pendingCommandIds)
    }
}

class GatewayHttpException(val code: Int, val body: String) : Exception("gateway_http_$code: $body")
