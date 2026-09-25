package com.dial.van.command.jev

import org.json.JSONObject

data class JevGlobalState(
    val ownerActive: Boolean = false,
    val bypassed: Boolean = false,
    val projects: Map<String, Boolean> = emptyMap(),
)

data class JevModule(
    val id: String,
    val ownerSystem: String,
    val projects: List<String>,
    val status: String,
    val effectDirection: String,
    val consequence: String,
    val deadlineMs: Int,
    val fallbackClass: String,
    val shadowRequired: Boolean,
)

data class JevServiceSnapshot(
    val serviceEnabled: Boolean,
    val circuit: String,
    val registryRevision: String?,
    val global: JevGlobalState,
    val modules: List<JevModule>,
)

data class JevOutcome(
    val moduleId: String,
    val requestId: String,
    val source: String,
    val success: Boolean,
    val outcomeQuality: Double?,
    val observedAt: String,
    val evidenceRefs: List<String>,
)

data class JevContribution(
    val moduleId: String,
    val sampleCount: Int,
    val outcomeDelta: Double,
    val costSavings: Double,
    val latencySavingsMs: Double,
    val capacityValue: Double,
    val errorCost: Double,
    val operationalCost: Double,
    val complexityPenalty: Double,
    val composite: Double,
)

internal object JevJson {
    fun snapshot(status: JSONObject, health: JSONObject): JevServiceSnapshot {
        val globalJson = status.optJSONObject("global") ?: JSONObject()
        val projectsJson = globalJson.optJSONObject("projects") ?: JSONObject()
        val projectMap = buildMap {
            projectsJson.keys().forEach { key -> put(key, projectsJson.optBoolean(key, true)) }
        }
        val modulesArray = status.optJSONArray("modules")
        val modules = buildList {
            if (modulesArray != null) {
                for (i in 0 until modulesArray.length()) {
                    val item = modulesArray.optJSONObject(i) ?: continue
                    val scope = item.optJSONArray("project_scope")
                    val projects = buildList {
                        if (scope != null) for (j in 0 until scope.length()) add(scope.optString(j))
                    }
                    val fallback = item.optJSONObject("fallback") ?: JSONObject()
                    val evaluation = item.optJSONObject("evaluation") ?: JSONObject()
                    add(
                        JevModule(
                            id = item.optString("module_id"),
                            ownerSystem = item.optString("owner_system"),
                            projects = projects,
                            status = item.optString("status", "DISABLED"),
                            effectDirection = item.optString("effect_direction"),
                            consequence = item.optString("consequence"),
                            deadlineMs = item.optInt("deadline_ms", 0),
                            fallbackClass = fallback.optString("class", "ABSTAIN"),
                            shadowRequired = evaluation.optBoolean("shadow_required", true),
                        )
                    )
                }
            }
        }
        return JevServiceSnapshot(
            serviceEnabled = health.optBoolean("enabled", false),
            circuit = health.optString("circuit", "UNKNOWN"),
            registryRevision = status.optString("registry_revision").takeIf { it.isNotBlank() },
            global = JevGlobalState(
                ownerActive = globalJson.optBoolean("owner_active", true),
                bypassed = globalJson.optBoolean("bypassed", false),
                projects = projectMap,
            ),
            modules = modules,
        )
    }

    fun outcomes(payload: JSONObject): List<JevOutcome> {
        val items = payload.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until items.length()) {
                val row = items.optJSONObject(i) ?: continue
                val evidence = row.optJSONArray("evidence_refs")
                val refs = buildList {
                    if (evidence != null) for (j in 0 until evidence.length()) add(evidence.optString(j))
                }
                add(
                    JevOutcome(
                        moduleId = row.optString("module_id"),
                        requestId = row.optString("request_id"),
                        source = row.optString("source"),
                        success = row.optBoolean("success", false),
                        outcomeQuality = if (row.has("outcome_quality")) row.optDouble("outcome_quality") else null,
                        observedAt = row.optString("observed_at"),
                        evidenceRefs = refs,
                    )
                )
            }
        }
    }

    fun contribution(moduleId: String, payload: JSONObject) = JevContribution(
        moduleId = moduleId,
        sampleCount = payload.optInt("sample_count", 0),
        outcomeDelta = payload.optDouble("outcome_delta", 0.0),
        costSavings = payload.optDouble("cost_savings", 0.0),
        latencySavingsMs = payload.optDouble("latency_savings_ms", 0.0),
        capacityValue = payload.optDouble("capacity_value", 0.0),
        errorCost = payload.optDouble("error_cost", 0.0),
        operationalCost = payload.optDouble("operational_cost", 0.0),
        complexityPenalty = payload.optDouble("complexity_penalty", 0.0),
        composite = payload.optDouble("composite", 0.0),
    )
}
