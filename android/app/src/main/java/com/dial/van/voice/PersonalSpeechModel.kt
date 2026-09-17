package com.dial.van.voice

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import java.util.UUID
import kotlin.math.exp

enum class SpeechContext {
    GENERAL,
    VAN_SYSTEM,
    DIAL,
    DDE,
    VATI_TRADING,
    CONTACTS,
    LOCATIONS,
    GOOGLE_SERVICES,
}

enum class SpeechLearningTrust {
    OWNER_CONFIRMED,
    PROJECT_TRUTH,
    DETERMINISTIC_STATE,
    CONVERSATION,
    UNTRUSTED,
    SECRET,
}

data class SpeechConfusionEdge(
    val id: String,
    val observed: String,
    val corrected: String,
    val contexts: Set<SpeechContext>,
    val trust: SpeechLearningTrust,
    val correctionCount: Int,
    val lastConfirmedAtMs: Long,
    val pinned: Boolean,
)

/**
 * Owner-scoped speech memory. It is deterministic data, not an agent loop.
 * Only trusted/confirmed material may influence recognizer biasing.
 */
class PersonalSpeechModel(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context.applicationContext,
        PREFS,
        MasterKey.Builder(context.applicationContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    private val lock = Any()

    fun recordCorrection(
        observed: String,
        corrected: String,
        contexts: Set<SpeechContext>,
        trust: SpeechLearningTrust = SpeechLearningTrust.OWNER_CONFIRMED,
        nowMs: Long = System.currentTimeMillis(),
    ): Boolean {
        val from = normalize(observed)
        val to = corrected.trim()
        if (from.isBlank() || to.isBlank() || from.equals(to, ignoreCase = true)) return false
        if (!trust.mayTeach()) return false
        val scoped = contexts.ifEmpty { setOf(SpeechContext.GENERAL) }
        synchronized(lock) {
            val edges = loadMutable()
            val index = edges.indexOfFirst {
                it.observed == from && it.corrected.equals(to, ignoreCase = true) && it.contexts == scoped
            }
            val next = if (index >= 0) {
                val existing = edges[index]
                existing.copy(
                    trust = strongerTrust(existing.trust, trust),
                    correctionCount = (existing.correctionCount + 1).coerceAtMost(MAX_CORRECTION_COUNT),
                    lastConfirmedAtMs = nowMs,
                )
            } else {
                SpeechConfusionEdge(
                    id = UUID.randomUUID().toString(),
                    observed = from,
                    corrected = to,
                    contexts = scoped,
                    trust = trust,
                    correctionCount = 1,
                    lastConfirmedAtMs = nowMs,
                    pinned = false,
                )
            }
            if (index >= 0) edges[index] = next else edges += next
            persist(edges.sortedByDescending { score(it, scoped, nowMs) }.take(MAX_EDGES))
            return true
        }
    }

    fun pinTerm(term: String, context: SpeechContext = SpeechContext.GENERAL, nowMs: Long = System.currentTimeMillis()): Boolean {
        val value = term.trim()
        if (value.isBlank()) return false
        synchronized(lock) {
            val edges = loadMutable()
            val existing = edges.indexOfFirst {
                it.pinned && it.corrected.equals(value, ignoreCase = true) && context in it.contexts
            }
            if (existing >= 0) return true
            edges += SpeechConfusionEdge(
                id = UUID.randomUUID().toString(),
                observed = normalize(value),
                corrected = value,
                contexts = setOf(context),
                trust = SpeechLearningTrust.OWNER_CONFIRMED,
                correctionCount = MAX_CORRECTION_COUNT,
                lastConfirmedAtMs = nowMs,
                pinned = true,
            )
            persist(edges.takeLast(MAX_EDGES))
            return true
        }
    }

    fun biasingStrings(
        activeContexts: Set<SpeechContext>,
        nowMs: Long = System.currentTimeMillis(),
        limit: Int = DEFAULT_BIAS_LIMIT,
    ): List<String> {
        val contexts = activeContexts + SpeechContext.GENERAL + SpeechContext.VAN_SYSTEM
        return synchronized(lock) {
            loadMutable()
                .asSequence()
                .filter { it.trust.mayTeach() && it.contexts.any(contexts::contains) }
                .filter { it.pinned || ageMs(it, nowMs) <= MAX_UNPINNED_AGE_MS }
                .sortedByDescending { score(it, contexts, nowMs) }
                .map { it.corrected.trim() }
                .filter { it.isNotBlank() && it.length <= MAX_BIAS_TERM_LENGTH }
                .distinctBy { it.lowercase(Locale.ROOT) }
                .take(limit.coerceIn(1, MAX_BIAS_LIMIT))
                .toList()
        }
    }

    fun correctionFor(
        observed: String,
        activeContexts: Set<SpeechContext>,
        nowMs: Long = System.currentTimeMillis(),
    ): String? {
        val key = normalize(observed)
        if (key.isBlank()) return null
        val contexts = activeContexts + SpeechContext.GENERAL
        return synchronized(lock) {
            loadMutable()
                .asSequence()
                .filter { it.observed == key && it.trust.mayTeach() && it.contexts.any(contexts::contains) }
                .maxByOrNull { score(it, contexts, nowMs) }
                ?.corrected
        }
    }

    fun snapshot(): List<SpeechConfusionEdge> = synchronized(lock) { loadMutable().toList() }

    private fun loadMutable(): MutableList<SpeechConfusionEdge> {
        val raw = prefs.getString(KEY_GRAPH, null) ?: return mutableListOf()
        return runCatching {
            val array = JSONArray(raw)
            MutableList(array.length()) { index -> decode(array.getJSONObject(index)) }
        }.getOrDefault(mutableListOf())
    }

    private fun persist(edges: List<SpeechConfusionEdge>) {
        val array = JSONArray()
        edges.forEach { array.put(encode(it)) }
        prefs.edit().putString(KEY_GRAPH, array.toString()).apply()
    }

    private fun encode(edge: SpeechConfusionEdge): JSONObject = JSONObject()
        .put("id", edge.id)
        .put("observed", edge.observed)
        .put("corrected", edge.corrected)
        .put("contexts", JSONArray(edge.contexts.map { it.name }))
        .put("trust", edge.trust.name)
        .put("count", edge.correctionCount)
        .put("last", edge.lastConfirmedAtMs)
        .put("pinned", edge.pinned)

    private fun decode(value: JSONObject): SpeechConfusionEdge {
        val contextsJson = value.optJSONArray("contexts") ?: JSONArray()
        val contexts = buildSet {
            for (i in 0 until contextsJson.length()) {
                runCatching { SpeechContext.valueOf(contextsJson.getString(i)) }.getOrNull()?.let(::add)
            }
        }.ifEmpty { setOf(SpeechContext.GENERAL) }
        return SpeechConfusionEdge(
            id = value.optString("id").ifBlank { UUID.randomUUID().toString() },
            observed = normalize(value.optString("observed")),
            corrected = value.optString("corrected"),
            contexts = contexts,
            trust = runCatching { SpeechLearningTrust.valueOf(value.optString("trust")) }
                .getOrDefault(SpeechLearningTrust.CONVERSATION),
            correctionCount = value.optInt("count", 1).coerceIn(1, MAX_CORRECTION_COUNT),
            lastConfirmedAtMs = value.optLong("last", 0L),
            pinned = value.optBoolean("pinned", false),
        )
    }

    private fun score(edge: SpeechConfusionEdge, active: Set<SpeechContext>, nowMs: Long): Double {
        val contextWeight = if (edge.contexts.any(active::contains)) 4.0 else 0.0
        val trustWeight = when (edge.trust) {
            SpeechLearningTrust.OWNER_CONFIRMED -> 6.0
            SpeechLearningTrust.PROJECT_TRUTH -> 5.0
            SpeechLearningTrust.DETERMINISTIC_STATE -> 4.0
            SpeechLearningTrust.CONVERSATION -> 1.0
            SpeechLearningTrust.UNTRUSTED, SpeechLearningTrust.SECRET -> -100.0
        }
        val recency = if (edge.pinned) 3.0 else 3.0 * exp(-ageMs(edge, nowMs).toDouble() / DECAY_HALF_LIFE_MS)
        val frequency = edge.correctionCount.coerceAtMost(10) * 0.45
        return contextWeight + trustWeight + recency + frequency + if (edge.pinned) 20.0 else 0.0
    }

    private fun ageMs(edge: SpeechConfusionEdge, nowMs: Long): Long = (nowMs - edge.lastConfirmedAtMs).coerceAtLeast(0L)

    private fun normalize(value: String): String = value.trim().lowercase(Locale.ROOT).replace(WHITESPACE, " ")

    private fun SpeechLearningTrust.mayTeach(): Boolean = when (this) {
        SpeechLearningTrust.OWNER_CONFIRMED,
        SpeechLearningTrust.PROJECT_TRUTH,
        SpeechLearningTrust.DETERMINISTIC_STATE,
        -> true
        SpeechLearningTrust.CONVERSATION,
        SpeechLearningTrust.UNTRUSTED,
        SpeechLearningTrust.SECRET,
        -> false
    }

    private fun strongerTrust(a: SpeechLearningTrust, b: SpeechLearningTrust): SpeechLearningTrust =
        if (trustRank(a) >= trustRank(b)) a else b

    private fun trustRank(value: SpeechLearningTrust): Int = when (value) {
        SpeechLearningTrust.OWNER_CONFIRMED -> 5
        SpeechLearningTrust.PROJECT_TRUTH -> 4
        SpeechLearningTrust.DETERMINISTIC_STATE -> 3
        SpeechLearningTrust.CONVERSATION -> 2
        SpeechLearningTrust.UNTRUSTED -> 1
        SpeechLearningTrust.SECRET -> 0
    }

    companion object {
        private const val PREFS = "van_personal_speech_model"
        private const val KEY_GRAPH = "confusion_graph_v1"
        private const val MAX_EDGES = 256
        private const val MAX_CORRECTION_COUNT = 100
        private const val MAX_BIAS_LIMIT = 40
        private const val DEFAULT_BIAS_LIMIT = 32
        private const val MAX_BIAS_TERM_LENGTH = 64
        private const val MAX_UNPINNED_AGE_MS = 180L * 24L * 60L * 60L * 1000L
        private const val DECAY_HALF_LIFE_MS = 30.0 * 24.0 * 60.0 * 60.0 * 1000.0
        private val WHITESPACE = Regex("\\s+")
    }
}
