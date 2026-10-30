package com.dial.van.session

import java.io.IOException
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HttpSessionCarrierTest {
    @Test fun `SSE comments and multiline data preserve a single durable event`() {
        val parser = SessionSseFrames.Parser()
        parser.feed(": keepalive")
        assertEquals(null, parser.feed(""))
        parser.feed("id: ignored")
        parser.feed("data: {\"seq\":7,")
        parser.feed("data: \"event_type\":\"mission.started\"}")
        assertEquals(7L, parser.feed("")!!.getLong("seq"))
        assertEquals(null, parser.feed(""))
        assertFailsWith<IllegalArgumentException> { parser.feed("data: " + "x".repeat(256 * 1024 + 1)) }
    }

    @Test fun `HTTP admission event pages and POST acknowledgement use existing frame identities`() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val frames = CopyOnWriteArrayList<JSONObject>()
        val sent = CopyOnWriteArrayList<JSONObject>()
        var opened = false
        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) { opened = true }
            override fun onMessage(webSocket: WebSocket, text: String) { frames += JSONObject(text) }
        }
        val carrier = HttpSessionCarrier(Request.Builder().url("https://gateway.invalid/v1/session/messages").build(), scope, listener,
            post = { sent += it; JSONObject().put("accepted", true).put("kind", it.getString("kind")) },
            downstream = { flow { emit(JSONObject()); emit(JSONObject().put("seq", 7).put("event_type", "mission.started")); awaitCancellation() } })
        try {
            carrier.start()
            withTimeout(5_000) { while (!opened || frames.isEmpty()) delay(5) }
            val envelope = JSONObject().put("message_id", "same-message").put("idempotency_key", "same-key").put("kind", "mission.cancel")
            assertTrue(carrier.send(envelope.toString()))
            withTimeout(5_000) { while (frames.size < 2) delay(5) }
            assertEquals("same-key", sent.single().getString("idempotency_key"))
            assertEquals(7L, (SessionDownstream.parse(frames.first()) as SessionDownstream.Frame.Event).page.nextCursor)
            assertEquals("same-message", (SessionDownstream.parse(frames.last()) as SessionDownstream.Frame.Acknowledgement).messageId)
        } finally { carrier.cancel(); scope.cancel() }
    }

    @Test fun `ambiguous POST failure closes carrier without inventing an acknowledgement`() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val frames = CopyOnWriteArrayList<String>()
        val failures = CopyOnWriteArrayList<Throwable>()
        val listener = object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) { frames += text }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { failures += t }
        }
        val carrier = HttpSessionCarrier(Request.Builder().url("https://gateway.invalid").build(), scope, listener,
            post = { throw IOException("reply lost") }, downstream = { flow { emit(JSONObject()); awaitCancellation() } })
        try {
            carrier.start()
            assertTrue(carrier.send(JSONObject().put("message_id", "retained").toString()))
            withTimeout(5_000) { while (failures.isEmpty()) delay(5) }
            assertTrue(frames.isEmpty())
            assertFalse(carrier.send("{}"))
        } finally { carrier.cancel(); scope.cancel() }
    }
}
