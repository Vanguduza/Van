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
    val deploymentEnabled: Boolean,
    val circuit: String,
    val registryRevision: String?,
    val global: JevGlobalState,
    val modules: List<JevModule>,
    val providerConfigured: Boolean,
    val providerQualified: Boolean,
    val providerModels: List<String>,
)

data class JevActivityItem(
    val event: String,
    val moduleId: String,
    val requestId: String,
    val provider: String,
    val lifecycleState: String,
    val latencyMs: Int,
    val fallbackReason: String?,
    val observedAt: String,
)

data class JevPerformance(
    val projectId: String,
    val moduleId: String?,
    val decisions: Int,
    val providerDecisions: Int,
    val fallbacks: Int,
    val cacheHits: Int,
    val fallbackRate: Double,
    val cacheHitRate: Double,
    val p50LatencyMs: Double,
    val p95LatencyMs: Double,
    val p99LatencyMs: Double,
    val inputTokens: Int,
    val outputTokens: Int,
)

data class JevEvaluationProposal(
    val proposalId: String,
    val moduleId: String,
    val moduleRevision: String,
    val recommendation: String,
    val rationale: String,
    val proposerLineage: String,
    val status: String,
    val proposedAt: String,
)

data class JevEvaluationReview(
    val reviewId: String,
    val proposalId: String,
    val reviewerLineage: String,
    val decision: String,
    val rationale: String,
    val reviewedAt: String,
)

data class JevCandidateRevision(
    val candidateId: String,
    val proposalId: String,
    val moduleId: String,
    val baseModuleRevision: String,
    val candidateModuleRevision: String,
    val lifecycleState: String,
    val reviewerLineage: String,
    val createdAt: String,
)

data class JevSafetyBreach(
    val code: String,
    val value: Double,
    val threshold: Double,
    val samples: Int,
)

