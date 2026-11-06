package com.dial.van.memory

import org.json.JSONObject

/** A deterministic snapshot producer is measured evidence, never a new action grant. */
data class LearningProducer(val id: String, val status: String, val body: JSONObject) {
    val ownerStatus: String get() = when (status) {
        "READY" -> "Current evidence snapshot computed"
        "NO_DATA" -> "No qualifying observations"
        "PARTIAL" -> "Some observations could not be compared"
        "DEGRADED" -> "Current computation needs attention"
        else -> "Current producer state is unknown"
    }

    companion object {
        fun parse(body: JSONObject): LearningProducer {
            require(!body.optBoolean("execution_grant")) { "Learning evidence cannot grant execution authority." }
            return LearningProducer(body.optString("id"), body.optString("status"), body)
        }
    }
}
