package com.dial.van.memory

import com.dial.van.design.StatusSemantics
import org.json.JSONArray
import org.json.JSONObject

/**
 * DNA §4 destination 5 (Memory): "facts, decisions, assumptions, preferences, unresolved
 * threads, provenance; add/correct/forget." Pure Kotlin — no Android, no Compose — so the
 * question "given this `/v1/context/export` and `/v1/context/conflicts` response, what does
 * the owner see" has one answer and it is asserted on the JVM (`android/verification`),
 * rather than only reasoned about while looking at a screenshot.
 *
 * `backend/van_gateway/context/models.py`'s `OwnerFactRecord` is the wire shape this reads:
 * a fact carries its own authority (epistemic tier), who/what is trusted to have said it
 * (`source_trust`), a validity window and a confidence in permille. Nothing here invents a
 * field the gateway did not send — an absent field reads as the row's own honest default
 * (`""`, `0`, `1000` permille), never a fixture value.
 */
data class MemoryFact(
    val factId: String,
    val subject: String,
    val predicate: String,
    val value: String,
    /** Raw `EpistemicState` value, e.g. `"CANONICAL_OWNER"`, `"PROJECT_TRUTH"`, `"INFERRED"`. */
    val authority: String,
    /** Raw `SourceTrust` value, e.g. `"OWNER_EXPLICIT"`, `"TRUSTED_OWNER_FILE"`. */
    val sourceTrust: String,
    val sourceRef: String,
    val scope: String,
    val validFromMs: Long,
    val validUntilMs: Long?,
    val observedAtMs: Long,
    val confidencePermille: Int,
    val supersedesFactId: String?,
) {
    /** `command/resolver.py`'s `memory.decision.record` always writes this predicate. */
    val isDecision: Boolean get() = predicate == "decision"

    /** `command/resolver.py`'s unstructured "remember that …" fallback predicate. */
    val isStatement: Boolean get() = predicate == "statement"

    /** DNA §2: never a raw permille on screen — confidence reads as a percentage. */
    val confidencePercent: Int get() = (confidencePermille.coerceIn(0, 1000)) / 10
}

/** DNA §4's Memory grammar names four provenance chips; every `EpistemicState` maps to one. */
enum class ProvenanceTier { CANONICAL_OWNER, PROJECT_TRUTH, VERIFIED, INFERRED }

object ProvenanceTiers {
    private val VERIFIED_AUTHORITIES = setOf(
        "VERIFIED_LIVE_STATE", "VERIFIED_HISTORY", "CONFIRMED_LEARNED", "EXTERNAL_EVIDENCE",
    )

    /**
     * `STALE`/`CONFLICTED`/`UNKNOWN` are not `INFERRED` in `context/models.py`'s own ladder,
     * but none of them is a claim VAN is confident enough to call CANONICAL_OWNER,
     * PROJECT_TRUTH or VERIFIED either — they read as INFERRED (least-certain) on this
     * four-chip grammar rather than growing a fifth chip DNA §4 does not name. The unmapped
     * `else` branch below folds any future `EpistemicState` value the same way, on purpose:
     * a tier this build has never heard of is exactly the case that should read as
     * "unconfirmed", not silently vanish into one of the confident tiers.
     */
    fun forAuthority(authority: String): ProvenanceTier = when (authority) {
        "CANONICAL_OWNER" -> ProvenanceTier.CANONICAL_OWNER
        "PROJECT_TRUTH" -> ProvenanceTier.PROJECT_TRUTH
        in VERIFIED_AUTHORITIES -> ProvenanceTier.VERIFIED
        else -> ProvenanceTier.INFERRED
    }

    /** `StatusSemantics` role name, so a fact's chip never invents its own colour. */
    fun statusRole(tier: ProvenanceTier): String = when (tier) {
        ProvenanceTier.CANONICAL_OWNER -> StatusSemantics.ROLE_FAVOURABLE
        ProvenanceTier.PROJECT_TRUTH -> StatusSemantics.ROLE_FAVOURABLE
        ProvenanceTier.VERIFIED -> StatusSemantics.ROLE_MONITOR
        ProvenanceTier.INFERRED -> StatusSemantics.ROLE_HYPOTHESIS
    }
}

