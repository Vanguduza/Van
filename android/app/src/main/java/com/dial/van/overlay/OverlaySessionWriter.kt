package com.dial.van.overlay

/** Testable latest-value writer; one drain, bounded memory, ordered acknowledged records. */
class OverlaySessionWriter(
    private val execute: (() -> Unit) -> Unit,
    private val persist: (String) -> Boolean,
    private val completed: (Long, Boolean) -> Unit,
) {
    private val lock = Any()
    private var pending: Pair<Long, String>? = null
    private var scheduled = false
    private var closed = false
    private var newest = -1L

    fun offer(revision: Long, encoded: String): Boolean {
        require(revision >= 0 && encoded.length <= OverlayLocalSessionCodec.MAX_RECORD_CHARS)
        val schedule = synchronized(lock) {
            if (closed || revision <= newest) return false
            newest = revision; pending = revision to encoded
            if (scheduled) false else { scheduled = true; true }
        }
        if (schedule) {
            try { execute(::drain) }
            catch (_: Exception) {
                val failed = synchronized(lock) { val p = pending; pending = null; scheduled = false; p }
                failed?.let { notify(it.first, false) }
                return false
            }
        }
        return true
    }

    /** Prevent new offers but let the existing executor drain its last value. */
    fun close() { synchronized(lock) { closed = true } }

    private fun notify(revision: Long, saved: Boolean) {
        // A dead UI observer cannot stall subsequent durable writes.
        try { completed(revision, saved) } catch (_: Exception) { }
    }

    private fun drain() {
        while (true) {
            val next = synchronized(lock) {
                pending?.also { pending = null } ?: run { scheduled = false; return }
            }
            val success = try { persist(next.second) } catch (_: Exception) { false }
            notify(next.first, success)
        }
    }
}
