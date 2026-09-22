package com.dial.van.design

import org.json.JSONArray
import org.json.JSONException

/**
 * Every destination's screen-state contract (DNA §5): LOADING, CONTENT, EMPTY, ERROR,
 * DEGRADED, OFFLINE, STALE.
 *
 * Pure Kotlin — no `@Composable`, no callbacks — so a screen's reducer can be asserted on the
 * JVM: "given this response and this health payload, which state does the owner see" is a
 * question with one right answer, and answering it by opening the app is how DEGRADED and
 * STALE silently trade places. `com.dial.van.design.components.VanScreen` is the only place
 * that turns a value of this type into pixels.
 */
sealed class ScreenState<out T> {

    /** Skeleton matching the final geometry; never a spinner-only screen. */
    object Loading : ScreenState<Nothing>()

    /** The live thing itself. */
    data class Content<T>(val data: T) : ScreenState<T>()

    /** Nothing to show, with a VAN-voiced sentence and at most one action. */
    data class Empty(val sentence: String, val action: ScreenAction? = null) : ScreenState<Nothing>()

    /** The request failed outright; no partial data to fall back on. */
    data class Error(val message: String, val canRetry: Boolean = true) : ScreenState<Nothing>()

    /**
     * A named subsystem is degraded. `rows` names which one and what it means for the owner;
     * `data` is whatever the screen could still assemble around that gap, or `null` if
     * nothing survived.
     */
    data class Degraded<T>(val rows: List<DegradedRow>, val data: T? = null) : ScreenState<T>()

    /** Connectivity is down; `queuedCount` is the owner's own queued work, still visible. */
    data class Offline(val queuedCount: Int) : ScreenState<Nothing>()

    /** Last-known-good `content`, `ageMs` old. Carries a `LiveBadge` showing that age. */
    data class Stale<T>(val ageMs: Long, val content: T) : ScreenState<T>()
}

/** A single action a [ScreenState.Empty] may offer — one, per DNA §5. */
data class ScreenAction(val label: String)

/** One subsystem read off `/health.degraded[]`, translated into what the owner reads. */
data class DegradedRow(val subsystem: String, val sentence: String)

/**
 * `/health.degraded[]` subsystem keys → the sentence DNA §5 asks for: "which subsystem, what
 * still works." Unknown keys are not dropped — an unnamed degraded subsystem is exactly the
 * case an owner most needs told about — they get a generic sentence built from the key itself
 * rather than being silently absent from the list.
 */
object DegradedCatalog {
    private val SENTENCES: Map<String, String> = mapOf(
        "gateway" to "The gateway connection is degraded — updates may lag.",
        "trading" to "Trading data is degraded — prices and positions may be stale.",
        "google_mesh" to "Google account access is degraded — some context may be missing.",
        "voice" to "Voice is degraded — try typing instead.",
        "browser" to "The remote browser is degraded — automation may fail to start.",
        "memory" to "Memory is degraded — recent facts may not be saved or recalled.",
        "hermes" to "Delegated agents are degraded — running work may stall.",
        "notifications" to "Notifications are degraded — some updates may arrive late.",
    )

    /** A owner-facing sentence for a raw subsystem key, known or not. */
    fun sentenceFor(subsystem: String): String =
        SENTENCES[subsystem] ?: "${subsystem.replace('_', ' ').replaceFirstChar { it.uppercase() }} is degraded."

    fun rowsFor(subsystems: List<String>): List<DegradedRow> =
        subsystems.filter { it.isNotBlank() }.map { DegradedRow(it, sentenceFor(it)) }

    /**
     * Parses the `degraded` array of a `/health` response body — a bare JSON array of
     * subsystem-key strings, e.g. `["trading","voice"]` — into [DegradedRow]s. Malformed
     * input (not an array, not strings) becomes an empty list rather than a thrown
     * exception: a screen that cannot parse its own health payload should read as CONTENT
     * with no degraded rows, not crash.
     */
    fun rowsFromHealthJson(degradedJson: String): List<DegradedRow> {
        val array = try {
            JSONArray(degradedJson)
        } catch (_: JSONException) {
            return emptyList()
        }
        val keys = buildList {
            for (index in 0 until array.length()) {
                val value = array.opt(index)
                if (value is String && value.isNotBlank()) add(value)
            }
        }
        return rowsFor(keys)
    }
}

/**
 * How a screen's raw signals (a fetched value, a loading flag, an error, queued offline work,
 * degraded subsystems, and the age of what is on screen) collapse into one [ScreenState].
 *
 * Precedence, most to least urgent-to-truth:
 * 1. **Stale overrides content and degraded** (DNA §5's `Stale` carries a `LiveBadge` age —
 *    once data is old enough to need that badge, that is the fact the owner most needs, even
 *    over "this is also degraded"; the degraded rows are not lost, [ScreenState.Stale] keeps
 *    whatever content survived and the caller may still render a `DEGRADED` sub-badge from
 *    the same [degradedSubsystems] it passed in).
 * 2. Degraded, when there is content to show around the gap.
 * 3. Plain content.
 * 4. Loading / error / offline / empty, only when there is no content to fall back on — a
 *    request that failed but still has yesterday's data is DEGRADED or STALE, not ERROR.
 */
object ScreenStateMerge {
    /** DNA §2 uses `LiveBadge`'s "STALE hh:mm" reading; one minute is the merge's own floor. */
    const val DEFAULT_STALE_THRESHOLD_MS = 60_000L

    fun <T> merge(
        content: T?,
        loading: Boolean = false,
        errorMessage: String? = null,
        offlineQueuedCount: Int? = null,
        degradedSubsystems: List<String> = emptyList(),
        ageMs: Long? = null,
        staleThresholdMs: Long = DEFAULT_STALE_THRESHOLD_MS,
        emptySentence: String = "Nothing here yet.",
        emptyAction: ScreenAction? = null,
    ): ScreenState<T> {
        if (content == null) {
            return when {
                offlineQueuedCount != null && offlineQueuedCount > 0 -> ScreenState.Offline(offlineQueuedCount)
                loading -> ScreenState.Loading
                errorMessage != null -> ScreenState.Error(errorMessage)
                else -> ScreenState.Empty(emptySentence, emptyAction)
            }
        }
        val stale = ageMs != null && ageMs >= staleThresholdMs
        val degraded = degradedSubsystems.isNotEmpty()
        return when {
            stale -> ScreenState.Stale(ageMs!!, content)
            degraded -> ScreenState.Degraded(DegradedCatalog.rowsFor(degradedSubsystems), content)
            else -> ScreenState.Content(content)
        }
    }
}
