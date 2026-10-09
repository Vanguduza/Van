package com.dial.van.connectivity

import java.io.IOException
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ProvisioningRecoveryTest {
    private val payload = ProvisioningPayload("attempt_1", "https://gateway.invalid", "pairing-secret",
        "bootstrap-secret", "challenge", 1, 1, 10_000)

    private class Device {
        var saved = ProvisioningRecovery.Pairing(null, "", "", false)
        var pairs = 0
        var binds = 0
        var failBind = false
        var status = JSONObject().put("configured", true).put("bound", false)
        var statusUnavailable = false
        var mayReplace: Boolean? = null
        suspend fun complete(payload: ProvisioningPayload) = ProvisioningRecovery.complete(
            payload, pairing = { saved }, pair = {
                pairs++
                saved = ProvisioningRecovery.Pairing(ProvisioningRecovery.fingerprint(payload), payload.gatewayUrl, "device_1", true)
            }, bindingStatus = {
                if (statusUnavailable) throw IOException("TLS enrollment is not yet available")
                status
            }, localKeyFingerprint = { "local-key" }, bind = { allowed ->
                binds++
                mayReplace = allowed
                if (failBind) throw IOException("attestation answer lost")
                JSONObject().put("device_id", "device_1")
            }, nowMs = 5_000,
        )
    }

    @Test fun `binding failure resumes the same signed pairing without spending its ticket twice`() = runBlocking {
        val d = Device()
        d.failBind = true
        assertFailsWith<IOException> { d.complete(payload) }
        d.failBind = false
        d.complete(payload)
        assertEquals(1, d.pairs)
        assertEquals(2, d.binds)
    }

    @Test fun `lost successful bind answer is recovered by matching the authoritative hardware key`() = runBlocking {
        val d = Device()
        d.failBind = true
        assertFailsWith<IOException> { d.complete(payload) }
        d.status = JSONObject().put("bound", true).put("device_key_fingerprint", "local-key")
        val response = d.complete(payload)
        assertTrue(response.getBoolean("bound"))
        assertEquals(1, d.pairs)
        assertEquals(1, d.binds)
    }

    @Test fun `changed signed payload cannot replace an existing device identity`() = runBlocking {
        val d = Device()
        d.complete(payload)
        assertFailsWith<IllegalArgumentException> { d.complete(payload.copy(bootstrapToken = "replacement")) }
        assertFailsWith<IllegalArgumentException> { d.complete(payload.copy(gatewayUrl = "https://other.invalid")) }
        d.saved = d.saved.copy(deviceId = "another_device")
        assertFailsWith<IllegalArgumentException> { d.complete(payload) }
        assertEquals(1, d.pairs)
        assertEquals(1, d.binds)
    }

    @Test fun `unavailable binding status never authorises deleting a key`() = runBlocking {
        val d = Device()
        d.statusUnavailable = true
        d.complete(payload)
        assertFalse(d.mayReplace!!)
    }

    @Test fun `explicit unbound response permits renewing an incomplete challenge key`() = runBlocking {
        val d = Device()
        d.complete(payload)
        assertTrue(d.mayReplace!!)
    }

    @Test fun `a bound fingerprint mismatch refuses without pairing or rebinding again`() = runBlocking {
        val d = Device()
        d.complete(payload)
        d.status = JSONObject().put("bound", true).put("device_key_fingerprint", "other-phone")
        assertFailsWith<IllegalArgumentException> { d.complete(payload) }
        assertEquals(1, d.pairs)
        assertEquals(1, d.binds)
    }

    @Test fun `expiry still applies to a partially completed attempt`() = runBlocking {
        val d = Device()
        assertFailsWith<IllegalArgumentException> { d.complete(payload.copy(expiresAtMs = 5_000)) }
        assertEquals(0, d.pairs)
    }

    @Test fun `bind first pairing recovers a lost first reply with the persisted device and client token`() = runBlocking {
        val events = mutableListOf<String>()
        val prepared = ProvisioningRecovery.PreparedPairing(ProvisioningRecovery.fingerprint(payload), "chosen-device", "x".repeat(43))
        var bound = false
        var pairs = 0
        suspend fun complete() = ProvisioningRecovery.completePrebound(payload,
            prepare = { events += "persist"; prepared },
            recoverBinding = { if (bound) JSONObject().put("bound", true) else null },
            bind = { events += "bind"; bound = true; JSONObject().put("bound", true) },
            pair = {
                events += "pair"
                if (++pairs == 1) throw IOException("answer lost after ticket consumption")
                JSONObject().put("device_id", prepared.deviceId).put("device_access_token", prepared.accessToken)
                    .put("ingress_token", "i".repeat(43))
            }, nowMs = 5_000)
        assertFailsWith<IOException> { complete() }
        complete()
        assertEquals(listOf("persist", "bind", "pair", "persist", "pair"), events)
        assertEquals(2, pairs)
    }

    @Test fun `an unknown binding outcome retains the prepared attempt without pair or attestation`() = runBlocking {
        var sideEffects = 0
        assertFailsWith<IOException> { ProvisioningRecovery.completePrebound(payload,
            prepare = { ProvisioningRecovery.PreparedPairing(ProvisioningRecovery.fingerprint(payload), "chosen", "x".repeat(43)) },
            recoverBinding = { throw IOException("recovery status unreachable") },
            bind = { sideEffects++; JSONObject() }, pair = { sideEffects++; JSONObject() }, nowMs = 5_000) }
        assertEquals(0, sideEffects)
    }

    @Test fun `pairing receipt cannot switch the prepared device or standing token`() = runBlocking {
        for (changed in listOf("device", "token")) {
            assertFailsWith<IllegalArgumentException> { ProvisioningRecovery.completePrebound(payload,
                prepare = { ProvisioningRecovery.PreparedPairing(ProvisioningRecovery.fingerprint(payload), "chosen", "x".repeat(43)) },
                recoverBinding = { JSONObject().put("bound", true) }, bind = { error("must not rebind") }, pair = {
                    JSONObject().put("device_id", if (changed == "device") "imposter" else "chosen")
                        .put("device_access_token", if (changed == "token") "y".repeat(43) else "x".repeat(43))
                        .put("ingress_token", "i".repeat(43))
                }, nowMs = 5_000) }
        }
    }
}
