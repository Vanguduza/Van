package com.dial.van.muse

/** Bounded SSE parser. A broken stream never advances its durable cursor. */
class MuseEventParser {
    data class Event(val cursor: Long, val data: String)
    private var id: Long? = null
    private val data = StringBuilder()
    fun feed(line: String): Event? {
        require(line.length <= 262144) { "Muse event line too large" }
        if (line.isEmpty()) {
            val event = id?.takeIf { data.isNotEmpty() }?.let { Event(it, data.toString().trimEnd('\n')) }
            id = null; data.clear(); return event
        }
        when {
            line.startsWith("id:") -> id = line.removePrefix("id:").trim().toLongOrNull()?.takeIf { it >= 0 }
            line.startsWith("data:") -> {
                require(data.length + line.length <= 262144) { "Muse event too large" }
                data.append(line.removePrefix("data:").trimStart()).append('\n')
            }
        }
        return null
    }
}
