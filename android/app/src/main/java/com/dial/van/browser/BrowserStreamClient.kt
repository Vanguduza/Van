package com.dial.van.browser

import android.content.Context
import com.dial.van.telemetry.DecoderStats
import com.dial.van.telemetry.DeviceTelemetryReporter
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.VideoTrack

/**
 * Rev 1.5 §§6.4, 7, 8 — the media plane, which the Gateway is deliberately not on.
 *
 * §6.4 keeps pixels and input out of the Gateway's path entirely. The Gateway mints a
 * short-lived grant and says where to signal; everything after that is between this phone
 * and the Browser Stream Host. The reason is not performance alone: a Gateway carrying
 * 60fps video is a Gateway whose owner-command path shares a queue with a video stream, and
 * the thing that degrades first is the one that matters most.
 *
 * Two data channels, because §8 needs two guarantees that no single channel provides:
 *
 *  * `input-fast` — unordered, no retransmits. Pointer moves. A move that arrives late is
 *    worse than one that never arrives, because the pointer has already moved on.
 *  * `input-reliable` — ordered and retransmitted. Downs, ups, keys, text. Losing one of
 *    these does not degrade the gesture; it corrupts it — a finger that went down and never
 *    came up leaves the page holding a drag the owner ended seconds ago.
 *
 * Gesture *edges* are sent on both and de-duplicated by the host on `(gesture_id, edge_id)`,
 * which is [BrowserGestureSequencer.duplicateEdge]. That is why the sequencer assigns one
 * edge id to both copies: two ids would be two taps for one finger.
 *
 * None of this is executed by any gate in this repository. WebRTC needs a peer, and the
 * peer is the stream host (RB-002), which does not exist yet. What *is* executed is the
 * wire format — `BrowserInputProtocolTest` in the JVM harness and
 * `tests/contracts/test_browser_input_protocol_matches.py` across the two languages —
 * because that is the part that can be wrong silently. Whether a real S24 negotiates H.264
 * with a real host is a device gate (RB-121) and is recorded as one.
 */
