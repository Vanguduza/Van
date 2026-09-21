package com.dial.van.voice

/**
 * Rev 1.5 §§21.14–21.17, 21.21, 21.25 — the spoken half of an answer, and what a reconnect
 * must not do to it.
 *
 * The failure this file exists to prevent is specific and it is the one every streaming
 * assistant gets wrong at least once: a transport reconnect makes
 *
 *     "Here is your answer..."
 *
 * start again from the beginning, when the owner has already heard four sentences of it.
 * §21.16 forbids that, and the mechanism is two cursors rather than one. `lastReceived` is
 * what arrived; `lastSpoken` is what the owner actually heard. They are different numbers
 * and a resume that only reports one of them cannot be correct.
 *
 * Everything here is pure, so the cases that matter — a duplicate segment after a failover,
 * a barge-in halfway through, an answer arriving hours later — are executed rather than
 * reasoned about. None of them can be produced on demand on a real phone.
 */

/** §21.15 — what has happened to one segment. */
enum class SpeechSegmentState {
    RECEIVED,
    SYNTHESIZING,
    READY,
    SPEAKING,
    SPOKEN,
    INTERRUPTED,
    FAILED;

    /** Whether the owner heard this one, which is the only thing "delivered" can mean. */
    val heard: Boolean get() = this == SPOKEN
}

data class SpeechSegment(
    val responseId: String,
    val speechStreamId: String,
    val segmentId: String,
    val segmentIndex: Int,
    val text: String,
    val final: Boolean = false,
    val interruptible: Boolean = true,
    val contentDigest: String = "",
    val state: SpeechSegmentState = SpeechSegmentState.RECEIVED,
)

/** §21.16 — the two numbers a resume reports. */
data class SpeechCursors(
    val responseId: String?,
    val speechStreamId: String?,
    val lastReceivedSegment: Int,
    val lastSpokenSegment: Int,
) {
    /**
     * What the Gateway has to resend. Everything past what the owner *heard*, not past what
     * arrived: segments that arrived and were never spoken are lost audio, and treating
     * them as delivered is how an answer develops a hole in the middle.
     */
    val resumeFromSegment: Int get() = lastSpokenSegment + 1
}

class SpeechQueue {

    private val segments = LinkedHashMap<String, SpeechSegment>()
    private var lastSpokenIndex: Int = -1
    private var lastReceivedIndex: Int = -1
    private var responseId: String? = null
    private var speechStreamId: String? = null

    /**
     * Accept a segment, or say why it was not accepted.
     *
     * @return true when it was added. False means a duplicate, which §21.16 requires be
     *   discarded silently — after a failover the Gateway resends from a cursor and some
     *   overlap is expected, not an error.
     */
    fun offer(segment: SpeechSegment): Boolean {
        // A segment from another answer is not late, it is unrelated. Accepting it would
        // interleave two answers in one queue and compare their indexes as if they were
        // the same sequence, which is meaningless.
        val current = speechStreamId
        if (current != null && segment.speechStreamId != current) return false

        if (segments.containsKey(segment.segmentId)) return false

        // A segment the owner has already heard is a replay, and replaying it would repeat
        // a sentence out loud. The cursor is the authority, not arrival order.
        //
        // This is not the same check as the one above, although a mutation of it survived
        // until a test separated them. The id check catches the ordinary resend, where the
        // Gateway serves from a cursor and some overlap is expected. This one catches a
        // *renumbered* stream — a Gateway that re-segmented the same answer and produced a
        // new id for text the owner has already heard. The ids differ, so only the index
        // says anything.
        if (segment.segmentIndex <= lastSpokenIndex) return false
        segments[segment.segmentId] = segment
        responseId = segment.responseId
        speechStreamId = segment.speechStreamId
        if (segment.segmentIndex > lastReceivedIndex) lastReceivedIndex = segment.segmentIndex
        return true
    }

    fun mark(segmentId: String, state: SpeechSegmentState) {
        val segment = segments[segmentId] ?: return
        segments[segmentId] = segment.copy(state = state)
        if (state == SpeechSegmentState.SPOKEN && segment.segmentIndex > lastSpokenIndex) {
            lastSpokenIndex = segment.segmentIndex
        }
    }

