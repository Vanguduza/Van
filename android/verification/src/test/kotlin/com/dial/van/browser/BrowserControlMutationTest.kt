package com.dial.van.browser

import java.io.IOException
import java.util.concurrent.Callable
import java.util.concurrent.Executors
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

class BrowserControlMutationTest {
    @Test fun `repeated concurrent taps admit one unkeyed control mutation and old completion cannot clear a new one`() {
        val gate = BrowserControlMutation.PendingGate()
        val pool = Executors.newFixedThreadPool(8)
        try {
            val attempts = pool.invokeAll((0 until 32).map { Callable { gate.acquire() } }).map { it.get() }
            val first = attempts.filterNotNull().single()
            assertTrue(gate.isPending)
            assertNull(gate.acquire())
            assertTrue(gate.release(first))
            val next = gate.acquire()!!
            assertFalse(gate.release(first))
            assertTrue(gate.isPending)
            assertTrue(gate.release(next))
            assertFalse(gate.isPending)
        } finally { pool.shutdownNow() }
    }

    @Test fun `cancelled request retains confirmed authority with unknown outcome and input held`() {
        val cancelled = BrowserControlMutation.cancelled("take control")
        assertSame(previous, cancelled.snapshotOr(previous))
        assertTrue(cancelled.outcomeUnknown)
        assertTrue(cancelled.inputHeld)
        assertTrue(cancelled.error!!.contains("may already have been applied"))
        assertFalse(BrowserControlMutation.mayActuate(owner, true, cancelled.inputHeld))
        assertFalse(BrowserControlMutation.mayRequestControl(previous, cancelled.inputHeld, false))
    }

    @Test fun `control requests require current agent state and hold while pending or uncertain`() {
        assertTrue(BrowserControlMutation.mayRequestControl(previous, false, false))
        assertFalse(BrowserControlMutation.mayRequestControl(previous, false, true))
        assertFalse(BrowserControlMutation.mayRequestControl(previous, true, false))
        assertFalse(BrowserControlMutation.mayRequestControl(owner, false, false))
        assertFalse(BrowserControlMutation.mayRequestControl(previous.copy(state = BrowserSessionState.TERMINATED), false, false))
    }

    @Test fun `late heartbeat cannot replace newer confirmed control or viewport identity`() {
        assertTrue(BrowserControlMutation.mayReplaceSnapshot(previous, owner))
        assertFalse(BrowserControlMutation.mayReplaceSnapshot(owner, previous))
        assertFalse(BrowserControlMutation.mayReplaceSnapshot(owner, owner.copy(sessionId = "another-session")))
        assertFalse(BrowserControlMutation.mayReplaceSnapshot(owner, owner.copy(viewport = owner.viewport.copy(revision = 3))))
        assertTrue(BrowserControlMutation.mayReplaceSnapshot(owner, owner.copy(viewport = owner.viewport.copy(revision = 5))))
    }
    private val previous = BrowserSessionSnapshot("browser-1", BrowserSessionState.AGENT_CONTROLLED,
        "owner", BrowserViewport(800, 600, 1f, 4), 4, BrowserControlHolder.HERMES_DETERMINISTIC,
        "agent-lease", 2, null, null, false, null)
    private val owner = previous.copy(state = BrowserSessionState.INTERACTIVE,
        controlHolder = BrowserControlHolder.OWNER, controlLeaseId = "owner-lease", controlGeneration = 3)
    private fun controlReceipt() = JSONObject().put("holder", "OWNER")
        .put("control_lease_id", "owner-lease").put("control_generation", 3)

    @Test fun `take control changes authority only after matching receipt and readback`() = runBlocking {
        var requests = 0
        var reads = 0
        val result = BrowserControlMutation.takeControl(previous,
            request = { requests++; controlReceipt() }, read = { reads++; owner })
        assertSame(owner, result.confirmedSnapshot)
        assertNull(result.error)
        assertFalse(result.outcomeUnknown)
        assertFalse(result.inputHeld)
        assertTrue(BrowserControlMutation.mayActuate(result.snapshotOr(previous), true, result.inputHeld))
        assertEquals(1, requests)
        assertEquals(1, reads)
    }

    @Test fun `refused take control retains latest confirmed state without readback or retry`() = runBlocking {
        var requests = 0
        var reads = 0
        val result = BrowserControlMutation.takeControl(previous,
            request = { requests++; throw IllegalStateException("refused") }, read = { reads++; owner })
        val newerConfirmed = previous.copy(controlGeneration = 4)
        assertSame(newerConfirmed, result.snapshotOr(newerConfirmed))
        assertFalse(result.outcomeUnknown)
        assertTrue(result.error!!.contains("Could not take control"))
        assertEquals(1, requests)
        assertEquals(0, reads)
    }

