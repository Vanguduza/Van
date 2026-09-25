package com.dial.van.dialdev

import com.dial.van.design.DegradedCatalog
import com.dial.van.design.DegradedRow
import com.dial.van.design.ScreenState
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/**
 * The DIAL Development Projection envelope (`VAN-DEVCC-R1` §3.1), as VAN's gateway relays it
 * on every `GET /v1/dial-dev/…` response:
 *
 * `{projection_revision, observed_at, sources, freshness_ms, degraded[], data}`.
 *
 * Parsed, not trusted: a body without a `projection_revision` is not a projection and is
 * refused ([parse] returns null) rather than rendered — an owner action built on a view with
 * no revision would have nothing to be checked against (§3.3).
 */
data class DialDevEnvelope(
    val projectionRevision: String,
    val observedAt: String?,
    val sources: Map<String, String>,
    val freshnessMs: Long,
    val degraded: List<DialDevDegraded>,
    val data: JSONObject,
) {
    companion object {
        fun parse(body: String): DialDevEnvelope? {
            val json = try {
                JSONObject(body)
            } catch (_: JSONException) {
                return null
            }
            return from(json)
        }

        fun from(json: JSONObject): DialDevEnvelope? {
            val revision = json.optString("projection_revision").trim()
            if (revision.isEmpty()) return null
            val sources = json.optJSONObject("sources")?.let { obj ->
                obj.keys().asSequence().associateWith { key -> obj.opt(key)?.toString().orEmpty() }
            }.orEmpty()
            // `data` is an object on every endpoint the contract names; a bare array (a list
            // endpoint answered without a wrapper) is carried as `{"items": [...]}` so parsers
            // read one shape.
            val data = json.optJSONObject("data")
                ?: json.optJSONArray("data")?.let { JSONObject().put("items", it) }
                ?: JSONObject()
            return DialDevEnvelope(
                projectionRevision = revision,
                observedAt = json.optString("observed_at").takeIf { it.isNotBlank() },
                sources = sources,
                // A missing freshness is not "fresh": it is unknown, and unknown reads as stale.
                freshnessMs = if (json.has("freshness_ms")) json.optLong("freshness_ms", Long.MAX_VALUE) else Long.MAX_VALUE,
                degraded = DialDevDegraded.parseAll(json.optJSONArray("degraded")),
                data = data,
            )
        }
    }
}

/** One `degraded[]` entry: which DIAL subsystem, what it costs, and what still works. */
data class DialDevDegraded(
    val subsystem: String,
    val effect: String?,
    val stillWorks: List<String>,
) {
    /** DNA §5's DEGRADED row: "which subsystem, what still works". */
    fun toRow(): DegradedRow {
        val key = subsystem.trim().lowercase()
        val head = effect?.trim()?.takeIf { it.isNotEmpty() }
            ?.let { "${DialDevSubsystems.label(key)}: $it." }
            ?: DegradedCatalog.sentenceFor(key)
        val still = if (stillWorks.isEmpty()) "" else " Still works: ${stillWorks.joinToString(", ")}."
        return DegradedRow(key, head + still)
    }

    companion object {
        fun parseAll(array: JSONArray?): List<DialDevDegraded> {
            if (array == null) return emptyList()
            return buildList {
                for (i in 0 until array.length()) {
                    when (val item = array.opt(i)) {
                        is JSONObject -> {
                            val subsystem = item.optString("subsystem").trim()
                            if (subsystem.isEmpty()) continue
                            add(
                                DialDevDegraded(
                                    subsystem = subsystem,
                                    effect = item.optString("effect").takeIf { it.isNotBlank() },
                                    stillWorks = item.optJSONArray("still_works").strings(),
                                ),
                            )
                        }
                        // A bare subsystem key is still a degraded subsystem; it is not dropped.
                        is String -> if (item.isNotBlank()) add(DialDevDegraded(item.trim(), null, emptyList()))
                        else -> Unit
                    }
                }
            }
        }
    }
}

/** DIAL subsystem keys → the name the owner reads. Keys match `DegradedCatalog`'s additions. */
object DialDevSubsystems {
    fun label(key: String): String = when (key.lowercase()) {
        "dial_dev" -> "DIAL development projection"
        "orca" -> "Orca workspaces"
        "spmrf" -> "Shared project memory (SPMRF)"
        "openviking" -> "OpenViking recall"
        "vekl" -> "Engineering knowledge (VEKL)"
        "artemis" -> "ARTEMIS Android testing"
        "zuul" -> "Zuul CI"
        "hermes_dial" -> "DIAL Hermes"
        else -> key.replace('_', ' ').replaceFirstChar { it.uppercase() }
    }
}

/**
 * The outcome of one read, before it becomes a [ScreenState]. Kept as data so the reducer is a
 * pure function the JVM harness executes against every case §3.4 names.
 */
sealed class DialDevFetch {
    object Loading : DialDevFetch()

    /** A projection arrived. [fetchedAtMs] is the phone's clock when it did. */
    data class Loaded(val envelope: DialDevEnvelope, val fetchedAtMs: Long) : DialDevFetch()

    /** The gateway answered with an error status. */
    data class Failed(val httpStatus: Int?, val body: String, val message: String?) : DialDevFetch()

    /** The phone has no network. Only the read refresh is pending; no owner action is queued. */
    object Offline : DialDevFetch()
}

/** Per-route stale thresholds (§3.1): 30 s by default, 10 s for Orca workspaces. */
object DialDevFreshness {
    const val DEFAULT_STALE_MS = 30_000L
    const val WORKSPACES_STALE_MS = 10_000L
}

