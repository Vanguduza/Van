package com.dial.van.overlay

import java.util.concurrent.atomic.AtomicLong

/**
 * A replacement service supersedes an old writer without waiting on disk on the
 * UI thread. Its background read waits for any already-running commit, then sees
 * that commit in full. Older queued writers cannot overwrite the new session.
 */
class OverlaySnapshotOwnership {
    private val newest = AtomicLong()
    private val disk = Any()
    fun acquire(): Long = newest.incrementAndGet()
    fun current(lease: Long): Boolean = lease > 0 && newest.get() == lease
    fun read(lease: Long, load: () -> String?): String? = synchronized(disk) {
        if (current(lease)) load() else null
    }
    fun write(lease: Long, save: () -> Boolean): Boolean = synchronized(disk) {
        if (current(lease)) save() else false
    }
}