    @Test fun `lost mutation reply and lost confirmation read stay unknown with one mutation attempt`() = runBlocking {
        for (loseMutationReply in listOf(true, false)) {
            var requests = 0
            var reads = 0
            val result = BrowserControlMutation.takeControl(previous, request = {
                requests++ // The remote preemption has already committed.
                if (loseMutationReply) throw IOException("reply lost")
                controlReceipt()
            }, read = { reads++; throw IOException("confirmation unavailable") })
            assertSame(previous, result.snapshotOr(previous))
            assertTrue(result.outcomeUnknown)
            assertTrue(result.error!!.contains("may already have been applied"))
            assertEquals(1, requests)
            assertEquals(if (loseMutationReply) 0 else 1, reads)
        }
    }

    @Test fun `pause and close require the same session and their observed states`() = runBlocking {
        val paused = owner.copy(state = BrowserSessionState.SUSPENDED)
        val closed = owner.copy(state = BrowserSessionState.TERMINATED)
        assertSame(paused, BrowserControlMutation.suspendSession(owner) { paused }.confirmedSnapshot)
        assertSame(closed, BrowserControlMutation.close(owner) { closed }.confirmedSnapshot)
        for (result in listOf(
            BrowserControlMutation.suspendSession(owner) { owner },
            BrowserControlMutation.close(owner) { paused },
            BrowserControlMutation.close(owner) { closed.copy(sessionId = "another-browser") },
            BrowserControlMutation.suspendSession(owner) { throw IOException("lost pause reply") },
            BrowserControlMutation.close(owner) { throw IOException("lost close reply") },
        )) {
            assertSame(owner, result.snapshotOr(owner))
            assertTrue(result.outcomeUnknown)
            assertTrue(result.inputHeld)
            assertFalse(BrowserControlMutation.mayActuate(result.snapshotOr(owner), true, result.inputHeld))
            assertTrue(result.error!!.startsWith("Could not"))
        }
        val refused = BrowserControlMutation.suspendSession(owner) { throw IllegalStateException("explicit refusal") }
        assertFalse(refused.outcomeUnknown)
        assertTrue(refused.inputHeld)
        assertFalse(BrowserControlMutation.mayActuate(refused.snapshotOr(owner), true, refused.inputHeld))
    }

    @Test fun `viewport acknowledgement opens the input gate only for exact session revision receipt`() = runBlocking {
        val resized = owner.copy(viewport = owner.viewport.copy(revision = 5))
        assertFalse(resized.mayActuate)
        fun receipt(id: String = resized.sessionId, revision: Int = 5) = JSONObject()
            .put("session_id", id).put("acked_viewport_revision", revision)
        val accepted = BrowserControlMutation.acknowledgeViewport(resized) { receipt() }
        assertTrue(accepted.confirmedSnapshot!!.mayActuate)
        for (result in listOf(
            BrowserControlMutation.acknowledgeViewport(resized) { receipt(revision = 4) },
            BrowserControlMutation.acknowledgeViewport(resized) { receipt(id = "another-browser") },
            BrowserControlMutation.acknowledgeViewport(resized) { throw IOException("lost ack") },
        )) {
            assertSame(resized, result.snapshotOr(resized))
            assertFalse(result.snapshotOr(resized).mayActuate)
            assertTrue(result.outcomeUnknown)
        }
    }

    @Test fun `control receipt cannot certify another holder session lease or old generation`() = runBlocking {
        for (readback in listOf(owner.copy(sessionId = "other"), owner.copy(controlHolder = BrowserControlHolder.HERMES_STAGEHAND),
            owner.copy(controlLeaseId = "another-lease"), owner.copy(controlGeneration = previous.controlGeneration))) {
            val result = BrowserControlMutation.takeControl(previous, { controlReceipt() }, { readback })
            assertSame(previous, result.snapshotOr(previous))
            assertTrue(result.outcomeUnknown)
        }
    }

    @Test fun `cancellation propagates through controls and shared result capture`() = runBlocking {
        val cancelled = CancellationException("owner left")
        assertSame(cancelled, assertFailsWith<CancellationException> {
            BrowserControlMutation.takeControl(previous, { throw cancelled }, { owner })
        })
        assertSame(cancelled, assertFailsWith<CancellationException> {
            BrowserControlMutation.suspendSession(owner) { throw cancelled }
        })
        assertSame(cancelled, assertFailsWith<CancellationException> {
            BrowserControlMutation.close(owner) { throw cancelled }
        })
        assertSame(cancelled, assertFailsWith<CancellationException> {
            BrowserControlMutation.acknowledgeViewport(owner) { throw cancelled }
        })
        assertSame(cancelled, assertFailsWith<CancellationException> {
            BrowserControlMutation.capture { throw cancelled }
        })
    }
    @Test fun `delegation requires confirmed owner session with existing linked mission`() {
        val linked = owner.copy(missionId = "mission-1", controlDelegateIssuedFor = "van-trading-core")
        assertTrue(BrowserControlMutation.mayDelegate(linked, false, false))
        assertFalse(BrowserControlMutation.mayDelegate(owner, false, false))
        assertFalse(BrowserControlMutation.mayDelegate(linked.copy(controlDelegateIssuedFor = null), false, false))
        assertFalse(BrowserControlMutation.mayDelegate(linked, true, false))
        assertFalse(BrowserControlMutation.mayDelegate(linked, false, true))
        assertFalse(BrowserControlMutation.mayDelegate(previous.copy(missionId = "mission-1"), false, false))
    }

