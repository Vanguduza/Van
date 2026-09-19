package com.dial.van.events

/**
 * The event stream's cursor, paging and backoff, as a pure state machine.
 *
 * P3-AND-002. There was a single `events(0)` call in the activity feed's initial
 * composition. The cursor was the literal `0`, it was never persisted, and nothing polled
 * again — so the event stream the gateway maintains was, from the client's side, one page of
 * history fetched once and never updated. Anything the gateway published after that first
 * composition never reached the owner's screen until they left it and came back.
 *
 * Three decisions here, each because the obvious version is wrong:
 *
 * **The cursor is persisted and restored.** A device that has been offline should resume
 * where it stopped rather than replaying the whole log — which at the gateway's 100-event
 * page size means paging through everything that ever happened, on every app start.
 *
 * **A truncated page polls again immediately.** The gateway reports `truncated` when more
 * events are waiting. Waiting the idle interval before asking for them would make catching
 * up take `pages × interval`, which for a device that has been away is minutes of an
 * out-of-date screen.
 *
 * **Failures back off, and say so.** A gateway that is down should not be polled every
 * second, and a feed that has stopped updating should not look like a feed with nothing in
 * it — the distinction the audit kept finding collapsed. [EventStreamState.error] carries
 * the reason so the screen can show it.
 *
 * No Android imports: the paging and backoff arithmetic is the part that was wrong, and it
 * is executed in the JVM verification harness.
 */
data class EventRecord(
    val seq: Long,
    val type: String,
    val payloadJson: String,
    val createdAtUnix: Long,
)

data class EventPage(
    val events: List<EventRecord>,
    val nextCursor: Long,
    val truncated: Boolean,
)

data class EventStreamState(
    val cursor: Long = 0L,
    val events: List<EventRecord> = emptyList(),
    val error: String? = null,
    val consecutiveFailures: Int = 0,
    /** Pages successfully applied. The screen uses it to tell "empty" from "not loaded". */
    val pagesApplied: Int = 0,
) {
    val loaded: Boolean get() = pagesApplied > 0
}

object EventStream {

    /** Newest-first retention on the client. Older events stay on the gateway. */
    const val MAX_RETAINED = 300

    const val IDLE_POLL_MS = 15_000L
    const val CATCH_UP_POLL_MS = 0L
    const val MIN_BACKOFF_MS = 2_000L
    const val MAX_BACKOFF_MS = 120_000L

    fun applyPage(state: EventStreamState, page: EventPage): EventStreamState {
        // Seq-keyed, so a page that overlaps what is already held — which happens whenever a
        // cursor is restored slightly behind — does not produce duplicate rows.
        val merged = LinkedHashMap<Long, EventRecord>(state.events.size + page.events.size)
        for (event in state.events) merged[event.seq] = event
        for (event in page.events) merged[event.seq] = event
        val ordered = merged.values.sortedByDescending { it.seq }.take(MAX_RETAINED)
        return state.copy(
            // Never rewind: a gateway that answers with a lower cursor than we hold would
            // otherwise make the client replay events it has already shown.
            cursor = maxOf(state.cursor, page.nextCursor),
            events = ordered,
            error = null,
            consecutiveFailures = 0,
            pagesApplied = state.pagesApplied + 1,
        )
    }

    fun applyFailure(state: EventStreamState, reason: String): EventStreamState = state.copy(
        error = reason,
        consecutiveFailures = state.consecutiveFailures + 1,
    )

    /**
     * How long to wait before the next poll.
     *
     * Exponential with a ceiling. No jitter here because there is one client per device; the
     * thundering-herd problem this would solve does not exist, and jitter would make the
     * backoff untestable for no gain.
     */
    fun nextDelayMillis(state: EventStreamState, lastPageTruncated: Boolean): Long = when {
        state.consecutiveFailures > 0 -> {
            val scaled = MIN_BACKOFF_MS shl (state.consecutiveFailures - 1).coerceAtMost(6)
            scaled.coerceAtMost(MAX_BACKOFF_MS)
        }
        lastPageTruncated -> CATCH_UP_POLL_MS
        else -> IDLE_POLL_MS
    }
}

/** Where the cursor survives a restart. Implemented over SharedPreferences on the device. */
interface EventCursorStore {
    fun load(): Long
    fun save(cursor: Long)
}

/** An in-memory store, for tests and for a client that has not been given a real one. */
class InMemoryEventCursorStore(private var cursor: Long = 0L) : EventCursorStore {
    override fun load(): Long = cursor
    override fun save(cursor: Long) {
        this.cursor = cursor
    }
}
