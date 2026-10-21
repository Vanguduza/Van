package com.dial.van.control

import androidx.fragment.app.FragmentActivity
import com.dial.van.gateway.GatewayHttpException
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.status.VanCommandStatus
import java.io.IOException
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class VanCommandControllerTest {
    private class Fixture {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val gateway = VanGatewayClient()
        val spoken = CopyOnWriteArrayList<String>()
        val saved = CopyOnWriteArrayList<String>()
        val controller = VanCommandController(gateway, scope, speak = { spoken += it }).apply {
            storeForLater = { body, _ -> saved += body.toString(); true }
        }
        suspend fun submitted() = await { !controller.state.value.submitting && gateway.commandCalls.get() > 0 }
        fun close() = scope.cancel()
    }

    @Test fun `ambiguous dispatch stores the exact original command instead of resigning it`() = runBlocking {
        val f = Fixture()
        try {
            f.gateway.onCommand = { throw IOException("response lost") }
            f.controller.submit(VanOwnerCommand("halt trading", VanCommandSource.QUICK_ACTION,
                clientContext = mapOf("owner_halt_authority_ref" to "signed-owner-reference")))
            f.submitted()
            val original = JSONObject(f.gateway.preparedCommands.single())
            val saved = JSONObject(f.saved.single())
            for (key in original.keySet()) assertEquals(original.get(key).toString(), saved.get(key).toString(), key)
            assertEquals(VanCommandStatus.QUEUED, f.controller.state.value.messages.last().status)
        } finally { f.close() }
    }

    @Test fun `a lost server error remains recoverable but an authenticated refusal is never queued`() = runBlocking {
        for ((code, storable) in listOf(503 to true, 408 to true, 403 to false, 409 to false)) {
            val f = Fixture()
            try {
                f.gateway.onCommand = { throw GatewayHttpException(code, "{}") }
                f.controller.submitText("read status", VanCommandSource.CHAT)
                f.submitted()
                assertEquals(storable, f.saved.isNotEmpty(), "HTTP $code")
            } finally { f.close() }
        }
    }

    @Test fun `overlapping polls append and speak a terminal answer only once`() = runBlocking {
        val f = Fixture()
        try {
            f.controller.submitText("read status", VanCommandSource.VOICE, turnId = "voice-turn")
            f.submitted()
            val release = CompletableDeferred<Unit>()
            f.gateway.onStatus = { release.await(); JSONObject().put("owner_status", "DONE").put("finished", true)
                .put("final_outcome", "The gateway is healthy") }
            List(20) { launch(Dispatchers.Default) { f.controller.pollUnfinishedCommands() } }.joinAll()
            await { f.gateway.statusCalls.get() == 1 }
            release.complete(Unit)
            await { f.spoken.size == 1 }
            assertEquals(1, f.controller.state.value.messages.count { it.text == "The gateway is healthy" })
            f.controller.pollUnfinishedCommands()
            delay(40)
            assertEquals(1, f.gateway.statusCalls.get())
        } finally { f.close() }
    }

    @Test fun `intermediate status changes do not multiply pending copies of the same command`() = runBlocking {
        val f = Fixture()
        try {
            f.controller.submitText("read status", VanCommandSource.CHAT)
            f.submitted()
            f.gateway.onStatus = { JSONObject().put("owner_status", "WAITING_ON_SOMETHING_ELSE").put("finished", false)
                .put("sentence", "Checking the result") }
            f.controller.pollUnfinishedCommands()
            await { f.controller.state.value.messages.any { it.text == "Checking the result" } }
            f.gateway.onStatus = { JSONObject().put("owner_status", "DONE").put("finished", true).put("final_outcome", "Checked") }
            f.controller.pollUnfinishedCommands()
            await { f.controller.state.value.messages.any { it.text == "Checked" } }
            assertEquals(2, f.gateway.statusCalls.get())
            assertEquals(1, f.controller.state.value.messages.count { it.text == "Checked" })
            assertTrue(f.spoken.isEmpty())
        } finally { f.close() }
    }

    @Test fun `gateway upgraded A4 approval cannot be stored after its receipt is lost`() = runBlocking {
        val f = Fixture()
        try {
            f.gateway.onCommand = { approval() }
            f.controller.submitText("send this message", VanCommandSource.CHAT, actionClass = "A1")
            f.submitted()
            val pending = assertNotNull(f.controller.state.value.pendingA4Approval)
            assertEquals("recipient@example.test", JSONObject(pending.resolvedParametersJson!!).getString("recipient"))
            f.gateway.onCommand = { throw IOException("approval execution response lost") }
            f.controller.approvePendingA4(FragmentActivity())
            await { f.gateway.commandCalls.get() == 2 && !f.controller.state.value.submitting }
            assertTrue(f.saved.isEmpty(), "a biometric proof was queued after the action was upgraded from A1 to A4")
            assertTrue(f.controller.state.value.messages.last().text.contains("may already have happened"))
        } finally { f.close() }
    }

    @Test fun `Gmail send cannot bypass challenge bound content review on another screen`() = runBlocking {
        val f = Fixture()
        try {
            val digest = "a".repeat(64)
            f.gateway.onCommand = { approval().put("resolved_action_id", "google.gmail.send")
                .put("resolved_parameters", JSONObject().put("draft_id", "D-1").put("draft_content_sha256", digest)) }
            f.controller.submitText("send draft D-1", VanCommandSource.CHAT)
            f.submitted()
            f.controller.approvePendingA4(FragmentActivity())
            assertEquals(1, f.gateway.commandCalls.get())
            assertTrue(f.controller.state.value.lastError!!.contains("Review"))
            f.controller.approvePendingA4(FragmentActivity(), "b".repeat(64))
            assertEquals(1, f.gateway.commandCalls.get())
            f.gateway.onCommand = { JSONObject().put("status", "accepted").put("command_id", "approved-send") }
            f.controller.approvePendingA4(FragmentActivity(), digest)
            await { f.gateway.commandCalls.get() == 2 && !f.controller.state.value.submitting }
        } finally { f.close() }
    }

    @Test fun `declining a stale approval cannot discard a newer challenge`() = runBlocking {
        val f = Fixture()
        try {
            f.gateway.onCommand = { approval() }
            f.controller.submitText("send this message", VanCommandSource.CHAT)
            f.submitted()
            f.controller.discardPendingA4("stale-challenge")
            assertNotNull(f.controller.state.value.pendingA4Approval)
            f.controller.discardPendingA4("approval-test-challenge")
            assertNull(f.controller.state.value.pendingA4Approval)
            assertEquals(1, f.gateway.commandCalls.get())
            assertFalse(f.controller.state.value.submitting)
        } finally { f.close() }
    }

    private companion object {
        suspend fun await(predicate: () -> Boolean) = withTimeout(5_000) { while (!predicate()) delay(5) }
        fun approval() = JSONObject().put("status", "approval_required").put("command_id", "approval-source")
            .put("approval_challenge_id", "approval-test-challenge").put("approval_challenge", "opaque-exact-action-challenge")
            .put("approval_expires_at_unix", System.currentTimeMillis() / 1000L + 60)
            .put("resolved_action_id", "message.send").put("effective_action_class", "A4")
            .put("resolved_parameters", JSONObject().put("recipient", "recipient@example.test"))
    }
}