/** A fact's freshness against `valid_until_ms`, independent of its provenance tier. */
enum class FactFreshness { NO_EXPIRY, CURRENT, EXPIRING_SOON, EXPIRED }

object MemoryFreshness {
    /** DNA has no stated window for this; a week is the same order of magnitude as
     *  `LiveBadge`'s own staleness read and gives the owner real notice before a fact lapses. */
    const val EXPIRING_SOON_WINDOW_MS = 7L * 24 * 60 * 60 * 1000L

    fun classify(fact: MemoryFact, nowMs: Long): FactFreshness {
        val until = fact.validUntilMs ?: return FactFreshness.NO_EXPIRY
        return when {
            until <= nowMs -> FactFreshness.EXPIRED
            until - nowMs <= EXPIRING_SOON_WINDOW_MS -> FactFreshness.EXPIRING_SOON
            else -> FactFreshness.CURRENT
        }
    }
}

/** One side of a claim VAN holds two contradictory answers to (`GET /v1/context/conflicts`). */
data class MemoryConflictSide(
    val factId: String,
    val value: String,
    val authority: String,
    val sourceTrust: String,
    val observedAtMs: Long,
)

data class MemoryConflict(
    val subject: String,
    val predicate: String,
    val scope: String,
    val sides: List<MemoryConflictSide>,
    /** `blocking` conflicts would trip a default context requirement; `inferred_only` ones
     *  only appear once inferences are admitted (`context/lifecycle.py`'s own split). */
    val blocking: Boolean,
)

/** "Things I'm unsure about": conflicts VAN holds, and facts trending toward expiry. */
data class MemoryUncertainty(
    val conflicts: List<MemoryConflict>,
    val staleOrExpiring: List<MemoryFact>,
) {
    val isEmpty: Boolean get() = conflicts.isEmpty() && staleOrExpiring.isEmpty()
}

/**
 * `GET /v1/context/export` → typed rows, grouping, freshness and conflict pairing. The one
 * place a Memory screen turns the gateway's export/conflicts payloads into what DNA §4's
 * five sections show, so a screen and a JVM test read the same decision.
 */
object MemoryReadModel {

    /** Facts VAN currently holds — excludes anything already superseded/forgotten. */
    private const val RECENT_CHANGES_LIMIT = 30

    /** `context/lifecycle.py::ContextLifecycle.export`'s shape: `stores.owner_facts.records`. */
    fun parseExportFacts(export: JSONObject): List<MemoryFact> {
        val records = export.optJSONObject("stores")
            ?.optJSONObject("owner_facts")
            ?.optJSONArray("records")
            ?: return emptyList()
        return (0 until records.length()).mapNotNull { index ->
            val row = records.optJSONObject(index) ?: return@mapNotNull null
            val factId = row.optString("fact_id")
            if (factId.isBlank()) return@mapNotNull null
            MemoryFact(
                factId = factId,
                subject = row.optString("subject"),
                predicate = row.optString("predicate"),
                value = stringifyValue(row.opt("value")),
                authority = row.optString("authority", "UNKNOWN"),
                sourceTrust = row.optString("source_trust", "UNTRUSTED_EXTERNAL"),
                sourceRef = row.optString("source_ref"),
                scope = row.optString("scope", "global"),
                validFromMs = row.optLong("valid_from_ms", 0L),
                validUntilMs = optLongOrNull(row, "valid_until_ms"),
                observedAtMs = row.optLong("observed_at_ms", row.optLong("valid_from_ms", 0L)),
                confidencePermille = row.optInt("confidence_permille", 1000),
                supersedesFactId = row.optString("supersedes_fact_id").ifBlank { null },
            )
        }
    }

    /** `context/lifecycle.py::ContextLifecycle.conflicts`'s `{blocking, inferred_only}` shape. */
    fun parseConflicts(conflicts: JSONObject): List<MemoryConflict> =
        parseConflictArray(conflicts.optJSONArray("blocking"), blocking = true) +
            parseConflictArray(conflicts.optJSONArray("inferred_only"), blocking = false)

