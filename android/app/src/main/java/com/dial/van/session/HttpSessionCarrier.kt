package com.dial.van.session

import java.io.IOException
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject

/** POST + SSE adapter preserves the manager's one envelope/ack/reducer boundary. */
class HttpSessionCarrier(
    private val initialRequest: Request,
    parent: CoroutineScope,
    private val listener: WebSocketListener,
    private val post: suspend (JSONObject) -> JSONObject,
    private val downstream: () -> Flow<JSONObject>,
) : WebSocket {
    private val job = SupervisorJob(parent.coroutineContext[Job])
    private val scope = CoroutineScope(parent.coroutineContext + job + Dispatchers.IO)
    private val outgoing = Channel<String>(64)
    private val bytes = AtomicLong()
    @Volatile private var closed = false

    fun start() {
        scope.launch {
            try {
                var opened = false
                downstream().collect { frame ->
                    if (!opened) {
                        // The first marker is emitted only after authenticated HTTP 200.
                        opened = true
                        listener.onOpen(this@HttpSessionCarrier, Response.Builder().request(initialRequest)
                            .protocol(Protocol.HTTP_1_1).code(200).message("SSE admitted").build())
                    } else listener.onMessage(this@HttpSessionCarrier,
                        JSONObject().put("direction", "DOWNSTREAM").put("event", frame).toString())
                }
                throw IOException("session_events_stream_closed")
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { fail(failure) }
        }
        scope.launch {
            try {
                for (text in outgoing) {
                    bytes.addAndGet(-text.toByteArray().size.toLong())
                    val envelope = JSONObject(text)
                    val answer = post(envelope).put("message_id", envelope.getString("message_id"))
                    listener.onMessage(this@HttpSessionCarrier, answer.toString())
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { fail(failure) }
        }
    }

    @Synchronized private fun fail(failure: Exception) {
        if (closed) return
        closed = true
        listener.onFailure(this, failure, null)
        outgoing.close()
        job.cancel()
    }

    override fun request(): Request = initialRequest
    override fun queueSize(): Long = bytes.get()
    @Synchronized override fun send(text: String): Boolean {
        if (closed) return false
        val size = text.toByteArray().size.toLong()
        bytes.addAndGet(size)
        if (outgoing.trySend(text).isSuccess) return true
        bytes.addAndGet(-size)
        return false
    }
    override fun send(bytes: ByteString): Boolean = false
    @Synchronized override fun close(code: Int, reason: String?): Boolean {
        if (closed) return false
        closed = true
        outgoing.close()
        job.cancel()
        listener.onClosed(this, code, reason.orEmpty())
        return true
    }
    @Synchronized override fun cancel() { closed = true; outgoing.close(); job.cancel() }
}
