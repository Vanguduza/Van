package com.dial.van.browser

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets

/**
 * Rev 1.5 §8 — the owner-input wire format, the phone's half.
 *
 * This mirrors `backend/van_gateway/browser/input_protocol.py` byte for byte. The two are
 * separate implementations of one format, which is a real risk: a format with two
 * implementations and no shared definition drifts silently, and the symptom is taps landing
 * in the wrong place rather than anything that looks like a bug.
 *
 * Three things reduce that risk and none of them is "be careful":
 *
 *  - the layout is a single fixed-width header, written here in the same field order as the
 *    Python `struct` format, with the version in the first byte;
 *  - `tests/contracts/test_browser_input_protocol_matches.py` reads both files and fails if
 *    the constants or the field order diverge;
 *  - a packet whose version byte is not [PROTOCOL_VERSION] is refused by the server rather
 *    than parsed as this version's fields.
 *
 * §8.7 is about what happens *before* this: Android may deliver historical touch samples
 * faster than the display refreshes, and those are kept for velocity. What this encoder
 * sends is coalesced to one MOVE per frame, with the final velocity preserved.
 */
object BrowserInputProtocol {

    /** Bumped when the layout changes. The server refuses anything else. */
    const val PROTOCOL_VERSION: Int = 1

    /** §8.6 — coordinates are normalized, so a packet means the same at any viewport. */
    const val COORDINATE_MAX: Int = 65535

    /** Byte length of the fixed header. The Python side asserts the same number. */
    const val HEADER_BYTES: Int = 57

    enum class Kind(val wire: Int) {
        POINTER_DOWN(1),
        POINTER_MOVE(2),
        POINTER_UP(3),
        POINTER_CANCEL(4),
        SCROLL(5),
        KEY_DOWN(6),
        KEY_UP(7),
        TEXT_COMMIT(8),
        IME_COMPOSITION(9),

        // Rev 1.5 §17.2 — "send a navigation command through RELIABLE_INPUT". Navigation
        // is an actuation, so it travels the same fenced path as a tap rather than
        // through a REST route: an address bar that could navigate by calling the Gateway
        // would be a way round the control lease.
        //
        // NAVIGATE and SEARCH carry their subject in `text`; the rest carry nothing.
        NAVIGATE(10),
        SEARCH(11),
        HISTORY_BACK(12),
        HISTORY_FORWARD(13),
        RELOAD(14),
        STOP_LOADING(15);

        /** §8.3 — edges go on both channels, so the server can de-duplicate them. */
        val isEdge: Boolean
            get() = this == POINTER_DOWN || this == POINTER_UP || this == POINTER_CANCEL

        /** Whether this moves the page rather than touching it. */
        val isNavigation: Boolean
            get() = this == NAVIGATE || this == SEARCH || this == HISTORY_BACK ||
                this == HISTORY_FORWARD || this == RELOAD || this == STOP_LOADING

        /**
         * Navigation kinds whose subject is the action itself.
         *
         * Text in one of these is a caller using a field the protocol does not define for
         * it, which is how a wire format drifts between two implementations.
         */
        val carriesNoText: Boolean
            get() = this == HISTORY_BACK || this == HISTORY_FORWARD ||
                this == RELOAD || this == STOP_LOADING
    }

    enum class Channel(val wire: Int) {
        /** Unordered, unreliable: motion and a fast copy of each edge. */
        FAST(1),

        /** Ordered, reliable: the canonical copy of everything that must not be lost. */
        RELIABLE(2),
    }

    /** §8.1 — what every actuation packet carries before it carries anything else. */
    data class Authority(
        val sessionId: String,
        val controlLeaseId: String,
        val controlGeneration: Int,
        val viewportRevision: Int,
    )

    data class Packet(
        val authority: Authority,
        val kind: Kind,
        val channel: Channel,
        val gestureId: Int = 0,
        val pointerId: Int = 0,
        val gestureEpoch: Int = 0,
        val edgeId: Int = 0,
        val fastSeq: Int = 0,
        val reliableSeq: Int = 0,
        val motionSeq: Int = 0,
        val x: Int = 0,
        val y: Int = 0,
        val valueA: Int = 0,
        val valueB: Int = 0,
        val text: String = "",
        val sentAtMs: Long = 0,
    )

    /**
     * Normalize a touch position against the viewport the device is currently showing.
     *
     * The revision is carried separately and checked by the server; this function cannot
     * check it, deliberately. §8.1 refuses a stale revision rather than transforming it, and
     * a helper that quietly rescaled would be the place that rule came undone.
     */
    fun normalize(value: Float, extent: Int): Int {
        if (extent <= 1) return 0
        val scaled = (value / (extent - 1).toFloat()) * COORDINATE_MAX
        return scaled.toInt().coerceIn(0, COORDINATE_MAX)
    }