    /** The next segment to speak: the lowest-indexed one that is ready and unspoken. */
    fun nextToSpeak(): SpeechSegment? =
        segments.values
            .filter { it.state == SpeechSegmentState.READY }
            .minByOrNull { it.segmentIndex }

    /**
     * §21.17 — how many segments to synthesise ahead.
     *
     * One or two, and not more. A deep queue keeps TTS going across a path switch, which is
     * the point; a deeper one means a barge-in has to discard audio the owner has already
     * been waiting through, and a refocused answer arrives stale.
     */
    fun synthesisTarget(): Int = SYNTHESIS_LOOKAHEAD

    fun readyCount(): Int = segments.values.count { it.state == SpeechSegmentState.READY }

    fun shouldSynthesiseMore(): Boolean = readyCount() < SYNTHESIS_LOOKAHEAD

    fun cursors(): SpeechCursors = SpeechCursors(
        responseId = responseId,
        speechStreamId = speechStreamId,
        lastReceivedSegment = lastReceivedIndex.coerceAtLeast(0),
        lastSpokenSegment = lastSpokenIndex.coerceAtLeast(0),
    )

    /**
     * §21.21 — the owner spoke. Everything unspoken stops being work.
     *
     * Marked INTERRUPTED rather than deleted: the difference between "VAN was cut off" and
     * "VAN never had anything to say" is a real distinction, and the Mission's record of the
     * turn needs it.
     */
    fun bargeIn(): Int {
        var interrupted = 0
        for ((id, segment) in segments) {
            if (segment.state in ACTIVE_STATES) {
                segments[id] = segment.copy(state = SpeechSegmentState.INTERRUPTED)
                interrupted += 1
            }
        }
        return interrupted
    }

    /** Whether the answer finished, which needs a final segment that was actually spoken. */
    fun completed(): Boolean =
        segments.values.any { it.final && it.state == SpeechSegmentState.SPOKEN }

    fun snapshot(): List<SpeechSegment> = segments.values.sortedBy { it.segmentIndex }

    private companion object {
        const val SYNTHESIS_LOOKAHEAD = 2
        val ACTIVE_STATES = setOf(
            SpeechSegmentState.RECEIVED,
            SpeechSegmentState.SYNTHESIZING,
            SpeechSegmentState.READY,
            SpeechSegmentState.SPEAKING,
        )
    }
}

/**
 * §21.25 — an answer that arrives hours after the question.
 *
 * The failure is concrete: the owner asked something while Hermes was unreachable, put the
 * phone down, and at 3am VAN starts talking. Speech resumes only when the owner is still in
 * the same voice context; otherwise the answer becomes something they can come back to.
 */
enum class DelayedAnswerAction {
    /** The owner is still here. Speak normally. */
    SPEAK_NOW,

    /** They are not. Post it and stay quiet. */
    NOTIFY_ONLY,

    /** They are here but not listening to VAN — surface it without taking the audio. */
    SHOW_WITHOUT_SPEAKING,
}

object DelayedAnswerPolicy {

    /**
     * How long an answer may sit before it stops being part of the conversation.
     *
     * Two minutes, because it is the span over which "you asked me that just now" is still
     * true. Beyond it, speaking unprompted is VAN starting a conversation rather than
     * finishing one.
     */
    const val SAME_CONTEXT_WINDOW_MS: Long = 120_000

    fun decide(
        askedAtMs: Long,
        completedAtMs: Long,
        ownerStillInVoiceContext: Boolean,
        screenInteractive: Boolean,
        policyPermitsUnpromptedSpeech: Boolean = false,
    ): DelayedAnswerAction {
        val elapsed = completedAtMs - askedAtMs
        if (ownerStillInVoiceContext && elapsed <= SAME_CONTEXT_WINDOW_MS) {
            return DelayedAnswerAction.SPEAK_NOW
        }
        if (policyPermitsUnpromptedSpeech && screenInteractive) {
            return DelayedAnswerAction.SPEAK_NOW
        }
        // The distinction that keeps VAN from being startling: the owner is holding the
        // phone, so show it; they are not in a voice turn, so do not take the audio.
        if (screenInteractive) return DelayedAnswerAction.SHOW_WITHOUT_SPEAKING
        return DelayedAnswerAction.NOTIFY_ONLY
    }
}
