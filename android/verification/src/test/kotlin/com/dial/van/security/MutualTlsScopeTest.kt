package com.dial.van.security

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MutualTlsScopeTest {
    private val direct = "https://62.83.35.103:8443"

    @Test
    fun `the direct endpoint and its session socket are on the pinned link`() {
        assertTrue(MutualTlsScope.applies(direct, "https://62.83.35.103:8443/v1/devices/pair"))
        assertTrue(MutualTlsScope.applies(direct, "wss://62.83.35.103:8443/v1/session/ws?van_session_id=s&device_token=t"))
        assertTrue(MutualTlsScope.applies("https://VAN.example/", "wss://van.example:443/v1/session/ws"))
    }

    @Test
    fun `every other route keeps platform trust`() {
        // A phone still saved on the older publicly-certified route.
        assertFalse(MutualTlsScope.applies(direct, "https://abc.trycloudflare.com/v1/session/open"))
        assertFalse(MutualTlsScope.applies(direct, "wss://abc.trycloudflare.com/v1/session/ws"))
        // Same host, another port or plain text: not the pinned listener.
        assertFalse(MutualTlsScope.applies(direct, "https://62.83.35.103/health"))
        assertFalse(MutualTlsScope.applies(direct, "http://62.83.35.103:8443/health"))
        // A look-alike authority.
        assertFalse(MutualTlsScope.applies(direct, "https://62.83.35.103.evil.example:8443/"))
    }

    @Test
    fun `a build without a direct endpoint pins nothing`() {
        assertFalse(MutualTlsScope.applies("", "https://62.83.35.103:8443/health"))
        assertFalse(MutualTlsScope.applies("http://127.0.0.1:8787", "http://127.0.0.1:8787/health"))
    }
}
