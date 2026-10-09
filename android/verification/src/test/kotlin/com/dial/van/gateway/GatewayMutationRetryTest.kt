package com.dial.van.gateway

import java.io.IOException
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue

class GatewayMutationRetryTest {
    @Test fun `lost create response does not automatically create a second unkeyed resource`() {
        var creates = 0
        var attempts = 0
        val path = "/v1/browser/sessions"
        val body = JSONObject().put("url", "https://example.com").toString()
        assertFalse(GatewayMutationRetry.replaySafe(path, body))
        val lostResponse = IOException("response lost after commit")
        val failure = assertFailsWith<GatewayMutationOutcomeUnknown> {
            GatewayMutationRetry.singleAttempt(httpStatus = { null }) {
                attempts++
                creates++ // Server committed before the response was lost.
                throw lostResponse
            }
        }
        assertSame(lostResponse, failure.cause)
        assertEquals(1, creates)
        assertEquals(1, attempts)
        assertFalse(GatewayMutationRetry.replaySafe(path, JSONObject().put("idempotency_key", "ignored-by-this-route").toString()))
    }

    @Test fun `uncertain server response stays unknown and explicit refusals keep their response`() {
        class HttpFailure(val status: Int) : Exception()
        for (status in listOf(408, 500, 503)) {
            val original = HttpFailure(status)
            val unknown = assertFailsWith<GatewayMutationOutcomeUnknown> {
                GatewayMutationRetry.singleAttempt({ (it as? HttpFailure)?.status }) { throw original }
            }
            assertSame(original, unknown.cause)
        }
        val refusal = HttpFailure(409)
        val reported = assertFailsWith<HttpFailure> {
            GatewayMutationRetry.singleAttempt({ (it as? HttpFailure)?.status }) { throw refusal }
        }
        assertSame(refusal, reported)
        val clientBug = IllegalArgumentException("bad local body")
        assertSame(clientBug, assertFailsWith<IllegalArgumentException> {
            GatewayMutationRetry.singleAttempt({ null }) { throw clientBug }
        })
    }

    @Test fun `only documented stable operation identities permit mutation retries`() {
        assertTrue(GatewayMutationRetry.replaySafe("/v1/session/messages", JSONObject().put("message_id", "same").put("idempotency_key", "same").toString()))
        assertTrue(GatewayMutationRetry.replaySafe("/v1/session/open", JSONObject().put("open_request_id", "stable-uuid").toString()))
        assertTrue(GatewayMutationRetry.replaySafe("/v1/commands", JSONObject().put("command_id", "same").put("idempotency_key", "same").toString()))
        assertTrue(GatewayMutationRetry.replaySafe("/v1/reminders/parse", JSONObject().put("idempotency_key", "same").toString()))
        assertFalse(GatewayMutationRetry.replaySafe("/v1/session/open", "{}"))
        assertFalse(GatewayMutationRetry.replaySafe("/v1/missions/mission1/cancel", "{}"))
        assertFalse(GatewayMutationRetry.replaySafe("/v1/devices/bootstrap/attest", JSONObject().put("token", "once").toString()))
    }

    @Test fun `legacy one return pairing is not retryable and prepared bound pairing is`() {
        val body = JSONObject().put("device_id", "same").put("device_secret", "same")
            .put("pairing_token", "single-use")
        assertFalse(GatewayMutationRetry.replaySafe("/v1/devices/pair", body.toString()))
        body.put("device_access_token", "x".repeat(43))
        assertTrue(GatewayMutationRetry.replaySafe("/v1/devices/pair", body.toString()))
    }
}
