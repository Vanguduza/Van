package com.dial.van.trading

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

/**
 * Owner-visible strategy-promotion read model.
 *
 * A row exists only when the gateway/commander has a policy-passing, durable
 * StrategyValidationCertificate whose capsule_hash still matches the current
 * capsule lineage. It is evidence for an owner decision, never an automatic
 * recommendation or authority grant.
 */
data class StrategyPromotionCandidate(
    val strategyId: String,
    val currentState: String,
    val targetState: String,
    val capsuleHash: String,
    val validationHash: String,
    val certificateId: String,
    val certificate: JsonObject,
    val evidenceRefs: List<String>,
    val dataManifestHash: String?,
    val dsrProbability: Double?,
    val pboProbability: Double?,
    val expectancyR: Double?,
    val expectancyLowerBoundR: Double?,
    val profitFactor: Double?,
    val maxDrawdown: Double?,
    val certificateEventHash: String?,
    val certificateEventMs: Long?,
) {
    companion object {
        fun from(o: JsonObject): StrategyPromotionCandidate? {
            val certificate = o.obj("certificate") ?: return null
            val strategyId = o.str("strategy_id")?.takeIf { it.isNotBlank() } ?: return null
            val currentState = o.str("current_state")?.takeIf { it.isNotBlank() } ?: return null
            val targetState = o.str("target_state")?.takeIf { it.isNotBlank() } ?: return null
            val capsuleHash = o.str("capsule_hash")?.takeIf { it.isNotBlank() } ?: return null
            val validationHash = o.str("validation_hash")?.takeIf { it.isNotBlank() } ?: return null
            return StrategyPromotionCandidate(
                strategyId = strategyId,
                currentState = currentState,
                targetState = targetState,
                capsuleHash = capsuleHash,
                validationHash = validationHash,
                certificateId = o.str("certificate_id") ?: "?",
                certificate = certificate,
                evidenceRefs = o.strList("evidence_refs"),
                dataManifestHash = o.str("data_manifest_hash"),
                dsrProbability = o.num("dsr_probability"),
                pboProbability = o.num("pbo_probability"),
                expectancyR = o.num("expectancy_R"),
                expectancyLowerBoundR = o.num("expectancy_lower_bound_R"),
                profitFactor = o.num("profit_factor"),
                maxDrawdown = o.num("max_drawdown"),
                certificateEventHash = o.str("certificate_event_hash"),
                certificateEventMs = o.long("certificate_event_ms"),
            )
        }

        fun parseAll(body: String): List<StrategyPromotionCandidate>? {
            val root = parseObject(body) ?: return null
            val rows = root["candidates"] as? JsonArray ?: return null
            return rows.mapNotNull { (it as? JsonObject)?.let(::from) }
        }
    }
}

/** Result shown only after the gateway returns the ledger-backed promotion event. */
data class StrategyPromotionResult(
    val strategyId: String,
    val from: String,
    val to: String,
    val capsuleHash: String,
    val validationHash: String,
    val eventHash: String,
    val registryProjection: String?,
    val requiresSessionRestart: Boolean,
) {
    companion object {
        fun parse(body: String): StrategyPromotionResult? {
            val o = parseObject(body) ?: return null
            if (o.bool("promoted") != true) return null
            return StrategyPromotionResult(
                strategyId = o.str("strategy_id") ?: return null,
                from = o.str("from") ?: return null,
                to = o.str("to") ?: return null,
                capsuleHash = o.str("capsule_hash") ?: return null,
                validationHash = o.str("validation_hash") ?: return null,
                eventHash = o.str("event_hash") ?: return null,
                registryProjection = o.str("registry_projection"),
                requiresSessionRestart = o.bool("requires_session_restart") ?: false,
            )
        }
    }
}