    fun encode(packet: Packet): ByteArray {
        require(packet.x in 0..COORDINATE_MAX && packet.y in 0..COORDINATE_MAX) {
            "coordinates must be normalized before encoding"
        }
        if (packet.kind.isNavigation) {
            // §17.2 — the reliable channel and nothing else. A navigate that can be
            // dropped or reordered against the tap after it leaves the owner interacting
            // with a page they had already left.
            require(packet.channel == Channel.RELIABLE) {
                "navigation travels on the reliable channel"
            }
            require(!packet.kind.carriesNoText || packet.text.isEmpty()) {
                "this kind carries no text"
            }
            if (packet.kind == Kind.NAVIGATE) {
                val lowered = packet.text.trim().lowercase()
                require(lowered.startsWith("http://") || lowered.startsWith("https://")) {
                    "navigation scheme refused"
                }
            }
        }
        val session = packet.authority.sessionId.toByteArray(StandardCharsets.UTF_8)
        val lease = packet.authority.controlLeaseId.toByteArray(StandardCharsets.UTF_8)
        val text = packet.text.toByteArray(StandardCharsets.UTF_8)

        val buffer = ByteBuffer
            .allocate(HEADER_BYTES + 6 + session.size + lease.size + text.size)
            .order(ByteOrder.LITTLE_ENDIAN)

        buffer.put(PROTOCOL_VERSION.toByte())
        buffer.put(packet.kind.wire.toByte())
        buffer.put(packet.channel.wire.toByte())
        buffer.putShort(packet.motionSeq.toShort())
        buffer.putInt(packet.authority.controlGeneration)
        buffer.putInt(packet.authority.viewportRevision)
        buffer.putInt(packet.gestureId)
        buffer.putInt(packet.pointerId)
        buffer.putInt(packet.gestureEpoch)
        buffer.putInt(packet.edgeId)
        buffer.putInt(packet.fastSeq)
        buffer.putInt(packet.reliableSeq)
        buffer.putShort(packet.x.toShort())
        buffer.putShort(packet.y.toShort())
        buffer.putInt(packet.valueA)
        buffer.putInt(packet.valueB)
        buffer.putLong(packet.sentAtMs)

        for (field in listOf(session, lease, text)) {
            require(field.size <= 0xFFFF) { "field too long for the wire format" }
            buffer.putShort(field.size.toShort())
            buffer.put(field)
        }
        return buffer.array()
    }
}

/**
 * §§8.2, 8.5 — gesture identity and the three sequence spaces, on the sending side.
 *
 * One sequence number across both channels would make a legitimately dropped FAST packet
 * look like a protocol gap, so there are three: `fastSeq` for stale-discard, `reliableSeq`
 * for real gap detection, and `motionSeq` per gesture so the server can drop a reordered
 * MOVE without treating it as loss.
 *
 * The epoch is per pointer and only ever increases. That is what lets the server cancel a
 * gesture that has been superseded rather than interleaving two.
 */
class BrowserGestureSequencer {

    private var fastSeq = 0
    private var reliableSeq = 0
    private var gestureId = 0
    private var edgeId = 0
    private val epochs = mutableMapOf<Int, Int>()
    private val motionSeqs = mutableMapOf<Int, Int>()
    private val gestures = mutableMapOf<Int, Int>()

    fun nextFast(): Int = ++fastSeq

    fun nextReliable(): Int = ++reliableSeq

    fun nextEdge(): Int = ++edgeId

    /** Opens a gesture on this pointer and returns `(gestureId, epoch)`. */
    fun beginGesture(pointerId: Int): Pair<Int, Int> {
        val epoch = (epochs[pointerId] ?: 0) + 1
        epochs[pointerId] = epoch
        motionSeqs[pointerId] = 0
        gestureId += 1
        gestures[pointerId] = gestureId
        return gestureId to epoch
    }

    fun epochFor(pointerId: Int): Int = epochs[pointerId] ?: 0

    /**
     * The gesture currently open on this pointer.
     *
     * A MOVE or an UP has to carry the id the DOWN opened, not a fresh one: the server
     * groups a gesture by that id, and an UP under a different id is a finger that went
     * down and never came up.
     */
    fun gestureFor(pointerId: Int): Int = gestures[pointerId] ?: 0

    /**
     * Forget every open gesture, for a control generation change (ADR-RB-007).
     *
     * Two things are deliberately *not* cleared, and both were cleared in the first version
     * of this method:
     *
     *  * **the sequence spaces.** They are per connection. Restarting them makes the server
     *    see a replay of numbers it has already processed.
     *  * **the epochs.** This is the one that actually breaks. The epoch's whole job is to
     *    increase, so the server can tell a superseded gesture from a current one; its
     *    `PointerStateMachine` drops a DOWN whose epoch is at or below the open gesture's,
     *    and raises `REJECT_STALE_EPOCH` for a MOVE below it. Restarting at 1 while a
     *    pointer is still open on the server — an app backgrounded mid-drag is enough —
     *    means the owner's first tap after taking control is dropped, silently, and the
     *    second one works. That is the exact shape of a bug nobody reproduces.
     *
     * What is dropped is the gesture *identity*, because a gesture begun while an agent
     * held the lease must not continue into the owner's. A pointer the server still has
     * open is closed by its own five-second gesture timeout, which is where that belongs:
     * the device cannot send an UP under a lease it no longer holds.
     */
    fun reset() {
        gestures.clear()
        motionSeqs.clear()
    }

    fun nextMotion(pointerId: Int): Int {
        val next = (motionSeqs[pointerId] ?: 0) + 1
        motionSeqs[pointerId] = next
        return next
    }

    /**
     * §8.3 — one edge, two copies, one identity.
     *
     * Both copies must carry the same edge id or the server's de-duplication cannot see
     * that they are the same event, and the owner gets two taps for one finger.
     */
    fun duplicateEdge(packet: BrowserInputProtocol.Packet): List<BrowserInputProtocol.Packet> {
        require(packet.kind.isEdge) { "only DOWN, UP and CANCEL are duplicated" }
        return listOf(
            packet.copy(
                channel = BrowserInputProtocol.Channel.FAST,
                fastSeq = nextFast(),
            ),
            packet.copy(
                channel = BrowserInputProtocol.Channel.RELIABLE,
                reliableSeq = nextReliable(),
            ),
        )
    }
}
