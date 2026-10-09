package com.dial.van.browser

import java.io.IOException
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.CancellationException
import org.json.JSONObject

/** One request, with observed confirmation; a lost reply never invents changed authority. */
object BrowserControlMutation {
    /** One unkeyed authority mutation at a time, including repeated taps and lifecycle calls. */
    class PendingGate {
        class Lease internal constructor()
        private val current = AtomicReference<Lease?>(null)
        val isPending: Boolean get() = current.get() != null
        fun acquire(): Lease? = Lease().takeIf { current.compareAndSet(null, it) }
        fun release(lease: Lease): Boolean = current.compareAndSet(lease, null)
    }
    data class Outcome(
        val confirmedSnapshot: BrowserSessionSnapshot? = null,
        val error: String? = null,
        val outcomeUnknown: Boolean = false,
    ) {
        fun snapshotOr(current: BrowserSessionSnapshot) = confirmedSnapshot ?: current
        val inputHeld: Boolean get() = error != null
    }

    fun mayActuate(snapshot: BrowserSessionSnapshot, mediaLive: Boolean, controlUnconfirmed: Boolean): Boolean =
        snapshot.mayActuate && mediaLive && !controlUnconfirmed

    fun mayRequestControl(snapshot: BrowserSessionSnapshot, controlUnconfirmed: Boolean, pending: Boolean): Boolean =
        snapshot.state.acceptsInput && snapshot.controlHolder.isAgent && !controlUnconfirmed && !pending

    fun mayDelegate(snapshot: BrowserSessionSnapshot, controlUnconfirmed: Boolean, pending: Boolean): Boolean =
        snapshot.state == BrowserSessionState.INTERACTIVE && snapshot.controlHolder == BrowserControlHolder.OWNER &&
            !snapshot.missionId.isNullOrBlank() && !snapshot.controlDelegateIssuedFor.isNullOrBlank() && !controlUnconfirmed && !pending

    fun mayReplaceSnapshot(current: BrowserSessionSnapshot, fresh: BrowserSessionSnapshot): Boolean =
        fresh.sessionId == current.sessionId && fresh.controlGeneration >= current.controlGeneration &&
            fresh.viewport.revision >= current.viewport.revision

    fun cancelled(action: String): Outcome = Outcome(
        error = "The request to $action was interrupted. It may already have been applied; check the browser state before trying again.",
        outcomeUnknown = true,
    )

    private class UnconfirmedReceipt : IllegalStateException()

