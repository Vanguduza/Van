package com.dial.van.memory

/** Observed erasure receipt, distinct from command admission and biometric challenge. */
data class MemoryEffectReceipt(
    val removedCounts: Map<String, Long>,
    val evidenceRef: String,
    val retainedReasons: List<String>,
) {
    fun mayRender(commandSucceeded: Boolean): Boolean = commandSucceeded

    companion object {
        private val stores = setOf("owner_facts", "owner_context_edges", "owner_cognitive_model",
            "reasoning_assessments", "symbiotic_growth", "strategic_memory", "decision_fingerprints",
            "shared_vocabulary", "intent_edges", "intent_nodes", "intent_missions")

        fun observed(actionId: String, verificationState: String, removedCounts: Map<String, Long>,
                     affectedStores: Set<String>, evidenceRef: String, retainedReasons: List<String>): MemoryEffectReceipt? {
            if (actionId != "memory.erase" || verificationState != "VERIFIED_SUCCESS" || evidenceRef.isBlank()) return null
            if (removedCounts.isEmpty() || removedCounts.keys != affectedStores || !stores.containsAll(affectedStores)) return null
            if (removedCounts.values.any { it < 0L }) return null
            return MemoryEffectReceipt(removedCounts.toMap(), evidenceRef, retainedReasons.filter { it.isNotBlank() })
        }
    }
}
