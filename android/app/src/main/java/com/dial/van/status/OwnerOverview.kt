package com.dial.van.status

import org.json.JSONArray
import org.json.JSONObject

/**
 * What the owner's home screen says about what is waiting for them.
 *
 * P3-AND-003. `VanGatewayClient.attention()` and `briefing()` were declared and never
 * called: the gateway maintained an attention queue and built a briefing, and the app had
 * methods to fetch both and no surface that did. Two capabilities that existed end to end
 * apart from the last ten lines.
 *
 * The summarising lives here rather than in the composable for the usual reason: a
 * composable cannot be executed by `android/verification`, and every decision below — what
 * counts as needing the owner, what to say when nothing does, what to say when VAN could
 * not reach the gateway — is a decision worth holding to a test.
 *
 * The rule that shapes all of it: **an empty queue and an unreachable gateway must never
 * produce the same sentence.** "Nothing is waiting for you" is a claim about the world, and
 * VAN may only make it when it has looked.
 */
data class OwnerAttentionItem(
    val id: String,
    val title: String,
    val severity: String,
    val source: String,
    val needsOwner: Boolean,
)

data class OwnerOverviewSummary(
    val loaded: Boolean,
    val items: List<OwnerAttentionItem>,
    val headline: String,
    val briefingLine: String?,
    val error: String?,
) {
    val waitingCount: Int get() = items.count { it.needsOwner }
}

object OwnerOverview {

    /** Severities that mean the owner has to do something, not just be told. */
    val OWNER_SEVERITIES = setOf("BLOCKER", "URGENT")

    fun parseAttention(payload: JSONArray?): List<OwnerAttentionItem> {
        if (payload == null) return emptyList()
        val items = mutableListOf<OwnerAttentionItem>()
        for (index in 0 until payload.length()) {
            val row = payload.optJSONObject(index) ?: continue
            val severity = row.optString("severity", "INFO").uppercase()
            items += OwnerAttentionItem(
                id = row.optString("id", "attention-$index"),
                title = row.optString("title").ifBlank { "Untitled" },
                severity = severity,
                source = row.optString("source", "van"),
                needsOwner = severity in OWNER_SEVERITIES,
            )
        }
        // Blockers first, then by title so the order is stable between polls — a list that
        // reshuffles on every refresh is a list nobody trusts.
        return items.sortedWith(compareBy({ !it.needsOwner }, { it.title }))
    }

    /**
     * The one line from the briefing worth putting on the home screen.
     *
     * Null rather than a placeholder when the briefing says nothing: a card that always has
     * text trains the owner to stop reading it.
     */
    fun briefingLine(payload: JSONObject?): String? {
        if (payload == null) return null
        val headline = payload.optString("headline").trim()
        if (headline.isNotEmpty()) return headline
        val summary = payload.optString("summary").trim()
        return summary.ifEmpty { null }
    }

    fun summarize(
        attention: JSONArray?,
        briefing: JSONObject?,
        error: String? = null,
    ): OwnerOverviewSummary {
        if (error != null) {
            return OwnerOverviewSummary(
                loaded = false,
                items = emptyList(),
                // Never "nothing is waiting for you": VAN has not looked.
                headline = "VAN could not reach the gateway, so it cannot tell you what is waiting",
                briefingLine = null,
                error = error,
            )
        }
        val items = parseAttention(attention)
        val waiting = items.count { it.needsOwner }
        val headline = when {
            waiting == 1 -> "One thing is waiting for you"
            waiting > 1 -> "$waiting things are waiting for you"
            items.isNotEmpty() -> "Nothing needs you; ${items.size} for information"
            else -> "Nothing is waiting for you"
        }
        return OwnerOverviewSummary(
            loaded = true,
            items = items,
            headline = headline,
            briefingLine = briefingLine(briefing),
            error = null,
        )
    }
}