class BrowserStreamClient(
    private val context: Context,
    private val eglBase: EglBase,
    /**
     * Rev 1.5 §28.1 — where the four device-side stream measurements go.
     *
     * Optional because this class is constructed in places that have no reporter, and a
     * required dependency would mean either a second constructor or a null check at every
     * call site. Null means the numbers are not collected, not that they are zero.
     */
    private val telemetry: DeviceTelemetryReporter? = null,
) {

    /** What the surface needs to know, in the owner's terms rather than WebRTC's. */
    enum class Link { CONNECTING, LIVE, RECOVERING, CLOSED, FAILED }

    private var factory: PeerConnectionFactory? = null
    private var peer: PeerConnection? = null
    private var fast: DataChannel? = null
    private var reliable: DataChannel? = null

    @Volatile
    private var link: Link = Link.CLOSED

    fun linkState(): Link = link

    /**
     * Negotiate with the stream host named by [grant] and attach the remote video track.
     *
     * @param onVideo called once the host's video track arrives.
     * @param onLink called on every transition, so the surface can stop accepting input
     *   the moment the link is no longer live. A frozen last frame with live touch handling
     *   is the failure §7 names: the owner keeps tapping a picture.
     */
    suspend fun connect(
        grant: BrowserStreamGrant,
        onVideo: (VideoTrack) -> Unit,
        onLink: (Link) -> Unit,
    ) = withContext(Dispatchers.IO) {
        require(grant.usableAt(System.currentTimeMillis())) { "browser_stream_grant_expired" }
        transition(Link.CONNECTING, onLink)

        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context)
                .createInitializationOptions(),
        )
        val built = PeerConnectionFactory.builder()
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(eglBase.eglBaseContext))
            .setVideoEncoderFactory(
                DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true),
            )
            .createPeerConnectionFactory()
        factory = built

        val config = PeerConnection.RTCConfiguration(
            grant.iceServers.map { server ->
                PeerConnection.IceServer.builder(server.urls)
                    .setUsername(server.username ?: "")
                    .setPassword(server.credential ?: "")
                    .createIceServer()
            },
        ).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            // The host is the only peer and it is reached through the grant's ICE servers.
            // Gathering host candidates on the phone's own interfaces would expose the
            // owner's home network to whatever is on the other end of a relay.
            iceTransportsType = PeerConnection.IceTransportsType.ALL
            bundlePolicy = PeerConnection.BundlePolicy.MAXBUNDLE
            rtcpMuxPolicy = PeerConnection.RtcpMuxPolicy.REQUIRE
        }

        val gathered = CompletableDeferred<Unit>()
        peer = built.createPeerConnection(config, object : PeerObserver() {
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
                // One-shot signalling: the offer is sent once gathering is complete, so
                // there is no trickle channel to keep open. Slower to establish, and it
                // removes an entire long-lived bidirectional path from the design.
                if (state == PeerConnection.IceGatheringState.COMPLETE) gathered.complete(Unit)
            }

            override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) {
                val track = receiver.track() as? VideoTrack ?: return
                // §28.1 — the sink is added before the caller's, so a frame is counted
                // even if the surface it is handed to drops it. What the decoder produced
                // and what the owner saw are different numbers and this one is the first.
                telemetry?.let { reporter -> track.addSink { reporter.recordBrowserFrame() } }
                onVideo(track)
            }

            override fun onConnectionChange(state: PeerConnection.PeerConnectionState) {
                transition(
                    when (state) {
                        PeerConnection.PeerConnectionState.CONNECTED -> Link.LIVE
                        PeerConnection.PeerConnectionState.DISCONNECTED -> Link.RECOVERING
                        PeerConnection.PeerConnectionState.FAILED -> Link.FAILED
                        PeerConnection.PeerConnectionState.CLOSED -> Link.CLOSED
                        else -> Link.CONNECTING
                    },
                    onLink,
                )
            }
        }) ?: run {
            transition(Link.FAILED, onLink)
            return@withContext
        }

        fast = peer?.createDataChannel(
            CHANNEL_FAST,
            DataChannel.Init().apply {
                ordered = false
                maxRetransmits = 0
                negotiated = false
            },
        )
        reliable = peer?.createDataChannel(
            CHANNEL_RELIABLE,
            DataChannel.Init().apply { ordered = true },
        )

        val offer = createOffer()
        setLocal(offer)
        gathered.await()

        val answer = exchange(grant, peer?.localDescription?.description ?: offer.description)
        setRemote(SessionDescription(SessionDescription.Type.ANSWER, answer))
    }

    /**
     * Send one input packet on the channel its kind requires.
     *
     * @return false when the channel is not open, which the caller must treat as "this
     *   input did not happen" rather than retrying: a replayed tap is a second tap.
     */
    fun send(packet: BrowserInputProtocol.Packet): Boolean {
        if (link != Link.LIVE) return false
        val channel = when (packet.channel) {
            BrowserInputProtocol.Channel.FAST -> fast
            BrowserInputProtocol.Channel.RELIABLE -> reliable
        } ?: return false
        if (channel.state() != DataChannel.State.OPEN) return false
        val bytes = BrowserInputProtocol.encode(packet)
        return channel.send(DataChannel.Buffer(ByteBuffer.wrap(bytes), true))
    }

    /**
     * Ask the peer connection what the decoder has dropped, and hand the total on.
     *
     * Polled rather than pushed because WebRTC exposes it only through a stats report,
     * and asked for on the telemetry flush rather than per frame: this is a JNI round
     * trip into the native stack, and sixty of them a second to measure jank would be
     * the jank.
     *
     * The report is converted to plain maps before anything decides what to read from it,
     * so the deciding — which `inbound-rtp` entry is the picture — is in
     * `DecoderStats.framesDropped` where the harness can execute it.
     */
    fun pollDecoderStats() {
        val reporter = telemetry ?: return
        peer?.getStats { report ->
            val entries = report.statsMap.values.map { it.type to it.members }
            DecoderStats.framesDropped(entries)?.let(reporter::recordBrowserDecoderDrops)
        }
    }

    fun close() {
        telemetry?.recordBrowserStreamClosed()
        fast?.close()
        reliable?.close()
        peer?.close()
        peer?.dispose()
        factory?.dispose()
        fast = null
        reliable = null
        peer = null
        factory = null
        link = Link.CLOSED
    }

    private fun transition(next: Link, onLink: (Link) -> Unit) {
        if (link == next) return
        // A recovery the owner did not ask for, counted as it happens. Counting on
        // CONNECTED alone would count the first connection as a reconnect; counting on
        // RECOVERING alone would count a wobble that never came back.
        if (link == Link.RECOVERING && next == Link.LIVE) telemetry?.recordBrowserReconnect()
        if (next == Link.CLOSED || next == Link.FAILED) telemetry?.recordBrowserStreamClosed()
        link = next
        onLink(next)
    }

    // --------------------------------------------------------------------- signalling

    /**
     * §6.3 — the grant is spent here, against the stream host, never against the Gateway.
     *
     * The token is a bearer credential for one session and one device, and it is short
     * lived because this is the only place it is used. A reconnect mints a new one rather
     * than reusing this, which is why `stream-grant` is a separate route from session
     * creation.
     */
    private fun exchange(grant: BrowserStreamGrant, offerSdp: String): String {
        val connection = (URL(grant.signalUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Authorization", "Bearer ${grant.token}")
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 30_000
        }
        val body = JSONObject()
            .put("session_id", grant.sessionId)
            .put("sdp", offerSdp)
            .put("type", "offer")
            .put(
                "data_channels",
                JSONArray(listOf(CHANNEL_FAST, CHANNEL_RELIABLE)),
            )
        connection.outputStream.use { it.write(body.toString().toByteArray(StandardCharsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.readText().orEmpty()
        check(code in 200..299) { "browser_stream_signal_failed_$code: $text" }
        return JSONObject(text).getString("sdp")
    }

    private suspend fun createOffer(): SessionDescription {
        val result = CompletableDeferred<SessionDescription>()
        val constraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
        }
        peer?.createOffer(object : SdpAdapter() {
            override fun onCreateSuccess(description: SessionDescription) {
                result.complete(description)
            }

            override fun onCreateFailure(error: String?) {
                result.completeExceptionally(IllegalStateException("offer_failed: $error"))
            }
        }, constraints)
        return result.await()
    }

    private suspend fun setLocal(description: SessionDescription) {
        val done = CompletableDeferred<Unit>()
        peer?.setLocalDescription(object : SdpAdapter() {
            override fun onSetSuccess() {
                done.complete(Unit)
            }

            override fun onSetFailure(error: String?) {
                done.completeExceptionally(IllegalStateException("set_local_failed: $error"))
            }
        }, description)
        done.await()
    }

    private suspend fun setRemote(description: SessionDescription) {
        val done = CompletableDeferred<Unit>()
        peer?.setRemoteDescription(object : SdpAdapter() {
            override fun onSetSuccess() {
                done.complete(Unit)
            }

            override fun onSetFailure(error: String?) {
                done.completeExceptionally(IllegalStateException("set_remote_failed: $error"))
            }
        }, description)
        done.await()
    }

    companion object {
        const val CHANNEL_FAST = "input-fast"
        const val CHANNEL_RELIABLE = "input-reliable"
    }
}

/** The half of `PeerConnection.Observer` this client cares about. */
private abstract class PeerObserver : PeerConnection.Observer {
    override fun onSignalingChange(state: PeerConnection.SignalingState) = Unit
    override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) = Unit
    override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit
    override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) = Unit
    override fun onIceCandidate(candidate: IceCandidate) = Unit
    override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) = Unit
    override fun onAddStream(stream: MediaStream) = Unit
    override fun onRemoveStream(stream: MediaStream) = Unit
    override fun onDataChannel(channel: DataChannel) = Unit
    override fun onRenegotiationNeeded() = Unit
    override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) = Unit
}

/** Likewise for `SdpObserver`, whose four methods are never all wanted at once. */
private abstract class SdpAdapter : SdpObserver {
    override fun onCreateSuccess(description: SessionDescription) = Unit
    override fun onSetSuccess() = Unit
    override fun onCreateFailure(error: String?) = Unit
    override fun onSetFailure(error: String?) = Unit
}
