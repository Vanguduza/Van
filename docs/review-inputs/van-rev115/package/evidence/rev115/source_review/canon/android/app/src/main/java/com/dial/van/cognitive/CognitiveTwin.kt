package com.dial.van.cognitive

import java.time.Instant
import org.json.JSONArray
import org.json.JSONObject

data class TwinRecord(val id: String, val authority: String, val classification: String, val summary: String, val evidenceRefs: List<String>)

data class CognitiveTwin(
    val twinId: String, val kind: String, val scopeId: String,
    val repositorySha: String, val projectTruthHash: String,
    val projectionRevision: String, val machineFactsHash: String,
    val generatedAtMs: Long, val expiresAtMs: Long, val sourceFreshness: String,
    val facts: List<TwinRecord>, val derivedState: List<TwinRecord>, val attention: List<TwinRecord>,
    val observations: List<TwinRecord>, val hypotheses: List<TwinRecord>, val annotations: List<TwinRecord>,
) {
    fun staleAt(nowMs: Long): Boolean = sourceFreshness != "CURRENT" || nowMs < generatedAtMs || nowMs >= expiresAtMs
    companion object {
        fun parse(body: String): CognitiveTwin? = runCatching {
            val envelope = JSONObject(body)
            if (envelope.optString("state") != "AVAILABLE") return null
            val projection = envelope.getJSONObject("projection")
            if (projection.getInt("schema_version") != 1) return null
            fun records(array: JSONArray?): List<TwinRecord> = (0 until (array?.length() ?: 0)).map { index ->
                val row = array!!.getJSONObject(index)
                val classification = row.getString("classification")
                require(classification == "PUBLIC" || classification == "INTERNAL_SANITIZED")
                val evidence = row.optJSONArray("evidence_refs")
                TwinRecord(row.getString("id"), row.optString("authority", "DERIVED"), classification,
                    listOf("summary", "state", "hypothesis", "repository_sha", "artifact_hash")
                        .firstNotNullOfOrNull { key -> if (row.has(key)) row.get(key).toString() else null } ?: row.getString("id"),
                    (0 until (evidence?.length() ?: 0)).map { evidence!!.getString(it) })
            }
            val freshness = projection.getJSONObject("freshness")
            val synthesis = projection.getJSONObject("dot_synthesis")
            CognitiveTwin(projection.getString("twin_id"), projection.getString("twin_kind"), projection.getString("scope_id"),
                projection.getString("repository_sha"), projection.getString("project_truth_hash"),
                projection.getString("projection_revision"), projection.getString("machine_facts_hash"),
                Instant.parse(projection.getString("generated_at")).toEpochMilli(),
                Instant.parse(freshness.getString("expires_at")).toEpochMilli(), freshness.getString("state"),
                records(projection.optJSONArray("facts")), records(projection.optJSONArray("derived_current_state")),
                records(projection.optJSONArray("attention")), records(synthesis.optJSONArray("observations")),
                records(synthesis.optJSONArray("hypotheses")), records(projection.optJSONArray("owner_annotations")))
        }.getOrNull()
        fun unavailableReason(body: String): String = runCatching { JSONObject(body).optString("reason", "TWIN_UNAVAILABLE") }.getOrDefault("TWIN_UNAVAILABLE")
    }
}
