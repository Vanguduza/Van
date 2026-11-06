package com.dial.van.command.connected

import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

class ConnectedReadbackTest {
    @Test fun `failed Google read does not discard independent healthy runtime`() = runBlocking {
        val health = JSONObject().put("hermes", JSONObject().put("ok", true))
        val first = ConnectedReadback.source { health }
        val second = ConnectedReadback.source { throw IOException("Google unavailable") }
        assertSame(health, first.value)
        assertNull(first.failure)
        assertNull(second.value)
        assertEquals("Google unavailable", second.failure)
    }

    @Test fun `revocation requires explicit disconnected receipt and independent disconnected read`() = runBlocking {
        var requests = 0
        var reads = 0
        val disconnected = JSONObject().put("connected", false)
        val outcome = ConnectedReadback.revoke(request = { requests++; disconnected }, read = { reads++; disconnected })
        assertTrue(outcome.confirmed)
        assertSame(disconnected, outcome.status)
        assertEquals(1, requests)
        assertEquals(1, reads)
    }

    @Test fun `lost or contradictory confirmation is unknown and no mutation retry occurs`() = runBlocking {
        for (kind in listOf("missing receipt", "connected receipt", "lost read", "connected read")) {
            var requests = 0
            val outcome = ConnectedReadback.revoke(request = {
                requests++
                when (kind) {
                    "missing receipt" -> JSONObject()
                    "connected receipt" -> JSONObject().put("connected", true)
                    else -> JSONObject().put("connected", false)
                }
            }, read = {
                if (kind == "lost read") throw IOException("read lost")
                JSONObject().put("connected", kind == "connected read")
            })
            assertFalse(outcome.confirmed)
            assertNull(outcome.status)
            assertTrue(outcome.error!!.contains("may have been applied"))
            assertEquals(1, requests)
        }
    }

    @Test fun `cancellation is not mistaken for connection failure or confirmed revocation`() {
        assertFailsWith<CancellationException> { runBlocking {
            ConnectedReadback.source { throw CancellationException("screen gone") }
        } }
        assertFailsWith<CancellationException> { runBlocking {
            ConnectedReadback.revoke(request = { throw CancellationException("screen gone") }, read = { JSONObject() })
        } }
    }
}
