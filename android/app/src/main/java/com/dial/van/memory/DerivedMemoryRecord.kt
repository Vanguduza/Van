package com.dial.van.memory

import org.json.JSONObject

/** A privacy-screened record has an opaque identity and an exact persisted revision. */
data class DerivedMemoryRecord(val store: String, val id: String, val revision: String, val body: JSONObject) {
    fun matches(other: DerivedMemoryRecord): Boolean = store == other.store && id == other.id && revision == other.revision

    fun erasureCommand(plan: JSONObject): String {
        require(plan.optString("store") == store && plan.optString("record_id") == id &&
            plan.optString("revision_sha256") == revision) { "This record changed. Refresh and review its current contents." }
        require(plan.optString("action_class") == "A4") { "Individual erasure requires fresh owner approval." }
        val exact = "forget owner-derived memory record $store $id $revision"
        require(plan.optString("command_text") == exact) { "The record erasure plan does not match this exact record." }
        return exact
    }

    val sourceLabel: String get() = when (body.optString("source_class")) {
        "OWNER_DECLARED" -> "Declared by you"
        "OBSERVED" -> "Observed evidence"
        "INFERRED" -> "VAN's inference"
        "MIXED" -> "Owner declaration and observed evidence"
        else -> "Source classification not established"
    }

    companion object {
        fun parse(body: JSONObject): DerivedMemoryRecord {
            val store = body.optString("store")
            val id = body.optString("record_id")
            val revision = body.optString("revision_sha256")
            require(store.matches(Regex("[a-z_]{1,80}")) && id.matches(Regex("mr_[a-f0-9]{64}")) &&
                revision.matches(Regex("[a-f0-9]{64}"))) { "Memory record identity is invalid." }
            require(body.optBoolean("content_screened") && !body.optBoolean("execution_grant")) {
                "This record has no safe owner inspection contract."
            }
            return DerivedMemoryRecord(store, id, revision, body)
        }
    }
}
