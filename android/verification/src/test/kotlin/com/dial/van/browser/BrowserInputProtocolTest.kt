package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * Rev 1.5 §8 — the phone's half of the input format.
 *
 * The format has two implementations and no shared definition, which is a real risk: they
 * drift, and the symptom is a tap landing somewhere the owner did not touch. These tests
 * pin the byte layout from this side; `tests/contracts/test_browser_input_protocol_matches.py`
 * compares the two files directly.
 */
class BrowserInputProtocolTest {

    private val authority = BrowserInputProtocol.Authority(
        sessionId = "ibs_1",
        controlLeaseId = "bctl_1",
        controlGeneration = 3,
        viewportRevision = 2,
    )

    private fun packet(
        kind: BrowserInputProtocol.Kind = BrowserInputProtocol.Kind.POINTER_DOWN,
        x: Int = 100,
        y: Int = 200,
        text: String = "",
    ) = BrowserInputProtocol.Packet(
        authority = authority,
        kind = kind,
        channel = BrowserInputProtocol.Channel.RELIABLE,
        gestureId = 7,
        pointerId = 1,
        gestureEpoch = 4,
        edgeId = 11,
        x = x,
        y = y,
        text = text,
        sentAtMs = 1234L,
    )

    @Test
    fun `the header is the length both implementations agree on`() {
        val encoded = BrowserInputProtocol.encode(packet())
        val strings = "ibs_1".length + "bctl_1".length
        assertEquals(BrowserInputProtocol.HEADER_BYTES + 6 + strings, encoded.size)
    }

    @Test
    fun `the version is the first byte so a mismatch is a refusal rather than a misparse`() {
        val encoded = BrowserInputProtocol.encode(packet())
        assertEquals(BrowserInputProtocol.PROTOCOL_VERSION.toByte(), encoded[0])
        assertEquals(BrowserInputProtocol.Kind.POINTER_DOWN.wire.toByte(), encoded[1])
        assertEquals(BrowserInputProtocol.Channel.RELIABLE.wire.toByte(), encoded[2])
    }

    @Test
    fun `coordinates outside the normalized range cannot be encoded`() {
        assertFailsWith<IllegalArgumentException> {
            BrowserInputProtocol.encode(packet(x = BrowserInputProtocol.COORDINATE_MAX + 1))
        }
    }

    @Test
    fun `normalization spans the full range at both ends`() {
        assertEquals(0, BrowserInputProtocol.normalize(0f, 1080))
        assertEquals(
            BrowserInputProtocol.COORDINATE_MAX,
            BrowserInputProtocol.normalize(1079f, 1080),
        )
    }

    @Test
    fun `a single pixel viewport normalizes to zero rather than dividing by zero`() {
        assertEquals(0, BrowserInputProtocol.normalize(0f, 1))
    }

    @Test
    fun `text beyond ascii survives the encoding`() {
        val encoded = BrowserInputProtocol.encode(
            packet(kind = BrowserInputProtocol.Kind.TEXT_COMMIT, text = "naïve — 東京"),
        )
        val utf8 = "naïve — 東京".toByteArray(Charsets.UTF_8)
        assertTrue(encoded.toList().windowed(utf8.size).any { it.toByteArray().contentEquals(utf8) })
    }
}

class BrowserGestureSequencerTest {

    private val authority = BrowserInputProtocol.Authority("ibs_1", "bctl_1", 1, 1)

    @Test
    fun `an edge is duplicated onto both channels with one identity`() {
        val sequencer = BrowserGestureSequencer()
        val (gestureId, epoch) = sequencer.beginGesture(pointerId = 1)
        val down = BrowserInputProtocol.Packet(
            authority = authority,
            kind = BrowserInputProtocol.Kind.POINTER_DOWN,
            channel = BrowserInputProtocol.Channel.RELIABLE,
            gestureId = gestureId,
            pointerId = 1,
            gestureEpoch = epoch,
            edgeId = sequencer.nextEdge(),
        )
        val copies = sequencer.duplicateEdge(down)

        assertEquals(2, copies.size)
        assertEquals(
            setOf(BrowserInputProtocol.Channel.FAST, BrowserInputProtocol.Channel.RELIABLE),
            copies.map { it.channel }.toSet(),
        )
        // The server de-duplicates on (gesture_id, edge_id). Two edge ids here would be two
        // taps for one finger.
        assertEquals(1, copies.map { it.edgeId }.toSet().size)
        assertEquals(1, copies.map { it.gestureId }.toSet().size)
    }

