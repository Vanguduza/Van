package com.dial.van.events

import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Rev 1.5 §§5.6, 20.1 — one event history, for the whole app.
 *
 * The Work screen used to own it: `var stream by remember { … }` inside a composable, fed
 * by an HTTP poll in a `LaunchedEffect`. Two consequences followed, and both are the
 * owner's rather than the architecture's.
 *
 * The stream only existed while that screen was composed, so a mission finishing while
 * the owner was anywhere else produced nothing they could see, and reopening the screen
 * started from the saved cursor as though the intervening time had not happened. And when
 * §20.1's socket began delivering durable pages — it SHALL feed
 * `EventStream.applyPage` — there was nowhere to put them: an application-scoped socket
 * cannot write into a composable's `remember`.
 *
 * So the history is held here and read there. Deliberately not a second reducer:
 * [EventStream] still decides what a page does to the state, and this owns only *which*
 * state, so a page from the socket and a page from the REST floor merge the same way.
 * They do overlap — the socket pushes while the floor polls — and `applyPage` is
 * seq-keyed precisely so the owner does not read the same event twice.
 *
 * Pure. The cursor is an [EventCursorStore], which is an interface, so this is executed
 * in `android/verification` rather than reasoned about.
 */
class VanEventStreamStore(private val cursors: EventCursorStore) {

    private val _state = MutableStateFlow(EventStreamState(cursor = cursors.load()))
    val state: StateFlow<EventStreamState> = _state.asStateFlow()

    /**
     * GAP-F-012 — new records, as they arrive, for producers that react to *this* event
     * rather than to the merged history.
     *
     * [state] is the right read for a screen rendering the timeline; it is the wrong read
     * for something that must fire once per `mission.waiting_owner` or `attention.upserted`
     * record, because two callers diffing consecutive [state] values against each other is
     * exactly the kind of second reducer this store's own class doc warns against. A
     * replay-less [SharedFlow] instead: a subscriber sees only what arrives after it starts
     * collecting, which is correct for an embodiment reaction — replaying a `mission.failed`
     * from an hour ago into a freshly opened screen would put VAN back into ERROR for
     * something already resolved. Buffered rather than suspending on emit, because
     * `apply` runs on whatever thread the socket/poll callback is already on and must not
     * block waiting for a slow collector.
     */
    private val _newRecords = MutableSharedFlow<EventRecord>(
        replay = 0,
        extraBufferCapacity = NEW_RECORD_BUFFER,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val newRecords: SharedFlow<EventRecord> = _newRecords.asSharedFlow()

    /**
     * Merge a page, from whichever carrier brought it, and remember how far it got.
     *
     * The cursor is saved from the merged state rather than from the page, because
     * `applyPage` refuses to rewind: a Gateway answering with a lower cursor than this
     * device holds is not a reason to ask for events it has already shown the owner.
     */
    fun apply(page: EventPage) {
        val before = _state.value
        val next = EventStream.applyPage(before, page)
        _state.value = next
        cursors.save(next.cursor)
        // Genuinely new records only: a page that overlaps what this device already holds
        // (a restored cursor slightly behind, a retried poll) must not re-fire a producer
        // for an event VAN already reacted to.
        if (next.events !== before.events) {
            val seenSeqs = before.events.mapTo(HashSet(before.events.size)) { it.seq }
            for (event in page.events) {
                if (event.seq !in seenSeqs) _newRecords.tryEmit(event)
            }
        }
    }

    /** A carrier failed. The history is kept; the failure is counted and shown. */
    fun fail(reason: String) {
        _state.value = EventStream.applyFailure(_state.value, reason)
    }

    /** Where the next poll should start. */
    fun cursor(): Long = _state.value.cursor

    private companion object {
        /** Generous relative to the gateway's page size; overflow drops the oldest, never blocks. */
        const val NEW_RECORD_BUFFER = 64
    }
}
