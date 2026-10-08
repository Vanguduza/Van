package com.dial.van.gateway

import android.content.Context
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dial.van.BuildConfig
import com.dial.van.connectivity.ConnectivityRegistry
import com.dial.van.connectivity.SignedConnectivityRouting
import com.dial.van.connectivity.SignedPinTrustManager
import com.dial.van.browser.BrowserParsing
import com.dial.van.browser.BrowserSessionSnapshot
import com.dial.van.browser.BrowserStreamGrant
import com.dial.van.dialdev.DialDevActionRequest
import com.dial.van.dialdev.DialDevChange
import com.dial.van.dialdev.DialDevSse
import com.dial.van.security.DeviceProofSigner
import com.dial.van.security.MutualTlsIdentity
import com.dial.van.security.MutualTlsScope
import com.dial.van.security.OwnerDeviceIdentity
import com.dial.van.security.OwnerApprovalKeyManager
import com.dial.van.security.OwnerAuthorityToken
import com.dial.van.trading.StrategyPromotionProtocol
import com.dial.van.visual.VanLiveVisualState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.X509TrustManager
import javax.net.ssl.TrustManagerFactory
import java.security.KeyStore
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

    private val provisioningMutex = kotlinx.coroutines.sync.Mutex()
    private val sessionOpenMutex = kotlinx.coroutines.sync.Mutex()

    /**
     * P3-AND-001 — stops VAN hammering a gateway that is down, and gives the health screen
     * a number instead of a guess.
     */
    private val breaker = GatewayCircuitBreaker()


    private val prefs = EncryptedSharedPreferences.create(
        context.applicationContext,
        "van_gateway_creds",
        MasterKey.Builder(context.applicationContext).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    private val approvalKeys = OwnerApprovalKeyManager()

    /**
     * ADR-RB-025 — the hardware key this phone signs privileged requests with.
     *
     * Separate from `approvalKeys` on purpose: an approval is a decision and is gated on
     * the owner's biometric, while a proof is an identity and has to work with the screen
     * off, or a browser session would die every time the phone was put down.
     */
    private val deviceIdentity = OwnerDeviceIdentity()
    private val proofSigner = DeviceProofSigner(deviceIdentity)

    /** The phone's client certificate and the pinned gateway CA for the direct mutual-TLS link. */
    private val mtls = MutualTlsIdentity(context)
    @Volatile private var deviceIdentityReady = false
    @Volatile private var signedRouting: SignedConnectivityRouting? = null
    private val platformTrust by lazy {
        TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).run {
            init(null as KeyStore?); trustManagers.filterIsInstance<X509TrustManager>().first()
        }
    }

    /** Re-read and verify the signed store before changing any credential-bearing route. */
    @Synchronized
    fun applyConnectivity(registry: ConnectivityRegistry): Boolean {
        val manifest = registry.current() ?: return false
        val next = SignedConnectivityRouting.from(manifest)
        if (next.version == signedRouting?.version) return false
        require(next.version > (signedRouting?.version ?: 0)) { "connectivity_manifest_rollback" }
        signedRouting = next
        return true
    }

    private fun signedTls(url: String, presentCertificate: Boolean): Pair<SSLSocketFactory, X509TrustManager>? {
        val route = signedRouting?.takeIf { it.permitsTls(url) } ?: return null
        val trust = SignedPinTrustManager(listOfNotNull(mtls.pinnedTrustManager(), platformTrust), route.pins)
        return mtls.socketFactoryWithTrust(trust, presentCertificate) to trust
    }

    fun browserSignalTransport(url: String): SSLSocketFactory? = signedTls(url, false)?.first

    fun admitBrowserGrant(grant: BrowserStreamGrant): BrowserStreamGrant = signedRouting?.let {
        com.dial.van.connectivity.SignedBrowserRouting.apply(it, grant)
    } ?: grant

    fun admitBrowserTransferUrl(url: String): String {
        val uri = java.net.URI(url)
        require(uri.scheme == "https" && uri.host != null && uri.rawUserInfo == null && uri.rawFragment == null && uri.rawQuery == null) {
            "browser_transfer_https_required"
        }
        return signedRouting?.let { com.dial.van.connectivity.SignedBrowserRouting.admitUrl(it, url) } ?: url
    }

    /**
     * Every HTTP connection to the gateway is opened here, so each one carries the pinned
     * trust and the client certificate when the build is configured for the direct link.
     */
    private fun open(url: String): HttpURLConnection {
        val route = signedRouting
        val direct = MutualTlsScope.appliesToManagedGateway(BuildConfig.VAN_GATEWAY_BASE_URL, url,
            route?.gatewayUrl, route?.sessionUrl)
        val preEnrolment = MutualTlsScope.isPreEnrolment(url)
        // Every other route on the direct link refuses a phone without a certificate, so
        // enrol (or renew) first. Best effort: an unpaired or unbound phone cannot yet, and
        // the gateway's 403 then says exactly that.
        if (direct && !preEnrolment) runCatching { ensureTlsIdentity() }
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.instanceFollowRedirects = false
        if (conn is HttpsURLConnection && signedRouting?.permitsTls(url) == true) {
            conn.sslSocketFactory = signedTls(url, !preEnrolment)?.first ?: error("signed_tls_unavailable")
        } else if (conn is HttpsURLConnection && direct) {
            val factory = if (preEnrolment) mtls.enrolmentSocketFactory() else mtls.socketFactory()?.first
            factory?.let { conn.sslSocketFactory = it }
        }
        return conn
    }

    /**
     * Socket factory + pinned trust for a session WebSocket to [url]: only when [url] is the
     * direct mutual-TLS endpoint this build pins, otherwise null (platform trust).
     */
    fun tlsTransport(url: String): Pair<SSLSocketFactory, X509TrustManager>? =
        signedTls(url, true) ?: if (MutualTlsScope.applies(BuildConfig.VAN_GATEWAY_BASE_URL, url)) mtls.socketFactory() else null

    /**
     * Hold a current client certificate for the direct mutual-TLS link: enrol on first use,
     * renew within thirty days of expiry. Blocking; call off the main thread. A no-op when
     * the build pins no CA or the phone is not paired yet. The request is proved with the
     * bound device key, and the certificate's key never leaves the Keystore.
     */
    @Synchronized
    fun ensureTlsIdentity() {
        if (!mtls.isConfigured || mtls.hasUsableCertificate()) return
        val route = signedRouting
        if (!MutualTlsScope.appliesToManagedGateway(BuildConfig.VAN_GATEWAY_BASE_URL, baseUrl,
                route?.gatewayUrl, route?.sessionUrl)) return
        val device = deviceId?.takeIf { it.isNotBlank() } ?: return
        ensureCertifiedIdentity()
        val answer = postProved(TLS_CERTIFICATE_PATH, JSONObject().put("csr_pem", mtls.certificateRequestPem(device)))
        mtls.storeCertificate(answer.getString("certificate_pem"))
    }

    /** Whether this device has enrolled a hardware identity (§0D.3). */
    fun hasDeviceIdentity(): Boolean = deviceIdentity.isEnrolled()

    @Synchronized
    private fun ensureCertifiedIdentity() {
        if (deviceIdentityReady) return
        require(isPaired() && deviceIdentity.isEnrolled()) { "device_identity_unavailable" }
        val answer = postProved("/v1/device-binding/certify", JSONObject()
            .put("attestation_chain_b64", JSONArray(deviceIdentity.certificateChainBase64())))
        require(answer.optBoolean("bound", false) && answer.optBoolean("attestation_chain_verified", false) &&
            answer.optString("device_key_fingerprint") == deviceIdentity.publicKeyFingerprint()) { "device_identity_certification_failed" }
        deviceIdentityReady = true
    }

    suspend fun ensureDeviceIdentityReady() = withContext(Dispatchers.IO) { ensureCertifiedIdentity() }

    /**
     * Enrol this phone as the owner's device.
     *
     * Two round trips because the challenge has to be inside the certificate: the gateway
     * issues it, the Keystore bakes it into the attestation, and a chain captured from one
     * enrolment is then useless for another.
     */
    suspend fun bindThisDevice(
        bootstrapToken: String,
        expectedChallenge: String? = null,
        mayReplaceUnboundKey: Boolean = false,
    ): JSONObject = withContext(Dispatchers.IO) {
        val challenge = postRawAt(
            baseUrl, "/v1/devices/bootstrap/challenge",
            JSONObject().put("token", bootstrapToken).toString(), useIngress = false,
        ).getString("attestation_challenge")
        require(expectedChallenge == null || expectedChallenge == challenge) { "provisioning_challenge_mismatch" }
        val material = deviceIdentity.ensureKey(challenge.toByteArray(StandardCharsets.UTF_8), mayReplaceUnboundKey)
        val device = deviceId ?: error("device_not_paired")
        val path = "/v1/devices/bootstrap/attest"
        val body = JSONObject()
                .put("token", bootstrapToken)
                .put("device_id", device)
                .put("public_key_pem", material.publicKeyPem)
                .put("attestation_extension_b64", material.attestationExtensionBase64)
                .put("attestation_root_fingerprint", material.attestationRootFingerprint)
                .put("attestation_chain_b64", JSONArray(material.attestationCertificateChainBase64))
                .put("os_version", android.os.Build.VERSION.SDK_INT.toString())
                .put("os_patch_level", android.os.Build.VERSION.SECURITY_PATCH)
                .toString()
        postRawAt(baseUrl, path, body, useIngress = false, freshHeaders = { proofHeaders("POST", path, body) })
    }

    suspend fun deviceBindingStatus(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/device-binding/status")
    }

    /**
     * The headers a privileged request carries, or none when this device has no identity.
     *
     * Empty rather than throwing because an unbound device is a supported state: the
     * gateway answers on the token alone and reports `bound: false`, and the owner surface
     * says so. Throwing here would make every action fail on a phone that has simply not
     * enrolled yet, which is not the same problem.
     */
    private fun proofHeaders(
        method: String,
        path: String,
        // Named `bodyText` rather than `body` on purpose: a contract test pins the absence
        // of `body.toByteArray(` because a JsonObject was once passed to it, and a second
        // legitimate use of that spelling would blunt the guard rather than benefit from it.
        bodyText: String,
    ): Map<String, String> {
        if (!deviceIdentity.isEnrolled()) return emptyMap()
        val device = deviceId ?: return emptyMap()
        return try {
            proofSigner.headers(
                method = method, path = path, deviceId = device,
                body = bodyText.toByteArray(StandardCharsets.UTF_8),
            )
        } catch (_: OwnerDeviceIdentity.IdentityUnavailable) {
            // The key is gone (a factory reset restores the app but not the Keystore). The
            // request will be refused by the gateway and the owner surface will tell the
            // owner to re-enrol, which is better than a signature over nothing.
            emptyMap()
        }
    }

    /**
     * Where VAN connects. Readable everywhere, writable only from provisioning.
     *
     * §0D.2 / RB-121 — the setter is private on purpose, and privacy is the enforcement
     * rather than a convention. A public setter is all a "change server address" screen
     * needs, and that screen is a phishing surface with the owner's whole assistant behind
     * it: anyone who persuades them to retype an address owns every command from then on,
     * and nothing on the phone looks wrong afterwards.
     *
     * The only writer is [provisionThisDevice], which takes a payload signed by the pinned
     * connectivity authority. A release build has no other path to this value.
     */
    var baseUrl: String
        get() {
            signedRouting?.let { return it.gatewayUrl }
            val saved = prefs.getString(KEY_BASE, null)
            val configured = MutualTlsScope.effectiveBaseUrl(saved, BuildConfig.VAN_GATEWAY_BASE_URL, mtls.isConfigured)
            if (configured != null && configured != saved) {
                // Upgraded onto a build that pins the direct link: move this phone over once.
                prefs.edit().putString(KEY_BASE, configured).apply()
            }
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
        private set(value) = prefs.edit().putString(KEY_BASE, normalizeGatewayBaseUrl(value)).apply()

    private fun defaultGatewayBaseUrl(): String {
        val buildConfigured = BuildConfig.VAN_GATEWAY_BASE_URL.trim()
        if (buildConfigured.isNotBlank()) return normalizeGatewayBaseUrl(buildConfigured)
        check(BuildConfig.DEBUG) {
            "Production VAN_GATEWAY_BASE_URL is missing; release builds must inject a stable HTTPS endpoint."
        }
        return "http://127.0.0.1:8787"
    }

    private fun normalizeGatewayBaseUrl(value: String): String {
        val normalized = value.trim()
        require(normalized.isNotBlank()) { "gateway_url_blank" }
        require(com.dial.van.connectivity.GatewayBaseUrl.accepts(normalized, BuildConfig.DEBUG)) {
            "gateway_url_must_use_https"
        }
        return normalized.trimEnd('/')
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

    fun prepareTradingPromotionAuthority(
        strategyId: String,
        targetState: String,
        validationHash: String,
        issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
    ): OwnerAuthorityToken.Prepared {
        require(strategyId.isNotBlank() && targetState.isNotBlank() && validationHash.isNotBlank()) {
            "promotion_authority_subject_incomplete"
        }
        return approvalKeys.prepareOwnerAuthority(
            act = "capsule-promote",
            subject = "$strategyId:$targetState:$validationHash",
            issuedAtUnix = issuedAtUnix,
        )
    }


    /**
     * ADR-RB-026 — the whole of provisioning, from a payload the installer delivered.
     *
     * Two steps because they buy two different things, and §0D.3 needs both. Pairing earns
     * this device its ingress and access tokens; binding attests a hardware-backed Keystore
     * key so those tokens are worth nothing on any other handset. A device that paired and
     * did not bind is exactly the failure §0D.3 describes — an APK copied to another phone
     * that works.
     *
     * New attempts commit a chosen device id and candidate token before the first POST,
     * attest that hardware identity, then recoverably pair the exact saved request.
     * Previously paired devices retain their earned credentials while finishing binding.
     */
    suspend fun provisionThisDevice(
        payload: com.dial.van.connectivity.ProvisioningPayload,
        label: String = "android",
    ): JSONObject = withContext(Dispatchers.IO) {
        provisioningMutex.lock()
        try {
            val intended = normalizeGatewayBaseUrl(payload.gatewayUrl)
            val active = MutualTlsScope.effectiveBaseUrl(intended, BuildConfig.VAN_GATEWAY_BASE_URL, mtls.isConfigured)
            require(active == null || normalizeGatewayBaseUrl(active) == intended) { "provisioning_gateway_mismatch" }
            if (!isPaired()) {
                return@withContext com.dial.van.connectivity.ProvisioningRecovery.completePrebound(
                    payload = payload,
                    prepare = { preparePairing(payload, label) },
                    recoverBinding = { recoverBootstrap(payload.bootstrapToken) },
                    bind = { bindThisDevice(payload.bootstrapToken, payload.attestationChallenge) },
                    pair = { pairPreparedDevice(intended) },
                )
            }
            com.dial.van.connectivity.ProvisioningRecovery.complete(
                payload = payload,
                pairing = {
                    com.dial.van.connectivity.ProvisioningRecovery.Pairing(
                        prefs.getString(KEY_PROVISIONING_FINGERPRINT, null),
                        prefs.getString(KEY_BASE, "").orEmpty(), deviceId.orEmpty(), isPaired(),
                        prefs.getString(KEY_PROVISIONING_DEVICE_ID, null),
                    )
                },
                pair = {
                    pairThisDevice(payload.gatewayUrl, payload.pairingToken, label,
                        com.dial.van.connectivity.ProvisioningRecovery.fingerprint(payload))
                },
                bindingStatus = { deviceBindingStatus() },
                localKeyFingerprint = { deviceIdentity.publicKeyFingerprint() },
                bind = { mayReplace -> bindThisDevice(payload.bootstrapToken, payload.attestationChallenge, mayReplace) },
            )
        } finally {
            provisioningMutex.unlock()
        }
    }

    private fun preparePairing(payload: com.dial.van.connectivity.ProvisioningPayload, label: String):
        com.dial.van.connectivity.ProvisioningRecovery.PreparedPairing {
        val fingerprint = com.dial.van.connectivity.ProvisioningRecovery.fingerprint(payload)
        val existing = prefs.getString(KEY_PENDING_PAIR, null)
        if (existing == null) {
            require(!isPaired()) { "provisioning_existing_identity_mismatch" }
            fun token(): String = Base64.encodeToString(ByteArray(32).also { SecureRandom().nextBytes(it) },
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            val id = "android-${UUID.randomUUID()}"
            val secret = token()
            val body = JSONObject().put("pairing_token", payload.pairingToken.trim()).put("device_id", id)
                .put("device_secret", secret).put("device_access_token", token())
                .put("public_key_pem", approvalKeys.publicKeyPem()).put("label", label)
            check(prefs.edit().putString(KEY_PENDING_PAIR, body.toString()).putString(KEY_BASE, payload.gatewayUrl.trimEnd('/'))
                .putString(KEY_PROVISIONING_FINGERPRINT, fingerprint).putString(KEY_PROVISIONING_DEVICE_ID, id)
                .putString(KEY_DEVICE, id).putString(KEY_SECRET, secret).commit()) { "provisioning_pending_store_failed" }
        }
        require(prefs.getString(KEY_PROVISIONING_FINGERPRINT, null) == fingerprint &&
            prefs.getString(KEY_BASE, null) == payload.gatewayUrl.trimEnd('/')) { "provisioning_pending_identity_mismatch" }
        val body = JSONObject(prefs.getString(KEY_PENDING_PAIR, null) ?: error("provisioning_pending_absent"))
        require(body.getString("device_id") == deviceId && body.getString("device_id") ==
            prefs.getString(KEY_PROVISIONING_DEVICE_ID, null)) { "provisioning_pending_identity_mismatch" }
        return com.dial.van.connectivity.ProvisioningRecovery.PreparedPairing(fingerprint,
            body.getString("device_id"), body.getString("device_access_token"))
    }

    private fun recoverBootstrap(token: String): JSONObject? {
        if (!deviceIdentity.isEnrolled()) return null
        val path = "/v1/devices/bootstrap/recover"
        val payload = JSONObject().put("device_id", deviceId).put("token", token).toString()
        return try {
            postRawAt(baseUrl, path, payload, useIngress = false, freshHeaders = { proofHeaders("POST", path, payload) }).also {
                require(it.optBoolean("bound", false) && it.optString("device_key_fingerprint") ==
                    deviceIdentity.publicKeyFingerprint()) { "provisioning_bound_key_mismatch" }
            }
        } catch (refused: GatewayHttpException) {
            val reason = runCatching { JSONObject(refused.body).optString("detail") }.getOrDefault("")
            if (refused.code == 404 && reason == "bootstrap_not_consumed") null else throw refused
        }
    }

    private fun pairPreparedDevice(gateway: String): JSONObject {
        val body = prefs.getString(KEY_PENDING_PAIR, null) ?: error("provisioning_pending_absent")
        val response = postRawAt(gateway, "/v1/devices/pair", body, useIngress = false,
            freshHeaders = { proofHeaders("POST", "/v1/devices/pair", body) })
        val pending = JSONObject(body)
        require(response.optString("device_id") == pending.getString("device_id") &&
            response.optString("device_access_token") == pending.getString("device_access_token") &&
            response.optString("ingress_token").length >= MIN_INGRESS_TOKEN_CHARS) { "provisioning_pairing_receipt_mismatch" }
        check(prefs.edit().putString(KEY_INGRESS_TOKEN, response.getString("ingress_token"))
            .putString(KEY_DEVICE_ACCESS_TOKEN, response.getString("device_access_token"))
            .remove(KEY_PENDING_PAIR).commit()) { "provisioning_credentials_store_failed" }
        return response
    }

    /**
     * §0D.2 — private, and this is the enforcement.
     *
     * Two screens used to call this with strings the owner had typed: a "Gateway address"
     * field and a "pairing code" field, which are the first and fifth entries on §0D.2's
     * list of what a production build must never expose. Making it private means a new
     * form cannot be added without also removing this comment.
     */
    private suspend fun pairThisDevice(
        gatewayUrl: String,
        pairingToken: String,
        label: String = "android",
        provisioningFingerprint: String,
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
            .putString(KEY_PROVISIONING_FINGERPRINT, provisioningFingerprint)
            .putString(KEY_PROVISIONING_DEVICE_ID, id)
            .commit().also { require(it) { "provisioning_credentials_store_failed" } }
        response.remove("ingress_token")
        response.remove("device_access_token")
        response
    }

    /**
     * P3-OBS-002 — the six measurements only the device can take.
     *
     * Raw body rather than a JSONObject: `DeviceTelemetry.body` builds it, and it is
     * executed in `android/verification` against the shape the route actually parses.
     */
    suspend fun postDeviceTelemetry(body: String): JSONObject = withContext(Dispatchers.IO) {
        postRawAt(baseUrl, "/v1/observability/device-telemetry", body, useIngress = true)
    }

    /**
     * Captured notification/share data is not an owner command.
     *
     * This is deliberately a separate, device-proofed ingress path. Routing captured data
     * through dispatchCommand would sign arbitrary third-party text as OWNER_DEVICE;
     * dropping it in QueueReplayer makes the feature fictional. The gateway stores it as
     * UNTRUSTED_EXTERNAL/NONE authority and never turns this call into executable intent.
     */
    suspend fun ingestCapturedContext(payload: JSONObject): JSONObject =
        withContext(Dispatchers.IO) {
            postProved("/v1/context/ingest", payload)
        }

    suspend fun health(): JSONObject = withContext(Dispatchers.IO) { getJson("/health") }

    suspend fun googleMesh(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/google/mesh") }

    /** Current Workspace connection and revocation state, independent of registry readiness. */
    suspend fun googleStatus(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/google/status") }

    suspend fun googleGmailDraftPreview(draftId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/google/gmail/drafts/${encodeSegment(draftId)}/preview")
    }

    suspend fun briefing(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/briefing") }

    suspend fun tradingTrades(view: String, limit: Int = 12): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/trades?view=${encodeQuery(view)}&limit=$limit")
    }

    /** Worker connection, execution gates and active owner-halt triggers for the overview. */
    suspend fun tradingStatus(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/status") }

    suspend fun tradingTickets(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/tickets") }

    suspend fun tradingPortfolio(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/portfolio") }

    suspend fun tradingAccounts(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/accounts") }

    suspend fun tradingMarketState(symbol: String? = null): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/market-state" + (symbol?.let { "?symbol=${encodeQuery(it)}" } ?: ""))
    }

    suspend fun tradingRisk(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/risk") }

    suspend fun tradingCognition(): String = withContext(Dispatchers.IO) { rawGet("/v1/trading/cognition") }

    suspend fun tradingTradeDetail(tradeIntentId: String): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/trades/${encodeSegment(tradeIntentId)}")
    }

    suspend fun tradingBars(symbol: String, timeframe: String = "H1", limit: Int = 300): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/bars?symbol=${encodeQuery(symbol)}&timeframe=${encodeQuery(timeframe)}&limit=$limit")
    }

    suspend fun tradingPromotionCandidates(): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/strategies/promotion-candidates")
    }

    private fun tradingPromotionBody(
        strategyId: String,
        targetState: String,
        ownerSignatureRef: String,
        certificate: JsonObject,
        evidenceRefs: List<String>,
        issuedAtUnix: Long,
        approvalProof: JsonObject? = null,
    ): JsonObject {
        val id = deviceId ?: error("not_enrolled")
        val secret = deviceSecret ?: error("not_enrolled")
        return StrategyPromotionProtocol.requestBody(
            deviceSecret = secret,
            deviceId = id,
            issuedAtUnix = issuedAtUnix,
            strategyId = strategyId,
            targetState = targetState,
            ownerSignatureRef = ownerSignatureRef,
            certificate = certificate,
            evidenceRefs = evidenceRefs,
            approvalProof = approvalProof,
        )
    }

    suspend fun tradingPromotionChallenge(
        strategyId: String,
        targetState: String,
        ownerSignatureRef: String,
        certificate: JsonObject,
        evidenceRefs: List<String>,
        issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
    ): Pair<Int, String> = withContext(Dispatchers.IO) {
        tradingPromotionPost(
            "/v1/trading/strategies/promotion-challenge",
            tradingPromotionBody(
                strategyId, targetState, ownerSignatureRef,
                certificate, evidenceRefs, issuedAtUnix,
            ),
        )
    }

    suspend fun tradingPromoteStrategy(
        strategyId: String,
        targetState: String,
        ownerSignatureRef: String,
        certificate: JsonObject,
        evidenceRefs: List<String>,
        approvalProof: JsonObject,
        issuedAtUnix: Long = System.currentTimeMillis() / 1000L,
    ): Pair<Int, String> = withContext(Dispatchers.IO) {
        tradingPromotionPost(
            "/v1/trading/strategies/promote",
            tradingPromotionBody(
                strategyId, targetState, ownerSignatureRef,
                certificate, evidenceRefs, issuedAtUnix, approvalProof,
            ),
        )
    }

    private fun tradingPromotionPost(path: String, body: JsonObject): Pair<Int, String> {
        val bodyText = body.toString()
        val conn = open("$baseUrl$path").apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            applyIngressAuth(this)
            proofHeaders("POST", path, bodyText).forEach { (name, value) -> setRequestProperty(name, value) }
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 60_000
        }
        conn.outputStream.use {
            it.write(bodyText.toByteArray(StandardCharsets.UTF_8))
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        return code to (stream?.bufferedReader()?.use { it.readText() } ?: "{}")
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
        val bodyText = body.toString()
        val conn = open("$baseUrl/v1/trading/accounts/action").apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            applyIngressAuth(this)
            proofHeaders("POST", "/v1/trading/accounts/action", bodyText).forEach { (name, value) -> setRequestProperty(name, value) }
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 90_000
        }
        // P0-AND-012 — `requestBody` returns a JsonObject, not a String. This read
        // `body.toByteArray(...)`, which does not exist on JsonObject, so the
        // trading account-action path has never compiled.
        conn.outputStream.use { it.write(bodyText.toByteArray(StandardCharsets.UTF_8)) }
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
        val bodyText = body.toString()
        val conn = open("$baseUrl/v1/trading/accounts/challenge").apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            applyIngressAuth(this)
            proofHeaders("POST", "/v1/trading/accounts/challenge", bodyText).forEach { (name, value) -> setRequestProperty(name, value) }
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        conn.outputStream.use { it.write(bodyText.toByteArray(StandardCharsets.UTF_8)) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        code to (stream?.bufferedReader()?.use { it.readText() } ?: "")
    }

    suspend fun decisions(): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/decisions"))
    }

    suspend fun missionControl(missionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/missions/${encodeSegment(missionId)}/control")
    }
    suspend fun missionControlRequest(missionId: String, requestId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/missions/${encodeSegment(missionId)}/control/requests/${encodeSegment(requestId)}")
    }
    suspend fun writeMissionControl(missionId: String, operation: String, exactRequest: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        val route = when (operation) { "PAUSE" -> "pause"; "RESUME" -> "resume"; "DIRECTION" -> "direction"; else -> error("mission_control_operation_invalid") }
        postJson("/v1/missions/${encodeSegment(missionId)}/$route", exactRequest)
    }

    suspend fun decision(decisionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/decisions/${encodeSegment(decisionId)}")
    }

    /** The immutable request ID/body permits exact recovery; an answer is not action approval. */
    suspend fun answerDecision(decisionId: String, exactRequest: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/decisions/${encodeSegment(decisionId)}/answer", exactRequest)
    }

    suspend fun resolveDecision(decisionId: String, approved: Boolean): JSONObject = withContext(Dispatchers.IO) {
        postJson(
            "/v1/decisions/${encodeSegment(decisionId)}/resolve",
            JSONObject().put("approved", approved),
        )
    }

    suspend fun projects(): JSONArray = withContext(Dispatchers.IO) {
        getJson("/v1/projects").getJSONArray("projects")
    }

    suspend fun projectTruth(projectId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/projects/${encodeSegment(projectId)}/truth")
    }

    suspend fun attention(): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/attention"))
    }

    /** POST /v1/attention/{id}/ack — the Attention screen's swipe-to-acknowledge. */
    suspend fun attentionAck(itemId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/attention/${encodeSegment(itemId)}/ack", JSONObject())
    }

    /** POST /v1/attention/{id}/snooze — durable owner attention suppression. */
    suspend fun attentionSnooze(itemId: String, untilUnix: Long): JSONObject = withContext(Dispatchers.IO) {
        postJson(
            "/v1/attention/${encodeSegment(itemId)}/snooze",
            JSONObject().put("until_unix", untilUnix),
        )
    }

    /**
     * Mint a short-lived, owner-device-bound ARTEMIS web-console launch.
     *
     * The Netcup ARTEMIS bearer token never reaches Android. This POST is protected by
     * VAN ingress auth, the device access token, and the hardware device proof; the
     * returned one-use URL exchanges into an HttpOnly same-origin Gateway cookie.
     */
    suspend fun artemisConsoleSession(): JSONObject = withContext(Dispatchers.IO) {
        postProved("/v1/artemis/console/session", JSONObject())
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

    suspend fun browserActionPlans(sessionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/browser/interactive-sessions/${encodeSegment(sessionId)}/action-plans")
    }
    suspend fun browserActionPlan(sessionId: String, planId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/browser/interactive-sessions/${encodeSegment(sessionId)}/action-plans/${encodeSegment(planId)}")
    }
    suspend fun createBrowserActionPlan(sessionId: String, exactDraft: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/browser/interactive-sessions/${encodeSegment(sessionId)}/action-plans", exactDraft)
    }
    suspend fun cancelBrowserActionPlan(sessionId: String, planId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/browser/interactive-sessions/${encodeSegment(sessionId)}/action-plans/${encodeSegment(planId)}/cancel", JSONObject())
    }

    // ------------------------------------------------- interactive browser (Rev 1.5 §6)
    //
    // The owner's phone owns these: it creates the session, heartbeats it, hands control
    // to Hermes and takes it back. Every mutation carries a device proof (ADR-RB-025).
    //
    // Deliberately absent: a "navigate to this URL" call. Navigation is an actuation and
    // is fenced by the control lease on the stream host, not by an authenticated REST
    // call — a gateway route that navigated would be a second actuation path with a
    // different authority, which §6.1 exists to prevent.

    suspend fun interactiveBrowserCreate(
        profileAlias: String,
        widthPx: Int,
        heightPx: Int,
        deviceScaleFactor: Float,
        maxFps: Int = 60,
        missionId: String? = null,
        idempotencyKey: String? = null,
    ): BrowserSessionSnapshot = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("profile_alias", profileAlias)
            .put(
                "viewport",
                JSONObject()
                    .put("width", widthPx)
                    .put("height", heightPx)
                    .put("device_scale_factor", deviceScaleFactor.toDouble()),
            )
            .put("media", JSONObject().put("max_fps", maxFps))
        missionId?.let { body.put("mission_id", it) }
        idempotencyKey?.let { body.put("idempotency_key", it) }
        BrowserParsing.session(postProved(INTERACTIVE_SESSIONS, body))
    }

    suspend fun interactiveBrowserRead(sessionId: String): BrowserSessionSnapshot =
        withContext(Dispatchers.IO) {
            BrowserParsing.session(getJson("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}"))
        }

    suspend fun interactiveBrowserStreamGrant(sessionId: String): BrowserStreamGrant =
        withContext(Dispatchers.IO) {
            admitBrowserGrant(BrowserParsing.streamGrant(
                postProved(
                    "$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/stream-grant",
                    JSONObject(),
                ),
            ))
        }

    suspend fun interactiveBrowserTakeControl(sessionId: String): JSONObject =
        withContext(Dispatchers.IO) {
            postProved(
                "$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/take-control", JSONObject(),
            )
        }

    suspend fun interactiveBrowserDelegateControl(
        sessionId: String,
        holder: String,
        issuedFor: String,
    ): JSONObject = withContext(Dispatchers.IO) {
        postProved(
            "$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/delegate-control",
            JSONObject().put("holder", holder).put("issued_for", issuedFor),
        )
    }

    suspend fun interactiveBrowserHeartbeat(sessionId: String): BrowserSessionSnapshot =
        withContext(Dispatchers.IO) {
            BrowserParsing.session(
                postProved(
                    "$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/heartbeat", JSONObject(),
                ),
            )
        }

    suspend fun interactiveBrowserProposeViewport(
        sessionId: String,
        widthPx: Int,
        heightPx: Int,
        deviceScaleFactor: Float,
    ): Int = withContext(Dispatchers.IO) {
        postProved(
            "$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/viewport",
            JSONObject()
                .put("width", widthPx)
                .put("height", heightPx)
                .put("device_scale_factor", deviceScaleFactor.toDouble()),
        ).getInt("viewport_revision")
    }

    /**
     * §8.6 — the device confirms it is drawing the new size.
     *
     * Actuation is withheld between the proposal and this call, because a tap mapped
     * through the old viewport lands somewhere the owner did not touch.
     */
    suspend fun interactiveBrowserAckViewport(sessionId: String, revision: Int,
        frameSequence: Long? = null, mediaEpoch: String? = null): JSONObject =
        withContext(Dispatchers.IO) {
            require((frameSequence == null) == (mediaEpoch == null)) { "browser_frame_proof_incomplete" }
            val body = JSONObject().put("revision", revision)
            frameSequence?.let { require(it > 0); body.put("frame_sequence", it) }
            mediaEpoch?.let { require(it.isNotBlank()); body.put("media_epoch", it) }
            postProved(
                "$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/viewport/ack",
                body,
            )
        }

    suspend fun interactiveBrowserSuspend(sessionId: String): BrowserSessionSnapshot =
        withContext(Dispatchers.IO) {
            BrowserParsing.session(
                postProved(
                    "$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/suspend", JSONObject(),
                ),
            )
        }

    suspend fun interactiveBrowserEnd(sessionId: String): BrowserSessionSnapshot =
        withContext(Dispatchers.IO) {
            BrowserParsing.session(
                deleteProved("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}"),
            )
        }

    suspend fun interactiveBrowserResume(sessionId: String): BrowserSessionSnapshot =
        withContext(Dispatchers.IO) {
            BrowserParsing.session(postProved("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/resume", JSONObject()))
        }

    suspend fun interactiveBrowserTabs(sessionId: String): JSONArray =
        withContext(Dispatchers.IO) {
            val response = getJson("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/tabs")
            require(response.optString("session_id") == sessionId) { "browser_tabs_session_mismatch" }
            response.getJSONArray("tabs")
        }

    suspend fun interactiveBrowserDownloads(sessionId: String): JSONArray =
        withContext(Dispatchers.IO) {
            val response = getJson("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/downloads")
            require(response.optString("session_id") == sessionId) { "browser_download_session_mismatch" }
            response.getJSONArray("downloads")
        }

    suspend fun browserFileOperations(sessionId: String, downloadId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/browser/interactive-sessions/${encodeSegment(sessionId)}/downloads/${encodeSegment(downloadId)}/operations")
    }

    suspend fun browserFileProviderContracts(sessionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/browser/interactive-sessions/${encodeSegment(sessionId)}/file-provider-contracts")
    }

    /** Drafting and readback only. Provider writes require the canonical exact A4 command. */
    suspend fun browserFileProviderRequests(sessionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/file-provider-requests")
    }
    suspend fun browserFileProviderRequest(sessionId: String, requestId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/file-provider-requests/${encodeSegment(requestId)}")
    }
    /** Explicit read-only observation; never creates a claim, write, or replacement authority. */
    suspend fun browserFileProviderObservation(sessionId: String, requestId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/file-provider-requests/${encodeSegment(requestId)}/observation")
    }
    suspend fun createBrowserFileProviderRequest(sessionId: String, exactDraft: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        postProved("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/file-provider-requests", exactDraft)
    }
    suspend fun cancelBrowserFileProviderRequest(sessionId: String, requestId: String): JSONObject = withContext(Dispatchers.IO) {
        postProved("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/file-provider-requests/${encodeSegment(requestId)}/cancel", JSONObject())
    }

    suspend fun automationPlanRequest(key: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/automation/requests/${encodeSegment(key)}")
    }

    suspend fun interactiveBrowserTransferGrant(sessionId: String, request: JSONObject): JSONObject =
        withContext(Dispatchers.IO) {
            postProved("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/transfer-grants", request)
        }

    suspend fun interactiveBrowserDeleteDownload(sessionId: String, downloadId: String): JSONObject =
        withContext(Dispatchers.IO) {
            deleteProved("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/downloads/${encodeSegment(downloadId)}")
        }

    suspend fun interactiveBrowserEvents(sessionId: String): JSONArray =
        withContext(Dispatchers.IO) {
            val response = getJson("$INTERACTIVE_SESSIONS/${encodeSegment(sessionId)}/events")
            require(response.optString("session_id") == sessionId) { "browser_events_session_mismatch" }
            response.getJSONArray("events")
        }

    // ------------------------------------------------ durable session (Rev 1.5 §20)

    /** This device's id, or empty when it has not paired. Used to address envelopes. */
    fun deviceIdOrEmpty(): String = deviceId ?: ""

    suspend fun sessionOpen(
        pathId: String,
        routeId: String,
        protocol: String = "WSS",
        pathClass: String = "A_REALTIME",
    ): JSONObject = withContext(Dispatchers.IO) {
        sessionOpenMutex.lock()
        try {
            var prepared = prefs.getString(KEY_PENDING_SESSION_OPEN, null)
            if (prepared == null) {
                prepared = JSONObject().put("open_request_id", UUID.randomUUID().toString())
                    .put("path_id", pathId).put("route_id", routeId).put("protocol", protocol)
                    .put("path_class", pathClass).toString()
                check(prefs.edit().putString(KEY_PENDING_SESSION_OPEN, prepared).commit()) { "session_open_store_failed" }
            }
            val path = "$SESSION_PREFIX/open"
            val exactBody = prepared
            val answer = try {
                postRawAt(baseUrl, path, exactBody, useIngress = true,
                    freshHeaders = { proofHeaders("POST", path, exactBody) })
            } catch (refused: GatewayHttpException) {
                if (refused.code != 409) throw refused
                throw SessionOpenRecoveryException(runCatching { JSONObject(refused.body).optString("detail") }
                    .getOrDefault("session_open_refused").ifBlank { "session_open_refused" })
            }
            val requestId = JSONObject(exactBody).getString("open_request_id")
            if (answer.optString("open_request_id") != requestId || answer.optString("van_session_id").isBlank()) {
                throw SessionOpenRecoveryException("session_open_identity_contract_missing")
            }
            storeSessionIdentity(answer.getString("van_session_id"), answer.getInt("session_epoch"), answer.getInt("path_epoch"), clearOpen = true)
            answer
        } finally { sessionOpenMutex.unlock() }
    }

    fun restoredSessionIdentity(): JSONObject? = prefs.getString(KEY_SESSION_IDENTITY, null)?.let { raw ->
        val identity = JSONObject(raw)
        require(identity.getString("device_id") == deviceId) { "session_identity_device_mismatch" }
        identity
    }

    private fun storeSessionIdentity(id: String, epoch: Int, pathEpoch: Int, clearOpen: Boolean = false) {
        val identity = JSONObject().put("device_id", deviceId).put("van_session_id", id)
            .put("session_epoch", epoch).put("path_epoch", pathEpoch)
        val edit = prefs.edit().putString(KEY_SESSION_IDENTITY, identity.toString())
        if (clearOpen) edit.remove(KEY_PENDING_SESSION_OPEN)
        check(edit.commit()) { "session_identity_store_failed" }
    }

    /**
     * §20.10 step 4 — reconcile against the Gateway's own account of this session.
     *
     * A refused resume comes back as `{"refusal": ...}` rather than an exception, because
     * a refusal is an answer: the caller has to open a new session, which is a different
     * action from retrying. Throwing here would put that decision in a catch block.
     */
    suspend fun sessionResume(
        vanSessionId: String,
        sessionEpoch: Int,
        lastEventSeq: Long,
        pendingCommandIds: List<String>,
        pathId: String,
        routeId: String,
        pathClass: String = "A_REALTIME",
    ): JSONObject = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("van_session_id", vanSessionId)
            .put("session_epoch", sessionEpoch)
            .put("last_event_seq", lastEventSeq)
            .put("pending_command_ids", JSONArray(pendingCommandIds))
            .put("path_id", pathId)
            .put("route_id", routeId)
            .put("path_class", pathClass)
        try {
            postProved("$SESSION_PREFIX/resume", body).also { response ->
                if (response.optBoolean("accepted", false)) storeSessionIdentity(vanSessionId,
                    response.getInt("session_epoch"), response.getInt("new_path_epoch"))
            }
        } catch (refused: GatewayHttpException) {
            if (refused.code != 409 && refused.code != 404) throw refused
            val response = JSONObject().put(
                "refusal",
                runCatching { JSONObject(refused.body).optString("detail") }
                    .getOrDefault("session_resume_refused")
                    .ifBlank { "session_resume_refused" },
            )
            if (response.optString("refusal") == "session_unknown") {
                check(prefs.edit().remove(KEY_SESSION_IDENTITY).commit()) { "session_identity_clear_failed" }
            }
            response
        }
    }

    suspend fun sessionStatus(vanSessionId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("$SESSION_PREFIX/status?van_session_id=${encodeQuery(vanSessionId)}")
    }

    suspend fun sessionUpstream(envelope: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        try { postProved("$SESSION_PREFIX/messages", envelope) }
        catch (refused: GatewayHttpException) {
            if (refused.code != 400 && refused.code != 409) throw refused
            JSONObject().put("accepted", false).put("kind", envelope.optString("kind"))
                .put("refusal", runCatching { JSONObject(refused.body).optString("detail") }.getOrDefault("session_refused"))
        }
    }

    /** Emits an admission marker first, then the gateway's unchanged durable event records. */
    fun sessionDownstream(vanSessionId: String, afterSeq: Long): Flow<JSONObject> = callbackFlow {
        val path = "$SESSION_PREFIX/events-stream"
        val connection = open("$baseUrl$path?van_session_id=${encodeQuery(vanSessionId)}&after_seq=$afterSeq")
        val reader = launch(Dispatchers.IO) {
            try {
                connection.requestMethod = "GET"
                applyIngressAuth(connection)
                proofHeaders("GET", path, "").forEach { (name, value) -> connection.setRequestProperty(name, value) }
                connection.setRequestProperty("Accept", "text/event-stream")
                connection.connectTimeout = 15_000
                connection.readTimeout = 60_000
                val code = connection.responseCode
                if (code !in 200..299) throw GatewayHttpException(code,
                    connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty())
                send(JSONObject())
                val parser = com.dial.van.session.SessionSseFrames.Parser()
                connection.inputStream.bufferedReader().use { lines ->
                    while (true) { val line = lines.readLine() ?: break; parser.feed(line)?.let { send(it) } }
                }
                close()
            } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
            catch (failure: Exception) { close(failure) }
        }
        awaitClose { connection.disconnect(); reader.cancel() }
    }

    /**
     * The full-duplex endpoint, with its credentials in the query string.
     *
     * HTTP middleware does not run for a WebSocket handshake, so the socket authenticates
     * itself. This revocable token is scoped to one device; the hardware proof is carried
     * separately in [sessionSocketHeaders].
     */
    fun sessionSocketUrl(vanSessionId: String): String {
        val root = baseUrl
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://")
        val token = deviceAccessToken?.takeIf { it.isNotBlank() } ?: error("device_access_token_unconfigured")
        val endpoint = signedRouting?.sessionUrl ?: "$root$SESSION_PREFIX/ws"
        return "$endpoint?van_session_id=${encodeQuery(vanSessionId)}" +
            "&device_token=${encodeQuery(token)}"
    }

    /** Hardware proof for the handshake; query credentials are authenticated separately. */
    fun sessionSocketHeaders(): Map<String, String> = proofHeaders("GET", "$SESSION_PREFIX/ws", "")

    // --------------------------------------------------- signed connectivity (ADR-RB-027)

    suspend fun connectivityManifest(knownVersion: Int): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/connectivity/manifest?known_version=$knownVersion")
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

    suspend fun ownerVocabulary(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/understanding/vocabulary")
    }

    suspend fun saveOwnerVocabulary(definition: com.dial.van.memory.OwnerVocabularyDefinition,
                                  sessionId: String, sessionEpoch: Int): JSONObject = withContext(Dispatchers.IO) {
        require(sessionId.isNotBlank() && sessionEpoch > 0) { "Reconnect the owner session before saving." }
        val path = "/v1/understanding/vocabulary"
        val saved = putProved(path, definition.content().put("van_session_id", sessionId).put("session_epoch", sessionEpoch))
        val scope = definition.projectId?.let { "&project_id=${encodeQuery(it)}" }.orEmpty()
        val observed = getJson("$path?term=${encodeQuery(definition.term)}$scope")
        com.dial.van.memory.verifyOwnerMemoryReadback(saved, observed)
        definition.verifyEntry(observed.getJSONObject("entry"))
        observed
    }

    suspend fun ownerCollaborationPreferences(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/understanding/complement/preferences")
    }

    suspend fun saveOwnerCollaborationPreference(preference: com.dial.van.memory.OwnerCollaborationPreference,
                                               sessionId: String, sessionEpoch: Int): JSONObject = withContext(Dispatchers.IO) {
        require(sessionId.isNotBlank() && sessionEpoch > 0) { "Reconnect the owner session before saving." }
        val path = "/v1/understanding/complement/preferences"
        val saved = putProved(path, preference.content().put("van_session_id", sessionId).put("session_epoch", sessionEpoch))
        val observed = getJson("$path?domain=${encodeQuery(preference.domain)}")
        com.dial.van.memory.verifyOwnerMemoryReadback(saved, observed)
        preference.verifyEntry(observed.getJSONObject("entry"))
        observed
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
    suspend fun permissionContracts(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/permissions/contracts") }
    suspend fun permissionGrant(grantId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/permissions/grants/${encodeSegment(grantId)}")
    }

    suspend fun revokePermission(grantId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/permissions/${encodeSegment(grantId)}/revoke", JSONObject())
    }

    suspend fun autonomy(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/autonomy") }

    suspend fun standingIntents(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/understanding/intents") }
    suspend fun decisionHistory(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/understanding/decisions") }
    suspend fun learnedStrategies(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/strategies") }
    suspend fun externalReality(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/external-reality") }
    suspend fun learningProducers(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/understanding/learning/producers") }
    suspend fun authorityDescriptor(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/authority") }

    suspend fun ownerKnowledge(limit: Int = 30): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/knowledge?limit=${limit.coerceIn(1, 100)}")
    }
    suspend fun ownerResearch(limit: Int = 30): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/research?limit=${limit.coerceIn(1, 100)}")
    }
    suspend fun ownerAutomation(limit: Int = 30): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/automation?limit=${limit.coerceIn(1, 100)}")
    }
    suspend fun automationContracts(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/owner/automation/contracts") }
    suspend fun proposeAutomationPlan(exactRequest: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/owner/automation/plans", exactRequest)
    }
    suspend fun automationPlans(limit: Int = 30): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/automation/plans?limit=${limit.coerceIn(1, 100)}")
    }
    suspend fun automationPlan(artifactId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/automation/plans/${encodeSegment(artifactId)}")
    }
    suspend fun automationRun(runId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/automation/runs/${encodeSegment(runId)}")
    }
    suspend fun ownerDiagnostics(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/owner/diagnostics") }
    suspend fun ownerBrowserOutcome(taskId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/owner/browser/tasks/${encodeSegment(taskId)}/outcome")
    }

    suspend fun technologyRadar(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/technology-radar")
    }

    /** §41 — the scoreboard, including every dimension VAN cannot yet measure. */
    suspend fun evalReport(): JSONObject = withContext(Dispatchers.IO) { getJson("/v1/eval") }

    suspend fun projectStrategicMemory(projectId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/projects/${encodeSegment(projectId)}/strategic-memory")
    }

    suspend fun recordProjectRationale(
        projectId: String,
        entryType: com.dial.van.projects.ProjectRationaleType,
        statement: String,
        rationale: String?,
        evidenceRefs: List<String>,
    ): JSONObject = withContext(Dispatchers.IO) {
        require(projectId.isNotBlank() && statement.isNotBlank()) { "project_rationale_required" }
        postProved("/v1/projects/${encodeSegment(projectId)}/strategic-memory", JSONObject()
            .put("entry_type", entryType.name).put("statement", statement.trim())
            .put("rationale", rationale?.trim()?.takeIf { it.isNotBlank() } ?: JSONObject.NULL)
            .put("evidence_refs", JSONArray(evidenceRefs.filter { it.isNotBlank() }.distinct())))
    }

    // ---------------------------------------------------------------- owner memory (Memory)
    //
    // DNA §4's Memory destination: facts, decisions, assumptions, preferences, unresolved
    // threads, provenance; add/correct/forget. Every write below is device-proofed like
    // ingest, because a canonical fact about the owner can only come from the owner
    // (backend/van_gateway/app.py's own reasoning for POST /v1/context/facts).

    /** GET /v1/context/memory — what VAN holds about the owner, store by store. */
    suspend fun contextMemory(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/context/memory")
    }

    suspend fun contextRecords(store: String, limit: Int = 50, cursor: Int = 0): JSONObject = withContext(Dispatchers.IO) {
        require(cursor in 0..1_000_000) { "memory_record_pagination_invalid" }
        getJson("/v1/context/records?store=${encodeSegment(store)}&limit=${limit.coerceIn(1, 100)}&cursor=$cursor")
    }

    suspend fun contextRecord(store: String, recordId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/context/records/${encodeSegment(store)}/${encodeSegment(recordId)}")
    }

    suspend fun exportContextRecord(store: String, recordId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/context/records/${encodeSegment(store)}/${encodeSegment(recordId)}/export")
    }

    suspend fun contextRecordErasurePlan(store: String, recordId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/context/records/${encodeSegment(store)}/${encodeSegment(recordId)}/erasure-plan")
    }

    suspend fun eraseContextMemory(store: String? = null): JSONObject = withContext(Dispatchers.IO) {
        deleteProved("/v1/context/memory" + (store?.let { "?store=${encodeQuery(it)}" } ?: ""))
    }

    /**
     * GET /v1/context/export — everything VAN holds about the owner, not a count of it
     * (`app.py`'s own distinction: `/v1/context/memory` says how many facts exist,
     * `/v1/context/export` is what they say — `stores.owner_facts.records[]`, each a full
     * `OwnerFactRecord`).
     */
    suspend fun contextExport(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/context/export")
    }

    /** GET /v1/context/conflicts — what VAN holds two contradictory answers to. */
    suspend fun contextConflicts(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/context/conflicts")
    }

    /** GET /v1/context/history?subject&predicate&scope — what VAN believed before. */
    suspend fun contextHistory(
        subject: String,
        predicate: String,
        scope: String = "global",
    ): JSONObject = withContext(Dispatchers.IO) {
        getJson(
            "/v1/context/history?subject=${encodeQuery(subject)}" +
                "&predicate=${encodeQuery(predicate)}&scope=${encodeQuery(scope)}",
        )
    }

    /**
     * POST /v1/context/facts — the owner stating something about themselves, at
     * CANONICAL_OWNER. Device-proofed: the gateway requires the caller's device identity
     * (`app.py`'s `state_owner_fact`) and refuses without it.
     */
    suspend fun stateOwnerFact(
        subject: String,
        predicate: String,
        value: String,
        scope: String = "global",
    ): JSONObject = withContext(Dispatchers.IO) {
        postProved(
            "/v1/context/facts",
            JSONObject()
                .put("subject", subject)
                .put("predicate", predicate)
                .put("value", value)
                .put("scope", scope),
        )
    }

    /**
     * DELETE /v1/context/facts?subject&predicate&scope — the owner's own way to end a fact
     * they stated. The gateway route takes the fact's identity (subject/predicate/scope),
     * not an opaque id (`app.py`'s `forget_owner_fact`), so that is what this takes too.
     */
    suspend fun forgetOwnerFact(
        subject: String,
        predicate: String,
        scope: String = "global",
    ): JSONObject = withContext(Dispatchers.IO) {
        deleteProved(
            "/v1/context/facts?subject=${encodeQuery(subject)}" +
                "&predicate=${encodeQuery(predicate)}&scope=${encodeQuery(scope)}",
        )
    }

    // -------------------------------------------------------------------------- reminders

    /** GET /v1/reminders — the owner's open reminders (Home's "Upcoming"). */
    suspend fun reminders(): JSONArray = withContext(Dispatchers.IO) {
        JSONArray(rawGet("/v1/reminders"))
    }

    /**
     * POST /v1/reminders — `text` plus a due expression, resolved gateway-side. Mirrors
     * `ReminderParseBody`'s shape (`app.py`'s `/v1/reminders/parse`, the richer of the two
     * creation routes) so the same call parses "tomorrow at 9" the owner typed.
     */
    suspend fun createReminder(text: String, dueExpression: String, idempotencyKey: String): JSONObject =
        withContext(Dispatchers.IO) {
            postJson(
                "/v1/reminders/parse",
                JSONObject().put("text", text).put("due_expression", dueExpression)
                    .put("idempotency_key", idempotencyKey),
            )
        }

    suspend fun resolveReminder(reminderId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/reminders/${encodeSegment(reminderId)}/resolve", JSONObject())
    }

    suspend fun cancelReminder(reminderId: String): JSONObject = withContext(Dispatchers.IO) {
        postJson("/v1/reminders/${encodeSegment(reminderId)}/cancel", JSONObject())
    }

    // --------------------------------------------------------------- Character Forge

    /** M4: device-proofed, biometric owner acceptance for the exact installed Rive SHA. */
    suspend fun recordVisualAcceptance(
        token: String,
        riveSha256: String,
        apkSha256: String,
        deviceModel: String,
        androidBuild: String,
    ): JSONObject = withContext(Dispatchers.IO) {
        postProved(
            "/v1/visual/acceptance",
            JSONObject()
                .put("token", token)
                .put("rive_sha256", riveSha256)
                .put("apk_sha256", apkSha256)
                .put("device_model", deviceModel)
                .put("android_build", androidBuild),
        )
    }

    suspend fun latestVisualAcceptance(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/visual/acceptance")
    }

    // --------------------------------------------------------------------------- degraded

    /** GET /v1/degraded — the gateway's own degraded snapshot (GAP-F-010). */
    suspend fun degraded(): JSONObject = withContext(Dispatchers.IO) {
        // The route returns a bare JSON array of DegradedCapability, matching `/health`'s
        // own `degraded` field — wrapped here so callers get the one shape
        // `GatewayDegradedMapping.parse` already reads off `/health`.
        JSONObject().put("degraded", JSONArray(rawGet("/v1/degraded")))
    }

    // ------------------------------------------------------- DIAL development projection

    /**
     * VAN-DEVCC-R1 §3.4 — the DIAL Development Projection, read through VAN's own gateway.
     *
     * Android never calls DIAL: every path here is under [DIAL_DEV_PREFIX] on VAN's gateway,
     * authenticated like every other owner read (ingress + device token), and the gateway
     * holds the DIAL-scoped credential in a token file that never reaches this phone. Reads
     * return the raw envelope body (`com.dial.van.dialdev.DialDevEnvelope.parse` owns it);
     * the one mutation, [DialDevClient.submitAction], goes through [postProved] like every
     * other owner mutation.
     */
    val dialDev: DialDevClient by lazy { DialDevClient() }

    inner class DialDevClient {
        suspend fun projects(): String = read("/projects")

        suspend fun home(projectId: String): String = read("/projects/${encodeSegment(projectId)}/home")

        suspend fun stagePlan(projectId: String): String = read("/projects/${encodeSegment(projectId)}/stage-plan")

        suspend fun tasks(projectId: String, view: String): String =
            read("/projects/${encodeSegment(projectId)}/tasks?view=${encodeQuery(view)}")

        suspend fun graph(projectId: String): String = read("/projects/${encodeSegment(projectId)}/graph")

        suspend fun task(taskId: String): String = read("/tasks/${encodeSegment(taskId)}")

        suspend fun agents(): String = read("/agents")

        suspend fun workspaces(): String = read("/workspaces")

        suspend fun workspace(workspaceId: String): String = read("/workspaces/${encodeSegment(workspaceId)}")

        suspend fun workspaceDiff(workspaceId: String): String = read("/workspaces/${encodeSegment(workspaceId)}/diff")

        /** Read-only and bounded: DIAL serves at most 200 secret-screened lines (§3.2). */
        suspend fun workspaceTerminalTail(workspaceId: String, lines: Int = 200): String =
            read("/workspaces/${encodeSegment(workspaceId)}/terminal-tail?lines=${lines.coerceIn(1, 200)}")

        /** The six hub children that are one read each (§6.7–§6.9). */
        suspend fun section(section: HubSection): String = read("/${section.path}")

        suspend fun evidence(ref: String): String = read("/evidence/${encodeSegment(ref)}")

        suspend fun infrastructure(): String = read("/infrastructure")

        /**
         * `POST /v1/dial-dev/actions` — device-proofed. Returns the 202 body; a 409
         * `STALE_VIEW` or any refusal surfaces as [GatewayHttpException] for the caller's
         * `DialDevActionReducer.onResponse`.
         */
        suspend fun submitAction(request: DialDevActionRequest): JSONObject = withContext(Dispatchers.IO) {
            postProved("$DIAL_DEV_PREFIX/actions", request.toJson())
        }

        /**
         * `GET /v1/dial-dev/events` as a stream of `{projection_revision, changed[]}` so a screen
         * refetches only what changed. The connection is closed when the collector cancels.
         * Screens also poll at their stale threshold, so a dropped stream costs latency, not truth.
         */
        fun events(): Flow<DialDevChange> = callbackFlow {
            val connection = open("$baseUrl$DIAL_DEV_PREFIX/events")
            val reader = launch(Dispatchers.IO) {
                try {
                    connection.requestMethod = "GET"
                    applyIngressAuth(connection)
                    connection.setRequestProperty("Accept", "text/event-stream")
                    connection.connectTimeout = 15_000
                    connection.readTimeout = 90_000
                    val code = connection.responseCode
                    if (code !in 200..299) {
                        throw GatewayHttpException(code, connection.errorStream?.bufferedReader()?.use { it.readText() } ?: "")
                    }
                    val parser = DialDevSse.Parser()
                    connection.inputStream.bufferedReader().use { lines ->
                        while (true) {
                            val line = lines.readLine() ?: break
                            parser.feed(line)?.let { send(it) }
                        }
                    }
                    close()
                } catch (exc: Throwable) {
                    close(exc)
                }
            }
            awaitClose {
                runCatching { connection.disconnect() }
                reader.cancel()
            }
        }

        private suspend fun read(path: String): String = withContext(Dispatchers.IO) { rawGet("$DIAL_DEV_PREFIX$path") }
    }

    /** §6.7–§6.9 hub children served by one `GET /v1/dial-dev/{path}` each. */
    enum class HubSection(val path: String) {
        REVIEWS("reviews"),
        MEMORY("memory"),
        RESEARCH("research"),
        DESIGN("design"),
        CI("ci"),
        SECURITY("security"),
    }

    // ---------------------------------------------------------------------- command status

    /** GET /v1/commands/{id} — GAP-F-011: what became of a dispatched command. */
    suspend fun commandStatus(commandId: String): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/commands/${encodeSegment(commandId)}")
    }

    // ------------------------------------------------------------------------------ Google

    /** GET /v1/google/planes — the four Google credentials, reported one by one. */
    suspend fun googlePlanes(): JSONObject = withContext(Dispatchers.IO) {
        getJson("/v1/google/planes")
    }

    /**
     * POST /v1/google/owner-revoke — the owner cutting Google from the phone. Device-proofed
     * like every other owner mutation (GAP-F-024); `google.revoke()` + `google.status()` is
     * the whole of the route's own effect, so nothing further is required in the body.
     */
    suspend fun googleOwnerRevoke(): JSONObject = withContext(Dispatchers.IO) {
        postProved("/v1/google/owner-revoke", JSONObject())
    }

    // ---------------------------------------------------------------- trading (read-only)
    //
    // DNA §4's Trading destination and Home's "Significant trade state" panel. Raw response
    // bodies, like the rest of this client's `tradingTrades`/`tradingPortfolio` family —
    // `trading/TradingFormat` and the trading worker's own read models own parsing them.
    // These five routes are not present in `backend/van_gateway/app.py` as of this change
    // (only `/v1/trading/{status,trades,portfolio,accounts,market-state,risk,cognition,
    // trades/{id},bars,tickets,halt,...}` exist there today); see this worker's final report
    // for what `tests/contracts/test_android_gateway_routes_match.py` says about them.

    suspend fun tradingAssessment(): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/assessment")
    }

    suspend fun tradingPositions(): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/positions")
    }

    suspend fun tradingEvents(limit: Int = 20): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/events?limit=$limit")
    }

    suspend fun tradingPotential(): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/potential")
    }

    suspend fun tradingHistory(limit: Int = 50): String = withContext(Dispatchers.IO) {
        rawGet("/v1/trading/history?limit=$limit")
    }

    suspend fun events(afterSeq: Long = 0L): JSONObject = withContext(Dispatchers.IO) {
        val id = deviceId ?: error("not_enrolled")
        getJson("/v1/events?device_id=${encodeQuery(id)}&after_seq=$afterSeq")
    }

    /**
     * Rev 3.1 signed owner-intent envelope. Authority-bearing provenance fields are HMAC-covered
     * by signature v3. v3 extends v2 with fixed-point speaker evidence; pairing/device-access
     * authentication remains mandatory on the transport.
     */
    /**
     * §20.14 — the signed command body, built once and usable twice.
     *
     * Extracted from [dispatchCommand] because a command that could not be sent has to be
     * *stored*, and storing "text plus an action class" stores something the Gateway
     * cannot accept: `CommandRequest` requires `command_id`, `issued_at_unix` and
     * `signature`, so a payload without them is refused as `command_payload_invalid` when
     * the outbox finally flushes it. The owner would be told their work was saved and it
     * would be rejected on their behalf hours later, which is a worse failure than losing
     * it outright because nothing looks wrong until it is too late to redo.
     *
     * The signature covers `issued_at_unix`, so a stored body carries the moment the
     * owner issued it rather than the moment it was sent — which is what makes the
     * Gateway's own `owner_intent_max_age_seconds` the right rule for refusing it, rather
     * than a re-signing here that would make every stored command look fresh.
     */
    fun buildCommandBody(
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
        speakerEvidenceMilli: Int? = null,
        contextCapsuleRevision: Int? = null,
        contextCapsuleHash: String? = null,
        declaredTrust: String = TRUST_CONVERSATION,
        clientContext: Map<String, String> = emptyMap(),
    ): JSONObject {
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
        require(speakerEvidenceMilli == null || speakerEvidenceMilli in 0..1000) {
            "speaker_evidence_milli_out_of_range"
        }
        val canonical = listOf(
            "v3",
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
            speakerEvidenceMilli?.toString() ?: "",
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
            .put("signature_version", 3)
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
        if (speakerEvidenceMilli != null) body.put("speaker_evidence_milli", speakerEvidenceMilli)
        if (contextCapsuleRevision != null) body.put("context_capsule_revision", contextCapsuleRevision)
        if (contextCapsuleHash != null) body.put("context_capsule_hash", contextCapsuleHash)
        // GAP-F-005 — `CommandRequest.client_context`: read by the gateway's typed-action
        // executors (e.g. `owner_halt_authority_ref`). Outside the v3 HMAC canonical on both
        // sides by design: each value is a separately signed credential the gateway verifies
        // itself, so the device's HMAC adds nothing to it.
        if (clientContext.isNotEmpty()) {
            val context = JSONObject()
            for ((key, value) in clientContext) context.put(key, value)
            body.put("client_context", context)
        }

        return body
    }

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
        speakerEvidenceMilli: Int? = null,
        contextCapsuleRevision: Int? = null,
        contextCapsuleHash: String? = null,
        declaredTrust: String = TRUST_CONVERSATION,
        clientContext: Map<String, String> = emptyMap(),
        /** The exact signed bytes that must be retained if the HTTP result is lost. */
        onPreparedCommand: (String) -> Unit = {},
    ): JSONObject = withContext(Dispatchers.IO) {
        val body = buildCommandBody(
            text = text,
            actionClass = actionClass,
            projectId = projectId,
            idempotencyKey = idempotencyKey,
            approvalToken = approvalToken,
            approvalChallengeId = approvalChallengeId,
            approvalSignatureBase64 = approvalSignatureBase64,
            approvalAlgorithm = approvalAlgorithm,
            issuedAtUnix = issuedAtUnix,
            turnId = turnId,
            originChannel = originChannel,
            expiresAtUnix = expiresAtUnix,
            noStaleReplay = noStaleReplay,
            speechEvidenceRef = speechEvidenceRef,
            speakerEvidenceMilli = speakerEvidenceMilli,
            contextCapsuleRevision = contextCapsuleRevision,
            contextCapsuleHash = contextCapsuleHash,
            declaredTrust = declaredTrust,
            clientContext = clientContext,
        )
        val bodyText = body.toString()
        onPreparedCommand(bodyText)
        VanLiveVisualState.dispatchStarted()
        try {
            val response = postRawAt(baseUrl, "/v1/commands", bodyText, useIngress = true)
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
    ): JSONObject = postRawAt(rootUrl, path, body.toString(), useIngress)

    private fun postRawAt(
        rootUrl: String,
        path: String,
        body: String,
        useIngress: Boolean,
        extraHeaders: Map<String, String> = emptyMap(),
        freshHeaders: (() -> Map<String, String>)? = null,
    ): JSONObject = withRetry(allowRetry = GatewayMutationRetry.replaySafe(path, body)) {
        val conn = open("$rootUrl$path").apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            if (useIngress) applyIngressAuth(this)
            val identityHeaders = freshHeaders?.invoke() ?: if (useIngress) proofHeaders("POST", path, body) else emptyMap()
            (extraHeaders + identityHeaders).forEach { (name, value) -> setRequestProperty(name, value) }
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 60_000
        }
        conn.outputStream.use { it.write(body.toString().toByteArray(StandardCharsets.UTF_8)) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseText = stream?.bufferedReader()?.readText() ?: "{}"
        if (code !in 200..299) throw GatewayHttpException(code, responseText)
        JSONObject(responseText)
    }

    /**
     * A POST that proves possession of the bound device key over this exact request.
     *
     * The proof is computed from the serialized body, so the body is serialized once and
     * that same string is sent. Re-serializing between signing and sending is how a
     * signature ends up covering a document that was never transmitted — a reordered key
     * is enough.
     */
    private fun postProved(path: String, body: JSONObject): JSONObject {
        val payload = body.toString()
        return postRawAt(
            baseUrl, path, payload, useIngress = true,
            freshHeaders = { proofHeaders("POST", path, payload) },
        )
    }

    private fun putProved(path: String, body: JSONObject): JSONObject = withRetry(allowRetry = false) {
        val payload = body.toString()
        val conn = open("$baseUrl$path").apply {
            requestMethod = "PUT"
            setRequestProperty("Content-Type", "application/json")
            applyIngressAuth(this)
            proofHeaders("PUT", path, payload).forEach { (name, value) -> setRequestProperty(name, value) }
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        try {
            conn.outputStream.use { it.write(payload.toByteArray(StandardCharsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val result = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
            if (code !in 200..299) throw GatewayHttpException(code, result)
            JSONObject(result)
        } finally { conn.disconnect() }
    }

    private fun deleteProved(path: String): JSONObject = withRetry(allowRetry = false) {
        val conn = open("$baseUrl$path").apply {
            requestMethod = "DELETE"
            applyIngressAuth(this)
            proofHeaders("DELETE", path, "").forEach { (name, value) ->
                setRequestProperty(name, value)
            }
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseText = stream?.bufferedReader()?.readText() ?: "{}"
        if (code !in 200..299) throw GatewayHttpException(code, responseText)
        JSONObject(responseText)
    }

    private fun getJson(path: String): JSONObject = JSONObject(rawGet(path))

    private fun applyIngressAuth(conn: HttpURLConnection) {
        val ingress = ingressToken?.takeIf { it.isNotBlank() } ?: error("ingress_token_unconfigured")
        val device = deviceAccessToken?.takeIf { it.isNotBlank() } ?: error("device_access_token_unconfigured")
        conn.setRequestProperty("X-Van-Ingress-Token", ingress)
        conn.setRequestProperty("X-Van-Device-Token", device)
    }

    private fun rawGet(path: String): String = withRetry {
        val conn = open("$baseUrl$path").apply {
            requestMethod = "GET"
            applyIngressAuth(this)
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseText = stream?.bufferedReader()?.readText() ?: "[]"
        if (code !in 200..299) throw GatewayHttpException(code, responseText)
        responseText
    }

    /**
     * Bounded retry with full jitter, behind a circuit breaker (P3-AND-001).
     *
     * There was none of this: a single `HttpURLConnection` per call, so the first request
     * after a tunnel drop failed, the owner tapped again, that failed, and VAN looked
     * broken — while a gateway that is briefly unreachable, which is the normal condition
     * of a self-hosted service on a home connection, was indistinguishable from one that
     * is down.
     *
     * What is and is not retried lives in `GatewayRetryPolicy`, which is pure and executed
     * in `android/verification`. The rule that matters: a 409 is an answer, and retrying it
     * is how one owner command becomes two.
     *
     * `Thread.sleep` rather than `delay` because every caller already wraps this in
     * `withContext(Dispatchers.IO)`; making these functions suspend would change forty call
     * sites to express the same thing.
     */
    private fun <T> withRetry(allowRetry: Boolean = true, call: () -> T): T {
        if (!allowRetry) return GatewayMutationRetry.singleAttempt(
            httpStatus = { (it as? GatewayHttpException)?.code },
        ) {
            try {
                call().also { breaker.recordSuccess() }
            } catch (failure: Throwable) {
                if (failure is GatewayHttpException || failure is IOException) breaker.recordFailure()
                throw failure
            }
        }
        var attempt = 0
        while (true) {
            try {
                val result = call()
                breaker.recordSuccess()
                return result
            } catch (exc: Throwable) {
                val status = (exc as? GatewayHttpException)?.code
                val transportFailed = status == null && exc is IOException
                // Anything that is neither an HTTP answer nor a transport failure is a bug
                // in this client, and retrying a bug just makes it happen four times.
                if (!transportFailed && status == null) throw exc
                breaker.recordFailure()
                if (GatewayRetryPolicy.verdict(attempt, status, transportFailed) == RetryVerdict.GIVE_UP) {
                    throw exc
                }
                Thread.sleep(GatewayRetryPolicy.delayMillis(attempt))
                attempt += 1
            }
        }
    }

    /**
     * Whether a *background* refresh should be attempted now.
     *
     * Deliberately advisory. A polling loop should honour it; the owner pressing send
     * should not be told "no" by a client-side heuristic about a server they can see is up,
     * which is why `withRetry` does not consult it.
     */
    fun backgroundCallsAdvisable(): Boolean = breaker.allow()

    /** For the owner's health surface: consecutive failures the breaker has seen. */
    fun consecutiveFailures(): Int = breaker.failures()

    private fun encodeSegment(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())
        .replace("+", "%20")

    private fun encodeQuery(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())

    companion object {
        private const val KEY_BASE = "base_url"
        private const val KEY_DEVICE = "device_id"
        private const val KEY_SECRET = "device_secret"
        private const val KEY_INGRESS_TOKEN = "ingress_token"
        private const val KEY_DEVICE_ACCESS_TOKEN = "device_access_token"
        private const val KEY_PROVISIONING_FINGERPRINT = "provisioning_payload_fingerprint"
        private const val KEY_PROVISIONING_DEVICE_ID = "provisioning_device_id"
        private const val KEY_PENDING_PAIR = "pending_pair_body"
        private const val KEY_PENDING_SESSION_OPEN = "pending_session_open"
        private const val KEY_SESSION_IDENTITY = "logical_session_identity"
        private const val MIN_INGRESS_TOKEN_CHARS = 32
        private const val MIN_DEVICE_ACCESS_TOKEN_CHARS = 32
        private const val MIN_PAIRING_TOKEN_CHARS = 32

        /** Rev 1.5 §6.1. One prefix, matching the gateway's own route classifier. */
        const val INTERACTIVE_SESSIONS = "/v1/browser/interactive-sessions"

        /** Rev 1.5 §20 / §34.1. Matches `van_gateway.session.api.SESSION_PREFIX`. */
        const val SESSION_PREFIX = "/v1/session"
        const val TLS_CERTIFICATE_PATH = "/v1/devices/tls-certificate"

        /** VAN-DEVCC-R1 §3.4 — the gateway's DIAL development proxy. Android never calls DIAL. */
        const val DIAL_DEV_PREFIX = "/v1/dial-dev"

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
