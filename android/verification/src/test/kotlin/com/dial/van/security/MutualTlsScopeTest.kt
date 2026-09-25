package com.dial.van.security

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
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

    @Test
    fun `a build that pins the direct link moves a phone saved on an older route`() {
        assertEquals(direct, MutualTlsScope.effectiveBaseUrl("https://abc.trycloudflare.com", "$direct/", buildPinsCa = true))
        assertEquals(direct, MutualTlsScope.effectiveBaseUrl(null, direct, buildPinsCa = true))
        assertEquals(direct, MutualTlsScope.effectiveBaseUrl(direct, direct, buildPinsCa = true))
    }

    @Test
    fun `without a pinned direct link the saved address stands`() {
        val saved = "https://abc.trycloudflare.com"
        // No CA in the build: the address alone is not a reason to move anyone.
        assertEquals(saved, MutualTlsScope.effectiveBaseUrl(saved, direct, buildPinsCa = false))
        // A CA with no usable https address pins nothing.
        assertEquals(saved, MutualTlsScope.effectiveBaseUrl(saved, "", buildPinsCa = true))
        assertEquals(saved, MutualTlsScope.effectiveBaseUrl(saved, "http://62.83.35.103:8443", buildPinsCa = true))
        assertNull(MutualTlsScope.effectiveBaseUrl(null, "", buildPinsCa = false))
        assertNull(MutualTlsScope.effectiveBaseUrl("  ", "", buildPinsCa = false))
    }

    @Test
    fun `only the routes a phone needs before it holds a certificate skip it`() {
        assertTrue(MutualTlsScope.isPreEnrolment("$direct/v1/devices/pair"))
        assertTrue(MutualTlsScope.isPreEnrolment("$direct/v1/devices/bootstrap/challenge"))
        assertTrue(MutualTlsScope.isPreEnrolment("$direct/v1/devices/bootstrap/attest"))
        assertTrue(MutualTlsScope.isPreEnrolment("$direct/v1/devices/tls-certificate"))
        assertFalse(MutualTlsScope.isPreEnrolment("$direct/v1/session/open"))
        assertFalse(MutualTlsScope.isPreEnrolment("$direct/v1/devices/pair/extra"))
        assertFalse(MutualTlsScope.isPreEnrolment("$direct/health"))
        assertFalse(MutualTlsScope.isPreEnrolment("wss://62.83.35.103:8443/v1/session/ws?van_session_id=s"))
    }
}