    private fun parseConflictArray(array: JSONArray?, blocking: Boolean): List<MemoryConflict> {
        array ?: return emptyList()
        return (0 until array.length()).mapNotNull { index ->
            val row = array.optJSONObject(index) ?: return@mapNotNull null
            val sidesArray = row.optJSONArray("sides")
            val sides = if (sidesArray == null) emptyList() else (0 until sidesArray.length()).mapNotNull { j ->
                val side = sidesArray.optJSONObject(j) ?: return@mapNotNull null
                MemoryConflictSide(
                    factId = side.optString("fact_id"),
                    value = stringifyValue(side.opt("value")),
                    authority = side.optString("authority"),
                    sourceTrust = side.optString("source_trust"),
                    observedAtMs = side.optLong("observed_at_ms", 0L),
                )
            }
            MemoryConflict(
                subject = row.optString("subject"),
                predicate = row.optString("predicate"),
                scope = row.optString("scope", "global"),
                sides = sides,
                blocking = blocking,
            )
        }
    }

    private fun isCurrentlyValid(fact: MemoryFact, nowMs: Long): Boolean =
        fact.validFromMs <= nowMs && (fact.validUntilMs == null || fact.validUntilMs > nowMs)

    /** "What I know about you": every currently-valid non-decision fact, grouped by scope. */
    fun factsByScope(facts: List<MemoryFact>, nowMs: Long): Map<String, List<MemoryFact>> =
        facts.asSequence()
            .filter { !it.isDecision && isCurrentlyValid(it, nowMs) }
            .sortedBy { it.predicate }
            .groupBy { it.scope }
            .toSortedMap()

    /** "Decisions you made": `predicate == "decision"`, newest first. */
    fun decisions(facts: List<MemoryFact>, nowMs: Long): List<MemoryFact> =
        facts.filter { it.isDecision && isCurrentlyValid(it, nowMs) }
            .sortedByDescending { it.validFromMs }

    /**
     * "Preferences": the structured "my X is Y" facts (a named predicate/value pair), as
     * opposed to the generic freeform "statement" catch-all or a recorded decision. Still
     * currently valid — a preference the owner forgot is not one they hold any more.
     */
    fun preferences(facts: List<MemoryFact>, nowMs: Long): List<MemoryFact> =
        facts.filter { !it.isDecision && !it.isStatement && isCurrentlyValid(it, nowMs) }
            .sortedBy { it.predicate }

    /** "Recent changes": every fact (including ended and decision ones), newest state first. */
    fun recentChanges(facts: List<MemoryFact>, limit: Int = RECENT_CHANGES_LIMIT): List<MemoryFact> =
        facts.sortedByDescending { it.validFromMs }.take(limit)

    /** Facts VAN holds with a shaken authority, or trending toward expiry, still in force. */
    fun staleOrExpiringFacts(facts: List<MemoryFact>, nowMs: Long): List<MemoryFact> =
        facts.filter { fact ->
            isCurrentlyValid(fact, nowMs) &&
                (fact.authority in SHAKEN_AUTHORITIES ||
                    MemoryFreshness.classify(fact, nowMs) == FactFreshness.EXPIRING_SOON)
        }.sortedWith(compareBy({ it.validUntilMs ?: Long.MAX_VALUE }, { it.predicate }))

    /** "Things I'm unsure about": conflicts plus stale/expiring facts, one section. */
    fun uncertainty(facts: List<MemoryFact>, conflicts: List<MemoryConflict>, nowMs: Long): MemoryUncertainty =
        MemoryUncertainty(conflicts = conflicts, staleOrExpiring = staleOrExpiringFacts(facts, nowMs))

    private val SHAKEN_AUTHORITIES = setOf("STALE", "CONFLICTED", "UNKNOWN")

    private fun optLongOrNull(row: JSONObject, key: String): Long? =
        if (!row.has(key) || row.isNull(key)) null else row.optLong(key)

    private fun stringifyValue(raw: Any?): String = when (raw) {
        null, JSONObject.NULL -> ""
        is String -> raw
        is Boolean -> raw.toString()
        is Number -> {
            val long = raw.toLong()
            if (raw.toDouble() == long.toDouble()) long.toString() else raw.toString()
        }
        else -> raw.toString()
    }
}