    @Test
    fun `only edges are duplicated`() {
        val sequencer = BrowserGestureSequencer()
        val move = BrowserInputProtocol.Packet(
            authority = authority,
            kind = BrowserInputProtocol.Kind.POINTER_MOVE,
            channel = BrowserInputProtocol.Channel.FAST,
        )
        assertFailsWith<IllegalArgumentException> { sequencer.duplicateEdge(move) }
    }

    @Test
    fun `each gesture on a pointer gets a higher epoch`() {
        val sequencer = BrowserGestureSequencer()
        val first = sequencer.beginGesture(pointerId = 1)
        val second = sequencer.beginGesture(pointerId = 1)
        assertTrue(second.second > first.second, "the epoch must increase or the server cannot fence")
        assertTrue(second.first > first.first)
    }

    @Test
    fun `motion sequence restarts per gesture and increases within one`() {
        val sequencer = BrowserGestureSequencer()
        sequencer.beginGesture(pointerId = 1)
        assertEquals(1, sequencer.nextMotion(1))
        assertEquals(2, sequencer.nextMotion(1))
        sequencer.beginGesture(pointerId = 1)
        assertEquals(1, sequencer.nextMotion(1), "a new gesture starts its own motion space")
    }

    @Test
    fun `the three sequence spaces are independent`() {
        val sequencer = BrowserGestureSequencer()
        sequencer.beginGesture(pointerId = 1)
        sequencer.nextFast()
        sequencer.nextFast()
        assertEquals(
            1,
            sequencer.nextReliable(),
            "a dropped fast packet must not look like a gap in the reliable stream",
        )
        assertEquals(1, sequencer.nextMotion(1))
    }

    @Test
    fun `a move and an up carry the gesture the down opened`() {
        // The server groups a gesture by its id. An UP under a fresh id is a finger that
        // went down and never came up, and the page is left holding a drag.
        val sequencer = BrowserGestureSequencer()
        val (gestureId, _) = sequencer.beginGesture(pointerId = 3)
        assertEquals(gestureId, sequencer.gestureFor(3))
        sequencer.beginGesture(pointerId = 9)
        assertEquals(gestureId, sequencer.gestureFor(3), "another pointer must not renumber this one")
    }

    @Test
    fun `an unopened pointer has no gesture rather than gesture zero by accident`() {
        assertEquals(0, BrowserGestureSequencer().gestureFor(1))
    }

    @Test
    fun `reset drops open gestures and keeps the sequence spaces moving`() {
        // ADR-RB-007 — a control handover must not let a gesture continue across it. But
        // restarting the sequence numbers would make the server see a replay of numbers it
        // has already processed, so only the gesture identity is dropped.
        val sequencer = BrowserGestureSequencer()
        sequencer.beginGesture(pointerId = 1)
        sequencer.nextReliable()
        val beforeFast = sequencer.nextFast()

        sequencer.reset()

        assertEquals(0, sequencer.gestureFor(1))
        assertTrue(
            sequencer.nextFast() > beforeFast,
            "the sequence spaces are per connection; restarting them looks like a replay",
        )
        assertEquals(2, sequencer.nextReliable())
    }

    @Test
    fun `the epoch keeps climbing across a reset`() {
        // The server drops a DOWN whose epoch is at or below the gesture it still has open.
        // Restarting the epoch at 1 means the owner's first tap after taking control is
        // dropped and the second one works — whenever a pointer was left open, which an
        // app backgrounded mid-drag is enough to produce.
        val sequencer = BrowserGestureSequencer()
        sequencer.beginGesture(pointerId = 1)
        sequencer.beginGesture(pointerId = 1)
        assertEquals(2, sequencer.epochFor(1))

        sequencer.reset()

        assertEquals(2, sequencer.epochFor(1), "the epoch is not the gesture identity")
        assertEquals(3, sequencer.beginGesture(pointerId = 1).second)
    }

    @Test
    fun `two pointers keep separate epochs`() {
        val sequencer = BrowserGestureSequencer()
        sequencer.beginGesture(pointerId = 1)
        sequencer.beginGesture(pointerId = 1)
        val other = sequencer.beginGesture(pointerId = 2)
        assertEquals(1, other.second)
        assertEquals(2, sequencer.epochFor(1))
    }
}