/**
 * §3.1 / §3.4 mapping onto DNA §5's seven states.
 *
 * - `degraded[]` non-empty → [ScreenState.Degraded] with the surviving data.
 * - age (`freshness_ms` when served + time since) over the route threshold → [ScreenState.Stale].
 *   Stale outranks Degraded, the same precedence `ScreenStateMerge` uses.
 * - `503 dial_dev_unavailable` (or any retryable failure) → [ScreenState.Error] with retry.
 * - offline → [ScreenState.Offline] with `queuedCount = 0`: owner actions are never queued
 *   offline, so there is no owner work to count; the read refresh re-runs on reconnect.
 * - a failure or an offline phone with a last-known projection keeps it on screen as
 *   [ScreenState.Stale] with its true age — last-known-good is not a guess, and hiding it
 *   behind an error would throw away the one thing VAN can still honestly show.
 */
object DialDevScreenReducer {

    fun <T> reduce(
        fetch: DialDevFetch,
        lastGood: DialDevFetch.Loaded?,
        nowMs: Long,
        staleThresholdMs: Long,
        parse: (DialDevEnvelope) -> T?,
        isEmpty: (T) -> Boolean,
        emptySentence: String,
    ): ScreenState<T> = when (fetch) {
        // A refetch in flight keeps the last projection on screen, judged by its own age.
        DialDevFetch.Loading -> lastGood?.let { loaded(it, nowMs, staleThresholdMs, parse, isEmpty, emptySentence) }
            ?: ScreenState.Loading
        is DialDevFetch.Loaded -> loaded(fetch, nowMs, staleThresholdMs, parse, isEmpty, emptySentence)
        is DialDevFetch.Failed -> lastGood?.let { stale(it, nowMs, parse) } ?: failure(fetch)
        DialDevFetch.Offline -> lastGood?.let { stale(it, nowMs, parse) } ?: ScreenState.Offline(0)
    }

    /**
     * The age a `LiveBadge` shows for a projection whose freshness DIAL did not report: the
     * badge's own ceiling ("STALE 99:59"). Unknown is treated as maximally stale, never as fresh.
     */
    const val UNKNOWN_AGE_MS = (99L * 60L + 59L) * 60_000L

    /** Age of a projection now: DIAL's freshness when served plus time on the phone since. */
    fun ageMs(loaded: DialDevFetch.Loaded, nowMs: Long): Long {
        val served = loaded.envelope.freshnessMs
        if (served == Long.MAX_VALUE) return UNKNOWN_AGE_MS
        return served + (nowMs - loaded.fetchedAtMs).coerceAtLeast(0L)
    }

    private fun <T> loaded(
        fetch: DialDevFetch.Loaded,
        nowMs: Long,
        staleThresholdMs: Long,
        parse: (DialDevEnvelope) -> T?,
        isEmpty: (T) -> Boolean,
        emptySentence: String,
    ): ScreenState<T> {
        val rows = fetch.envelope.degraded.map { it.toRow() }
        val content = parse(fetch.envelope)
        if (content == null || isEmpty(content)) {
            return if (rows.isNotEmpty()) ScreenState.Degraded(rows, content) else ScreenState.Empty(emptySentence)
        }
        val age = ageMs(fetch, nowMs)
        return when {
            age > staleThresholdMs -> ScreenState.Stale(age, content)
            rows.isNotEmpty() -> ScreenState.Degraded(rows, content)
            else -> ScreenState.Content(content)
        }
    }

    private fun <T> stale(last: DialDevFetch.Loaded, nowMs: Long, parse: (DialDevEnvelope) -> T?): ScreenState<T>? {
        val content = parse(last.envelope) ?: return null
        return ScreenState.Stale(ageMs(last, nowMs), content)
    }

    fun failure(fetch: DialDevFetch.Failed): ScreenState.Error {
        val code = errorCode(fetch.body)
        return when {
            fetch.httpStatus == 503 || code == "dial_dev_unavailable" -> ScreenState.Error(
                "DIAL's development projection is unreachable right now. Nothing here is guessed — try again shortly.",
                canRetry = true,
            )
            fetch.httpStatus == 401 || fetch.httpStatus == 403 -> ScreenState.Error(
                "This phone is not authorised to read DIAL development state.",
                canRetry = false,
            )
            fetch.httpStatus == 404 -> ScreenState.Error("DIAL has no record of this.", canRetry = false)
            fetch.httpStatus == null -> ScreenState.Error(
                fetch.message ?: "VAN could not reach its gateway.",
                canRetry = true,
            )
            else -> ScreenState.Error("DIAL answered ${fetch.httpStatus}. Try again.", canRetry = true)
        }
    }

    /** The `error`/`detail`/`code` string of a gateway error body, if it has one. */
    fun errorCode(body: String): String? {
        val json = try {
            JSONObject(body)
        } catch (_: JSONException) {
            return null
        }
        val detail = json.opt("detail")
        val nested = (detail as? JSONObject)?.optString("error")
        return listOf(json.optString("error"), json.optString("code"), nested, detail as? String)
            .firstOrNull { !it.isNullOrBlank() }
    }
}

internal fun JSONArray?.strings(): List<String> {
    if (this == null) return emptyList()
    return buildList {
        for (i in 0 until length()) {
            val value = opt(i)
            if (value is String && value.isNotBlank()) add(value)
        }
    }
}

internal fun JSONArray?.objects(): List<JSONObject> {
    if (this == null) return emptyList()
    return buildList {
        for (i in 0 until length()) {
            (opt(i) as? JSONObject)?.let(::add)
        }
    }
}
