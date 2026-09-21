package com.dial.van.events

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
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
     * Merge a page, from whichever carrier brought it, and remember how far it got.
     *
     * The cursor is saved from the merged state rather than from the page, because
     * `applyPage` refuses to rewind: a Gateway answering with a lower cursor than this
     * device holds is not a reason to ask for events it has already shown the owner.
     */
    fun apply(page: EventPage) {
        val next = EventStream.applyPage(_state.value, page)
        _state.value = next
        cursors.save(next.cursor)
    }

    /** A carrier failed. The history is kept; the failure is counted and shown. */
    fun fail(reason: String) {
        _state.value = EventStream.applyFailure(_state.value, reason)
    }

    /** Where the next poll should start. */
    fun cursor(): Long = _state.value.cursor
}
