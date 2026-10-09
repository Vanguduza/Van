package com.dial.van.browser

import org.json.JSONArray

/** The gateway's digest-only inventory is a read model, not a tab actuation protocol. */
object BrowserSessionRecords {
    data class Tab(val id: String, val title: String, val urlDigest: String?, val active: Boolean)
    data class Event(val id: String, val summary: String, val severity: String,
        val occurredAtMs: Long, val evidenceRef: String?)

    fun tabs(rows: JSONArray): List<Tab> = (0 until rows.length()).map { index ->
        val row = rows.getJSONObject(index)
        val id = row.getString("target_id").also { require(it.isNotBlank()) }
        Tab(id, row.optString("title").ifBlank { "Untitled tab" },
            if (row.isNull("url_digest")) null else row.optString("url_digest").ifBlank { null },
            row.getBoolean("is_active"))
    }.also { tabs -> require(tabs.map { it.id }.distinct().size == tabs.size) }

    fun events(rows: JSONArray): List<Event> = (0 until rows.length()).map { index ->
        val row = rows.getJSONObject(index)
        val id = row.getString("event_id").also { require(it.isNotBlank()) }
        Event(id, row.getString("summary"), row.getString("severity"), row.getLong("occurred_at_ms"),
            if (row.isNull("evidence_ref")) null else row.optString("evidence_ref").ifBlank { null })
    }.also { events -> require(events.map { it.id }.distinct().size == events.size) }
}
