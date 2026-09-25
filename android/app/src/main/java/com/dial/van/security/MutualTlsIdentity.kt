package com.dial.van.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.dial.van.BuildConfig
import java.io.File
import java.net.Socket
import java.nio.charset.StandardCharsets
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Principal
import java.security.PrivateKey
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.spec.ECGenParameterSpec
import javax.net.ssl.KeyManager
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLEngine
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509ExtendedKeyManager
import javax.net.ssl.X509TrustManager

/**
 * The phone's identity on the direct mutual-TLS link to the VAN gateway on the Hermes host.
 *
 * * The server is trusted only if its certificate chains to the VAN device CA compiled into
 *   the build (`VAN_GATEWAY_CA_PEM_B64`). No public CA is trusted on this link, so a
 *   mis-issued public certificate cannot impersonate the gateway.
 * * The client certificate's key is generated in the Android Keystore and never leaves it.
 *   The phone sends a CSR naming its enrolled device id; the gateway signs it after a
 *   device proof, and every later connection presents it.
 *
 * When the build carries no CA, this is inert and the app keeps its previous transport.
 */
class MutualTlsIdentity(context: Context) {

    private val certFile = File(context.applicationContext.filesDir, "mtls/client.pem")

    private val pinnedCa: X509Certificate? = BuildConfig.VAN_GATEWAY_CA_PEM_B64.trim()
        .takeIf { it.isNotEmpty() }
        ?.let { encoded -> parseCertificate(String(Base64.decode(encoded, Base64.DEFAULT), StandardCharsets.US_ASCII)) }

    val isConfigured: Boolean get() = pinnedCa != null

    private val trustManager: X509TrustManager? by lazy {
        val ca = pinnedCa ?: return@lazy null
        val anchors = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
            load(null, null)
            setCertificateEntry("van-device-ca", ca)
        }
        TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).run {
            init(anchors)
            trustManagers.filterIsInstance<X509TrustManager>().first()
        }
    }

    /**
     * The context that presents the client certificate. Rebuilt whenever the certificate
     * changes, which also drops its TLS session cache: a session resumed from before
     * enrolment would reach the gateway as a connection with no certificate.
     */
    @Volatile private var sslContext: SSLContext? = null

    /** Pinned trust, never a certificate: pairing, bootstrap and certificate enrolment only. */
    private val enrolmentContext: SSLContext? by lazy {
        val tm = trustManager ?: return@lazy null
        SSLContext.getInstance("TLSv1.3").apply { init(null, arrayOf(tm), null) }
    }

    private fun certificateContext(): SSLContext? {
        sslContext?.let { return it }
        val tm = trustManager ?: return null
        return synchronized(this) {
            sslContext ?: SSLContext.getInstance("TLSv1.3").apply {
                init(arrayOf<KeyManager>(KeystoreKeyManager()), arrayOf(tm), null)
            }.also { sslContext = it }
        }
    }

    /** Socket factory that presents the client certificate, and its pinned trust; null without a CA. */
    fun socketFactory(): Pair<SSLSocketFactory, X509TrustManager>? {
        val ctx = certificateContext() ?: return null
        return ctx.socketFactory to trustManager!!
    }

    /** Socket factory for the pre-enrolment routes: pinned trust, no certificate. */
    fun enrolmentSocketFactory(): SSLSocketFactory? = enrolmentContext?.socketFactory

    /** True when a certificate for the current key is held and is not within [renewWithinMs] of expiry. */
    fun hasUsableCertificate(renewWithinMs: Long = RENEW_WITHIN_MS): Boolean {
        val cert = currentCertificate() ?: return false
        if (cert.notAfter.time - System.currentTimeMillis() < renewWithinMs) return false
        return keyEntry()?.certificate?.publicKey?.encoded?.contentEquals(cert.publicKey.encoded) == true
    }

    /** PEM PKCS#10 request for [deviceId], signed inside the Keystore. Creates the key once. */
    fun certificateRequestPem(deviceId: String): String {
        val entry = keyEntry() ?: run { generateKey(); keyEntry() } ?: error("mtls_key_unavailable")
        return Pkcs10.pem(deviceId, entry.certificate.publicKey, entry.privateKey)
    }

    /** Store the gateway's answer. Refuses a certificate not for this key or not from the pinned CA. */
    fun storeCertificate(certificatePem: String) {
        val cert = parseCertificate(certificatePem)
        val ca = pinnedCa ?: error("mtls_not_configured")
        cert.verify(ca.publicKey)
        val entry = keyEntry() ?: error("mtls_key_unavailable")
        require(entry.certificate.publicKey.encoded.contentEquals(cert.publicKey.encoded)) { "mtls_certificate_key_mismatch" }
        certFile.parentFile?.mkdirs()
        val tmp = File(certFile.parentFile, "client.pem.tmp")
        tmp.writeText(certificatePem, StandardCharsets.US_ASCII)
        if (!tmp.renameTo(certFile)) error("mtls_certificate_store_failed")
        sslContext = null  // next connection builds a fresh context with the new certificate
    }

    fun forget() {
        certFile.delete()
        runCatching { androidKeyStore().deleteEntry(KEY_ALIAS) }
        sslContext = null
    }

    private fun currentCertificate(): X509Certificate? =
        certFile.takeIf { it.isFile }?.let { runCatching { parseCertificate(it.readText(StandardCharsets.US_ASCII)) }.getOrNull() }

    private fun keyEntry(): KeyStore.PrivateKeyEntry? =
        androidKeyStore().getEntry(KEY_ALIAS, null) as? KeyStore.PrivateKeyEntry

    private fun generateKey() {
        // TEE-backed, not StrongBox: a TLS handshake signs on every reconnect and StrongBox
        // signing is slow enough to show up as connection latency. No user authentication:
        // the socket has to reconnect with the screen off.
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply {
            initialize(
                KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_SIGN)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_NONE)
                    .build(),
            )
            generateKeyPair()
        }
    }

    private inner class KeystoreKeyManager : X509ExtendedKeyManager() {
        private fun alias(): String? = if (hasUsableCertificate(renewWithinMs = 0)) KEY_ALIAS else null
        override fun chooseClientAlias(keyType: Array<out String>?, issuers: Array<out Principal>?, socket: Socket?) = alias()
        override fun chooseEngineClientAlias(keyType: Array<out String>?, issuers: Array<out Principal>?, engine: SSLEngine?) = alias()
        override fun getClientAliases(keyType: String?, issuers: Array<out Principal>?) = alias()?.let { arrayOf(it) }
        override fun getCertificateChain(alias: String?): Array<X509Certificate>? =
            if (alias == KEY_ALIAS) currentCertificate()?.let { arrayOf(it) } else null
        override fun getPrivateKey(alias: String?): PrivateKey? = if (alias == KEY_ALIAS) keyEntry()?.privateKey else null
        override fun getServerAliases(keyType: String?, issuers: Array<out Principal>?): Array<String>? = null
        override fun chooseServerAlias(keyType: String?, issuers: Array<out Principal>?, socket: Socket?): String? = null
    }

    companion object {
        const val KEY_ALIAS = "van_mtls_client_v1"
        const val RENEW_WITHIN_MS = 30L * 24 * 60 * 60 * 1000

        private fun androidKeyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

        fun parseCertificate(pem: String): X509Certificate =
            CertificateFactory.getInstance("X.509").generateCertificate(pem.byteInputStream(StandardCharsets.US_ASCII)) as X509Certificate
    }
}