    inline fun <T> capture(call: () -> T): Result<T> = try {
        Result.success(call())
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (failure: Exception) {
        Result.failure(failure)
    }

    private suspend fun perform(action: String, call: suspend () -> BrowserSessionSnapshot): Outcome = try {
        Outcome(confirmedSnapshot = call())
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (failure: Exception) {
        val unknown = failure is IOException || failure is UnconfirmedReceipt
        Outcome(error = if (unknown) {
            "Could not confirm $action. The request may already have been applied; check the browser state before trying again."
        } else {
            "Could not $action. The last confirmed browser state is still shown."
        }, outcomeUnknown = unknown)
    }

    suspend fun takeControl(
        previous: BrowserSessionSnapshot,
        request: suspend () -> JSONObject,
        read: suspend () -> BrowserSessionSnapshot,
    ): Outcome = perform("take control") {
        val receipt = request()
        val fresh = read()
        if (fresh.sessionId != previous.sessionId || fresh.controlHolder != BrowserControlHolder.OWNER ||
            fresh.controlLeaseId.isNullOrBlank() || fresh.controlLeaseId != receipt.optString("control_lease_id") ||
            fresh.controlGeneration != receipt.optInt("control_generation", -1) ||
            fresh.controlGeneration <= previous.controlGeneration ||
            receipt.optString("holder") != BrowserControlHolder.OWNER.name) throw UnconfirmedReceipt()
        fresh
    }

    suspend fun resume(previous: BrowserSessionSnapshot, request: suspend () -> BrowserSessionSnapshot,
        read: suspend () -> BrowserSessionSnapshot): Outcome = perform("resume the browser") {
        if (previous.state != BrowserSessionState.SUSPENDED) throw UnconfirmedReceipt()
        val receipt = request()
        val fresh = read()
        if (fresh.sessionId != previous.sessionId || fresh.profileAlias != previous.profileAlias ||
            fresh.controlHolder != BrowserControlHolder.OWNER || fresh.controlLeaseId.isNullOrBlank() ||
            fresh.controlGeneration <= previous.controlGeneration || fresh.controlGeneration != receipt.controlGeneration ||
            fresh.controlLeaseId != receipt.controlLeaseId || fresh.state !in setOf(BrowserSessionState.CONNECTING,
                BrowserSessionState.RECONNECTING, BrowserSessionState.INTERACTIVE) || fresh.viewport.revision < previous.viewport.revision)
            throw UnconfirmedReceipt()
        fresh
    }

    /** A handoff is confirmed only by the exact new agent lease, never by an HTTP success alone. */
    suspend fun delegate(
        previous: BrowserSessionSnapshot,
        holder: BrowserControlHolder,
        request: suspend () -> JSONObject,
        read: suspend () -> BrowserSessionSnapshot,
    ): Outcome = perform("hand browser control to VAN") {
        require(holder.isAgent && !previous.missionId.isNullOrBlank())
        val receipt = request()
        val fresh = read()
        if (fresh.sessionId != previous.sessionId || fresh.missionId != previous.missionId ||
            fresh.state != BrowserSessionState.AGENT_CONTROLLED || fresh.controlHolder != holder ||
            fresh.controlLeaseId.isNullOrBlank() || fresh.controlLeaseId != receipt.optString("control_lease_id") ||
            fresh.controlGeneration != receipt.optInt("control_generation", -1) ||
            fresh.controlGeneration <= previous.controlGeneration || receipt.optString("holder") != holder.name) throw UnconfirmedReceipt()
        fresh
    }

    suspend fun suspendSession(previous: BrowserSessionSnapshot, request: suspend () -> BrowserSessionSnapshot): Outcome =
        perform("pause the browser") {
            request().also {
                if (it.sessionId != previous.sessionId || it.state != BrowserSessionState.SUSPENDED) throw UnconfirmedReceipt()
            }
        }

    suspend fun close(previous: BrowserSessionSnapshot, request: suspend () -> BrowserSessionSnapshot): Outcome =
        perform("close the remote browser") {
            request().also {
                if (it.sessionId != previous.sessionId || !it.state.isTerminal) throw UnconfirmedReceipt()
            }
        }

    suspend fun acknowledgeViewport(
        previous: BrowserSessionSnapshot,
        request: suspend () -> JSONObject,
    ): Outcome = perform("confirm the browser size") {
        val receipt = request()
        if (receipt.optString("session_id") != previous.sessionId ||
            receipt.optInt("acked_viewport_revision", -1) != previous.viewport.revision) throw UnconfirmedReceipt()
        previous.copy(ackedViewportRevision = previous.viewport.revision)
    }

    suspend fun acknowledgeRenderedViewport(previous: BrowserSessionSnapshot,
        frame: BrowserStreamMetadata.RenderedFrame, request: suspend () -> JSONObject,
        read: suspend () -> BrowserSessionSnapshot): Outcome = perform("confirm the rendered browser size") {
        val binding = frame.binding
        require(binding.sessionId == previous.sessionId && binding.controlGeneration == previous.controlGeneration &&
            binding.viewportRevision == previous.viewport.revision && binding.width == previous.viewport.width &&
            binding.height == previous.viewport.height && frame.frameSequence > 0)
        val receipt = request()
        if (receipt.optString("session_id") != previous.sessionId ||
            receipt.optInt("acked_viewport_revision", -1) != binding.viewportRevision ||
            receipt.optString("media_epoch") != binding.mediaEpoch ||
            receipt.optLong("frame_sequence", -1) != frame.frameSequence) throw UnconfirmedReceipt()
        val fresh = read()
        if (fresh.sessionId != previous.sessionId || fresh.controlGeneration != binding.controlGeneration ||
            fresh.viewport.revision != binding.viewportRevision || fresh.ackedViewportRevision != binding.viewportRevision ||
            fresh.viewport.width != binding.width || fresh.viewport.height != binding.height || !fresh.state.acceptsInput) throw UnconfirmedReceipt()
        fresh
    }
}
