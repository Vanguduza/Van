package com.dial.van.connectivity

import com.dial.van.browser.BrowserIceServer
import com.dial.van.browser.BrowserStreamGrant
import java.io.File
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.Base64
import java.util.Properties
import javax.net.ssl.X509TrustManager
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SignedConnectivityRoutingTest {
    private val pin = "sha256/" + Base64.getEncoder().encodeToString(ByteArray(32) { 1 })
    private fun manifest() = ConnectivityManifest(4, "https://new.example", "wss://socket.example/v1/session/ws",
        "https://stream.example/rtc", listOf("stun:ice.example:3478", "turns:relay.example:5349"), listOf(pin), "{}")

    @Test fun `signed endpoints automatically include the distinct socket and stream authorities`() {
        val route = SignedConnectivityRouting.from(manifest())
        assertEquals("https://new.example", route.gatewayUrl)
        assertTrue(route.permitsTls("wss://socket.example/v1/session/ws?device_token=ephemeral"))
        assertTrue(route.permitsTls("https://stream.example/rtc/session"))
        assertFalse(route.permitsTls("https://attacker.example/rtc"))
    }

    @Test fun `malformed or credential carrying endpoints and unsigned pin formats are refused`() {
        val source = manifest()
        for (bad in listOf(source.copy(gatewayUrl = "http://new.example"), source.copy(gatewayUrl = "https://u:p@new.example"),
            source.copy(gatewayUrl = "https://new.example/base"), source.copy(sessionWebsocketUrl = "wss://socket.example/other"),
            source.copy(sessionWebsocketUrl = "wss://socket.example/v1/session/ws?token=secret"),
            source.copy(certificatePins = emptyList()), source.copy(certificatePins = listOf("trust-all")),
            source.copy(iceServerUrls = listOf("turn:secret@evil.example:3478")))) {
            assertFailsWith<IllegalArgumentException> { SignedConnectivityRouting.from(bad) }
        }
    }

    @Test fun `browser grants retain scoped relay credentials and use signed STUN configuration`() {
        val route = SignedConnectivityRouting.from(manifest())
        val grant = BrowserStreamGrant("browser1", "short-lived-grant", "https://stream.example/rtc/browser1", 10_000,
            listOf(BrowserIceServer(listOf("turns:relay.example:5349"), "scoped-user", "scoped-password")))
        val applied = SignedBrowserRouting.apply(route, grant)
        assertEquals(grant.iceServers.first(), applied.iceServers.first())
        assertEquals(listOf("stun:ice.example:3478"), applied.iceServers.last().urls)
        assertFailsWith<IllegalArgumentException> { SignedBrowserRouting.apply(route, grant.copy(signalUrl = "https://evil.example/rtc/browser1")) }
        assertFailsWith<IllegalArgumentException> { SignedBrowserRouting.apply(route, grant.copy(signalUrl = "https://stream.example/rtc/../steal")) }
        assertFailsWith<IllegalArgumentException> { SignedBrowserRouting.apply(route, grant.copy(signalUrl = "https://stream.example/rtc/%2e%2e/steal")) }
        assertFailsWith<IllegalArgumentException> { SignedBrowserRouting.apply(route, grant.copy(iceServers =
            listOf(BrowserIceServer(listOf("turn:evil.example"), "scoped-user", "scoped-password")))) }
    }

    @Test fun `a matching pin never bypasses CA trust and a trusted wrong pin fails closed`() {
        val properties = Properties().apply { File("../van-gateway.properties").inputStream().use(::load) }
        val pem = Base64.getDecoder().decode(properties.getProperty("VAN_GATEWAY_CA_PEM_B64"))
        val certificate = CertificateFactory.getInstance("X.509").generateCertificate(pem.inputStream()) as X509Certificate
        val matching = "sha256/" + Base64.getEncoder().encodeToString(java.security.MessageDigest.getInstance("SHA-256").digest(certificate.publicKey.encoded))
        fun delegate(allow: Boolean) = object : X509TrustManager {
            override fun getAcceptedIssuers() = emptyArray<X509Certificate>()
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                if (!allow) throw CertificateException("untrusted issuer")
            }
        }
        val chain = arrayOf(certificate)
        SignedPinTrustManager(listOf(delegate(true)), setOf(matching)).checkServerTrusted(chain, "EC")
        assertFailsWith<CertificateException> { SignedPinTrustManager(listOf(delegate(false)), setOf(matching)).checkServerTrusted(chain, "EC") }
        assertFailsWith<CertificateException> { SignedPinTrustManager(listOf(delegate(true)), setOf(pin)).checkServerTrusted(chain, "EC") }

        val unrelated = javaClass.getResourceAsStream("/connectivity/unrelated-test-server.pem")!!.use {
            CertificateFactory.getInstance("X.509").generateCertificate(it) as X509Certificate
        }
        // A CA-valid leaf plus an unrelated appended pinned certificate is not a
        // pinned server. Trust delegates may ignore unrelated supplied certificates.
        assertFailsWith<CertificateException> {
            SignedPinTrustManager(listOf(delegate(true)), setOf(matching))
                .checkServerTrusted(arrayOf(unrelated, certificate), "EC")
        }
        assertFailsWith<CertificateException> {
            SignedPinTrustManager(listOf(delegate(true)), setOf(matching)).checkServerTrusted(emptyArray(), "EC")
        }
    }
}