data class JevSafetySnapshot(
    val moduleId: String,
    val lifecycleState: String,
    val healthy: Boolean,
    val outcomeSamples: Int,
    val highConfidenceErrorRate: Double?,
    val falseRaiseRate: Double?,
    val reviewLoadPer100: Double?,
    val breaches: List<JevSafetyBreach>,
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
    fun snapshot(status: JSONObject, health: JSONObject, provider: JSONObject): JevServiceSnapshot {
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
            deploymentEnabled = health.optBoolean("deployment_enabled", health.optBoolean("enabled", false)),
            circuit = health.optString("circuit", "UNKNOWN"),
            registryRevision = status.optString("registry_revision").takeIf { it.isNotBlank() },
            global = JevGlobalState(
                ownerActive = globalJson.optBoolean("owner_active", true),
                bypassed = globalJson.optBoolean("bypassed", false),
                projects = projectMap,
            ),
            modules = modules,
            providerConfigured = provider.optBoolean("configured", false),
            providerQualified = provider.optBoolean("qualified", false),
            providerModels = buildList {
                val rows = provider.optJSONArray("models")
                if (rows != null) {
                    for (i in 0 until rows.length()) {
                        val row = rows.optJSONObject(i)
                        if (row != null) add(row.optString("name")) else add(rows.optString(i))
                    }
                }
            }.filter { it.isNotBlank() },
        )
    }

    fun activity(payload: JSONObject): List<JevActivityItem> {
        val items = payload.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until items.length()) {
                val row = items.optJSONObject(i) ?: continue
                add(
                    JevActivityItem(
                        event = row.optString("event"),
                        moduleId = row.optString("module_id"),
                        requestId = row.optString("request_id"),
                        provider = row.optString("provider"),
                        lifecycleState = row.optString("lifecycle_state"),
                        latencyMs = row.optInt("latency_ms", 0),
                        fallbackReason = row.optString("fallback_reason").takeIf { it.isNotBlank() },
                        observedAt = row.optString("observed_at"),
                    )
                )
            }
        }
    }

    fun performance(payload: JSONObject) = JevPerformance(
        projectId = payload.optString("project_id"),
        moduleId = payload.optString("module_id").takeIf { it.isNotBlank() },
        decisions = payload.optInt("decisions", 0),
        providerDecisions = payload.optInt("provider_decisions", 0),
        fallbacks = payload.optInt("fallbacks", 0),
        cacheHits = payload.optInt("cache_hits", 0),
        fallbackRate = payload.optDouble("fallback_rate", 0.0),
        cacheHitRate = payload.optDouble("cache_hit_rate", 0.0),
        p50LatencyMs = payload.optDouble("p50_latency_ms", 0.0),
        p95LatencyMs = payload.optDouble("p95_latency_ms", 0.0),
        p99LatencyMs = payload.optDouble("p99_latency_ms", 0.0),
        inputTokens = payload.optInt("input_tokens", 0),
        outputTokens = payload.optInt("output_tokens", 0),
    )

    fun proposals(payload: JSONObject): List<JevEvaluationProposal> {
        val items = payload.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until items.length()) {
                val row = items.optJSONObject(i) ?: continue
                add(
                    JevEvaluationProposal(
                        proposalId = row.optString("proposal_id"),
                        moduleId = row.optString("module_id"),
                        moduleRevision = row.optString("module_revision"),
                        recommendation = row.optString("recommendation"),
                        rationale = row.optString("rationale"),
                        proposerLineage = row.optString("proposer_lineage"),
                        status = row.optString("status"),
                        proposedAt = row.optString("proposed_at"),
                    )
                )
            }
        }
    }

    fun reviews(payload: JSONObject): List<JevEvaluationReview> {
        val items = payload.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until items.length()) {
                val row = items.optJSONObject(i) ?: continue
                add(
                    JevEvaluationReview(
                        reviewId = row.optString("review_id"),
                        proposalId = row.optString("proposal_id"),
                        reviewerLineage = row.optString("reviewer_lineage"),
                        decision = row.optString("decision"),
                        rationale = row.optString("rationale"),
                        reviewedAt = row.optString("reviewed_at"),
                    )
                )
            }
        }
    }

    fun candidates(payload: JSONObject): List<JevCandidateRevision> {
        val items = payload.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until items.length()) {
                val row = items.optJSONObject(i) ?: continue
                add(
                    JevCandidateRevision(
                        candidateId = row.optString("candidate_id"),
                        proposalId = row.optString("proposal_id"),
                        moduleId = row.optString("module_id"),
                        baseModuleRevision = row.optString("base_module_revision"),
                        candidateModuleRevision = row.optString("candidate_module_revision"),
                        lifecycleState = row.optString("lifecycle_state", "SHADOW"),
                        reviewerLineage = row.optString("reviewer_lineage"),
                        createdAt = row.optString("created_at"),
                    )
                )
            }
        }
    }

    fun safety(payload: JSONObject): JevSafetySnapshot {
        val breachesJson = payload.optJSONArray("breaches")
        val breaches = buildList {
            if (breachesJson != null) {
                for (i in 0 until breachesJson.length()) {
                    val row = breachesJson.optJSONObject(i) ?: continue
                    add(
                        JevSafetyBreach(
                            code = row.optString("code"),
                            value = row.optDouble("value", 0.0),
                            threshold = row.optDouble("threshold", 0.0),
                            samples = row.optInt("samples", 0),
                        )
                    )
                }
            }
        }
        fun nullableDouble(name: String): Double? =
            if (!payload.has(name) || payload.isNull(name)) null else payload.optDouble(name)

        return JevSafetySnapshot(
            moduleId = payload.optString("module_id"),
            lifecycleState = payload.optString("lifecycle_state"),
            healthy = payload.optBoolean("healthy", true),
            outcomeSamples = payload.optInt("outcome_samples", 0),
            highConfidenceErrorRate = nullableDouble("high_confidence_error_rate"),
            falseRaiseRate = nullableDouble("false_raise_rate"),
            reviewLoadPer100 = nullableDouble("review_load_per_100"),
            breaches = breaches,
        )
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
