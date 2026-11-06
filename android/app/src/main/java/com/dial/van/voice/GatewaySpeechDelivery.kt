package com.dial.van.voice

import com.dial.van.control.SpokenCommandResult
import java.security.MessageDigest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject

/** A definitive server refusal of the current speech source, distinct from a lost report. */
class SpeechSourceRefused(val status: Int) : IllegalStateException("speech_source_refused:$status")

/** The authenticated wire answer, validated before any words enter a playback queue. */
data class BoundSpeechResponse(
    val commandId: String,
    val resultRef: String,
    val responseId: String,
    val streamId: String,
    val heard: Int,
    val interrupted: Boolean,
    val segments: List<SpeechSegment>,
) {
    companion object {
        fun parse(json: JSONObject): BoundSpeechResponse {
            fun nonempty(key: String) = json.getString(key).also { require(it.isNotBlank()) }
            fun integer(obj: JSONObject, key: String): Int = obj.get(key).let {
                require(it is Int || it is Long)
                val number = (it as Number).toLong()
                require(number in Int.MIN_VALUE..Int.MAX_VALUE)
                number.toInt()
            }
            val command = nonempty("command_id")
            val ref = nonempty("result_ref")
            val response = nonempty("response_id")
            val stream = nonempty("speech_stream_id")
            val heard = integer(json, "last_spoken_segment")
            val received = integer(json, "last_received_segment")
            val total = integer(json, "total_segments")
            require(total > 0 && heard >= -1 && heard <= received && received < total)
            val interrupted = json.get("interrupted").also { require(it is Boolean) } as Boolean
            val array = json.getJSONArray("segments")
            val segments = (0 until array.length()).map { index ->
                val item = array.getJSONObject(index)
                require(item.getString("response_id") == response && item.getString("speech_stream_id") == stream)
                val text = item.getString("text").also { require(it.isNotBlank()) }
                val digest = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))
                    .joinToString("") { "%02x".format(it) }
                require(item.getString("content_digest") == digest)
                val segmentIndex = integer(item, "segment_index")
                require(segmentIndex == heard + 1 + index && segmentIndex < total)
                val id = item.getString("segment_id").also { require(it.isNotBlank()) }
                val final = item.get("final").also { require(it is Boolean) } as Boolean
                require(final == (segmentIndex == total - 1))
                val interruptible = item.get("interruptible").also { require(it is Boolean) } as Boolean
                SpeechSegment(response, stream, id, segmentIndex, text, final, interruptible,
                    digest, cueTiming = SegmentCueTiming.fromJson(item.optJSONObject("cue_timing")))
            }
            require(segments.map { it.segmentId }.distinct().size == segments.size)
            require(if (interrupted) segments.isEmpty() else segments.size == total - heard - 1)
            return BoundSpeechResponse(command, ref, response, stream, heard, interrupted, segments)
        }
    }
}

/** Uses the provisioned gateway client; no endpoint, key, or provider settings live here. */
class GatewaySpeechDelivery(
    private val scope: CoroutineScope,
    private val current: (SpokenCommandResult) -> Boolean,
    private val open: suspend (SpokenCommandResult) -> JSONObject,
    private val read: suspend (String) -> JSONObject,
    private val report: suspend (SpeechCursors) -> Unit,
    private val interrupt: suspend (String) -> Unit,
    private val play: (BoundSpeechResponse) -> Unit,
    private val stop: () -> Unit,
    private val cursors: () -> SpeechCursors,
) {
    private var active: SpokenCommandResult? = null
    private var streamId: String? = null
    private var opening: Job? = null
    private val network = Mutex()
    private val _failure = MutableStateFlow<String?>(null)
    val failure = _failure.asStateFlow()

    fun deliver(request: SpokenCommandResult) {
        cancel()
        if (!current(request)) return
        active = request
        _failure.value = null
        opening = scope.launch {
            try { adopt(request, BoundSpeechResponse.parse(open(request))) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) {
                if (active === request) _failure.value = "I couldn't deliver this answer aloud. It is in the conversation."
            }
        }
    }

    private fun adopt(request: SpokenCommandResult, response: BoundSpeechResponse) {
        if (active !== request || !current(request)) {
            scope.launch { safely { interrupt(response.streamId) } }
            return
        }
        require(response.commandId == request.commandId)
        require(request.resultRef == null || response.resultRef == request.resultRef)
        require(streamId == null || streamId == response.streamId)
        streamId = response.streamId
        if (response.interrupted) cancel() else play(response)
    }

    /** Local cancellation is immediate; a lost interrupt reply cannot restart local speech. */
    fun cancel() {
        active = null
        opening?.cancel()
        opening = null
        val previous = streamId
        streamId = null
        stop()
        if (previous != null) scope.launch { network.withLock { safely { interrupt(previous) } } }
    }

    fun playbackFailed() {
        if (active != null) _failure.value = "Audio playback failed. The answer remains in the conversation."
    }

    fun mayContinue(id: String?): Boolean = id != streamId || active?.let(current) == true

    fun progress(value: SpeechCursors, stopped: Boolean) {
        val id = streamId ?: return
        if (active?.let(current) != true) { cancel(); return }
        if (value.speechStreamId != id) return
        scope.launch {
            network.withLock {
                try { report(value) }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (refused: SpeechSourceRefused) {
                    if (streamId == id) {
                        cancel()
                        _failure.value = "This spoken result changed or is no longer available. Check the conversation."
                    }
                }
                catch (_: Exception) { /* Retry the local heard cursor after transport recovery. */ }
                if (stopped) safely { interrupt(id) }
            }
        }
    }

    /** Reconcile the real local heard cursor before asking for anything to be resent. */
    fun reconnect() {
        val request = active ?: return
        if (!current(request)) { cancel(); return }
        val id = streamId
        if (id == null) { deliver(request); return }
        val local = cursors()
        scope.launch {
            try {
                val response = network.withLock {
                    if (local.speechStreamId == id) report(local)
                    BoundSpeechResponse.parse(read(id))
                }
                adopt(request, response)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) {
                if (active === request) {
                    stop()
                    _failure.value = "Speech could not resume safely. The answer remains in the conversation."
                }
            }
        }
    }

    private suspend fun safely(action: suspend () -> Unit) {
        try { action() }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { /* Local heard/interrupted facts survive a failed report. */ }
    }
}
