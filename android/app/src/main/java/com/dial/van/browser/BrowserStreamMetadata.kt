package com.dial.van.browser

import org.json.JSONObject

/** A media peer is bound to one authoritative viewport. PTS is informational, not a clock proof. */
object BrowserStreamMetadata {
    const val CHANNEL = "browser-state"
    const val MAX_BYTES = 65_536
    data class Binding(val sessionId: String, val controlGeneration: Int, val viewportRevision: Int,
        val width: Int, val height: Int, val mediaEpoch: String)
    data class Answer(val binding: Binding, val sdp: String)
    sealed interface Event {
        val binding: Binding
        val sequence: Long
        data class Frame(override val binding: Binding, override val sequence: Long, val frameSequence: Long) : Event
        data class Tabs(override val binding: Binding, override val sequence: Long, val tabs: List<BrowserTab>,
            val activeTargetId: String?) : Event
        data class Session(override val binding: Binding, override val sequence: Long, val state: BrowserSessionState) : Event
        data class Chooser(override val binding: Binding, override val sequence: Long, val chooserId: String,
            val targetId: String, val acceptTypes: List<String>, val expiresInMs: Long) : Event
        data class Download(override val binding: Binding, override val sequence: Long, val downloadId: String, val state: String) : Event
        data class Refused(override val binding: Binding, override val sequence: Long, val input: Boolean, val reason: String) : Event
    }
    data class RenderedFrame(val binding: Binding, val frameSequence: Long)

    private fun number(row: JSONObject, key: String, max: Long = Long.MAX_VALUE): Long {
        val value = row.opt(key)
        require(value is Number && value.toDouble().isFinite() && value.toDouble() == value.toLong().toDouble()) { "browser_metadata_invalid_$key" }
        return value.toLong().also { require(it in 1..max) { "browser_metadata_invalid_$key" } }
    }
    private fun text(row: JSONObject, key: String, limit: Int): String = row.getString(key).also {
        require(it.isNotBlank() && it.length <= limit && '\u0000' !in it) { "browser_metadata_invalid_$key" }
    }
    private fun binding(row: JSONObject): Binding {
        require(row.opt("protocol") == 1) { "browser_metadata_protocol_mismatch" }
        return Binding(text(row, "session_id", 256), number(row, "control_generation", Int.MAX_VALUE.toLong()).toInt(),
            number(row, "viewport_revision", Int.MAX_VALUE.toLong()).toInt(), number(row, "width", 7680).toInt(),
            number(row, "height", 7680).toInt(), text(row, "media_epoch", 256))
    }
    fun answer(row: JSONObject, expected: BrowserSessionSnapshot): Answer {
        require(row.optString("type") == "answer") { "browser_signal_answer_required" }
        val binding = binding(row)
        require(binding.sessionId == expected.sessionId && binding.controlGeneration == expected.controlGeneration &&
            binding.viewportRevision == expected.viewport.revision && binding.width == expected.viewport.width &&
            binding.height == expected.viewport.height) { "browser_signal_binding_mismatch" }
        return Answer(binding, text(row, "sdp", 1_048_576))
    }
    fun event(row: JSONObject): Event {
        val binding = binding(row)
        val sequence = number(row, "event_seq")
        return when (row.optString("event_type")) {
            "viewport.frame" -> Event.Frame(binding, sequence, number(row, "frame_sequence"))
            "tab.snapshot" -> {
                val rows = row.getJSONArray("tabs")
                require(rows.length() <= 64) { "browser_metadata_tab_limit" }
                val tabs = (0 until rows.length()).map { index ->
                    val tab = rows.getJSONObject(index)
                    fun optional(key: String, limit: Int): String = if (tab.isNull(key)) "" else tab.getString(key).also { require(it.length <= limit) }
                    fun flag(key: String): Boolean = if (!tab.has(key)) false else (tab.opt(key) as? Boolean ?: error("browser_metadata_invalid_$key"))
                    BrowserTab(targetId = text(tab, "target_id", 256), title = optional("title", 512),
                        url = optional("url", 4096), urlDigest = optional("url_digest", 256), loading = flag("loading"),
                        canGoBack = flag("can_go_back"), canGoForward = flag("can_go_forward"),
                        securityState = when (tab.optString("security_state").uppercase()) {
                            "SECURE" -> SecurityState.SECURE
                            "INSECURE" -> SecurityState.INSECURE
                            "BROKEN", "INSECURE-BROKEN" -> SecurityState.BROKEN
                            else -> SecurityState.UNKNOWN
                        })
                }
                require(tabs.map { it.targetId }.distinct().size == tabs.size) { "browser_metadata_duplicate_target" }
                val active = if (row.isNull("active_target_id")) null else row.getString("active_target_id")
                require(active == null || tabs.any { it.targetId == active }) { "browser_metadata_active_target_unknown" }
                Event.Tabs(binding, sequence, tabs, active)
            }
            "session.state" -> Event.Session(binding, sequence, BrowserSessionState.from(row.getString("state"))).also {
                require(it.state != BrowserSessionState.UNKNOWN) { "browser_metadata_state_unknown" }
            }
            "file.chooser" -> {
                val types = row.getJSONArray("accept_types")
                require(types.length() <= 16 && row.opt("multiple") == false) { "browser_metadata_chooser_invalid" }
                Event.Chooser(binding, sequence, text(row, "chooser_id", 256), text(row, "target_id", 256),
                    (0 until types.length()).map { index -> types.getString(index).also { require(it.length <= 128) } },
                    number(row, "expires_in_ms", BrowserUploadPolicy.DEFAULT_TTL_MS))
            }
            "download.available" -> Event.Download(binding, sequence, text(row, "download_id", 256), text(row, "state", 32)).also {
                require(it.state in setOf("IN_PROGRESS", "COMPLETED", "QUARANTINED", "FAILED")) { "browser_metadata_download_state_unknown" }
            }
            "input.refused", "file.refused" -> Event.Refused(binding, sequence, row.getString("event_type") == "input.refused", text(row, "reason", 128))
            else -> error("browser_metadata_event_unknown")
        }
    }

    /** Old peers, duplicated metadata and mismatched geometry can never confirm a new viewport. */
    class Gate(private val expected: Binding) {
        private var sequence = 0L
        private var frameSequence = 0L
        private var marker: Event.Frame? = null
        private var confirmed = false
        @Synchronized fun accept(event: Event): Boolean {
            if (event.binding != expected || event.sequence <= sequence) return false
            if (event is Event.Frame && event.frameSequence <= frameSequence) return false
            sequence = event.sequence
            if (event is Event.Frame) { frameSequence = event.frameSequence; marker = event }
            return true
        }
        @Synchronized fun decoded(width: Int, height: Int): RenderedFrame? {
            val marker = marker ?: return null
            if (confirmed || width != expected.width || height != expected.height) return null
            confirmed = true
            return RenderedFrame(expected, marker.frameSequence)
        }
    }
}
