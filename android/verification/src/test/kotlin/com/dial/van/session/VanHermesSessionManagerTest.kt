package com.dial.van.session

import com.dial.van.gateway.VanGatewayClient
import com.dial.van.gateway.SessionOpenRecoveryException
import java.io.IOException
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class VanHermesSessionManagerTest {
    @Test fun `repeated pending results recover on WSS without misclassifying server delay as a failed handshake`() = runBlocking {
        val gateway = VanGatewayClient()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val factory = Factory()
        val httpSockets = CopyOnWriteArrayList<Socket>()
        val manager = VanHermesSessionManager(gateway, scope, webSocketFactory = factory,
            httpCarrierFactory = { request, listener, _, _ -> Socket(request, listener).also { httpSockets += it } },
            reconnectDelayMillis = { 20L })
        try {
            manager.start()
            factory.sockets.single().open()
            await { manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
            val sent = manager.submit("command.submit", payload("pending-delay"), "A1") as VanHermesSessionManager.SubmissionOutcome.Sent
            gateway.onResume = { call, _ -> JSONObject().put("accepted", true).put("session_epoch", 1)
                .put("new_path_epoch", call + 1).put("command_states", JSONObject().put("pending-delay", "RESULT_PENDING")) }
            repeat(2) { index ->
                factory.sockets.last().resultPending(sent.messageId)
                await { factory.sockets.size == index + 2 }
                factory.sockets.last().open()
                await { factory.sockets.last().sent.size == 1 }
            }
            assertTrue(httpSockets.isEmpty())
            assertEquals(3, factory.sockets.size)
            assertEquals(VanHermesSessionManager.PRIMARY_PATH_ID, manager.state.value.authoritativePathId)
        } finally { manager.close(); scope.cancel() }
    }
    @Test fun `an empty outbox restores persisted logical session instead of opening new authority`() = runBlocking {
        val f = Fixture()
        try {
            f.gateway.restoredIdentity = JSONObject().put("van_session_id", "existing-empty-session")
                .put("session_epoch", 1).put("path_epoch", 1)
            f.manager.start()
            assertEquals(0, f.gateway.openCalls.get())
            assertEquals("existing-empty-session", f.factory.sockets.single().request().url.queryParameter("van_session_id"))
            f.factory.sockets.single().open()
            await { f.manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
            assertEquals(1, f.gateway.resumeCalls.get())
        } finally { f.dispose() }
    }

    @Test fun `a server without the open recovery contract cannot silently mint retry sessions`() = runBlocking {
        val f = Fixture()
        try {
            f.gateway.onOpen = { throw SessionOpenRecoveryException("session_open_identity_contract_missing") }
            f.manager.start()
            delay(100)
            assertEquals(1, f.gateway.openCalls.get())
            assertTrue(f.factory.sockets.isEmpty())
            assertEquals("session_open_identity_contract_missing", f.manager.state.value.reason)
        } finally { f.dispose() }
    }
    @Test fun `two WSS handshake failures promote HTTP carrier with the granted path and retained identity`() = runBlocking {
        val gateway = VanGatewayClient()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val factory = Factory()
        val httpSockets = CopyOnWriteArrayList<Socket>()
        val store = Store()
        val manager = VanHermesSessionManager(gateway, scope, store = store, webSocketFactory = factory,
            httpCarrierFactory = { request, listener, _, _ -> Socket(request, listener).also { httpSockets += it } },
            reconnectDelayMillis = { 20L })
        try {
            val original = manager.submit("command.submit", payload("fallback-work"), "A1") as VanHermesSessionManager.SubmissionOutcome.Queued
            manager.start()
            factory.sockets.single().fail()
            await { factory.sockets.size == 2 }
            factory.sockets.last().fail()
            await { httpSockets.size == 1 }
            httpSockets.single().open()
            await { httpSockets.single().sent.size == 1 }
            val sent = JSONObject(httpSockets.single().sent.single())
            assertEquals(original.messageId, sent.getString("message_id"))
            assertEquals(VanHermesSessionManager.HTTP_PATH_ID, manager.state.value.authoritativePathId)
            assertEquals(manager.state.value.pathEpoch, sent.getInt("path_epoch"))
            assertEquals(VanHermesSessionManager.HTTP_PATH_ID to "B_STREAMING", gateway.resumePaths.last())
            assertEquals(1, gateway.openCalls.get())
            assertEquals(1, store.restore().size)
        } finally { manager.close(); scope.cancel() }
    }
    private class Socket(private val request: Request, val listener: WebSocketListener) : WebSocket {
        val sent = CopyOnWriteArrayList<String>()
        @Volatile var accepts = true
        @Volatile var cancelled = false
        override fun request() = request
        override fun queueSize() = 0L
        override fun send(text: String): Boolean {
            if (!accepts || cancelled) return false
            sent += text
            return true
        }
        override fun send(bytes: ByteString) = send(bytes.utf8())
        override fun close(code: Int, reason: String?) = true
        override fun cancel() { cancelled = true }
        fun open() = listener.onOpen(this, Response.Builder().request(request)
            .protocol(Protocol.HTTP_1_1).code(101).message("Switching Protocols").build())
        fun fail() = listener.onFailure(this, IOException("link lost"), null)
        fun acknowledge(messageId: String) = listener.onMessage(this,
            JSONObject().put("message_id", messageId).put("accepted", true).toString())
        fun resultPending(messageId: String) = listener.onMessage(this,
            JSONObject().put("message_id", messageId).put("accepted", false)
                .put("refusal", "session_result_pending").toString())
    }

    private class Factory : WebSocket.Factory {
        val sockets = CopyOnWriteArrayList<Socket>()
        override fun newWebSocket(request: Request, listener: WebSocketListener): WebSocket =
            Socket(request, listener).also { sockets += it }
    }

    private class Store : SessionOutboxStore {
        private val entries = linkedMapOf<String, Pair<OutboxEntry, String>>()
        @Synchronized override fun persist(entry: OutboxEntry, envelopeJson: String) {
            entries[entry.messageId] = entry to envelopeJson
        }
        @Synchronized override fun restore() = entries.values.toList()
        @Synchronized override fun forget(messageId: String) { entries.remove(messageId) }
    }

    private class Fixture(val store: Store = Store()) {
        val gateway = VanGatewayClient()
        val factory = Factory()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = VanHermesSessionManager(gateway, scope, store = store,
            webSocketFactory = factory, reconnectDelayMillis = { 20L })
        suspend fun connected() {
            manager.start()
            factory.sockets.last().open()
            await { manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
        }
        suspend fun nextSocket(count: Int): Socket {
            await { factory.sockets.size >= count }
            return factory.sockets[count - 1]
        }
        fun dispose() { manager.close(); scope.cancel() }
    }

    private companion object {
        suspend fun await(predicate: () -> Boolean) = withTimeout(3_000L) {
            while (!predicate()) delay(5L)
        }
        fun payload(id: String) = JSONObject().put("command_id", id).put("text", "read status")
        fun ids(socket: Socket) = socket.sent.map { JSONObject(it).getString("message_id") }
    }

    @Test fun `pairing after startup opens one session and concurrent starts share one socket`() = runBlocking {
        val f = Fixture()
        try {
            f.gateway.paired = false
            f.manager.start()
            assertEquals(0, f.gateway.openCalls.get())
            f.gateway.paired = true
            List(16) { launch(Dispatchers.Default) { f.manager.start() } }.joinAll()
            assertEquals(1, f.gateway.openCalls.get())
            assertEquals(1, f.factory.sockets.size)
            f.factory.sockets.single().open()
            await { f.manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
        } finally { f.dispose() }
    }

    @Test fun `initial open failure retries and explicit close cancels further recovery`() = runBlocking {
        val f = Fixture()
        try {
            f.gateway.onOpen = { call ->
                if (call == 1) throw IOException("gateway unavailable")
                JSONObject().put("van_session_id", "recovered").put("session_epoch", 1).put("path_epoch", 1)
            }
            f.manager.start()
            val socket = f.nextSocket(1)
            socket.open()
            await { f.manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
            assertEquals(2, f.gateway.openCalls.get())
            f.manager.close()
            socket.fail()
            delay(80L)
            assertEquals(1, f.factory.sockets.size)
        } finally { f.dispose() }
    }

    @Test fun `ordinary reconnect resends unknown commands with original message and idempotency identities`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            repeat(2) { assertIs<VanHermesSessionManager.SubmissionOutcome.Sent>(
                f.manager.submit("command.submit", payload("command_$it"), "A1")) }
            val first = f.factory.sockets.single()
            first.fail()
            val second = f.nextSocket(2)
            assertEquals("test-proof-1", first.request().header("X-Van-Device-Proof"))
            assertEquals("test-proof-2", second.request().header("X-Van-Device-Proof"))
            assertEquals("2", second.request().header("X-Van-Device-Proof-Issued-At"))
            assertEquals("session_1", second.request().url.queryParameter("van_session_id"))
            second.open()
            await { second.sent.size == 2 }
            assertEquals(ids(first), ids(second))
            first.sent.zip(second.sent).forEach { (before, after) ->
                val a = JSONObject(before); val b = JSONObject(after)
                assertEquals(a.getString("idempotency_key"), b.getString("idempotency_key"))
                assertEquals(a.getString("payload_digest"), b.getString("payload_digest"))
                assertTrue(b.getInt("path_epoch") > a.getInt("path_epoch"))
            }
            assertEquals(1, f.gateway.openCalls.get())
        } finally { f.dispose() }
    }

    @Test fun `failed resend retains every unvisited pending command for the next reconnect`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            repeat(3) { f.manager.submit("command.submit", payload("command_$it"), "A1") }
            val first = f.factory.sockets.single()
            first.fail()
            val second = f.nextSocket(2)
            second.accepts = false
            second.open()
            await { f.gateway.resumeCalls.get() == 2 && f.manager.state.value.pathEpoch == 3 }
            second.fail()
            val third = f.nextSocket(3)
            third.open()
            await { third.sent.size == 3 }
            assertEquals(ids(first), ids(third))
            assertEquals(listOf("command_0", "command_1", "command_2"), f.gateway.pendingRequests.last())
        } finally { f.dispose() }
    }

    @Test fun `resume timeout keeps the session and durable outbox instead of abandoning owner work`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            f.factory.sockets.single().fail()
            assertIs<VanHermesSessionManager.SubmissionOutcome.Queued>(
                f.manager.submit("command.submit", payload("offline"), "A1"))
            f.gateway.onResume = { call, _ ->
                if (call == 2) throw IOException("resume response timed out")
                JSONObject().put("accepted", true).put("session_epoch", 1)
                    .put("new_path_epoch", call + 1).put("command_states", JSONObject())
            }
            f.nextSocket(2).open()
            val third = f.nextSocket(3)
            assertEquals("session_1", f.manager.state.value.vanSessionId)
            assertEquals(1, f.store.restore().size)
            assertTrue(f.manager.undeliveredSinceLastRead().isEmpty())
            third.open()
            await { third.sent.size == 1 }
            assertEquals(1, f.gateway.openCalls.get())
        } finally { f.dispose() }
    }

    @Test fun `queued write remains durable until gateway acknowledgement`() = runBlocking {
        val f = Fixture()
        try {
            val queued = assertIs<VanHermesSessionManager.SubmissionOutcome.Queued>(
                f.manager.submit("command.submit", payload("offline"), "A1"))
            f.connected()
            val socket = f.factory.sockets.single()
            await { socket.sent.size == 1 }
            assertEquals(1, f.store.restore().size, "send enqueues bytes and does not prove server admission")
            socket.acknowledge(queued.messageId)
            assertTrue(f.store.restore().isEmpty())
        } finally { f.dispose() }
    }

    @Test fun `pending server result retains durable work and retries with its original identity`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            val sent = assertIs<VanHermesSessionManager.SubmissionOutcome.Sent>(
                f.manager.submit("command.submit", payload("pending-result"), "A1"))
            val first = f.factory.sockets.single()
            f.gateway.onResume = { call, _ ->
                JSONObject().put("accepted", true).put("session_epoch", 1).put("new_path_epoch", call + 1)
                    .put("command_states", JSONObject().put("pending-result", "RESULT_PENDING"))
            }
            first.resultPending(sent.messageId)
            assertEquals(1, f.store.restore().size)
            val second = f.nextSocket(2)
            second.open()
            await { second.sent.size == 1 }
            assertEquals(ids(first), ids(second))
            assertEquals(JSONObject(first.sent.single()).getString("idempotency_key"),
                JSONObject(second.sent.single()).getString("idempotency_key"))
            assertEquals(1, f.store.restore().size)
            second.acknowledge(sent.messageId)
            assertTrue(f.store.restore().isEmpty())
            assertEquals(1, f.gateway.openCalls.get())
        } finally { f.dispose() }
    }

    @Test fun `a pending receipt for an unknown message cannot disrupt the live path`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            f.factory.sockets.single().resultPending("unknown-message")
            delay(80L)
            assertEquals(1, f.factory.sockets.size)
            assertEquals(SupervisorState.SINGLE_PATH, f.manager.state.value.supervisor)
        } finally { f.dispose() }
    }

    @Test fun `resume reconciliation removes a durable in flight entry before process restart`() = runBlocking {
        val f = Fixture()
        try {
            f.manager.submit("command.submit", payload("admitted"), "A1")
            f.connected()
            await { f.factory.sockets.single().sent.size == 1 }
            assertEquals(1, f.store.restore().size)
            f.gateway.onResume = { call, _ ->
                JSONObject().put("accepted", true).put("session_epoch", 1).put("new_path_epoch", call + 1)
                    .put("command_states", JSONObject().put("admitted", "ADMITTED"))
            }
            f.factory.sockets.single().fail()
            val second = f.nextSocket(2)
            second.open()
            await { f.manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
            assertTrue(f.store.restore().isEmpty())
            assertTrue(second.sent.isEmpty())
            val restarted = Fixture(f.store)
            try {
                restarted.connected()
                assertTrue(restarted.factory.sockets.single().sent.isEmpty())
            } finally { restarted.dispose() }
        } finally { f.dispose() }
    }

    @Test fun `process death before acknowledgement restores the original durable message`() = runBlocking {
        val f = Fixture()
        try {
            f.manager.submit("command.submit", payload("not_yet_admitted"), "A1")
            f.connected()
            val first = f.factory.sockets.single()
            await { first.sent.size == 1 }
            f.dispose()
            val restarted = Fixture(f.store)
            try {
                restarted.gateway.onOpen = { JSONObject().put("van_session_id", "after_restart")
                    .put("session_epoch", 1).put("path_epoch", 1) }
                restarted.connected()
                val second = restarted.factory.sockets.single()
                await { second.sent.size == 1 }
                assertEquals(ids(first), ids(second))
                assertEquals(JSONObject(first.sent.single()).getString("idempotency_key"),
                    JSONObject(second.sent.single()).getString("idempotency_key"))
            } finally { restarted.dispose() }
        } finally { f.dispose() }
    }

    @Test fun `eligible live send is persisted before the socket write and survives process death`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            val outcome = assertIs<VanHermesSessionManager.SubmissionOutcome.Sent>(
                f.manager.submit("command.submit", payload("live"), "A1"))
            assertEquals(outcome.messageId, f.store.restore().single().first.messageId)
            f.dispose()
            val restarted = Fixture(f.store)
            try {
                restarted.gateway.onResume = { _, _ -> JSONObject().put("accepted", true)
                    .put("session_epoch", 1).put("new_path_epoch", 3).put("command_states", JSONObject()) }
                restarted.connected()
                await { restarted.factory.sockets.single().sent.size == 1 }
                assertEquals(listOf(outcome.messageId), ids(restarted.factory.sockets.single()))
                assertEquals(0, restarted.gateway.openCalls.get(), "resume the recorded session before opening another")
                val sent = JSONObject(restarted.factory.sockets.single().sent.single())
                assertEquals("session_1", sent.getString("van_session_id"))
                assertEquals(3, sent.getInt("path_epoch"))
            } finally { restarted.dispose() }
        } finally { f.dispose() }
    }

    @Test fun `live A3 requiring owner context is reconfirmed after process death and live A4 is never persisted`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            f.manager.submit("command.submit", payload("approval"), "A4")
            assertTrue(f.store.restore().isEmpty())
            val sensitive = assertIs<VanHermesSessionManager.SubmissionOutcome.Sent>(
                f.manager.submit("command.submit", payload("owner_context"), "A3", requiresLiveOwnerContext = true))
            f.dispose()
            val restarted = Fixture(f.store)
            try {
                restarted.connected()
                assertTrue(restarted.factory.sockets.single().sent.isEmpty())
                assertEquals(sensitive.messageId, restarted.manager.awaitingReconfirmation().single().messageId)
            } finally { restarted.dispose() }
        } finally { f.dispose() }
    }

    @Test fun `restored work for conflicting logical sessions is held without guessing new authority`() = runBlocking {
        val store = Store()
        repeat(2) { index ->
            val id = "msg_$index"
            val entry = DurableOutbox.admit(id, "cmd_$index", "idem_$index", "", "A1", false, id,
                System.currentTimeMillis())!!
            val envelope = SessionEnvelope.build(id, "old_session_$index", 1, 2, "test-device",
                "command.submit", System.currentTimeMillis(), payload("cmd_$index"), "idem_$index")
            store.persist(entry, envelope.toString())
        }
        val f = Fixture(store)
        try {
            f.manager.start()
            f.manager.start()
            assertEquals(0, f.gateway.openCalls.get())
            assertTrue(f.factory.sockets.isEmpty())
            assertEquals(2, store.restore().size)
            assertTrue(f.manager.state.value.reason.contains("conflicting sessions"))
        } finally { f.dispose() }
    }

    @Test fun `explicit unknown session attaches a replacement socket and reports abandoned work`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            f.factory.sockets.single().fail()
            f.manager.submit("command.submit", payload("old_session_work"), "A1")
            f.gateway.onResume = { call, _ ->
                if (call == 2) JSONObject().put("refusal", "session_unknown")
                else JSONObject().put("accepted", true).put("session_epoch", 1)
                    .put("new_path_epoch", call + 1).put("command_states", JSONObject())
            }
            f.nextSocket(2).open()
            val replacement = f.nextSocket(3)
            assertEquals("session_2", f.manager.state.value.vanSessionId)
            assertEquals("session_2", replacement.request().url.queryParameter("van_session_id"))
            assertTrue(f.store.restore().isEmpty())
            assertEquals(1, f.manager.undeliveredSinceLastRead().size)
            replacement.open()
            await { f.manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
            assertTrue(replacement.sent.isEmpty())
        } finally { f.dispose() }
    }

    @Test fun `authoritative refusal holds pending work without creating replacement authority`() = runBlocking {
        val f = Fixture()
        try {
            f.manager.submit("command.submit", payload("pending"), "A1")
            f.gateway.onResume = { _, _ -> JSONObject().put("refusal", "session_device_mismatch") }
            f.manager.start()
            f.factory.sockets.single().open()
            await { f.manager.state.value.reason == "session_device_mismatch" }
            delay(80L)
            assertEquals(1, f.gateway.openCalls.get())
            assertEquals(1, f.factory.sockets.size)
            assertEquals(1, f.store.restore().size)
        } finally { f.dispose() }
    }

    @Test fun `A4 remains unstorable until resume confirms a live session epoch`() = runBlocking {
        val f = Fixture()
        try {
            f.manager.start()
            assertIs<VanHermesSessionManager.SubmissionOutcome.Refused>(
                f.manager.submit("command.submit", payload("approval"), "A4"))
            assertTrue(f.store.restore().isEmpty())
            assertTrue(f.factory.sockets.single().sent.isEmpty())
        } finally { f.dispose() }
    }

    @Test fun `stale socket callbacks cannot disconnect a recovered transport`() = runBlocking {
        val f = Fixture()
        try {
            f.connected()
            val first = f.factory.sockets.single()
            first.fail()
            val second = f.nextSocket(2)
            second.open()
            await { f.manager.state.value.supervisor == SupervisorState.SINGLE_PATH }
            first.listener.onClosed(first, 1006, "late close")
            delay(80L)
            assertEquals(2, f.factory.sockets.size)
            assertEquals(SupervisorState.SINGLE_PATH, f.manager.state.value.supervisor)
        } finally { f.dispose() }
    }
}