    @Test fun `delegation confirms exact agent lease mission and generation before replacing authority`() = runBlocking {
        val linked = owner.copy(missionId = "mission-1", controlDelegateIssuedFor = "van-trading-core")
        val agent = linked.copy(state = BrowserSessionState.AGENT_CONTROLLED,
            controlHolder = BrowserControlHolder.HERMES_STAGEHAND, controlLeaseId = "new-agent", controlGeneration = 4)
        fun receipt() = JSONObject().put("holder", "HERMES_STAGEHAND")
            .put("control_lease_id", "new-agent").put("control_generation", 4)
        val result = BrowserControlMutation.delegate(linked, BrowserControlHolder.HERMES_STAGEHAND,
            request = { receipt() }, read = { agent })
        assertSame(agent, result.confirmedSnapshot)
        assertFalse(result.inputHeld)
        for (mismatch in listOf(agent.copy(controlLeaseId = "old-agent"), agent.copy(missionId = "other"),
            agent.copy(controlHolder = BrowserControlHolder.HERMES_DETERMINISTIC), agent.copy(controlGeneration = 3))) {
            val refused = BrowserControlMutation.delegate(linked, BrowserControlHolder.HERMES_STAGEHAND,
                request = { receipt() }, read = { mismatch })
            assertNull(refused.confirmedSnapshot)
            assertTrue(refused.outcomeUnknown)
            assertTrue(refused.inputHeld)
            assertSame(linked, refused.snapshotOr(linked))
        }
    }

    @Test fun `lost handoff readback is unknown and mutation is not retried`() = runBlocking {
        var requests = 0
        val linked = owner.copy(missionId = "mission-1", controlDelegateIssuedFor = "van-trading-core")
        val result = BrowserControlMutation.delegate(linked, BrowserControlHolder.HERMES_DETERMINISTIC,
            request = { requests++; JSONObject() }, read = { throw IOException("readback lost") })
        assertEquals(1, requests)
        assertTrue(result.outcomeUnknown)
        assertTrue(result.inputHeld)
        assertNull(result.confirmedSnapshot)
    }

    @Test fun `resume requires renewed owner lease generation and independent readback`() = runBlocking {
        val suspended = owner.copy(state = BrowserSessionState.SUSPENDED)
        val resumed = owner.copy(state = BrowserSessionState.CONNECTING, controlGeneration = 4,
            controlLeaseId = "renewed-owner", ackedViewportRevision = null)
        val result = BrowserControlMutation.resume(suspended, request = { resumed }, read = { resumed })
        assertSame(resumed, result.confirmedSnapshot)
        assertNull(result.error)
        for (wrong in listOf(resumed.copy(controlGeneration = 3), resumed.copy(controlLeaseId = "other"),
            resumed.copy(state = BrowserSessionState.SUSPENDED), resumed.copy(profileAlias = "other"))) {
            val failure = BrowserControlMutation.resume(suspended, request = { resumed }, read = { wrong })
            assertNull(failure.confirmedSnapshot)
            assertTrue(failure.inputHeld)
        }
    }

    @Test fun `rendered viewport acknowledgment requires exact peer frame proof and independent usable state`() = runBlocking {
        val pending = owner.copy(state = BrowserSessionState.CONNECTING, ackedViewportRevision = null)
        val binding = BrowserStreamMetadata.Binding(pending.sessionId, pending.controlGeneration, 4, 800, 600, "peer-1")
        val frame = BrowserStreamMetadata.RenderedFrame(binding, 7)
        fun receipt() = JSONObject().put("session_id", pending.sessionId).put("acked_viewport_revision", 4)
            .put("media_epoch", "peer-1").put("frame_sequence", 7)
        val result = BrowserControlMutation.acknowledgeRenderedViewport(pending, frame,
            request = { receipt() }, read = { owner })
        assertSame(owner, result.confirmedSnapshot)
        assertFalse(result.inputHeld)
        for (broken in listOf(receipt().put("media_epoch", "old-peer"), receipt().put("frame_sequence", 6),
            receipt().put("acked_viewport_revision", 3))) {
            val unknown = BrowserControlMutation.acknowledgeRenderedViewport(pending, frame,
                request = { broken }, read = { owner })
            assertNull(unknown.confirmedSnapshot)
            assertTrue(unknown.inputHeld)
        }
        val unavailable = BrowserControlMutation.acknowledgeRenderedViewport(pending, frame,
            request = { receipt() }, read = { owner.copy(state = BrowserSessionState.SUSPENDED) })
        assertNull(unavailable.confirmedSnapshot)
        assertTrue(unavailable.outcomeUnknown)
    }

}
