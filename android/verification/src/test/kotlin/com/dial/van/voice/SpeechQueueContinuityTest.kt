package com.dial.van.voice

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class SpeechQueueContinuityTest {
    private fun segment(index: Int, final: Boolean = false) = SpeechSegment(
        responseId = "response", speechStreamId = "stream", segmentId = "segment-$index",
        segmentIndex = index, text = "Sentence $index", final = final,
    )

    @Test
    fun `nothing heard resumes with segment zero`() {
        val queue = SpeechQueue()
        assertEquals(-1, queue.cursors().lastSpokenSegment)
        assertEquals(0, queue.cursors().resumeFromSegment)
        queue.offer(segment(0))
        assertEquals(0, queue.cursors().resumeFromSegment)
    }

    @Test
    fun `ready later audio cannot skip an earlier unfinished sentence`() {
        val queue = SpeechQueue()
        queue.offer(segment(0))
        queue.offer(segment(1))
        queue.mark("segment-1", SpeechSegmentState.READY)
        assertNull(queue.nextToSpeak())
        queue.mark("segment-0", SpeechSegmentState.READY)
        assertEquals(0, queue.nextToSpeak()?.segmentIndex)
    }

    @Test
    fun `a late completion cannot acknowledge a sentence interrupted by the owner`() {
        val queue = SpeechQueue()
        queue.offer(segment(0, final = true))
        queue.mark("segment-0", SpeechSegmentState.SPEAKING)
        queue.bargeIn()
        queue.mark("segment-0", SpeechSegmentState.SPOKEN)
        assertEquals(SpeechSegmentState.INTERRUPTED, queue.snapshot().single().state)
        assertEquals(-1, queue.cursors().lastSpokenSegment)
        assertFalse(queue.completed())
    }

    @Test
    fun `completion advances only the contiguous heard prefix`() {
        val queue = SpeechQueue()
        queue.offer(segment(0))
        queue.offer(segment(1, final = true))
        queue.mark("segment-1", SpeechSegmentState.SPOKEN)
        assertEquals(-1, queue.cursors().lastSpokenSegment)
        assertFalse(queue.completed())
        queue.mark("segment-0", SpeechSegmentState.SPOKEN)
        assertEquals(1, queue.cursors().lastSpokenSegment)
        assertTrue(queue.completed())
    }

    @Test
    fun `a different id at an existing index is not a second sentence`() {
        val queue = SpeechQueue()
        assertTrue(queue.offer(segment(0)))
        assertFalse(queue.offer(segment(0).copy(segmentId = "other-id", text = "Replacement content")))
        assertEquals(1, queue.snapshot().size)
    }

    @Test
    fun `a shared stream id cannot merge different responses`() {
        val queue = SpeechQueue()
        queue.offer(segment(0))
        assertFalse(queue.offer(segment(1).copy(responseId = "another-response")))
    }

    @Test
    fun `reusing a segment id at a different index is also refused`() {
        val queue = SpeechQueue()
        queue.offer(segment(0))
        assertFalse(queue.offer(segment(1).copy(segmentId = "segment-0")))
    }

    @Test
    fun `new unheard speech cannot inherit an earlier completed final marker`() {
        val queue = SpeechQueue()
        queue.offer(segment(0, final = true))
        queue.mark("segment-0", SpeechSegmentState.SPOKEN)
        assertTrue(queue.completed())
        queue.offer(segment(1, final = true))
        assertFalse(queue.completed())
        queue.mark("segment-1", SpeechSegmentState.SPOKEN)
        assertTrue(queue.completed())
    }
}
