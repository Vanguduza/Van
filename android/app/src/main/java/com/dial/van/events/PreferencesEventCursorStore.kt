package com.dial.van.events

import android.content.Context

/**
 * The cursor, on disk (P3-AND-002).
 *
 * Separate from [EventStream] because the arithmetic is worth testing on the JVM and a
 * `SharedPreferences` is not. Its own file rather than the overlay's store: an event cursor
 * is not overlay state, and putting them together would mean clearing one clears the other.
 */
class PreferencesEventCursorStore(context: Context) : EventCursorStore {
    private val prefs = context.applicationContext
        .getSharedPreferences("van_event_stream", Context.MODE_PRIVATE)

    override fun load(): Long = prefs.getLong(KEY_CURSOR, 0L)

    override fun save(cursor: Long) {
        // `commit` rather than `apply`: the process can be killed at any moment, and a
        // cursor lost to an unflushed write replays events the owner has already seen.
        prefs.edit().putLong(KEY_CURSOR, cursor).commit()
    }

    private companion object {
        const val KEY_CURSOR = "after_seq"
    }
}
